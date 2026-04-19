from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from .leap_selector import select_best_leap_calls
from .pmcc_advisor import suggest_short_calls
from .polygon_client import PolygonApiError, PolygonClient

st.set_page_config(page_title="LEAP + PMCC Advisor", layout="wide")
st.title("INTC LEAP Selector + Poor Man's Covered Call Advisor")
st.caption("Uses Polygon (Massive) live market data with built-in 5 req/min rate limiting.")


def load_positions(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_positions(path: Path, positions: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(positions, indent=2), encoding="utf-8")


with st.sidebar:
    st.header("Settings")
    api_key = st.text_input("Polygon API Key", value=os.getenv("POLYGON_API_KEY", ""), type="password")
    symbol = st.text_input("Underlying", value="INTC").strip().upper()
    risk_profile = st.selectbox("Risk Profile", ["conservative", "moderate", "aggressive"], index=1)
    cycle = st.selectbox("Call Writing Cycle", ["weekly", "monthly"], index=0)
    positions_path_str = st.text_input(
        "Positions JSON Path",
        value=str(Path("data") / "leap_positions.json"),
        help="Where your bought LEAP positions are stored.",
    )

if not api_key:
    st.warning("Enter your Polygon API key in the sidebar to continue.")
    st.stop()

client = PolygonClient(api_key=api_key, max_requests_per_minute=5)

try:
    snapshot = client.get_stock_snapshot(symbol)
    ticker = snapshot.get("ticker", {})
    spot = ticker.get("lastTrade", {}).get("p") or ticker.get("day", {}).get("c")
    if not spot:
        trade = client.get_stock_last_trade(symbol)
        spot = trade.get("last", {}).get("price")

    if not spot:
        st.error("Could not fetch stock price.")
        st.stop()

    st.metric(f"{symbol} Spot Price", f"${spot:,.2f}")
except PolygonApiError as exc:
    st.error(f"API error: {exc}")
    st.stop()

col1, col2 = st.columns(2)

with col1:
    st.subheader("1) LEAP Selector")
    with st.spinner("Loading LEAP chain..."):
        leap_chain = client.get_option_chain(
            symbol,
            expiration_gte=dt.date.today() + dt.timedelta(days=280),
            expiration_lte=dt.date.today() + dt.timedelta(days=900),
            contract_type="call",
        )

    leaps_df = select_best_leap_calls(leap_chain, float(spot), risk_profile=risk_profile)
    if leaps_df.empty:
        st.info("No LEAP candidates found with current filters.")
    else:
        st.dataframe(leaps_df.head(15), use_container_width=True)
        best = leaps_df.iloc[0].to_dict()
        st.success(
            f"Top LEAP: {best['option_ticker']} | Strike {best['strike']} | Exp {best['expiration']} | Score {best['score']}"
        )

with col2:
    st.subheader("2) Save/Load Your Bought LEAP")
    positions_path = Path(positions_path_str)
    positions = load_positions(positions_path)

    with st.form("add_position"):
        st.markdown("Add a LEAP position you've already bought.")
        pos_underlying = st.text_input("Underlying", value=symbol)
        pos_ticker = st.text_input("Option Ticker (optional)", value="")
        pos_exp = st.date_input("Expiration")
        pos_strike = st.number_input("Long Strike", min_value=0.0, value=20.0, step=0.5)
        pos_entry = st.number_input("Entry Price (debit paid)", min_value=0.01, value=7.5, step=0.05)
        pos_contracts = st.number_input("Contracts", min_value=1, value=1, step=1)
        submitted = st.form_submit_button("Save Position")

        if submitted:
            positions.append(
                {
                    "underlying": pos_underlying.upper(),
                    "option_ticker": pos_ticker,
                    "expiration": str(pos_exp),
                    "strike": pos_strike,
                    "entry_price": pos_entry,
                    "contracts": int(pos_contracts),
                }
            )
            save_positions(positions_path, positions)
            st.success(f"Saved to {positions_path}")

    st.markdown("Current saved LEAP positions")
    st.json(positions)

st.subheader("3) PMCC Covered Call Suggestions")
positions_path = Path(positions_path_str)
positions = load_positions(positions_path)

matching = [p for p in positions if p.get("underlying", "").upper() == symbol]
if not matching:
    st.info("No saved LEAP positions for this symbol yet. Add one first.")
    st.stop()

selected_idx = st.selectbox(
    "Select long LEAP position",
    options=list(range(len(matching))),
    format_func=lambda i: f"{matching[i].get('option_ticker') or matching[i]['underlying']} | K={matching[i]['strike']} | debit={matching[i]['entry_price']}",
)
selected_long = matching[selected_idx]

short_min = dt.date.today() + dt.timedelta(days=5 if cycle == "weekly" else 22)
short_max = dt.date.today() + dt.timedelta(days=17 if cycle == "weekly" else 55)

with st.spinner("Loading short-call candidates..."):
    short_chain = client.get_option_chain(
        symbol,
        expiration_gte=short_min,
        expiration_lte=short_max,
        contract_type="call",
    )

suggestions = suggest_short_calls(short_chain, selected_long, risk_profile, cycle)
if suggestions.empty:
    st.warning("No short call candidates found. Try changing cycle/risk profile.")
else:
    st.dataframe(suggestions.head(20), use_container_width=True)
    top = suggestions.iloc[0].to_dict()
    st.success(
        "Best short call now: "
        f"{top['option_ticker']} | strike {top['strike']} | exp {top['expiration']} | "
        f"est premium ${top['total_premium']:.2f}"
    )

st.caption(
    "Note: This is guidance, not financial advice. Validate liquidity, assignment risk, and earnings/events before trading."
)