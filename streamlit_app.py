import json
import os
import re
import time
import streamlit as st

# --- try import scoring ---
try:
    from neo_scoring import score_blocks
except Exception as e:
    st.error("Не могу импортировать score_blocks из neo_scoring.py. Проверь, что neo_scoring.py лежит в корне и внутри есть def score_blocks(...).")
    st.code(str(e))
    st.stop()

BLOCKS_PATH = "neo_blocks.json"
DATA_DIR = "data"
CLIENTS_DIR = os.path.join(DATA_DIR, "clients")
os.makedirs(CLIENTS_DIR, exist_ok=True)

st.set_page_config(page_title="NEO Potentials — Диагностика", layout="centered")


# ---------------- helpers ----------------
def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^a-z0-9а-яё\-]", "", s, flags=re.IGNORECASE)
    s = s.strip("-")
    return s or "client"


def get_opt_label(opt: dict) -> str:
    return opt.get("label") or opt.get("text") or opt.get("title") or ""


def get_opt_potential(opt: dict) -> str:
    return (opt.get("potential") or opt.get("potential_id") or opt.get("id") or opt.get("code") or "").strip()


def is_single(qtype: str) -> bool:
    qtype = (qtype or "").lower()
    return qtype in ("single_select", "single_choice", "radio")


def is_multi(qtype: str) -> bool:
    qtype = (qtype or "").lower()
    return qtype in ("multi_select", "multi_choice", "checkbox")


def normalize_blocks(blocks_data: dict):
    blocks = blocks_data.get("blocks", [])
    if not isinstance(blocks, list):
        return []

    flat = []
    for b in blocks:
        bname = b.get("block_name") or b.get("name") or ""
        bcode = b.get("block_code") or b.get("code") or ""
        qs = b.get("questions", [])
        if not isinstance(qs, list):
            continue
        for q in qs:
            q2 = dict(q)
            q2["_block_name"] = bname
            q2["_block_code"] = bcode
            flat.append(q2)

    # сортируем по order если есть
    def keyfn(q):
        try:
            return int(q.get("order", 9999))
        except Exception:
            return 9999

    flat.sort(key=keyfn)
    return flat


# ---------------- load blocks ----------------
if not os.path.exists(BLOCKS_PATH):
    st.error(f"Не найден файл {BLOCKS_PATH} в корне репозитория.")
    st.stop()

try:
    blocks_data = load_json(BLOCKS_PATH)
except Exception as e:
    st.error("neo_blocks.json битый или не читается.")
    st.code(str(e))
    st.stop()

questions = normalize_blocks(blocks_data)
if not questions:
    st.error("В neo_blocks.json не найдено вопросов: blocks -> questions пусто.")
    st.stop()


# ---------------- session state ----------------
if "client_created" not in st.session_state:
    st.session_state.client_created = False

if "respondent" not in st.session_state:
    st.session_state.respondent = {}

if "answers" not in st.session_state:
    st.session_state.answers = {}

if "step" not in st.session_state:
    st.session_state.step = 0


# ---------------- UI: start screen ----------------
st.title("NEO Potentials — Диагностика")

if not st.session_state.client_created:
    st.subheader("Данные клиента (минимум)")

    name = st.text_input("Имя", value="")
    phone = st.text_input("Телефон", value="")

    st.caption("После старта мы не будем показывать имя/телефон на каждом вопросе — только сохраним в профиле клиента.")

    if st.button("Начать тест →", use_container_width=True):
        if not name.strip():
            st.error("Введи имя.")
            st.stop()

        ts = int(time.time())
        client_id = f"{slugify(name)}-{ts}"

        st.session_state.respondent = {
            "client_id": client_id,
            "name": name.strip(),
            "phone": phone.strip(),
            "created_at": ts,
        }

        # создаём папку клиента и сохраняем profile.json сразу
        client_dir = os.path.join(CLIENTS_DIR, client_id)
        os.makedirs(client_dir, exist_ok=True)
        save_json(os.path.join(client_dir, "profile.json"), st.session_state.respondent)

        st.session_state.client_created = True
        st.session_state.step = 0
        st.session_state.answers = {}
        st.rerun()

    st.stop()


# ---------------- UI: one-question-per-page ----------------
idx = int(st.session_state.step)
idx = max(0, min(idx, len(questions) - 1))
q = questions[idx]

total = len(questions)
progress = (idx + 1) / total

st.progress(progress)
st.caption(f"Вопрос {idx + 1} из {total} • Осталось: {total - (idx + 1)}")

prompt = q.get("prompt") or ""
st.markdown(f"<h2 style='text-align:center; margin-top: 0.2rem;'>{prompt}</h2>", unsafe_allow_html=True)

qtype = (q.get("type") or "").lower()
qid = q.get("id")

if not qid:
    st.error("У вопроса нет id. Проверь neo_blocks.json.")
    st.stop()

options = q.get("options", []) or []
option_labels = []
option_potentials = []

for opt in options:
    pot = get_opt_potential(opt)
    lab = get_opt_label(opt)
    if not pot or not lab:
        continue
    option_potentials.append(pot)   # amber / citrine / heliodor ...
    option_labels.append(lab)       # человекочитаемо

key = f"ui_{qid}"

# restore previous
prev = st.session_state.answers.get(qid, {})
prev_selected = prev.get("selected", []) if isinstance(prev, dict) else []

# --- render answer input ---
if is_single(qtype):
    # radio needs index, so we'll map selected -> label
    default_index = None
    if prev_selected:
        try:
            pot0 = prev_selected[0]
            if pot0 in option_potentials:
                default_index = option_potentials.index(pot0)
        except Exception:
            default_index = None

    chosen = st.radio(
        "Выберите 1 вариант:",
        option_labels,
        index=default_index,
        key=key
    )

    if chosen is not None:
        pos = option_labels.index(chosen)
        pot = option_potentials[pos]
        st.session_state.answers[qid] = {"selected": [pot]}

elif is_multi(qtype):
    max_choices = q.get("max_choices")
    default = []
    for pot in prev_selected:
        if pot in option_potentials:
            default.append(option_labels[option_potentials.index(pot)])

    chosen_list = st.multiselect(
        "Выберите варианты:",
        option_labels,
        default=default,
        key=key
    )

    selected_pots = [option_potentials[option_labels.index(x)] for x in chosen_list]
    if max_choices:
        selected_pots = selected_pots[: int(max_choices)]
    st.session_state.answers[qid] = {"selected": selected_pots}

elif qtype == "text":
    default_text = prev.get("text", "") if isinstance(prev, dict) else ""
    txt = st.text_area("Введите ответ:", value=default_text, key=key)
    st.session_state.answers[qid] = {"text": txt}

else:
    st.info("Этот тип вопроса пока не поддержан. Пропусти его кнопкой Далее →")
    # оставим пустой ответ


# optional note/comment
if q.get("text_field", False):
    prev_note = ""
    if isinstance(prev, dict):
        prev_note = prev.get("note", "")
    note = st.text_input("Комментарий (необязательно):", value=prev_note, key=f"note_{qid}")
    st.session_state.answers.setdefault(qid, {})
    if isinstance(st.session_state.answers[qid], dict):
        st.session_state.answers[qid]["note"] = note


st.divider()

c1, c2, c3 = st.columns([1, 2, 1])

with c1:
    if st.button("← Назад", use_container_width=True, disabled=(idx == 0)):
        st.session_state.step = max(0, idx - 1)
        st.rerun()

with c2:
    is_last = (idx == total - 1)
    next_label = "Завершить ✅" if is_last else "Далее →"
    if st.button(next_label, use_container_width=True):
        if not is_last:
            st.session_state.step = min(total - 1, idx + 1)
            st.rerun()
        else:
            # FINISH: save + score
            client_id = st.session_state.respondent["client_id"]
            client_dir = os.path.join(CLIENTS_DIR, client_id)
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

            st.success("Готово! Результаты сохранены ✅")
            st.caption("Теперь они должны появиться в Master Panel в списке клиентов.")
            st.stop()

with c3:
    st.write("")  # пусто, чтобы красиво центрировалось