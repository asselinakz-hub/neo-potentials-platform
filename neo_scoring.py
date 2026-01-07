#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
NEO Potentials — Scoring Engine

Input:
  1) neo_blocks.json   (твои 4 блока с вопросами)
  2) neo_answers.json  (ответы клиента)

Output:
  - JSON-отчет в stdout
  - человекочитаемая таблица матрицы 3×3

Usage:
  python neo_scoring.py --blocks neo_blocks.json --answers neo_answers.json --out report.json

Answers format (пример):
{
  "respondent_id": "client_001",
  "answers": {
    "b1_q1": { "selected": ["Янтарь","Гелиодор","Аметист"], "text": "..." },
    "b1_q2": { "selected": ["Гелиодор"] },
    "b2_q12": { "text": "3 факта..." }
  }
}

Supported question types:
  - single_choice / single_select
  - multi_choice / multi_select
  - text

Scoring rules (по умолчанию):
  - multi_choice: вес делится на кол-во выбранных
  - invert_score: начисление идет в минус с множителем 0.8 (как в твоей методике)
  - block3: выбранное = слабость (row3), reverse_items уменьшают слабость (валидация)
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Optional


POTENTIALS_RU = [
    "Янтарь", "Шунгит", "Цитрин",
    "Изумруд", "Рубин", "Гранат",
    "Сапфир", "Гелиодор", "Аметист",
]

COLUMNS = ["perception", "motivation", "instrument"]


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def safe_get_selected(ans_obj: Any) -> List[str]:
    """
    ans_obj can be:
      - {"selected": ["..."]} or {"selected": "..."} or {"value": "..."} etc.
    """
    if ans_obj is None:
        return []
    if isinstance(ans_obj, dict):
        if "selected" in ans_obj:
            sel = ans_obj["selected"]
        elif "value" in ans_obj:
            sel = ans_obj["value"]
        else:
            return []
    else:
        sel = ans_obj

    if isinstance(sel, list):
        return [str(x) for x in sel]
    if isinstance(sel, str):
        return [sel]
    return []


def clamp_floor(x: float, floor: float = 0.0) -> float:
    return x if x >= floor else floor


@dataclass
class PotentialScore:
    strength: float = 0.0   # row1 candidates
    weakness: float = 0.0   # row3 candidates
    # row2 будет вычисляться остатком
    col_points: Dict[str, float] = None

    def __post_init__(self):
        if self.col_points is None:
            self.col_points = {c: 0.0 for c in COLUMNS}


def question_type(q: Dict[str, Any]) -> str:
    return str(q.get("type", "")).strip().lower()


def is_multi(q: Dict[str, Any]) -> bool:
    t = question_type(q)
    return t in ("multi_choice", "multi_select", "multiple_choice", "checkbox")


def is_single(q: Dict[str, Any]) -> bool:
    t = question_type(q)
    return t in ("single_choice", "single_select", "radio")


def normalize_potential_name(p: str) -> Optional[str]:
    # Иногда люди случайно пишут "Гелиodор" и т.п.
    if not isinstance(p, str):
        return None
    p2 = p.strip()

    # быстрые фиксы опечаток
    p2 = p2.replace("Гелиodор", "Гелиодор").replace("Гелиodor", "Гелиодор")

    # если потенциально пришло англ. — можно расширить позже
    if p2 in POTENTIALS_RU:
        return p2
    return None


def score_blocks(blocks_json: Dict[str, Any], answers_json: Dict[str, Any]) -> Dict[str, Any]:
    blocks = blocks_json.get("blocks", [])
    answers_map: Dict[str, Any] = answers_json.get("answers", answers_json.get("responses", answers_json))

    # init
    scores: Dict[str, PotentialScore] = {p: PotentialScore() for p in POTENTIALS_RU}

    # defaults
    invert_multiplier_default = 0.8

    # process
    for blk in blocks:
        blk_id = blk.get("block_id", "")
        scoring_rules = blk.get("scoring_rules", {}) or {}
        reverse_items = set(scoring_rules.get("reverse_items", []) or [])
        anti_weight_multiplier = float(scoring_rules.get("anti_weight_multiplier", 1.0) or 1.0)

        for q in blk.get("questions", []):
            qid = q.get("id")
            if not qid:
                continue

            w = float(q.get("weight", 1.0) or 1.0)
            col = q.get("column")  # may be None for some blocks/questions
            invert_score = bool(q.get("invert_score", False))

            # get selected
            ans_obj = answers_map.get(qid)
            selected_raw = safe_get_selected(ans_obj)
            selected = [normalize_potential_name(x) for x in selected_raw]
            selected = [x for x in selected if x is not None]

            # text-only questions: optional keyword scoring later
            if not selected and not (is_single(q) or is_multi(q)):
                continue

            # split for multi-choice
            if len(selected) == 0:
                continue
            per_item = w / len(selected) if is_multi(q) else w

            # sign logic
            # Block3: weakness direction by default
            is_block3 = str(blk_id).lower().startswith("block3") or str(blk_id).lower().endswith("antipatterns")
            row_target = q.get("row_target", None)  # weakness / validation_reverse / etc.

            if is_block3:
                # weakness scoring
                # reverse items: reduce weakness (internal validation)
                sign = -1.0 if qid in reverse_items or row_target == "validation_reverse" else 1.0
                pts = per_item * anti_weight_multiplier * sign
                for p in selected:
                    scores[p].weakness += pts
                continue

            # Blocks 1,2,4: strength scoring (+) with optional invert
            if invert_score:
                pts = -per_item * invert_multiplier_default
            else:
                pts = per_item

            for p in selected:
                scores[p].strength += pts
                if col in COLUMNS:
                    scores[p].col_points[col] += pts

    # normalize weakness floor (не даём уходить в минус из-за reverse-валидации)
    for p in POTENTIALS_RU:
        scores[p].weakness = clamp_floor(scores[p].weakness, 0.0)

    # pick rows
    # Row3 = top3 weaknesses
    row3 = sorted(POTENTIALS_RU, key=lambda p: scores[p].weakness, reverse=True)[:3]

    # Row1 = top3 strengths excluding row3
    row1_candidates = [p for p in POTENTIALS_RU if p not in row3]
    row1 = sorted(row1_candidates, key=lambda p: scores[p].strength, reverse=True)[:3]

    # Row2 = remaining
    row2 = [p for p in POTENTIALS_RU if p not in row1 and p not in row3]

    def dominant_column(p: str) -> str:
        cp = scores[p].col_points
        best = max(COLUMNS, key=lambda c: cp.get(c, 0.0))
        # если всё 0 — вернем perception по умолчанию
        if all(abs(cp.get(c, 0.0)) < 1e-9 for c in COLUMNS):
            return "perception"
        return best

    def order_row_by_columns(row: List[str]) -> Dict[str, Optional[str]]:
        # пытаемся разложить 1 в 1 по perception/motivation/instrument
        remaining = set(row)
        slots: Dict[str, Optional[str]] = {c: None for c in COLUMNS}

        # 1) сначала кладем тех, у кого сильнее всего выражен конкретный столбец
        for c in COLUMNS:
            best_p = None
            best_val = -1e18
            for p in remaining:
                val = scores[p].col_points.get(c, 0.0)
                if val > best_val:
                    best_val = val
                    best_p = p
            if best_p is not None:
                slots[c] = best_p
                remaining.remove(best_p)

        # 2) если еще остались (на всякий случай), докидываем по силе
        if remaining:
            leftovers = sorted(list(remaining), key=lambda p: scores[p].strength, reverse=True)
            for c in COLUMNS:
                if slots[c] is None and leftovers:
                    slots[c] = leftovers.pop(0)

        return slots

    matrix = {
        "row1_strengths": order_row_by_columns(row1),
        "row2_energy": order_row_by_columns(row2),
        "row3_weaknesses": order_row_by_columns(row3),
    }

    # prepare output
    out = {
        "respondent_id": answers_json.get("respondent_id"),
        "scores": {
            p: {
                "strength": round(scores[p].strength, 4),
                "weakness": round(scores[p].weakness, 4),
                "columns": {c: round(scores[p].col_points[c], 4) for c in COLUMNS},
                "dominant_column": dominant_column(p),
            }
            for p in POTENTIALS_RU
        },
        "rows": {
            "row1_strengths": row1,
            "row2_energy": row2,
            "row3_weaknesses": row3,
        },
        "matrix_3x3": matrix,
    }
    return out


def print_matrix(matrix: Dict[str, Dict[str, Optional[str]]]) -> None:
    def row_line(title: str, row_map: Dict[str, Optional[str]]) -> str:
        return f"{title:<16} | " + " | ".join([f"{(row_map.get(c) or '-'):>10}" for c in COLUMNS])

    header = f"{'':<16} | {'perception':>10} | {'motivation':>10} | {'instrument':>10}"
    sep = "-" * len(header)
    print(header)
    print(sep)
    print(row_line("ROW1 (СИЛЫ)", matrix["row1_strengths"]))
    print(row_line("ROW2 (ЭНЕРГИЯ)", matrix["row2_energy"]))
    print(row_line("ROW3 (СЛАБОСТИ)", matrix["row3_weaknesses"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blocks", required=True, help="Path to neo_blocks.json")
    ap.add_argument("--answers", required=True, help="Path to neo_answers.json")
    ap.add_argument("--out", default=None, help="Optional path to write report.json")
    args = ap.parse_args()

    blocks = load_json(args.blocks)
    answers = load_json(args.answers)

    report = score_blocks(blocks, answers)

    # print matrix for human
    print("\nNEO MATRIX 3×3\n")
    print_matrix(report["matrix_3x3"])
    print("\n")

    # write json
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    # also dump to stdout as json (после таблицы удобно смотреть)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
