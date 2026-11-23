#!/usr/bin/env python3
"""Build or verify the deterministic OKF-ONS public bundle."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from okf_ons.build import BuildError, check_bundle, compile_bundle, default_inputs  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--snapshot-dir",
        type=Path,
        default=ROOT / "source" / "demo-snapshot",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "bundle")
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    inputs = replace(default_inputs(ROOT), snapshot_directory=arguments.snapshot_dir)
    try:
        if arguments.check:
            check_bundle(inputs, arguments.output)
            print(f"Bundle is deterministic: {arguments.output}")
        else:
            result = compile_bundle(inputs, arguments.output)
            counts = result["descriptor"]["counts"]
            print(
                f"Built {counts['records']} records and "
                f"{counts['relationships']} relationships in {arguments.output}"
            )
    except BuildError as exc:
        parser.exit(1, f"build error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
