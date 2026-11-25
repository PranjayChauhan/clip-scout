"""Base interface for clip-scout modular platform adapters (Stage 2)."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx

from src.schema import Campaign

DEFAULT_ADAPTER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


@dataclass
class AdapterResult:
    """Outcome of running a single platform adapter without crashing the pipeline."""

    platform_id: str
    campaigns: list[Campaign] = field(default_factory=list)
    status: str = "ok"  # "ok" | "stub" | "error"
    message: str = ""
    elapsed_ms: int = 0


class BaseAdapter(ABC):
    """
    Abstract base adapter for clipping marketplaces.

    Design principles:
    - HTTP/JSON endpoints first; fall back to Playwright only when explicitly needed.
    - Polite rate limiting between requests.
    - Never raise unhandled exceptions during batch scraping (`safe_fetch`).
    """

    platform_id: str = ""
    platform_name: str = ""
    default_fee_pct: float = 0.0
    rate_limit_seconds: float = 0.5
    is_stub: bool = False

    def __init__(
        self,
        http_client: Optional[httpx.Client] = None,
        fixture_path: Optional[Path | str] = None,
        timeout_seconds: float = 12.0,
    ) -> None:
        self._external_client = http_client
        self.fixture_path = Path(fixture_path) if fixture_path else None
        self.timeout_seconds = timeout_seconds
        self._last_request_ts: float = 0.0

    def _throttle(self) -> None:
        if self.rate_limit_seconds <= 0:
            return
        elapsed = time.monotonic() - self._last_request_ts
        if self._last_request_ts > 0 and elapsed < self.rate_limit_seconds:
            time.sleep(self.rate_limit_seconds - elapsed)
        self._last_request_ts = time.monotonic()

    def _get_client(self) -> tuple[httpx.Client, bool]:
        if self._external_client is not None:
            return self._external_client, False
        return httpx.Client(headers=DEFAULT_ADAPTER_HEADERS, timeout=self.timeout_seconds), True

    def http_get(self, url: str, **kwargs) -> httpx.Response:
        """Rate-limited HTTP GET helper."""
        self._throttle()
        client, owns = self._get_client()
        try:
            resp = client.get(url, follow_redirects=True, **kwargs)
            resp.raise_for_status()
            return resp
        finally:
            if owns:
                client.close()

    @abstractmethod
    def fetch_campaigns(self) -> list[Campaign]:
        """Fetch and normalize active campaigns into the canonical Campaign schema."""

    def safe_fetch(self) -> AdapterResult:
        """Execute `fetch_campaigns()` safely, capturing errors so other adapters continue."""
        start = time.perf_counter()
        if self.is_stub and self.fixture_path is None:
            return AdapterResult(
                platform_id=self.platform_id,
                campaigns=[],
                status="stub",
                message=f"{self.platform_name or self.platform_id} adapter stub (live endpoint pending Phase 2).",
                elapsed_ms=int((time.perf_counter() - start) * 1000),
            )
        try:
            campaigns = self.fetch_campaigns()
            return AdapterResult(
                platform_id=self.platform_id,
                campaigns=campaigns,
                status="ok",
                message=f"Fetched {len(campaigns)} campaigns",
                elapsed_ms=int((time.perf_counter() - start) * 1000),
            )
        except Exception as exc:  # noqa: BLE001 — intentional fault isolation per adapter
            return AdapterResult(
                platform_id=self.platform_id,
                campaigns=[],
                status="error",
                message=f"{type(exc).__name__}: {exc}",
                elapsed_ms=int((time.perf_counter() - start) * 1000),
            )
