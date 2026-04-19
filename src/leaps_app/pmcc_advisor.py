from __future__ import annotations

import datetime as dt
from typing import Any

import pandas as pd

def _proxy_short_delta(spot_price: float, strike: float) -> float:
    moneyness = strike / max(spot_price, 0.01)
    return max(0.02, min(0.60, 1.5 - moneyness))


RISK_TO_SHORT_DELTA = {
    "conservative": 0.15,
    "moderate": 0.25,
    "aggressive": 0.35,
}


def suggest_short_calls(
    option_chain: list[dict[str, Any]],
    long_leap: dict[str, Any],
    risk_profile: str,
    cycle: str,
) -> pd.DataFrame:
    today = dt.date.today()
    target_delta = RISK_TO_SHORT_DELTA.get(risk_profile, 0.25)
    min_dte, max_dte = (6, 14) if cycle == "weekly" else (25, 45)

    long_strike = float(long_leap["strike"])
    long_debit = float(long_leap["entry_price"])
    contracts = int(long_leap.get("contracts", 1))

    break_even_like = long_strike + long_debit
    spot_price = float(long_leap.get("spot_price", break_even_like))

    rows: list[dict[str, Any]] = []
    for contract in option_chain:
        details = contract.get("details", {})
        greeks = contract.get("greeks", {})
        last_quote = contract.get("last_quote", {})
        day = contract.get("day", {})

        expiration_raw = details.get("expiration_date")
        strike = details.get("strike_price")
        delta = greeks.get("delta")
        if delta is None:
            delta = _proxy_short_delta(spot_price, float(strike)) if strike is not None else None

        if expiration_raw is None or strike is None or delta is None:
            continue

        expiration = dt.date.fromisoformat(expiration_raw)
        dte = (expiration - today).days

        if dte < min_dte or dte > max_dte:
            continue

        if delta < 0.05 or delta > 0.50:
            continue

        if strike <= long_strike:
            continue

        bid = last_quote.get("bid")
        ask = last_quote.get("ask")
        if bid is not None and ask is not None and bid > 0 and ask > 0:
            mark = (bid + ask) / 2
        else:
            close = day.get("close")
            if not close:
                continue
            mark = float(close)

        if mark <= 0:
            continue

        annualized_yield = (mark / long_debit) * (365 / dte)
        buffer_from_break_even = strike - break_even_like

        delta_score = 1.0 - min(1.0, abs(delta - target_delta) / 0.35)
        income_score = min(1.0, annualized_yield / 1.5)
        safety_score = 0.0 if buffer_from_break_even < 0 else min(1.0, buffer_from_break_even / 8.0)

        score = (0.45 * delta_score) + (0.35 * income_score) + (0.20 * safety_score)

        rows.append(
            {
                "option_ticker": details.get("ticker"),
                "expiration": expiration_raw,
                "dte": dte,
                "strike": strike,
                "delta": delta,
                "bid": bid,
                "ask": ask,
                "mark": mark,
                "premium_per_contract": mark * 100,
                "total_premium": mark * 100 * contracts,
                "buffer_from_break_even": buffer_from_break_even,
                "annualized_yield": annualized_yield,
                "score": round(score, 4),
            }
        )

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)
