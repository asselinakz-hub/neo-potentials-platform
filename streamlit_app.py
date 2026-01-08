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

st.title("NEO Potentials — Диагностика")

if not os.path.exists(BLOCKS_PATH):
    st.error(f"Не найден файл {BLOCKS_PATH}.")
    st.stop()

blocks_data = load_json(BLOCKS_PATH)
blocks = blocks_data.get("blocks", [])
# --- Potentials dictionary (safe) ---
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

potentials_list = blocks_data.get("potentials", [])

potentials = {}
if isinstance(potentials_list, list):
    for p in potentials_list:
        if isinstance(p, dict):
            pid = p.get("potential_id") or p.get("id") or p.get("code")
            name = p.get("name") or p.get("title")
            if pid and name:
                potentials[str(pid)] = str(name)

# fallback if file has no potentials section or wrong format
if not potentials:
    potentials = DEFAULT_POTENTIALS
# storage for answers in session
if "answers" not in st.session_state:
    st.session_state.answers = {}

st.caption("Заполняй ответы → нажми Save → потом Run scoring.")

for b in blocks:
    st.header(f'{b["block_code"]}. {b["block_name"]}')
    st.write(b.get("goal", ""))

    for q in b.get("questions", []):
        qid = q["id"]
        qtype = q["type"]
        prompt = q["prompt"]
        st.subheader(prompt)

        options = q.get("options", [])
        option_labels = []
        option_ids = []

        for opt in options:
           # option can be {"potential_id": "..."} OR {"potential": "..."} OR {"potential": "Янтарь"} etc.
pid = opt.get("potential_id") or opt.get("potential") or opt.get("id") or opt.get("code")
label = opt.get("label") or opt.get("text") or opt.get("title") or str(pid)

if pid is None:
    continue
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

pid = RU2ID.get(pid, pid)
            option_ids.append(pid)
            option_labels.append(f"{label}  ({potentials.get(pid, pid)})")

        key = f"ans_{qid}"

        if qtype == "single_choice":
            chosen = st.radio("Выберите 1 вариант:", option_labels, index=None, key=key)
            if chosen is not None:
                idx = option_labels.index(chosen)
                st.session_state.answers[qid] = {"selected": [option_ids[idx]]}

        elif qtype == "multi_choice":
            max_choices = q.get("max_choices", None)
            chosen = st.multiselect(
                f"Выберите варианты{' (макс ' + str(max_choices) + ')' if max_choices else ''}:",
                option_labels,
                key=key
            )
            selected_ids = [option_ids[option_labels.index(c)] for c in chosen]
            if max_choices:
                selected_ids = selected_ids[:max_choices]
            st.session_state.answers[qid] = {"selected": selected_ids}

        elif qtype == "text":
            txt = st.text_area("Введите ответ:", key=key)
            st.session_state.answers[qid] = {"text": txt}

        elif qtype == "matrix_time":
            st.info("Этот вопрос (matrix_time) пока пропускаем в UI. Добавим позже красиво.")
            # Можно будет добавить отдельный UI для fast/slow списков
        else:
            st.warning(f"Тип вопроса '{qtype}' пока не поддержан в UI.")
        
        if q.get("text_field", False):
            note = st.text_input("Комментарий (необязательно):", key=f"note_{qid}")
            st.session_state.answers.setdefault(qid, {})
            st.session_state.answers[qid]["note"] = note

        st.divider()

col1, col2, col3 = st.columns(3)

with col1:
    if st.button("Save responses.json"):
        payload = {
            "respondent_id": "demo_user",
            "answers": st.session_state.answers
        }
        save_json(RESPONSES_PATH, payload)
        st.success(f"Сохранила ответы в {RESPONSES_PATH}")

with col2:
    if st.button("Run scoring"):
        if not os.path.exists(RESPONSES_PATH):
            st.error("Сначала нажми Save responses.json")
        else:
            # Запускаем твой CLI-скрипт
            cmd = ["python", "neo_scoring.py", "--blocks", BLOCKS_PATH, "--answers", RESPONSES_PATH, "--out", REPORT_PATH]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                st.error("Ошибка при запуске скоринга:")
                st.code(result.stderr or result.stdout)
            else:
                st.success("Скоринг выполнен. Смотри report.json ниже.")
                if os.path.exists(REPORT_PATH):
                    st.json(load_json(REPORT_PATH))

with col3:
    st.write("Файлы в папке:")
    st.code("\n".join(sorted(os.listdir("."))))
