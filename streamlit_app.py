import os
import json
import re
import time
import streamlit as st

# --- safe import scoring ---
try:
    from neo_scoring import score_blocks
except Exception as e:
    score_blocks = None
    IMPORT_ERR = str(e)

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
    s = re.sub(r"[^a-z0-9а-яё]+", "_", s, flags=re.IGNORECASE)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or f"client_{int(time.time())}"


def get_blocks_and_questions(blocks_data: dict):
    """
    Терпимый парсер:
    - blocks_data["blocks"] = [ { "questions": [...] }, ... ]
    - blocks_data["blocks"] может отсутствовать, тогда ищем "questions" на верхнем уровне
    """
    blocks = blocks_data.get("blocks")
    if isinstance(blocks, list) and blocks:
        pass
    else:
        # fallback: если вдруг структура другая
        maybe_questions = blocks_data.get("questions")
        if isinstance(maybe_questions, list):
            blocks = [{"id": "b1", "title": "", "questions": maybe_questions}]
        else:
            blocks = []

    all_q = []
    for b_i, b in enumerate(blocks):
        qs = b.get("questions") if isinstance(b, dict) else None
        if not isinstance(qs, list):
            continue
        for q_i, q in enumerate(qs):
            if not isinstance(q, dict):
                continue
            qid = q.get("id") or q.get("qid") or f"b{b_i+1}_q{q_i+1}"
            prompt = q.get("prompt") or q.get("text") or q.get("question") or ""
            qtype = (q.get("type") or q.get("kind") or "single").strip().lower()
            options = q.get("options", [])
            all_q.append(
                {
                    "id": str(qid),
                    "prompt": str(prompt),
                    "type": str(qtype),
                    "options": options,
                }
            )

    return blocks, all_q


def opt_label(o):
    if isinstance(o, dict):
        return o.get("label") or o.get("text") or o.get("ru") or o.get("title") or ""
    return str(o)


def opt_value(o):
    if isinstance(o, dict):
        return o.get("potential_id") or o.get("id") or o.get("value") or opt_label(o)
    return str(o)


def normalize_type(t: str) -> str:
    t = (t or "").lower().strip()
    if t in ["single", "single_choice", "radio", "one", "one_choice", "choose_one"]:
        return "single"
    if t in ["multi", "multi_choice", "checkbox", "choose_many", "multi_select"]:
        return "multi"
    if t in ["text", "free_text", "textarea", "open"]:
        return "text"
    if t in ["scale", "rating", "slider"]:
        return "scale"
    if t in ["fast_slow", "fastslow", "two_speed"]:
        return "fast_slow"
    return t


# ---------------- load blocks ----------------
if not os.path.exists(BLOCKS_PATH):
    st.error(f"Не найден файл {BLOCKS_PATH} в корне репозитория.")
    st.stop()

blocks_data = load_json(BLOCKS_PATH)
_, QUESTIONS = get_blocks_and_questions(blocks_data)

if not QUESTIONS:
    st.error("Я не вижу вопросов в neo_blocks.json. Проверь структуру: blocks -> questions.")
    st.stop()

TOTAL = len(QUESTIONS)

# ---------------- session init ----------------
if "step" not in st.session_state:
    st.session_state.step = 0

if "answers" not in st.session_state:
    st.session_state.answers = {}

if "respondent" not in st.session_state:
    st.session_state.respondent = None


# ---------------- intro (name/phone once) ----------------
if st.session_state.respondent is None:
    st.title("NEO Potentials — Диагностика")
    st.write("Пожалуйста, введите данные (они сохранятся у мастера).")

    name = st.text_input("Имя")
    phone = st.text_input("Телефон")
    c = st.columns(2)

    with c[0]:
        if st.button("Начать тест", use_container_width=True):
            cid = slugify(f"{name}_{phone}")
            st.session_state.respondent = {"name": name.strip(), "phone": phone.strip(), "client_id": cid}
            st.session_state.step = 0
            st.rerun()

    with c[1]:
        st.caption("Дальше имя/телефон показываться не будут.")
    st.stop()


# ---------------- render question page ----------------
idx = int(st.session_state.step)
idx = max(0, min(TOTAL - 1, idx))
q = QUESTIONS[idx]
qid = q["id"]
qtype = normalize_type(q.get("type"))
options = q.get("options", [])

# progress
st.progress((idx + 1) / TOTAL)
st.caption(f"Вопрос {idx + 1} из {TOTAL}")

# big question only (без названий блоков)
st.markdown(
    f"<h2 style='text-align:center; font-size: 34px; line-height: 1.2'>{q.get('prompt','')}</h2>",
    unsafe_allow_html=True
)
st.write("")

# previous saved
prev = st.session_state.answers.get(qid, {})

# render by type
rendered = False

# --- fast/slow (options dict) ---
if isinstance(options, dict) and ("fast" in options or "slow" in options):
    fast_opts = options.get("fast", [])
    slow_opts = options.get("slow", [])

    fast_labels = [opt_label(o) for o in fast_opts if opt_label(o)]
    slow_labels = [opt_label(o) for o in slow_opts if opt_label(o)]

    prev_fast = prev.get("fast", []) if isinstance(prev, dict) else []
    prev_slow = prev.get("slow", []) if isinstance(prev, dict) else []

    st.write("**Быстро / легко:**")
    fast_pick = st.multiselect(
        "",
        fast_labels,
        default=[lbl for lbl in fast_labels if opt_value(fast_opts[fast_labels.index(lbl)]) in prev_fast],
        key=f"{qid}_fast",
    )

    st.write("**Медленно / через силу:**")
    slow_pick = st.multiselect(
        "",
        slow_labels,
        default=[lbl for lbl in slow_labels if opt_value(slow_opts[slow_labels.index(lbl)]) in prev_slow],
        key=f"{qid}_slow",
    )

    fast_selected = [opt_value(fast_opts[fast_labels.index(lbl)]) for lbl in fast_pick] if fast_pick else []
    slow_selected = [opt_value(slow_opts[slow_labels.index(lbl)]) for lbl in slow_pick] if slow_pick else []

    st.session_state.answers[qid] = {"fast": fast_selected, "slow": slow_selected}
    rendered = True

# --- list options ---
if (not rendered) and isinstance(options, list) and options:
    labels = [opt_label(o) for o in options]
    labels = [l for l in labels if l]

    if qtype == "multi":
        prev_sel = prev.get("selected", []) if isinstance(prev, dict) else []
        default_lbls = []
        for i, lbl in enumerate(labels):
            try:
                if opt_value(options[i]) in prev_sel:
                    default_lbls.append(lbl)
            except Exception:
                pass

        chosen = st.multiselect("Выберите варианты:", labels, default=default_lbls, key=f"{qid}_multi")
        selected = []
        for lbl in chosen:
            i = labels.index(lbl)
            selected.append(opt_value(options[i]))
        st.session_state.answers[qid] = {"selected": selected}
        rendered = True

    else:
        # single by default
        prev_sel = None
        if isinstance(prev, dict):
            s = prev.get("selected", [])
            if isinstance(s, list) and s:
                prev_sel = s[0]

        # find index
        index = None
        if prev_sel is not None:
            for i, lbl in enumerate(labels):
                try:
                    if opt_value(options[i]) == prev_sel:
                        index = i
                        break
                except Exception:
                    pass

        choice = st.radio("Выберите 1 вариант:", labels, index=index if index is not None else 0, key=f"{qid}_single")
        i = labels.index(choice)
        st.session_state.answers[qid] = {"selected": [opt_value(options[i])]}
        rendered = True

# --- scale ---
if (not rendered) and qtype == "scale":
    prev_v = 5
    if isinstance(prev, dict) and isinstance(prev.get("value"), (int, float)):
        prev_v = int(prev["value"])
    v = st.slider("Оценка", 1, 10, prev_v, key=f"{qid}_scale")
    st.session_state.answers[qid] = {"value": v}
    rendered = True

# --- text ---
if (not rendered) and qtype == "text":
    prev_t = prev.get("text", "") if isinstance(prev, dict) else ""
    t = st.text_area("", value=prev_t, height=140, key=f"{qid}_text")
    st.session_state.answers[qid] = {"text": t}
    rendered = True

if not rendered:
    st.warning("Этот вопрос пока не отрисовывается (неизвестный формат options/type).")
    st.json(q)


# ---------------- navigation + save ----------------
st.write("")
c1, c2 = st.columns([1, 1])

with c1:
    if st.button("← Назад", use_container_width=True, disabled=(idx == 0)):
        st.session_state.step = max(0, idx - 1)
        st.rerun()

with c2:
    is_last = (idx == TOTAL - 1)
    next_label = "Завершить" if is_last else "Далее →"

    if st.button(next_label, use_container_width=True):
        # autosave draft each step
        cid = st.session_state.respondent["client_id"]
        client_dir = os.path.join(CLIENTS_DIR, cid)
        os.makedirs(client_dir, exist_ok=True)

        save_json(os.path.join(client_dir, "profile.json"), st.session_state.respondent)

        payload = {
            "respondent": st.session_state.respondent,
            "respondent_id": cid,
            "answers": st.session_state.answers,
        }
        save_json(os.path.join(client_dir, "responses.json"), payload)

        if not is_last:
            st.session_state.step = min(TOTAL - 1, idx + 1)
            st.rerun()

        # finish
        if score_blocks is None:
            st.error("Не могу импортировать score_blocks из neo_scoring.py")
            st.code(IMPORT_ERR)
            st.stop()

        try:
            report = score_blocks(blocks_data, payload)
            save_json(os.path.join(client_dir, "report.json"), report)
            st.success("Готово! Результат сохранён. Мастер увидит клиента в Master Panel.")
            st.stop()
        except Exception as e:
            st.error("Ошибка при скоринге:")
            st.code(str(e))
            st.stop()