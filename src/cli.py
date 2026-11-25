"""Interactive intake & zero-token CLI (`clipscout`) for clip-scout."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from src.adapters import scrape_active_campaigns
from src.discovery import (
    DEFAULT_PLATFORMS_PATH,
    ensure_fresh_trusted_registry,
    get_active_trusted_platforms,
    run_discovery,
)
from src.ranker import (
    DEFAULT_CAMPAIGNS_PATH,
    load_campaigns,
    rank_campaigns,
    save_campaigns,
)
from src.schema import ClipperProfile, RankedCampaign

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROFILE_PATH = REPO_ROOT / "profile.json"

app = typer.Typer(
    name="clipscout",
    help="Zero-token-burn clipping campaign discovery engine & ranker.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console(stderr=True)
stdout_console = Console()


def _split_csv(raw: str) -> list[str]:
    if not raw or not raw.strip():
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def load_profile_or_default(profile_path: Optional[Path]) -> ClipperProfile:
    if profile_path and profile_path.exists():
        raw = json.loads(profile_path.read_text(encoding="utf-8"))
        return ClipperProfile.model_validate(raw)
    return ClipperProfile()


def _format_money(val: Optional[float]) -> str:
    if val is None:
        return "—"
    if val >= 1000 and float(val).is_integer():
        return f"${int(val):,}"
    if float(val).is_integer():
        return f"${int(val)}"
    return f"${val:,.2f}"


def render_markdown_top(ranked: list[RankedCampaign]) -> str:
    """Render ranked campaigns as a rich GitHub-flavored Markdown table + Top 3 notes."""
    if not ranked:
        return "_No matching campaigns found for the current profile constraints._\n"

    lines: list[str] = [
        "| # | Score | Campaign | Platform | Net RPM | Remaining Budget | Min / Max Cap | Socials |",
        "|---:|---:|---|---|---:|---:|---|---|",
    ]
    for item in ranked:
        c = item.campaign
        net_rpm = f"${(c.effective_rpm_usd or c.rpm_usd):.2f}"
        rem_str = _format_money(c.remaining_budget_usd)
        if c.remaining_budget_usd is not None and c.total_budget_usd:
            pct = int(round((c.remaining_budget_usd / c.total_budget_usd) * 100))
            rem_str = f"{rem_str} ({pct}%)"
        cap_str = f"{_format_money(c.min_payout_usd)} / {_format_money(c.max_payout_per_clip_usd)}"
        socials_str = ", ".join(c.allowed_socials)
        link_md = f"[{c.title}]({c.url}) — *{c.creator_or_brand}*"
        lines.append(
            f"| {item.rank} | **{item.real_value_score:.1f}** | {link_md} | `{c.platform}` | "
            f"**{net_rpm}** | {rem_str} | {cap_str} | {socials_str} |"
        )

    lines.append("")
    lines.append("### Top 3 Actionable Brief Notes & Rejection Traps")
    for item in ranked[:3]:
        c = item.campaign
        lines.append(
            f"{item.rank}. **[{c.title}]({c.url})** (`{c.platform}`, "
            f"${(c.effective_rpm_usd or c.rpm_usd):.2f}/1K net, "
            f"socials: `{', '.join(c.allowed_socials)}`): {c.requirements_summary}"
        )
    return "\n".join(lines) + "\n"


def render_compact_json_top(ranked: list[RankedCampaign]) -> str:
    """Render ultra-compact JSON (~450-500 tokens max for Top 10) for Stage 3 AI consumption."""
    compact_rows = []
    for item in ranked:
        c = item.campaign
        max_rule_len = 110 if item.rank <= 3 else 52
        rules_short = (
            c.requirements_summary[: max_rule_len - 3].rstrip() + "..."
            if len(c.requirements_summary) > max_rule_len
            else c.requirements_summary
        )
        compact_rows.append(
            {
                "rank": item.rank,
                "score": round(item.real_value_score, 1),
                "plat": c.platform,
                "title": c.title,
                "brand": c.creator_or_brand,
                "url": c.url,
                "rpm": round(c.effective_rpm_usd or c.rpm_usd, 2),
                "rem": int(c.remaining_budget_usd) if c.remaining_budget_usd is not None else None,
                "min": int(c.min_payout_usd) if c.min_payout_usd is not None else None,
                "cap": int(c.max_payout_per_clip_usd) if c.max_payout_per_clip_usd is not None else None,
                "soc": c.allowed_socials,
                "rules": rules_short,
            }
        )
    return json.dumps({"top": compact_rows}, separators=(",", ":"), ensure_ascii=False)


@app.command("discover")
def cmd_discover(
    platforms_path: Path = typer.Option(
        DEFAULT_PLATFORMS_PATH,
        "--platforms-path",
        help="Path to data/platforms.json registry.",
    ),
    offline: bool = typer.Option(
        False,
        "--offline",
        help="Skip live HTTP URL checks & web search (for deterministic offline unit tests).",
    ),
    web_search: bool = typer.Option(
        True,
        "--web-search/--no-web-search",
        help="Independently search the live web for newly launched clipping marketplaces.",
    ),
    output_format: str = typer.Option(
        "table",
        "--format",
        help="Output format: 'table' or 'json'.",
    ),
) -> None:
    """Stage 0: Independently search & live-audit active clipping platforms in data/platforms.json."""
    records, diff = run_discovery(
        platforms_path=platforms_path,
        check_live=not offline,
        web_search=(web_search and not offline),
    )

    if output_format.lower() == "json":
        typer.echo(
            json.dumps(
                {
                    "diff": diff.to_dict(),
                    "platforms": [r.model_dump(mode="json") for r in records],
                },
                indent=2,
            )
        )
        return

    table = Table(title=f"Verified Clipping Platform Registry ({diff.active_trusted_count} active & trusted)")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Name", style="bold")
    table.add_column("Status")
    table.add_column("Free")
    table.add_column("Model")
    table.add_column("RPM Range")
    table.add_column("Adapter")

    for r in records:
        status_label = "[green]active[/green]" if r.is_trusted_active else f"[red]{r.status}[/red]"
        adapter_label = "[green]ready[/green]" if r.adapter_implemented else "[yellow]stub[/yellow]"
        table.add_row(
            r.id,
            r.name,
            status_label,
            "yes" if r.free_to_join else "no",
            r.model,
            r.typical_rpm_range,
            adapter_label,
        )

    stdout_console.print(table)
    stdout_console.print(
        f"Diff — web_checked={diff.web_candidates_checked}, "
        f"newly_discovered={diff.newly_discovered or 'none'}, "
        f"reactivated={diff.reactivated or 'none'}, "
        f"marked_inactive={diff.marked_inactive or 'none'}, "
        f"excluded={diff.excluded_untrusted or 'none'}"
    )


@app.command("init")
def cmd_init(
    profile_path: Path = typer.Option(
        DEFAULT_PROFILE_PATH,
        "--profile",
        "-p",
        help="Where to write profile.json.",
    ),
    platforms_path: Path = typer.Option(
        DEFAULT_PLATFORMS_PATH,
        "--platforms-path",
        help="Path to data/platforms.json.",
    ),
) -> None:
    """Stage 1: Auto-runs Stage 0 live verification if stale/unverified, then asks 5 intake questions."""
    trusted, auto_diff = ensure_fresh_trusted_registry(platforms_path=platforms_path)
    if auto_diff is not None:
        stdout_console.print(
            f"[dim]Stage 0 live audit completed automatically: "
            f"{auto_diff.active_trusted_count} active trusted platforms verified.[/dim]"
        )

    trusted_ids = [p.id for p in trusted]
    stdout_console.print(
        f"[bold cyan]clip-scout Onboarding (5 quick questions)[/bold cyan]\n"
        f"Live-verified trusted platforms: [green]{', '.join(trusted_ids) or 'none'}[/green]\n"
    )

    q1_socials = typer.prompt(
        "1/5 Target social platforms (comma-separated: tiktok, reels, shorts, x)",
        default="tiktok,reels,shorts",
    )
    q2_type = typer.prompt(
        "2/5 Campaign content type (clipping / ugc / both)",
        default="clipping",
    ).strip().lower()
    if q2_type not in ("clipping", "ugc", "both"):
        q2_type = "clipping"

    q3_thresholds = typer.prompt(
        "3/5 Minimum net RPM ($) and minimum remaining budget ($), separated by comma",
        default="1.0,500",
    )
    parts = [p.strip().lstrip("$") for p in q3_thresholds.split(",") if p.strip()]
    min_rpm = float(parts[0]) if len(parts) >= 1 else 1.0
    min_budget = float(parts[1]) if len(parts) >= 2 else 500.0

    q4_niches = typer.prompt(
        "4/5 Preferred niches | Excluded niches (format: gaming,tech | casino,gambling)",
        default="gaming,streamers,tech,podcasts | casino,gambling",
    )
    if "|" in q4_niches:
        pref_raw, excl_raw = q4_niches.split("|", 1)
    else:
        pref_raw, excl_raw = q4_niches, ""

    q5_platforms = typer.prompt(
        f"5/5 Preferred platforms from [{', '.join(trusted_ids)}] (leave blank for ALL active trusted)",
        default="",
        show_default=False,
    )

    profile = ClipperProfile(
        allowed_socials=_split_csv(q1_socials),
        content_type=q2_type,  # type: ignore[arg-type]
        min_rpm_usd=min_rpm,
        min_budget_remaining_usd=min_budget,
        preferred_niches=_split_csv(pref_raw),
        exclude_niches=_split_csv(excl_raw),
        platforms=_split_csv(q5_platforms),
    )

    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(
        json.dumps(profile.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    stdout_console.print(f"\n[green]Saved clipper profile to {profile_path}[/green]")


@app.command("scrape")
def cmd_scrape(
    profile_path: Path = typer.Option(
        DEFAULT_PROFILE_PATH,
        "--profile",
        "-p",
        help="Path to profile.json.",
    ),
    platforms_path: Path = typer.Option(
        DEFAULT_PLATFORMS_PATH,
        "--platforms-path",
        help="Path to data/platforms.json.",
    ),
    output_path: Path = typer.Option(
        DEFAULT_CAMPAIGNS_PATH,
        "--output",
        "-o",
        help="Where to write normalized campaigns JSON.",
    ),
    fixture: Optional[Path] = typer.Option(
        None,
        "--fixture",
        help="Optional fixture JSON path for deterministic offline/CI testing.",
    ),
) -> None:
    """Stage 2: Ensure Stage 0 registry is fresh, then run active trusted adapters -> data/campaigns.json."""
    if fixture is None:
        ensure_fresh_trusted_registry(platforms_path=platforms_path)

    profile = load_profile_or_default(profile_path)
    campaigns, results = scrape_active_campaigns(
        profile=profile,
        platforms_path=platforms_path,
        fixture_path=fixture,
    )

    if campaigns or not output_path.exists():
        save_campaigns(campaigns, output_path)
        saved_note = f"saved {len(campaigns)} campaigns -> {output_path}"
    else:
        saved_note = (
            f"live adapters returned 0 campaigns; preserved existing cache at {output_path}"
        )

    summary = [f"{r.platform_id}:{r.status}({len(r.campaigns)})" for r in results]
    typer.echo(f"Scrape complete [{', '.join(summary) or 'no-adapters'}] — {saved_note}")


@app.command("top")
def cmd_top(
    profile_path: Path = typer.Option(
        DEFAULT_PROFILE_PATH,
        "--profile",
        "-p",
        help="Path to profile.json.",
    ),
    platforms_path: Path = typer.Option(
        DEFAULT_PLATFORMS_PATH,
        "--platforms-path",
        help="Path to data/platforms.json (excludes any platform marked inactive).",
    ),
    campaigns_path: Path = typer.Option(
        DEFAULT_CAMPAIGNS_PATH,
        "--campaigns-path",
        help="Path to data/campaigns.json.",
    ),
    limit: int = typer.Option(
        10,
        "--limit",
        "-n",
        min=1,
        max=50,
        help="Number of top campaigns to return.",
    ),
    output_format: str = typer.Option(
        "markdown",
        "--format",
        "-f",
        help="Output format: 'json' (compact ~500 tokens for AI agents) or 'markdown'.",
    ),
) -> None:
    """Stage 3: Filter out inactive platforms, rank by Real Value Score (0-100), and output Top N."""
    profile = load_profile_or_default(profile_path)
    active_trusted_ids = {p.id for p in get_active_trusted_platforms(platforms_path)}
    campaigns = load_campaigns(campaigns_path)
    if active_trusted_ids:
        campaigns = [c for c in campaigns if c.platform in active_trusted_ids]

    ranked = rank_campaigns(campaigns, profile=profile, limit=limit)

    fmt = output_format.strip().lower()
    if fmt == "json":
        typer.echo(render_compact_json_top(ranked))
    elif fmt in ("markdown", "md"):
        typer.echo(render_markdown_top(ranked), nl=False)
    else:
        raise typer.BadParameter("Expected --format to be 'json' or 'markdown'.")


if __name__ == "__main__":
    app()
