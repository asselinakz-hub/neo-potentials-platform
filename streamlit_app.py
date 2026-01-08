import json
import os
import re
import subprocess
import streamlit as st

BLOCKS_PATH = "neo_blocks.json"
RESPONSES_PATH = "responses.json"   # сохраняем ответы сюда (как ты просила)
REPORT_PATH = "report.json"

# ----------------------------
# helpers
# ----------------------------
def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^a-z0-9_]+", "", s)
    return s

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

def normalize_pid(x):
    if x is None:
        return None
    x = str(x).strip()
    return RU2ID.get(x, x)

def qtype_norm(t: str) -> str:
    t = (t or "").strip().lower()
    # нормализуем варианты
    if t in ("single_select", "radio"):
        return "single_choice"
    if t in ("multi_select", "multiple_choice"):
        return "multi_choice"
    if t in ("checkbox",):
        return "checkbox"
    return t

def is_multi(t: str) -> bool:
    t = qtype_norm(t)
    return t in ("multi_choice", "checkbox")

def is_single(t: str) -> bool:
    t = qtype_norm(t)
    return t in ("single_choice",)

def get_potentials_dict(blocks_data):
    """
    поддерживаем 2 формата:
    1) "potentials": { "amber": {"ru":"Янтарь","emoji":"..."} , ... }
    2) "potentials": [ {"potential_id":"amber","name":"Янтарь"}, ... ]
    """
    p = blocks_data.get("potentials")
    out = {}
    if isinstance(p, dict):
        for k, v in p.items():
            if isinstance(v, dict):
                ru = v.get("ru") or v.get("name") or v.get("title") or k
            else:
                ru = str(v)
            out[str(k)] = str(ru)
    elif isinstance(p, list):
        for item in p:
            if isinstance(item, dict):
                pid = item.get("potential_id") or item.get("id") or item.get("code")
                name = item.get("ru") or item.get("name") or item.get("title")
                if pid and name:
                    out[str(pid)] = str(name)
    # fallback
    if not out:
        out = {
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
    return out

def extract_option(opt):
    """
    Возвращает:
    (label, option_id, potential_id)
    """
    if isinstance(opt, str):
        # если опции просто строками
        return opt, opt, None

    if not isinstance(opt, dict):
        return None, None, None

    option_id = opt.get("id") or opt.get("option_id") or opt.get("code")
    label = opt.get("label") or opt.get("text") or opt.get("title") or option_id

    pid = (
        opt.get("potential_id")
        or opt.get("potential")
        or opt.get("pid")
        or opt.get("gem")
        or opt.get("value")
    )
    pid = normalize_pid(pid)

    # иногда option_id выглядит как opt_amber — вытащим потенциально pid
    if (pid is None) and isinstance(option_id, str) and option_id.startswith("opt_"):
        maybe = option_id.replace("opt_", "")
        pid = normalize_pid(maybe)

    return str(label) if label is not None else None, str(option_id) if option_id is not None else None, pid

def run_scoring():
    cmd = ["python", "neo_scoring.py", "--blocks", BLOCKS_PATH, "--answers", RESPONSES_PATH, "--out", REPORT_PATH]
    return subprocess.run(cmd, capture_output=True, text=True)

# ----------------------------
# page config
# ----------------------------
st.set_page_config(page_title="NEO Potentials — Диагностика", layout="wide")
st.title("NEO Potentials — Диагностика")

if not os.path.exists(BLOCKS_PATH):
    st.error(f"Не найден файл {BLOCKS_PATH}.")
    st.stop()

blocks_data = load_json(BLOCKS_PATH)
potentials = get_potentials_dict(blocks_data)
blocks = blocks_data.get("blocks", [])

if "answers" not in st.session_state:
    st.session_state.answers = {}
if "step" not in st.session_state:
    st.session_state.step = 0
if "respondent" not in st.session_state:
    st.session_state.respondent = {"name": "", "phone": "", "client_id": ""}

# ----------------------------
# respondent info
# ----------------------------
with st.expander("Ваши данные (имя и телефон)"):
    name = st.text_input("Имя", value=st.session_state.respondent.get("name", ""))
    phone = st.text_input("Телефон", value=st.session_state.respondent.get("phone", ""))
    if st.button("Сохранить данные"):
        st.session_state.respondent["name"] = name.strip()
        st.session_state.respondent["phone"] = phone.strip()
        cid = slugify(f"{name}_{phone}") or "client"
        st.session_state.respondent["client_id"] = cid
        st.success("Сохранено ✅")

# ----------------------------
# flatten questions
# ----------------------------
flat = []
for b in blocks:
    bcode = b.get("block_code") or b.get("block_id") or "B?"
    bname = b.get("block_name") or b.get("name") or ""
    for q in b.get("questions", []):
        qid = q.get("id")
        if not qid:
            continue
        flat.append((bcode, bname, q))

total = len(flat)
if total == 0:
    st.error("В neo_blocks.json не найдено вопросов (blocks[].questions[]).")
    st.stop()

# clamp step
st.session_state.step = max(0, min(st.session_state.step, total - 1))
idx = st.session_state.step

# progress
st.progress((idx + 1) / total)
st.caption(f"Вопрос {idx + 1} из {total}")

bcode, bname, q = flat[idx]
qid = q.get("id")
qtype = qtype_norm(q.get("type"))
prompt = q.get("prompt") or q.get("text") or q.get("title") or qid

st.subheader(f"{bcode}. {bname}")
st.write(prompt)

# ----------------------------
# render one question
# ----------------------------
options = q.get("options", []) or []
labels = []
pids = []   # будем сохранять potential_id (если есть), иначе option_id

for opt in options:
    label, option_id, pid = extract_option(opt)
    if not label:
        continue

    final_id = pid or option_id or label
    final_id = normalize_pid(final_id)

    # красивый label
    ru = potentials.get(final_id, "")
    if ru and ru != final_id:
        labels.append(str(label))

    pids.append(final_id)

key = f"q_{qid}"

# предыдущие значения
prev = st.session_state.answers.get(qid, {})
prev_sel = prev.get("selected", [])
if isinstance(prev_sel, str):
    prev_sel = [prev_sel]
if prev_sel is None:
    prev_sel = []

if is_single(qtype):
    # индекс по prev
    default_index = None
    if prev_sel:
        try:
            default_index = pids.index(prev_sel[0])
        except Exception:
            default_index = None

    choice = st.radio("Выберите 1 вариант:", labels, index=default_index, key=key)
    if choice is not None:
        i = labels.index(choice)
        st.session_state.answers[qid] = {"selected": [pids[i]]}

elif is_multi(qtype):
    defaults = []
    for s in prev_sel:
        if s in pids:
            defaults.append(s)

    # multiselect сразу позволяет выбрать несколько — без “кликни ещё раз”
    chosen_labels = []
    if defaults:
        # превратим defaults -> labels
        for d in defaults:
            try:
                chosen_labels.append(labels[pids.index(d)])
            except Exception:
                pass

    chosen = st.multiselect("Выберите варианты:", labels, default=chosen_labels, key=key)
    selected = []
    for lab in chosen:
        i = labels.index(lab)
        selected.append(pids[i])

    st.session_state.answers[qid] = {"selected": selected}

elif qtype == "scale":
    # универсально: min/max/step
    mn = int(q.get("min", 1))
    mx = int(q.get("max", 10))
    step = int(q.get("step", 1))
    prev_val = prev.get("value")
    if prev_val is None:
        prev_val = mn
    val = st.slider("Оценка:", mn, mx, int(prev_val), step=step, key=key)
    st.session_state.answers[qid] = {"value": val}

elif qtype == "text":
    prev_text = prev.get("text", "")
    txt = st.text_area("Введите ответ:", value=prev_text, key=key)
    st.session_state.answers[qid] = {"text": txt}

else:
    st.warning(f"Тип вопроса '{qtype}' пока не поддержан — пропускаю.")
    st.session_state.answers.setdefault(qid, {})

# optional note
if q.get("text_field", False):
    prev_note = st.session_state.answers.get(qid, {}).get("note", "")
    note = st.text_input("Комментарий (необязательно):", value=prev_note, key=f"note_{qid}")
    st.session_state.answers.setdefault(qid, {})
    st.session_state.answers[qid]["note"] = note

# ----------------------------
# navigation buttons
# ----------------------------
c1, c2, c3, c4 = st.columns([1, 1, 1, 2])

with c1:
    if st.button("⬅ Назад", disabled=(idx == 0)):
        st.session_state.step = max(0, idx - 1)
        st.rerun()

with c2:
    if st.button("Далее ➡", disabled=(idx >= total - 1)):
        st.session_state.step = min(total - 1, idx + 1)
        st.rerun()
        
payload = {
    "respondent": st.session_state.get("respondent", {}),
    "respondent_id": st.session_state.get("respondent_id", "client"),
    "answers": st.session_state.get("answers", {}),
}
save_json("responses.json", payload)