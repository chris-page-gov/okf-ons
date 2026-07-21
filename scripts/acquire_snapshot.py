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

from okf_ons.els import ELSProjectionError, validate_els_acquisition_envelope  # noqa: E402
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
    parser.add_argument(
        "--projected-acquisition",
        action="append",
        type=Path,
        default=[],
        help=(
            "Frozen acquisition envelope produced by a registered local projector; "
            "may be repeated"
        ),
    )
    parser.add_argument("--request-interval", type=float, default=0.2)
    parser.add_argument("--maximum-pages", type=int, default=100)
    arguments = parser.parse_args()

    sources = load_source_register(arguments.source_register)
    selected_ids = arguments.source_ids or [
        source_id
        for source_id, source in sources.items()
        if source.acquisition_method == "http-json"
    ]
    unknown = sorted(set(selected_ids) - set(sources))
    if unknown:
        parser.error("unknown source id(s): " + ", ".join(unknown))
    projected = sorted(
        source_id
        for source_id in selected_ids
        if sources[source_id].acquisition_method != "http-json"
    )
    if projected:
        parser.error(
            "source id(s) require their deterministic projector: " + ", ".join(projected)
        )

    snapshot_directory = arguments.output_dir / arguments.snapshot_id
    snapshot_directory.mkdir(parents=True, exist_ok=True)
    manifest_sources: list[dict[str, Any]] = []

    def add_public_result(source_id: str, public_result: dict[str, Any]) -> None:
        text = canonical_json(public_result)
        output_path = snapshot_directory / f"{source_id}.json"
        output_path.write_text(text, encoding="utf-8", newline="\n")
        provenance = public_result["provenance"]
        manifest_row = {
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
        if provenance.get("explainedExclusionCount") is not None:
            manifest_row["explainedExclusionCount"] = provenance["explainedExclusionCount"]
        manifest_sources.append(manifest_row)

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
        add_public_result(source_id, public_result)
        provenance = public_result["provenance"]
        print(
            f"{source_id}: {provenance['recordCount']} records "
            f"(reported {provenance.get('reportedTotal')}, "
            f"complete={provenance['coverageComplete']})"
        )

    projected_ids: set[str] = set()
    for projected_path in arguments.projected_acquisition:
        try:
            public_result = json.loads(projected_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            parser.error(f"unable to read projected acquisition {projected_path}: {exc}")
        if not isinstance(public_result, dict) or public_result.get("schemaVersion") != (
            "okf-ons.source-acquisition.v1"
        ):
            parser.error(f"unsupported projected acquisition: {projected_path}")
        provenance = public_result.get("provenance")
        records = public_result.get("records")
        if not isinstance(provenance, dict) or not isinstance(records, list):
            parser.error(f"malformed projected acquisition: {projected_path}")
        source = provenance.get("source")
        source_id = str(source.get("id") or "") if isinstance(source, dict) else ""
        definition = sources.get(source_id)
        if definition is None or definition.acquisition_method != "local-projection":
            parser.error(
                f"projected acquisition source is not registered for local projection: {source_id}"
            )
        if source.get("adapter") != definition.adapter:
            parser.error(f"projected acquisition adapter mismatch: {source_id}")
        if definition.adapter != "els-metadata-projection":
            parser.error(f"no allowlist validator is registered for projected source: {source_id}")
        try:
            validate_els_acquisition_envelope(public_result)
        except ELSProjectionError as exc:
            parser.error(f"unsafe projected acquisition {source_id}: {exc}")
        if source_id in projected_ids or source_id in selected_ids:
            parser.error(f"duplicate acquired source id: {source_id}")
        add_public_result(source_id, public_result)
        projected_ids.add(source_id)
        print(
            f"{source_id}: {provenance['recordCount']} projected records "
            f"(complete={provenance['coverageComplete']})"
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
        and (set(selected_ids) | projected_ids) == set(sources),
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
