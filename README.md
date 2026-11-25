# `clip-scout`

**Self-verifying, zero-token-burn clipping campaign discovery engine, CLI, FastMCP server, and universal AI Agent Skill.**

Short-form clippers waste hours checking multiple websites for high-RPM bounties—and naive AI agents burn **30,000–100,000+ tokens** opening browser tabs across marketplaces on every prompt. Worse, static "best clipping sites" repos go stale within months as startups pivot, freeze payouts, or shut down.

`clip-scout` solves both problems with a **future-proof 4-stage pipeline**:

1. **Stage 0 — Independent Web Discovery & Live Activity Gate (`data/platforms.json`):**
   On every fresh `git clone` (`.clipscout_verified` gate) and weekly thereafter, `clip-scout` independently searches live web feeds (zero API keys required) for new clipping marketplaces and **audits every platform's live pages for active per-view/campaign operations**. Any company that shuts down, pivots to a pure SaaS editor, parks its domain, or charges pay-to-join fees is automatically marked `inactive` and blocked from Stages 1–3.
2. **Stage 1 — 5-Question Clipper Intake (`profile.json`):**
   Asks 5 quick questions once—presenting **only** platforms verified active & trusted in Stage 0—and saves `profile.json`.
3. **Stage 2 — Deterministic Scraping & `Real Value Score` (`data/campaigns.json`):**
   Runs modular Python HTTP adapters only for active trusted platforms matching `profile.json` (or reads the hourly GitHub Actions feed) and scores every eligible campaign from `0–100`:
   - **45%** Effective Net RPM (after platform fees)
   - **30%** Remaining Budget Depth & `%` Unspent
   - **15%** Per-Clip Payout Cap Upside
   - **10%** Low Minimum Cashout Threshold
4. **Stage 3 — Rich Low-Token Output (~500 tokens max):**
   Hands only the compact Top 10 JSON to your AI agent (automatically excluding any platform marked `inactive`) with direct clickable URLs, net RPM, remaining budget, payout caps, allowed socials, and brief rejection traps.

---

## Quickstart

```bash
# 1. Install with uv (recommended)
uv sync --extra dev

# 2. Independently search & live-verify active clipping platforms (Stage 0)
uv run clipscout discover

# 3. Complete 5-question onboarding (auto-runs Stage 0 if unverified/stale)
uv run clipscout init

# 4. Scrape & view your ranked Top 10 (Stages 2 & 3)
uv run clipscout scrape --profile profile.json
uv run clipscout top --profile profile.json --limit 10 --format markdown
```

Preview deterministic ranking offline with the bundled Whop fixture:

```bash
uv run clipscout scrape --profile profile.example.json --fixture tests/fixtures/whop_campaigns.json
uv run clipscout top --profile profile.example.json --limit 10 --format markdown
```

---

## Universal AI Agent Compatibility

| Agent / IDE | Discovery Mechanism Included |
| :--- | :--- |
| **Google Antigravity / Gemini CLI / Codex / Cursor** | `.agents/skills/clip-scout/SKILL.md` + `AGENTS.md` |
| **Claude Code** | `.claude/skills/clip-scout/SKILL.md` + `CLAUDE.md` |
| **Any MCP Client (Claude Desktop, Cursor, VS Code, Antigravity)** | `mcp/server.py` (FastMCP server) |

### FastMCP Server Config

```json
{
  "mcpServers": {
    "clip-scout": {
      "command": "uv",
      "args": ["--directory", "/path/to/clip-scout", "run", "python", "mcp/server.py"]
    }
  }
}
```

Exposed tools: `list_trusted_platforms`, `discover_platforms`, `save_profile`, `refresh_campaigns`, `get_top_campaigns`.

---

## Contributing a Platform Adapter

1. Run `uv run clipscout discover` to confirm the target platform passes the Stage 0 live campaign-activity & free-to-join audit.
2. Implement `fetch_campaigns(self) -> list[Campaign]` in `src/adapters/<platform_id>.py` subclassing `BaseAdapter` (`is_stub = False`).
3. Add a deterministic JSON fixture under `tests/fixtures/` and tests under `tests/`.
4. Set `"adapter_implemented": true` in `data/platforms.json` and run `uv run pytest -v`.

## License

MIT
