#!/usr/bin/env python3
"""Compare two fixed-denominator OKF metadata-gap profiles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from okf_ons.metadata_gaps import compare_profiles


def _load(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Profile must be a JSON object: {path}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("current", type=Path)
    parser.add_argument("--elapsed-seconds", type=float)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    comparison = compare_profiles(
        _load(args.baseline),
        _load(args.current),
        elapsed_seconds=args.elapsed_seconds,
    )
    rendered = json.dumps(comparison, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
