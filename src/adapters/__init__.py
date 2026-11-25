"""Dynamic registry of modular platform adapters keyed by platform ID."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Type

from src.adapters.base import AdapterResult, BaseAdapter
from src.adapters.clipping_io import ClippingIoAdapter
from src.adapters.clipping_net import ClippingNetAdapter
from src.adapters.clipster import ClipsterAdapter
from src.adapters.promote_fun import PromoteFunAdapter
from src.adapters.ssemble import SsembleAdapter
from src.adapters.vyro import VyroAdapter
from src.adapters.whop import WhopAdapter
from src.discovery import DEFAULT_PLATFORMS_PATH, get_active_trusted_platforms
from src.schema import Campaign, ClipperProfile

ADAPTER_CLASSES: dict[str, Type[BaseAdapter]] = {
    WhopAdapter.platform_id: WhopAdapter,
    VyroAdapter.platform_id: VyroAdapter,
    ClippingNetAdapter.platform_id: ClippingNetAdapter,
    ClipsterAdapter.platform_id: ClipsterAdapter,
    PromoteFunAdapter.platform_id: PromoteFunAdapter,
    ClippingIoAdapter.platform_id: ClippingIoAdapter,
    SsembleAdapter.platform_id: SsembleAdapter,
}


def resolve_target_adapters(
    profile: Optional[ClipperProfile] = None,
    platforms_path: Path | str = DEFAULT_PLATFORMS_PATH,
    fixture_path: Optional[Path | str] = None,
    include_stubs: bool = False,
) -> list[BaseAdapter]:
    """
    Instantiate adapters ONLY for active, free-to-join trusted platforms in data/platforms.json
    that also match `profile.platforms` (when specified).
    """
    trusted = get_active_trusted_platforms(platforms_path)
    allowed_ids = set(profile.platforms) if (profile and profile.platforms) else None

    instances: list[BaseAdapter] = []
    for record in trusted:
        if allowed_ids is not None and record.id not in allowed_ids:
            continue
        cls = ADAPTER_CLASSES.get(record.id)
        if cls is None:
            continue
        if cls.is_stub and not include_stubs and fixture_path is None:
            continue
        adapter_fixture = fixture_path if record.id == "whop" else None
        instances.append(cls(fixture_path=adapter_fixture))
    return instances


def scrape_active_campaigns(
    profile: Optional[ClipperProfile] = None,
    platforms_path: Path | str = DEFAULT_PLATFORMS_PATH,
    fixture_path: Optional[Path | str] = None,
    include_stubs: bool = False,
) -> tuple[list[Campaign], list[AdapterResult]]:
    """Run all resolved adapters safely and deduplicate normalized campaigns by ID."""
    adapters = resolve_target_adapters(
        profile=profile,
        platforms_path=platforms_path,
        fixture_path=fixture_path,
        include_stubs=include_stubs,
    )
    results: list[AdapterResult] = []
    deduped: dict[str, Campaign] = {}

    for adapter in adapters:
        res = adapter.safe_fetch()
        results.append(res)
        for camp in res.campaigns:
            deduped[camp.id] = camp

    return list(deduped.values()), results


__all__ = [
    "ADAPTER_CLASSES",
    "AdapterResult",
    "BaseAdapter",
    "ClippingIoAdapter",
    "ClippingNetAdapter",
    "ClipsterAdapter",
    "PromoteFunAdapter",
    "SsembleAdapter",
    "VyroAdapter",
    "WhopAdapter",
    "resolve_target_adapters",
    "scrape_active_campaigns",
]
