import os
import streamlit as st

def is_master() -> bool:
    # пароль берём из Secrets (Streamlit Cloud) или из переменной окружения
    master_pw = st.secrets.get("MASTER_PASSWORD", None)
    if master_pw is None:
        master_pw = os.getenv("MASTER_PASSWORD", "")

    if not master_pw:
        # если пароль не задан — считаем, что мастерка открыта (на время разработки)
        return True

    if st.session_state.get("is_master", False):
        return True

    with st.sidebar:
        st.markdown("### 🔒 Master login")
        pw = st.text_input("Пароль", type="password")

        if st.button("Войти"):
            if pw == master_pw:
                st.session_state["is_master"] = True
                st.success("Ок, мастер доступ открыт ✅")
                st.rerun()
            else:
                st.error("Неверный пароль")

    return False
