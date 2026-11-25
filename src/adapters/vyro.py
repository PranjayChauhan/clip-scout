"""Phase 2 adapter stub for Vyro (https://vyro.com)."""

from __future__ import annotations

from src.adapters.base import BaseAdapter
from src.schema import Campaign


class VyroAdapter(BaseAdapter):
    platform_id = "vyro"
    platform_name = "Vyro"
    default_fee_pct = 0.0
    is_stub = True

    def fetch_campaigns(self) -> list[Campaign]:
        return []
