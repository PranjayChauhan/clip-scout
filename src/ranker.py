"""Deterministic campaign filtering and Real Value Score (0-100) ranking engine."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

from src.schema import Campaign, ClipperProfile, RankedCampaign

DEFAULT_CAMPAIGNS_PATH = Path(__file__).resolve().parent.parent / "data" / "campaigns.json"

# Normalization benchmarks for deterministic 0-100 scoring
RPM_BENCHMARK_USD = 4.0          # $4.00+ net RPM achieves full 45-point RPM weight
BUDGET_BENCHMARK_USD = 25000.0   # $25k+ remaining pool achieves full absolute budget credit
CAP_BENCHMARK_USD = 2500.0       # $2,500+ max per-clip cap (or uncapped) achieves full 15-point upside
MAX_PAINFUL_MIN_PAYOUT = 100.0   # $0 min payout -> 10 pts; >=$100 min payout -> 0 pts


def load_campaigns(path: Path | str = DEFAULT_CAMPAIGNS_PATH) -> list[Campaign]:
    """Load cached Campaign records from data/campaigns.json."""
    target = Path(path)
    if not target.exists():
        return []
    raw = json.loads(target.read_text(encoding="utf-8"))
    items = raw.get("campaigns", []) if isinstance(raw, dict) else raw
    return [Campaign.model_validate(item) for item in items]


def save_campaigns(
    campaigns: Iterable[Campaign],
    path: Path | str = DEFAULT_CAMPAIGNS_PATH,
    scraped_at: Optional[str] = None,
) -> Path:
    """Save normalized Campaign records to data/campaigns.json with metadata envelope."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    items = [c.model_dump(mode="json") for c in campaigns]
    envelope = {
        "updated_at": scraped_at
        or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "count": len(items),
        "campaigns": items,
    }
    target.write_text(json.dumps(envelope, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def is_campaigns_cache_stale(
    path: Path | str = DEFAULT_CAMPAIGNS_PATH,
    max_age_hours: float = 2.0,
    now: Optional[datetime] = None,
) -> bool:
    """Return True if data/campaigns.json is missing, empty, or older than `max_age_hours`."""
    target = Path(path)
    if not target.exists():
        return True
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True

    items = raw.get("campaigns", []) if isinstance(raw, dict) else raw
    if not items:
        return True

    ts_str = raw.get("updated_at") if isinstance(raw, dict) else None
    if not ts_str and items and isinstance(items[0], dict):
        ts_str = items[0].get("scraped_at")
    if not ts_str:
        return True

    cleaned = str(ts_str).strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        updated_dt = datetime.fromisoformat(cleaned)
        if updated_dt.tzinfo is None:
            updated_dt = updated_dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return True

    ref_now = now or datetime.now(timezone.utc)
    return updated_dt < (ref_now - timedelta(hours=max_age_hours))


def _content_type_matches(campaign_ct: str, profile_ct: str) -> bool:
    if profile_ct == "both" or campaign_ct == "both":
        return True
    return campaign_ct == profile_ct


def filter_campaigns(
    campaigns: Iterable[Campaign],
    profile: ClipperProfile,
) -> list[Campaign]:
    """
    Apply strict hard constraints from `profile.json`:
    - `platforms` (if non-empty)
    - `allowed_socials` intersection
    - `content_type` compatibility
    - `effective_rpm_usd >= profile.min_rpm_usd`
    - `remaining_budget_usd >= profile.min_budget_remaining_usd` (when budget is reported)
    - `exclude_niches` (reject if any campaign niche matches excluded list)
    """
    allowed_platforms = set(profile.platforms)
    wanted_socials = set(profile.allowed_socials)
    excluded_niches = set(profile.exclude_niches)

    passed: list[Campaign] = []
    for c in campaigns:
        if allowed_platforms and c.platform.lower() not in allowed_platforms:
            continue

        if wanted_socials and c.allowed_socials:
            if not wanted_socials.intersection(c.allowed_socials):
                continue

        if not _content_type_matches(c.content_type, profile.content_type):
            continue

        net_rpm = c.effective_rpm_usd if c.effective_rpm_usd is not None else c.rpm_usd
        if net_rpm < profile.min_rpm_usd:
            continue

        if c.remaining_budget_usd is not None and c.remaining_budget_usd < profile.min_budget_remaining_usd:
            continue

        campaign_niches = set(c.niches)
        if excluded_niches and campaign_niches.intersection(excluded_niches):
            continue

        passed.append(c)

    return passed


def score_campaign(
    campaign: Campaign,
    profile: Optional[ClipperProfile] = None,
) -> tuple[float, dict[str, float]]:
    """
    Compute the deterministic `Real Value Score` (0.0 - 100.0) using exact weights:
    - Effective RPM: 45% (0 - 45 pts)
    - Remaining Budget health & % unspent: 30% (0 - 30 pts: 18 pts pool depth + 12 pts % unspent)
    - Per-Clip Cap upside: 15% (0 - 15 pts)
    - Low Minimum Payout threshold: 10% (0 - 10 pts)
    """
    net_rpm = campaign.effective_rpm_usd if campaign.effective_rpm_usd is not None else campaign.rpm_usd
    rpm_pts = min(max(net_rpm / RPM_BENCHMARK_USD, 0.0), 1.0) * 45.0

    # Budget health (30 pts): 18 pts absolute remaining pool + 12 pts unspent ratio
    rem = campaign.remaining_budget_usd
    tot = campaign.total_budget_usd
    if rem is None and tot is None:
        budget_pts = 15.0  # Neutral default when platform hides budget numbers
    else:
        abs_pool = rem if rem is not None else (tot or 0.0)
        depth_pts = min(max(abs_pool / BUDGET_BENCHMARK_USD, 0.0), 1.0) * 18.0
        if rem is not None and tot and tot > 0:
            unspent_ratio = min(max(rem / tot, 0.0), 1.0)
        elif rem is not None and rem > 0:
            unspent_ratio = 0.75
        else:
            unspent_ratio = 0.0
        ratio_pts = unspent_ratio * 12.0
        budget_pts = depth_pts + ratio_pts

    # Per-clip cap upside (15 pts): uncapped (None) or >= $2,500 gets full 15 pts
    cap = campaign.max_payout_per_clip_usd
    if cap is None:
        cap_pts = 15.0
    else:
        cap_pts = min(max(cap / CAP_BENCHMARK_USD, 0.0), 1.0) * 15.0

    # Low minimum payout threshold (10 pts): $0-$5 gets ~9.5-10 pts; >=$100 gets 0 pts
    min_pay = campaign.min_payout_usd
    if min_pay is None:
        min_payout_pts = 6.0  # Neutral when unspecified
    else:
        min_payout_pts = max(0.0, 1.0 - min(min_pay / MAX_PAINFUL_MIN_PAYOUT, 1.0)) * 10.0

    raw_total = rpm_pts + budget_pts + cap_pts + min_payout_pts

    # Subtle tie-breaker nudge (up to +2 pts, clamped to 100) for preferred niche alignment
    niche_bonus = 0.0
    if profile and profile.preferred_niches and campaign.niches:
        overlap = len(set(profile.preferred_niches).intersection(campaign.niches))
        if overlap > 0:
            niche_bonus = min(2.0, overlap * 1.0)

    final_score = round(min(100.0, max(0.0, raw_total + niche_bonus)), 2)
    breakdown = {
        "effective_rpm_pts": round(rpm_pts, 2),
        "budget_health_pts": round(budget_pts, 2),
        "per_clip_cap_pts": round(cap_pts, 2),
        "low_min_payout_pts": round(min_payout_pts, 2),
        "preferred_niche_bonus": round(niche_bonus, 2),
    }
    return final_score, breakdown


def rank_campaigns(
    campaigns: Iterable[Campaign],
    profile: Optional[ClipperProfile] = None,
    limit: int = 10,
) -> list[RankedCampaign]:
    """Filter and deterministically rank campaigns by Real Value Score descending."""
    effective_profile = profile or ClipperProfile()
    eligible = filter_campaigns(campaigns, effective_profile)

    scored: list[tuple[float, float, dict[str, float], Campaign]] = []
    for c in eligible:
        score, breakdown = score_campaign(c, effective_profile)
        net_rpm = c.effective_rpm_usd if c.effective_rpm_usd is not None else c.rpm_usd
        scored.append((score, net_rpm, breakdown, c))

    # Deterministic sort: score desc -> net RPM desc -> remaining budget desc -> id asc
    scored.sort(
        key=lambda item: (
            -item[0],
            -item[1],
            -(item[3].remaining_budget_usd or 0.0),
            item[3].id,
        )
    )

    top_slice = scored[: max(0, limit)]
    return [
        RankedCampaign(
            rank=idx + 1,
            real_value_score=score,
            score_breakdown=breakdown,
            campaign=camp,
        )
        for idx, (score, _rpm, breakdown, camp) in enumerate(top_slice)
    ]
