from __future__ import annotations

import datetime as dt
from typing import Any

import pandas as pd

def _proxy_call_delta(spot_price: float, strike: float) -> float:
    moneyness = strike / max(spot_price, 0.01)
    return max(0.05, min(0.95, 1.5 - moneyness))


RISK_TO_LONG_DELTA = {
    "conservative": 0.80,
    "moderate": 0.75,
    "aggressive": 0.70,
}


def _safe_get(d: dict[str, Any], *keys: str) -> Any:
    cur: Any = d
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def select_best_leap_calls(
    option_chain: list[dict[str, Any]],
    spot_price: float,
    risk_profile: str,
    min_dte: int = 300,
    max_dte: int = 900,
) -> pd.DataFrame:
    today = dt.date.today()
    target_delta = RISK_TO_LONG_DELTA.get(risk_profile, 0.75)

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
            delta = _proxy_call_delta(spot_price, float(strike)) if strike is not None else None

        if expiration_raw is None or strike is None or delta is None:
            continue

        expiration = dt.date.fromisoformat(expiration_raw)
        dte = (expiration - today).days
        if dte < min_dte or dte > max_dte:
            continue

        if delta < 0.55 or delta > 0.9:
            continue

        if strike > spot_price * 1.08:
            continue

        bid = last_quote.get("bid")
        ask = last_quote.get("ask")
        mark = None
        if bid is not None and ask is not None and bid > 0 and ask > 0:
            mark = (bid + ask) / 2
        else:
            close = day.get("close")
            if close:
                mark = float(close)

        if not mark or mark <= 0:
            continue

        volume = day.get("volume") or 0
        oi = contract.get("open_interest") or 0
        liquidity_score = min(1.0, (volume / 500.0) + (oi / 5000.0))

        delta_score = 1.0 - min(1.0, abs(delta - target_delta) / 0.3)
        dte_score = 1.0 - min(1.0, abs(dte - 540) / 600)

        total_score = (0.55 * delta_score) + (0.30 * dte_score) + (0.15 * liquidity_score)

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
                "volume": volume,
                "open_interest": oi,
                "score": round(total_score, 4),
                "intrinsic": max(0.0, spot_price - strike),
                "extrinsic": max(0.0, mark - max(0.0, spot_price - strike)),
            }
        )

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows).sort_values(["score", "open_interest"], ascending=[False, False])
    return df.reset_index(drop=True)
