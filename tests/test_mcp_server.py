"""Unit tests for the FastMCP server tools (`mcp/server.py` / `src/mcp_app.py`)."""

import importlib.util
from pathlib import Path

from src.adapters.whop import WhopAdapter
from src.ranker import save_campaigns

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_FILE = Path(__file__).resolve().parent / "fixtures" / "whop_campaigns.json"


def _load_mcp_server_module():
    server_path = REPO_ROOT / "mcp" / "server.py"
    spec = importlib.util.spec_from_file_location("clip_scout_mcp_server", server_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_mcp_server_loads_without_shadowing_and_executes_tools(tmp_path: Path) -> None:
    mod = _load_mcp_server_module()
    assert mod.mcp.name == "clip-scout"

    platforms_file = tmp_path / "platforms.json"
    profile_file = tmp_path / "profile.json"
    campaigns_file = tmp_path / "campaigns.json"

    disc = mod.discover_platforms(check_live=False, platforms_path=str(platforms_file))
    assert "whop" in disc["active_platforms"]
    assert "clipaffiliates" not in disc["active_platforms"]

    listed = mod.list_trusted_platforms(include_inactive=False, platforms_path=str(platforms_file))
    assert listed["stale"] is False
    assert listed["count"] >= 7

    prof = mod.save_profile(
        allowed_socials=["tiktok", "shorts"],
        content_type="clipping",
        min_rpm_usd=1.0,
        min_budget_remaining_usd=500.0,
        preferred_niches=["gaming", "tech"],
        exclude_niches=["casino"],
        profile_path=str(profile_file),
    )
    assert Path(prof["saved_to"]).exists()

    seeded = WhopAdapter(fixture_path=FIXTURE_FILE).fetch_campaigns()
    save_campaigns(seeded, campaigns_file)

    refresh = mod.refresh_campaigns(
        profile_path=str(profile_file),
        platforms_path=str(platforms_file),
        campaigns_path=str(campaigns_file),
        force=False,
    )
    assert refresh["refreshed"] is False
    assert refresh["campaign_count"] == 12

    top = mod.get_top_campaigns(
        profile_path=str(profile_file),
        campaigns_path=str(campaigns_file),
        limit=5,
    )
    assert top["count"] == 5
    assert all(row["url"].startswith("https://") for row in top["top"])
