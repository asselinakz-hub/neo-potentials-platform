import json
import os
import streamlit as st

DATA_DIR = "data"
CLIENTS_PATH = os.path.join(DATA_DIR, "clients.json")
RESP_DIR = os.path.join(DATA_DIR, "responses")
REPORT_DIR = os.path.join(DATA_DIR, "reports")
BLOCKS_PATH = "neo_blocks.json"

st.set_page_config(page_title="Master Panel — NEO", layout="wide")
st.title("🛠️ Master Panel — NEO Potentials")

def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(RESP_DIR, exist_ok=True)
os.makedirs(REPORT_DIR, exist_ok=True)

# ---- Clients ----
clients = []
if os.path.exists(CLIENTS_PATH):
    try:
        clients = load_json(CLIENTS_PATH)
    except Exception:
        clients = []

st.subheader("1) Клиенты")
if not clients:
    st.info("Пока нет клиентов. Сначала пройди диагностику на главной странице.")
else:
    # simple selector
    options = {f"{c.get('name','')} — {c.get('phone','')} ({c.get('client_id')})": c for c in clients}
    chosen_label = st.selectbox("Выбери клиента:", list(options.keys()))
    c = options[chosen_label]
    cid = c["client_id"]

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### responses")
        resp_path = os.path.join(RESP_DIR, f"{cid}.json")
        if os.path.exists(resp_path):
            st.json(load_json(resp_path))
        else:
            st.info("responses пока нет")

    with col2:
        st.markdown("### report")
        rep_path = os.path.join(REPORT_DIR, f"{cid}.json")
        if os.path.exists(rep_path):
            st.json(load_json(rep_path))
            with open(rep_path, "rb") as f:
                st.download_button("⬇️ Скачать report.json", data=f, file_name=f"{cid}_report.json", mime="application/json")
        else:
            st.info("report пока нет")

st.divider()

# ---- blocks editor ----
st.subheader("2) Редактор neo_blocks.json")
if not os.path.exists(BLOCKS_PATH):
    st.error("neo_blocks.json не найден в корне репозитория.")
else:
    try:
        blocks_data = load_json(BLOCKS_PATH)
        blocks_text_default = json.dumps(blocks_data, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error("neo_blocks.json битый.")
        st.code(str(e))
        st.stop()

    blocks_text = st.text_area("neo_blocks.json", value=blocks_text_default, height=420)

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("✅ Validate JSON"):
            try:
                json.loads(blocks_text)
                st.success("JSON валидный ✅")
            except Exception as e:
                st.error("JSON невалидный ❌")
                st.code(str(e))

    with c2:
        if st.button("💾 Save neo_blocks.json"):
            try:
                parsed = json.loads(blocks_text)
                save_json(BLOCKS_PATH, parsed)
                st.success("Сохранено ✅")
            except Exception as e:
                st.error("Не сохранилось")
                st.code(str(e))

    with c3:
        st.download_button("⬇️ Download neo_blocks.json", data=blocks_text.encode("utf-8"), file_name="neo_blocks.json", mime="application/json")

st.divider()
st.subheader("3) Файлы")
st.code("\n".join(sorted(os.listdir("."))))
