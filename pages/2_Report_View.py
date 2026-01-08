import json
import os
import streamlit as st

from auth import is_master

# 🔒 Закрываем отчёт для клиента
if not is_master():
    st.stop()

REPORT_PATH = "report.json"

st.set_page_config(page_title="Report View — NEO", layout="wide")
st.title("📄 Report View — NEO Potentials")


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


if not os.path.exists(REPORT_PATH):
    st.info("report.json пока нет. Сначала пройди диагностику и нажми Run scoring на клиентской странице.")
    st.stop()

try:
    report = load_json(REPORT_PATH)
except Exception as e:
    st.error("report.json есть, но не читается (битый JSON).")
    st.code(str(e))
    st.stop()


# ---- Красивый верх отчёта ----
respondent_id = report.get("respondent_id", "—")
st.caption(f"Respondent ID: **{respondent_id}**")

matrix = report.get("matrix_3x3", {})
rows = report.get("rows", {})

c1, c2, c3 = st.columns(3)
with c1:
    st.subheader("ROW 1 — СИЛЫ")
    st.write(rows.get("row1_strengths", []))
with c2:
    st.subheader("ROW 2 — ЭНЕРГИЯ")
    st.write(rows.get("row2_energy", []))
with c3:
    st.subheader("ROW 3 — СЛАБОСТИ")
    st.write(rows.get("row3_weaknesses", []))

st.divider()

st.subheader("Матрица 3×3 (по столбцам)")
col_map = {
    "perception": "Восприятие",
    "motivation": "Мотивация",
    "instrument": "Инструмент",
}

def show_row(title: str, row_key: str):
    row = matrix.get(row_key, {}) or {}
    a, b, c = st.columns(3)
    with a:
        st.metric(col_map["perception"], row.get("perception", "—"))
    with b:
        st.metric(col_map["motivation"], row.get("motivation", "—"))
    with c:
        st.metric(col_map["instrument"], row.get("instrument", "—"))
    st.caption(title)

show_row("Ряд 1 — что даёт энергию и рост", "row1_strengths")
st.divider()
show_row("Ряд 2 — нейтрально/ресурсно", "row2_energy")
st.divider()
show_row("Ряд 3 — зоны истощения", "row3_weaknesses")

st.divider()
with st.expander("Показать полный JSON отчёта (для отладки)"):
    st.json(report)

with open(REPORT_PATH, "rb") as f:
    st.download_button(
        "⬇️ Скачать report.json",
        data=f,
        file_name="report.json",
        mime="application/json",
    )
