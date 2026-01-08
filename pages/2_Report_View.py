import json
import os
import streamlit as st
from auth import is_master

if not is_master():
    st.stop()

DATA_DIR = "data"
CLIENTS_PATH = os.path.join(DATA_DIR, "clients.json")
REPORT_DIR = os.path.join(DATA_DIR, "reports")

st.set_page_config(page_title="Report — NEO", layout="wide")
st.title("📄 Отчёт — NEO Potentials")

# -----------------------
# Helpers
# -----------------------
def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def safe(v, default="—"):
    return v if v not in (None, "", []) else default

def load_clients():
    if not os.path.exists(CLIENTS_PATH):
        return []
    try:
        data = load_json(CLIENTS_PATH)
        return data if isinstance(data, list) else []
    except Exception:
        return []

def report_path_for(client_id: str) -> str:
    return os.path.join(REPORT_DIR, f"{client_id}.json")

def nice_potential(p: str) -> str:
    # на случай если где-то попадутся англ-ключи
    mapping = {
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
    return mapping.get(p, p)

def cell(title: str, value: str, subtitle: str = ""):
    with st.container(border=True):
        st.caption(title)
        st.markdown(f"### {safe(value)}")
        if subtitle:
            st.caption(subtitle)

def matrix_row(row_title: str, row_map: dict):
    cols = st.columns(3)
    labels = [("Восприятие", "perception"), ("Мотивация", "motivation"), ("Инструмент", "instrument")]
    for i, (lab, key) in enumerate(labels):
        p = row_map.get(key)
        with cols[i]:
            cell(f"{row_title} · {lab}", nice_potential(p) if p else "—")

def list_scores(report: dict, which: str, top_n: int = 5):
    # which: "strength" or "weakness"
    scores = report.get("scores", {})
    items = []
    for p, s in scores.items():
        items.append((p, float(s.get(which, 0.0)), s.get("dominant_column")))
    items.sort(key=lambda x: x[1], reverse=True)
    return items[:top_n]

# -----------------------
# UI
# -----------------------
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)

clients = load_clients()

if not clients:
    st.info("Пока нет клиентов. Сначала пройди диагностику на главной странице (NEO Potentials — Диагностика).")
    st.stop()

# select client
options = {f"{c.get('name','')} — {c.get('phone','')} ({c.get('client_id')})": c for c in clients}
chosen_label = st.selectbox("Выбери клиента:", list(options.keys()))
client = options[chosen_label]
cid = client.get("client_id")

path = report_path_for(cid)

if not os.path.exists(path):
    st.warning("Для этого клиента ещё нет отчёта. Пройди тест до конца и нажми Finish & Run scoring.")
    st.stop()

# load report
try:
    report = load_json(path)
except Exception as e:
    st.error("report.json есть, но не читается.")
    st.code(str(e))
    st.stop()

respondent = report.get("respondent") or {}
name = respondent.get("name") or client.get("name")
phone = respondent.get("phone") or client.get("phone")

# header
st.subheader("Данные клиента")
c1, c2, c3 = st.columns([2, 2, 1])
with c1:
    cell("Имя", safe(name))
with c2:
    cell("Телефон", safe(phone))
with c3:
    cell("ID", safe(cid))

st.divider()

# Matrix 3x3
st.subheader("Матрица 3×3")
matrix = report.get("matrix_3x3") or {}
r1 = matrix.get("row1_strengths") or {}
r2 = matrix.get("row2_energy") or {}
r3 = matrix.get("row3_weaknesses") or {}

matrix_row("ROW 1 · СИЛЫ", r1)
matrix_row("ROW 2 · ЭНЕРГИЯ", r2)
matrix_row("ROW 3 · СЛАБОСТИ", r3)

st.divider()

# Top lists
st.subheader("Ключевые акценты")
left, right = st.columns(2)

with left:
    st.markdown("#### Топ потенциалы по СИЛЕ")
    top_strengths = list_scores(report, "strength", top_n=5)
    for p, val, col in top_strengths:
        st.write(f"**{nice_potential(p)}** — {val:.2f}  · столбец: _{safe(col)}_")

with right:
    st.markdown("#### Топ зоны по СЛАБОСТИ")
top_weak = list_scores(report, "weakness", top_n=5)
    for p, val, col in top_weak:
        st.write(f"**{nice_potential(p)}** — {val:.2f}  · столбец: _{safe(col)}_")

st.divider()

# Download
with open(path, "rb") as f:
    st.download_button(
        "⬇️ Скачать отчёт (report.json)",
        data=f,
        file_name=f"{cid}_report.json",
        mime="application/json"
    )

# Optional: debug expander (чтобы не мешал клиенту)
with st.expander("Технические детали (скрыто)"):
    st.json(report)
