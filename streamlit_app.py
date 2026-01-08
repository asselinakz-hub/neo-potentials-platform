import json
import os
import subprocess
import streamlit as st

BLOCKS_PATH = "neo_blocks.json"
RESPONSES_PATH = "responses.json"
REPORT_PATH = "report.json"

st.set_page_config(page_title="NEO Potentials", layout="wide")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# --- helpers ---
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


def get_potential_id(opt: dict):
    pid = opt.get("potential_id") or opt.get("potential") or opt.get("id") or opt.get("code")
    if pid is None:
        return None
    pid = RU2ID.get(pid, pid)  # allow RU names
    return str(pid)


def get_opt_label(opt: dict):
    return str(opt.get("label") or opt.get("text") or opt.get("title") or opt.get("name") or "")


st.title("NEO Potentials — Диагностика")

if not os.path.exists(BLOCKS_PATH):
    st.error(f"Не найден файл {BLOCKS_PATH}.")
    st.stop()

blocks_data = load_json(BLOCKS_PATH)
blocks = blocks_data.get("blocks", [])

# potentials section could be dict or list — normalize
potentials = {}
pots = blocks_data.get("potentials")
if isinstance(pots, dict):
    # expecting {"amber": {"ru": "...", ...}, ...} OR {"amber":"Янтарь", ...}
    for k, v in pots.items():
        if isinstance(v, dict):
            potentials[str(k)] = str(v.get("ru") or v.get("name") or v.get("title") or k)
        else:
            potentials[str(k)] = str(v)
elif isinstance(pots, list):
    for p in pots:
        if isinstance(p, dict):
            pid = p.get("potential_id") or p.get("id") or p.get("code")
            name = p.get("name") or p.get("title")
            if pid and name:
                potentials[str(pid)] = str(name)

if not potentials:
    potentials = DEFAULT_POTENTIALS

# session answers
if "answers" not in st.session_state:
    st.session_state.answers = {}

st.caption("Заполни ответы → нажми Save responses.json → потом Run scoring.")


for b in blocks:
    block_code = b.get("block_code") or b.get("code") or b.get("block_id") or "BLOCK"
    st.header(f"{block_code}. {b.get('block_name', '')}")
    if b.get("goal"):
        st.write(b["goal"])

    for q in b.get("questions", []):
        qid = q.get("id")
        if not qid:
            continue

        qtype = str(q.get("type", "")).strip().lower()
        prompt = q.get("prompt", "")
        st.subheader(prompt)

        key = f"ans_{qid}"

        # ---- choice questions ----
        if qtype in ("single_choice", "single_select"):
            options = q.get("options", []) or []
            option_labels, option_ids = [], []
            for opt in options:
                if not isinstance(opt, dict):
                    continue
                pid = get_potential_id(opt)
                if pid is None:
                    continue
                label = get_opt_label(opt) or pid
                option_ids.append(pid)
                option_labels.append(f"{label} ({potentials.get(pid, pid)})")

            chosen = st.radio("Выберите 1 вариант:", option_labels, index=None, key=key)
            if chosen is not None:
                idx = option_labels.index(chosen)
                st.session_state.answers[qid] = {"selected": [option_ids[idx]]}

        elif qtype in ("multi_choice", "multi_select"):
            options = q.get("options", []) or []
            option_labels, option_ids = [], []
            for opt in options:
                if not isinstance(opt, dict):
                    continue
                pid = get_potential_id(opt)
if pid is None:
                    continue
                label = get_opt_label(opt) or pid
                option_ids.append(pid)
                option_labels.append(f"{label} ({potentials.get(pid, pid)})")

            max_choices = q.get("max_choices")
            chosen = st.multiselect(
                f"Выберите варианты{' (макс ' + str(max_choices) + ')' if max_choices else ''}:",
                option_labels,
                key=key,
            )
            selected_ids = [option_ids[option_labels.index(c)] for c in chosen]
            if isinstance(max_choices, int) and max_choices > 0:
                selected_ids = selected_ids[:max_choices]
            st.session_state.answers[qid] = {"selected": selected_ids}

        # ---- text ----
        elif qtype == "text":
            txt = st.text_area("Введите ответ:", key=key)
            st.session_state.answers[qid] = {"text": txt}

        # ---- scale support ----
        elif qtype == "scale":
            mn = int(q.get("min", 1))
            mx = int(q.get("max", 10))
            step = int(q.get("step", 1))
            default = int(q.get("default", mn))
            val = st.slider("Оценка:", min_value=mn, max_value=mx, value=default, step=step, key=key)
            # сохраняем как value — скоринг пока может игнорировать, но UI не ломается
            st.session_state.answers[qid] = {"value": val}

        else:
            st.warning(f"Тип вопроса '{qtype}' пока не поддержан в UI (не критично).")

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
        st.success(f"Сохранила ответы в {RESPONSES_PATH}")

with col2:
    if st.button("Run scoring"):
        if not os.path.exists(RESPONSES_PATH):
            st.error("Сначала нажми Save responses.json")
        else:
            cmd = ["python", "neo_scoring.py", "--blocks", BLOCKS_PATH, "--answers", RESPONSES_PATH, "--out", REPORT_PATH]
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                st.error("Ошибка при запуске скоринга:")
                st.code(result.stderr or result.stdout)
            else:
                st.success("Скоринг выполнен ✅")

                if os.path.exists(REPORT_PATH):
                    rep = load_json(REPORT_PATH)

                    st.subheader("Итоговая матрица (3×3)")
                    m = rep.get("matrix_3x3", {})
                    st.json(m)

                    st.subheader("ТОП рядов (списком)")
                    st.write("**Row1 (Силы):**", rep.get("rows", {}).get("row1_strengths"))
                    st.write("**Row2 (Энергия):**", rep.get("rows", {}).get("row2_energy"))
                    st.write("**Row3 (Слабости):**", rep.get("rows", {}).get("row3_weaknesses"))

                    with st.expander("Полный report.json"):
                        st.json(rep)

with col3:
    st.write("Файлы в папке:")
    st.code("\n".join(sorted(os.listdir("."))))
