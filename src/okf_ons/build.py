"""Compile a frozen ONS metadata snapshot into a deterministic OKF bundle."""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import tempfile
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from . import __version__
from .evaluation import evaluate_rankings, load_gold_suite
from .model import (
    BUNDLE_PUBLISHER,
    build_alternatives,
    build_cross_source_reconciliation,
    content_sha256,
    normalize_acquisition_record,
    unique_records,
)
from .search import MISSING_FILTER_VALUE, build_search, filter_values, rank_records, result_document

PUBLIC_ROOT = "https://chris-page-gov.github.io/okf-ons/"
EXPLORER_ROOT = "https://chris-page-gov.github.io/okf-explorer/"
CHUNK_SIZE = 500
NON_ENDORSEMENT = (
    "This experimental metadata bundle is independently published by the OKF ONS "
    "project and is not endorsed by the Office for National Statistics or other "
    "source producers. Source attribution does not transfer semantic, operational "
    "or decision authority to the bundle publisher."
)


class BuildError(RuntimeError):
    """Raised when frozen inputs or generated output violate the bundle contract."""


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


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BuildError(f"Unable to read JSON input: {path}") from exc
    if not isinstance(value, dict):
        raise BuildError(f"Expected a JSON object: {path}")
    return value


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_json(value: Any) -> str:
    """Hash source-acquisition content using its canonical digest contract."""

    payload = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return _sha256_bytes(payload.encode("utf-8"))


@dataclass
class BundleWriter:
    root: Path
    paths: set[Path] = field(default_factory=set)

    def write_json(self, relative_path: str | Path, value: Any) -> None:
        self.write_text(relative_path, canonical_json(value))

    def write_text(self, relative_path: str | Path, value: str) -> None:
        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise BuildError(f"Unsafe bundle output path: {relative}")
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8", newline="\n")
        self.paths.add(relative)

    def checksums(self) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        for relative in sorted(self.paths, key=lambda path: path.as_posix()):
            data = (self.root / relative).read_bytes()
            rows.append(
                {
                    "path": relative.as_posix(),
                    "bytes": len(data),
                    "sha256": _sha256_bytes(data),
                }
            )
        return {
            "schema": "okf-ons-checksums.v1",
            "algorithm": "sha256",
            "files": rows,
            "fileCount": len(rows),
            "rootSha256": content_sha256(
                [{"path": row["path"], "sha256": row["sha256"]} for row in rows]
            ),
        }


@dataclass(frozen=True)
class BuildInputs:
    snapshot_directory: Path
    source_register: Path
    provider_datapacks: Path
    standards_register: Path
    ontology_crosswalk: Path
    gold_suite: Path
    evaluation_aliases: Path


@dataclass
class FrozenCorpus:
    snapshot: dict[str, Any]
    acquisitions: list[dict[str, Any]]
    records: list[dict[str, Any]]
    source_register: dict[str, Any]
    standards_register: dict[str, Any]
    ontology_crosswalk: dict[str, Any]
    aliases: dict[str, Any]


def default_inputs(root: Path) -> BuildInputs:
    return BuildInputs(
        snapshot_directory=root / "source" / "demo-snapshot",
        source_register=root / "source" / "source-register.json",
        provider_datapacks=root / "source" / "provider-datapacks",
        standards_register=root / "source" / "standards-register.json",
        ontology_crosswalk=root / "source" / "ontology-crosswalk.json",
        gold_suite=root / "evaluation" / "gold-queries.json",
        evaluation_aliases=root / "source" / "evaluation-aliases.json",
    )


def load_frozen_corpus(inputs: BuildInputs) -> FrozenCorpus:
    snapshot_path = inputs.snapshot_directory / "snapshot.json"
    snapshot = _read_json(snapshot_path)
    if snapshot.get("schema") != "okf-ons.frozen-snapshot.v1":
        raise BuildError("Unsupported frozen snapshot schema")
    if snapshot.get("metadataOnly") is not True:
        raise BuildError("Frozen snapshot must assert metadataOnly=true")
    if snapshot.get("observationsIncluded") is not False:
        raise BuildError("Frozen snapshot must assert observationsIncluded=false")

    snapshot_id = str(snapshot.get("snapshotId") or "").strip()
    if not snapshot_id:
        raise BuildError("Frozen snapshot has no snapshotId")
    source_rows = snapshot.get("sources")
    if not isinstance(source_rows, list) or not source_rows:
        raise BuildError("Frozen snapshot has no source files")

    acquisitions: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    for source_row in source_rows:
        if not isinstance(source_row, Mapping):
            raise BuildError("Frozen snapshot source row must be an object")
        filename = str(source_row.get("file") or "")
        if not filename or Path(filename).name != filename:
            raise BuildError("Frozen snapshot source filename is unsafe")
        path = inputs.snapshot_directory / filename
        data = path.read_bytes()
        if _sha256_bytes(data) != source_row.get("sha256"):
            raise BuildError(f"Frozen source hash mismatch: {filename}")
        acquisition = _read_json(path)
        if acquisition.get("schemaVersion") != "okf-ons.source-acquisition.v1":
            raise BuildError(f"Unsupported acquisition schema: {filename}")
        provenance = acquisition.get("provenance")
        source_records = acquisition.get("records")
        if not isinstance(provenance, Mapping) or not isinstance(source_records, list):
            raise BuildError(f"Malformed acquisition result: {filename}")
        source_id = str(source_row.get("sourceId") or "").strip()
        provenance_source = provenance.get("source")
        provenance_source = provenance_source if isinstance(provenance_source, Mapping) else {}
        if not source_id or provenance_source.get("id") != source_id:
            raise BuildError(f"Acquisition source identity mismatch: {filename}")
        if provenance.get("recordCount") != len(source_records):
            raise BuildError(f"Acquisition record count mismatch: {filename}")
        if source_row.get("recordCount") != len(source_records):
            raise BuildError(f"Frozen manifest record count mismatch: {filename}")

        record_set_sha256 = _sha256_json(source_records)
        if provenance.get("recordSetSha256") != record_set_sha256:
            raise BuildError(f"Acquisition record-set hash mismatch: {filename}")
        if source_row.get("recordSetSha256") != record_set_sha256:
            raise BuildError(f"Frozen manifest record-set hash mismatch: {filename}")

        pages = provenance.get("pages")
        if not isinstance(pages, list):
            raise BuildError(f"Acquisition page receipts are missing: {filename}")
        snapshot_receipts: list[dict[str, str]] = []
        for page in pages:
            if not isinstance(page, Mapping):
                raise BuildError(f"Acquisition page receipt is malformed: {filename}")
            request_url = page.get("requestUrl")
            content_sha256 = page.get("contentSha256")
            if not isinstance(request_url, str) or not isinstance(content_sha256, str):
                raise BuildError(f"Acquisition page receipt is incomplete: {filename}")
            snapshot_receipts.append(
                {"requestUrl": request_url, "contentSha256": content_sha256}
            )
        snapshot_set_sha256 = _sha256_json(snapshot_receipts)
        if provenance.get("snapshotSetSha256") != snapshot_set_sha256:
            raise BuildError(f"Acquisition snapshot-set hash mismatch: {filename}")
        if source_row.get("snapshotSetSha256") != snapshot_set_sha256:
            raise BuildError(f"Frozen manifest snapshot-set hash mismatch: {filename}")
        acquisitions.append(acquisition)
        for projected in source_records:
            if not isinstance(projected, Mapping):
                continue
            record = normalize_acquisition_record(
                projected,
                snapshot_id=snapshot_id,
                provenance=provenance,
            )
            if record is not None:
                records.append(record)

    normalised = unique_records(records)
    expected = sum(int(source.get("recordCount") or 0) for source in source_rows)
    if len(normalised) != expected:
        raise BuildError(
            f"Normalised record count {len(normalised)} does not match frozen count {expected}"
        )

    aliases = _read_json(inputs.evaluation_aliases)
    alias_rows = aliases.get("aliases")
    if not isinstance(alias_rows, Mapping):
        raise BuildError("Evaluation aliases register has no aliases object")
    records_by_id = {record["id"]: record for record in normalised}
    resolved_aliases: list[dict[str, str]] = []
    missing_alias_targets: list[dict[str, str]] = []
    for alias, canonical_id in sorted(alias_rows.items()):
        alias_text = str(alias)
        canonical_text = str(canonical_id)
        record = records_by_id.get(canonical_text)
        if record is None:
            missing_alias_targets.append({"alias": alias_text, "canonicalRecordId": canonical_text})
            continue
        record.setdefault("evaluation_aliases", []).append(alias_text)
        resolved_aliases.append({"alias": alias_text, "canonicalRecordId": canonical_text})
    for record in normalised:
        record["evaluation_aliases"] = sorted(record.get("evaluation_aliases", []))
    aliases["resolution"] = {
        "resolved": resolved_aliases,
        "resolvedCount": len(resolved_aliases),
        "missingTargets": missing_alias_targets,
        "missingTargetCount": len(missing_alias_targets),
        "curatedUnresolved": aliases.get("unresolved", []),
        "curatedUnresolvedCount": len(aliases.get("unresolved", [])),
        "releaseGateEnabled": False,
        "baselineStatus": "partial-source-coverage",
    }

    return FrozenCorpus(
        snapshot=snapshot,
        acquisitions=acquisitions,
        records=normalised,
        source_register=_read_json(inputs.source_register),
        standards_register=_read_json(inputs.standards_register),
        ontology_crosswalk=_read_json(inputs.ontology_crosswalk),
        aliases=aliases,
    )


def _chunks(
    writer: BundleWriter,
    prefix: str,
    rows: list[dict[str, Any]],
    *,
    size: int = CHUNK_SIZE,
) -> list[str]:
    paths: list[str] = []
    if not rows:
        path = f"data/{prefix}-0.json"
        writer.write_json(path, [])
        return [path]
    for offset in range(0, len(rows), size):
        path = f"data/{prefix}-{offset // size}.json"
        writer.write_json(path, rows[offset : offset + size])
        paths.append(path)
    return paths


def _generated_at(corpus: FrozenCorpus) -> str:
    values = [
        str(page.get("retrievedAt"))
        for acquisition in corpus.acquisitions
        for page in acquisition["provenance"].get("pages", [])
        if isinstance(page, Mapping) and page.get("retrievedAt")
    ]
    return max(values) if values else f"{corpus.snapshot['snapshotId']}T00:00:00Z"


def _source_counts(records: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    return dict(
        sorted(
            Counter(str(record.get("source_surface") or "unknown") for record in records).items()
        )
    )


def _source_temporal_evidence(provenance: Mapping[str, Any]) -> dict[str, str]:
    retrieved_at = max(
        (
            str(page.get("retrievedAt"))
            for page in provenance.get("pages", [])
            if isinstance(page, Mapping) and page.get("retrievedAt")
        ),
        default="",
    )
    submodule = provenance.get("submodule")
    submodule = submodule if isinstance(submodule, Mapping) else {}
    commit_as_of = str(submodule.get("commitAsOf") or "")
    if retrieved_at:
        source_as_of = retrieved_at
        basis = "acquisition-retrieved-at"
    elif commit_as_of:
        source_as_of = commit_as_of
        basis = "pinned-source-commit-as-of"
    else:
        source_as_of = ""
        basis = "not-evidenced"
    return {
        "sourceAsOf": source_as_of,
        "sourceAsOfBasis": basis,
        "acquisitionRetrievedAt": retrieved_at,
        "commitAsOf": commit_as_of,
    }


_PROVIDER_DATAPACK_SOURCE_SCHEMA = "okf-ons.provider-datapack-source.v1"
_PROVIDER_DATAPACK_SCHEMA = "okf-explorer-provider-datapack.v1"
_PROVIDER_DATAPACK_MANIFEST_SCHEMA = "okf-explorer-provider-datapack-manifest.v1"
_PROVIDER_DATAPACK_ROOT_KEYS = {
    "schema",
    "id",
    "provider",
    "selector",
    "snapshotExpectations",
    "reviewedLiveReference",
    "comparison",
    "presentation",
}
_PROVIDER_KEYS = {"id", "title", "liveServiceUrl", "repositoryUrl"}
_SELECTOR_KEYS = {"field", "operator", "value"}
_SNAPSHOT_EXPECTATION_KEYS = {"sourceCommit", "recordCount", "records"}
_RECORD_REFERENCE_KEYS = {
    "recordId",
    "title",
    "timeCoverageEnd",
    "metadataModified",
    "dataModified",
}
_LIVE_REFERENCE_KEYS = {
    "status",
    "label",
    "lastChecked",
    "network",
    "liveServiceUrl",
    "repositoryUrl",
    "sourceCommit",
    "sourceCommitAsOf",
    "metadataInputSha256",
    "records",
}
_COMPARISON_KEYS = {
    "status",
    "comparisonAsOf",
    "evidenceScope",
    "exhaustive",
    "summary",
    "executionRequiresLiveValidation",
}
_PRESENTATION_KEYS = {
    "snapshotLabel",
    "liveLabel",
    "lastCheckedWording",
    "notice",
    "actions",
}
_ACTION_KEYS = {"id", "label", "kind", "urlTemplate", "network"}
_COMPARISON_FIELDS = (
    ("title", "title"),
    ("timeCoverage.end", "timeCoverageEnd"),
    ("metadataModified", "metadataModified"),
    ("dataModified", "dataModified"),
)
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*$")
_SELECTOR_FIELD_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATE_TIME_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


def _exact_keys(value: Any, keys: set[str], context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BuildError(f"{context} must be an object")
    actual = set(value)
    if actual != keys:
        missing = sorted(keys - actual)
        unexpected = sorted(actual - keys)
        raise BuildError(f"{context} fields changed (missing={missing}, unexpected={unexpected})")
    return value


def _text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BuildError(f"{context} must be a non-empty string")
    return value.strip()


def _identifier(value: Any, context: str) -> str:
    text = _text(value, context)
    if not _IDENTIFIER_PATTERN.fullmatch(text):
        raise BuildError(f"{context} must be a safe identifier")
    return text


def _selector_field(value: Any, context: str) -> str:
    text = _text(value, context)
    if not _SELECTOR_FIELD_PATTERN.fullmatch(text):
        raise BuildError(f"{context} must be a safe record field")
    return text


def _date(value: Any, context: str) -> str:
    text = _text(value, context)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as exc:
        raise BuildError(f"{context} must be an RFC 3339 full-date") from exc
    if not _DATE_PATTERN.fullmatch(text) or parsed.isoformat() != text:
        raise BuildError(f"{context} must be an RFC 3339 full-date")
    return text


def _date_time(value: Any, context: str) -> str:
    text = _text(value, context)
    if not _DATE_TIME_PATTERN.fullmatch(text):
        raise BuildError(f"{context} must be an RFC 3339 date-time")
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise BuildError(f"{context} must be an RFC 3339 date-time") from exc
    return text


def _hex_digest(value: Any, length: int, context: str) -> str:
    text = _text(value, context).casefold()
    if len(text) != length or any(character not in "0123456789abcdef" for character in text):
        raise BuildError(f"{context} must be a {length}-character hexadecimal value")
    return text


def _https_url(value: Any, context: str, *, template: bool = False) -> str:
    text = _text(value, context)
    comparable = text.replace("{native_id}", "record") if template else text
    if template and ("{" in comparable or "}" in comparable):
        raise BuildError(f"{context} contains an unsupported template placeholder")
    if "\\" in comparable or any(character.isspace() for character in comparable):
        raise BuildError(f"{context} must be an absolute HTTPS URL without credentials")
    try:
        parsed = urlsplit(comparable)
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError as exc:
        raise BuildError(
            f"{context} must be an absolute HTTPS URL without credentials"
        ) from exc
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise BuildError(f"{context} must be an absolute HTTPS URL without credentials")
    if template:
        token_count = text.count("{native_id}")
        path_token_count = sum(
            unquote(segment) == "{native_id}" for segment in urlsplit(text).path.split("/")
        )
        if path_token_count != token_count:
            raise BuildError(
                f"{context} must use {{native_id}} as a complete pathname segment"
            )
    return text


def _record_reference(value: Any, context: str) -> dict[str, str]:
    row = _exact_keys(value, _RECORD_REFERENCE_KEYS, context)
    return {
        key: _text(row.get(key), f"{context}.{key}")
        for key in (
            "recordId",
            "title",
            "timeCoverageEnd",
            "metadataModified",
            "dataModified",
        )
    }


def _snapshot_record_reference(
    expected: Mapping[str, str],
    records_by_id: Mapping[str, Mapping[str, Any]],
    *,
    selector: Mapping[str, str],
) -> dict[str, str]:
    record_id = expected["recordId"]
    actual = records_by_id.get(record_id)
    if actual is None:
        raise BuildError(f"provider datapack snapshot record is absent: {record_id}")
    if actual.get(selector["field"]) != selector["value"]:
        raise BuildError(
            f"provider datapack snapshot record does not match its selector: {record_id}"
        )
    actual_reference = {
        "recordId": record_id,
        "title": str(actual.get("title") or ""),
        "timeCoverageEnd": str(
            (actual.get("time_coverage") or {}).get("end")
            if isinstance(actual.get("time_coverage"), Mapping)
            else ""
        ),
        "metadataModified": str(actual.get("metadata_modified") or ""),
        "dataModified": str(actual.get("data_modified") or ""),
    }
    for reference_field, expected_value in expected.items():
        if actual_reference.get(reference_field) != expected_value:
            raise BuildError(
                f"provider datapack frozen {record_id} {reference_field} changed: "
                f"expected {expected_value!r}, "
                f"found {actual_reference.get(reference_field)!r}"
            )
    return actual_reference


def _provider_datapack(
    source: Mapping[str, Any],
    corpus: FrozenCorpus,
    *,
    path: Path,
) -> dict[str, Any]:
    root = _exact_keys(source, _PROVIDER_DATAPACK_ROOT_KEYS, f"provider datapack {path.name}")
    if root.get("schema") != _PROVIDER_DATAPACK_SOURCE_SCHEMA:
        raise BuildError(f"unsupported provider datapack source schema: {path.name}")
    pack_id = _identifier(root.get("id"), f"provider datapack {path.name}.id")
    if path.stem != pack_id:
        raise BuildError(f"provider datapack filename does not match id: {path.name}")

    provider_source = _exact_keys(
        root.get("provider"), _PROVIDER_KEYS, f"provider datapack {pack_id}.provider"
    )
    provider = {
        "id": _identifier(
            provider_source.get("id"), f"provider datapack {pack_id}.provider.id"
        ),
        "title": _text(provider_source.get("title"), f"provider datapack {pack_id}.provider.title"),
        "liveServiceUrl": _https_url(
            provider_source.get("liveServiceUrl"),
            f"provider datapack {pack_id}.provider.liveServiceUrl",
        ),
        "repositoryUrl": _https_url(
            provider_source.get("repositoryUrl"),
            f"provider datapack {pack_id}.provider.repositoryUrl",
        ),
    }
    if provider["id"] != pack_id:
        raise BuildError(f"provider datapack provider id differs from pack id: {pack_id}")

    selector_source = _exact_keys(
        root.get("selector"), _SELECTOR_KEYS, f"provider datapack {pack_id}.selector"
    )
    selector = {
        "field": _selector_field(
            selector_source.get("field"), f"provider datapack {pack_id}.selector.field"
        ),
        "operator": _text(
            selector_source.get("operator"), f"provider datapack {pack_id}.selector.operator"
        ),
        "value": _text(selector_source.get("value"), f"provider datapack {pack_id}.selector.value"),
    }
    if selector["operator"] != "equals":
        raise BuildError(f"provider datapack {pack_id} supports only the equals selector")
    selected = [
        record for record in corpus.records if record.get(selector["field"]) == selector["value"]
    ]
    if not selected:
        raise BuildError(f"provider datapack selector matches no records: {pack_id}")

    expectations = _exact_keys(
        root.get("snapshotExpectations"),
        _SNAPSHOT_EXPECTATION_KEYS,
        f"provider datapack {pack_id}.snapshotExpectations",
    )
    expected_commit = _hex_digest(
        expectations.get("sourceCommit"),
        40,
        f"provider datapack {pack_id}.snapshotExpectations.sourceCommit",
    )
    expected_count = expectations.get("recordCount")
    if (
        not isinstance(expected_count, int)
        or isinstance(expected_count, bool)
        or expected_count < 1
    ):
        raise BuildError(
            f"provider datapack {pack_id}.snapshotExpectations.recordCount must be positive"
        )
    if len(selected) != expected_count:
        raise BuildError(
            f"provider datapack {pack_id} frozen record count changed: "
            f"expected {expected_count}, found {len(selected)}"
        )
    source_commits = {
        str((record.get("provenance") or {}).get("source_commit") or "")
        for record in selected
        if isinstance(record.get("provenance"), Mapping)
    }
    if source_commits != {expected_commit}:
        raise BuildError(
            f"provider datapack {pack_id} frozen source commit changed: "
            f"expected {expected_commit}, found {sorted(source_commits)}"
        )
    expected_records_source = expectations.get("records")
    if not isinstance(expected_records_source, list) or not expected_records_source:
        raise BuildError(
            f"provider datapack {pack_id}.snapshotExpectations.records must be non-empty"
        )
    expected_records = [
        _record_reference(row, f"provider datapack {pack_id}.snapshotExpectations.records[{index}]")
        for index, row in enumerate(expected_records_source)
    ]
    expected_ids = [row["recordId"] for row in expected_records]
    if len(expected_ids) != len(set(expected_ids)):
        raise BuildError(f"provider datapack {pack_id} has duplicate snapshot record ids")
    records_by_id = {str(record["id"]): record for record in corpus.records}
    snapshot_records = [
        _snapshot_record_reference(row, records_by_id, selector=selector)
        for row in expected_records
    ]

    live_source = _exact_keys(
        root.get("reviewedLiveReference"),
        _LIVE_REFERENCE_KEYS,
        f"provider datapack {pack_id}.reviewedLiveReference",
    )
    if live_source.get("status") != "reviewed-reference-not-live-validated":
        raise BuildError(
            f"provider datapack {pack_id} live reference must be "
            "reviewed-reference-not-live-validated"
        )
    if live_source.get("network") != "external":
        raise BuildError(f"provider datapack {pack_id} live reference must be external")
    live_records_source = live_source.get("records")
    if not isinstance(live_records_source, list) or not live_records_source:
        raise BuildError(f"provider datapack {pack_id} live records must be non-empty")
    live_records = [
        _record_reference(
            row, f"provider datapack {pack_id}.reviewedLiveReference.records[{index}]"
        )
        for index, row in enumerate(live_records_source)
    ]
    if [row["recordId"] for row in live_records] != expected_ids:
        raise BuildError(
            f"provider datapack {pack_id} live record ids must match snapshot examples"
        )
    reviewed_live_reference = {
        "status": "reviewed-reference-not-live-validated",
        "label": _text(
            live_source.get("label"),
            f"provider datapack {pack_id}.reviewedLiveReference.label",
        ),
        "lastChecked": _date(
            live_source.get("lastChecked"),
            f"provider datapack {pack_id}.reviewedLiveReference.lastChecked",
        ),
        "network": "external",
        "liveServiceUrl": _https_url(
            live_source.get("liveServiceUrl"),
            f"provider datapack {pack_id}.reviewedLiveReference.liveServiceUrl",
        ),
        "repositoryUrl": _https_url(
            live_source.get("repositoryUrl"),
            f"provider datapack {pack_id}.reviewedLiveReference.repositoryUrl",
        ),
        "sourceCommit": _hex_digest(
            live_source.get("sourceCommit"),
            40,
            f"provider datapack {pack_id}.reviewedLiveReference.sourceCommit",
        ),
        "sourceCommitAsOf": _date_time(
            live_source.get("sourceCommitAsOf"),
            f"provider datapack {pack_id}.reviewedLiveReference.sourceCommitAsOf",
        ),
        "metadataInputSha256": _hex_digest(
            live_source.get("metadataInputSha256"),
            64,
            f"provider datapack {pack_id}.reviewedLiveReference.metadataInputSha256",
        ),
        "records": live_records,
    }
    reviewed_live_reference["sourceCommitShort"] = reviewed_live_reference["sourceCommit"][:7]
    if reviewed_live_reference["liveServiceUrl"] != provider["liveServiceUrl"]:
        raise BuildError(f"provider datapack {pack_id} live service URLs disagree")
    if reviewed_live_reference["repositoryUrl"] != provider["repositoryUrl"]:
        raise BuildError(f"provider datapack {pack_id} repository URLs disagree")

    comparison_source = _exact_keys(
        root.get("comparison"),
        _COMPARISON_KEYS,
        f"provider datapack {pack_id}.comparison",
    )
    if comparison_source.get("status") != "known-drift":
        raise BuildError(f"provider datapack {pack_id} comparison must be known-drift")
    if comparison_source.get("evidenceScope") != "reviewed-record-examples":
        raise BuildError(
            f"provider datapack {pack_id} comparison evidence scope must be "
            "reviewed-record-examples"
        )
    if comparison_source.get("exhaustive") is not False:
        raise BuildError(
            f"provider datapack {pack_id} comparison must be explicitly non-exhaustive"
        )
    if comparison_source.get("executionRequiresLiveValidation") is not True:
        raise BuildError(f"provider datapack {pack_id} execution must require live validation")
    comparison_as_of = _date(
        comparison_source.get("comparisonAsOf"),
        f"provider datapack {pack_id}.comparison.comparisonAsOf",
    )
    if comparison_as_of != reviewed_live_reference["lastChecked"]:
        raise BuildError(
            f"provider datapack {pack_id} comparison date must equal last checked date"
        )
    live_by_id = {row["recordId"]: row for row in live_records}
    differences: list[dict[str, Any]] = []
    for snapshot_record in snapshot_records:
        live_record = live_by_id[snapshot_record["recordId"]]
        fields = [
            {
                "field": public_field,
                "snapshot": snapshot_record[source_field],
                "reviewedLiveReference": live_record[source_field],
            }
            for public_field, source_field in _COMPARISON_FIELDS
            if snapshot_record[source_field] != live_record[source_field]
        ]
        if fields:
            differences.append(
                {
                    "recordId": snapshot_record["recordId"],
                    "title": snapshot_record["title"],
                    "fields": fields,
                }
            )
    if not differences:
        raise BuildError(f"provider datapack {pack_id} declares known-drift without a difference")
    if reviewed_live_reference["sourceCommit"] == expected_commit:
        raise BuildError(f"provider datapack {pack_id} known-drift commits must be different")

    presentation_source = _exact_keys(
        root.get("presentation"),
        _PRESENTATION_KEYS,
        f"provider datapack {pack_id}.presentation",
    )
    actions_source = presentation_source.get("actions")
    if not isinstance(actions_source, list) or not actions_source:
        raise BuildError(f"provider datapack {pack_id} must declare presentation actions")
    actions: list[dict[str, str]] = []
    for index, action_source in enumerate(actions_source):
        context = f"provider datapack {pack_id}.presentation.actions[{index}]"
        action_row = _exact_keys(action_source, _ACTION_KEYS, context)
        if action_row.get("kind") != "external-link" or action_row.get("network") != "external":
            raise BuildError(f"{context} must be an external-link on the external network")
        actions.append(
            {
                "id": _identifier(action_row.get("id"), f"{context}.id"),
                "label": _text(action_row.get("label"), f"{context}.label"),
                "kind": "external-link",
                "urlTemplate": _https_url(
                    action_row.get("urlTemplate"), f"{context}.urlTemplate", template=True
                ),
                "network": "external",
            }
        )
    if len({action["id"] for action in actions}) != len(actions):
        raise BuildError(f"provider datapack {pack_id} presentation action ids repeat")
    presentation = {
        "snapshotLabel": _text(
            presentation_source.get("snapshotLabel"),
            f"provider datapack {pack_id}.presentation.snapshotLabel",
        ),
        "liveLabel": _text(
            presentation_source.get("liveLabel"),
            f"provider datapack {pack_id}.presentation.liveLabel",
        ),
        "lastCheckedWording": _text(
            presentation_source.get("lastCheckedWording"),
            f"provider datapack {pack_id}.presentation.lastCheckedWording",
        ),
        "notice": _text(
            presentation_source.get("notice"),
            f"provider datapack {pack_id}.presentation.notice",
        ),
        "actions": actions,
    }
    if (
        not presentation["lastCheckedWording"].startswith("Live reference last checked ")
        or "not live-validated" not in presentation["lastCheckedWording"]
    ):
        raise BuildError(
            f"provider datapack {pack_id} last-checked wording must state that the "
            "reference is not live-validated"
        )

    source_provenance = {
        (
            str(provenance.get("source_as_of") or ""),
            str(provenance.get("source_as_of_basis") or ""),
        )
        for record in selected
        for provenance in [
            record.get("provenance")
            if isinstance(record.get("provenance"), Mapping)
            else {}
        ]
    }
    if len(source_provenance) != 1 or any(not value for value in next(iter(source_provenance), ())):
        raise BuildError(
            f"provider datapack {pack_id} source provenance differs across selected records"
        )
    source_as_of, source_as_of_basis = next(iter(source_provenance))
    source_as_of = _date_time(
        source_as_of, f"provider datapack {pack_id} source_as_of"
    )
    return {
        "schema": _PROVIDER_DATAPACK_SCHEMA,
        "snapshot": corpus.snapshot["snapshotId"],
        "id": pack_id,
        "provider": provider,
        "selector": selector,
        "governedSnapshot": {
            "status": "governed-pinned-snapshot",
            "label": presentation["snapshotLabel"],
            "snapshotId": corpus.snapshot["snapshotId"],
            "recordCount": len(selected),
            "sourceCommit": expected_commit,
            "sourceCommitShort": expected_commit[:7],
            "sourceAsOf": source_as_of,
            "sourceAsOfBasis": source_as_of_basis,
            "metadataOnly": True,
            "observationsIncluded": False,
            "records": snapshot_records,
        },
        "reviewedLiveReference": reviewed_live_reference,
        "comparison": {
            "status": "known-drift",
            "comparisonAsOf": comparison_as_of,
            "evidenceScope": "reviewed-record-examples",
            "exhaustive": False,
            "summary": _text(
                comparison_source.get("summary"),
                f"provider datapack {pack_id}.comparison.summary",
            ),
            "executionRequiresLiveValidation": True,
            "differences": differences,
        },
        "presentation": presentation,
    }


def build_provider_datapacks(
    corpus: FrozenCorpus,
    source_directory: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Validate provider source declarations and derive snapshot-bound public packs."""

    if not source_directory.is_dir():
        raise BuildError(f"provider datapack source directory is missing: {source_directory}")
    paths = sorted(source_directory.glob("*.json"))
    if not paths:
        raise BuildError("provider datapack source directory contains no JSON packs")
    packs = [_provider_datapack(_read_json(path), corpus, path=path) for path in paths]
    ids = [pack["id"] for pack in packs]
    if len(ids) != len(set(ids)):
        raise BuildError("provider datapack ids must be unique")
    manifest = {
        "schema": _PROVIDER_DATAPACK_MANIFEST_SCHEMA,
        "snapshot": corpus.snapshot["snapshotId"],
        "packCount": len(packs),
        "packs": [
            {
                "id": pack["id"],
                "selector": pack["selector"],
                "path": f"data/providers/{pack['id']}.json",
                "sha256": _sha256_bytes(canonical_json(pack).encode("utf-8")),
                "status": pack["comparison"]["status"],
                "lastChecked": pack["reviewedLiveReference"]["lastChecked"],
            }
            for pack in packs
        ],
    }
    return packs, manifest


def _coverage_ledger(corpus: FrozenCorpus) -> dict[str, Any]:
    implemented: list[dict[str, Any]] = []
    for acquisition in corpus.acquisitions:
        provenance = acquisition["provenance"]
        source = provenance["source"]
        implemented.append(
            {
                "sourceId": source["id"],
                "title": source["title"],
                "endpoint": source["endpoint"],
                "reportedTotal": provenance.get("reportedTotal"),
                "represented": provenance["recordCount"],
                "upstreamRecordsSeen": provenance["upstreamRecordsSeen"],
                "normalisationDropped": provenance["normalisationDroppedCount"],
                "unrepresented": provenance.get("unrepresentedCount"),
                "coverageComplete": provenance["coverageComplete"],
                "pageCount": provenance["pageCount"],
                "recordSetSha256": provenance["recordSetSha256"],
                "snapshotSetSha256": provenance["snapshotSetSha256"],
                "metadataOnly": provenance["assurance"]["metadataOnly"],
                **_source_temporal_evidence(provenance),
                "explainedExclusions": provenance.get("explainedExclusions", []),
                "freshnessPolicy": {"status": "not-defined", "validThrough": None},
            }
        )
    planned = corpus.source_register.get("reconciliationSourceLedger", {}).get("lanes", [])
    implemented_total = sum(row["represented"] for row in implemented)
    reported_total = sum(int(row["reportedTotal"] or 0) for row in implemented)
    implemented_omissions = sum(int(row["unrepresented"] or 0) for row in implemented)
    return {
        "schema": "okf-ons-coverage-ledger.v1",
        "snapshotId": corpus.snapshot["snapshotId"],
        "status": "demonstrator",
        "source_count": len(implemented),
        "record_count": implemented_total,
        "allOnsMetadataClaim": False,
        "unexplained_omissions": None,
        "claim": (
            "The implemented registered adapters close their reported denominators. "
            "The broader all-ONS claim remains disabled until every planned lane has "
            "a bounded denominator and zero unexplained omissions."
        ),
        "implementedScope": {
            "reportedTotal": reported_total,
            "represented": implemented_total,
            "implementedLaneUnexplainedOmissions": implemented_omissions,
            "explainedExclusionCount": sum(
                len(row["explainedExclusions"])
                for row in implemented
                if isinstance(row["explainedExclusions"], list)
            ),
            "coverageComplete": all(row["coverageComplete"] for row in implemented),
            "nonAdditivityWarning": (
                "Source counts are catalogue representations and can describe the same "
                "statistical product; they are not a unique-product count."
            ),
            "sources": implemented,
        },
        "wholeScope": {
            "implementedLaneCount": len(implemented),
            "plannedLaneCount": len(planned),
            "denominatorStatus": "incomplete",
            "plannedLanes": planned,
        },
        "releaseGate": {
            "rule": "all in-scope lanes bounded and unexplained_omissions = 0",
            "passed": False,
            "reason": "Five reconciliation lanes remain planned without closed denominators.",
        },
    }


def _quality_and_standards_summary(corpus: FrozenCorpus) -> dict[str, Any]:
    standards = corpus.standards_register.get("standards", [])
    requirements = [
        requirement
        for standard in standards
        if isinstance(standard, Mapping)
        for requirement in standard.get("requirements", [])
        if isinstance(requirement, Mapping)
    ]
    records = corpus.records
    methodology = sum(bool(record.get("methodology_links")) for record in records)
    quality = sum(bool(record.get("quality_links")) for record in records)
    provenance = sum(bool(record.get("provenance")) for record in records)
    dimensions = sum(bool(record.get("dimensions")) for record in records)
    return {
        "schema": "okf-ons-standards-evaluation.v1",
        "snapshotId": corpus.snapshot["snapshotId"],
        "registerSchema": corpus.standards_register.get("schemaVersion"),
        "standardCount": len(standards),
        "requirementCount": len(requirements),
        "currentAsOf": max(
            (
                str(standard.get("currentAsOf"))
                for standard in standards
                if isinstance(standard, Mapping) and standard.get("currentAsOf")
            ),
            default="",
        ),
        "profileAlignment": {
            "status": "partial",
            "claim": (
                "The bundle maps evidence to the registered standards and ontologies. "
                "This is not certification of ONS products or legal compliance."
            ),
            "ontologyCrosswalk": "data/standards/ontology-crosswalk.json",
        },
        "recordEvidenceAvailability": {
            "denominator": len(records),
            "methodologyLinks": methodology,
            "qualityDocumentationLinks": quality,
            "provenance": provenance,
            "dimensionMetadata": dimensions,
        },
        "statisticalAccuracy": {
            "evaluated": False,
            "score": None,
            "statement": (
                "Metadata evidence availability does not establish the accuracy of "
                "observations, estimates, calculations or interpretations."
            ),
        },
        "statusVocabulary": [
            "aligned",
            "partial",
            "not-evaluated",
            "not-applicable",
        ],
        "standards": [
            {
                "id": standard.get("id"),
                "title": standard.get("title"),
                "canonicalUri": standard.get("canonicalUri"),
                "category": standard.get("category"),
                "normativeStatus": standard.get("normativeStatus"),
                "requirementCount": len(standard.get("requirements", [])),
            }
            for standard in standards
            if isinstance(standard, Mapping)
        ],
    }


def _sdmx_implementation(corpus: FrozenCorpus) -> dict[str, Any]:
    standards = [
        standard
        for standard in corpus.standards_register.get("standards", [])
        if isinstance(standard, Mapping) and standard.get("id") == "sdmx-3-1"
    ]
    if len(standards) != 1:
        raise BuildError("Standards register must contain exactly one sdmx-3-1 entry")
    standard = standards[0]
    mappings = [
        {
            "field": field.get("field"),
            "term": mapping.get("term"),
            "mappingKind": mapping.get("mappingKind"),
            "notes": mapping.get("notes"),
        }
        for field in corpus.ontology_crosswalk.get("canonicalFields", [])
        if isinstance(field, Mapping)
        for mapping in field.get("mappings", [])
        if isinstance(mapping, Mapping) and mapping.get("standardId") == "sdmx-3-1"
    ]
    expected_fields = {
        "concept",
        "dimensions",
        "codeLists",
        "selectionConstraints",
        "frequency",
        "measure",
        "unit",
    }
    mapped_fields = {str(mapping["field"]) for mapping in mappings}
    if mapped_fields != expected_fields or len(mappings) != len(expected_fields):
        raise BuildError("SDMX crosswalk must contain exactly the seven canonical mappings")

    nomis_records = [
        record for record in corpus.records if record.get("source_surface") == "nomis"
    ]
    sdmx_structures = [
        record.get("sdmx")
        for record in nomis_records
        if isinstance(record.get("sdmx"), Mapping)
    ]
    dimensions = [
        dimension
        for structure in sdmx_structures
        for dimension in structure.get("dimensions", [])
        if isinstance(dimension, Mapping)
    ]
    components = [
        component
        for structure in sdmx_structures
        for component in structure.get("components", [])
        if isinstance(component, Mapping)
    ]
    query_tools = sorted(
        {
            str(record.get("selection", {}).get("query_tool"))
            for record in nomis_records
            if record.get("selection", {}).get("query_tool")
        }
    )
    serialization = corpus.ontology_crosswalk.get("serializationBoundary", {})
    return {
        "schema": "okf-ons-sdmx-implementation.v1",
        "snapshotId": corpus.snapshot["snapshotId"],
        "registeredStandard": {
            "standardId": standard.get("id"),
            "title": standard.get("title"),
            "category": standard.get("category"),
            "canonicalUri": standard.get("canonicalUri"),
            "normativeStatus": standard.get("normativeStatus"),
            "requirementCount": len(standard.get("requirements", [])),
            "claim": "Evidence mapping and profile alignment; not certification.",
        },
        "ontologyCrosswalk": {
            "path": "data/standards/ontology-crosswalk.json",
            "mappingCount": len(mappings),
            "mappings": mappings,
            "identityPolicy": corpus.ontology_crosswalk.get("sdmxIdentityPolicy", {}),
        },
        "upstreamNomis": {
            "sourceSurface": "nomis",
            "sourceAdapter": "nomis-sdmx",
            "recordCount": len(nomis_records),
            "dimensionMetadata": len(sdmx_structures),
            "sdmxIdentity": {
                "agency": sum(
                    bool(structure.get("identity", {}).get("agency"))
                    for structure in sdmx_structures
                ),
                "identifier": sum(
                    bool(structure.get("identity", {}).get("identifier"))
                    for structure in sdmx_structures
                ),
                "version": sum(
                    bool(structure.get("identity", {}).get("version"))
                    for structure in sdmx_structures
                ),
            },
            "dimensionOrderPreserved": bool(dimensions)
            and all(
                isinstance(dimension.get("position"), int)
                and not isinstance(dimension.get("position"), bool)
                for dimension in dimensions
            ),
            "dsdRolesPreserved": bool(components)
            and all(bool(component.get("role")) for component in components),
            "selectionBindings": {
                "complete": sum(
                    record.get("selection", {}).get("complete") is True
                    for record in nomis_records
                ),
                "incomplete": sum(
                    record.get("selection", {}).get("complete") is not True
                    for record in nomis_records
                ),
                "queryTools": query_tools,
                "reason": (
                    "Nomis dimensions and codelist values must be selected before querying."
                ),
            },
        },
        "serializationBoundary": {
            **serialization,
            "contextPath": "context/okf-ons.jsonld",
            "sdmxNamespacePresent": "sdmx" in corpus.ontology_crosswalk.get("namespaces", {}),
        },
        "assuranceBoundary": (
            "The SDMX mappings support discovery and exchange. They do not assert "
            "that upstream ONS or Nomis products conform to SDMX 3.1."
        ),
    }


def _resource_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": f"{record['id']}#source",
            "name": f"{record['name']}-source",
            "title": f"Official metadata source for {record['title']}",
            "description": (
                "Metadata-only source endpoint for discovery and query planning; "
                "no observation values are stored in this bundle."
            ),
            "dataset": record["name"],
            "dataset_id": record["id"],
            "dataset_route": record["route"],
            "route": f"resource/{record['name']}-source",
            "url": record.get("url", ""),
            "host": record.get("host", ""),
            "documentation": record.get("documentation", ""),
            "format": next(iter(record.get("formats", [])), "Metadata"),
            "source_format": next(iter(record.get("formats", [])), ""),
            "formats": record.get("formats", []),
            "protocol": record.get("protocol", []),
            "resource_type": "metadata",
            "position": 0,
            "created": record.get("metadata_created", ""),
            "last_modified": record.get("metadata_modified", ""),
            "metadata_modified": record.get("metadata_modified", ""),
            "source_surface": record.get("source_surface"),
            "selection": record.get("selection", {}),
            "provenance": record.get("provenance", {}),
            "authority": record.get("authority", {}),
            "metadata_only": True,
            "metadata_derivation": (
                {
                    "schema": "okf-ons-field-derivation.v1",
                    "modes": ["deterministic-extraction"],
                    "fields": {
                        "host": {
                            "mode": "deterministic-extraction",
                            "sourceField": "url",
                            "rule": "public-url-host-v1",
                        }
                    },
                }
                if record.get("host")
                else {}
            ),
        }
        for record in records
    ]


def _publisher_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build source-publisher facets without implying bundle endorsement."""

    counts: Counter[str] = Counter()
    publishers: dict[str, dict[str, str]] = {}
    for record in records:
        parties = record.get("source_publishers")
        if not isinstance(parties, list) or not parties:
            parties = [
                {
                    "id": record.get("publisher") or "unknown-source-publisher",
                    "name": record.get("publisher_title") or "Unknown source publisher",
                    "url": record.get("publisher_uri") or "",
                }
            ]
        seen: set[str] = set()
        for party in parties:
            if not isinstance(party, Mapping):
                continue
            publisher_id = str(party.get("id") or "").strip()
            if not publisher_id or publisher_id in seen:
                continue
            seen.add(publisher_id)
            counts[publisher_id] += 1
            publishers.setdefault(
                publisher_id,
                {
                    "name": publisher_id,
                    "title": str(party.get("name") or publisher_id),
                    "url": str(party.get("url") or ""),
                },
            )
    return [
        {
            "id": publisher_id,
            **publishers[publisher_id],
            "route": f"publisher/{publisher_id}",
            "dataset_count": counts[publisher_id],
            "resource_count": counts[publisher_id],
            "description": (
                "Source producer attribution carried from frozen metadata. "
                "It does not imply endorsement of this OKF bundle."
            ),
        }
        for publisher_id in sorted(publishers)
    ]


def _mcp_bindings(records: list[dict[str, Any]], snapshot_id: str) -> dict[str, Any]:
    available = sum(record.get("selection", {}).get("mcp_available") is True for record in records)
    return {
        "schema": "okf-ons-mcp-bindings.v1",
        "snapshotId": snapshot_id,
        "readOnly": True,
        "credentialsStored": False,
        "observationValuesStored": False,
        "contract": "browse-reduce-compare-configure-execute",
        "availableBindingCount": available,
        "plannedBindingCount": len(records) - available,
        "bindings": [
            {
                "record_id": record["id"],
                "native_id": record["native_id"],
                "source_surface": record["source_surface"],
                **record.get("selection", {}),
            }
            for record in records
        ],
        "executionBoundary": (
            "The static bundle prepares a selection. A trusted MCP server validates "
            "current versions, dimensions and options before any live query."
        ),
    }


def _numeric_points(value: Any) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    if isinstance(value, list):
        if (
            len(value) >= 2
            and isinstance(value[0], (int, float))
            and not isinstance(value[0], bool)
            and isinstance(value[1], (int, float))
            and not isinstance(value[1], bool)
        ):
            x = float(value[0])
            y = float(value[1])
            if math.isfinite(x) and math.isfinite(y):
                points.append((x, y))
        else:
            for child in value:
                points.extend(_numeric_points(child))
    return points


def _portal_bbox(record: Mapping[str, Any]) -> list[float]:
    extent = record.get("portal_extent")
    if not isinstance(extent, Mapping):
        return []
    points = _numeric_points(extent.get("coordinates"))
    if not points:
        return []
    if any(abs(x) > 180 or abs(y) > 90 for x, y in points):
        return []
    return [
        min(point[0] for point in points),
        min(point[1] for point in points),
        max(point[0] for point in points),
        max(point[1] for point in points),
    ]


def _spatial_index(records: list[dict[str, Any]], snapshot_id: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for record in records:
        if record.get("source_surface") != "ons-open-geography":
            continue
        bbox = record.get("spatial", {}).get("bbox") or _portal_bbox(record)
        if not bbox and not record.get("spatial_reference"):
            continue
        rows.append(
            {
                "record_id": record["id"],
                "title": record["title"],
                "route": record["route"],
                "bbox": bbox,
                "bbox_evidence": "portal-extent" if bbox else "not-evidenced",
                "coordinate_interpretation": (
                    "source portal extent; no CRS transformation inferred"
                    if bbox
                    else "not-evidenced"
                ),
                "source_spatial_reference": record.get("spatial_reference") or None,
                "geography": record.get("geography", []),
                "url": record.get("url", ""),
            }
        )
    return {
        "schema": "okf-ons-spatial-index.v1",
        "snapshotId": snapshot_id,
        "geometryIncluded": False,
        "recordCount": len(rows),
        "recordsWithBbox": sum(bool(row["bbox"]) for row in rows),
        "records": rows,
    }


def _materialize_explorer_fields(records: list[dict[str, Any]]) -> None:
    """Keep hydrated dataset rows consistent with worker filters and map views."""

    for record in records:
        for key in (
            "metadata_evidence_band",
            "has_methodology",
            "has_quality_documentation",
            "has_alternatives",
        ):
            values = filter_values(record, key)
            record[key] = values[0] if values else MISSING_FILTER_VALUE
        if record.get("source_surface") != "ons-open-geography":
            continue
        bbox = record.get("spatial", {}).get("bbox") or _portal_bbox(record)
        if bbox:
            record["bbox"] = bbox
            record["bbox_evidence"] = "source-portal-extent"
            record["coordinate_interpretation"] = (
                "Source portal extent; no CRS transformation inferred."
            )


def _demo_projection(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Select a broad, bounded UI projection while Explorer indexes every record."""

    discovery_terms = (
        "population",
        "consumer price",
        "inflation",
        "unemployment",
        "claimant",
        "earnings",
        "migration",
        "deaths",
        "household",
        "occupancy",
        "local authority",
        "ward",
        "boundary",
        "postcode",
        "lookup",
        "census",
    )
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()

    def add(record: dict[str, Any]) -> None:
        if record["id"] not in selected_ids:
            selected.append(record)
            selected_ids.add(record["id"])

    # The ONS Data API lane is small and central to the MCP hand-off.
    for record in records:
        if record["source_surface"] == "ons-data-api":
            add(record)
    # Every resolved gold-suite identity must remain demonstrable.
    for record in records:
        if record.get("evaluation_aliases"):
            add(record)
    # Sample each other lane, then deliberately cover high-value discovery
    # concepts rather than taking only an alphabetical prefix.
    for source in sorted(
        {record["source_surface"] for record in records} - {"ons-data-api"}
    ):
        source_records = [record for record in records if record["source_surface"] == source]
        for record in source_records[:50]:
            add(record)
        for term in discovery_terms:
            matched = [
                record
                for record in source_records
                if term in f"{record['title']} {record.get('notes', '')}".casefold()
            ]
            for record in matched[:30]:
                add(record)
    # Keep one-hop alternatives visible, bounded for reliable conference Wi-Fi.
    records_by_id = {record["id"]: record for record in records}
    for record in list(selected):
        for alternative in record.get("alternatives", []):
            target = records_by_id.get(str(alternative.get("record_id") or ""))
            if target is not None:
                add(target)
            if len(selected) >= 1_200:
                break
        if len(selected) >= 1_200:
            break
    return selected[:1_200]


def _evaluation_standard_claims(record: Mapping[str, Any]) -> dict[str, Any]:
    provenance = record.get("provenance") or {}
    timestamp = record.get("metadata_modified") or provenance.get("retrieved_at")
    dimensions = record.get("dimensions") or []
    geography_evidence = record.get("geography") or record.get("declared_table_codes")
    return {
        "DCAT-AP": {
            "status": "partial",
            "evidence": {
                "identifier": record.get("id"),
                "title": record.get("title"),
                "landingPage": record.get("url"),
            },
        },
        "SDMX": {
            "status": (
                "aligned"
                if record.get("source_surface") == "nomis"
                else "partial"
                if dimensions
                else "not-applicable"
            ),
            **(
                {"evidence": {"dimensions": dimensions, "source": record.get("source_surface")}}
                if record.get("source_surface") == "nomis" or dimensions
                else {}
            ),
        },
        "ISO 8601": {
            "status": "partial" if timestamp else "not-evaluated",
            **({"evidence": {"timestamp": timestamp}} if timestamp else {}),
        },
        "PROV-O": {
            "status": "aligned" if provenance else "not-evaluated",
            **({"evidence": provenance} if provenance else {}),
        },
        "GSS geography codes": {
            "status": "partial" if geography_evidence else "not-evaluated",
            **({"evidence": geography_evidence} if geography_evidence else {}),
        },
    }


def _evaluation_contrast(record: Mapping[str, Any]) -> dict[str, Any]:
    statistical = record.get("statistical") or {}
    return {
        "measure_concept": statistical.get("measure"),
        "unit": statistical.get("unit"),
        "population_scope": statistical.get("population"),
        "geography": statistical.get("geography"),
        "reference_period": statistical.get("time_coverage"),
        "frequency": statistical.get("frequency"),
        "method": record.get("methodology_links"),
        "revision_basis": record.get("revision_status"),
        "official_status": record.get("national_statistic"),
        "data_source": record.get("source_surface"),
        "estimate_maturity": record.get("state"),
        "time_lag": record.get("next_release"),
        "estimate_or_projection": record.get("title"),
        "population_basis": statistical.get("population"),
        "denominator": record.get("unit_of_measure"),
        "housing_cost_treatment": record.get("notes"),
    }


def _baseline_evaluation(
    corpus: FrozenCorpus,
    gold_suite_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    suite = load_gold_suite(gold_suite_path)
    maximum_depth = max(
        max(suite["defaults"]["cutoffs"]),
        max(
            alternative["must_expose_by"]
            for query in suite["queries"]
            for alternative in query["alternatives"]
        ),
    )
    ranking_rows: list[dict[str, Any]] = []
    for query in suite["queries"]:
        ranked = rank_records(corpus.records, query["query"], limit=maximum_depth)
        results: list[dict[str, Any]] = []
        for record in ranked:
            aliases = record.get("evaluation_aliases", [])
            evaluation_id = aliases[0] if aliases else record["id"]
            results.append(
                {
                    "record_id": evaluation_id,
                    "canonical_record_id": record["id"],
                    "metadata": {
                        "title": record.get("title"),
                        "identity": record.get("identity", {}),
                        "provenance": record.get("provenance", {}),
                        "publication": record.get("publication", {}),
                        "statistical": record.get("statistical", {}),
                    },
                    "contrast": _evaluation_contrast(record),
                    "standards": _evaluation_standard_claims(record),
                }
            )
        ranking_rows.append(
            {
                "query_id": query["id"],
                "query": query["query"],
                "results": results,
            }
        )
    rankings = {
        "schema": "okf-ons-evaluation-rankings.v1",
        "system": "okf-ons-static-weighted-baseline",
        "snapshotId": corpus.snapshot["snapshotId"],
        "releaseGateEnabled": False,
        "coverageStatus": "partial-source-coverage",
        "queries": ranking_rows,
    }
    report = evaluate_rankings(suite, rankings)
    unresolved_count = corpus.aliases["resolution"]["missingTargetCount"]
    implemented_source_count = len(_source_counts(corpus.records))
    report["release_gate"] = {
        "enabled": False,
        "reason": (
            f"The baseline runs all questions, but {unresolved_count} curated aliases "
            f"are explicitly unresolved by the {implemented_source_count} implemented "
            "source lanes."
        ),
    }
    report["alias_resolution"] = corpus.aliases["resolution"]
    return rankings, report


def _write_search(writer: BundleWriter, search: dict[str, Any]) -> None:
    writer.write_json("data/search/manifest.json", search["manifest"])
    for shard, payload in search["lexicon"].items():
        writer.write_json(f"data/search/lexicon/{shard}.json", payload)
    for shard, payload in search["prefixes"].items():
        writer.write_json(f"data/search/prefixes/{shard}.json", payload)
    for path, payload in search["postings"].items():
        writer.write_json(path, payload)
    for path, payload in search["result_chunks"]:
        writer.write_json(path, payload)
    writer.write_json("data/search/doc-map.json", search["doc_map"])
    for path, payload in search["filter_payloads"].items():
        writer.write_json(path, payload)
    writer.write_json("data/search/sort-values.json", search["sort_values"])
    writer.write_json("data/facets.json", search["facets"])


def compile_bundle(inputs: BuildInputs, output: Path) -> dict[str, Any]:
    corpus = load_frozen_corpus(inputs)
    output.mkdir(parents=True, exist_ok=True)
    writer = BundleWriter(output)

    provider_datapacks, provider_datapack_manifest = build_provider_datapacks(
        corpus, inputs.provider_datapacks
    )
    provider_datapack_manifest_sha256 = _sha256_bytes(
        canonical_json(provider_datapack_manifest).encode("utf-8")
    )
    reconciliation_relationships, reconciliation = build_cross_source_reconciliation(corpus.records)
    alternative_relationships = build_alternatives(corpus.records)
    _materialize_explorer_fields(corpus.records)
    relationships = sorted(
        reconciliation_relationships + alternative_relationships,
        key=lambda row: (
            str(row.get("source") or ""),
            str(row.get("target") or ""),
            str(row.get("kind") or ""),
        ),
    )
    resources = _resource_rows(corpus.records)
    search = build_search(corpus.records, snapshot_id=corpus.snapshot["snapshotId"])
    rankings, evaluation_report = _baseline_evaluation(corpus, inputs.gold_suite)
    coverage = _coverage_ledger(corpus)
    standards_evaluation = _quality_and_standards_summary(corpus)
    sdmx_implementation = _sdmx_implementation(corpus)
    generated_at = _generated_at(corpus)
    source_counts = _source_counts(corpus.records)
    record_type_counts = dict(
        sorted(Counter(record["record_type"] for record in corpus.records).items())
    )
    publisher_rows = _publisher_rows(corpus.records)
    rights_not_evaluated_count = sum(
        record.get("rights_status") == "not-evaluated"
        or record.get("license_id") == "not-evaluated"
        for record in corpus.records
    )

    dataset_chunks = _chunks(writer, "datasets", corpus.records)
    resource_chunks = _chunks(writer, "resources", resources)
    relationship_chunks = _chunks(writer, "relationships", relationships)
    publisher_chunks = _chunks(
        writer,
        "publishers",
        publisher_rows,
    )
    _write_search(writer, search)

    overview = {
        "schema": "okf-ons-overview.v1",
        "title": "ONS data discovery",
        "generated_at": generated_at,
        "snapshot": corpus.snapshot["snapshotId"],
        "snapshotId": corpus.snapshot["snapshotId"],
        "status": "demonstrator",
        "counts": {
            "records": len(corpus.records),
            "resources": len(resources),
            "relationships": len(relationships),
            "recordsWithAlternatives": sum(
                bool(record.get("alternatives")) for record in corpus.records
            ),
            "sources": len(source_counts),
            "publishers": len(publisher_rows),
            "providerDatapacks": len(provider_datapacks),
            "sourcePublisherAttributions": sum(
                row["dataset_count"] for row in publisher_rows
            ),
            "standards": standards_evaluation["standardCount"],
        },
        "sourceCounts": source_counts,
        "recordTypeCounts": record_type_counts,
        "allOnsMetadataClaim": False,
        "coverage": "data/coverage/ledger.json",
        "evaluation": "data/evaluation/report.json",
    }
    writer.write_json("data/overview.json", overview)
    writer.write_json(
        "data/analysis/overview.json",
        {
            **overview,
            "schema": "okf-explorer-analysis.v1",
            "metadataEvidence": standards_evaluation["recordEvidenceAvailability"],
            "reconciliation": {
                "matchedCodes": reconciliation["matched_code_count"],
                "titleAligned": reconciliation["title_aligned_code_count"],
                "titleConflicted": reconciliation["title_conflicted_code_count"],
                "unmatchedAnchors": reconciliation["unmatched_anchor_code_count"],
            },
            "evaluationMetrics": evaluation_report["metrics"],
            "statisticalAccuracyEvaluated": False,
            "providerDatapacks": {
                "count": len(provider_datapacks),
                "knownDrift": sum(
                    pack["comparison"]["status"] == "known-drift" for pack in provider_datapacks
                ),
            },
        },
    )
    writer.write_json("data/coverage/ledger.json", coverage)
    writer.write_json("data/standards/evaluation.json", standards_evaluation)
    writer.write_json("data/standards/register.json", corpus.standards_register)
    writer.write_json("data/standards/ontology-crosswalk.json", corpus.ontology_crosswalk)
    writer.write_json("data/standards/sdmx.json", sdmx_implementation)
    writer.write_json("data/reconciliation/report.json", reconciliation)
    writer.write_json("data/evaluation/alias-resolution.json", corpus.aliases)
    writer.write_json("data/evaluation/rankings.json", rankings)
    writer.write_json("data/evaluation/report.json", evaluation_report)
    writer.write_json(
        "data/ons/mcp-bindings.json",
        _mcp_bindings(corpus.records, corpus.snapshot["snapshotId"]),
    )
    writer.write_json(
        "data/ons/spatial-index.json",
        _spatial_index(corpus.records, corpus.snapshot["snapshotId"]),
    )
    for provider_datapack in provider_datapacks:
        writer.write_json(
            f"data/providers/{provider_datapack['id']}.json",
            provider_datapack,
        )
    writer.write_json("data/providers/manifest.json", provider_datapack_manifest)
    demo_projection = _demo_projection(corpus.records)
    writer.write_json(
        "data/demo/contrast-records.json",
        {
            "schema": "okf-ons-contrast-records.v1",
            "snapshotId": corpus.snapshot["snapshotId"],
            "bounded": True,
            "metadataOnly": True,
            "recordCount": len(demo_projection),
            "totalRecordCount": len(corpus.records),
            "scopeNote": (
                "This bounded browser projection is chosen for a fast human demo. "
                "The OKF Explorer search index contains every frozen record."
            ),
            "records": [
                result_document(record, ordinal)
                | {
                    "quality_evidence": record.get("quality_evidence", {}),
                    "identity": record.get("identity", {}),
                    "publication": record.get("publication", {}),
                    "statistical": record.get("statistical", {}),
                    "methodology_links": record.get("methodology_links", []),
                    "quality_links": record.get("quality_links", []),
                    "provenance": record.get("provenance", {}),
                    "spatial": record.get("spatial", {}),
                    "portal_extent": record.get("portal_extent", {}),
                    "spatial_reference": record.get("spatial_reference", {}),
                    "declared_table_codes": record.get("declared_table_codes", []),
                }
                for ordinal, record in enumerate(demo_projection)
            ],
        },
    )

    data_manifest = {
        "schema": "okf-explorer-data-manifest.v1",
        "title": "ONS data discovery OKF",
        "generated_at": generated_at,
        "snapshot": corpus.snapshot["snapshotId"],
        "chunks": {
            "datasets": dataset_chunks,
            "publishers": publisher_chunks,
            "resources": resource_chunks,
            "relationships": relationship_chunks,
        },
        "counts": {
            "datasets": len(corpus.records),
            "publishers": len(publisher_rows),
            "resources": len(resources),
            "relationships": len(relationships),
            "records": len(corpus.records),
            "sourcePublisherAttributions": sum(
                row["dataset_count"] for row in publisher_rows
            ),
        },
        "publisherSemantics": (
            "Source-producer attributions, not the bundle publisher. Co-produced "
            "records count once for each attributed producer, so totals are non-additive."
        ),
        "indexes": {
            "overview": "data/overview.json",
            "analysis": "data/analysis/overview.json",
            "facets": "data/facets.json",
            "search": "data/search/manifest.json",
            "coverage": "data/coverage/ledger.json",
            "reconciliation": "data/reconciliation/report.json",
            "sdmx": "data/standards/sdmx.json",
            "governance": "data/governance/release.json",
            "context_set": "data/governance/context-set.json",
            "provider_datapacks": "data/providers/manifest.json",
        },
        "performance": {
            "startup_mode": "overview-first",
            "full_record_hydration": "lazy",
            "relationship_hydration": "lazy",
            "search": "static worker-compatible shards",
        },
        "search": {
            "schema": search["manifest"]["schema"],
            "documents": search["manifest"]["counts"]["documents"],
            "tokens": search["manifest"]["counts"]["tokens"],
            "result_limit": search["manifest"]["result_limit"],
        },
    }
    writer.write_json("data/manifest.json", data_manifest)

    context = {
        "@context": {
            "okf": f"{PUBLIC_ROOT}vocab/",
            "dcat": "http://www.w3.org/ns/dcat#",
            "dct": "http://purl.org/dc/terms/",
            "dqv": "http://www.w3.org/ns/dqv#",
            "prov": "http://www.w3.org/ns/prov#",
            "qb": "http://purl.org/linked-data/cube#",
            "skos": "http://www.w3.org/2004/02/skos/core#",
            "Catalog": "dcat:Catalog",
            "Dataset": "dcat:Dataset",
            "title": "dct:title",
            "description": "dct:description",
            "identifier": "dct:identifier",
            "publisher": {"@id": "dct:publisher", "@type": "@id"},
            "landingPage": {"@id": "dcat:landingPage", "@type": "@id"},
            "conformsTo": {"@id": "dct:conformsTo", "@type": "@id"},
            "wasDerivedFrom": {"@id": "prov:wasDerivedFrom", "@type": "@id"},
            "wasGeneratedBy": {"@id": "prov:wasGeneratedBy", "@type": "@id"},
            "wasAttributedTo": {"@id": "prov:wasAttributedTo", "@type": "@id"},
            "sourcePublisher": {"@id": "okf:sourcePublisher", "@type": "@id"},
            "bundlePublisher": {"@id": "okf:bundlePublisher", "@type": "@id"},
            "semanticAuthority": {"@id": "okf:semanticAuthority", "@type": "@id"},
            "reviewedBy": {"@id": "okf:reviewedBy", "@type": "@id"},
            "notEndorsedBySource": "okf:notEndorsedBySource",
            "nonEndorsementStatement": "okf:nonEndorsementStatement",
            "contextSet": {"@id": "okf:contextSet", "@type": "@id"},
            "dataset": {"@id": "dcat:dataset", "@type": "@id"},
            "alignmentClaim": "okf:alignmentClaim",
            "statisticalAccuracyEvaluated": "okf:statisticalAccuracyEvaluated",
        }
    }
    context_text = canonical_json(context)
    context_sha256 = _sha256_bytes(context_text.encode("utf-8"))
    writer.write_text("context/okf-ons.jsonld", context_text)
    context_set = {
        "schema": "okf-context-set.v1",
        "snapshotId": corpus.snapshot["snapshotId"],
        "resolutionPolicy": "local-release-path-only",
        "networkRetrievalAllowed": False,
        "contexts": [
            {
                "url": f"{PUBLIC_ROOT}context/okf-ons.jsonld",
                "path": "context/okf-ons.jsonld",
                "sha256": context_sha256,
            }
        ],
    }
    writer.write_json("data/governance/context-set.json", context_set)
    governance = {
        "schema": "okf-governed-knowledge-contract-release.v1",
        "releaseVersion": __version__,
        "pattern": "Governed Knowledge Contract and Evidence-Carriage Plane",
        "status": "experimental-demonstrator",
        "snapshotId": corpus.snapshot["snapshotId"],
        "snapshotSha256": content_sha256(corpus.snapshot),
        "authority": {
            "bundlePublisher": BUNDLE_PUBLISHER,
            "semanticAuthority": {
                **BUNDLE_PUBLISHER,
                "scope": "this generated bundle release only",
            },
            "reviewedBy": [],
            "notEndorsedBySource": True,
            "nonEndorsementStatement": NON_ENDORSEMENT,
            "operationalAuthority": "external live-data service",
            "decisionAuthority": "accountable external person or institution",
        },
        "canonicality": {
            "sourceSystems": "source publication state and source data",
            "frozenSnapshot": "inputs to this deterministic bundle release",
            "semanticBundle": "semantic claims made by this release publisher",
            "indexesAndPlans": "replaceable non-authoritative runtime projections",
        },
        "sourceEvidence": [
            {
                "sourceId": source["sourceId"],
                "sourceAsOf": source["sourceAsOf"],
                "sourceAsOfBasis": source["sourceAsOfBasis"],
                "acquisitionRetrievedAt": source["acquisitionRetrievedAt"],
                "commitAsOf": source["commitAsOf"],
                "recordSetSha256": source["recordSetSha256"],
                "snapshotSetSha256": source["snapshotSetSha256"],
                "coverageComplete": source["coverageComplete"],
            }
            for source in coverage["implementedScope"]["sources"]
        ],
        "buildProvenance": {
            "activity": "deterministic frozen metadata compilation",
            "software": "okf-ons",
            "softwareVersion": __version__,
            "repository": BUNDLE_PUBLISHER["url"],
            "inputSnapshotSha256": content_sha256(corpus.snapshot),
            "codeReleasePinned": False,
            "attested": False,
        },
        "integrity": {
            "checksumsAvailable": True,
            "authenticatedSignature": False,
            "status": "checksums-only-not-authenticated",
            "warning": (
                "Checksums detect change only when obtained through a trusted channel; "
                "this release is not cryptographically authenticated."
            ),
        },
        "contextSet": "data/governance/context-set.json",
        "freshnessPolicy": {
            "status": "not-defined",
            "validThrough": None,
            "liveRevalidationRequiredBeforeExecution": True,
        },
        "observationValuesIncluded": False,
        "liveExecutionAvailable": False,
    }
    writer.write_json("data/governance/release.json", governance)
    semantic_bundle = {
        "@context": f"{PUBLIC_ROOT}context/okf-ons.jsonld",
        "@id": f"{PUBLIC_ROOT}okf-bundle.jsonld",
        "@type": "dcat:Catalog",
        "title": "ONS data discovery OKF",
        "description": (
            "Metadata-only demonstrator built from independently attributed public "
            "statistical metadata lanes."
        ),
        "publisher": BUNDLE_PUBLISHER["id"],
        "bundlePublisher": BUNDLE_PUBLISHER["id"],
        "semanticAuthority": BUNDLE_PUBLISHER["id"],
        "reviewedBy": [],
        "notEndorsedBySource": True,
        "nonEndorsementStatement": NON_ENDORSEMENT,
        "contextSet": "data/governance/context-set.json",
        "conformsTo": [
            "https://www.w3.org/TR/vocab-dcat-3/",
            "https://www.w3.org/TR/prov-o/",
            "https://www.w3.org/TR/skos-reference/",
            "https://www.w3.org/TR/vocab-data-cube/",
        ],
        "alignmentClaim": (
            "These terms describe the generated catalogue mapping. They do not assert "
            "that an upstream statistical product is certified or fully conformant."
        ),
        "dataset": [
            {
                "@id": f"{PUBLIC_ROOT}{record['route']}",
                "@type": "Dataset",
                "identifier": record["id"],
                "title": record["title"],
                "description": record.get("notes", ""),
                "landingPage": record.get("url", ""),
                "wasDerivedFrom": record.get("provenance", {}).get("source_url", ""),
                "wasGeneratedBy": f"{PUBLIC_ROOT}data/governance/release.json",
                "wasAttributedTo": BUNDLE_PUBLISHER["id"],
                "sourcePublisher": [
                    publisher.get("url")
                    or f"{PUBLIC_ROOT}publisher/{publisher.get('id', 'unknown')}"
                    for publisher in record.get("source_publishers", [])
                    if isinstance(publisher, Mapping)
                ],
                "bundlePublisher": BUNDLE_PUBLISHER["id"],
                "semanticAuthority": BUNDLE_PUBLISHER["id"],
                "reviewedBy": [],
                "notEndorsedBySource": True,
            }
            for record in corpus.records
        ],
        "statisticalAccuracyEvaluated": False,
    }
    writer.write_json("okf-bundle.jsonld", semantic_bundle)
    # JSON is valid YAML 1.2, keeping this dependency-free and byte-stable.
    writer.write_json("okf-bundle.yamlld", semantic_bundle)

    descriptor = {
        "@context": "https://chris-page-gov.github.io/okf-explorer/profile/bundle-wiki/v1/context.jsonld",
        "@id": f"{PUBLIC_ROOT}okf-explorer.json",
        "schema": "okf-explorer-large-corpus.v1",
        "kind": "okf-large-corpus",
        "profile": "https://chris-page-gov.github.io/okf-explorer/profile/bundle-wiki/v1/",
        "title": "ONS data discovery OKF",
        "description": (
            "Metadata-only ONS discovery demonstrator with explicit coverage, "
            "confusable alternatives, standards evidence and MCP selection bindings."
        ),
        "version": __version__,
        "snapshot": corpus.snapshot["snapshotId"],
        "generated_at": generated_at,
        "status": "bounded-demonstrator",
        "publisher": BUNDLE_PUBLISHER["id"],
        "authority": governance["authority"],
        "rights": {
            "status": "mixed-record-level",
            "recordLevel": True,
            "notEvaluatedRecordCount": rights_not_evaluated_count,
            "codeLicense": f"{BUNDLE_PUBLISHER['url']}/blob/v{__version__}/LICENSE",
            "statement": (
                "No single licence is asserted for all source metadata. Consult each "
                "record's license_id, license_source_id and rights_status fields; some "
                "records remain explicitly not evaluated."
            ),
        },
        "semantic_descriptor": f"{PUBLIC_ROOT}okf-bundle.yamlld",
        "counts": {
            "datasets": len(corpus.records),
            "records": len(corpus.records),
            "publishers": len(publisher_rows),
            "resources": len(resources),
            "relationships": len(relationships),
            "sources": len(source_counts),
            "standards": standards_evaluation["standardCount"],
            "providerDatapacks": len(provider_datapacks),
        },
        "scope": {
            "kind": "metadata-only-ons-discovery-demonstrator",
            "complete_ons_corpus": False,
            "implemented_source_records": len(corpus.records),
            "planned_source_lanes": coverage["wholeScope"]["plannedLaneCount"],
        },
        "entrypoints": {
            "data_manifest": "data/manifest.json",
            "overview_index": "data/overview.json",
            "analysis_overview": "data/analysis/overview.json",
            "search_manifest": "data/search/manifest.json",
            "coverage": "data/coverage/ledger.json",
            "reconciliation": "data/reconciliation/report.json",
            "standards": "data/standards/evaluation.json",
            "sdmx": "data/standards/sdmx.json",
            "evaluation": "data/evaluation/report.json",
            "governance": "data/governance/release.json",
            "context_set": "data/governance/context-set.json",
            "provider_datapacks": "data/providers/manifest.json",
            "mcp_bindings": "data/ons/mcp-bindings.json",
            "spatial_index": "data/ons/spatial-index.json",
            "viewer": EXPLORER_ROOT,
        },
        "entrypoint_integrity": {
            "provider_datapacks": {
                "path": "data/providers/manifest.json",
                "sha256": provider_datapack_manifest_sha256,
            }
        },
        "extensions": {
            "okf-ons-discovery.v1": {
                "mode": "metadata-only-demonstrator",
                "all_ons_metadata_claim": False,
                "compare_alternatives": True,
                "statistical_accuracy_evaluated": False,
                "not_endorsed_by_source": True,
            },
            "okf-governed-knowledge-contract.v1": {
                "entrypoint": "governance",
                "status": "experimental",
                "evidence_carried_not_certified": True,
                "authorises_execution": False,
            },
            "okf-mcp-binding.v1": {
                "entrypoint": "mcp_bindings",
                "read_only": True,
                "secret_values_stored": False,
            },
            "okf-ons-standards-evidence.v1": {
                "entrypoint": "standards",
                "claim": "Evidence mapping and profile alignment; not certification.",
            },
            "okf-ons-sdmx.v1": {
                "entrypoint": "sdmx",
                "serialized_as_sdmx": False,
                "upstream_source_surface": "nomis",
                "query_tool": "nomis_query",
            },
            "okf-ons-geography.v1": {
                "entrypoint": "spatial_index",
                "geometry_included": False,
            },
            "okf-explorer-provider-datapacks.v1": {
                "entrypoint": "provider_datapacks",
                "pack_count": len(provider_datapacks),
                "snapshot_state_derived_from_frozen_bundle": True,
                "reviewed_live_references_are_external": True,
                "live_validation_performed": False,
            },
        },
        "performance": {
            "startup_mode": "overview-first",
            "full_record_hydration": "lazy",
            "relationship_hydration": "lazy",
            "search": "static worker-compatible shards",
        },
        "vocabulary": {
            "record_singular": "ONS metadata record",
            "record_plural": "ONS metadata records",
            "publisher_singular": "publisher",
            "publisher_plural": "publishers",
            "resource_singular": "source/access resource",
            "resource_plural": "source/access resources",
            "search_placeholder": "Search ONS products, concepts, geographies and identifiers",
        },
        "source": {
            "title": "Official ONS public metadata catalogues",
            "url": "https://www.ons.gov.uk/",
            "adapters": sorted(source_counts),
            "metadata_only": True,
            "snapshot_sha256": content_sha256(corpus.snapshot),
        },
    }
    writer.write_json("okf-explorer.json", descriptor)
    writer.write_text(
        "index.md",
        "# ONS data discovery OKF\n\n"
        "Metadata-only demonstrator. Open `okf-explorer.json` in OKF Explorer or "
        "use the GitHub Pages discovery interface.\n",
    )
    checksums = writer.checksums()
    writer.write_json("checksums.json", checksums)
    return {
        "descriptor": descriptor,
        "checksums": checksums,
        "coverage": coverage,
        "reconciliation": reconciliation,
        "evaluation": evaluation_report,
    }


def check_bundle(inputs: BuildInputs, output: Path) -> None:
    if not output.is_dir():
        raise BuildError(f"Bundle output does not exist: {output}")
    with tempfile.TemporaryDirectory(prefix="okf-ons-check-") as temporary:
        candidate = Path(temporary) / "bundle"
        compile_bundle(inputs, candidate)
        manifest = _read_json(candidate / "checksums.json")
        paths = [str(row["path"]) for row in manifest["files"]] + ["checksums.json"]
        mismatches: list[str] = []
        for relative in paths:
            expected = candidate / relative
            actual = output / relative
            if not actual.is_file() or actual.read_bytes() != expected.read_bytes():
                mismatches.append(relative)
        if mismatches:
            sample = ", ".join(mismatches[:10])
            message = (
                "Bundle differs from a deterministic rebuild in "
                f"{len(mismatches)} file(s): {sample}"
            )
            raise BuildError(message)


def copy_pages_assets(pages: Path, output: Path) -> None:
    """Copy stable static UI assets into a compiled bundle for local publication."""

    if not pages.is_dir():
        raise BuildError(f"Pages asset directory does not exist: {pages}")
    for source in sorted(pages.iterdir()):
        if source.is_file():
            shutil.copy2(source, output / source.name)
