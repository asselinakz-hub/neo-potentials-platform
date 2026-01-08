import json
import os
import subprocess
import streamlit as st

BLOCKS_PATH = "neo_blocks.json"
RESPONSES_PATH = "responses.json"
REPORT_PATH = "report.json"

st.set_page_config(page_title="NEO Potentials — Диагностика", layout="wide")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


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


def norm_type(t):
    t = (t or "").lower()
    if t in ("single_choice", "single_select", "radio"):
        return "single"
    if t in ("multi_choice", "multi_select", "checkbox"):
        return "multi"
    if t in ("text", "textarea"):
        return "text"
    if t in ("scale",):
        return "scale"
    return "unknown"


st.title("NEO Potentials — Диагностика")

blocks_data = load_json(BLOCKS_PATH)
blocks = blocks_data.get("blocks", [])
potentials = blocks_data.get("potentials", {})

if "answers" not in st.session_state:
    st.session_state.answers = {}

for block in blocks:
    st.header(f'{block.get("block_code")}. {block.get("block_name")}')
    if block.get("goal"):
        st.write(block["goal"])

    for q in block.get("questions", []):
        qid = q.get("id")
        qtype = norm_type(q.get("type"))
        prompt = q.get("prompt")

        st.subheader(prompt)

        options = q.get("options", [])
        key = f"ans_{qid}"

        if qtype in ("single", "multi") and options:
            labels = []
            ids = []

            for opt in options:
                pid = opt.get("potential_id") or opt.get("id") or opt.get("code")
                label = opt.get("label") or opt.get("text")

                if pid in RU2ID:
                    pid = RU2ID[pid]

                if not label:
                    label = pid

                labels.append(label)
                ids.append(pid)

            if qtype == "single":
                choice = st.radio("Выберите вариант:", labels, key=key)
                if choice:
                    idx = labels.index(choice)
                    st.session_state.answers[qid] = {"selected": [ids[idx]]}

            else:
                choice = st.multiselect("Выберите варианты:", labels, key=key)
                selected = [ids[labels.index(c)] for c in choice]
                st.session_state.answers[qid] = {"selected": selected}

        elif qtype == "text":
            txt = st.text_area("Ответ:", key=key)
            st.session_state.answers[qid] = {"text": txt}

        elif qtype == "scale":
            val = st.slider("Оценка:", 1, 10, 5, key=key)
            st.session_state.answers[qid] = {"value": val}

        else:
            st.info("Тип вопроса пока без UI")

        st.divider()

if st.button("Save responses.json"):
    save_json(RESPONSES_PATH, {"answers": st.session_state.answers})
    st.success("responses.json сохранён")

if st.button("Run scoring"):
    subprocess.run(
        ["python", "neo_scoring.py", "--blocks", BLOCKS_PATH, "--answers", RESPONSES_PATH, "--out", REPORT_PATH]
    )
    if os.path.exists(REPORT_PATH):
        st.json(load_json(REPORT_PATH))
