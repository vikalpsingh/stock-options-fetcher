import datetime
import hashlib
import importlib
import os
import secrets
from pathlib import Path
from typing import Any

import streamlit as st

st.set_page_config(page_title="Kite Trader", page_icon="📈", layout="wide")


SALT = b"f9d2a3d7b5f1e6bc"
PASSWORD_HASH = "e58f90b3c2d2c1dd2ed8e22cecfc3f570c28f70f72a02add6b41bade777e13bb"
USERNAME = "vikalpsingh"


@st.cache_resource
def load_kite_app():
    return importlib.import_module("app")


class LazyKiteApp:
    def __getattr__(self, name: str) -> Any:
        return getattr(load_kite_app(), name)


kite_app = LazyKiteApp()


def hash_password(password: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), SALT, 200_000).hex()


def verify_password(password: str) -> bool:
    return secrets.compare_digest(hash_password(password), PASSWORD_HASH)


def default_csv_path() -> Path:
    return kite_app.DEFAULT_CSV_PATH


def set_kite_env_from_sidebar() -> None:
    st.sidebar.subheader("Kite setup")
    api_key = st.sidebar.text_input(
        "KITE_API_KEY",
        value=os.getenv("KITE_API_KEY", kite_app.DEFAULT_KITE_ENV["KITE_API_KEY"]),
    )
    api_secret = st.sidebar.text_input(
        "KITE_API_SECRET",
        value=os.getenv("KITE_API_SECRET", kite_app.DEFAULT_KITE_ENV["KITE_API_SECRET"]),
        type="password",
    )
    access_token = st.sidebar.text_input(
        "KITE_ACCESS_TOKEN",
        value=os.getenv("KITE_ACCESS_TOKEN", kite_app.DEFAULT_KITE_ENV["KITE_ACCESS_TOKEN"]),
        type="password",
    )
    confirm = st.sidebar.text_input(
        "KITE_CONFIRM_LIVE_ORDER",
        value=os.getenv("KITE_CONFIRM_LIVE_ORDER", "YES"),
    )
    os.environ["KITE_API_KEY"] = api_key
    os.environ["KITE_API_SECRET"] = api_secret
    os.environ["KITE_ACCESS_TOKEN"] = access_token
    os.environ["KITE_CONFIRM_LIVE_ORDER"] = confirm


def login() -> bool:
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
        st.session_state.username = ""
    if st.session_state.authenticated:
        return True

    st.title("Kite Trader")
    st.subheader("Login")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        login_button = st.form_submit_button("Log in")
    if login_button:
        if username == USERNAME and verify_password(password):
            st.session_state.authenticated = True
            st.session_state.username = username
            st.success("Login successful.")
            st.rerun()
        else:
            st.error("Invalid username or password.")
    st.info("Use your registered username and password to access the Kite trading app.")
    return False


def logout_button() -> None:
    st.sidebar.markdown(f"**Logged in as:** {st.session_state.username}")
    if st.sidebar.button("Logout"):
        st.session_state.authenticated = False
        st.session_state.username = ""
        st.rerun()


def show_results(results: list[dict[str, Any]] | None) -> None:
    if results:
        st.dataframe(results, use_container_width=True)


def trading_tab() -> None:
    st.subheader("Trading")
    csv_path = st.text_input("CSV path", value=str(default_csv_path()))
    csv_text = st.text_area("CSV text", value=kite_app.read_default_csv_text(), height=180)
    dry_run = st.checkbox("Dry run", value=True)
    no_ltp_price = st.checkbox("Use CSV/manual price only", value=True)
    keep_existing_orders = st.checkbox("Place new order instead of modifying similar open order", value=False)

    col1, col2 = st.columns(2)
    if col1.button("Load / Preview CSV"):
        rows, saved_text = kite_app.load_rows(csv_path, csv_text)
        orders = kite_app.build_orders(rows, no_ltp_price, keep_existing_orders)
        st.session_state.preview_rows = rows
        st.session_state.preview_orders = orders
        st.success(f"Loaded {len(orders)} order(s).")
    if col2.button("Execute Selected"):
        rows = st.session_state.get("preview_rows")
        if not rows:
            rows, _ = kite_app.load_rows(csv_path, csv_text)
        selected = set(range(len(rows)))
        orders, results = kite_app.execute_orders(
            rows,
            selected,
            dry_run,
            no_ltp_price,
            keep_existing_orders,
        )
        st.session_state.preview_orders = orders
        st.success("Dry run completed." if dry_run else "Submitted selected orders to Kite.")
        show_results(results)

    orders = st.session_state.get("preview_orders")
    if orders:
        st.dataframe(orders, use_container_width=True)


def modify_cancel_tab() -> None:
    st.subheader("Modify / Cancel Kite Orders")
    if st.button("Refresh Kite Orders"):
        st.session_state.kite_orders = kite_app.kite_order_book()
    orders = st.session_state.get("kite_orders")
    if not orders:
        st.info("Click Refresh Kite Orders.")
        return

    st.dataframe(orders, use_container_width=True)
    options = [f"{row['variety']}|{row['order_id']}" for row in orders if row.get("is_cancellable")]
    selected = st.multiselect("Select open orders", options, default=options)

    col1, col2 = st.columns(2)
    if col1.button("Cancel Selected Orders"):
        results = kite_app.cancel_selected_orders(selected)
        st.session_state.kite_orders = kite_app.kite_order_book()
        show_results(results)
    if col2.button("Cancel All Orders"):
        results = kite_app.cancel_all_open_orders()
        st.session_state.kite_orders = kite_app.kite_order_book()
        show_results(results)

    with st.expander("Modify selected order quantity / price"):
        if selected:
            key = selected[0]
            order = next((item for item in orders if f"{item['variety']}|{item['order_id']}" == key), {})
            field_key = kite_app.order_form_key(key)
            qty = st.number_input("Quantity", min_value=1, value=int(float(order.get("quantity") or 1)))
            price = st.number_input("Limit price", min_value=0.0, value=float(order.get("price") or 0), step=0.01)
            if st.button("Modify First Selected Order"):
                form = {
                    f"modify_quantity_{field_key}": [str(qty)],
                    f"modify_price_{field_key}": [str(price)],
                }
                results = kite_app.modify_selected_orders([key], form)
                st.session_state.kite_orders = kite_app.kite_order_book()
                show_results(results)


def research_tab() -> None:
    st.subheader("Research")
    st.caption(f"CSV source: {kite_app.default_csv_label()}")
    if st.button("Run Research on CSV Symbols"):
        st.session_state.research_rows = kite_app.research_csv_symbols()
    rows = st.session_state.get("research_rows")
    if rows:
        st.dataframe(rows, use_container_width=True)


def analytics_tab() -> None:
    st.subheader("Option Analytics")
    symbols = kite_app.csv_trading_symbols(kite_app.read_default_csv_text())
    symbol = st.selectbox("Trading symbol", options=symbols or [""], index=0)
    custom = st.text_input("Or enter symbol manually", value=symbol)
    if st.button("Analyze"):
        data = kite_app.option_analytics_for_symbol(custom.strip().upper())
        st.json(data)


def positions_tab() -> None:
    st.subheader("Analysis of current Positions")
    if st.button("Load Active Positions"):
        rows, summary = kite_app.positions_research()
        st.session_state.position_rows = rows
        st.session_state.position_summary = summary
    if st.session_state.get("position_summary"):
        st.metric("Current P&L", kite_app.fmt_number(st.session_state.position_summary.get("total_pnl")))
        st.metric("Margin required", kite_app.fmt_number(st.session_state.position_summary.get("total_deployed")))
    if st.session_state.get("position_rows"):
        st.dataframe(st.session_state.position_rows, use_container_width=True)


def income_tab() -> None:
    st.subheader("INCOME - Monthly PE Sell Strategy")
    if st.button("Refresh PFC / CAMS Candidates"):
        rows, summary = kite_app.income_strategy_candidates()
        st.session_state.income_rows = rows
        st.session_state.income_summary = summary
    if st.session_state.get("income_summary"):
        st.metric("Overall monthly P&L", kite_app.fmt_number(st.session_state.income_summary.get("overall_pnl")))
    if st.session_state.get("income_rows"):
        st.dataframe(st.session_state.income_rows, use_container_width=True)


def commodity_tab() -> None:
    st.subheader("Commodity ETF Watch")
    if st.button("Refresh ETF Quotes"):
        st.session_state.commodity_quotes = kite_app.fetch_commodity_etf_quotes().get("quotes", [])
        st.session_state.commodity_holdings = kite_app.commodity_etf_holdings()
    if st.session_state.get("commodity_quotes"):
        st.dataframe(st.session_state.commodity_quotes, use_container_width=True)
    if st.session_state.get("commodity_holdings"):
        st.subheader("Current ETF Holdings")
        st.dataframe(st.session_state.commodity_holdings, use_container_width=True)


def main() -> None:
    if not login():
        return
    logout_button()
    set_kite_env_from_sidebar()
    st.title("Kite Trader")
    st.caption(f"Default CSV: {default_csv_path()} | {datetime.datetime.now():%d %b %Y %H:%M}")

    tabs = st.tabs(
        [
            "Trading",
            "Modify / Cancel",
            "Positions",
            "Analytics",
            "Research",
            "INCOME",
            "Commodity",
        ]
    )
    with tabs[0]:
        trading_tab()
    with tabs[1]:
        modify_cancel_tab()
    with tabs[2]:
        positions_tab()
    with tabs[3]:
        analytics_tab()
    with tabs[4]:
        research_tab()
    with tabs[5]:
        income_tab()
    with tabs[6]:
        commodity_tab()


if __name__ == "__main__":
    main()
