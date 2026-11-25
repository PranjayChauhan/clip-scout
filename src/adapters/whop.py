"""Working reference adapter for Whop Content Rewards (platform_id='whop')."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from src.adapters.base import BaseAdapter
from src.schema import Campaign, utc_now_iso

WHOP_DISCOVER_URL = "https://whop.com/content-rewards/"
WHOP_API_CANDIDATE_URL = "https://whop.com/api/graphql/fetchContentRewardsCampaigns"
NEXT_DATA_RE = re.compile(
    r'<script[^>]+id="__NEXT_DATA__"[^>]*>(?P<payload>.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


class WhopAdapter(BaseAdapter):
    """
    Whop Content Rewards adapter.

    Strategy:
    1. If `fixture_path` is provided, parse deterministic fixture JSON (used in CI/offline mode).
    2. Otherwise attempt lightweight HTTP fetch against Whop's public discovery page and
       extract embedded JSON campaign records (`__NEXT_DATA__` / JSON state) without burning
       any LLM tokens.
    """

    platform_id = "whop"
    platform_name = "Whop Content Rewards"
    default_fee_pct = 10.0
    rate_limit_seconds = 0.5
    is_stub = False

    def fetch_campaigns(self) -> list[Campaign]:
        raw_items = self._load_raw_items()
        scraped_at = utc_now_iso()
        campaigns: list[Campaign] = []
        for item in raw_items:
            parsed = self.normalize_item(item, scraped_at=scraped_at)
            if parsed is not None:
                campaigns.append(parsed)
        return campaigns

    def _load_raw_items(self) -> list[dict[str, Any]]:
        if self.fixture_path is not None:
            data = json.loads(Path(self.fixture_path).read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return list(data.get("campaigns") or data.get("items") or data.get("nodes") or [])
            if isinstance(data, list):
                return data
            return []

        resp = self.http_get(WHOP_DISCOVER_URL)
        content_type = resp.headers.get("content-type", "").lower()
        if "application/json" in content_type:
            payload = resp.json()
            return self._extract_campaign_dicts(payload)

        return self._extract_from_html(resp.text)

    @classmethod
    def _extract_from_html(cls, html: str) -> list[dict[str, Any]]:
        match = NEXT_DATA_RE.search(html or "")
        if not match:
            return []
        try:
            payload = json.loads(match.group("payload"))
        except json.JSONDecodeError:
            return []
        return cls._extract_campaign_dicts(payload)

    @classmethod
    def _extract_campaign_dicts(cls, node: Any) -> list[dict[str, Any]]:
        """Recursively locate campaign-like dict objects inside JSON/Next.js trees."""
        found: list[dict[str, Any]] = []

        def _walk(obj: Any) -> None:
            if isinstance(obj, dict):
                has_rpm = any(k in obj for k in ("rpm_usd", "rpm", "cpm", "rewardPerThousandViews", "rate_per_1k"))
                has_title = any(k in obj for k in ("title", "name", "campaignName"))
                if has_rpm and has_title:
                    found.append(obj)
                    return
                for val in obj.values():
                    _walk(val)
            elif isinstance(obj, list):
                for elem in obj:
                    _walk(elem)

        _walk(node)
        return found

    def normalize_item(self, raw: dict[str, Any], scraped_at: str | None = None) -> Campaign | None:
        """Normalize a raw Whop Content Rewards dictionary into the canonical Campaign schema."""
        raw_id = str(raw.get("id") or raw.get("slug") or "").strip()
        title = str(raw.get("title") or raw.get("name") or raw.get("campaignName") or "").strip()
        if not raw_id or not title:
            return None

        campaign_id = raw_id if raw_id.startswith("whop:") else f"whop:{raw_id}"
        creator = str(
            raw.get("creator_or_brand")
            or raw.get("creator")
            or raw.get("brand")
            or raw.get("companyName")
            or title
        ).strip()

        slug_or_url = str(raw.get("url") or raw.get("route") or raw.get("slug") or raw_id).strip()
        if slug_or_url.startswith("http://") or slug_or_url.startswith("https://"):
            url = slug_or_url
        else:
            clean_slug = slug_or_url.lstrip("/")
            url = f"https://whop.com/content-rewards/{clean_slug}"

        rpm_val = (
            raw.get("rpm_usd")
            if raw.get("rpm_usd") is not None
            else raw.get("rpm")
            if raw.get("rpm") is not None
            else raw.get("cpm")
            if raw.get("cpm") is not None
            else raw.get("rewardPerThousandViews", 0.0)
        )
        rpm_usd = float(rpm_val or 0.0)
        if rpm_usd <= 0:
            return None

        fee_pct = float(raw.get("platform_fee_pct", self.default_fee_pct))

        total_budget = raw.get("total_budget_usd", raw.get("totalBudget", raw.get("budgetPool")))
        remaining_budget = raw.get("remaining_budget_usd", raw.get("remainingBudget"))
        if remaining_budget is None and total_budget is not None and raw.get("spentBudget") is not None:
            remaining_budget = max(0.0, float(total_budget) - float(raw["spentBudget"]))

        min_payout = raw.get("min_payout_usd", raw.get("minPayout", raw.get("minimumPayout")))
        max_payout = raw.get(
            "max_payout_per_clip_usd",
            raw.get("maxPayoutPerClip", raw.get("maxPayout")),
        )

        socials = raw.get("allowed_socials") or raw.get("platforms") or ["tiktok", "reels", "shorts"]
        raw_ct = str(raw.get("content_type") or raw.get("categoryType") or "clipping").strip().lower()
        content_type = raw_ct if raw_ct in ("clipping", "ugc", "both") else "clipping"

        niches = raw.get("niches") or raw.get("tags") or []
        if isinstance(niches, str):
            niches = [n.strip() for n in niches.split(",") if n.strip()]

        requirements = str(
            raw.get("requirements_summary")
            or raw.get("requirements")
            or raw.get("rules")
            or "Follow campaign brief; authentic organic views only."
        ).strip()

        return Campaign(
            id=campaign_id,
            platform=self.platform_id,
            title=title,
            creator_or_brand=creator,
            url=url,
            rpm_usd=rpm_usd,
            platform_fee_pct=fee_pct,
            total_budget_usd=float(total_budget) if total_budget is not None else None,
            remaining_budget_usd=float(remaining_budget) if remaining_budget is not None else None,
            min_payout_usd=float(min_payout) if min_payout is not None else None,
            max_payout_per_clip_usd=float(max_payout) if max_payout is not None else None,
            allowed_socials=list(socials),
            content_type=content_type,  # type: ignore[arg-type]
            niches=list(niches),
            requirements_summary=requirements,
            scraped_at=scraped_at or utc_now_iso(),
        )
