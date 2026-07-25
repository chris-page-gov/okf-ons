#!/usr/bin/env python3
"""Validate this producer's generated Markdown layer against OKF v0.2."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from okf_ons.okf import OKFConformanceError, validate_okf_bundle  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", nargs="?", type=Path, default=ROOT / "bundle")
    arguments = parser.parse_args()
    try:
        report = validate_okf_bundle(arguments.bundle)
    except (OSError, OKFConformanceError) as exc:
        parser.exit(1, f"OKF v0.2 conformance error: {exc}\n")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
