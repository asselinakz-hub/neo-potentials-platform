from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

POTENTIALS_RU = [
    "Янтарь", "Шунгит", "Цитрин",
    "Изумруд", "Рубин", "Гранат",
    "Сапфир", "Гелиодор", "Аметист",
]

COLUMNS = ["perception", "motivation", "instrument"]


def safe_get_selected(ans_obj: Any) -> List[str]:
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
    strength: float = 0.0
    weakness: float = 0.0
    col_points: Dict[str, float] = None  # type: ignore

    def __post_init__(self):
        if self.col_points is None:
            self.col_points = {c: 0.0 for c in COLUMNS}


def question_type(q: Dict[str, Any]) -> str:
    return str(q.get("type", "")).strip().lower()


def is_multi(q: Dict[str, Any]) -> bool:
    return question_type(q) in ("multi_choice", "multi_select", "multiple_choice", "checkbox")


def is_single(q: Dict[str, Any]) -> bool:
    return question_type(q) in ("single_choice", "single_select", "radio")


def normalize_potential_name(p: str) -> Optional[str]:
    if not isinstance(p, str):
        return None
    p2 = p.strip()

    # быстрые фиксы опечаток
    p2 = p2.replace("Гелиodор", "Гелиодор").replace("Гелиodor", "Гелиодор")

    if p2 in POTENTIALS_RU:
        return p2
    return None


def score_blocks(blocks_json: Dict[str, Any], answers_json: Dict[str, Any]) -> Dict[str, Any]:
    blocks = blocks_json.get("blocks", [])

    answers_map: Dict[str, Any] = (
        answers_json.get("answers")
        or answers_json.get("responses")
        or answers_json
    )

    scores: Dict[str, PotentialScore] = {p: PotentialScore() for p in POTENTIALS_RU}

    invert_multiplier_default = 0.8

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
            col = q.get("column")  # may be None
            invert_score = bool(q.get("invert_score", False))

            ans_obj = answers_map.get(qid)
            selected_raw = safe_get_selected(ans_obj)
            selected = [normalize_potential_name(x) for x in selected_raw]
            selected = [x for x in selected if x is not None]

            # text-only вопрос — пока без скоринга
            if not selected and not (is_single(q) or is_multi(q)):
                continue

            if len(selected) == 0:
                continue

            per_item = (w / len(selected)) if is_multi(q) else w

            is_block3 = str(blk_id).lower().startswith("block3") or str(blk_id).lower().endswith("antipatterns")
            row_target = q.get("row_target", None)

            if is_block3:
                sign = -1.0 if (qid in reverse_items or row_target == "validation_reverse") else 1.0
                pts = per_item * anti_weight_multiplier * sign
                for p in selected:
                    scores[p].weakness += pts
                continue

            # blocks 1,2,4 strength scoring
            pts = (-per_item * invert_multiplier_default) if invert_score else per_item

            for p in selected:
                scores[p].strength += pts
                if col in COLUMNS:
                    scores[p].col_points[col] += pts

    for p in POTENTIALS_RU:
        scores[p].weakness = clamp_floor(scores[p].weakness, 0.0)

    row3 = sorted(POTENTIALS_RU, key=lambda p: scores[p].weakness, reverse=True)[:3]
    row1_candidates = [p for p in POTENTIALS_RU if p not in row3]
    row1 = sorted(row1_candidates, key=lambda p: scores[p].strength, reverse=True)[:3]
    row2 = [p for p in POTENTIALS_RU if p not in row1 and p not in row3]

    def dominant_column(p: str) -> str:
        cp = scores[p].col_points
        if all(abs(cp.get(c, 0.0)) < 1e-9 for c in COLUMNS):
            return "perception"
        return max(COLUMNS, key=lambda c: cp.get(c, 0.0))

    def order_row_by_columns(row: List[str]) -> Dict[str, Optional[str]]:
        remaining = set(row)
        slots: Dict[str, Optional[str]] = {c: None for c in COLUMNS}

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