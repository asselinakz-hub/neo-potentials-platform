import sys
from pathlib import Path

# добавляем корень проекта в sys.path (чтобы импорты работали из pages/)
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from neo_auth import require_master_password

require_master_password()

import json
import os
import streamlit as st

DATA_DIR = "data"
BLOCKS_PATH = "neo_blocks.json"

st.set_page_config(page_title="Master Panel — NEO", layout="wide")
st.title("🛠️ Master Panel — NEO Potentials")


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_clients():
    if not os.path.exists(DATA_DIR):
        return []
    out = []
    for name in sorted(os.listdir(DATA_DIR)):
        p = os.path.join(DATA_DIR, name)
        if os.path.isdir(p):
            out.append(name)
    return out


def format_matrix_positions(report: dict) -> str:
    m = report.get("matrix_3x3", {})
    rows = [
        ("РЯД 1 (СИЛЫ)", m.get("row1_strengths", {})),
        ("РЯД 2 (ЭНЕРГИЯ)", m.get("row2_energy", {})),
        ("РЯД 3 (СЛАБОСТИ)", m.get("row3_weaknesses", {})),
    ]
    cols = ["perception", "motivation", "instrument"]

    lines = []
    for title, row in rows:
        lines.append(title)
        for c in cols:
            val = row.get(c) or "-"
            lines.append(f"  • {c}: {val}")
        lines.append("")
    return "\n".join(lines).strip()


clients = list_clients()

if not clients:
    st.info("Пока нет клиентов. Клиент должен пройти диагностику на главной странице.")
    st.stop()

selected = st.selectbox("Выбери клиента", clients)

client_dir = os.path.join(DATA_DIR, selected)
responses_path = os.path.join(client_dir, "responses.json")
report_path = os.path.join(client_dir, "report.json")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Клиент")
    if os.path.exists(responses_path):
        r = load_json(responses_path)
        resp = r.get("respondent", {})
        st.write(f"**Имя:** {resp.get('name','-')}")
        st.write(f"**Телефон:** {resp.get('phone','-')}")
        st.write(f"**Client ID:** `{r.get('respondent_id','-')}`")
    else:
        st.warning("responses.json не найден у клиента.")

with col2:
    st.subheader("Результат (текстом)")
    if os.path.exists(report_path):
        report = load_json(report_path)

        # 1) коротко: топы по рядам
        rows = report.get("rows", {})
        st.write("**Ряд 1 (силы):** " + ", ".join(rows.get("row1_strengths", [])))
        st.write("**Ряд 2 (энергия):** " + ", ".join(rows.get("row2_energy", [])))
        st.write("**Ряд 3 (слабости):** " + ", ".join(rows.get("row3_weaknesses", [])))

        st.divider()

        # 2) позиционирование 3×3 текстом
        st.code(format_matrix_positions(report))

        # 3) скачать json если нужно
        with open(report_path, "rb") as f:
            st.download_button("⬇️ Скачать report.json", data=f, file_name=f"{selected}_report.json")
    else:
        st.info("report.json пока нет. Значит клиент не завершил тест до конца.")