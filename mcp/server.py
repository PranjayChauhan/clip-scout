"""Entry point for FastMCP server (`python mcp/server.py` or `fastmcp run mcp/server.py`).

Note: `mcp/` intentionally has no `__init__.py` so it never shadows the official `mcp` PyPI SDK.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.mcp_app import (  # noqa: E402
    discover_platforms,
    get_top_campaigns,
    list_trusted_platforms,
    main,
    mcp,
    refresh_campaigns,
    save_profile,
)

__all__ = [
    "mcp",
    "main",
    "list_trusted_platforms",
    "discover_platforms",
    "save_profile",
    "refresh_campaigns",
    "get_top_campaigns",
]

if __name__ == "__main__":
    main()
