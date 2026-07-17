#!/usr/bin/env python3
"""Acquire a bounded, metadata-only ONS catalogue snapshot.

Raw upstream pages remain in ``--cache-dir``.  The output directory contains
only the path-free, projected records and provenance that are safe to use as a
frozen publication input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from okf_ons.sources import acquire_source, load_source_register  # noqa: E402


def canonical_json(value: Any) -> str:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-register",
        type=Path,
        default=ROOT / "source" / "source-register.json",
    )
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument(
        "--mode",
        choices=("prefer-cache", "refresh", "frozen"),
        default="prefer-cache",
    )
    parser.add_argument("--source", action="append", dest="source_ids")
    parser.add_argument("--request-interval", type=float, default=0.2)
    parser.add_argument("--maximum-pages", type=int, default=100)
    arguments = parser.parse_args()

    sources = load_source_register(arguments.source_register)
    selected_ids = arguments.source_ids or list(sources)
    unknown = sorted(set(selected_ids) - set(sources))
    if unknown:
        parser.error("unknown source id(s): " + ", ".join(unknown))

    snapshot_directory = arguments.output_dir / arguments.snapshot_id
    snapshot_directory.mkdir(parents=True, exist_ok=True)
    manifest_sources: list[dict[str, Any]] = []

    for source_id in selected_ids:
        source = sources[source_id]
        result = acquire_source(
            source,
            cache_directory=arguments.cache_dir,
            mode=arguments.mode,
            maximum_pages=arguments.maximum_pages,
            request_interval_seconds=arguments.request_interval,
        )
        public_result = result.as_public_dict()
        text = canonical_json(public_result)
        output_path = snapshot_directory / f"{source_id}.json"
        output_path.write_text(text, encoding="utf-8", newline="\n")
        provenance = public_result["provenance"]
        manifest_sources.append(
            {
                "sourceId": source_id,
                "file": output_path.name,
                "sha256": sha256_text(text),
                "reportedTotal": provenance.get("reportedTotal"),
                "recordCount": provenance["recordCount"],
                "coverageComplete": provenance["coverageComplete"],
                "unrepresentedCount": provenance.get("unrepresentedCount"),
                "normalisationDroppedCount": provenance["normalisationDroppedCount"],
                "recordSetSha256": provenance["recordSetSha256"],
                "snapshotSetSha256": provenance["snapshotSetSha256"],
            }
        )
        print(
            f"{source_id}: {provenance['recordCount']} records "
            f"(reported {provenance.get('reportedTotal')}, "
            f"complete={provenance['coverageComplete']})"
        )

    manifest = {
        "schema": "okf-ons.frozen-snapshot.v1",
        "snapshotId": arguments.snapshot_id,
        "metadataOnly": True,
        "observationsIncluded": False,
        "sources": sorted(manifest_sources, key=lambda row: row["sourceId"]),
        "completeForRegisteredAdapters": all(
            source["coverageComplete"] for source in manifest_sources
        )
        and set(selected_ids) == set(sources),
        "claimBoundary": (
            "Completeness here covers only the implemented registered adapters. "
            "The bundle coverage ledger separately records planned and reconciliation lanes."
        ),
    }
    (snapshot_directory / "snapshot.json").write_text(
        canonical_json(manifest),
        encoding="utf-8",
        newline="\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
