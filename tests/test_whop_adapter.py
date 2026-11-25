"""Unit tests for Whop reference adapter, Next.js extraction, and fault isolation."""

import json
from pathlib import Path

import httpx

from src.adapters.base import BaseAdapter
from src.adapters.whop import WhopAdapter
from src.schema import Campaign

FIXTURE_FILE = Path(__file__).resolve().parent / "fixtures" / "whop_campaigns.json"


def test_whop_adapter_normalizes_fixture_campaigns() -> None:
    adapter = WhopAdapter(fixture_path=FIXTURE_FILE)
    res = adapter.safe_fetch()

    assert res.status == "ok"
    assert len(res.campaigns) == 12

    by_id = {c.id: c for c in res.campaigns}
    cursor = by_id["whop:cr_cursor_ai_launch"]
    assert cursor.rpm_usd == 3.5
    assert cursor.platform_fee_pct == 10.0
    assert cursor.effective_rpm_usd == 3.15
    assert cursor.url == "https://whop.com/content-rewards/cursor-ai-launch"
    assert "x" in cursor.allowed_socials


def test_whop_adapter_extracts_embedded_next_data() -> None:
    embedded = {
        "props": {
            "pageProps": {
                "campaigns": [
                    {
                        "id": "live_camp_99",
                        "title": "Live Embedded Campaign",
                        "companyName": "Acme Streamers",
                        "slug": "acme-streamers",
                        "rewardPerThousandViews": 2.0,
                        "totalBudget": 10000,
                        "spentBudget": 2500,
                        "minPayout": 10,
                        "maxPayoutPerClip": 1000,
                        "platforms": ["tiktok", "shorts"],
                        "rules": "Tag @acme",
                    }
                ]
            }
        }
    }
    html = f'<html><body><script id="__NEXT_DATA__" type="application/json">{json.dumps(embedded)}</script></body></html>'
    client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, text=html)))

    adapter = WhopAdapter(http_client=client, timeout_seconds=5.0)
    adapter.rate_limit_seconds = 0.0
    campaigns = adapter.fetch_campaigns()

    assert len(campaigns) == 1
    assert campaigns[0].id == "whop:live_camp_99"
    assert campaigns[0].effective_rpm_usd == 1.8
    assert campaigns[0].remaining_budget_usd == 7500.0


def test_broken_adapter_never_crashes_safe_fetch() -> None:
    class BrokenAdapter(BaseAdapter):
        platform_id = "broken"
        platform_name = "Broken Site"

        def fetch_campaigns(self) -> list[Campaign]:
            raise RuntimeError("Layout changed unexpectedly")

    res = BrokenAdapter().safe_fetch()
    assert res.status == "error"
    assert res.campaigns == []
    assert "RuntimeError" in res.message
