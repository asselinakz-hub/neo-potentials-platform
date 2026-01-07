#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NEO Potentials Diagnostic System — scoring engine.

Designed to be *schema-tolerant* because your JSON may evolve.

INPUTS
1) Questions JSON (your 4 blocks in a single file is OK)
   Expected to contain a list of blocks or an object with "blocks".
   Each question should include at minimum:
     - id (string)
     - weight (number)
     - type (one of: "single", "multi", "time", "text", "mixed")
     - column (e.g., "perception" / "motivation" / "instrument")
     - options: list of { id, text, potential }

   Special for time questions:
     - the response should include "fast" and/or "slow" arrays of option ids.

2) Responses JSON
   Supported formats:
     A) {"answers": {"q_id": "opt_id" | ["opt_id", ...] | {"fast": [...], "slow": [...] } | "free text" }}
     B) {"q_id": ...}  (answers at root)

OUTPUT
- results.json with totals, column breakdowns, and row assignments.

ROW LOGIC
- Overall rows: top 3 potentials -> Row1, middle 3 -> Row2, bottom 3 -> Row3.
- Per column rows: same tertile split *inside each column*.

You can adjust coefficients with CLI args.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


POTENTIALS = [
    "Янтарь",
    "Шунгит",
    "Цитрин",
    "Изумруд",
    "Рубин",
    "Гранат",
    "Сапфир",
    "Гелиодор",
    "Аметист",
]

# Sphere mapping (for pretty output)
SPHERES = {
    "Янтарь": "Материя",
    "Шунгит": "Материя",
    "Цитрин": "Материя",
    "Изумруд": "Эмоции",
    "Рубин": "Эмоции",
    "Гранат": "Эмоции",
    "Сапфир": "Смыслы",
    "Гелиодор": "Смыслы",
    "Аметист": "Смыслы",
}

DEFAULT_KEYWORDS = {
    "Янтарь": ["порядок", "система", "структур", "организац", "регламент", "процесс"],
    "Шунгит": ["движ", "спорт", "тело", "физич", "руками", "ходь", "бег"],
    "Цитрин": ["деньг", "результ", "быстро", "эффектив", "ускор", "сделк", "прибыл"],
    "Изумруд": ["красот", "дизайн", "гармон", "уют", "эстет"],
    "Гранат": ["люди", "общен", "команд", "друз", "семья", "отношен"],
    "Рубин": ["драйв", "адрен", "эмоци", "вдохнов", "новые места", "путеше"],
    "Сапфир": ["идея", "смысл", "концепц", "философ", "почему", "мисс"],
    "Гелиодор": ["знан", "изуч", "обуч", "развит", "объясн", "педагог"],
    "Аметист": ["цель", "стратег", "управлен", "лидер", "план", "коорди"],
}


@dataclass
class Option:
    id: str
    potential: Optional[str] = None


@dataclass
class Question:
    id: str
    qtype: str
    weight: float
    column: str
    options: Dict[str, Option]
    is_antipattern: bool = False
    is_time: bool = False
    text_weight: float = 0.0  # additional per keyword hit


def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _as_blocks(obj: Any) -> List[Dict[str, Any]]:
    if isinstance(obj, list):
        # could be list of blocks or list of questions
        if obj and isinstance(obj[0], dict) and "questions" in obj[0]:
            return obj
        # wrap as one block
        return [{"id": "block", "title": "", "questions": obj}]
    if isinstance(obj, dict):
        if "blocks" in obj and isinstance(obj["blocks"], list):
            return obj["blocks"]
        if "questions" in obj and isinstance(obj["questions"], list):
            return [{"id": obj.get("id", "block"), "title": obj.get("title", ""), "questions": obj["questions"]}]
    raise ValueError("Unsupported questions JSON structure")


def _norm_str(x: str) -> str:
    return re.sub(r"\s+", " ", x.strip().lower())


def parse_questions(questions_json: Any, *, text_hit_weight: float) -> Dict[str, Question]:
    blocks = _as_blocks(questions_json)

    out: Dict[str, Question] = {}

    for b in blocks:
        for q in b.get("questions", []):
            qid = str(q.get("id") or q.get("qid") or "").strip()
            if not qid:
                raise ValueError("Question without id")

            qtype = str(q.get("type") or q.get("qtype") or "single").strip().lower()
            weight = float(q.get("weight", 1.0))
            column = str(q.get("column") or q.get("col") or "unknown").strip().lower()

            tags = set([str(t).lower() for t in (q.get("tags") or [])])
            is_antipattern = bool(q.get("antipattern", False) or ("antipattern" in tags) or ("anti" in tags))
            is_time = bool(q.get("time", False) or (qtype == "time") or ("time" in tags))

            # Options
            options_map: Dict[str, Option] = {}
            for opt in q.get("options", []) or []:
                oid = str(opt.get("id") or opt.get("value") or opt.get("key") or "").strip()
                if not oid:
                    continue
                potential = opt.get("potential") or opt.get("pot")
                if isinstance(potential, str):
                    potential = potential.strip()
                options_map[oid] = Option(id=oid, potential=potential)

            out[qid] = Question(
                id=qid,
                qtype=qtype,
                weight=weight,
                column=column,
                options=options_map,
                is_antipattern=is_antipattern,
                is_time=is_time,
                text_weight=float(q.get("text_weight", 0.0)) or float(text_hit_weight),
            )

    return out


def parse_responses(responses_json: Any) -> Dict[str, Any]:
    if isinstance(responses_json, dict):
        if "answers" in responses_json and isinstance(responses_json["answers"], dict):
            return responses_json["answers"]
        return responses_json
    raise ValueError("Unsupported responses JSON structure")


def add_score(bucket: Dict[str, float], key: str, val: float) -> None:
    bucket[key] = bucket.get(key, 0.0) + float(val)


def score_text(text: str, *, keywords: Dict[str, List[str]], hit_weight: float) -> Dict[str, float]:
    text_l = _norm_str(text)
    scores: Dict[str, float] = {}
    for pot, keys in keywords.items():
        hits = 0
        for k in keys:
            if k in text_l:
                hits += 1
        if hits:
            scores[pot] = hits * hit_weight
    return scores


def tertile_rows(sorted_items: List[Tuple[str, float]]) -> Dict[str, str]:
    """Assign Row1/Row2/Row3 by rank (top/middle/bottom thirds).

    Always assigns exactly 3/3/3 when there are 9 items.
    """
    n = len(sorted_items)
    if n == 0:
        return {}

    # If not 9, still split roughly into thirds.
    t1 = max(1, math.ceil(n / 3))
    t2 = max(1, math.ceil(2 * n / 3))

    rows: Dict[str, str] = {}
    for i, (k, _v) in enumerate(sorted_items):
        if i < t1:
            rows[k] = "ROW_1"
        elif i < t2:
            rows[k] = "ROW_2"
        else:
            rows[k] = "ROW_3"
    return rows


def compute(
    questions: Dict[str, Question],
    answers: Dict[str, Any],
    *,
    antipattern_factor: float,
    time_slow_factor: float,
    keywords: Dict[str, List[str]],
) -> Dict[str, Any]:
    total: Dict[str, float] = {p: 0.0 for p in POTENTIALS}
    by_column: Dict[str, Dict[str, float]] = {}
    debug: List[Dict[str, Any]] = []

    def add(pot: str, val: float, col: str, meta: Dict[str, Any]):
        if pot not in total:
            total[pot] = 0.0
        add_score(total, pot, val)
        by_column.setdefault(col, {})
        add_score(by_column[col], pot, val)
        meta.update({"potential": pot, "delta": val, "column": col})
        debug.append(meta)

    for qid, q in questions.items():
        if qid not in answers:
            continue
        ans = answers[qid]

        # TIME question: {fast:[...], slow:[...]}
        if q.is_time and isinstance(ans, dict):
            fast = ans.get("fast") or ans.get("FAST") or []
            slow = ans.get("slow") or ans.get("SLOW") or []

            if isinstance(fast, str):
                fast = [fast]
            if isinstance(slow, str):
                slow = [slow]

            # Add for fast, subtract for slow
            if fast:
                per = q.weight / max(1, len(fast))
                for oid in fast:
                    oid = str(oid)
                    pot = q.options.get(oid, Option(id=oid)).potential
                    if pot:
                        add(pot, per, q.column, {"qid": qid, "type": "time_fast", "option": oid})

            if slow:
                per = (q.weight * time_slow_factor) / max(1, len(slow))
                for oid in slow:
                    oid = str(oid)
                    pot = q.options.get(oid, Option(id=oid)).potential
                    if pot:
                        add(pot, -per, q.column, {"qid": qid, "type": "time_slow", "option": oid})
            continue

        # TEXT
        if q.qtype == "text" and isinstance(ans, str):
            text_scores = score_text(ans, keywords=keywords, hit_weight=q.text_weight)
            for pot, val in text_scores.items():
                add(pot, val, q.column, {"qid": qid, "type": "text", "text": ans[:80]})
            continue

        # MIXED: can be {"selected": [...], "text": "..."}
        if isinstance(ans, dict) and ("selected" in ans or "choices" in ans):
            selected = ans.get("selected") or ans.get("choices") or []
            text = ans.get("text") or ans.get("comment")
            answers[qid] = selected
            # score selected below and then text
            if isinstance(text, str) and text.strip():
                text_scores = score_text(text, keywords=keywords, hit_weight=q.text_weight)
                for pot, val in text_scores.items():
                    add(pot, val, q.column, {"qid": qid, "type": "mixed_text", "text": text[:80]})
            ans = selected

        # SINGLE
        if isinstance(ans, str):
            oid = ans
            pot = q.options.get(oid, Option(id=oid)).potential
            if pot:
                val = q.weight
                if q.is_antipattern:
                    val = -q.weight * antipattern_factor
                add(pot, val, q.column, {"qid": qid, "type": "single", "option": oid, "antipattern": q.is_antipattern})
            continue

        # MULTI
        if isinstance(ans, list):
            oids = [str(x) for x in ans]
            per = q.weight / max(1, len(oids))
            for oid in oids:
                pot = q.options.get(oid, Option(id=oid)).potential
                if not pot:
                    continue
                val = per
                if q.is_antipattern:
                    val = -per * antipattern_factor
                add(pot, val, q.column, {"qid": qid, "type": "multi", "option": oid, "antipattern": q.is_antipattern})
            continue

        # Fallback: if numeric scales are ever added
        if isinstance(ans, (int, float)):
            # numeric answer should be accompanied by a potential in question
            pot = q.options.get("_self", Option(id="_self")).potential or q.options.get("0", Option(id="0")).potential
            if pot:
                add(pot, float(ans) * q.weight, q.column, {"qid": qid, "type": "numeric", "value": ans})

    # Normalize column maps to include all potentials
    for col, m in by_column.items():
        for p in POTENTIALS:
            m.setdefault(p, 0.0)

    # Rank overall
    overall_rank = sorted(total.items(), key=lambda kv: kv[1], reverse=True)
    overall_rows = tertile_rows(overall_rank)

    # Rank per column
    columns_rows: Dict[str, Dict[str, str]] = {}
    for col, m in by_column.items():
        r = sorted(m.items(), key=lambda kv: kv[1], reverse=True)
        columns_rows[col] = tertile_rows(r)

    # Build matrix representation (sphere x overall_row)
    matrix: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
        "Материя": {"ROW_1": [], "ROW_2": [], "ROW_3": []},
        "Эмоции": {"ROW_1": [], "ROW_2": [], "ROW_3": []},
        "Смыслы": {"ROW_1": [], "ROW_2": [], "ROW_3": []},
    }
    for pot, score in total.items():
        sphere = SPHERES.get(pot, "Unknown")
        row = overall_rows.get(pot, "ROW_2")
        matrix.setdefault(sphere, {}).setdefault(row, []).append({"potential": pot, "score": score})

    # Sort lists inside matrix
    for sphere in matrix:
        for row in matrix[sphere]:
            matrix[sphere][row].sort(key=lambda x: x["score"], reverse=True)

    return {
        "totals": total,
        "overall_rank": [{"potential": k, "score": v, "row": overall_rows.get(k)} for k, v in overall_rank],
        "by_column": by_column,
        "column_rows": columns_rows,
        "matrix_by_sphere": matrix,
        "debug": debug,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", required=True, help="Path to questions JSON")
    ap.add_argument("--responses", required=True, help="Path to responses JSON")
    ap.add_argument("--out", default="results.json", help="Output JSON file")
    ap.add_argument("--antipattern_factor", type=float, default=0.8)
    ap.add_argument("--time_slow_factor", type=float, default=1.0)
    ap.add_argument("--text_hit_weight", type=float, default=0.15)
    args = ap.parse_args()

    qjson = _load_json(args.questions)
    rjson = _load_json(args.responses)

    questions = parse_questions(qjson, text_hit_weight=args.text_hit_weight)
    answers = parse_responses(rjson)

    res = compute(
        questions,
        answers,
        antipattern_factor=args.antipattern_factor,
        time_slow_factor=args.time_slow_factor,
        keywords=DEFAULT_KEYWORDS,
    )

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)

    # Console summary
    print("\nNEO scoring complete. Top potentials (overall):")
    for i, item in enumerate(res["overall_rank"][:5], start=1):
        print(f"{i}. {item['potential']}: {item['score']:.3f} ({item['row']})")

    print("\nRows by column (top potential each):")
    for col, rows in res["column_rows"].items():
        # find top in that column
        top = sorted(res["by_column"][col].items(), key=lambda kv: kv[1], reverse=True)[0]
        print(f"- {col}: top = {top[0]} ({top[1]:.3f})")

    print(f"\nWrote: {os.path.abspath(args.out)}")


if __name__ == "__main__":
    main()
