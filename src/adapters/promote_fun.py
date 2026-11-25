"""Phase 2 adapter stub for Promote.fun (https://promote.fun)."""

from __future__ import annotations

from src.adapters.base import BaseAdapter
from src.schema import Campaign


class PromoteFunAdapter(BaseAdapter):
    platform_id = "promote_fun"
    platform_name = "Promote.fun"
    default_fee_pct = 0.0
    is_stub = True

    def fetch_campaigns(self) -> list[Campaign]:
        return []
