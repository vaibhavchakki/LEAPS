from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import streamlit as st

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from leaps_app.leap_selector import select_best_leap_calls
from leaps_app.pmcc_advisor import suggest_short_calls
from leaps_app.yahoo_client import YahooApiError, YahooDataClient

st.set_page_config(page_title="LEAP + PMCC Advisor", layout="wide")
st.title("INTC LEAP Selector + Poor Man's Covered Call Advisor")
st.caption("Uses Yahoo Finance live data (free API path).")


def load_positions(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_positions(path: Path, positions: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(positions, indent=2), encoding="utf-8")


with st.sidebar:
    st.header("Settings")
    symbol = st.text_input("Underlying", value="INTC").strip().upper()
    risk_profile = st.selectbox("Risk Profile", ["conservative", "moderate", "aggressive"], index=1)
    cycle = st.selectbox("Call Writing Cycle", ["weekly", "monthly"], index=0)
    positions_path_str = st.text_input(
        "Positions JSON Path",
        value=str(Path("data") / "leap_positions.json"),
        help="Where your bought LEAP positions are stored.",
    )

client = YahooDataClient()

try:
    spot = client.get_spot_price(symbol)
    st.metric(f"{symbol} Spot Price", f"${spot:,.2f}")
except YahooApiError as exc:
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
                    "spot_price": spot,
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
selected_long["spot_price"] = spot

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

st.caption("Note: This is guidance, not financial advice.")
