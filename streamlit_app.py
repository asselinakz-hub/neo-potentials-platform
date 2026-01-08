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


def get_potential_id(opt):
    pid = opt.get("potential_id") or opt.get("potential") or opt.get("id") or opt.get("code")
    if pid is None:
        return None
    return RU2ID.get(pid, str(pid))


def get_label(opt):
    return opt.get("label") or opt.get("text") or opt.get("title") or opt.get("name") or ""


st.title("NEO Potentials — Диагностика")

blocks_data = load_json(BLOCKS_PATH)
blocks = blocks_data.get("blocks", [])

potentials = {}
pots = blocks_data.get("potentials")

if isinstance(pots, dict):
    for k, v in pots.items():
        if isinstance(v, dict):
            potentials[k] = v.get("ru", k)
        else:
            potentials[k] = v
else:
    potentials = DEFAULT_POTENTIALS

if "answers" not in st.session_state:
    st.session_state.answers = {}

st.caption("Ответь → Save → Run scoring")

for block in blocks:
    st.header(f"{block.get('block_code')}. {block.get('block_name')}")
    st.write(block.get("goal", ""))

    for q in block.get("questions", []):
        qid = q.get("id")
        qtype = q.get("type")
        st.subheader(q.get("prompt", ""))

        key = f"ans_{qid}"

        if qtype == "single_choice":
            labels = []
            ids = []

            for opt in q.get("options", []):
                pid = get_potential_id(opt)
                if pid:
                    ids.append(pid)
                    labels.append(f"{get_label(opt)} ({potentials.get(pid, pid)})")

            choice = st.radio("Выбери вариант:", labels, index=None, key=key)
            if choice:
                idx = labels.index(choice)
                st.session_state.answers[qid] = {"selected": [ids[idx]]}

        elif qtype == "multi_choice":
            labels = []
            ids = []

            for opt in q.get("options", []):
                pid = get_potential_id(opt)
                if pid:
                    ids.append(pid)
                    labels.append(f"{get_label(opt)} ({potentials.get(pid, pid)})")

            choice = st.multiselect("Выбери варианты:", labels, key=key)
            st.session_state.answers[qid] = {
                "selected": [ids[labels.index(c)] for c in choice]
            }

        elif qtype == "text":
            txt = st.text_area("Ответ:", key=key)
            st.session_state.answers[qid] = {"text": txt}

        elif qtype == "scale":
            val = st.slider("Оценка:", 1, 10, 5, key=key)
            st.session_state.answers[qid] = {"value": val}

        st.divider()


col1, col2 = st.columns(2)

with col1:
    if st.button("Save responses.json"):
        save_json(RESPONSES_PATH, {
            "respondent_id": "demo_user",
            "answers": st.session_state.answers
        })
        st.success("responses.json сохранён")

with col2:
    if st.button("Run scoring"):
        cmd = ["python", "neo_scoring.py", "--blocks", BLOCKS_PATH, "--answers", RESPONSES_PATH, "--out", REPORT_PATH]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            st.error(res.stderr)
        else:
            st.success("Скоринг выполнен")
            st.json(load_json(REPORT_PATH))
