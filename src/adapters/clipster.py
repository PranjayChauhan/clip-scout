"""Phase 2 adapter stub for Clipster (https://clipster.gg)."""

from __future__ import annotations

from src.adapters.base import BaseAdapter
from src.schema import Campaign


class ClipsterAdapter(BaseAdapter):
    platform_id = "clipster"
    platform_name = "Clipster"
    default_fee_pct = 0.0
    is_stub = True

    def fetch_campaigns(self) -> list[Campaign]:
        return []
