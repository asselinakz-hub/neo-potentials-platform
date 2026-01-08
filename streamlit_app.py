import json
import os
import subprocess
import streamlit as st

BLOCKS_PATH = "neo_blocks.json"
RESPONSES_PATH = "responses.json"
REPORT_PATH = "report.json"

st.set_page_config(page_title="NEO Potentials", layout="wide")


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# --- Canonical potentials mapping ---
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

RU_SET = set(DEFAULT_POTENTIALS.values())


def build_potentials_dict(blocks_data: dict) -> dict:
    """
    Returns mapping: potential_id -> RU name
    If neo_blocks.json doesn't contain potentials section, fallback to DEFAULT_POTENTIALS.
    """
    potentials_list = blocks_data.get("potentials", [])
    potentials = {}

    if isinstance(potentials_list, list):
        for p in potentials_list:
            if not isinstance(p, dict):
                continue
            pid = p.get("potential_id") or p.get("id") or p.get("code")
            name = p.get("name") or p.get("title")
            if pid and name:
                potentials[str(pid)] = str(name)

    if not potentials:
        potentials = dict(DEFAULT_POTENTIALS)

    return potentials


def option_to_ru(opt: dict, potentials_map: dict) -> str | None:
    """
    Convert option potential into RU name that neo_scoring.py expects.
    Supported keys in option: potential_id / potential / id / code
    - If option already contains RU name (e.g., "Янтарь") -> return it
    - If option contains id (e.g., "amber") -> map via potentials_map
    """
    if not isinstance(opt, dict):
        return None

    raw = opt.get("potential_id")
    if raw is None:
        raw = opt.get("potential")
    if raw is None:
        raw = opt.get("id")
    if raw is None:
        raw = opt.get("code")

    if raw is None:
        return None

    raw_str = str(raw).strip()

    # Fix common typos
    raw_str = raw_str.replace("Гелиodор", "Гелиодор").replace("Гелиodor", "Гелиодор")

    # If already RU:
    if raw_str in RU_SET:
        return raw_str

    # If id -> RU
    if raw_str in potentials_map:
        return potentials_map[raw_str]

    # Sometimes label contains "(Янтарь)" etc; we avoid parsing that (fragile)
    return None


def normalize_qtype(qtype: str) -> str:
    t = (qtype or "").strip().lower()
    if t in ("single_select", "single_choice", "radio"):
        return "single"
    if t in ("multi_select", "multi_choice", "checkbox"):
        return "multi"
    if t in ("text",):
        return "text"
    return t


st.title("NEO Potentials — Диагностика")

if not os.path.exists(BLOCKS_PATH):
    st.error(f"Не найден файл {BLOCKS_PATH}.")
    st.stop()

blocks_data = load_json(BLOCKS_PATH)
blocks = blocks_data.get("blocks", [])
potentials_map = build_potentials_dict(blocks_data)

if not isinstance(blocks, list) or not blocks:
    st.error("В neo_blocks.json не найден массив blocks. Ожидаю структуру: {\"blocks\": [ ... ] }")
    st.stop()

if "answers" not in st.session_state:
    st.session_state["answers"] = {}

st.caption("Заполни ответы → нажми **Save responses.json** → потом **Run scoring**.")

# --- Render blocks/questions ---
for b in blocks:
    block_code = b.get("block_code") or b.get("code") or b.get("block_id") or "BLOCK"
    block_name = b.get("block_name") or b.get("name") or ""
    st.header(f"{block_code}. {block_name}".strip())
    goal = b.get("goal") or b.get("purpose") or ""
    if goal:
        st.write(goal)

    questions = b.get("questions", [])
    if not isinstance(questions, list):
        st.warning("В блоке questions не массив — пропускаю блок.")
        continue

    for q in questions:
        if not isinstance(q, dict):
            continue

        qid = q.get("id")
        if not qid:
            continue

        qtype_raw = q.get("type", "")
        qtype = normalize_qtype(qtype_raw)

        prompt = q.get("prompt") or q.get("title") or ""
        if prompt:
            st.subheader(prompt)
        else:
            st.subheader(f"Вопрос {qid}")

        options = q.get("options", [])
        if options is None:
            options = []
        if not isinstance(options, list):
            options = []

        # build options display
        option_labels = []
        option_ru_values = []

        for opt in options:
            if not isinstance(opt, dict):
                continue

            ru = option_to_ru(opt, potentials_map)
            if ru is None:
                # if we cannot map it, skip to avoid crashing
                continue

            label = opt.get("label") or opt.get("text") or opt.get("title") or ru
            option_labels.append(str(label))
            option_ru_values.append(ru)

        key = f"ans_{qid}"

        # Single
        if qtype == "single":
            if not option_labels:
                st.warning("Нет options для single-вопроса.")
            else:
                chosen = st.radio("Выберите 1 вариант:", option_labels, index=None, key=key)
                if chosen is not None:
                    idx = option_labels.index(chosen)
                    st.session_state["answers"][qid] = {"selected": [option_ru_values[idx]]}

        # Multi
        elif qtype == "multi":
            if not option_labels:
                st.warning("Нет options для multi-вопроса.")
            else:
                max_choices = q.get("max_choices")
                if isinstance(max_choices, str) and max_choices.isdigit():
                    max_choices = int(max_choices)
                if not isinstance(max_choices, int):
                    max_choices = None

                chosen = st.multiselect(
                    "Выберите варианты" + (f" (макс {max_choices})" if max_choices else "") + ":",
                    option_labels,
                    key=key
                )

                selected_ru = [option_ru_values[option_labels.index(c)] for c in chosen]
                if max_choices:
                    selected_ru = selected_ru[:max_choices]

                st.session_state["answers"][qid] = {"selected": selected_ru}

        # Text
        elif qtype == "text":
            txt = st.text_area("Введите ответ:", key=key)
            st.session_state["answers"][qid] = {"text": txt}

        # Special types
        elif qtype == "matrix_time":
            st.info("Тип matrix_time пока не отрисован в UI. Добавим позже отдельным экраном.")
        else:
            st.warning(f"Тип вопроса '{qtype_raw}' пока не поддержан в UI.")

        # Optional comment field
        if bool(q.get("text_field", False)):
            note = st.text_input("Комментарий (необязательно):", key=f"note_{qid}")
            st.session_state["answers"].setdefault(qid, {})
            st.session_state["answers"][qid]["note"] = note

        st.divider()


# --- Controls ---
col1, col2, col3 = st.columns(3)

with col1:
    if st.button("Save responses.json"):
        payload = {
            "respondent_id": "demo_user",
            "answers": st.session_state["answers"]
        }
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
                st.success("Скоринг выполнен.")
                if os.path.exists(REPORT_PATH):
                    st.json(load_json(REPORT_PATH))
                else:
                    st.warning("report.json не найден после скоринга. Проверь права записи в Streamlit Cloud.")

with col3:
    st.write("Файлы в папке:")
    try:
        st.code("\n".join(sorted(os.listdir("."))))
    except Exception as e:
        st.code(f"Не могу прочитать директорию: {e}")
