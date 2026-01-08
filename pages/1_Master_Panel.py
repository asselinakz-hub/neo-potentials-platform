import os
import json
from pathlib import Path
import importlib.util
import streamlit as st

# ----------------- AUTH (читаем auth.py из корня репо) -----------------
ROOT = Path(__file__).resolve().parents[1]
AUTH_PATH = ROOT / "auth.py"

if not AUTH_PATH.exists():
    st.error(f"Не найден auth.py в корне: {AUTH_PATH}")
    st.stop()

spec = importlib.util.spec_from_file_location("neo_auth_local", str(AUTH_PATH))
auth_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auth_mod)

if not hasattr(auth_mod, "require_master_password"):
    st.error("В auth.py нет функции require_master_password().")
    st.stop()

auth_mod.require_master_password()

# ----------------- CONFIG -----------------
st.set_page_config(page_title="Master Panel — NEO", layout="wide")
st.title("🛠️ Master Panel — NEO Potentials")

BLOCKS_PATH = "neo_blocks.json"
DATA_DIR = "data"
CLIENTS_DIR = os.path.join(DATA_DIR, "clients")  # data/clients/<client_id>/

# ----------------- HELPERS -----------------
def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def safe_read_json(path: str):
    if not os.path.exists(path):
        return None
    try:
        return load_json(path)
    except Exception:
        return None

def ensure_dirs():
    os.makedirs(CLIENTS_DIR, exist_ok=True)

def pot_ru_map_from_blocks(blocks_data: dict) -> dict:
    """
    Поддерживаем оба формата:
    1) "potentials": {"amber":{"ru":"Янтарь"}, ...}
    2) "potentials": [{"potential_id":"amber","name":"Янтарь"}, ...]
    """
    pot = {}
    p = blocks_data.get("potentials", {})

    if isinstance(p, dict):
        for pid, meta in p.items():
            if isinstance(meta, dict):
                ru = meta.get("ru") or meta.get("name") or meta.get("title")
                if ru:
                    pot[str(pid)] = str(ru)

    if isinstance(p, list):
        for item in p:
            if isinstance(item, dict):
                pid = item.get("potential_id") or item.get("id") or item.get("code")
                ru = item.get("ru") or item.get("name") or item.get("title")
                if pid and ru:
                    pot[str(pid)] = str(ru)

    return pot

def prettify_pid(pid: str, pot_ru: dict) -> str:
    # если в report уже RU — просто вернём
    if isinstance(pid, str) and pid in ["Янтарь","Шунгит","Цитрин","Изумруд","Рубин","Гранат","Сапфир","Гелиодор","Аметист"]:
        return pid
    return pot_ru.get(str(pid), str(pid))

def format_matrix_text(report: dict, pot_ru: dict) -> str:
    """
    Хотим простой текст:
    1 позиция — ряд 1 столбец perception — Янтарь
    ...
    Берём report["matrix_3x3"] если есть.
    """
    if not report:
        return "Отчёта пока нет (report.json не найден)."

    matrix = report.get("matrix_3x3")
    if not isinstance(matrix, dict):
        # fallback: по strength топ-9
        scores = report.get("scores", {})
        if not isinstance(scores, dict) or not scores:
            return "В report.json нет matrix_3x3 и нет scores."
        items = []
        for k, v in scores.items():
            if isinstance(v, dict):
                items.append((k, float(v.get("strength", 0) or 0)))
        items.sort(key=lambda x: x[1], reverse=True)
        top9 = items[:9]

        def row_col(pos):
            row = 1 if pos <= 3 else (2 if pos <= 6 else 3)
            col = pos if pos <= 3 else (pos-3 if pos <= 6 else pos-6)
            return row, col

        lines = ["**Позиции (fallback по strength):**"]
        for pos, (pid, val) in enumerate(top9, start=1):
            row, col = row_col(pos)
            lines.append(f"{pos}) **{prettify_pid(pid, pot_ru)}** — ряд {row}, столбец {col} (score {val:.3f})")
        return "\n".join(lines)

    # нормальный путь: matrix_3x3
    col_names = {
        "perception": "Восприятие",
        "motivation": "Мотивация",
        "instrument": "Инструмент",
    }

    def row_to_positions(row_key: str, row_title: str, row_index: int):
        row_map = matrix.get(row_key, {})
        if not isinstance(row_map, dict):
            return [f"**{row_title}:** нет данных"]
        out = [f"**{row_title}:**"]
        # порядок столбцов фиксируем
        for col_i, col_key in enumerate(["perception","motivation","instrument"], start=1):
            pid = row_map.get(col_key)
            if not pid:
                out.append(f"— ряд {row_index}, столбец {col_names[col_key]}: —")
            else:
                out.append(f"— ряд {row_index}, столбец {col_names[col_key]}: **{prettify_pid(pid, pot_ru)}**")
        return out

    lines = []
    lines += row_to_positions("row1_strengths", "Ряд 1 (Силы)", 1)
    lines.append("")
    lines += row_to_positions("row2_energy", "Ряд 2 (Энергия)", 2)
    lines.append("")
    lines += row_to_positions("row3_weaknesses", "Ряд 3 (Слабости)", 3)

    return "\n".join(lines)

def list_clients() -> list:
    """
    Ищем папки data/clients/<client_id>/
    Клиент считается существующим, если есть responses.json или report.json
    """
    ensure_dirs()
    out = []
    for cid in sorted(os.listdir(CLIENTS_DIR)):
        cdir = os.path.join(CLIENTS_DIR, cid)
        if not os.path.isdir(cdir):
            continue
        has_any = os.path.exists(os.path.join(cdir, "responses.json")) or os.path.exists(os.path.join(cdir, "report.json"))
        if has_any:
            out.append(cid)
    return out

def read_client_profile(client_id: str) -> dict:
    """
    Берём имя/телефон/почту из responses.json -> respondent (или respondent_id)
    """
    cdir = os.path.join(CLIENTS_DIR, client_id)
    resp = safe_read_json(os.path.join(cdir, "responses.json")) or {}
    respondent = resp.get("respondent") or {}
    # возможные ключи
    name = respondent.get("name") or respondent.get("full_name") or ""
    phone = respondent.get("phone") or ""
    email = respondent.get("email") or ""
    return {"name": name, "phone": phone, "email": email}

# ----------------- UI -----------------
blocks_data = safe_read_json(BLOCKS_PATH) or {}
pot_ru = pot_ru_map_from_blocks(blocks_data)

st.subheader("Клиенты")

client_ids = list_clients()
if not client_ids:
    st.info("Пока нет клиентов. Клиенты появятся после прохождения диагностики и нажатия «Завершить».")
    st.stop()

# сформируем красивый список
labels = []
label_to_id = {}
for cid in client_ids:
    prof = read_client_profile(cid)
    label = (prof.get("name") or "").strip()
    if label:
        label = f"{label}  —  {cid}"
    else:
        label = cid
    labels.append(label)
    label_to_id[label] = cid

selected_label = st.selectbox("Выбери клиента:", labels)
selected_cid = label_to_id[selected_label]

colA, colB = st.columns([1, 2])

with colA:
    st.subheader("Профиль")
    prof = read_client_profile(selected_cid)
    st.write(f"**Имя:** {prof.get('name') or '—'}")
    st.write(f"**Телефон:** {prof.get('phone') or '—'}")
    st.write(f"**Email:** {prof.get('email') or '—'}")
    st.write(f"**client_id:** `{selected_cid}`")

with colB:
    st.subheader("Результат")
    report_path = os.path.join(CLIENTS_DIR, selected_cid, "report.json")
    report = safe_read_json(report_path)

    text = format_matrix_text(report, pot_ru)
    st.markdown(text)

    st.download_button(
        "⬇️ Скачать результат (txt)",
        data=text.encode("utf-8"),
        file_name=f"{selected_cid}_result.txt",
        mime="text/plain"
    )

st.divider()

with st.expander("⚙️ Опционально: редактор neo_blocks.json", expanded=False):
    if not os.path.exists(BLOCKS_PATH):
        st.error(f"Не найден {BLOCKS_PATH}")
    else:
        raw = safe_read_json(BLOCKS_PATH) or {}
        text_default = json.dumps(raw, ensure_ascii=False, indent=2)
        text = st.text_area("neo_blocks.json", value=text_default, height=420)

        c1, c2 = st.columns(2)
        with c1:
            if st.button("✅ Validate JSON"):
                try:
                    json.loads(text)
                    st.success("JSON валидный ✅")
                except Exception as e:
                    st.error("JSON невалидный ❌")
                    st.code(str(e))
        with c2:
            if st.button("💾 Save neo_blocks.json"):
                try:
                    parsed = json.loads(text)
                    with open(BLOCKS_PATH, "w", encoding="utf-8") as f:
                        json.dump(parsed, f, ensure_ascii=False, indent=2)
                    st.success("Сохранено ✅")
                except Exception as e:
                    st.error("Не сохранилось")
                    st.code(str(e))