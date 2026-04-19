from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass
from typing import Any

import requests

from .rate_limiter import SlidingWindowRateLimiter


class PolygonApiError(RuntimeError):
    pass


@dataclass
class PolygonClient:
    api_key: str
    max_requests_per_minute: int = 5
    timeout_seconds: int = 20

    def __post_init__(self) -> None:
        self.base_url = "https://api.polygon.io"
        self.session = requests.Session()
        self.limiter = SlidingWindowRateLimiter(self.max_requests_per_minute, 60)

    def _request(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        query = dict(params or {})
        query["apiKey"] = self.api_key
        url = f"{self.base_url}{path}"

        retries = 3
        for attempt in range(retries):
            self.limiter.acquire()
            response = self.session.get(url, params=query, timeout=self.timeout_seconds)

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", "12"))
                time.sleep(retry_after)
                continue

            if response.status_code >= 400:
                raise PolygonApiError(
                    f"Polygon API request failed: {response.status_code} - {response.text}"
                )

            payload = response.json()
            if payload.get("status") in {"ERROR", "NOT_AUTHORIZED"}:
                raise PolygonApiError(str(payload))
            return payload

        raise PolygonApiError("Polygon API rate limit retries exhausted.")

    def get_stock_last_trade(self, symbol: str) -> dict[str, Any]:
        return self._request(f"/v2/last/trade/{symbol.upper()}")

    def get_stock_snapshot(self, symbol: str) -> dict[str, Any]:
        return self._request(f"/v2/snapshot/locale/us/markets/stocks/tickers/{symbol.upper()}")

    def get_option_chain(
        self,
        underlying: str,
        expiration_gte: dt.date | None = None,
        expiration_lte: dt.date | None = None,
        contract_type: str = "call",
        limit: int = 250,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "contract_type": contract_type,
            "limit": limit,
            "sort": "expiration_date",
            "order": "asc",
        }
        if expiration_gte:
            params["expiration_date.gte"] = expiration_gte.isoformat()
        if expiration_lte:
            params["expiration_date.lte"] = expiration_lte.isoformat()

        results: list[dict[str, Any]] = []
        path = f"/v3/snapshot/options/{underlying.upper()}"

        while True:
            data = self._request(path, params=params)
            results.extend(data.get("results", []))

            next_url = data.get("next_url")
            if not next_url:
                break

            if next_url.startswith(self.base_url):
                path = next_url[len(self.base_url) :]
            else:
                path = next_url
            params = {}

        return results