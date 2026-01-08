import os
import json
import uuid
import streamlit as st

from neo_scoring import score_blocks

# ---------------- CONFIG ----------------
BLOCKS_PATH = "neo_blocks.json"
DATA_DIR = "data"
CLIENTS_DIR = os.path.join(DATA_DIR, "clients")

os.makedirs(CLIENTS_DIR, exist_ok=True)

st.set_page_config(page_title="NEO Potentials", layout="centered")

# ---------------- HELPERS ----------------
def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ---------------- LOAD BLOCKS ----------------
blocks_data = load_json(BLOCKS_PATH)
blocks = blocks_data["blocks"]

# flatten questions
questions = []
for block in blocks:
    for q in block["questions"]:
        questions.append(q)

TOTAL = len(questions)

# ---------------- SESSION INIT ----------------
if "step" not in st.session_state:
    st.session_state.step = 0

if "answers" not in st.session_state:
    st.session_state.answers = {}

if "client_id" not in st.session_state:
    st.session_state.client_id = str(uuid.uuid4())[:8]

# ---------------- UI ----------------
st.progress((st.session_state.step + 1) / TOTAL)
st.caption(f"Вопрос {st.session_state.step + 1} из {TOTAL}")

question = questions[st.session_state.step]

st.markdown(
    f"<h2 style='text-align:center'>{question['prompt']}</h2>",
    unsafe_allow_html=True
)

qid = question["id"]
qtype = question["type"]
options = question.get("options", [])

# -------- ANSWERS --------
if qtype == "single_choice":
    labels = [o["label"] for o in options]
    choice = st.radio("", labels, index=None)

    if choice:
        selected = [options[labels.index(choice)]["potential_id"]]
        st.session_state.answers[qid] = {"selected": selected}

elif qtype == "multi_choice":
    labels = [o["label"] for o in options]
    choices = st.multiselect("", labels)

    if choices:
        selected = [
            options[labels.index(c)]["potential_id"]
            for c in choices
        ]
        st.session_state.answers[qid] = {"selected": selected}

elif qtype == "text":
    txt = st.text_area("", height=120)
    st.session_state.answers[qid] = {"text": txt}

# ---------------- NAVIGATION ----------------
st.divider()

col1, col2 = st.columns(2)

with col2:
    label = "Завершить" if st.session_state.step == TOTAL - 1 else "Далее →"

    if st.button(label, use_container_width=True):
        if st.session_state.step < TOTAL - 1:
            st.session_state.step += 1
            st.rerun()
        else:
            # -------- FINISH --------
            client_id = st.session_state.client_id
            client_dir = os.path.join(CLIENTS_DIR, client_id)
            os.makedirs(client_dir, exist_ok=True)

            payload = {
                "respondent_id": client_id,
                "answers": st.session_state.answers
            }

            save_json(
                os.path.join(client_dir, "responses.json"),
                payload
            )

            report = score_blocks(blocks_data, payload)
            save_json(
                os.path.join(client_dir, "report.json"),
                report
            )

            st.success("Готово! Диагностика завершена.")
            st.write("Результат сохранён. Мастер увидит его в панели.")
            st.stop()