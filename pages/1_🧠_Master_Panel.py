import json
import os
import glob
import subprocess
import streamlit as st

BLOCKS_PATH = "neo_blocks.json"
DEFAULT_RESPONSES_PATH = "responses.json"   # твой текущий формат (1 клиент)
DEFAULT_REPORT_PATH = "report.json"

# если позже захочешь много клиентов:
RESPONSES_DIR = "responses"
REPORTS_DIR = "reports"

st.set_page_config(page_title="NEO Potentials — Master", layout="wide")
st.title("🧠 NEO Potentials — Панель мастера")

# ---------- helpers ----------
def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def exists(p: str) -> bool:
    return os.path.exists(p)

def safe_get(d, keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur

def render_matrix(matrix_3x3: dict):
    # matrix_3x3:
    # {
    #   "row1_strengths": {"perception": "...", "motivation": "...", "instrument": "..."},
    #   "row2_energy": {...},
    #   "row3_weaknesses": {...}
    # }
    cols = ["perception", "motivation", "instrument"]
    header = ["Ряд / Столбец"] + cols
    rows = []

    def row_line(title, key):
        rm = matrix_3x3.get(key, {}) or {}
        rows.append([title, rm.get("perception", "-"), rm.get("motivation", "-"), rm.get("instrument", "-")])

    row_line("ROW1 — СИЛЫ", "row1_strengths")
    row_line("ROW2 — ЭНЕРГИЯ", "row2_energy")
    row_line("ROW3 — СЛАБОСТИ", "row3_weaknesses")

    st.table([header] + rows)

def potential_table(report: dict):
    scores = report.get("scores", {}) or {}
    if not scores:
        st.warning("В отчёте нет scores.")
        return

    data = []
    for p, s in scores.items():
        cols = s.get("columns", {}) or {}
        data.append({
            "Потенциал": p,
            "Strength": s.get("strength", 0),
            "Weakness": s.get("weakness", 0),
            "Perception": cols.get("perception", 0),
            "Motivation": cols.get("motivation", 0),
            "Instrument": cols.get("instrument", 0),
            "Dominant column": s.get("dominant_column", "")
        })

    # сортировка: сначала силы
    data_sorted = sorted(data, key=lambda x: x["Strength"], reverse=True)
    st.dataframe(data_sorted, use_container_width=True)

# ---------- sanity checks ----------
if not exists(BLOCKS_PATH):
    st.error(f"Не найден файл {BLOCKS_PATH}. Панель мастера не может работать без него.")
    st.stop()

# ---------- choose data mode ----------
st.caption("Выбери источник ответов клиента: один файл (responses.json) или папка responses/ (много клиентов).")

mode = st.radio(
    "Режим данных",
    ["Один клиент (responses.json)", "Много клиентов (responses/*.json)"],
    horizontal=True
)

client_id = None
answers_path = None
report_path = None

if mode == "Один клиент (responses.json)":
    if not exists(DEFAULT_RESPONSES_PATH):
        st.warning(f"Файл {DEFAULT_RESPONSES_PATH} не найден. Сначала пройди клиентскую диагностику и нажми Save.")
    else:
        answers_path = DEFAULT_RESPONSES_PATH
        payload = load_json(answers_path)
        client_id = payload.get("respondent_id", "demo_user")
        report_path = DEFAULT_REPORT_PATH

else:
    # multi-client mode
    os.makedirs(RESPONSES_DIR, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)

    files = sorted(glob.glob(os.path.join(RESPONSES_DIR, "*.json")))
    if not files:
        st.warning(f"В папке {RESPONSES_DIR}/ нет файлов. Добавь ответы клиентов туда (например client_001.json).")
    else:
        chosen = st.selectbox("Выбери клиента (файл ответов):", files)
        answers_path = chosen
        payload = load_json(answers_path)
        client_id = payload.get("respondent_id", os.path.splitext(os.path.basename(answers_path))[0])
        report_path = os.path.join(REPORTS_DIR, f"{client_id}_report.json")

st.
divider()

# ---------- actions ----------
colA, colB, colC = st.columns([1, 1, 1])

with colA:
    st.subheader("⚙️ Скоринг")
    if st.button("Run scoring для выбранного клиента", disabled=(answers_path is None)):
        cmd = ["python", "neo_scoring.py", "--blocks", BLOCKS_PATH, "--answers", answers_path]
        if report_path:
            cmd += ["--out", report_path]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            st.error("Ошибка при запуске скоринга:")
            st.code(result.stderr or result.stdout)
        else:
            st.success("Скоринг выполнен.")
            # полезно показать последние строки вывода
            out_txt = (result.stdout or "").strip()
            if out_txt:
                st.caption("Лог скоринга (последние строки):")
                st.code("\n".join(out_txt.splitlines()[-25:]))

with colB:
    st.subheader("📄 Отчёт")
    if st.button("Открыть report.json", disabled=(report_path is None or not exists(report_path))):
        rep = load_json(report_path)
        st.session_state["last_report"] = rep
        st.success("Отчёт загружен.")

with colC:
    st.subheader("🗂️ Файлы проекта")
    st.code("\n".join(sorted(os.listdir("."))))

st.divider()

# ---------- show report ----------
rep = st.session_state.get("last_report")
if rep is None and report_path and exists(report_path):
    # автозагрузка если есть
    rep = load_json(report_path)
    st.session_state["last_report"] = rep

if rep:
    st.header(f"Результаты клиента: {rep.get('respondent_id', client_id or '')}")

    # TOPS
    rows = rep.get("rows", {}) or {}
    r1 = rows.get("row1_strengths", [])
    r3 = rows.get("row3_weaknesses", [])

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🔥 ТОП СИЛЫ (ROW1)")
        st.write(", ".join(r1) if r1 else "—")
    with c2:
        st.subheader("😮‍💨 ТОП СЛАБОСТИ (ROW3)")
        st.write(", ".join(r3) if r3 else "—")

    st.subheader("🧩 Матрица 3×3 (ряд × столбец)")
    render_matrix(rep.get("matrix_3x3", {}) or {})

    st.subheader("📊 Таблица потенциалов (подробно)")
    potential_table(rep)

    st.subheader("⬇️ Скачать отчёт")
    st.download_button(
        "Download report.json",
        data=json.dumps(rep, ensure_ascii=False, indent=2).encode("utf-8"),
        file_name=os.path.basename(report_path or "report.json"),
        mime="application/json",
    )
else:
    st.info("Пока нет отчёта. Нажми Run scoring, затем открой report.json.")
