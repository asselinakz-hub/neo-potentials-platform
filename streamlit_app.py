import json
import os
import re
import subprocess
import time
import streamlit as st

BLOCKS_PATH = "neo_blocks.json"
DATA_DIR = "data"
RESP_DIR = os.path.join(DATA_DIR, "responses")
REPORT_DIR = os.path.join(DATA_DIR, "reports")
CLIENTS_PATH = os.path.join(DATA_DIR, "clients.json")

SCORING_SCRIPT = "neo_scoring.py"

st.set_page_config(page_title="NEO Potentials — Диагностика", layout="wide")
st.title("NEO Potentials — Диагностика")

# -----------------------
# Helpers
# -----------------------
def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(RESP_DIR, exist_ok=True)
    os.makedirs(REPORT_DIR, exist_ok=True)

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_clients():
    if not os.path.exists(CLIENTS_PATH):
        return []
    try:
        return load_json(CLIENTS_PATH)
    except Exception:
        return []

def save_clients(clients_list):
    save_json(CLIENTS_PATH, clients_list)

def slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9а-яё]+", "-", s, flags=re.IGNORECASE)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "client"

def phone_digits(phone: str) -> str:
    return re.sub(r"\D+", "", phone or "")

def build_client_id(name: str, phone: str) -> str:
    # стабильный id: имя + последние 6 цифр
    d = phone_digits(phone)
    suffix = d[-6:] if len(d) >= 6 else d
    return f"{slugify(name)}_{suffix or 'phone'}"

def flatten_questions(blocks_data):
    """Возвращает список вопросов в порядке блоков."""
    blocks = blocks_data.get("blocks", [])
    items = []
    for b in blocks:
        b_code = b.get("block_code") or b.get("code") or b.get("block_id") or ""
        b_name = b.get("block_name") or b.get("name") or ""
        for q in b.get("questions", []):
            items.append({
                "block_id": b.get("block_id"),
                "block_code": b_code,
                "block_name": b_name,
                "q": q
            })
    return items

def option_pid(opt: dict):
    return opt.get("potential_id") or opt.get("potential") or opt.get("id") or opt.get("code")

def option_label(opt: dict):
    return opt.get("label") or opt.get("text") or opt.get("title")

# -----------------------
# Init
# -----------------------
ensure_dirs()

if not os.path.exists(BLOCKS_PATH):
    st.error(f"Не найден файл {BLOCKS_PATH} в корне репозитория.")
    st.stop()

blocks_data = load_json(BLOCKS_PATH)
questions = flatten_questions(blocks_data)

if not questions:
    st.error("В neo_blocks.json не найдены вопросы (blocks[].questions[] пусто).")
    st.stop()

# session state
if "step" not in st.session_state:
    st.session_state.step = 0  # 0 = форма клиента, 1..N = вопросы
if "client" not in st.session_state:
    st.session_state.client = {"name": "", "phone": "", "client_id": ""}
if "answers" not in st.session_state:
    st.session_state.answers = {}  # {qid: {selected:[...], text, note}}
if "saved_paths" not in st.session_state:
    st.session_state.saved_paths = {"responses": None, "report": None}

total_q = len(questions)

# -----------------------
# Step 0: client info
# -----------------------
if st.session_state.step == 0:
    st.subheader("Данные клиента")

    name = st.text_input("Имя клиента*", value=st.session_state.client.get("name", ""))
    phone = st.text_input("Телефон*", value=st.session_state.client.get("phone", ""), help="Можно с пробелами/скобками — мы сами почистим.")

    colA, colB = st.columns([1, 2])
    with colA:
        if st.button("Начать диагностику ➜"):
            if not name.strip():
                st.error("Введите имя клиента.")
                st.stop()
            if len(phone_digits(phone)) < 7:
                st.error("Введите корректный телефон (минимум 7 цифр).")
                st.stop()

            cid = build_client_id(name, phone)
            st.session_state.client = {"name": name.
strip(), "phone": phone.strip(), "client_id": cid}

            # register in clients.json
            clients = load_clients()
            now = int(time.time())
            # update or append
            found = False
            for c in clients:
                if c.get("client_id") == cid:
                    c["name"] = name.strip()
                    c["phone"] = phone.strip()
                    c["updated_at"] = now
                    found = True
                    break
            if not found:
                clients.append({"client_id": cid, "name": name.strip(), "phone": phone.strip(), "created_at": now, "updated_at": now})
            save_clients(clients)

            st.session_state.step = 1
            st.rerun()

    st.caption("После заполнения нажми Начать диагностику — вопросы пойдут по одному, с прогрессом.")
    st.stop()

# -----------------------
# Wizard UI: steps 1..N
# -----------------------
idx = st.session_state.step - 1
idx = max(0, min(idx, total_q - 1))

progress = (idx + 1) / total_q
st.progress(progress, text=f"Вопрос {idx+1} из {total_q}")

meta = questions[idx]
q = meta["q"]
qid = q.get("id")
qtype = (q.get("type") or "").strip().lower()
prompt = q.get("prompt") or ""

st.markdown(f"### {meta['block_code']}. {meta['block_name']}")
st.write(prompt)

# load previous answer if any
prev = st.session_state.answers.get(qid, {})
prev_selected = prev.get("selected", [])
prev_text = prev.get("text", "")
prev_note = prev.get("note", "")

options = q.get("options", []) or []
labels = []
ids = []

for opt in options:
    pid = option_pid(opt)
    lbl = option_label(opt) or pid
    if pid is None:
        continue
    labels.append(str(lbl))
    ids.append(str(pid))

# Render by type
if qtype in ("single_choice", "single_select", "radio"):
    # determine default index
    default_idx = None
    if prev_selected:
        try:
            # match by pid
            pi = ids.index(prev_selected[0])
            default_idx = pi
        except Exception:
            default_idx = None

    choice = st.radio(
        "Выберите 1 вариант:",
        options=list(range(len(labels))),
        format_func=lambda i: labels[i],
        index=default_idx
    )

    st.session_state.answers[qid] = {"selected": [ids[choice]]}

elif qtype in ("multi_choice", "multi_select", "checkbox", "multiple_choice"):
    max_choices = q.get("max_choices")
    # default selections by indexes
    default_idxs = []
    for s in prev_selected:
        if s in ids:
            default_idxs.append(ids.index(s))

    chosen_idxs = st.multiselect(
        f"Выберите варианты{f' (макс {max_choices})' if max_choices else ''}:",
        options=list(range(len(labels))),
        default=default_idxs,
        format_func=lambda i: labels[i],
    )
    selected_ids = [ids[i] for i in chosen_idxs]
    if max_choices:
        selected_ids = selected_ids[: int(max_choices)]
    st.session_state.answers[qid] = {"selected": selected_ids}

elif qtype == "text":
    txt = st.text_area("Введите ответ:", value=prev_text, height=160)
    st.session_state.answers[qid] = {"text": txt}

else:
    st.warning(f"Тип вопроса '{qtype}' пока не поддержан. Пропускаю.")
    st.session_state.answers[qid] = prev or {}

# optional text_field note
if bool(q.get("text_field", False)):
    note = st.text_input("Комментарий (необязательно):", value=prev_note)
    st.session_state.answers.setdefault(qid, {})
    st.session_state.answers[qid]["note"] = note

# navigation buttons
nav1, nav2, nav3, nav4 = st.columns([1, 1, 1, 2])

with nav1:
    if st.button("⬅ Назад", disabled=(idx == 0)):
        st.session_state.step = max(1, st.session_state.step - 1)
        st.rerun()

with nav2:
    if st.button("Далее ➜", disabled=(idx >= total_q - 1)):
        st.session_state.step = min(total_q, st.session_state.step + 1)
        st.rerun()

with nav3:
    if st.button("💾 Save"):
        # save per client
        c = st.session_state.client
        payload = {
            "respondent": c,
            "respondent_id": c["client_id"],
            "answers": st.
session_state.answers,
        }
        resp_path = os.path.join(RESP_DIR, f"{c['client_id']}.json")
        save_json(resp_path, payload)
        st.session_state.saved_paths["responses"] = resp_path
        st.success(f"Сохранено: {resp_path}")

with nav4:
    if st.button("✅ Finish & Run scoring", disabled=(idx != total_q - 1)):
        c = st.session_state.client
        payload = {
            "respondent": c,
            "respondent_id": c["client_id"],
            "answers": st.session_state.answers,
        }
        resp_path = os.path.join(RESP_DIR, f"{c['client_id']}.json")
        report_path = os.path.join(REPORT_DIR, f"{c['client_id']}.json")
        save_json(resp_path, payload)

        cmd = ["python", SCORING_SCRIPT, "--blocks", BLOCKS_PATH, "--answers", resp_path, "--out", report_path]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            st.error("Ошибка при скоринге:")
            st.code(result.stderr or result.stdout)
        else:
            st.success("Готово! Отчёт сформирован.")
            st.session_state.saved_paths["responses"] = resp_path
            st.session_state.saved_paths["report"] = report_path

            # show report nicely (минимально)
            rep = load_json(report_path)
            st.divider()
            st.subheader("Результат (черновой вид)")
            st.write(f"Клиент: {c['name']}, тел: **{c['phone']}**")
            st.json(rep)

            with open(report_path, "rb") as f:
                st.download_button("⬇️ Скачать report.json", data=f, file_name=f"{c['client_id']}_report.json", mime="application/json")
