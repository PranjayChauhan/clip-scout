"""Core Pydantic schemas for clip-scout platforms, clipper profiles, and campaigns."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

PlatformModelType = Literal["open_marketplace", "managed_agency", "native_program"]
PlatformStatusType = Literal["active", "inactive", "unverified"]
ContentType = Literal["clipping", "ugc", "both"]
SocialPlatform = str  # Normalized lowercase: "tiktok", "reels", "shorts", "x"


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_social(value: str) -> str:
    """Normalize social network aliases into canonical lowercase identifiers."""
    cleaned = value.strip().lower()
    aliases = {
        "instagram": "reels",
        "ig": "reels",
        "instagram_reels": "reels",
        "ig_reels": "reels",
        "youtube": "shorts",
        "yt": "shorts",
        "youtube_shorts": "shorts",
        "yt_shorts": "shorts",
        "twitter": "x",
        "tt": "tiktok",
    }
    return aliases.get(cleaned, cleaned)


class PlatformRecord(BaseModel):
    """Verified clipping platform entry in data/platforms.json (Stage 0)."""

    id: str = Field(..., min_length=1, description="Unique lowercase snake_case identifier")
    name: str = Field(..., min_length=1, description="Human-readable platform name")
    url: str = Field(..., min_length=8, description="Canonical platform or campaign marketplace URL")
    model: PlatformModelType = Field(..., description="Marketplace model classification")
    status: PlatformStatusType = Field(..., description="Current verification status")
    free_to_join: bool = Field(..., description="True only if clippers never pay to join or view briefs")
    typical_rpm_range: str = Field(..., description="Typical RPM range string, e.g. '$1.00-$3.00'")
    payout_methods: list[str] = Field(default_factory=list, description="Supported payout rails")
    supported_socials: list[str] = Field(default_factory=list, description="Supported short-form socials")
    adapter_implemented: bool = Field(default=False, description="Whether a working scraper adapter exists")
    trust_notes: str = Field(default="", description="Verification context, fee notes, or shutdown reason")
    last_verified: str = Field(default_factory=utc_now_iso, description="ISO-8601 UTC timestamp")

    @field_validator("supported_socials", mode="before")
    @classmethod
    def _normalize_socials(cls, values: list[str]) -> list[str]:
        return [normalize_social(v) for v in (values or [])]

    @property
    def is_trusted_active(self) -> bool:
        """True only when active AND free to join (excludes scams/paywalled groups/dead sites)."""
        return self.status == "active" and self.free_to_join


class Campaign(BaseModel):
    """Normalized clipping campaign schema across all platform adapters (Stage 2)."""

    id: str = Field(..., min_length=1, description="Deterministic unique campaign ID (e.g. 'whop:camp_123')")
    platform: str = Field(..., min_length=1, description="Platform ID matching data/platforms.json")
    title: str = Field(..., min_length=1, description="Campaign title")
    creator_or_brand: str = Field(..., min_length=1, description="Sponsoring creator, streamer, or brand")
    url: str = Field(..., min_length=8, description="Direct clickable campaign URL")
    rpm_usd: float = Field(..., ge=0.0, description="Gross payout per 1,000 verified views in USD")
    platform_fee_pct: float = Field(default=0.0, ge=0.0, le=100.0, description="Platform fee percentage (0-100)")
    effective_rpm_usd: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Net payout per 1,000 views after platform fees",
    )
    total_budget_usd: Optional[float] = Field(default=None, ge=0.0, description="Total campaign pool in USD")
    remaining_budget_usd: Optional[float] = Field(default=None, ge=0.0, description="Remaining unspent pool in USD")
    min_payout_usd: Optional[float] = Field(default=None, ge=0.0, description="Minimum earnings threshold to cash out")
    max_payout_per_clip_usd: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Maximum payout cap for a single clip",
    )
    allowed_socials: list[str] = Field(default_factory=list, description="Allowed social networks for submissions")
    content_type: ContentType = Field(default="clipping", description="clipping, ugc, or both")
    niches: list[str] = Field(default_factory=list, description="Normalized lowercase niche tags")
    requirements_summary: str = Field(
        default="",
        description="Concise brief rules, required tags/watermarks, and rejection traps",
    )
    scraped_at: str = Field(default_factory=utc_now_iso, description="ISO-8601 UTC scrape timestamp")

    @field_validator("allowed_socials", mode="before")
    @classmethod
    def _normalize_allowed_socials(cls, values: list[str]) -> list[str]:
        seen: list[str] = []
        for raw in values or []:
            norm = normalize_social(raw)
            if norm and norm not in seen:
                seen.append(norm)
        return seen

    @field_validator("niches", mode="before")
    @classmethod
    def _normalize_niches(cls, values: list[str]) -> list[str]:
        seen: list[str] = []
        for raw in values or []:
            norm = str(raw).strip().lower()
            if norm and norm not in seen:
                seen.append(norm)
        return seen

    @model_validator(mode="after")
    def _compute_effective_rpm(self) -> "Campaign":
        computed = round(self.rpm_usd * (1.0 - self.platform_fee_pct / 100.0), 4)
        if self.effective_rpm_usd is None:
            self.effective_rpm_usd = computed
        if (
            self.total_budget_usd is not None
            and self.remaining_budget_usd is not None
            and self.remaining_budget_usd > self.total_budget_usd
        ):
            self.total_budget_usd = self.remaining_budget_usd
        return self


class ClipperProfile(BaseModel):
    """Clipper onboarding preferences stored in profile.json (Stage 1)."""

    allowed_socials: list[str] = Field(
        default_factory=lambda: ["tiktok", "reels", "shorts"],
        description="Social channels the clipper posts to",
    )
    content_type: ContentType = Field(
        default="clipping",
        description="Preferred campaign format: 'clipping', 'ugc', or 'both'",
    )
    min_rpm_usd: float = Field(default=0.5, ge=0.0, description="Minimum effective net RPM in USD")
    min_budget_remaining_usd: float = Field(
        default=100.0,
        ge=0.0,
        description="Minimum remaining campaign budget in USD",
    )
    preferred_niches: list[str] = Field(default_factory=list, description="Preferred content niches")
    exclude_niches: list[str] = Field(default_factory=list, description="Excluded content niches")
    platforms: list[str] = Field(
        default_factory=list,
        description="Specific platform IDs to check (empty list = all active trusted platforms)",
    )

    @field_validator("allowed_socials", mode="before")
    @classmethod
    def _norm_socials(cls, values: list[str]) -> list[str]:
        return [normalize_social(v) for v in (values or []) if str(v).strip()]

    @field_validator("preferred_niches", "exclude_niches", "platforms", mode="before")
    @classmethod
    def _norm_lower_list(cls, values: list[str]) -> list[str]:
        out: list[str] = []
        for raw in values or []:
            cleaned = str(raw).strip().lower()
            if cleaned and cleaned not in out:
                out.append(cleaned)
        return out


class RankedCampaign(BaseModel):
    """Campaign annotated with its deterministic Real Value Score (0-100) for Stage 3 output."""

    rank: int = Field(..., ge=1)
    real_value_score: float = Field(..., ge=0.0, le=100.0)
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    campaign: Campaign

    def to_compact_dict(self) -> dict:
        """Low-token dictionary (~45-50 tokens per campaign) optimized for AI agent consumption."""
        c = self.campaign
        return {
            "rank": self.rank,
            "score": round(self.real_value_score, 1),
            "id": c.id,
            "platform": c.platform,
            "title": c.title,
            "creator_or_brand": c.creator_or_brand,
            "url": c.url,
            "effective_rpm_usd": round(c.effective_rpm_usd or 0.0, 2),
            "gross_rpm_usd": round(c.rpm_usd, 2),
            "fee_pct": c.platform_fee_pct,
            "remaining_budget_usd": c.remaining_budget_usd,
            "total_budget_usd": c.total_budget_usd,
            "min_payout_usd": c.min_payout_usd,
            "max_payout_per_clip_usd": c.max_payout_per_clip_usd,
            "allowed_socials": c.allowed_socials,
            "content_type": c.content_type,
            "niches": c.niches,
            "requirements_summary": c.requirements_summary,
        }
