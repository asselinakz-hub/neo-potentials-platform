#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
NEO Potentials — Scoring Engine (fixed invert logic)

Input:
  1) neo_blocks.json   (blocks with questions)
  2) responses.json    (answers)

Output:
  - JSON report (optionally saved to --out)
  - human readable 3×3 matrix printed to stdout

Key logic:
  - Blocks 1/2/4: selected -> strength (+)
  - invert_score: selected -> weakness (+), NOT strength (-)
  - Block 3: selected -> weakness (+), reverse_items reduce weakness (validation)
  - multi_select: weight is split across selected options
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

POTENTIALS_RU = [
    "Янтарь", "Шунгит", "Цитрин",
    "Изумруд", "Рубин", "Гранат",
    "Сапфир", "Гелиодор", "Аметист",
]

# canonical ids used in blocks
POTENTIAL_IDS = [
    "amber", "shungite", "citrine",
    "emerald", "ruby", "garnet",
    "sapphire", "heliodor", "amethyst",
]

ID2RU = {
    "amber": "Янтарь",
    "shungite": "Шунгит",
    "citrine": "Цитрин",
    "emerald": "Изумруд",
    "ruby": "Рубин",
    "garnet": "Гранат",
    "sapphire": "Сапфир",
    "heliodor": "Гелиодор",
    "amethyst": "Аметист",
}

RU2ID = {v: k for k, v in ID2RU.items()}

COLUMNS = ["perception", "motivation", "instrument"]


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def safe_get_selected(ans_obj: Any) -> List[str]:
    """
    Accepts:
      - {"selected": ["..."]} or {"selected": "..."}
      - {"value": "..."} etc.
      - direct string/list
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


def question_type(q: Dict[str, Any]) -> str:
    return str(q.get("type", "")).strip().lower()


def is_multi(q: Dict[str, Any]) -> bool:
    return question_type(q) in ("multi_choice", "multi_select", "multiple_choice", "checkbox")


def is_single(q: Dict[str, Any]) -> bool:
    return question_type(q) in ("single_choice", "single_select", "radio")


def normalize_potential(x: str) -> Optional[str]:
    """
    Normalize selected potential key to RU name (internal scoring keys).
    Accepts:
      - RU: "Цитрин"
      - id: "citrine"
      - common typos: "Гелиodор"
    """
    if not isinstance(x, str):
        return None

    s = x.strip()

    # fix common mixed-letter typo
    s = s.replace("Гелиodор", "Гелиодор").replace("Гелиodor", "Гелиодор")

    # if already RU
    if s in POTENTIALS_RU:
        return s

    # if id -> RU
    sid = s.lower()
    if sid in ID2RU:
        return ID2RU[sid]

    return None


def clamp_floor(x: float, floor: float = 0.0) -> float:
    return x if x >= floor else floor


@dataclass
class PotentialScore:
    strength: float = 0.0   # for row1 candidates
    weakness: float = 0.0   # for row3 candidates
    col_points: Dict[str, float] = None

    def __post_init__(self):
        if self.col_points is None:
            self.col_points = {c: 0.0 for c in COLUMNS}


def score_blocks(blocks_json: Dict[str, Any], answers_json: Dict[str, Any]) -> Dict[str, Any]:
    blocks = blocks_json.get("blocks", [])

    # answers_map can be either {"answers": {...}} or direct mapping
    answers_map: Dict[str, Any] = (
        answers_json.get("answers")
        or answers_json.get("responses")
        or answers_json
    )

    scores: Dict[str, PotentialScore] = {p: PotentialScore() for p in POTENTIALS_RU}

    invert_multiplier_default = 0.8

    for blk in blocks:
        blk_id = str(blk.get("block_id", "") or "")
        scoring_rules = blk.get("scoring_rules", {}) or {}
        reverse_items = set(scoring_rules.get("reverse_items", []) or [])
        anti_weight_multiplier = float(scoring_rules.get("anti_weight_multiplier", 1.0) or 1.0)

        is_block3 = blk_id.lower().startswith("block3") or blk_id.lower().endswith("antipatterns")

        for q in blk.get("questions", []):
            qid = q.get("id")
            if not qid:
                continue

            w = float(q.get("weight", 1.0) or 1.0)
            col = q.get("column")
            invert_score = bool(q.get("invert_score", False))
            invert_multiplier = float(q.get("invert_multiplier", invert_multiplier_default) or invert_multiplier_default)

            ans_obj = answers_map.get(qid)
            selected_raw = safe_get_selected(ans_obj)
            selected = [normalize_potential(x) for x in selected_raw]
            selected = [x for x in selected if x is not None]

            # text-only question (no selection) => skip
            if not selected and not (is_single(q) or is_multi(q)):
                continue
            if not selected:
                continue

            per_item = (w / len(selected)) if is_multi(q) else w

            # ---------------- Block 3 ----------------
            if is_block3:
                row_target = q.get("row_target", None)
                # weakness by default, reverse reduces weakness
                sign = -1.0 if (qid in reverse_items or row_target == "validation_reverse") else 1.0
                pts = per_item * anti_weight_multiplier * sign
                for p in selected:
                    scores[p].weakness += pts
                continue

            # ---------------- Blocks 1/2/4 ----------------
            # FIX: invert_score => add to weakness, not subtract from strength
            if invert_score:
                pts = per_item * invert_multiplier
                for p in selected:
                    scores[p].weakness += pts
                # we intentionally DO NOT add to col_points here (это не "столбец силы")
                continue

            # normal scoring => strength (+) and column points
            pts = per_item
            for p in selected:
                scores[p].strength += pts
                if col in COLUMNS:
                    scores[p].col_points[col] += pts

    # normalize weakness floor (reverse-items may reduce)
    for p in POTENTIALS_RU:
        scores[p].weakness = clamp_floor(scores[p].weakness, 0.0)

    # Row3: top3 weakness
    row3 = sorted(POTENTIALS_RU, key=lambda p: scores[p].weakness, reverse=True)[:3]

    # Row1: top3 strength excluding row3
    row1_candidates = [p for p in POTENTIALS_RU if p not in row3]
    row1 = sorted(row1_candidates, key=lambda p: scores[p].strength, reverse=True)[:3]

    # Row2: remaining
    row2 = [p for p in POTENTIALS_RU if p not in row1 and p not in row3]

    def dominant_column(p: str) -> str:
        cp = scores[p].col_points
        if all(abs(cp.get(c, 0.0)) < 1e-9 for c in COLUMNS):
            return "perception"
        return max(COLUMNS, key=lambda c: cp.get(c, 0.0))

    def order_row_by_columns(row: List[str]) -> Dict[str, Optional[str]]:
        remaining = set(row)
        slots: Dict[str, Optional[str]] = {c: None for c in COLUMNS}

        # greedily place best match per column
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

        # fill leftovers if any
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

    out = {
        "respondent_id": answers_json.get("respondent_id") or answers_json.get("respondent", {}).get("client_id"),
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
    ap.add_argument("--answers", required=True, help="Path to responses.json / neo_answers.json")
    ap.add_argument("--out", default=None, help="Optional path to write report.json")
    args = ap.parse_args()

    blocks = load_json(args.blocks)
    answers = load_json(args.answers)

    report = score_blocks(blocks, answers)

    print("\nNEO MATRIX 3×3\n")
    print_matrix(report["matrix_3x3"])
    print("\n")

    if args.out:
        save_json(args.out, report)

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()