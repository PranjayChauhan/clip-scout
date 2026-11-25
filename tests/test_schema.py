"""Unit tests for core Pydantic schemas (PlatformRecord, Campaign, ClipperProfile)."""

from src.schema import Campaign, ClipperProfile, PlatformRecord


def test_campaign_computes_effective_rpm_automatically() -> None:
    camp = Campaign(
        id="whop:test_1",
        platform="whop",
        title="Test Campaign",
        creator_or_brand="Test Brand",
        url="https://whop.com/content-rewards/test",
        rpm_usd=3.0,
        platform_fee_pct=10.0,
        allowed_socials=["TikTok", "Instagram", "YouTube", "Twitter"],
        niches=["Gaming", "Tech", "gaming"],
    )
    assert camp.effective_rpm_usd == 2.7
    assert camp.allowed_socials == ["tiktok", "reels", "shorts", "x"]
    assert camp.niches == ["gaming", "tech"]


def test_platform_record_trusted_active_property() -> None:
    trusted = PlatformRecord(
        id="whop",
        name="Whop Content Rewards",
        url="https://whop.com/discover/content-rewards/",
        model="open_marketplace",
        status="active",
        free_to_join=True,
        typical_rpm_range="$0.50-$3.00",
    )
    paywalled = trusted.model_copy(update={"id": "scam", "free_to_join": False})
    dead = trusted.model_copy(update={"id": "clipaffiliates", "status": "inactive"})

    assert trusted.is_trusted_active is True
    assert paywalled.is_trusted_active is False
    assert dead.is_trusted_active is False


def test_clipper_profile_normalizes_socials_and_lists() -> None:
    profile = ClipperProfile(
        allowed_socials=["IG", "YT_Shorts", "TikTok"],
        preferred_niches=["Gaming ", "TECH"],
        exclude_niches=["Casino"],
        platforms=["WHOP"],
    )
    assert profile.allowed_socials == ["reels", "shorts", "tiktok"]
    assert profile.preferred_niches == ["gaming", "tech"]
    assert profile.exclude_niches == ["casino"]
    assert profile.platforms == ["whop"]
