"""Phase 2 adapter stub for Clipping.io (https://clipping.io)."""

from __future__ import annotations

from src.adapters.base import BaseAdapter
from src.schema import Campaign


class ClippingIoAdapter(BaseAdapter):
    platform_id = "clipping_io"
    platform_name = "Clipping.io"
    default_fee_pct = 0.0
    is_stub = True

    def fetch_campaigns(self) -> list[Campaign]:
        return []
