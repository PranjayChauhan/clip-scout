# CLAUDE.md — `clip-scout` Instructions for Claude Code

Read `AGENTS.md` and `.claude/skills/clip-scout/SKILL.md` before responding to any clipping campaign discovery or adapter request.

## Strict Rules

1. **Future-Proof Trust Gate First (Stage 0):**
   Never assume a hardcoded platform is still alive or offering clipper campaigns. On a fresh clone (`.clipscout_verified` missing) or if `data/platforms.json` is >7 days old, run `clipscout discover` (or MCP `discover_platforms(check_live=True, web_search=True)`) **first** so shut-down or pivoted companies (e.g., if a platform stops running campaigns in the future) are marked `inactive` and newly launched marketplaces are surfaced before onboarding or ranking.
2. **Zero Raw Browsing for Routine Campaign Checks:**
   Do NOT browse clipping sites directly in a browser to list campaigns. Use `clipscout` CLI (`init`, `scrape`, `top --format json`) or the `mcp/server.py` FastMCP tools (`list_trusted_platforms`, `discover_platforms`, `save_profile`, `refresh_campaigns`, `get_top_campaigns`).
