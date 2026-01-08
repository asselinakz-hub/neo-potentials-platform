import json
import os
import streamlit as st

# ====== MASTER PASSWORD (inline, no imports) ======
def require_master_password():
    master_pw = ""
    # Streamlit secrets (Cloud)
    try:
        master_pw = st.secrets.get("MASTER_PASSWORD", "")
    except Exception:
        master_pw = ""

    # Fallback to env var
    master_pw = master_pw or os.getenv("MASTER_PASSWORD", "")

    if "master_ok" not in st.session_state:
        st.session_state.master_ok = False

    if st.session_state.master_ok:
        return

    st.set_page_config(page_title="Master Panel — NEO", layout="wide")
    st.title("🔒 Master Panel — доступ по паролю")

    pw = st.text_input("Введите пароль мастера", type="password")
    if st.button("Войти"):
        if master_pw and pw == master_pw:
            st.session_state.master_ok = True
            st.rerun()
        else:
            st.error("Неверный пароль")

    st.stop()

require_master_password()
# ================================================

BLOCKS_PATH = "neo_blocks.json"
REPORT_PATH = "report.json"
RESPONSES_PATH = "responses.json"

st.set_page_config(page_title="Master Panel — NEO", layout="wide")
st.title("🛠️ Master Panel — NEO Potentials")

def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path: str, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

left, right = st.columns([2, 1])

with left:
    st.subheader("1) Редактор neo_blocks.json")

    if not os.path.exists(BLOCKS_PATH):
        st.error(f"Не найден файл {BLOCKS_PATH} в корне репозитория.")
        st.stop()

    try:
        blocks_data = load_json(BLOCKS_PATH)
        blocks_text_default = json.dumps(blocks_data, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error("Не могу прочитать neo_blocks.json (битый JSON).")
        st.code(str(e))
        st.stop()

    blocks_text = st.text_area(
        "neo_blocks.json (редактируй аккуратно — это JSON)",
        value=blocks_text_default,
        height=520
    )

    c1, c2, c3 = st.columns(3)

    with c1:
        if st.button("✅ Validate JSON"):
            try:
                json.loads(blocks_text)
                st.success("JSON валидный ✅")
            except Exception as e:
                st.error("JSON НЕ валидный ❌")
                st.code(str(e))

    with c2:
        if st.button("💾 Save neo_blocks.json"):
            try:
                parsed = json.loads(blocks_text)
                save_json(BLOCKS_PATH, parsed)
                st.success("Сохранила neo_blocks.json ✅")
            except Exception as e:
                st.error("Не смогла сохранить: JSON невалидный или ошибка записи")
                st.code(str(e))

    with c3:
        st.download_button(
            "⬇️ Download neo_blocks.json",
            data=blocks_text_default.encode("utf-8"),
            file_name="neo_blocks.json",
            mime="application/json"
        )

with right:
    st.subheader("2) Быстрый просмотр файлов")
    st.code("\n".join(sorted(os.listdir("."))))

    st.divider()
    st.subheader("3) report.json")

    if os.path.exists(REPORT_PATH):
        try:
            st.json(load_json(REPORT_PATH))
            with open(REPORT_PATH, "rb") as f:
                st.download_button(
                    "⬇️ Download report.json",
                    data=f,
                    file_name="report.json",
                    mime="application/json"
                )
        except Exception as e:
            st.error("report.json есть, но не читается.")
            st.code(str(e))
    else:
        st.info("report.json пока нет — сначала пройди тест и сделай скоринг на основной странице.")

    st.divider()
    st.subheader("4) responses.json")

    if os.path.exists(RESPONSES_PATH):
        try:
            st.json(load_json(RESPONSES_PATH))
        except Exception as e:
            st.error("responses.json есть, но не читается.")
            st.code(str(e))
    else:
        st.info("responses.json пока нет — на основной странице сохрани ответы.")