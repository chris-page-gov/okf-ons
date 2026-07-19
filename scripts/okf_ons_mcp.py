#!/usr/bin/env python3
"""Launch the dependency-free OKF-ONS metadata broker over stdio."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from okf_ons.mcp_broker import MCPBroker, serve  # noqa: E402,I001


if __name__ == "__main__":
    raise SystemExit(serve(MCPBroker(ROOT)))
