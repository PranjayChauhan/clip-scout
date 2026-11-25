"""Phase 2 adapter stub for Ssemble Clip Rewards (https://www.ssemble.com/clip-rewards/)."""

from __future__ import annotations

from src.adapters.base import BaseAdapter
from src.schema import Campaign


class SsembleAdapter(BaseAdapter):
    platform_id = "ssemble"
    platform_name = "Ssemble Clip Rewards"
    default_fee_pct = 0.0
    is_stub = True

    def fetch_campaigns(self) -> list[Campaign]:
        return []
