#!/usr/bin/env python3
"""Create a public-safe DOCX derivative without exposing redacted values."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from okf_ons.docx_release import DocxReleaseError, sanitize_public_docx  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("destination")
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing destination",
    )
    arguments = parser.parse_args()
    destination = Path(arguments.destination)
    if destination.exists() and not arguments.force:
        parser.error("destination exists; pass --force to replace it")
    try:
        report = sanitize_public_docx(arguments.source, destination)
    except (DocxReleaseError, OSError) as error:
        parser.exit(1, f"sanitization failed: {error}\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
