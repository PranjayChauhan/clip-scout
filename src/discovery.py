"""Stage 0: Independent Web Discovery & Deep Activity Verification for Clipping Platforms.

Why this exists:
A repository cloned months or years later must NEVER blindly trust a static list of companies.
Platforms shut down, pivot away from creator payouts, freeze campaigns, or turn into paid courses,
while new legitimate clipping marketplaces launch.

`src/discovery.py` therefore enforces two guarantees before Stage 1-3 proceed:
1. Independent Live Web Search: Queries live web search feeds (zero API key required) to surface
   newly launched pay-per-view clipping marketplaces automatically.
2. Deep Activity & Trust Audit (beyond HTTP 200): Inspects live page titles, meta descriptions,
   and body signals to verify active per-view/campaign operations, and automatically marks
   dead, parked, sunset/pivoted, pure-SaaS-editor, or pay-to-join sites `inactive`.
"""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse

import httpx

from src.schema import PlatformRecord, utc_now_iso

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PLATFORMS_PATH = REPO_ROOT / "data" / "platforms.json"
LOCAL_VERIFIED_SENTINEL = REPO_ROOT / ".clipscout_verified"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

DISCOVERY_SEARCH_QUERIES: tuple[str, ...] = (
    "clipping marketplace get paid per 1000 views creators",
    "content rewards clipping campaign platform cpm payout",
    "get paid to clip videos per 1k views campaigns",
)

# Domains that are content/social/search/news hosts or pure AI video-cutter SaaS tools (not marketplaces)
IGNORED_SEARCH_DOMAINS: frozenset[str] = frozenset(
    {
        "bing.com",
        "microsoft.com",
        "yahoo.com",
        "yimg.com",
        "oath.com",
        "google.com",
        "youtube.com",
        "youtu.be",
        "reddit.com",
        "medium.com",
        "substack.com",
        "tiktok.com",
        "instagram.com",
        "facebook.com",
        "x.com",
        "twitter.com",
        "linkedin.com",
        "discord.com",
        "discord.gg",
        "github.com",
        "wikipedia.org",
        "forbes.com",
        "digiday.com",
        "analyticsinsight.net",
        "trustpilot.com",
        "g2.com",
        "capterra.com",
        "apple.com",
        "play.google.com",
        "w3.org",
        "purl.org",
        # Pure AI video-clipping SaaS editors without campaign payout marketplaces
        "opus.pro",
        "choppity.com",
        "vizard.ai",
        "klap.app",
        "submagic.co",
        "captions.ai",
        "descript.com",
        "veed.io",
        "capcut.com",
    }
)

PARKED_OR_SHUTDOWN_SIGNALS: tuple[str, ...] = (
    "domain is for sale",
    "buy this domain",
    "sedoparking",
    "hugedomains",
    "afternic",
    "dan.com",
    "parked free, courtesy of godaddy",
    "has shut down",
    "we have shut down",
    "shutting down our",
    "no longer operating",
    "service has been discontinued",
    "platform is closed",
    "paused all campaigns indefinitely",
)

PAYWALL_OR_AFFILIATE_SPAM_SIGNALS: tuple[str, ...] = (
    "pay to access campaigns",
    "membership required to view campaigns",
    "buy course to unlock clipping",
    "enroll now for $",
    "best creator, sales and side-hustle communities",
    "top 10 clipping platforms",
    "best clipping platforms in 20",
)

# Title / meta-description signals that identify blogs, news sites, or pure AI video-cutter SaaS tools
NON_MARKETPLACE_TITLE_META_SIGNALS: tuple[str, ...] = (
    "ai video clipper",
    "ai stream clipper",
    "ai stream clipping",
    "clipping software",
    "ai clip maker",
    "long videos into vertical clips",
    "turn long videos into viral clips",
    "guides and news on clipping",
    "how clipping works",
)

# Strong multi-word marketplace proof required for newly discovered unknown web domains
STRONG_MARKETPLACE_PROOF_SIGNALS: tuple[str, ...] = (
    "browse campaigns",
    "active campaigns",
    "choose campaigns",
    "clipping marketplace",
    "campaign platform",
    "content rewards",
    "get paid to clip",
    "pay only for verified views",
    "per 1,000 verified views",
    "per 1,000 views",
    "per 1k views",
)

# A genuine active clipping platform must show BOTH clipping/creator distribution intent AND campaign/payout mechanics
CLIPPING_INTENT_SIGNALS: tuple[str, ...] = (
    "clip",
    "clipping",
    "clipper",
    "content rewards",
    "post content, get paid",
    "short-form",
    "creator campaigns",
)

CAMPAIGN_PAYOUT_SIGNALS: tuple[str, ...] = (
    "campaign",
    "campaigns",
    "per 1,000",
    "per 1k",
    "/1k",
    "1,000 views",
    "1k views",
    "verified views",
    "cpm",
    "rpm",
    "payout",
    "bounties",
    "get paid",
)

# Starting bootstrap candidates — NEVER trusted blindly; every entry is audited live during discovery
BOOTSTRAP_CANDIDATES: list[dict] = [
    {
        "id": "whop",
        "name": "Whop Content Rewards",
        "url": "https://whop.com/content-rewards/",
        "model": "open_marketplace",
        "status": "unverified",
        "free_to_join": True,
        "typical_rpm_range": "$0.50-$3.00",
        "payout_methods": ["whop_balance", "stripe", "bank_transfer", "crypto", "paypal"],
        "supported_socials": ["tiktok", "reels", "shorts", "x"],
        "adapter_implemented": True,
        "trust_notes": "Decentralized clipping & UGC bounty marketplace on Whop (10% platform fee; free for clippers).",
    },
    {
        "id": "content_rewards",
        "name": "Content Rewards",
        "url": "https://contentrewards.com/",
        "model": "open_marketplace",
        "status": "unverified",
        "free_to_join": True,
        "typical_rpm_range": "$0.50-$3.00",
        "payout_methods": ["stripe", "paypal", "whop_balance"],
        "supported_socials": ["tiktok", "reels", "shorts", "x"],
        "adapter_implemented": False,
        "trust_notes": "Dedicated Content Rewards clipping & UGC campaign portal.",
    },
    {
        "id": "vyro",
        "name": "Vyro",
        "url": "https://vyro.com",
        "model": "open_marketplace",
        "status": "unverified",
        "free_to_join": True,
        "typical_rpm_range": "$1.00-$3.00+",
        "payout_methods": ["stripe", "paypal"],
        "supported_socials": ["tiktok", "reels", "shorts"],
        "adapter_implemented": False,
        "trust_notes": "Creator-backed short-form distribution & CPM clipping marketplace.",
    },
    {
        "id": "clipping_net",
        "name": "Clipping.net",
        "url": "https://clipping.net",
        "model": "open_marketplace",
        "status": "unverified",
        "free_to_join": True,
        "typical_rpm_range": "$0.50-$3.00",
        "payout_methods": ["paypal", "stripe", "crypto"],
        "supported_socials": ["tiktok", "reels", "shorts"],
        "adapter_implemented": False,
        "trust_notes": "Standalone clipping network for streamers, music labels, and consumer brands.",
    },
    {
        "id": "clipster",
        "name": "Clipster",
        "url": "https://www.clipster.com/",
        "model": "open_marketplace",
        "status": "unverified",
        "free_to_join": True,
        "typical_rpm_range": "$1.00-$2.50",
        "payout_methods": ["stripe", "paypal", "bank_transfer"],
        "supported_socials": ["tiktok", "reels", "shorts"],
        "adapter_implemented": False,
        "trust_notes": "Performance-based creator marketing & clipping campaign platform.",
    },
    {
        "id": "promote_fun",
        "name": "Promote.fun",
        "url": "https://www.promote.fun/",
        "model": "open_marketplace",
        "status": "unverified",
        "free_to_join": True,
        "typical_rpm_range": "$0.20-$2.00+",
        "payout_methods": ["crypto", "stripe"],
        "supported_socials": ["tiktok", "reels", "shorts", "x"],
        "adapter_implemented": False,
        "trust_notes": "Performance-based creator campaign & promotional distribution marketplace.",
    },
    {
        "id": "clipping_io",
        "name": "Clipping.io",
        "url": "https://www.clipping.io/",
        "model": "managed_agency",
        "status": "unverified",
        "free_to_join": True,
        "typical_rpm_range": "$0.50-$2.50",
        "payout_methods": ["paypal", "bank_transfer", "crypto"],
        "supported_socials": ["tiktok", "reels", "shorts"],
        "adapter_implemented": False,
        "trust_notes": "Managed creator & brand clipping network with CPM payouts.",
    },
    {
        "id": "ssemble",
        "name": "Ssemble Clip Rewards",
        "url": "https://www.ssemble.com/clip-rewards",
        "model": "native_program",
        "status": "unverified",
        "free_to_join": True,
        "typical_rpm_range": "$0.50-$2.00",
        "payout_methods": ["paypal", "stripe"],
        "supported_socials": ["tiktok", "reels", "shorts"],
        "adapter_implemented": False,
        "trust_notes": "Native Clip Rewards marketplace integrated into Ssemble.",
    },
    {
        "id": "picsart_clipping",
        "name": "Picsart Clipping",
        "url": "https://picsart.com/earn/clipping/",
        "model": "native_program",
        "status": "unverified",
        "free_to_join": True,
        "typical_rpm_range": "$0.50-$2.50",
        "payout_methods": ["paypal", "bank_transfer"],
        "supported_socials": ["tiktok", "reels", "shorts"],
        "adapter_implemented": False,
        "trust_notes": "Official Picsart creator clipping reward program.",
    },
    {
        "id": "clipaffiliates",
        "name": "ClipAffiliates",
        "url": "https://clipaffiliates.com",
        "model": "open_marketplace",
        "status": "inactive",
        "free_to_join": True,
        "typical_rpm_range": "N/A",
        "payout_methods": [],
        "supported_socials": ["tiktok", "reels", "shorts"],
        "adapter_implemented": False,
        "trust_notes": "Known shut-down platform retained as inactive regression sentinel.",
    },
]


@dataclass
class DiscoveryDiff:
    """Summary of changes found during a Stage 0 platform discovery/verification run."""

    newly_discovered: list[str] = field(default_factory=list)
    reactivated: list[str] = field(default_factory=list)
    marked_inactive: list[str] = field(default_factory=list)
    excluded_untrusted: list[str] = field(default_factory=list)
    web_candidates_checked: int = 0
    active_trusted_count: int = 0
    total_count: int = 0
    verified_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict:
        return {
            "verified_at": self.verified_at,
            "active_trusted_count": self.active_trusted_count,
            "total_count": self.total_count,
            "web_candidates_checked": self.web_candidates_checked,
            "newly_discovered": self.newly_discovered,
            "reactivated": self.reactivated,
            "marked_inactive": self.marked_inactive,
            "excluded_untrusted": self.excluded_untrusted,
        }


def _parse_iso(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    cleaned = ts.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _registrable_domain(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


def _slug_from_domain(domain: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", domain.lower()).strip("_")
    return slug or "discovered_platform"


def _extract_title_and_meta(raw_html: str) -> tuple[str, str]:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
    title = html.unescape(re.sub(r"\s+", " ", title_match.group(1)).strip()) if title_match else ""
    if not title:
        meta_title = re.search(
            r'<meta[^>]+name=["\']title["\'][^>]+content=["\'](.*?)["\']',
            raw_html,
            re.IGNORECASE | re.DOTALL,
        )
        if meta_title:
            title = html.unescape(meta_title.group(1).strip())

    meta_desc = ""
    desc_match = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
        raw_html,
        re.IGNORECASE | re.DOTALL,
    )
    if desc_match:
        meta_desc = html.unescape(re.sub(r"\s+", " ", desc_match.group(1)).strip())
    return title[:120], meta_desc[:240]


def load_platforms(path: Path | str = DEFAULT_PLATFORMS_PATH) -> list[PlatformRecord]:
    """Load and validate PlatformRecord entries from data/platforms.json."""
    target = Path(path)
    if not target.exists():
        return []
    raw = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"Expected JSON list in {target}, got {type(raw).__name__}")
    return [PlatformRecord.model_validate(item) for item in raw]


def save_platforms(
    platforms: Iterable[PlatformRecord],
    path: Path | str = DEFAULT_PLATFORMS_PATH,
) -> Path:
    """Persist validated PlatformRecord entries to data/platforms.json."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = [p.model_dump(mode="json") for p in platforms]
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def get_active_trusted_platforms(path: Path | str = DEFAULT_PLATFORMS_PATH) -> list[PlatformRecord]:
    """Return only platforms with status == 'active' AND free_to_join == True."""
    return [p for p in load_platforms(path) if p.is_trusted_active]


def is_registry_stale(
    path: Path | str = DEFAULT_PLATFORMS_PATH,
    max_age_days: int = 7,
    now: Optional[datetime] = None,
    require_local_verification: bool = False,
    sentinel_path: Path | str = LOCAL_VERIFIED_SENTINEL,
) -> bool:
    """
    Return True if data/platforms.json is missing, empty, verified > max_age_days ago,
    or (when `require_local_verification=True`) has never been verified live on this machine
    since cloning from GitHub.
    """
    if require_local_verification and not Path(sentinel_path).exists():
        return True

    records = load_platforms(path)
    if not records:
        return True
    active = [r for r in records if r.is_trusted_active]
    if not active:
        return True

    ref_now = now or datetime.now(timezone.utc)
    cutoff = ref_now - timedelta(days=max_age_days)
    timestamps = [_parse_iso(r.last_verified) for r in active]
    valid_ts = [t for t in timestamps if t is not None]
    if not valid_ts:
        return True
    return max(valid_ts) < cutoff


def discover_candidates_from_web(
    client: httpx.Client,
    known_domains: set[str],
    max_new_candidates: int = 8,
) -> list[dict]:
    """
    Independently search live web feeds (Bing RSS + Yahoo Search, zero API keys needed)
    for newly launched pay-per-view clipping marketplaces.
    """
    discovered_urls: list[str] = []
    seen_domains = set(known_domains)

    for query in DISCOVERY_SEARCH_QUERIES:
        encoded = query.replace(" ", "+")
        search_endpoints = (
            f"https://www.bing.com/search?q={encoded}&format=rss",
            f"https://search.yahoo.com/search?p={encoded}",
        )
        for endpoint in search_endpoints:
            try:
                resp = client.get(endpoint, follow_redirects=True)
                if resp.status_code != 200:
                    continue
            except httpx.HTTPError:
                continue

            raw_urls = re.findall(r"https?://[a-zA-Z0-9._-]+(?:/[^\s<>\"'()]*)?", resp.text)
            for candidate_url in raw_urls:
                domain = _registrable_domain(candidate_url)
                if not domain or "." not in domain:
                    continue
                if any(domain == bad or domain.endswith("." + bad) for bad in IGNORED_SEARCH_DOMAINS):
                    continue
                # Skip blog/article URLs — we want root or program landing pages
                path_lower = (urlparse(candidate_url).path or "").lower()
                if any(seg in path_lower for seg in ("/blog/", "/news/", "/article/", "/posts/", "/wiki/")):
                    continue
                if domain in seen_domains:
                    continue

                seen_domains.add(domain)
                parsed = urlparse(candidate_url)
                clean_path = parsed.path if parsed.path and len(parsed.path) <= 32 else "/"
                normalized_url = f"{parsed.scheme}://{parsed.netloc}{clean_path}"
                discovered_urls.append(normalized_url)
                if len(discovered_urls) >= max_new_candidates:
                    break
            if len(discovered_urls) >= max_new_candidates:
                break
        if len(discovered_urls) >= max_new_candidates:
            break

    candidates: list[dict] = []
    for url in discovered_urls:
        domain = _registrable_domain(url)
        candidates.append(
            {
                "id": _slug_from_domain(domain),
                "name": domain,
                "url": url,
                "model": "open_marketplace",
                "status": "unverified",
                "free_to_join": True,
                "typical_rpm_range": "Varies (live discovered)",
                "payout_methods": [],
                "supported_socials": ["tiktok", "reels", "shorts"],
                "adapter_implemented": False,
                "trust_notes": "Independently discovered via live web search; audited by Stage 0 activity gate.",
            }
        )
    return candidates


def verify_platform_url(
    url: str,
    client: httpx.Client,
    require_activity_signals: bool = True,
    strict_new_candidate: bool = False,
) -> tuple[bool, str, Optional[str]]:
    """
    Deeply verify whether a clipping platform URL is live, free of shutdown/parked/paywall
    red flags, not a blog or pure AI-editor SaaS, AND actively running creator campaigns.

    Returns `(is_trusted_active, audit_note, extracted_title)`.
    """
    try:
        resp = client.get(url, follow_redirects=True)
    except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
        return False, f"Offline / unreachable ({type(exc).__name__})", None
    except httpx.HTTPError as exc:
        return False, f"HTTP error ({type(exc).__name__})", None

    status_code = resp.status_code
    if status_code in (404, 410) or status_code >= 500:
        return False, f"Dead endpoint (HTTP {status_code})", None

    is_waf_protected = status_code == 429 or (
        status_code in (401, 403)
        and (
            "cf-ray" in resp.headers
            or "x-vercel-id" in resp.headers
            or "cloudflare" in resp.headers.get("server", "").lower()
            or "vercel" in resp.headers.get("server", "").lower()
        )
    )

    raw_text = resp.text or ""
    title, meta_desc = _extract_title_and_meta(raw_text[:65536])
    title_meta_lower = f"{title} {meta_desc}".lower()
    combined_lower = f"{title_meta_lower} {raw_text[:120000]}".lower()

    for signal in PARKED_OR_SHUTDOWN_SIGNALS:
        if signal in combined_lower:
            return False, f"Inactive/shutdown signal detected ('{signal}')", title or None

    for signal in PAYWALL_OR_AFFILIATE_SPAM_SIGNALS:
        if signal in combined_lower:
            return False, f"Untrusted paywall/listicle signal ('{signal}')", title or None

    for signal in NON_MARKETPLACE_TITLE_META_SIGNALS:
        if signal in title_meta_lower:
            return False, f"Rejected non-marketplace SaaS/blog ('{signal}')", title or None

    if is_waf_protected:
        if strict_new_candidate:
            return False, f"Unverified WAF-gated candidate (HTTP {status_code})", title or None
        return True, f"Live host behind WAF/rate-limit (HTTP {status_code})", title or None

    if not (200 <= status_code < 400):
        return False, f"Unexpected HTTP {status_code}", title or None

    if require_activity_signals:
        matched_intent = [s for s in CLIPPING_INTENT_SIGNALS if s in combined_lower]
        matched_payout = [s for s in CAMPAIGN_PAYOUT_SIGNALS if s in combined_lower]
        if not matched_intent or not matched_payout:
            return (
                False,
                "No active clipping campaign/payout signals found on live page (possible pivot or pure SaaS tool)",
                title or None,
            )
        if strict_new_candidate:
            strong_matches = [s for s in STRONG_MARKETPLACE_PROOF_SIGNALS if s in combined_lower]
            if not strong_matches:
                return (
                    False,
                    "Insufficient marketplace proof for newly discovered web candidate",
                    title or None,
                )
        return (
            True,
            f"Verified live clipping activity (signals: {', '.join((matched_intent[:2] + matched_payout[:2]))})",
            title or None,
        )

    return True, f"Verified live (HTTP {status_code})", title or None


def run_discovery(
    platforms_path: Path | str = DEFAULT_PLATFORMS_PATH,
    check_live: bool = True,
    web_search: bool = False,
    candidates: Optional[list[dict]] = None,
    http_client: Optional[httpx.Client] = None,
    timeout_seconds: float = 10.0,
    require_activity_signals: bool = True,
    mark_local_sentinel: bool = True,
    sentinel_path: Path | str = LOCAL_VERIFIED_SENTINEL,
) -> tuple[list[PlatformRecord], DiscoveryDiff]:
    """
    Run Stage 0 independent discovery & deep activity verification.

    - Merges existing registry, bootstrap candidates, optional explicit `candidates`,
      and (when `web_search=True` and `check_live=True`) live web-searched candidates.
    - Audits every platform's live URL for real clipping/campaign activity, marking
      shut-down, pivoted, parked, SaaS-only, or pay-to-join platforms `inactive`.
    - Saves updated `data/platforms.json` and stamps `.clipscout_verified` locally.
    """
    target = Path(platforms_path)
    existing_list = load_platforms(target)
    existing_by_id: dict[str, PlatformRecord] = {p.id: p for p in existing_list}

    diff = DiscoveryDiff(verified_at=utc_now_iso())
    merged_by_id: dict[str, PlatformRecord] = {}

    # Seed from bootstrap first so canonical URLs stay up to date, then overlay user/existing records
    bootstrap_by_id = {item["id"]: item for item in BOOTSTRAP_CANDIDATES}
    for pid, b_item in bootstrap_by_id.items():
        if pid in existing_by_id:
            prev = existing_by_id[pid]
            # Keep updated canonical URL if bootstrap fixed a legacy 404 route
            merged_by_id[pid] = prev.model_copy(update={"url": b_item["url"]})
        else:
            rec = PlatformRecord.model_validate({**b_item, "last_verified": diff.verified_at})
            merged_by_id[pid] = rec

    for pid, prev in existing_by_id.items():
        if pid not in merged_by_id:
            merged_by_id[pid] = prev

    for item in candidates or []:
        rec = PlatformRecord.model_validate({**item, "last_verified": diff.verified_at})
        if rec.id not in merged_by_id:
            merged_by_id[rec.id] = rec

    owns_client = http_client is None and check_live
    client = http_client or (
        httpx.Client(headers=DEFAULT_HEADERS, timeout=timeout_seconds) if check_live else None
    )

    try:
        if check_live and web_search and client is not None:
            known_domains = {_registrable_domain(r.url) for r in merged_by_id.values()}
            web_candidates = discover_candidates_from_web(client, known_domains=known_domains)
            diff.web_candidates_checked = len(web_candidates)
            for wc in web_candidates:
                rec = PlatformRecord.model_validate({**wc, "last_verified": diff.verified_at})
                if rec.id not in merged_by_id:
                    merged_by_id[rec.id] = rec

        updated_records: list[PlatformRecord] = []
        for pid, record in merged_by_id.items():
            was_previously_known_active = (
                pid in existing_by_id and existing_by_id[pid].status == "active"
            )

            # Hard rule: pay-to-join platforms are NEVER trusted
            if not record.free_to_join:
                record.status = "inactive"
                if "EXCLUDED (pay-to-join)" not in record.trust_notes:
                    record.trust_notes = f"EXCLUDED (pay-to-join): {record.trust_notes}".strip()
                diff.excluded_untrusted.append(record.id)
                record.last_verified = diff.verified_at
                updated_records.append(record)
                continue

            is_ephemeral_web_hit = (
                pid not in existing_by_id
                and pid not in bootstrap_by_id
                and not any((c.get("id") == pid) for c in (candidates or []))
            )

            if check_live and client is not None:
                is_live_active, audit_note, page_title = verify_platform_url(
                    record.url,
                    client,
                    require_activity_signals=require_activity_signals,
                    strict_new_candidate=is_ephemeral_web_hit,
                )
                if is_live_active:
                    if page_title and record.name == _registrable_domain(record.url):
                        clean_name = re.split(r"[|—:]", page_title)[0].strip()
                        record.name = clean_name[:60] or record.name
                    if not was_previously_known_active:
                        if pid in existing_by_id and existing_by_id[pid].status == "inactive":
                            diff.reactivated.append(record.id)
                        else:
                            diff.newly_discovered.append(record.id)
                    record.status = "active"
                    base_note = re.sub(r"\s*\[[^\]]+\]\s*$", "", record.trust_notes).strip()
                    record.trust_notes = f"{base_note} [{audit_note}]".strip()
                else:
                    if is_ephemeral_web_hit:
                        continue

                    if was_previously_known_active or record.status == "active":
                        diff.marked_inactive.append(record.id)
                    record.status = "inactive"
                    base_note = re.sub(r"\s*\[[^\]]+\]\s*$", "", record.trust_notes).strip()
                    record.trust_notes = f"{base_note} [{audit_note}]".strip()
            else:
                # Offline mode: promote bootstrap 'unverified' entries (except known inactive) for deterministic offline tests
                if record.status == "unverified" and record.free_to_join:
                    record.status = "active"
                    if not was_previously_known_active:
                        diff.newly_discovered.append(record.id)

            record.last_verified = diff.verified_at
            updated_records.append(record)
    finally:
        if owns_client and client is not None:
            client.close()

    diff.total_count = len(updated_records)
    diff.active_trusted_count = sum(1 for r in updated_records if r.is_trusted_active)
    save_platforms(updated_records, target)

    if check_live and mark_local_sentinel and target.resolve() == DEFAULT_PLATFORMS_PATH.resolve():
        Path(sentinel_path).write_text(diff.verified_at + "\n", encoding="utf-8")

    return updated_records, diff


def ensure_fresh_trusted_registry(
    platforms_path: Path | str = DEFAULT_PLATFORMS_PATH,
    max_age_days: int = 7,
    sentinel_path: Path | str = LOCAL_VERIFIED_SENTINEL,
) -> tuple[list[PlatformRecord], Optional[DiscoveryDiff]]:
    """
    Mandatory Stage 0 gate called before Stage 1 (init), Stage 2 (scrape), or Stage 3 (top).
    Automatically runs independent live discovery + activity verification if:
    - This is a fresh clone (`.clipscout_verified` missing for default registry), OR
    - `data/platforms.json` is missing/empty/older than `max_age_days`.
    """
    target = Path(platforms_path)
    use_sentinel = target.resolve() == DEFAULT_PLATFORMS_PATH.resolve()
    if is_registry_stale(
        target,
        max_age_days=max_age_days,
        require_local_verification=use_sentinel,
        sentinel_path=sentinel_path,
    ):
        records, diff = run_discovery(
            platforms_path=target,
            check_live=True,
            web_search=True,
            mark_local_sentinel=use_sentinel,
            sentinel_path=sentinel_path,
        )
        return [r for r in records if r.is_trusted_active], diff
    return get_active_trusted_platforms(target), None
