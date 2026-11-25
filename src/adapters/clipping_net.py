"""Phase 2 adapter stub for Clipping.net (https://clipping.net)."""

from __future__ import annotations

from src.adapters.base import BaseAdapter
from src.schema import Campaign


class ClippingNetAdapter(BaseAdapter):
    platform_id = "clipping_net"
    platform_name = "Clipping.net"
    default_fee_pct = 0.0
    is_stub = True

    def fetch_campaigns(self) -> list[Campaign]:
        return []
