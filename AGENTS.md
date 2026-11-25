# AGENTS.md — `clip-scout` Operating Rules

This repository powers a **zero-token-burn, self-verifying clipping campaign discovery engine** compatible with Google Antigravity, Claude Code, Gemini CLI, OpenAI Codex, Cursor, and VS Code.

## Core Architectural Guarantee — Never Trust Stale Companies

A user may clone `clip-scout` months or years after a commit. Companies in the clipping space frequently launch, pivot to SaaS-only tools, pause creator payouts, or shut down completely.

- **Stage 0 MUST run first** on every fresh clone (when `.clipscout_verified` is absent) or whenever `data/platforms.json` is > 7 days old.
- `clipscout discover` (and `ensure_fresh_trusted_registry()`) independently searches live web feeds for new clipping marketplaces AND inspects live page content on every registered platform to confirm active per-view/campaign operations—automatically downgrading dead, pivoted, SaaS-only, or pay-to-join sites to `status: "inactive"` **before** Stage 1–3 execute.

## Mandatory Zero-Token Policy for Campaign Checks

1. **No Raw LLM Web Browsing for Routine Campaign Lookups:**
   Never launch a browser subagent or dump raw marketplace HTML into LLM context to browse campaigns when `clipscout` CLI or `mcp/server.py` can answer deterministically.
2. **Strict 4-Stage Execution (`.agents/skills/clip-scout/SKILL.md`):**
   - **Stage 0 (`clipscout discover` / `discover_platforms`):** Independent web search + live campaign-activity verification on initial clone and weekly schedule.
   - **Stage 1 (`clipscout init` / `save_profile`):** 5-question clipper intake showing **only** currently active, free-to-join verified platforms.
   - **Stage 2 (`clipscout scrape` / `refresh_campaigns`):** Deterministic Python adapters for active trusted platforms matching `profile.json`.
   - **Stage 3 (`clipscout top --format json` / `get_top_campaigns`):** Compact Top 10 JSON (~500 tokens max), automatically excluding any platform marked `inactive`.
