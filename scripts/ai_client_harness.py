#!/usr/bin/env python3
"""Run the fixture-safe OKF-ONS AI-client evaluation harness."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from okf_ons.ai_evaluation import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["--root", str(ROOT), *sys.argv[1:]]))
