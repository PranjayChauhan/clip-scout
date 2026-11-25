"""Unit tests for deterministic filtering and Real Value Score (0-100) ranking."""

from pathlib import Path

from src.adapters.whop import WhopAdapter
from src.ranker import filter_campaigns, rank_campaigns, score_campaign
from src.schema import Campaign, ClipperProfile

FIXTURE_FILE = Path(__file__).resolve().parent / "fixtures" / "whop_campaigns.json"


def test_filter_excludes_disallowed_niches_ugc_and_depleted_budgets() -> None:
    campaigns = WhopAdapter(fixture_path=FIXTURE_FILE).fetch_campaigns()
    profile = ClipperProfile(
        allowed_socials=["tiktok", "reels", "shorts"],
        content_type="clipping",
        min_rpm_usd=1.0,
        min_budget_remaining_usd=500.0,
        preferred_niches=["gaming", "tech"],
        exclude_niches=["casino", "gambling"],
        platforms=["whop"],
    )

    filtered = filter_campaigns(campaigns, profile)
    filtered_ids = {c.id for c in filtered}

    # Casino excluded via exclude_niches
    assert "whop:cr_StakeClone_high_rpm" not in filtered_ids
    # Pure UGC excluded when profile wants clipping
    assert "whop:cr_fitness_app_ugc" not in filtered_ids
    # $180 remaining budget excluded via min_budget_remaining_usd=500
    assert "whop:cr_almost_depleted_pool" not in filtered_ids
    # Valid clipping & 'both' campaigns retained
    assert "whop:cr_cursor_ai_launch" in filtered_ids
    assert "whop:cr_kaicenat_marathon" in filtered_ids


def test_real_value_score_prefers_healthy_budget_and_low_min_payout_over_raw_rpm_trap() -> None:
    healthy_camp = Campaign(
        id="whop:healthy",
        platform="whop",
        title="Healthy High-Cap Campaign",
        creator_or_brand="Creator A",
        url="https://whop.com/content-rewards/healthy",
        rpm_usd=3.2,
        platform_fee_pct=10.0,
        total_budget_usd=30000.0,
        remaining_budget_usd=27000.0,
        min_payout_usd=10.0,
        max_payout_per_clip_usd=3000.0,
        allowed_socials=["tiktok", "shorts"],
        content_type="clipping",
        niches=["gaming"],
    )
    trap_camp = Campaign(
        id="whop:trap",
        platform="whop",
        title="Slightly Higher RPM Trap Campaign",
        creator_or_brand="Creator B",
        url="https://whop.com/content-rewards/trap",
        rpm_usd=3.5,
        platform_fee_pct=10.0,
        total_budget_usd=20000.0,
        remaining_budget_usd=600.0,  # 97% depleted!
        min_payout_usd=100.0,         # High cashout barrier
        max_payout_per_clip_usd=250.0, # Tiny per-clip upside cap
        allowed_socials=["tiktok", "shorts"],
        content_type="clipping",
        niches=["gaming"],
    )

    s_healthy, _ = score_campaign(healthy_camp)
    s_trap, _ = score_campaign(trap_camp)
    assert s_healthy > s_trap

    ranked = rank_campaigns([trap_camp, healthy_camp], limit=2)
    assert ranked[0].campaign.id == "whop:healthy"
    assert ranked[0].rank == 1
