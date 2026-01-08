import json
import os
import subprocess
import streamlit as st

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

    # Upload (чтобы быстро заменить файл)
    uploaded = st.file_uploader("⬆️ Upload neo_blocks.json", type=["json"])
    if uploaded is not None:
        try:
            uploaded_data = json.load(uploaded)
            save_json(BLOCKS_PATH, uploaded_data)
            st.success("Загрузила и сохранила neo_blocks.json ✅")
            st.rerun()
        except Exception as e:
            st.error("Не смогла загрузить: файл невалидный JSON")
            st.code(str(e))

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

    c1, c2, c3, c4 = st.columns(4)

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
        # ВАЖНО: скачиваем текущий текст из text_area, а не blocks_text_default
        st.download_button(
            "⬇️ Download CURRENT",
            data=blocks_text.encode("utf-8"),
            file_name="neo_blocks.json",
            mime="application/json"
        )

    with c4:
        if st.button("🔄 Reload from file"):
            st.rerun()

with right:
    st.subheader("2) Быстрый просмотр файлов")
    st.code("\n".join(sorted(os.listdir("."))))

    st.divider()
    st.subheader("3) Run scoring (прямо тут)")

    if st.button("▶️ Run scoring now"):
        if not os.path.exists(RESPONSES_PATH):
            st.error("responses.json не найден. Сначала пройди тест и нажми Save responses.json на основной странице.")
        else:
            cmd = ["python", "neo_scoring.py", "--blocks", BLOCKS_PATH, "--answers", RESPONSES_PATH, "--out", REPORT_PATH]
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                st.error("Ошибка при запуске скоринга:")
                st.code(result.stderr or result.stdout)
            else:
                st.success("Скоринг выполнен ✅ report.json обновлён")
                st.rerun()

    st.divider()
    st.subheader("4) report.json")

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
        st.info("report.json пока нет — сначала пройди тест и нажми Run scoring (или кнопку выше).")

    st.divider()
    st.subheader("5) responses.json")

    if os.path.exists(RESPONSES_PATH):
        try:
            st.json(load_json(RESPONSES_PATH))
        except Exception as e:
            st.error("responses.json есть, но не читается.")
            st.code(str(e))
    else:
        st.info("responses.json пока нет — на основной странице нажми Save responses.json.")
