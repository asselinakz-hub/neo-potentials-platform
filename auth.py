import os
import streamlit as st


def require_master_password():
    """
    Простая защита мастер-страниц паролем.
    Пароль берём из:
      1) st.secrets["MASTER_PASSWORD"] (Streamlit Cloud -> Settings -> Secrets)
      2) переменной окружения MASTER_PASSWORD
      3) запасного варианта (не рекомендую) — можно временно оставить DEFAULT_MASTER_PASSWORD
    """

    # 1) Streamlit secrets
    master = None
    try:
        master = st.secrets.get("MASTER_PASSWORD", None)
    except Exception:
        master = None

    # 2) env var
    if not master:
        master = os.environ.get("MASTER_PASSWORD")

    # 3) fallback (временно, потом удали)
    DEFAULT_MASTER_PASSWORD = "12345"
    if not master:
        master = DEFAULT_MASTER_PASSWORD

    # уже авторизованы
    if st.session_state.get("is_master", False):
        return

    st.title("🔒 Master login")

    pwd = st.text_input("Введите пароль мастера", type="password")
    if st.button("Войти"):
        if pwd == master:
            st.session_state["is_master"] = True
            st.success("Ок. Доступ открыт ✅")
            st.rerun()
        else:
            st.error("Неверный пароль ❌")

    st.stop()