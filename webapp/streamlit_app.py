import streamlit as st


st.set_page_config(page_title="Kite Trader Disabled", page_icon="X", layout="centered")

st.title("Kite Trader Access Disabled")
st.error("Streamlit Cloud access is blocked.")
st.info(
    "This trading app is being moved to AWS. "
    "For safety, live trading, Kite credentials, positions, orders, and analytics "
    "are not available through Streamlit Cloud."
)
st.stop()
