# neo_scoring.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple, Optional


# --- базовый список потенциалов (id) ---
POTENTIAL_IDS = [
    "amber",
    "shungite",
    "citrine",
    "emerald",
    "ruby",
    "garnet",
    "sapphire",
    "heliodor",
    "amethyst",
]

COLUMNS = ["perception", "motivation", "instrument"]


@dataclass
class PotentialScore:
    # положительные баллы (выборы в обычных вопросах)
    pos: Dict[str, float] = field(default_factory=lambda: {c: 0.0 for c in COLUMNS})
    # отрицательные баллы (выборы в invert_score вопросах)
    neg: Dict[str, float] = field(default_factory=lambda: {c: 0.0 for c in COLUMNS})

    def add_pos(self, col: str, v: float):
        if col in self.pos:
            self.pos[col] += v

    def add_neg(self, col: str, v: float):
        if col in self.neg:
            self.neg[col] += v

    def effective(self, col: str, invert_multiplier: float = 1.0) -> float:
        # “эффективный” скор — плюсы минус штрафы
        return self.pos.get(col, 0.0) - (self.neg.get(col, 0.0) * invert_multiplier)

    def total_effective(self, invert_multiplier: float = 1.0) -> float:
        return sum(self.effective(c, invert_multiplier) for c in COLUMNS)


def _safe_get_answers_map(answers_json: Dict[str, Any]) -> Dict[str, Any]:
    return (
        answers_json.get("answers")
        or answers_json.get("responses")
        or answers_json
        or {}
    )


def _extract_all_selected(raw_answer: Any) -> List[str]:
    """
    Превращает ответ любой формы в список строк:
    - "citrine"
    - "opt_citrine"
    - ["opt_1","opt_3"]
    - {"fast":[...], "slow":[...]}
    """
    out: List[str] = []

    if raw_answer is None:
        return out

    if isinstance(raw_answer, str):
        return [raw_answer]

    if isinstance(raw_answer, list):
        for x in raw_answer:
            out.extend(_extract_all_selected(x))
        return out

    if isinstance(raw_answer, dict):
        # иногда ответы лежат как {"selected":[...]} или {"fast":[...]}
        for _, v in raw_answer.items():
            out.extend(_extract_all_selected(v))
        return out

    # всё остальное игнорируем
    return out


def _normalize_token(token: str) -> str:
    """
    Нормализация:
    - "opt_citrine" -> "citrine"
    - "  citrine " -> "citrine"
    """
    t = (token or "").strip().lower()
    if t.startswith("opt_"):
        t = t[4:]
    return t


def _build_q_option_map(question: Dict[str, Any]) -> Dict[str, str]:
    """
    Для каждого вопроса строим словарь:
    token -> potential_id

    Поддерживаем:
    - потенциальные id в опциях: {"potential":"citrine"}
    - если есть {"id":"opt_3"} то тоже маппим
    - если id нет, создаём "opt_1", "opt_2"... (как раньше)
    """
    m: Dict[str, str] = {}
    options = question.get("options", []) or []

    for i, opt in enumerate(options, start=1):
        if not isinstance(opt, dict):
            continue
        pid = opt.get("potential")
        if not pid:
            continue
        pid = str(pid).strip().lower()

        # 1) прямое имя потенциала
        m[pid] = pid

        # 2) opt_<potential>
        m[f"opt_{pid}"] = pid

        # 3) явный id, если есть
        opt_id = opt.get("id")
        if opt_id:
            m[str(opt_id).strip().lower()] = pid

        # 4) старый формат без id: opt_1/opt_2/...
        m[f"opt_{i}"] = pid

    return m


def _blocks_list(blocks_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    # поддержка форматов: {"blocks":[...]} или {"schema_version":..., "blocks":[...]}
    blocks = blocks_json.get("blocks", [])
    if isinstance(blocks, list):
        return blocks
    return []


def _all_questions(blocks_json: Dict[str, Any]) -> List[Dict[str, Any]]:
    qs: List[Dict[str, Any]] = []
    for b in _blocks_list(blocks_json):
        qlist = b.get("questions", [])
        if isinstance(qlist, list):
            for q in qlist:
                if isinstance(q, dict) and q.get("id"):
                    qs.append(q)
    # сортируем по order если есть
    def _key(q: Dict[str, Any]) -> Tuple[int, str]:
        o = q.get("order")
        try:
            oi = int(o)
        except Exception:
            oi = 10**9
        return (oi, str(q.get("id")))
    qs.sort(key=_key)
    return qs


def score_blocks(blocks_json: Dict[str, Any], answers_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Главная функция для Streamlit.
    Возвращает report.json со структурой:
    {
      "scores": {
        "citrine": {"strength": ..., "by_column": {...}, "pos":..., "neg":...},
        ...
      },
      "matrix": {
         "perception": {"row1": "...", "row2": "...", "row3": "..."},
         ...
      }
    }
    """

    answers_map = _safe_get_answers_map(answers_json)
    questions = _all_questions(blocks_json)

    # создаём контейнеры скоринга
    scores: Dict[str, PotentialScore] = {pid: PotentialScore() for pid in POTENTIAL_IDS}

    # общий множитель штрафа (можно переопределять в вопросе)
    default_invert_multiplier = 1.0

    # 1) собираем баллы
    for q in questions:
        qid = q.get("id")
        col = (q.get("column") or "").strip().lower()

        if col not in COLUMNS:
            # если вдруг колонка не задана — пропускаем
            continue

        weight = q.get("weight", 1.0)
        try:
            w = float(weight)
        except Exception:
            w = 1.0

        invert = bool(q.get("invert_score", False))
        inv_mul = q.get("invert_multiplier", default_invert_multiplier)
        try:
            inv_mul = float(inv_mul)
        except Exception:
            inv_mul = default_invert_multiplier

        # достаём ответ
        raw_answer = answers_map.get(qid)

        # иногда текстовые поля идут как b1_q12_text — игнорируем для скоринга
        if raw_answer is None:
            continue

        tokens = _extract_all_selected(raw_answer)
        if not tokens:
            continue

        opt_map = _build_q_option_map(q)

        for t in tokens:
            norm = _normalize_token(t)

            # 1) прямое попадание в opt_map
            pid = opt_map.get(norm)

            # 2) если не нашли, но это выглядит как потенциальный id
            if not pid and norm in POTENTIAL_IDS:
                pid = norm

            if not pid or pid not in scores:
                continue

            if invert:
                # чем чаще человек выбирает это как “через силу/откладываю”, тем больше минус
                scores[pid].add_neg(col, w * inv_mul)
            else:
                scores[pid].add_pos(col, w)

    # 2) формируем “матрицу 3х3” по колонкам
    # Важно: РЯД 3 (слабости) даём только если реально есть neg в этой колонке.
    matrix: Dict[str, Dict[str, Optional[str]]] = {c: {"row1": None, "row2": None, "row3": None} for c in COLUMNS}

    for col in COLUMNS:
        # считаем эффективность
        eff: List[Tuple[str, float, float]] = []  # (pid, effective, neg)
        for pid in POTENTIAL_IDS:
            neg_val = scores[pid].neg.get(col, 0.0)
            eff_val = scores[pid].effective(col, invert_multiplier=1.0)
            eff.append((pid, eff_val, neg_val))

        # row1 и row2 — по effective
        eff_sorted = sorted(eff, key=lambda x: x[1], reverse=True)
        row1 = eff_sorted[0][0] if eff_sorted else None
        row2 = eff_sorted[1][0] if len(eff_sorted) > 1 else None

        # row3 — ТОЛЬКО если есть отрицательные маркеры
        # берём того, у кого neg максимальный (если равны — кто хуже по effective)
        any_neg = any(n > 0 for _, _, n in eff)
        if any_neg:
            row3 = sorted(eff, key=lambda x: (x[2], -x[1]), reverse=True)[0][0]
        else:
            row3 = None  # нет “слабости” по этой колонке

        matrix[col]["row1"] = row1
        matrix[col]["row2"] = row2
        matrix[col]["row3"] = row3

    # 3) собираем общий словарь scores для report.json
    out_scores: Dict[str, Any] = {}
    for pid in POTENTIAL_IDS:
        by_col = {c: scores[pid].effective(c, invert_multiplier=1.0) for c in COLUMNS}
        out_scores[pid] = {
            "strength": float(sum(by_col.values())),
            "by_column": by_col,
            "pos": scores[pid].pos,
            "neg": scores[pid].neg,
        }

    return {
        "scores": out_scores,
        "matrix": matrix,
        "meta": {
            "note": "Row3 (weakness) is assigned only if invert_score evidence exists in that column.",
        },
    }