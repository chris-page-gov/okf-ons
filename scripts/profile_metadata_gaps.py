#!/usr/bin/env python3
"""Profile generated OKF metadata gaps without making network calls."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from okf_ons.metadata_gaps import profile_bundle  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=Path("bundle"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--sample-limit", type=int, default=10)
    args = parser.parse_args()
    if args.sample_limit < 0:
        parser.error("--sample-limit must be non-negative")
    profile = profile_bundle(args.bundle, sample_limit=args.sample_limit)
    rendered = json.dumps(profile, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
