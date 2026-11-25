"""End-to-end CLI tests for `clipscout discover`, `init`, `scrape`, and `top`."""

import json
from pathlib import Path

from typer.testing import CliRunner

from src.cli import app

runner = CliRunner()
FIXTURE_FILE = Path(__file__).resolve().parent / "fixtures" / "whop_campaigns.json"


def test_cli_full_4_stage_pipeline_and_token_budget(tmp_path: Path) -> None:
    platforms_file = tmp_path / "platforms.json"
    profile_file = tmp_path / "profile.json"
    campaigns_file = tmp_path / "campaigns.json"

    # Stage 0: discover --offline
    r0 = runner.invoke(app, ["discover", "--platforms-path", str(platforms_file), "--offline"])
    assert r0.exit_code == 0, r0.output
    assert platforms_file.exists()

    # Stage 1: init (5 interactive questions)
    user_answers = "\n".join(
        [
            "tiktok,reels,shorts",
            "clipping",
            "1.0,500",
            "gaming,tech,streamers | casino,gambling",
            "whop",
        ]
    ) + "\n"
    r1 = runner.invoke(
        app,
        ["init", "--profile", str(profile_file), "--platforms-path", str(platforms_file)],
        input=user_answers,
    )
    assert r1.exit_code == 0, r1.output
    saved_profile = json.loads(profile_file.read_text(encoding="utf-8"))
    assert saved_profile["exclude_niches"] == ["casino", "gambling"]

    # Stage 2: scrape with deterministic fixture
    r2 = runner.invoke(
        app,
        [
            "scrape",
            "--profile",
            str(profile_file),
            "--platforms-path",
            str(platforms_file),
            "--output",
            str(campaigns_file),
            "--fixture",
            str(FIXTURE_FILE),
        ],
    )
    assert r2.exit_code == 0, r2.output
    assert campaigns_file.exists()

    # Stage 3: top --format json (verify compact ~500-token payload)
    r3_json = runner.invoke(
        app,
        [
            "top",
            "--profile",
            str(profile_file),
            "--campaigns-path",
            str(campaigns_file),
            "--limit",
            "10",
            "--format",
            "json",
        ],
    )
    assert r3_json.exit_code == 0, r3_json.output
    payload = json.loads(r3_json.output)
    assert 1 <= len(payload["top"]) <= 10
    # Strict ~500-token Stage 3 budget check (~5 chars/token BPE -> < 3,000 chars for up to 10 items)
    assert len(r3_json.output) < 3000

    # Stage 3: top --format markdown
    r3_md = runner.invoke(
        app,
        [
            "top",
            "--profile",
            str(profile_file),
            "--campaigns-path",
            str(campaigns_file),
            "--limit",
            "10",
            "--format",
            "markdown",
        ],
    )
    assert r3_md.exit_code == 0, r3_md.output
    assert "Top 3 Actionable Brief Notes & Rejection Traps" in r3_md.output
    assert "https://whop.com/content-rewards/" in r3_md.output
