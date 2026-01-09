import os
import json
from pathlib import Path
import importlib.util
import streamlit as st

# =========================
#  Load auth.py safely
# =========================
ROOT = Path(__file__).resolve().parents[1]
AUTH_PATH = ROOT / "auth.py"

if not AUTH_PATH.exists():
    st.error(f"Не найден auth.py в корне репозитория: {AUTH_PATH}")
    st.stop()

spec = importlib.util.spec_from_file_location("neo_auth_local", str(AUTH_PATH))
auth_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auth_mod)

if not hasattr(auth_mod, "require_master_password"):
    st.error("В auth.py нет функции require_master_password().")
    st.stop()

auth_mod.require_master_password()

# =========================
#  Page config
# =========================
st.set_page_config(page_title="Master Panel — NEO", layout="wide")
st.title("🛠️ Master Panel — NEO Potentials")

DATA_DIR = "data"
CLIENTS_DIR = os.path.join(DATA_DIR, "clients")  # data/clients/<client_id>/
BLOCKS_PATH = "neo_blocks.json"


# =========================
#  Helpers
# =========================
def ensure_dirs():
    os.makedirs(CLIENTS_DIR, exist_ok=True)


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


def potentials_map(blocks_data: dict) -> dict:
    """
    Вернёт map: potential_id -> RU name
    Поддерживает 2 формата:
    1) "potentials": { "amber": {"ru":"Янтарь"}, ... }
    2) "potentials": [ {"id":"amber","name":"Янтарь"}, ... ]
    """
    pot = {}

    p = blocks_data.get("potentials")

    # dict-format
    if isinstance(p, dict):
        for pid, meta in p.items():
            if isinstance(meta, dict):
                ru = meta.get("ru") or meta.get("name") or meta.get("title")
                if ru:
                    pot[str(pid)] = str(ru)

    # list-format
    if isinstance(p, list):
        for item in p:
            if isinstance(item, dict):
                pid = item.get("potential_id") or item.get("id") or item.get("code")
                ru = item.get("ru") or item.get("name") or item.get("title")
                if pid and ru:
                    pot[str(pid)] = str(ru)

    # fallback (если в blocks ничего нет)
    if not pot:
        pot = {
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

    return pot


def format_matrix_text(report: dict, pot_ru: dict) -> str:
    """
    Красивый текст матрицы 3×3 по столбцам.
    Ожидаем report["matrix"] формата:
    {
      "perception": {"row1": "citrine", "row2": "...", "row3": "..."},
      "motivation": {...},
      "instrument": {...}
    }
    """
    if not report:
        return "Отчёта пока нет."

    matrix = report.get("matrix")
    if not isinstance(matrix, dict):
        return (
            "В report.json нет поля **matrix**.\n\n"
            "Скорее всего у клиента старый report.json.\n"
            "Решение: пройти тест заново и нажать **Завершить** (Finish), чтобы пересчитать отчёт."
        )

    col_ru = {
        "perception": "Восприятие",
        "motivation": "Мотивация",
        "instrument": "Инструмент",
    }
    row_ru = {
        "row1": "Ряд 1 (Силы)",
        "row2": "Ряд 2 (Энергия)",
        "row3": "Ряд 3 (Слабости)",
    }

    order_cols = ["perception", "motivation", "instrument"]
    order_rows = ["row1", "row2", "row3"]

    lines = []
    lines.append("## Результат (матрица 3×3)\n")

    for col in order_cols:
        lines.append(f"### {col_ru.get(col, col)}")
        col_block = matrix.get(col, {}) if isinstance(matrix.get(col), dict) else {}

        for row in order_rows:
            pid = col_block.get(row)
            if not pid:
                lines.append(f"- **{row_ru[row]}:** —")
            else:
                name = pot_ru.get(str(pid), str(pid))
                lines.append(f"- **{row_ru[row]}:** **{name}**")
        lines.append("")

    return "\n".join(lines)


def list_clients():
    """
    Возвращает список client_id (папки) из data/clients
    """
    if not os.path.exists(CLIENTS_DIR):
        return []
    ids = []
    for name in sorted(os.listdir(CLIENTS_DIR)):
        p = os.path.join(CLIENTS_DIR, name)
        if os.path.isdir(p):
            ids.append(name)
    return ids


# =========================
#  UI
# =========================
ensure_dirs()

blocks_data = safe_read_json(BLOCKS_PATH) or {}
pot_ru = potentials_map(blocks_data)

st.subheader("1) Клиенты")

client_ids = list_clients()
if not client_ids:
    st.info("Пока нет клиентов. Клиенты появятся после прохождения диагностики на главной странице (после «Завершить»).")
    st.stop()

# читаем профили
clients = []
for cid in client_ids:
    profile = safe_read_json(os.path.join(CLIENTS_DIR, cid, "profile.json")) or {}
    label = profile.get("name") or cid
    clients.append((label, cid))

clients.sort(key=lambda x: x[0].lower())

selected_label = st.selectbox("Выбери клиента:", [c[0] for c in clients], index=0)
selected_cid = dict(clients)[selected_label]

colA, colB = st.columns([1, 2])

with colA:
    st.subheader("Профиль")
    profile_path = os.path.join(CLIENTS_DIR, selected_cid, "profile.json")
    prof = safe_read_json(profile_path) or {}
    st.write(f"**Имя:** {prof.get('name', '—')}")
    st.write(f"**Телефон:** {prof.get('phone', '—')}")
    st.write(f"**client_id:** `{selected_cid}`")

    st.divider()
    st.caption("Файлы клиента:")
    st.code("\n".join(sorted(os.listdir(os.path.join(CLIENTS_DIR, selected_cid)))))

with colB:
    st.subheader("Результат")
    report_path = os.path.join(CLIENTS_DIR, selected_cid, "report.json")
    report = safe_read_json(report_path)

    if not report:
        st.warning("report.json пока нет. Клиент должен пройти тест до конца и нажать «Завершить».")
    else:
        text = format_matrix_text(report, pot_ru)
        st.markdown(text)

        st.download_button(
            "⬇️ Скачать результат (txt)",
            data=text.encode("utf-8"),
            file_name=f"{selected_cid}_matrix.txt",
            mime="text/plain",
            use_container_width=True,
        )

st.divider()

# Опционально: редактор blocks — спрятан
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