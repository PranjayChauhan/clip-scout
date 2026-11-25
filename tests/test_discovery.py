"""Unit tests for Stage 0 independent web discovery, activity gate, and zombie/scam exclusion."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from src.discovery import (
    DEFAULT_PLATFORMS_PATH,
    get_active_trusted_platforms,
    is_registry_stale,
    load_platforms,
    run_discovery,
)


def test_default_platforms_registry_valid_and_excludes_clipaffiliates() -> None:
    all_platforms = load_platforms(DEFAULT_PLATFORMS_PATH)
    active_trusted = get_active_trusted_platforms(DEFAULT_PLATFORMS_PATH)

    ids_all = {p.id for p in all_platforms}
    ids_active = {p.id for p in active_trusted}

    assert "whop" in ids_active
    assert "clipaffiliates" in ids_all
    assert "clipaffiliates" not in ids_active


def test_registry_staleness_and_fresh_clone_sentinel(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    assert is_registry_stale(missing) is True

    target = tmp_path / "platforms.json"
    sentinel = tmp_path / ".clipscout_verified"
    run_discovery(platforms_path=target, check_live=False)

    # Without sentinel when require_local_verification=True -> treated as fresh clone (stale!)
    assert is_registry_stale(target, require_local_verification=True, sentinel_path=sentinel) is True

    sentinel.write_text("2026-11-25T14:00:00Z\n", encoding="utf-8")
    assert is_registry_stale(target, require_local_verification=True, sentinel_path=sentinel) is False

    future = datetime.now(timezone.utc) + timedelta(days=8)
    assert is_registry_stale(target, max_age_days=7, now=future) is True


def test_discovery_catches_zombie_pivot_shutdown_and_discovers_new_web_platform(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        host = request.url.host or ""

        # Simulated Bing RSS / Yahoo web search returning a real new marketplace + a SaaS editor + a spam blog
        if "bing.com" in host or "yahoo.com" in host:
            rss = """
            <rss><channel>
              <item><link>https://nextgenclips.example/campaigns</link></item>
              <item><link>https://aislicer-saas.example/</link></item>
              <item><link>https://spamlisticle.example/</link></item>
            </channel></rss>
            """
            return httpx.Response(200, text=rss)

        if "nextgenclips.example" in host:
            return httpx.Response(
                200,
                text=(
                    "<html><head><title>NextGenClips | Creator Clipping Marketplace</title></head>"
                    "<body>Browse live campaigns and get paid $2.50 per 1,000 verified views.</body></html>"
                ),
            )
        if "aislicer-saas.example" in host:
            # Pure AI video cutter tool with NO campaigns or payouts
            return httpx.Response(
                200,
                text="<html><head><title>AISlicer</title></head><body>AI video clip maker $29/mo subscription.</body></html>",
            )
        if "spamlisticle.example" in host:
            return httpx.Response(
                200,
                text="<html><body>Best Creator, Sales And Side-Hustle Communities — enroll now for $99</body></html>",
            )
        if "vyro.com" in host:
            # Simulate future scenario where Vyro pivots to enterprise analytics & stops offering clipper campaigns!
            return httpx.Response(
                200,
                text="<html><head><title>Vyro Enterprise Analytics</title></head><body>B2B brand dashboard software.</body></html>",
            )
        if "deadclipper.example" in host:
            return httpx.Response(404, text="Not Found")
        if "shutdownboard.example" in host:
            return httpx.Response(
                200,
                text="<html><body>Thank you clippers — our platform has shut down and paused all campaigns indefinitely.</body></html>",
            )
        if "parked.example" in host:
            return httpx.Response(200, text="<html>This domain is for sale on SedoParking</html>")

        # Healthy active clipping platforms
        return httpx.Response(
            200,
            text=(
                "<html><head><title>Active Clipping Platform</title></head>"
                "<body>Join creator clipping campaigns and earn CPM payouts per 1,000 views.</body></html>"
            ),
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    candidates = [
        {
            "id": "dead_board",
            "name": "Dead Board",
            "url": "https://deadclipper.example",
            "model": "open_marketplace",
            "status": "active",
            "free_to_join": True,
            "typical_rpm_range": "$1-$2",
        },
        {
            "id": "shutdown_board",
            "name": "Shutdown Board",
            "url": "https://shutdownboard.example",
            "model": "open_marketplace",
            "status": "active",
            "free_to_join": True,
            "typical_rpm_range": "$1-$2",
        },
        {
            "id": "paid_discord_scam",
            "name": "Paid Discord Course",
            "url": "https://paidcourse.example",
            "model": "managed_agency",
            "status": "active",
            "free_to_join": False,
            "typical_rpm_range": "$2-$5",
        },
    ]

    reg_file = tmp_path / "platforms.json"
    records, diff = run_discovery(
        platforms_path=reg_file,
        check_live=True,
        web_search=True,
        candidates=candidates,
        http_client=client,
    )
    by_id = {r.id: r for r in records}

    # Newly launched clipping marketplace discovered independently from web search!
    assert "nextgenclips_example" in by_id
    assert by_id["nextgenclips_example"].is_trusted_active is True
    assert by_id["nextgenclips_example"].name == "NextGenClips"
    assert "nextgenclips_example" in diff.newly_discovered

    # Pure SaaS AI editor & $99 spam listicle from web search were rejected and NOT added
    assert "aislicer_saas_example" not in by_id
    assert "spamlisticle_example" not in by_id

    # Simulated future Vyro pivot (HTTP 200 but zero clipping/campaign payout signals) marked inactive!
    assert by_id["vyro"].status == "inactive"
    assert by_id["vyro"].is_trusted_active is False

    # Dead 404, explicit shutdown notice, and pay-to-join scam all marked inactive
    assert by_id["dead_board"].status == "inactive"
    assert by_id["shutdown_board"].status == "inactive"
    assert by_id["paid_discord_scam"].is_trusted_active is False
    assert "paid_discord_scam" in diff.excluded_untrusted
