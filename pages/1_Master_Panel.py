import os
import json
import sys
from pathlib import Path
import streamlit as st

# ✅ гарантируем, что корень репозитория в sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ✅ импорт пароля мастера
from auth import require_master_password

require_master_password()

st.set_page_config(page_title="Master Panel — NEO", layout="wide")
st.title("🛠️ Master Panel — NEO Potentials")

DATA_DIR = "data"
CLIENTS_DIR = os.path.join(DATA_DIR, "clients")  # data/clients/<client_id>/
BLOCKS_PATH = "neo_blocks.json"


# ----------------- helpers -----------------
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


def potentials_map(blocks_data: dict) -> dict:
    """
    Возвращает мапу potential_id -> RU name.
    Ожидаем формат:
    "potentials": { "amber": {"ru":"Янтарь", ...}, ... }
    """
    pot = {}
    p = blocks_data.get("potentials", {})
    if isinstance(p, dict):
        for pid, meta in p.items():
            if isinstance(meta, dict):
                ru = meta.get("ru") or meta.get("name") or meta.get("title")
                if ru:
                    pot[str(pid)] = str(ru)
    return pot


def format_positions(report: dict, pot_ru: dict) -> str:
    """
    Делает текст 1–9 позиций из report["scores"].
    Ожидаем: report["scores"][<potential_ru_or_id>] = {"strength":..., "weakness":...}
    """
    if not report:
        return "Отчёта пока нет."

    scores = report.get("scores", {})
    if not isinstance(scores, dict) or not scores:
        return "В report.json нет scores."

    # преобразуем в список
    items = []
    for k, v in scores.items():
        if isinstance(v, dict):
            strength = v.get("strength", 0) or 0
            items.append((k, float(strength)))
        else:
            # если вдруг просто число
            try:
                items.append((k, float(v)))
            except Exception:
                pass

    items.sort(key=lambda x: x[1], reverse=True)

    # берём топ-9
    top9 = items[:9]

    def row_col(i: int):
        # i: 1..9
        row = 1 if i <= 3 else (2 if i <= 6 else 3)
        col = i if i <= 3 else (i - 3 if i <= 6 else i - 6)
        return row, col

    lines = []
    lines.append("**Позиции (1–9):**")
    for idx, (pid_or_name, val) in enumerate(top9, start=1):
        row, col = row_col(idx)
        # если ключ уже RU — оставляем, если это id — ищем RU
        ru = pot_ru.get(pid_or_name, pid_or_name)
        lines.append(f"{idx}) **{ru}** — ряд {row}, столбец {col} (score: {val:.3f})")

    return "\n".join(lines)


# ----------------- UI -----------------
ensure_dirs()

blocks_data = safe_read_json(BLOCKS_PATH) or {}
pot_ru = potentials_map(blocks_data)

st.subheader("1) Клиенты")

# клиентские папки
client_ids = []
if os.path.exists(CLIENTS_DIR):
    for name in sorted(os.listdir(CLIENTS_DIR)):
        p = os.path.join(CLIENTS_DIR, name)
        if os.path.isdir(p):
            client_ids.append(name)

if not client_ids:
    st.info("Пока нет клиентов. Клиенты появятся после прохождения диагностики на главной странице.")
    st.stop()

# читаем профили
clients = []
for cid in client_ids:
    profile = safe_read_json(os.path.join(CLIENTS_DIR, cid, "profile.json")) or {}
    label = profile.get("name") or cid
    clients.append((label, cid))

clients.sort(key=lambda x: x[0].lower())

selected_label = st.selectbox("Выбери клиента:", [c[0] for c in clients])
selected_cid = dict(clients)[selected_label]

colA, colB = st.columns([1, 1])

with colA:
    st.subheader("Профиль")
    profile_path = os.path.join(CLIENTS_DIR, selected_cid, "profile.json")
    prof = safe_read_json(profile_path) or {}
    st.write(f"**Имя:** {prof.get('name','—')}")
    st.write(f"**Телефон:** {prof.get('phone','—')}")
    st.write(f"**client_id:** {selected_cid}")

with colB:
    st.subheader("Результат (текстом)")
    report_path = os.path.join(CLIENTS_DIR, selected_cid, "report.json")
    report = safe_read_json(report_path)

    if not report:
        st.warning("report.json пока нет. Сделай скоринг на клиентской странице (Finish).")
    else:
        st.markdown(format_positions(report, pot_ru))
        st.download_button(
            "⬇️ Скачать результат (txt)",
            data=format_positions(report, pot_ru).encode("utf-8"),
            file_name=f"{selected_cid}_result.txt",
            mime="text/plain"
        )

st.divider()

# --- опционально: оставить JSON-редактор, но спрятать ---
with st.expander("⚙️ (Опционально) Редактор neo_blocks.json", expanded=False):
    if not os.path.exists(BLOCKS_PATH):
        st.error(f"Не найден {BLOCKS_PATH}")
    else:
        raw = load_json(BLOCKS_PATH)
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