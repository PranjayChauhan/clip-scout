"""FastMCP server implementation for clip-scout (zero-token clipping campaign tools)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP

from src.adapters import scrape_active_campaigns
from src.cli import DEFAULT_PROFILE_PATH, load_profile_or_default
from src.discovery import (
    DEFAULT_PLATFORMS_PATH,
    ensure_fresh_trusted_registry,
    get_active_trusted_platforms,
    is_registry_stale,
    load_platforms,
    run_discovery,
)
from src.ranker import (
    DEFAULT_CAMPAIGNS_PATH,
    is_campaigns_cache_stale,
    load_campaigns,
    rank_campaigns,
    save_campaigns,
)
from src.schema import ClipperProfile

mcp = FastMCP(
    name="clip-scout",
    instructions=(
        "Zero-token clipping campaign discovery engine. "
        "Always verify/discover live trusted platforms first (Stage 0) before onboarding or ranking."
    ),
)


@mcp.tool()
def list_trusted_platforms(
    include_inactive: bool = False,
    auto_verify_if_stale: bool = False,
    platforms_path: str = str(DEFAULT_PLATFORMS_PATH),
) -> dict:
    """List verified clipping platforms from data/platforms.json (Stage 0)."""
    path = Path(platforms_path)
    use_sentinel = path.resolve() == DEFAULT_PLATFORMS_PATH.resolve()
    stale = is_registry_stale(path, require_local_verification=use_sentinel)
    if stale and auto_verify_if_stale:
        ensure_fresh_trusted_registry(platforms_path=path)
        stale = False

    records = load_platforms(path) if include_inactive else get_active_trusted_platforms(path)
    return {
        "stale": stale,
        "count": len(records),
        "platforms": [
            {
                "id": r.id,
                "name": r.name,
                "url": r.url,
                "model": r.model,
                "status": r.status,
                "free_to_join": r.free_to_join,
                "typical_rpm_range": r.typical_rpm_range,
                "supported_socials": r.supported_socials,
                "adapter_implemented": r.adapter_implemented,
                "trust_notes": r.trust_notes,
                "last_verified": r.last_verified,
            }
            for r in records
        ],
    }


@mcp.tool()
def discover_platforms(
    check_live: bool = True,
    web_search: bool = True,
    extra_candidates: Optional[list[dict]] = None,
    platforms_path: str = str(DEFAULT_PLATFORMS_PATH),
) -> dict:
    """
    Independently search the web and live-audit every clipping platform for real campaign activity,
    marking shut-down, pivoted, or pay-to-join platforms `inactive` in data/platforms.json.
    """
    records, diff = run_discovery(
        platforms_path=Path(platforms_path),
        check_live=check_live,
        web_search=(web_search and check_live),
        candidates=extra_candidates,
    )
    return {
        "diff": diff.to_dict(),
        "active_platforms": [r.id for r in records if r.is_trusted_active],
    }


@mcp.tool()
def save_profile(
    allowed_socials: list[str],
    content_type: str = "clipping",
    min_rpm_usd: float = 1.0,
    min_budget_remaining_usd: float = 500.0,
    preferred_niches: Optional[list[str]] = None,
    exclude_niches: Optional[list[str]] = None,
    platforms: Optional[list[str]] = None,
    profile_path: str = str(DEFAULT_PROFILE_PATH),
) -> dict:
    """Save the clipper's 5-question intake preferences to profile.json (Stage 1)."""
    profile = ClipperProfile(
        allowed_socials=allowed_socials,
        content_type=content_type,  # type: ignore[arg-type]
        min_rpm_usd=min_rpm_usd,
        min_budget_remaining_usd=min_budget_remaining_usd,
        preferred_niches=preferred_niches or [],
        exclude_niches=exclude_niches or [],
        platforms=platforms or [],
    )
    target = Path(profile_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(profile.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return {"saved_to": str(target), "profile": profile.model_dump(mode="json")}


@mcp.tool()
def refresh_campaigns(
    profile_path: str = str(DEFAULT_PROFILE_PATH),
    platforms_path: str = str(DEFAULT_PLATFORMS_PATH),
    campaigns_path: str = str(DEFAULT_CAMPAIGNS_PATH),
    force: bool = False,
) -> dict:
    """Refresh data/campaigns.json using only live-verified active trusted adapters."""
    plat_file = Path(platforms_path)
    camp_file = Path(campaigns_path)

    if force or plat_file.resolve() == DEFAULT_PLATFORMS_PATH.resolve():
        ensure_fresh_trusted_registry(platforms_path=plat_file)

    if not force and not is_campaigns_cache_stale(camp_file, max_age_hours=2.0):
        cached = load_campaigns(camp_file)
        return {
            "refreshed": False,
            "reason": "Cache is fresh (<2 hours old)",
            "campaign_count": len(cached),
        }

    profile = load_profile_or_default(Path(profile_path))
    campaigns, results = scrape_active_campaigns(
        profile=profile,
        platforms_path=plat_file,
    )
    if campaigns or not camp_file.exists():
        save_campaigns(campaigns, camp_file)
        final_count = len(campaigns)
        preserved = False
    else:
        final_count = len(load_campaigns(camp_file))
        preserved = True

    return {
        "refreshed": not preserved,
        "preserved_existing_cache": preserved,
        "campaign_count": final_count,
        "adapters": [
            {"platform": r.platform_id, "status": r.status, "fetched": len(r.campaigns), "message": r.message}
            for r in results
        ],
    }


@mcp.tool()
def get_top_campaigns(
    profile_path: str = str(DEFAULT_PROFILE_PATH),
    platforms_path: str = str(DEFAULT_PLATFORMS_PATH),
    campaigns_path: str = str(DEFAULT_CAMPAIGNS_PATH),
    limit: int = 10,
) -> dict:
    """Return compact ranked Top N campaigns (~500 tokens max) strictly from active trusted platforms."""
    profile = load_profile_or_default(Path(profile_path))
    active_trusted_ids = {p.id for p in get_active_trusted_platforms(Path(platforms_path))}
    campaigns = load_campaigns(Path(campaigns_path))
    if active_trusted_ids:
        campaigns = [c for c in campaigns if c.platform in active_trusted_ids]

    ranked = rank_campaigns(campaigns, profile=profile, limit=min(max(limit, 1), 25))
    return {
        "count": len(ranked),
        "top": [
            {
                "rank": item.rank,
                "score": round(item.real_value_score, 1),
                "plat": item.campaign.platform,
                "title": item.campaign.title,
                "brand": item.campaign.creator_or_brand,
                "url": item.campaign.url,
                "rpm": round(item.campaign.effective_rpm_usd or item.campaign.rpm_usd, 2),
                "rem": int(item.campaign.remaining_budget_usd)
                if item.campaign.remaining_budget_usd is not None
                else None,
                "min": int(item.campaign.min_payout_usd)
                if item.campaign.min_payout_usd is not None
                else None,
                "cap": int(item.campaign.max_payout_per_clip_usd)
                if item.campaign.max_payout_per_clip_usd is not None
                else None,
                "soc": item.campaign.allowed_socials,
                "rules": (
                    item.campaign.requirements_summary[: (107 if item.rank <= 3 else 49)].rstrip() + "..."
                    if len(item.campaign.requirements_summary) > (110 if item.rank <= 3 else 52)
                    else item.campaign.requirements_summary
                ),
            }
            for item in ranked
        ],
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
