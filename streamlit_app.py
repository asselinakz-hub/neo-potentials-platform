import json
import os
import subprocess
import streamlit as st

BLOCKS_PATH = "neo_blocks.json"
RESPONSES_PATH = "responses.json"
REPORT_PATH = "report.json"

st.set_page_config(page_title="NEO Potentials — Диагностика", layout="wide")


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# Маппинг RU -> ID (если в options вдруг лежит "Янтарь" вместо "amber")
RU2ID = {
    "Янтарь": "amber",
    "Шунгит": "shungite",
    "Цитрин": "citrine",
    "Изумруд": "emerald",
    "Рубин": "ruby",
    "Гранат": "garnet",
    "Сапфир": "sapphire",
    "Гелиодор": "heliodor",
    "Аметист": "amethyst",
}

DEFAULT_POTENTIALS = {
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


def norm_qtype(qtype: str) -> str:
    t = (qtype or "").strip().lower()
    # делаем типы "всеядными"
    if t in ("single_choice", "single_select", "radio"):
        return "single"
    if t in ("multi_choice", "multi_select", "checkbox"):
        return "multi"
    if t in ("text", "textarea"):
        return "text"
    if t in ("scale", "slider"):
        return "scale"
    if t in ("matrix_time",):
        return "matrix_time"
    return t  # неизвестный


def get_potentials_dict(blocks_data: dict) -> dict:
    pots = blocks_data.get("potentials")
    # твой neo_blocks.json (по скрину) хранит potentials как dict
    if isinstance(pots, dict):
        out = {}
        for pid, meta in pots.items():
            if isinstance(meta, dict):
                out[str(pid)] = meta.get("ru") or meta.get("name") or str(pid)
            else:
                out[str(pid)] = str(meta)
        return out
    return DEFAULT_POTENTIALS


def get_opt_pid(opt: dict):
    # поддерживаем разные схемы option
    pid = opt.get("potential_id") or opt.get("potential") or opt.get("id") or opt.get("code")
    if pid is None:
        pid = opt.get("value")  # иногда так называют
    if pid is None:
        return None
    pid = RU2ID.get(pid, pid)
    return str(pid)


def get_opt_label(opt: dict):
    return opt.get("label") or opt.get("text") or opt.get("title") or opt.get("name") or ""


st.title("NEO Potentials — Диагностика")

if not os.path.exists(BLOCKS_PATH):
    st.error(f"Не найден файл {BLOCKS_PATH}")
    st.stop()

blocks_data = load_json(BLOCKS_PATH)
blocks = blocks_data.get("blocks", [])
potentials = get_potentials_dict(blocks_data)

if "answers" not in st.session_state:
    st.session_state.answers = {}

st.caption("Заполняй ответы → нажми Save responses.json → потом **Run scoring**")


for b in blocks:
    block_code = b.get("block_code") or b.get("code") or b.get("id") or "B?"
    block_name = b.get("block_name") or b.get("name") or "Без названия"
    st.header(f"{block_code}. {block_name}")
    if b.get("goal"):
        st.write(b.get("goal"))

    for q in b.get("questions", []):
        qid = q.get("id")
        if not qid:
            continue

        qtype_raw = q.get("type", "")
        qtype = norm_qtype(qtype_raw)
        prompt = q.get("prompt") or q.get("title") or f"Вопрос {qid}"

        st.subheader(prompt)

        options = q.get("options", [])
        key = f"ans_{qid}"

        # --- SINGLE / MULTI: рисуем варианты ---
        if qtype in ("single", "multi"):
            if not isinstance(options, list) or len(options) == 0:
                st.warning("У этого вопроса нет options (вариантов). Проверь neo_blocks.json.")
                st.divider()
                continue

            labels = []
            ids = []

            for opt in options:
                if not isinstance(opt, dict):
                    continue
                pid = get_opt_pid(opt)
                label = get_opt_label(opt)

                # если pid отсутствует — создадим технический id
if not pid:
                    pid = f"opt_{len(ids)+1}"

                # если label пустой — покажем pid
                if not label:
                    label = pid

                # показываем человекочитаемо
                ru_name = potentials.get(pid, pid)
                labels.append(f"{label} ({ru_name})")
                ids.append(pid)

            if qtype == "single":
                chosen = st.radio("Выберите 1 вариант:", labels, index=None, key=key)
                if chosen is not None:
                    idx = labels.index(chosen)
                    st.session_state.answers[qid] = {"selected": [ids[idx]]}

            else:
                max_choices = q.get("max_choices")
                chosen = st.multiselect("Выберите варианты:", labels, key=key)
                selected_ids = [ids[labels.index(c)] for c in chosen]

                if isinstance(max_choices, int) and max_choices > 0:
                    selected_ids = selected_ids[:max_choices]

                st.session_state.answers[qid] = {"selected": selected_ids}

        # --- TEXT ---
        elif qtype == "text":
            txt = st.text_area("Введите ответ:", key=key)
            st.session_state.answers[qid] = {"text": txt}

        # --- SCALE ---
        elif qtype == "scale":
            min_v = int(q.get("min", 1))
            max_v = int(q.get("max", 10))
            default_v = int(q.get("default", (min_v + max_v) // 2))
            val = st.slider("Оценка:", min_v, max_v, default_v, key=key)
            st.session_state.answers[qid] = {"value": val}

        # --- MATRIX_TIME (пока простая форма) ---
        elif qtype == "matrix_time":
            st.info("matrix_time: временно сохраняем как текст. Потом сделаем красивый UI.")
            txt = st.text_area("Напишите ответ (fast/slow или описание):", key=key)
            st.session_state.answers[qid] = {"text": txt}

        else:
            st.warning(f"Тип вопроса '{qtype_raw}' пока не поддержан.")
            st.divider()
            continue

        # optional note
        if q.get("text_field", False):
            note = st.text_input("Комментарий (необязательно):", key=f"note_{qid}")
            st.session_state.answers.setdefault(qid, {})
            st.session_state.answers[qid]["note"] = note

        st.divider()


col1, col2, col3 = st.columns(3)

with col1:
    if st.button("Save responses.json"):
        payload = {"respondent_id": "demo_user", "answers": st.session_state.answers}
        save_json(RESPONSES_PATH, payload)
        st.success("responses.json сохранён")

with col2:
    if st.button("Run scoring"):
        if not os.path.exists(RESPONSES_PATH):
            st.error("Сначала нажми Save responses.json")
        else:
            cmd = ["python", "neo_scoring.py", "--blocks", BLOCKS_PATH, "--answers", RESPONSES_PATH, "--out", REPORT_PATH]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                st.error("Ошибка скоринга:")
                st.code(result.stderr or result.stdout)
            else:
                st.success("Скоринг выполнен ✅")
                if os.path.exists(REPORT_PATH):
                    st.json(load_json(REPORT_PATH))

with col3:
    st.write("Файлы в папке:")
    st.code("\n".join(sorted(os.listdir("."))))
