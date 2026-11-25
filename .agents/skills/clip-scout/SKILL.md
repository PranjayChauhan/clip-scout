---
name: clip-scout
description: Zero-token-burn clipping campaign discovery engine. Independently searches and verifies which clipping marketplaces are STILL alive, free-to-join, and actively running creator payout campaigns before onboarding the clipper or ranking Top 10 campaigns.
---

# clip-scout — Zero-Token Clipping Campaign Skill

Follow this strict **4-Step Protocol** whenever the user asks for clipping/UGC campaigns, best RPM bounties, or trusted clipping platforms.

> **WHY STEP 1 IS MANDATORY (FUTURE-PROOF TRUST GATE):**
> Clipping startups launch, pivot, freeze payouts, or shut down every few months. **Never blindly trust a static list in a cloned repo** (e.g., if a user clones `clip-scout` a year from now and a company like Vyro or Promote.fun has stopped offering clipper campaigns). You MUST complete Step 1 before proceeding to Steps 2–4.

---

## Step 1 — Independent Platform Discovery & Live Activity Audit (`Stage 0`)

1. Check if `.clipscout_verified` exists locally **AND** `data/platforms.json` has `last_verified` within the last **7 days** (or call MCP `list_trusted_platforms()` and check `"stale"`).
2. **Whenever `.clipscout_verified` is missing (first run after `git clone`), `data/platforms.json` is missing, OR `last_verified` > 7 days old — STOP and run Stage 0 FIRST:**
   - Run `clipscout discover` (or MCP `discover_platforms(check_live=True, web_search=True)`), which independently searches live web feeds for newly launched clipping marketplaces and audits every platform's live page for active per-view/campaign signals (automatically marking shut-down, pivoted, pure-SaaS-editor, or pay-to-join sites `inactive`).
   - If you have a lightweight `search_web` tool available during this initial/weekly Stage 0 audit, also run 1–2 quick web searches (e.g. `"active clipping campaign platforms pay per 1000 views"`, `"<platform> shut down OR scam OR stopped paying clippers"`) and pass any newly launched legitimate free-to-join portals into `discover_platforms(extra_candidates=[...])` so `data/platforms.json` reflects real-world ground truth **today**.
   - Once verified (<7 days old on this machine), skip Step 1 on subsequent routine queries to burn **zero extra tokens**.

---

## Step 2 — Clipper Intake (`Stage 1`)

1. Check if `profile.json` exists in the repository root.
2. If `profile.json` does **not** exist, ask the user these **5 intake questions in ONE concise message**, showing **ONLY** the platforms currently verified `"status": "active"` and `"free_to_join": true` from Step 1:
   1. **Target Socials:** Which platforms do you post to? (`tiktok`, `reels`, `shorts`, `x`)
   2. **Content Format:** Pure `clipping`, original `ugc`, or `both`?
   3. **Payout Floor:** Minimum net RPM ($/1K views) and minimum remaining campaign budget ($)? *(e.g., `$1.00` RPM, `$500` remaining)*
   4. **Niches:** Any preferred niches *(e.g., gaming, streamers, tech, podcasts)* or excluded niches *(e.g., casino, gambling)*?
   5. **Platforms:** Specific live-verified trusted platforms from `data/platforms.json` *(or all active trusted platforms)*?
3. Save `profile.json` (via `clipscout init` or MCP `save_profile(...)`).

---

## Step 3 — Zero-Token Scrape & Deterministic Filter (`Stage 2`)

1. **NEVER** open a headless browser across multiple clipping marketplaces to read campaigns into LLM context.
2. If `data/campaigns.json` is missing or older than **2 hours**, run:
   ```bash
   clipscout scrape --profile profile.json
   ```
   *(or call MCP `refresh_campaigns(profile_path="profile.json")`)*
3. Fetch the deterministically ranked Top 10 (~500 tokens max), which automatically excludes any platform marked `inactive` in `data/platforms.json`:
   ```bash
   clipscout top --profile profile.json --limit 10 --format json
   ```
   *(or call MCP `get_top_campaigns(profile_path="profile.json", limit=10)`)*

---

## Step 4 — Structured Low-Token Response (`Stage 3`)

Present the ranked **Top 10 campaigns** in a clean Markdown table, followed by **short actionable notes for the Top 3**. Every entry **must** include:

1. **Direct clickable campaign URL** (`[Campaign Title](https://...)`)
2. **Platform name** and **Creator / Brand**
3. **Effective Net RPM** (after platform fees) & **Real Value Score** (`0–100`)
4. **Remaining Budget** (and `%` unspent when available)
5. **Min Payout** & **Max Payout Per-Clip Cap**
6. **Allowed Socials** (`tiktok`, `reels`, `shorts`, `x`)
7. **Key Brief Rules & Rejection Traps** from `requirements_summary`
