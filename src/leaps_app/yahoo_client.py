from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

import pandas as pd
import yfinance as yf


class YahooApiError(RuntimeError):
    pass


@dataclass
class YahooDataClient:
    timeout_seconds: int = 20

    def get_spot_price(self, symbol: str) -> float:
        ticker = yf.Ticker(symbol.upper())
        fast = ticker.fast_info or {}
        for key in ("lastPrice", "regularMarketPrice", "previousClose"):
            value = fast.get(key)
            if value:
                return float(value)

        hist = ticker.history(period="1d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])

        raise YahooApiError(f"Could not fetch spot price for {symbol} from Yahoo Finance.")

    def get_option_chain(
        self,
        symbol: str,
        expiration_gte: dt.date,
        expiration_lte: dt.date,
        contract_type: str = "call",
    ) -> list[dict[str, Any]]:
        ticker = yf.Ticker(symbol.upper())
        expirations = ticker.options
        if not expirations:
            raise YahooApiError(f"No option expirations found for {symbol}.")

        selected = []
        for exp_str in expirations:
            exp = dt.date.fromisoformat(exp_str)
            if expiration_gte <= exp <= expiration_lte:
                selected.append(exp_str)

        results: list[dict[str, Any]] = []
        for exp_str in selected:
            chain = ticker.option_chain(exp_str)
            frame: pd.DataFrame = chain.calls if contract_type == "call" else chain.puts
            if frame.empty:
                continue

            for _, row in frame.iterrows():
                bid = row.get("bid")
                ask = row.get("ask")
                last_price = row.get("lastPrice")
                volume = row.get("volume")
                oi = row.get("openInterest")
                strike = row.get("strike")
                contract_symbol = row.get("contractSymbol")

                results.append(
                    {
                        "details": {
                            "ticker": contract_symbol,
                            "expiration_date": exp_str,
                            "strike_price": float(strike) if strike is not None else None,
                        },
                        "last_quote": {
                            "bid": float(bid) if bid is not None else None,
                            "ask": float(ask) if ask is not None else None,
                        },
                        "day": {
                            "close": float(last_price) if last_price is not None else None,
                            "volume": int(volume) if volume is not None and volume == volume else 0,
                        },
                        "open_interest": int(oi) if oi is not None and oi == oi else 0,
                        "greeks": {},
                    }
                )

        if not results:
            raise YahooApiError(
                f"No {contract_type} contracts found between {expiration_gte} and {expiration_lte} for {symbol}."
            )

        return results
