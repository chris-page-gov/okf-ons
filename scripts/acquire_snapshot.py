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
import os
import shutil
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from okf_ons.els import ELSProjectionError, validate_els_acquisition_envelope  # noqa: E402
from okf_ons.sources import (  # noqa: E402
    SourceDefinition,
    acquire_source,
    load_source_register,
)


class SnapshotCompositionError(ValueError):
    """Raised when a frozen source cannot be safely composed into a snapshot."""


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


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    payload = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256_text(payload)


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SnapshotCompositionError(f"unable to read JSON object: {path.name}") from exc
    if not isinstance(value, dict):
        raise SnapshotCompositionError(f"expected a JSON object: {path.name}")
    return value


def _validate_public_result(
    public_result: Mapping[str, Any],
    source_id: str,
    definition: SourceDefinition,
    *,
    require_complete: bool,
) -> dict[str, Any]:
    if public_result.get("schemaVersion") != "okf-ons.source-acquisition.v1":
        raise SnapshotCompositionError(f"unsupported acquisition envelope: {source_id}")
    provenance = public_result.get("provenance")
    records = public_result.get("records")
    if not isinstance(provenance, Mapping) or not isinstance(records, list):
        raise SnapshotCompositionError(f"malformed acquisition envelope: {source_id}")
    source = provenance.get("source")
    if not isinstance(source, Mapping) or source.get("id") != source_id:
        raise SnapshotCompositionError(f"acquisition source identity mismatch: {source_id}")
    declared_adapter = source.get("adapter")
    if declared_adapter is not None and declared_adapter != definition.adapter:
        raise SnapshotCompositionError(f"acquisition adapter mismatch: {source_id}")
    if source.get("endpoint") != definition.endpoint:
        raise SnapshotCompositionError(f"acquisition endpoint mismatch: {source_id}")
    if provenance.get("recordCount") != len(records):
        raise SnapshotCompositionError(f"acquisition record count mismatch: {source_id}")
    record_set_sha256 = sha256_json(records)
    if provenance.get("recordSetSha256") != record_set_sha256:
        raise SnapshotCompositionError(f"acquisition record-set hash mismatch: {source_id}")
    pages = provenance.get("pages")
    if not isinstance(pages, list):
        raise SnapshotCompositionError(f"acquisition page receipts are missing: {source_id}")
    receipts: list[dict[str, str]] = []
    for page in pages:
        if not isinstance(page, Mapping):
            raise SnapshotCompositionError(f"acquisition page receipt is malformed: {source_id}")
        request_url = page.get("requestUrl")
        content_sha256 = page.get("contentSha256")
        if not isinstance(request_url, str) or not isinstance(content_sha256, str):
            raise SnapshotCompositionError(f"acquisition page receipt is incomplete: {source_id}")
        receipts.append(
            {"requestUrl": request_url, "contentSha256": content_sha256}
        )
    snapshot_set_sha256 = sha256_json(receipts)
    if provenance.get("snapshotSetSha256") != snapshot_set_sha256:
        raise SnapshotCompositionError(f"acquisition snapshot-set hash mismatch: {source_id}")
    if require_complete and provenance.get("coverageComplete") is not True:
        raise SnapshotCompositionError(f"acquisition is incomplete: {source_id}")
    if definition.adapter == "els-metadata-projection":
        try:
            validate_els_acquisition_envelope(dict(public_result))
        except ELSProjectionError as exc:
            raise SnapshotCompositionError(
                f"unsafe projected acquisition {source_id}: {exc}"
            ) from exc
    return {
        "sourceId": source_id,
        "reportedTotal": provenance.get("reportedTotal"),
        "recordCount": provenance["recordCount"],
        "coverageComplete": provenance.get("coverageComplete") is True,
        "unrepresentedCount": provenance.get("unrepresentedCount"),
        "normalisationDroppedCount": provenance.get("normalisationDroppedCount"),
        "recordSetSha256": record_set_sha256,
        "snapshotSetSha256": snapshot_set_sha256,
        **(
            {"explainedExclusionCount": provenance["explainedExclusionCount"]}
            if provenance.get("explainedExclusionCount") is not None
            else {}
        ),
    }


def _load_base_snapshot(
    directory: Path,
    sources: Mapping[str, SourceDefinition],
    *,
    require_complete: bool,
) -> tuple[dict[str, Any], dict[str, tuple[bytes, dict[str, Any]]], str]:
    manifest_path = directory / "snapshot.json"
    manifest_bytes = manifest_path.read_bytes() if manifest_path.is_file() else b""
    if not manifest_bytes:
        raise SnapshotCompositionError("base snapshot manifest is missing")
    manifest = _read_json_object(manifest_path)
    if manifest.get("schema") != "okf-ons.frozen-snapshot.v1":
        raise SnapshotCompositionError("base snapshot uses an unsupported schema")
    if manifest.get("metadataOnly") is not True:
        raise SnapshotCompositionError("base snapshot must assert metadataOnly=true")
    if manifest.get("observationsIncluded") is not False:
        raise SnapshotCompositionError("base snapshot must assert observationsIncluded=false")
    rows = manifest.get("sources")
    if not isinstance(rows, list) or not rows:
        raise SnapshotCompositionError("base snapshot has no source rows")

    resolved_directory = directory.resolve()
    carried: dict[str, tuple[bytes, dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise SnapshotCompositionError("base snapshot source row is malformed")
        source_id = str(row.get("sourceId") or "")
        definition = sources.get(source_id)
        if definition is None or source_id in carried:
            raise SnapshotCompositionError(
                f"base snapshot has an unknown or duplicate source: {source_id}"
            )
        filename = str(row.get("file") or "")
        if not filename or Path(filename).name != filename:
            raise SnapshotCompositionError(f"base snapshot filename is unsafe: {source_id}")
        path = directory / filename
        if not path.is_file() or path.resolve().parent != resolved_directory:
            raise SnapshotCompositionError(f"base snapshot source file is unsafe: {source_id}")
        data = path.read_bytes()
        if sha256_bytes(data) != row.get("sha256"):
            raise SnapshotCompositionError(f"base snapshot file hash mismatch: {source_id}")
        public_result = _read_json_object(path)
        expected = _validate_public_result(
            public_result,
            source_id,
            definition,
            require_complete=require_complete,
        )
        for key, value in expected.items():
            if key != "sourceId" and row.get(key) != value:
                raise SnapshotCompositionError(
                    f"base snapshot manifest binding mismatch for {source_id}: {key}"
                )
        carried[source_id] = (data, dict(row))
    if set(carried) != set(sources):
        raise SnapshotCompositionError(
            "base snapshot does not contain every registered source exactly once"
        )
    if require_complete and manifest.get("completeForRegisteredAdapters") is not True:
        raise SnapshotCompositionError("base snapshot is not complete for registered adapters")
    return manifest, carried, sha256_bytes(manifest_bytes)


def main(argv: Sequence[str] | None = None) -> int:
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
        "--base-snapshot",
        type=Path,
        help=(
            "Complete frozen snapshot whose unselected source envelopes are carried "
            "forward after hash validation"
        ),
    )
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
    parser.add_argument("--page-size", type=int)
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="Fail instead of publishing a snapshot with any incomplete source lane",
    )
    arguments = parser.parse_args(argv)

    snapshot_name = str(arguments.snapshot_id).strip()
    if (
        not snapshot_name
        or Path(snapshot_name).name != snapshot_name
        or snapshot_name in {".", ".."}
    ):
        parser.error("snapshot id must be a safe directory name")

    sources = load_source_register(arguments.source_register)
    selected_ids = arguments.source_ids or [
        source_id
        for source_id, source in sources.items()
        if source.acquisition_method == "http-json"
    ]
    unknown = sorted(set(selected_ids) - set(sources))
    if unknown:
        parser.error("unknown source id(s): " + ", ".join(unknown))
    if len(selected_ids) != len(set(selected_ids)):
        parser.error("source id(s) may not be repeated")
    projected = sorted(
        source_id
        for source_id in selected_ids
        if sources[source_id].acquisition_method != "http-json"
    )
    if projected:
        parser.error(
            "source id(s) require their deterministic projector: " + ", ".join(projected)
        )

    snapshot_directory = arguments.output_dir / snapshot_name
    if snapshot_directory.exists():
        parser.error(f"snapshot destination already exists: {snapshot_directory}")
    snapshot_directory.parent.mkdir(parents=True, exist_ok=True)

    base_manifest: dict[str, Any] | None = None
    base_sources: dict[str, tuple[bytes, dict[str, Any]]] = {}
    base_manifest_sha256 = ""
    if arguments.base_snapshot is not None:
        try:
            base_manifest, base_sources, base_manifest_sha256 = _load_base_snapshot(
                arguments.base_snapshot,
                sources,
                require_complete=arguments.require_complete,
            )
        except (OSError, SnapshotCompositionError) as exc:
            parser.error(str(exc))

    temporary_directory = Path(
        tempfile.mkdtemp(
            prefix=f".{snapshot_name}.",
            suffix=".tmp",
            dir=snapshot_directory.parent,
        )
    )
    manifest_sources: list[dict[str, Any]] = []
    emitted_ids: set[str] = set()
    published = False

    def add_public_result(source_id: str, public_result: dict[str, Any]) -> None:
        if source_id in emitted_ids:
            raise SnapshotCompositionError(f"duplicate acquired source id: {source_id}")
        definition = sources[source_id]
        manifest_row = _validate_public_result(
            public_result,
            source_id,
            definition,
            require_complete=arguments.require_complete,
        )
        text = canonical_json(public_result)
        output_path = temporary_directory / f"{source_id}.json"
        output_path.write_text(text, encoding="utf-8", newline="\n")
        manifest_row["file"] = output_path.name
        manifest_row["sha256"] = sha256_text(text)
        manifest_sources.append(manifest_row)
        emitted_ids.add(source_id)

    try:
        for source_id in selected_ids:
            source = sources[source_id]
            result = acquire_source(
                source,
                cache_directory=arguments.cache_dir,
                mode=arguments.mode,
                page_size=arguments.page_size,
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

        for projected_path in arguments.projected_acquisition:
            try:
                public_result = json.loads(projected_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise SnapshotCompositionError(
                    f"unable to read projected acquisition {projected_path}: {exc}"
                ) from exc
            if not isinstance(public_result, dict):
                raise SnapshotCompositionError(
                    f"malformed projected acquisition: {projected_path}"
                )
            provenance = public_result.get("provenance")
            source = provenance.get("source") if isinstance(provenance, Mapping) else None
            source_id = str(source.get("id") or "") if isinstance(source, Mapping) else ""
            definition = sources.get(source_id)
            if definition is None or definition.acquisition_method != "local-projection":
                raise SnapshotCompositionError(
                    "projected acquisition source is not registered for local projection: "
                    f"{source_id}"
                )
            add_public_result(source_id, public_result)
            print(
                f"{source_id}: {provenance['recordCount']} projected records "
                f"(complete={provenance['coverageComplete']})"
            )

        for source_id, (data, row) in sorted(base_sources.items()):
            if source_id in emitted_ids:
                continue
            output_path = temporary_directory / str(row["file"])
            if output_path.exists():
                raise SnapshotCompositionError(
                    f"base snapshot filename collides with another source: {source_id}"
                )
            output_path.write_bytes(data)
            manifest_sources.append(row)
            emitted_ids.add(source_id)
            print(
                f"{source_id}: carried forward from "
                f"{base_manifest.get('snapshotId') if base_manifest else 'base snapshot'}"
            )

        complete = all(
            source["coverageComplete"] for source in manifest_sources
        ) and emitted_ids == set(sources)
        if arguments.require_complete and not complete:
            raise SnapshotCompositionError(
                "composed snapshot is not complete for every registered adapter"
            )
        manifest = {
            "schema": "okf-ons.frozen-snapshot.v1",
            "snapshotId": snapshot_name,
            "metadataOnly": True,
            "observationsIncluded": False,
            "sources": sorted(manifest_sources, key=lambda row: row["sourceId"]),
            "completeForRegisteredAdapters": complete,
            "claimBoundary": (
                "Completeness here covers only the implemented registered adapters. "
                "The bundle coverage ledger separately records planned and reconciliation lanes."
            ),
        }
        if base_manifest is not None:
            manifest["basedOn"] = {
                "snapshotId": base_manifest.get("snapshotId"),
                "manifestSha256": base_manifest_sha256,
            }
        (temporary_directory / "snapshot.json").write_text(
            canonical_json(manifest),
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temporary_directory, snapshot_directory)
        published = True
        return 0
    except SnapshotCompositionError as exc:
        parser.error(str(exc))
    finally:
        if not published and temporary_directory.exists():
            shutil.rmtree(temporary_directory)


if __name__ == "__main__":
    raise SystemExit(main())
