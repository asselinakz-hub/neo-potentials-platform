import json
import os
import re
import streamlit as st

from neo_scoring import score_blocks

BLOCKS_PATH = "neo_blocks.json"
DATA_DIR = "data"  # тут будут папки клиентов
CLIENTS_DIR = os.path.join(DATA_DIR, "clients")
os.makedirs(CLIENTS_DIR, exist_ok=True)

st.set_page_config(page_title="NEO Potentials — Диагностика", layout="centered")

# -------------------------
# Helpers
# -------------------------
def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^a-z0-9_а-яё-]", "", s, flags=re.IGNORECASE)
    return s or "client"


def normalize_phone(p: str) -> str:
    digits = re.sub(r"\D+", "", (p or ""))
    return digits


def get_opt_label(opt: dict) -> str:
    # показываем клиенту только "человеческий" текст
    return str(
        opt.get("label")
        or opt.get("text")
        or opt.get("title")
        or opt.get("name")
        or ""
    ).strip()


def get_opt_pid(opt: dict):
    # id/код опции (для скоринга)
    return (
        opt.get("potential_id")
        or opt.get("potential")
        or opt.get("id")
        or opt.get("code")
        or opt.get("value")
    )


def flatten_questions(blocks: list) -> list:
    items = []
    for b in blocks:
        for q in b.get("questions", []):
            items.append({"block": b, "q": q})
    return items


# -------------------------
# Load blocks
# -------------------------
if not os.path.exists(BLOCKS_PATH):
    st.error(f"Не найден {BLOCKS_PATH} в корне репозитория.")
    st.stop()

blocks_data = load_json(BLOCKS_PATH)
blocks = blocks_data.get("blocks", [])
questions = flatten_questions(blocks)
total = len(questions)

if total == 0:
    st.error("В neo_blocks.json нет вопросов.")
    st.stop()


# -------------------------
# Session state init
# -------------------------
if "step" not in st.session_state:
    st.session_state.step = 0

if "answers" not in st.session_state:
    st.session_state.answers = {}

if "respondent" not in st.session_state:
    st.session_state.respondent = {"name": "", "phone": "", "client_id": ""}

if "started" not in st.session_state:
    st.session_state.started = False


# -------------------------
# START SCREEN (name + phone only once)
# -------------------------
if not st.session_state.started:
    st.title("NEO Potentials — Диагностика")
    st.write("Введите имя и телефон — дальше они показываться не будут.")

    name = st.text_input("Имя", value=st.session_state.respondent.get("name", ""))
    phone = st.text_input("Телефон", value=st.session_state.respondent.get("phone", ""))

    if st.button("Начать"):
        name_clean = (name or "").strip()
        phone_clean = normalize_phone(phone)

        if not name_clean:
            st.error("Введите имя.")
            st.stop()

        # телефон можно оставить пустым, но лучше чтобы был
        client_id = slugify(name_clean)
        if phone_clean:
            client_id = f"{client_id}_{phone_clean}"

        st.session_state.respondent = {
            "name": name_clean,
            "phone": phone_clean,
            "client_id": client_id,
        }
        st.session_state.started = True
        st.session_state.step = 0
        st.rerun()

    st.stop()


# -------------------------
# QUESTION SCREEN (one per page)
# -------------------------
idx = st.session_state.step
idx = max(0, min(idx, total - 1))
st.session_state.step = idx

item = questions[idx]
block = item["block"]
q = item["q"]

qid = q.get("id")
qtype = str(q.get("type", "")).strip().lower()
prompt = str(q.get("prompt", "")).strip()

# progress
st.progress((idx + 1) / total)
st.caption(f"Вопрос {idx + 1} из {total}")

# big question text
st.markdown(
    f"<h2 style='text-align:center; line-height:1.25'>{prompt}</h2>",
    unsafe_allow_html=True
)

# prepare options
options = q.get("options", []) or []
labels = []
pids = []

for opt in options:
    if not isinstance(opt, dict):
        continue
    pid = get_opt_pid(opt)
    label = get_opt_label(opt)
    if pid is None:
        continue
    if not label:
        label = str(pid)
    labels.append(label)
    pids.append(pid)

# render input
key = f"ans_{qid}"

if qtype in ("single_choice", "single_select", "radio"):
    prev = st.session_state.answers.get(qid, {}).get("selected", [])
    prev_pid = prev[0] if prev else None
    prev_index = None
    if prev_pid in pids:
        prev_index = pids.index(prev_pid)

    choice = st.radio(
        "Выберите один вариант:",
        options=list(range(len(labels))),
        format_func=lambda i: labels[i],
        index=prev_index if prev_index is not None else None,
        key=key,
        label_visibility="collapsed",
    )
    if choice is not None:
        st.session_state.answers[qid] = {"selected": [pids[choice]]}

elif qtype in ("multi_choice", "multi_select", "checkbox", "multiple_choice"):
    prev = st.session_state.answers.get(qid, {}).get("selected", [])
    prev_labels = [labels[pids.index(pid)] for pid in prev if pid in pids]

    chosen = st.multiselect(
        "Выберите варианты:",
        options=labels,
        default=prev_labels,
        key=key,
        label_visibility="collapsed",
    )
    selected_ids = [pids[labels.index(c)] for c in chosen]
    max_choices = q.get("max_choices")
    if isinstance(max_choices, int) and max_choices > 0:
        selected_ids = selected_ids[:max_choices]
    st.session_state.answers[qid] = {"selected": selected_ids}

elif qtype == "text":
    prev_txt = st.session_state.answers.get(qid, {}).get("text", "")
    txt = st.text_area("Ваш ответ:", value=prev_txt, key=key, label_visibility="collapsed")
    st.session_state.answers[qid] = {"text": txt}

else:
    st.info(f"Тип вопроса '{qtype}' пока пропускаем.")
    st.session_state.answers.setdefault(qid, {})

# navigation
c1, c2 = st.columns(2)

with c1:
    if st.button("← Назад", use_container_width=True, disabled=(idx == 0)):
        st.session_state.step = max(0, idx - 1)
        st.rerun()

with c2:
    is_last = (idx == total - 1)
    next_label = "Завершить" if is_last else "Далее →"
    if st.button(next_label, use_container_width=True):
        if not is_last:
            st.session_state.step = min(total - 1, idx + 1)
            st.rerun()
        else:
            # FINISH: save + score
            client_id = st.session_state.respondent["client_id"]
            client_dir = os.path.join(DATA_DIR, client_id)
            responses_path = os.path.join(client_dir, "responses.json")
            report_path = os.path.join(client_dir, "report.json")

            payload = {
                "respondent": st.session_state.respondent,
                "respondent_id": client_id,
                "answers": st.session_state.answers,
            }
            save_json(responses_path, payload)

            report = score_blocks(blocks_data, payload)
            save_json(report_path, report)

            st.success("Готово! Результат сохранён.")
            st.write("Теперь мастер увидит клиента и результат в Master Panel.")
            st.stop()