#!/usr/bin/env python3
"""Compare two fixed-denominator OKF metadata-gap profiles."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from okf_ons.metadata_gaps import compare_profiles  # noqa: E402


def _load(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Profile must be a JSON object: {path}")
    return payload


def _utc_timestamp(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed.astimezone(UTC)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("current", type=Path)
    parser.add_argument("--elapsed-seconds", type=float)
    parser.add_argument("--started-at")
    parser.add_argument("--completed-at")
    parser.add_argument("--clock-basis", default="UTC wall clock")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if bool(args.started_at) != bool(args.completed_at):
        parser.error("--started-at and --completed-at must be supplied together")
    elapsed_seconds = args.elapsed_seconds
    timing = None
    if args.started_at and args.completed_at:
        try:
            started = _utc_timestamp(args.started_at, "started-at")
            completed = _utc_timestamp(args.completed_at, "completed-at")
        except ValueError as exc:
            parser.error(str(exc))
        measured = (completed - started).total_seconds()
        if measured < 0:
            parser.error("--completed-at must not precede --started-at")
        if elapsed_seconds is not None and abs(elapsed_seconds - measured) > 1:
            parser.error("--elapsed-seconds contradicts the timestamp interval")
        elapsed_seconds = measured
        timing = {
            "startedAt": started.isoformat().replace("+00:00", "Z"),
            "completedAt": completed.isoformat().replace("+00:00", "Z"),
            "elapsedSeconds": round(measured, 3),
            "clockBasis": args.clock_basis,
        }
    comparison = compare_profiles(
        _load(args.baseline),
        _load(args.current),
        elapsed_seconds=elapsed_seconds,
    )
    if timing is not None:
        comparison["timing"] = timing
    rendered = json.dumps(comparison, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
