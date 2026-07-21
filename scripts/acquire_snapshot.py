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
import re
import shutil
import sys
import tempfile
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

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


_BOUNDED_REPLACEMENT_SCHEMA = "okf-ons.bounded-source-replacement.v1"
_NOMIS_ENRICHMENT_SCHEMA = "okf-ons.nomis-overview-enrichment.v1"
_NOMIS_SOURCE_ID = "nomis-dataset-definitions"
_NOMIS_OVERVIEW_SELECT = "DatasetInfo,Coverage,DateMetadata,Contact"
_ONS_VERSION_ENRICHMENT_SCHEMA = "okf-ons.ons-version-metadata-enrichment.v1"
_ONS_SOURCE_ID = "ons-data-api"
_ONS_EXPECTED_COHORT_COUNT = 337
_ONS_VERSION_DIMENSION_FIELDS = {
    "id",
    "isAreaType",
    "label",
    "name",
    "qualityStatementText",
    "qualityStatementUrl",
}
_ONS_VERSION_DIMENSION_REQUIRED_FIELDS = {"id", "isAreaType", "name"}
_ONS_SOURCE_KEYS = {
    "acquisitionMethod",
    "adapter",
    "crossReferences",
    "endpoint",
    "id",
    "identityFields",
    "publisher",
    "responseFormat",
    "scope",
    "standards",
    "title",
}
_SAFE_REPLACEMENT_FIELDS = {
    "contacts",
    "firstReleased",
    "geographicCoverage",
    "lastRevised",
    "lastUpdated",
    "nextUpdate",
}
_DATE_REPLACEMENT_FIELDS = {
    "firstReleased",
    "lastRevised",
    "lastUpdated",
    "nextUpdate",
}
_CONTACT_FIELDS = {"name", "email", "telephone", "url"}
_ACQUISITION_KEYS = {"schemaVersion", "records", "provenance"}
_BASE_NOMIS_PROVENANCE_KEYS = {
    "assurance",
    "complete",
    "coverageComplete",
    "normalisationDroppedCount",
    "normalisedRecordsSeen",
    "pageCount",
    "pages",
    "recordCount",
    "recordSetSha256",
    "reportedTotal",
    "retrievalMode",
    "snapshotSetSha256",
    "source",
    "stopReason",
    "unrepresentedCount",
    "upstreamRecordsSeen",
}
_REPLACEMENT_PROVENANCE_KEYS = _BASE_NOMIS_PROVENANCE_KEYS | {
    "enrichmentRun",
    "replacement",
}
_REPLACEMENT_DECLARATION_KEYS = {
    "allowedRecordFields",
    "baseRecordSetSha256",
    "baseSnapshotId",
    "baseSnapshotSetSha256",
    "schema",
}
_ENRICHMENT_RUN_KEYS = {
    "cohortCount",
    "coverageComplete",
    "requestedLimit",
    "schema",
    "select",
    "selectedCount",
    "selectedRecordSetSha256",
    "selectionOrder",
    "unselectedCount",
}
_ONS_VERSION_RUN_KEYS = {
    "cohortCount",
    "cohortRecordSetSha256",
    "coverageComplete",
    "requestedLimit",
    "schema",
    "selectedCount",
    "selectedRecordSetSha256",
    "selectionOrder",
    "unselectedCount",
}
_REPLACEMENT_ASSURANCE = {
    "cacheLocationPublished": False,
    "codelistsFetched": False,
    "credentialsRequired": False,
    "metadataOnly": True,
    "observationsFetched": False,
    "rawResponsesPublished": False,
}
_ONS_BASE_ASSURANCE = {
    "cacheLocationPublished": False,
    "credentialsRequired": False,
    "metadataOnly": True,
    "observationsFetched": False,
}
_ONS_REPLACEMENT_ASSURANCE = {
    **_ONS_BASE_ASSURANCE,
    "dimensionMetadataFetched": True,
    "dimensionOptionsFetched": False,
    "downloadsFetched": False,
    "rawResponsesPublished": False,
}
_PAGE_KEYS = {
    "cacheHit",
    "contentSha256",
    "normalisedRecordCount",
    "requestUrl",
    "responseHeaders",
    "responseUrl",
    "retrievedAt",
    "upstreamRecordCount",
}
_SAFE_RESPONSE_HEADER_KEYS = {"content-type", "etag", "last-modified"}
_MANIFEST_KEYS = {
    "claimBoundary",
    "completeForRegisteredAdapters",
    "metadataOnly",
    "observationsIncluded",
    "schema",
    "snapshotId",
    "sources",
}
_MANIFEST_SOURCE_KEYS = {
    "coverageComplete",
    "file",
    "normalisationDroppedCount",
    "recordCount",
    "recordSetSha256",
    "reportedTotal",
    "sha256",
    "snapshotSetSha256",
    "sourceId",
    "unrepresentedCount",
}
_HEX_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_NOMIS_ID_RE = re.compile(r"^NM_[0-9]+_[0-9]+$")
_ONS_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*$")
_ONS_EDITION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]*$")
_NOMIS_DATE_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}$"
)
_UTC_TIMESTAMP_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?Z$"
)
_LOCAL_PATH_RE = re.compile(
    r"(?:/Users/|/Volumes/|/private/tmp/|/tmp/|[A-Za-z]:\\Users\\)",
    re.IGNORECASE,
)
_SECRET_VALUE_PATTERNS = (
    re.compile(
        r"(?i)(?:access[_-]?token|api[_-]?key|authorization|client[_-]?secret|"
        r"credential|password|secret|token|x-api-key)=[^&\s]{4,}"
    ),
    re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]{12,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{30,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)
_FORBIDDEN_PUBLIC_KEYS = {
    "accesstoken",
    "apikey",
    "authorization",
    "binary",
    "blob",
    "clientsecret",
    "coordinates",
    "credential",
    "credentials",
    "data",
    "datasetpayload",
    "downloadpayload",
    "features",
    "geometry",
    "observation",
    "observations",
    "observationvalue",
    "observationvalues",
    "password",
    "secret",
    "token",
    "topology",
    "value",
    "values",
    "xapikey",
}
_SECRET_QUERY_KEYS = {
    "access_token",
    "apikey",
    "api_key",
    "authorization",
    "client_secret",
    "credential",
    "key",
    "password",
    "secret",
    "sig",
    "signature",
    "token",
    "uid",
    "x-api-key",
}


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


def _validate_exact_keys(
    value: Mapping[str, Any], expected: set[str], label: str
) -> None:
    actual = set(value)
    if actual != expected:
        unknown = sorted(actual - expected)
        missing = sorted(expected - actual)
        detail = []
        if unknown:
            detail.append("unreviewed field(s): " + ", ".join(unknown))
        if missing:
            detail.append("missing field(s): " + ", ".join(missing))
        raise SnapshotCompositionError(f"{label} has " + "; ".join(detail))


def _validated_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _HEX_SHA256_RE.fullmatch(value):
        raise SnapshotCompositionError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _validate_utc_timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _UTC_TIMESTAMP_RE.fullmatch(value):
        raise SnapshotCompositionError(f"{label} must be a UTC ISO 8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SnapshotCompositionError(
            f"{label} must be a UTC ISO 8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise SnapshotCompositionError(f"{label} must be a UTC ISO 8601 timestamp")
    return value


def _normalised_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def _assert_public_safe(value: Any, source_id: str, *, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if _normalised_key(key) in _FORBIDDEN_PUBLIC_KEYS:
                raise SnapshotCompositionError(
                    f"bounded replacement contains unsafe field {key!r}: {source_id}"
                )
            _assert_public_safe(child, source_id, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_public_safe(child, source_id, path=f"{path}[{index}]")
    elif isinstance(value, bytes):
        raise SnapshotCompositionError(
            f"bounded replacement contains binary content at {path}: {source_id}"
        )
    elif isinstance(value, float) and not (float("-inf") < value < float("inf")):
        raise SnapshotCompositionError(
            f"bounded replacement contains a non-finite number at {path}: {source_id}"
        )
    elif isinstance(value, str):
        if _LOCAL_PATH_RE.search(value) or any(
            pattern.search(value) for pattern in _SECRET_VALUE_PATTERNS
        ):
            raise SnapshotCompositionError(
                f"bounded replacement contains an unsafe value at {path}: {source_id}"
            )


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
    # The ELS projector has a stricter allowlist and credential scan than this
    # generic envelope validator. Run it before digest checks so unsafe fields
    # are reported as unsafe projection content rather than merely as a stale
    # record-set hash. Its validator also independently verifies both digests.
    if definition.adapter == "els-metadata-projection":
        try:
            validate_els_acquisition_envelope(dict(public_result))
        except ELSProjectionError as exc:
            raise SnapshotCompositionError(
                f"unsafe projected acquisition {source_id}: {exc}"
            ) from exc
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


def _replacement_records_by_id(
    value: Any,
    source_id: str,
    *,
    label: str,
) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        raise SnapshotCompositionError(f"{label} records are malformed: {source_id}")
    records: dict[str, dict[str, Any]] = {}
    for item in value:
        if not isinstance(item, dict) or item.get("sourceId") != source_id:
            raise SnapshotCompositionError(f"{label} record identity is invalid: {source_id}")
        record_id = item.get("sourceRecordId")
        if not isinstance(record_id, str) or not record_id or record_id in records:
            raise SnapshotCompositionError(f"{label} record identity is invalid: {source_id}")
        records[record_id] = item
    return records


def _validate_replacement_url(value: str, source_id: str) -> None:
    parsed = urlsplit(value)
    query_keys = {key.casefold() for key, _ in parse_qsl(parsed.query)}
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or query_keys.intersection(_SECRET_QUERY_KEYS)
    ):
        raise SnapshotCompositionError(
            f"bounded replacement contains an unsafe contact URL: {source_id}"
        )


def _validate_replacement_field(field: str, value: Any, source_id: str) -> None:
    if field == "contacts":
        if not isinstance(value, list) or not value or len(value) > 20:
            raise SnapshotCompositionError(
                f"bounded replacement contacts are malformed: {source_id}"
            )
        for contact in value:
            if (
                not isinstance(contact, Mapping)
                or not contact
                or set(contact) - _CONTACT_FIELDS
            ):
                raise SnapshotCompositionError(
                    f"bounded replacement contact is malformed: {source_id}"
                )
            for key, item in contact.items():
                if not isinstance(item, str) or not item.strip() or len(item) > 2_000:
                    raise SnapshotCompositionError(
                        f"bounded replacement contact value is malformed: {source_id}"
                    )
                if key == "url":
                    _validate_replacement_url(item, source_id)
        return
    if field == "geographicCoverage":
        if not isinstance(value, str) or not value.strip() or len(value) > 500:
            raise SnapshotCompositionError(
                f"bounded replacement geographic coverage is malformed: {source_id}"
            )
        return
    if field in _DATE_REPLACEMENT_FIELDS:
        if not isinstance(value, str) or _NOMIS_DATE_RE.fullmatch(value) is None:
            raise SnapshotCompositionError(
                f"bounded replacement date metadata is malformed: {source_id}"
            )
        try:
            datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except ValueError as exc:
            raise SnapshotCompositionError(
                f"bounded replacement date metadata is malformed: {source_id}"
            ) from exc
        return
    raise SnapshotCompositionError(f"bounded replacement field is unsupported: {field}")


def _validate_nomis_enrichment_pages(
    pages: list[Any],
    run: Mapping[str, Any],
    source_id: str,
    cohort_ids: list[str],
) -> list[str]:
    requested_limit = run.get("requestedLimit")
    if (
        isinstance(requested_limit, bool)
        or not isinstance(requested_limit, int)
        or requested_limit < 1
    ):
        raise SnapshotCompositionError(
            f"bounded replacement requested limit is invalid: {source_id}"
        )
    ranked_ids = sorted(
        cohort_ids,
        key=lambda item: (
            hashlib.sha256(item.encode("utf-8")).hexdigest(),
            item.casefold(),
            item,
        ),
    )
    expected_ids = ranked_ids[: min(requested_limit, len(ranked_ids))]
    selected_ids: list[str] = []
    for index, page in enumerate(pages):
        if not isinstance(page, Mapping):
            raise SnapshotCompositionError(
                f"bounded replacement enrichment page is malformed: {source_id}"
            )
        _validate_exact_keys(
            page, _PAGE_KEYS, f"bounded replacement enrichment page {index}"
        )
        request_url = page.get("requestUrl")
        response_url = page.get("responseUrl")
        if (
            not isinstance(request_url, str)
            or not isinstance(response_url, str)
            or response_url != request_url
        ):
            raise SnapshotCompositionError(
                f"bounded replacement enrichment page is incomplete: {source_id}"
            )
        parsed = urlsplit(request_url)
        path_match = re.fullmatch(
            r"/api/v01/dataset/(NM_[0-9]+_[0-9]+)\.overview\.json", parsed.path
        )
        if (
            parsed.scheme != "https"
            or parsed.netloc != "www.nomisweb.co.uk"
            or parsed.username
            or parsed.password
            or parsed.fragment
            or parse_qsl(parsed.query, keep_blank_values=True)
            != [("select", _NOMIS_OVERVIEW_SELECT)]
            or path_match is None
        ):
            raise SnapshotCompositionError(
                f"bounded replacement escaped the Nomis metadata-only endpoint: {source_id}"
            )
        record_id = path_match.group(1)
        _validated_sha256(
            page.get("contentSha256"),
            f"bounded replacement enrichment page {index} content hash",
        )
        _validate_utc_timestamp(
            page.get("retrievedAt"),
            f"bounded replacement enrichment page {index} retrieval time",
        )
        headers = page.get("responseHeaders")
        if not isinstance(headers, Mapping) or set(headers) - _SAFE_RESPONSE_HEADER_KEYS:
            raise SnapshotCompositionError(
                f"bounded replacement enrichment page headers are unsafe: {source_id}"
            )
        for key, value in headers.items():
            if (
                key != key.casefold()
                or not isinstance(value, str)
                or not value.strip()
                or len(value) > 2_000
                or _LOCAL_PATH_RE.search(value)
                or any(pattern.search(value) for pattern in _SECRET_VALUE_PATTERNS)
            ):
                raise SnapshotCompositionError(
                    f"bounded replacement enrichment page headers are unsafe: {source_id}"
                )
        content_type = headers.get("content-type")
        if content_type is not None and not content_type.casefold().startswith(
            "application/json"
        ):
            raise SnapshotCompositionError(
                f"bounded replacement enrichment page content type is unsafe: {source_id}"
            )
        if (
            not isinstance(page.get("cacheHit"), bool)
            or isinstance(page.get("upstreamRecordCount"), bool)
            or page.get("upstreamRecordCount") != 1
            or isinstance(page.get("normalisedRecordCount"), bool)
            or page.get("normalisedRecordCount") != 1
        ):
            raise SnapshotCompositionError(
                f"bounded replacement enrichment page counts are invalid: {source_id}"
            )
        selected_ids.append(record_id)
    if (
        selected_ids != expected_ids
        or run.get("selectedRecordSetSha256") != sha256_json(selected_ids)
    ):
        raise SnapshotCompositionError(
            f"bounded replacement deterministic selection is invalid: {source_id}"
        )
    return selected_ids


def _ons_latest_version_identity(value: Any, source_id: str) -> tuple[str, str, int]:
    if not isinstance(value, str):
        raise SnapshotCompositionError(
            f"bounded replacement latest-version URL is malformed: {source_id}"
        )
    parsed = urlsplit(value)
    match = re.fullmatch(
        r"/v1/datasets/([^/]+)/editions/([^/]+)/versions/([0-9]+)", parsed.path
    )
    if (
        parsed.scheme != "https"
        or parsed.netloc != "api.beta.ons.gov.uk"
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or match is None
    ):
        raise SnapshotCompositionError(
            f"bounded replacement escaped the ONS latest-version endpoint: {source_id}"
        )
    record_id, edition, raw_version = match.groups()
    if (
        _ONS_ID_RE.fullmatch(record_id) is None
        or _ONS_EDITION_RE.fullmatch(edition) is None
    ):
        raise SnapshotCompositionError(
            f"bounded replacement latest-version identity is malformed: {source_id}"
        )
    return record_id, edition, int(raw_version)


def _ons_record_latest_version_href(
    record: Mapping[str, Any], source_id: str
) -> str:
    record_id = record.get("sourceRecordId")
    links = record.get("links")
    latest = links.get("latest_version") if isinstance(links, Mapping) else None
    href = latest.get("href") if isinstance(latest, Mapping) else None
    href_record_id, _, version = _ons_latest_version_identity(href, source_id)
    if (
        not isinstance(record_id, str)
        or record_id != href_record_id
        or not isinstance(latest, Mapping)
        or set(latest) != {"href", "id"}
        or latest.get("id") != str(version)
    ):
        raise SnapshotCompositionError(
            f"base ONS latest-version identity is invalid: {source_id}"
        )
    return href


def _validate_ons_source_provenance(value: Mapping[str, Any], source_id: str) -> None:
    _validate_exact_keys(value, _ONS_SOURCE_KEYS, "base ONS source provenance")
    publisher = value.get("publisher")
    scope = value.get("scope")
    if (
        value.get("id") != source_id
        or value.get("adapter") != "ons-data-api"
        or value.get("acquisitionMethod") != "http-json"
        or value.get("endpoint") != "https://api.beta.ons.gov.uk/v1/datasets"
        or value.get("identityFields") != ["id"]
        or not isinstance(value.get("crossReferences"), list)
        or not isinstance(value.get("standards"), list)
        or not isinstance(value.get("title"), str)
        or not value["title"].strip()
        or not isinstance(value.get("responseFormat"), str)
        or not value["responseFormat"].strip()
        or not isinstance(publisher, Mapping)
        or set(publisher) != {"name", "url"}
        or not isinstance(publisher.get("name"), str)
        or not publisher["name"].strip()
        or not isinstance(scope, Mapping)
        or set(scope) != {"excludes", "includes"}
        or not all(
            isinstance(scope.get(key), list)
            and all(isinstance(item, str) and item.strip() for item in scope[key])
            for key in ("excludes", "includes")
        )
    ):
        raise SnapshotCompositionError(
            f"base ONS source provenance is invalid: {source_id}"
        )
    _validate_ons_public_url(publisher["url"], source_id)


def _validate_ons_catalogue_page_url(value: Any, source_id: str) -> None:
    if not isinstance(value, str):
        raise SnapshotCompositionError(
            f"base ONS catalogue page URL is malformed: {source_id}"
        )
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "api.beta.ons.gov.uk"
        or parsed.username
        or parsed.password
        or parsed.path != "/v1/datasets"
        or parsed.fragment
        or parse_qsl(parsed.query, keep_blank_values=True)
        != [("limit", "1000"), ("offset", "0")]
    ):
        raise SnapshotCompositionError(
            f"base ONS catalogue page URL is invalid: {source_id}"
        )


def _validate_ons_public_url(value: Any, source_id: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 2_000:
        raise SnapshotCompositionError(
            f"bounded replacement public URL is malformed: {source_id}"
        )
    parsed = urlsplit(value)
    query_keys = {key.casefold() for key, _ in parse_qsl(parsed.query)}
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or query_keys.intersection(_SECRET_QUERY_KEYS)
        or _LOCAL_PATH_RE.search(value)
        or any(pattern.search(value) for pattern in _SECRET_VALUE_PATTERNS)
    ):
        raise SnapshotCompositionError(
            f"bounded replacement public URL is unsafe: {source_id}"
        )


def _validate_ons_version_dimensions(value: Any, source_id: str) -> list[Any]:
    if not isinstance(value, list) or not value or len(value) > 1_000:
        raise SnapshotCompositionError(
            f"bounded replacement version dimensions are malformed: {source_id}"
        )
    dimension_ids: set[str] = set()
    for dimension in value:
        if not isinstance(dimension, Mapping):
            raise SnapshotCompositionError(
                f"bounded replacement version dimension is malformed: {source_id}"
            )
        keys = set(dimension)
        if (
            not _ONS_VERSION_DIMENSION_REQUIRED_FIELDS.issubset(keys)
            or not keys.issubset(_ONS_VERSION_DIMENSION_FIELDS)
        ):
            raise SnapshotCompositionError(
                f"bounded replacement version dimension has unreviewed or missing "
                f"fields: {source_id}"
            )
        for field in ("id", "name"):
            item = dimension[field]
            if not isinstance(item, str) or not item.strip() or len(item) > 500:
                raise SnapshotCompositionError(
                    f"bounded replacement version dimension is malformed: {source_id}"
                )
        if "label" in dimension:
            label = dimension["label"]
            if not isinstance(label, str) or not label.strip() or len(label) > 500:
                raise SnapshotCompositionError(
                    f"bounded replacement version dimension is malformed: {source_id}"
                )
        if not isinstance(dimension["isAreaType"], bool):
            raise SnapshotCompositionError(
                f"bounded replacement version dimension is malformed: {source_id}"
            )
        dimension_id = dimension["id"]
        if dimension_id in dimension_ids:
            raise SnapshotCompositionError(
                f"bounded replacement version dimension ids are duplicated: {source_id}"
            )
        dimension_ids.add(dimension_id)
        if "qualityStatementUrl" in dimension:
            _validate_ons_public_url(dimension["qualityStatementUrl"], source_id)
        if "qualityStatementText" in dimension:
            quality_text = dimension["qualityStatementText"]
            if (
                not isinstance(quality_text, str)
                or not quality_text.strip()
                or len(quality_text) > 20_000
            ):
                raise SnapshotCompositionError(
                    f"bounded replacement quality statement is malformed: {source_id}"
                )
    return value


def _validate_ons_page_receipt(
    page: Any,
    source_id: str,
    *,
    label: str,
    expected_url: str | None = None,
    require_single_record: bool,
) -> None:
    if not isinstance(page, Mapping):
        raise SnapshotCompositionError(f"{label} is malformed: {source_id}")
    _validate_exact_keys(page, _PAGE_KEYS, label)
    request_url = page.get("requestUrl")
    response_url = page.get("responseUrl")
    if (
        not isinstance(request_url, str)
        or not isinstance(response_url, str)
        or response_url != request_url
        or (expected_url is not None and request_url != expected_url)
    ):
        raise SnapshotCompositionError(f"{label} has invalid response identity: {source_id}")
    _validated_sha256(page.get("contentSha256"), f"{label} content hash")
    _validate_utc_timestamp(page.get("retrievedAt"), f"{label} retrieval time")
    headers = page.get("responseHeaders")
    allowed_header_keys = _SAFE_RESPONSE_HEADER_KEYS | {"retry-after"}
    if not isinstance(headers, Mapping) or set(headers) - allowed_header_keys:
        raise SnapshotCompositionError(f"{label} headers are unsafe: {source_id}")
    for key, item in headers.items():
        if (
            key != key.casefold()
            or not isinstance(item, str)
            or not item.strip()
            or len(item) > 2_000
            or _LOCAL_PATH_RE.search(item)
            or any(pattern.search(item) for pattern in _SECRET_VALUE_PATTERNS)
        ):
            raise SnapshotCompositionError(f"{label} headers are unsafe: {source_id}")
    content_type = headers.get("content-type")
    if content_type is not None and not content_type.casefold().startswith(
        "application/json"
    ):
        raise SnapshotCompositionError(f"{label} content type is unsafe: {source_id}")
    upstream_count = page.get("upstreamRecordCount")
    normalised_count = page.get("normalisedRecordCount")
    if (
        not isinstance(page.get("cacheHit"), bool)
        or isinstance(upstream_count, bool)
        or not isinstance(upstream_count, int)
        or upstream_count < 0
        or isinstance(normalised_count, bool)
        or not isinstance(normalised_count, int)
        or normalised_count < 0
        or (require_single_record and (upstream_count != 1 or normalised_count != 1))
    ):
        raise SnapshotCompositionError(f"{label} counts are invalid: {source_id}")


def _validate_ons_bounded_replacement(
    replacement: Mapping[str, Any],
    base: Mapping[str, Any],
    source_id: str,
    *,
    base_snapshot_id: str,
) -> dict[str, int]:
    """Validate a frozen-URL ONS version-metadata replacement."""

    _validate_exact_keys(
        replacement, _ACQUISITION_KEYS, "bounded replacement acquisition"
    )
    _validate_exact_keys(base, _ACQUISITION_KEYS, "base ONS acquisition")
    if (
        replacement.get("schemaVersion") != "okf-ons.source-acquisition.v1"
        or base.get("schemaVersion") != "okf-ons.source-acquisition.v1"
    ):
        raise SnapshotCompositionError(
            f"bounded replacement acquisition schema is unsupported: {source_id}"
        )
    provenance = replacement.get("provenance")
    base_provenance = base.get("provenance")
    if not isinstance(provenance, Mapping) or not isinstance(base_provenance, Mapping):
        raise SnapshotCompositionError(
            f"bounded replacement provenance is malformed: {source_id}"
        )
    _validate_exact_keys(
        base_provenance,
        _BASE_NOMIS_PROVENANCE_KEYS,
        "base ONS acquisition provenance",
    )
    _validate_exact_keys(
        provenance,
        _BASE_NOMIS_PROVENANCE_KEYS | {"replacement", "versionMetadataRun"},
        "bounded replacement provenance",
    )
    base_source = base_provenance.get("source")
    if (
        not isinstance(base_source, Mapping)
        or base_source.get("id") != source_id
        or provenance.get("source") != base_source
    ):
        raise SnapshotCompositionError(
            f"bounded replacement source provenance is invalid: {source_id}"
        )
    _validate_ons_source_provenance(base_source, source_id)
    if base_provenance.get("assurance") != _ONS_BASE_ASSURANCE:
        raise SnapshotCompositionError(
            f"base ONS acquisition assurance is invalid: {source_id}"
        )
    assurance = provenance.get("assurance")
    if (
        not isinstance(assurance, Mapping)
        or set(assurance) != set(_ONS_REPLACEMENT_ASSURANCE)
        or any(
            assurance[key] is not expected
            for key, expected in _ONS_REPLACEMENT_ASSURANCE.items()
        )
    ):
        raise SnapshotCompositionError(
            f"bounded replacement lacks ONS metadata-only assurance: {source_id}"
        )

    declaration = provenance.get("replacement")
    if not isinstance(declaration, Mapping):
        raise SnapshotCompositionError(
            f"bounded replacement declaration is malformed: {source_id}"
        )
    _validate_exact_keys(
        declaration,
        _REPLACEMENT_DECLARATION_KEYS,
        "bounded replacement declaration",
    )
    if (
        declaration.get("schema") != _BOUNDED_REPLACEMENT_SCHEMA
        or declaration.get("baseSnapshotId") != base_snapshot_id
        or declaration.get("baseRecordSetSha256")
        != base_provenance.get("recordSetSha256")
        or declaration.get("baseSnapshotSetSha256")
        != base_provenance.get("snapshotSetSha256")
        or declaration.get("allowedRecordFields") != ["versionDimensions"]
    ):
        raise SnapshotCompositionError(
            f"bounded replacement is not bound to its base acquisition: {source_id}"
        )

    base_records = _replacement_records_by_id(
        base.get("records"), source_id, label="base acquisition"
    )
    replacement_records = _replacement_records_by_id(
        replacement.get("records"), source_id, label="replacement acquisition"
    )
    base_record_ids = list(base_records)
    if (
        len(base_records) != _ONS_EXPECTED_COHORT_COUNT
        or base_provenance.get("recordCount") != _ONS_EXPECTED_COHORT_COUNT
        or base_provenance.get("reportedTotal") != _ONS_EXPECTED_COHORT_COUNT
        or base_provenance.get("normalisedRecordsSeen")
        != _ONS_EXPECTED_COHORT_COUNT
        or base_provenance.get("upstreamRecordsSeen")
        != _ONS_EXPECTED_COHORT_COUNT
        or base_provenance.get("complete") is not True
        or base_provenance.get("coverageComplete") is not True
        or base_provenance.get("normalisationDroppedCount") != 0
        or base_provenance.get("unrepresentedCount") != 0
        or base_provenance.get("stopReason") != "sourceExhausted"
        or set(base_records) != set(replacement_records)
    ):
        raise SnapshotCompositionError(
            f"bounded replacement changed the exact ONS source-record cohort: {source_id}"
        )
    if list(replacement_records) != base_record_ids:
        raise SnapshotCompositionError(
            f"bounded replacement reordered the ONS source-record cohort: {source_id}"
        )
    if any(_ONS_ID_RE.fullmatch(record_id) is None for record_id in base_record_ids):
        raise SnapshotCompositionError(f"base ONS cohort identity is invalid: {source_id}")
    if base_provenance.get("recordSetSha256") != sha256_json(base.get("records")):
        raise SnapshotCompositionError(
            f"base ONS acquisition record-set hash is invalid: {source_id}"
        )

    cohort_pairs: list[dict[str, str]] = []
    latest_hrefs: set[str] = set()
    for record_id, base_record in base_records.items():
        href = _ons_record_latest_version_href(base_record, source_id)
        if href in latest_hrefs:
            raise SnapshotCompositionError(
                f"base ONS latest-version URLs are not unique: {source_id}"
            )
        latest_hrefs.add(href)
        cohort_pairs.append(
            {"sourceRecordId": record_id, "latestVersionHref": href}
        )

    base_pages = base_provenance.get("pages")
    replacement_pages = provenance.get("pages")
    if (
        not isinstance(base_pages, list)
        or not isinstance(replacement_pages, list)
        or len(base_pages) != 1
        or base_provenance.get("pageCount") != len(base_pages)
        or replacement_pages[: len(base_pages)] != base_pages
    ):
        raise SnapshotCompositionError(
            f"bounded replacement changed base page lineage: {source_id}"
        )
    for index, page in enumerate(base_pages):
        _validate_ons_page_receipt(
            page,
            source_id,
            label=f"base ONS acquisition page {index}",
            require_single_record=False,
        )
        _validate_ons_catalogue_page_url(page["requestUrl"], source_id)
        if (
            page["upstreamRecordCount"] != _ONS_EXPECTED_COHORT_COUNT
            or page["normalisedRecordCount"] != _ONS_EXPECTED_COHORT_COUNT
        ):
            raise SnapshotCompositionError(
                f"base ONS acquisition page counts are invalid: {source_id}"
            )
    base_snapshot_receipts = [
        {"requestUrl": page["requestUrl"], "contentSha256": page["contentSha256"]}
        for page in base_pages
    ]
    if base_provenance.get("snapshotSetSha256") != sha256_json(
        base_snapshot_receipts
    ):
        raise SnapshotCompositionError(
            f"base ONS acquisition snapshot-set hash is invalid: {source_id}"
        )

    run = provenance.get("versionMetadataRun")
    if not isinstance(run, Mapping):
        raise SnapshotCompositionError(
            f"bounded replacement ONS version run is missing: {source_id}"
        )
    _validate_exact_keys(run, _ONS_VERSION_RUN_KEYS, "bounded replacement ONS version run")
    requested_limit = run.get("requestedLimit")
    if (
        isinstance(requested_limit, bool)
        or not isinstance(requested_limit, int)
        or requested_limit < 1
    ):
        raise SnapshotCompositionError(
            f"bounded replacement ONS requested limit is invalid: {source_id}"
        )
    ranked_pairs = sorted(
        cohort_pairs,
        key=lambda row: (
            hashlib.sha256(row["sourceRecordId"].encode("utf-8")).hexdigest(),
            row["sourceRecordId"].casefold(),
            row["sourceRecordId"],
        ),
    )
    expected_pairs = ranked_pairs[
        : min(requested_limit, _ONS_EXPECTED_COHORT_COUNT)
    ]
    expected_selected_count = len(expected_pairs)
    for field in ("cohortCount", "selectedCount", "unselectedCount"):
        count = run.get(field)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise SnapshotCompositionError(
                f"bounded replacement ONS enrichment denominator is invalid: {source_id}"
            )
    if (
        run.get("schema") != _ONS_VERSION_ENRICHMENT_SCHEMA
        or run.get("cohortCount") != _ONS_EXPECTED_COHORT_COUNT
        or run.get("selectedCount") != expected_selected_count
        or run.get("unselectedCount")
        != _ONS_EXPECTED_COHORT_COUNT - expected_selected_count
        or not isinstance(run.get("coverageComplete"), bool)
        or run.get("coverageComplete")
        is not (expected_selected_count == _ONS_EXPECTED_COHORT_COUNT)
        or run.get("selectionOrder") != "sha256(sourceRecordId)-ascending"
        or run.get("cohortRecordSetSha256") != sha256_json(cohort_pairs)
        or run.get("selectedRecordSetSha256") != sha256_json(expected_pairs)
    ):
        raise SnapshotCompositionError(
            f"bounded replacement ONS enrichment denominator is invalid: {source_id}"
        )

    enrichment_pages = replacement_pages[len(base_pages) :]
    if len(enrichment_pages) != expected_selected_count:
        raise SnapshotCompositionError(
            f"bounded replacement ONS request receipts are incomplete: {source_id}"
        )
    selected_ids = {row["sourceRecordId"] for row in expected_pairs}
    changed_record_ids: set[str] = set()
    changed_fields = 0
    for record_id, base_record in base_records.items():
        replacement_record = replacement_records[record_id]
        differences = {
            key
            for key in set(base_record) | set(replacement_record)
            if (
                key not in base_record
                or key not in replacement_record
                or base_record[key] != replacement_record[key]
            )
        }
        if differences - {"versionDimensions"}:
            raise SnapshotCompositionError(
                f"bounded replacement changed protected fields for {source_id}:{record_id}"
            )
        if differences:
            if "versionDimensions" not in replacement_record:
                raise SnapshotCompositionError(
                    f"bounded replacement removed metadata for {source_id}:{record_id}"
                )
            _validate_ons_version_dimensions(
                replacement_record["versionDimensions"], source_id
            )
            changed_record_ids.add(record_id)
            changed_fields += 1
    if not changed_record_ids.issubset(selected_ids):
        raise SnapshotCompositionError(
            f"bounded replacement changed records outside its ONS selection: {source_id}"
        )

    for index, (page, pair) in enumerate(zip(enrichment_pages, expected_pairs, strict=True)):
        expected_url = pair["latestVersionHref"]
        _validate_ons_page_receipt(
            page,
            source_id,
            label=f"bounded replacement ONS version page {index}",
            expected_url=expected_url,
            require_single_record=True,
        )
        _ons_latest_version_identity(expected_url, source_id)
        record = replacement_records[pair["sourceRecordId"]]
        dimensions = record.get("versionDimensions")
        if dimensions is None:
            raise SnapshotCompositionError(
                f"bounded replacement ONS response is not represented: {source_id}"
            )
        _validate_ons_version_dimensions(dimensions, source_id)
        if page.get("contentSha256") != sha256_json({"dimensions": dimensions}):
            raise SnapshotCompositionError(
                f"bounded replacement ONS response hash is invalid: {source_id}"
            )

    mutable_provenance = {
        "assurance",
        "pageCount",
        "pages",
        "recordSetSha256",
        "retrievalMode",
        "snapshotSetSha256",
        "stopReason",
    }
    for key in _BASE_NOMIS_PROVENANCE_KEYS - mutable_provenance:
        if provenance[key] != base_provenance[key]:
            raise SnapshotCompositionError(
                f"bounded replacement changed unrelated base provenance {key!r}: {source_id}"
            )
    if provenance.get("pageCount") != len(replacement_pages):
        raise SnapshotCompositionError(
            f"bounded replacement ONS page count is invalid: {source_id}"
        )
    expected_complete = expected_selected_count == _ONS_EXPECTED_COHORT_COUNT
    retrieval_mode = provenance.get("retrievalMode")
    if (
        provenance.get("stopReason")
        != ("sourceExhausted" if expected_complete else "recordLimit")
        or retrieval_mode
        not in {
            "version-metadata-enrichment:frozen",
            "version-metadata-enrichment:prefer-cache",
            "version-metadata-enrichment:refresh",
        }
    ):
        raise SnapshotCompositionError(
            f"bounded replacement ONS run state is invalid: {source_id}"
        )
    if (
        retrieval_mode == "version-metadata-enrichment:frozen"
        and any(page["cacheHit"] is not True for page in enrichment_pages)
    ) or (
        retrieval_mode == "version-metadata-enrichment:refresh"
        and any(page["cacheHit"] is not False for page in enrichment_pages)
    ):
        raise SnapshotCompositionError(
            f"bounded replacement ONS cache receipts contradict retrieval mode: {source_id}"
        )
    if provenance.get("recordSetSha256") != sha256_json(replacement.get("records")):
        raise SnapshotCompositionError(
            f"bounded replacement ONS record-set hash is invalid: {source_id}"
        )
    replacement_snapshot_receipts = [
        {"requestUrl": page["requestUrl"], "contentSha256": page["contentSha256"]}
        for page in replacement_pages
    ]
    if provenance.get("snapshotSetSha256") != sha256_json(
        replacement_snapshot_receipts
    ):
        raise SnapshotCompositionError(
            f"bounded replacement ONS snapshot-set hash is invalid: {source_id}"
        )
    _assert_public_safe(replacement, source_id)
    return {"changedRecords": len(changed_record_ids), "changedFields": changed_fields}


def _validate_bounded_replacement(
    replacement: Mapping[str, Any],
    base: Mapping[str, Any],
    source_id: str,
    *,
    base_snapshot_id: str,
) -> dict[str, int]:
    """Validate a full-cohort replacement with narrowly allowlisted changes."""

    if source_id == _ONS_SOURCE_ID:
        return _validate_ons_bounded_replacement(
            replacement,
            base,
            source_id,
            base_snapshot_id=base_snapshot_id,
        )
    if source_id != _NOMIS_SOURCE_ID:
        raise SnapshotCompositionError(
            f"bounded replacement source is unsupported: {source_id}"
        )
    _validate_exact_keys(
        replacement, _ACQUISITION_KEYS, "bounded replacement acquisition"
    )
    _validate_exact_keys(base, _ACQUISITION_KEYS, "base Nomis acquisition")
    if (
        replacement.get("schemaVersion") != "okf-ons.source-acquisition.v1"
        or base.get("schemaVersion") != "okf-ons.source-acquisition.v1"
    ):
        raise SnapshotCompositionError(
            f"bounded replacement acquisition schema is unsupported: {source_id}"
        )
    provenance = replacement.get("provenance")
    base_provenance = base.get("provenance")
    if not isinstance(provenance, Mapping) or not isinstance(base_provenance, Mapping):
        raise SnapshotCompositionError(
            f"bounded replacement provenance is malformed: {source_id}"
        )
    _validate_exact_keys(
        base_provenance,
        _BASE_NOMIS_PROVENANCE_KEYS,
        "base Nomis acquisition provenance",
    )
    _validate_exact_keys(
        provenance,
        _REPLACEMENT_PROVENANCE_KEYS,
        "bounded replacement provenance",
    )
    base_source = base_provenance.get("source")
    source = provenance.get("source")
    if (
        not isinstance(base_source, Mapping)
        or not isinstance(source, Mapping)
        or base_source.get("id") != _NOMIS_SOURCE_ID
        or source != base_source
    ):
        raise SnapshotCompositionError(
            f"bounded replacement source provenance is invalid: {source_id}"
        )
    declaration = provenance.get("replacement")
    if (
        not isinstance(declaration, Mapping)
        or declaration.get("schema") != _BOUNDED_REPLACEMENT_SCHEMA
        or declaration.get("baseSnapshotId") != base_snapshot_id
        or declaration.get("baseRecordSetSha256")
        != base_provenance.get("recordSetSha256")
        or declaration.get("baseSnapshotSetSha256")
        != base_provenance.get("snapshotSetSha256")
    ):
        raise SnapshotCompositionError(
            f"bounded replacement is not bound to its base acquisition: {source_id}"
        )
    _validate_exact_keys(
        declaration,
        _REPLACEMENT_DECLARATION_KEYS,
        "bounded replacement declaration",
    )
    raw_fields = declaration.get("allowedRecordFields")
    if (
        not isinstance(raw_fields, list)
        or raw_fields != sorted(_SAFE_REPLACEMENT_FIELDS)
    ):
        raise SnapshotCompositionError(
            f"bounded replacement field declaration is malformed: {source_id}"
        )
    allowed_fields = set(raw_fields)

    base_records = _replacement_records_by_id(
        base.get("records"), source_id, label="base acquisition"
    )
    replacement_records = _replacement_records_by_id(
        replacement.get("records"), source_id, label="replacement acquisition"
    )
    if set(base_records) != set(replacement_records):
        raise SnapshotCompositionError(
            f"bounded replacement changed the source-record cohort: {source_id}"
        )
    base_record_ids = list(base_records)
    if list(replacement_records) != base_record_ids:
        raise SnapshotCompositionError(
            f"bounded replacement reordered the source-record cohort: {source_id}"
        )
    if not base_record_ids or any(
        _NOMIS_ID_RE.fullmatch(record_id) is None for record_id in base_record_ids
    ):
        raise SnapshotCompositionError(
            f"base Nomis cohort identity is invalid: {source_id}"
        )

    changed_record_ids: set[str] = set()
    changed_fields = 0
    for record_id, base_record in base_records.items():
        replacement_record = replacement_records[record_id]
        differences = {
            key
            for key in set(base_record) | set(replacement_record)
            if (
                key not in base_record
                or key not in replacement_record
                or base_record[key] != replacement_record[key]
            )
        }
        if differences - allowed_fields:
            raise SnapshotCompositionError(
                f"bounded replacement changed protected fields for {source_id}:{record_id}"
            )
        if differences:
            changed_record_ids.add(record_id)
        for field in differences:
            if field not in replacement_record:
                raise SnapshotCompositionError(
                    f"bounded replacement removed metadata for {source_id}:{record_id}"
                )
            _validate_replacement_field(field, replacement_record[field], source_id)
            changed_fields += 1

    mutable_provenance = {
        "assurance",
        "pageCount",
        "pages",
        "recordSetSha256",
        "retrievalMode",
        "snapshotSetSha256",
        "stopReason",
    }
    for key in _BASE_NOMIS_PROVENANCE_KEYS - mutable_provenance:
        if provenance[key] != base_provenance[key]:
            raise SnapshotCompositionError(
                f"bounded replacement changed unrelated base provenance {key!r}: {source_id}"
            )
    base_pages = base_provenance.get("pages")
    replacement_pages = provenance.get("pages")
    if (
        not isinstance(base_pages, list)
        or not isinstance(replacement_pages, list)
        or len(replacement_pages) < len(base_pages)
    ):
        raise SnapshotCompositionError(
            f"bounded replacement page lineage is incomplete: {source_id}"
        )
    if replacement_pages[: len(base_pages)] != base_pages:
        raise SnapshotCompositionError(
            f"bounded replacement changed base page lineage: {source_id}"
        )

    assurance = provenance.get("assurance")
    if (
        not isinstance(assurance, Mapping)
        or set(assurance) != set(_REPLACEMENT_ASSURANCE)
        or any(
            assurance[key] is not expected
            for key, expected in _REPLACEMENT_ASSURANCE.items()
        )
    ):
        raise SnapshotCompositionError(
            f"bounded replacement lacks metadata-only assurance: {source_id}"
        )
    run = provenance.get("enrichmentRun")
    if not isinstance(run, Mapping):
        raise SnapshotCompositionError(
            f"bounded replacement enrichment run is missing: {source_id}"
        )
    _validate_exact_keys(run, _ENRICHMENT_RUN_KEYS, "bounded replacement enrichment run")
    if run.get("schema") != _NOMIS_ENRICHMENT_SCHEMA:
        raise SnapshotCompositionError(
            f"bounded replacement enrichment schema is unsupported: {source_id}"
        )
    cohort_count = run.get("cohortCount")
    selected_count = run.get("selectedCount")
    unselected_count = run.get("unselectedCount")
    requested_limit = run.get("requestedLimit")
    expected_selected_count = (
        min(requested_limit, len(base_records))
        if isinstance(requested_limit, int) and not isinstance(requested_limit, bool)
        else -1
    )
    if (
        isinstance(cohort_count, bool)
        or not isinstance(cohort_count, int)
        or cohort_count != len(base_records)
        or isinstance(selected_count, bool)
        or not isinstance(selected_count, int)
        or selected_count != expected_selected_count
        or isinstance(unselected_count, bool)
        or not isinstance(unselected_count, int)
        or unselected_count != cohort_count - selected_count
        or not isinstance(run.get("coverageComplete"), bool)
        or run.get("coverageComplete") is not (selected_count == cohort_count)
        or run.get("selectionOrder") != "sha256(sourceRecordId)-ascending"
        or run.get("select") != _NOMIS_OVERVIEW_SELECT.split(",")
    ):
        raise SnapshotCompositionError(
            f"bounded replacement enrichment denominator is invalid: {source_id}"
        )
    selected_ids = _validate_nomis_enrichment_pages(
        replacement_pages[len(base_pages) :],
        run,
        source_id,
        base_record_ids,
    )
    if len(selected_ids) != selected_count or not changed_record_ids.issubset(selected_ids):
        raise SnapshotCompositionError(
            f"bounded replacement changed records outside its selection: {source_id}"
        )
    if provenance.get("pageCount") != len(replacement_pages):
        raise SnapshotCompositionError(
            f"bounded replacement page count is invalid: {source_id}"
        )
    expected_complete = selected_count == cohort_count
    retrieval_mode = provenance.get("retrievalMode")
    if (
        provenance.get("stopReason")
        != ("sourceExhausted" if expected_complete else "recordLimit")
        or retrieval_mode
        not in {
            "overview-enrichment:frozen",
            "overview-enrichment:prefer-cache",
            "overview-enrichment:refresh",
        }
    ):
        raise SnapshotCompositionError(
            f"bounded replacement run state is invalid: {source_id}"
        )
    enrichment_pages = replacement_pages[len(base_pages) :]
    if (
        retrieval_mode == "overview-enrichment:frozen"
        and any(page["cacheHit"] is not True for page in enrichment_pages)
    ) or (
        retrieval_mode == "overview-enrichment:refresh"
        and any(page["cacheHit"] is not False for page in enrichment_pages)
    ):
        raise SnapshotCompositionError(
            f"bounded replacement cache receipts contradict retrieval mode: {source_id}"
        )
    if provenance.get("recordSetSha256") != sha256_json(replacement.get("records")):
        raise SnapshotCompositionError(
            f"bounded replacement record-set hash is invalid: {source_id}"
        )
    snapshot_receipts = [
        {
            "requestUrl": page["requestUrl"],
            "contentSha256": page["contentSha256"],
        }
        for page in replacement_pages
    ]
    if provenance.get("snapshotSetSha256") != sha256_json(snapshot_receipts):
        raise SnapshotCompositionError(
            f"bounded replacement snapshot-set hash is invalid: {source_id}"
        )
    _assert_public_safe(replacement, source_id)
    return {"changedRecords": len(changed_record_ids), "changedFields": changed_fields}


def _load_base_snapshot(
    directory: Path,
    sources: Mapping[str, SourceDefinition],
    *,
    require_complete: bool,
) -> tuple[dict[str, Any], dict[str, tuple[bytes, dict[str, Any]]], str]:
    if directory.is_symlink() or not directory.is_dir():
        raise SnapshotCompositionError("base snapshot directory is unsafe")
    manifest_path = directory / "snapshot.json"
    manifest_bytes = (
        manifest_path.read_bytes()
        if manifest_path.is_file() and not manifest_path.is_symlink()
        else b""
    )
    if not manifest_bytes:
        raise SnapshotCompositionError("base snapshot manifest is missing")
    manifest = _read_json_object(manifest_path)
    manifest_keys = set(manifest)
    if manifest_keys != _MANIFEST_KEYS and manifest_keys != _MANIFEST_KEYS | {"basedOn"}:
        raise SnapshotCompositionError("base snapshot manifest fields are not allowlisted")
    if manifest.get("schema") != "okf-ons.frozen-snapshot.v1":
        raise SnapshotCompositionError("base snapshot uses an unsupported schema")
    if manifest.get("metadataOnly") is not True:
        raise SnapshotCompositionError("base snapshot must assert metadataOnly=true")
    if manifest.get("observationsIncluded") is not False:
        raise SnapshotCompositionError("base snapshot must assert observationsIncluded=false")
    if not isinstance(manifest.get("completeForRegisteredAdapters"), bool):
        raise SnapshotCompositionError("base snapshot completeness flag is malformed")
    snapshot_id = manifest.get("snapshotId")
    if (
        not isinstance(snapshot_id, str)
        or not snapshot_id
        or Path(snapshot_id).name != snapshot_id
        or snapshot_id in {".", ".."}
    ):
        raise SnapshotCompositionError("base snapshot id is unsafe")
    if not isinstance(manifest.get("claimBoundary"), str) or not manifest[
        "claimBoundary"
    ].strip():
        raise SnapshotCompositionError("base snapshot claim boundary is malformed")
    based_on = manifest.get("basedOn")
    if based_on is not None:
        if not isinstance(based_on, Mapping):
            raise SnapshotCompositionError("base snapshot lineage is malformed")
        _validate_exact_keys(
            based_on, {"manifestSha256", "snapshotId"}, "base snapshot lineage"
        )
        if not isinstance(based_on["snapshotId"], str) or not based_on["snapshotId"]:
            raise SnapshotCompositionError("base snapshot lineage is malformed")
        _validated_sha256(based_on["manifestSha256"], "base snapshot lineage hash")
    rows = manifest.get("sources")
    if not isinstance(rows, list) or not rows:
        raise SnapshotCompositionError("base snapshot has no source rows")

    resolved_directory = directory.resolve()
    carried: dict[str, tuple[bytes, dict[str, Any]]] = {}
    filenames: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise SnapshotCompositionError("base snapshot source row is malformed")
        row_keys = set(row)
        if row_keys != _MANIFEST_SOURCE_KEYS and row_keys != _MANIFEST_SOURCE_KEYS | {
            "explainedExclusionCount"
        }:
            raise SnapshotCompositionError("base snapshot source row fields are not allowlisted")
        if not isinstance(row.get("coverageComplete"), bool):
            raise SnapshotCompositionError("base snapshot source coverage flag is malformed")
        for key in (
            "normalisationDroppedCount",
            "recordCount",
            "unrepresentedCount",
        ):
            if (
                isinstance(row.get(key), bool)
                or not isinstance(row.get(key), int)
                or row[key] < 0
            ):
                raise SnapshotCompositionError(
                    f"base snapshot source row count is malformed: {key}"
                )
        reported_total = row.get("reportedTotal")
        if reported_total is not None and (
            isinstance(reported_total, bool)
            or not isinstance(reported_total, int)
            or reported_total < 0
        ):
            raise SnapshotCompositionError(
                "base snapshot source reported total is malformed"
            )
        if "explainedExclusionCount" in row and (
            isinstance(row["explainedExclusionCount"], bool)
            or not isinstance(row["explainedExclusionCount"], int)
            or row["explainedExclusionCount"] < 0
        ):
            raise SnapshotCompositionError(
                "base snapshot explained exclusion count is malformed"
            )
        source_id = str(row.get("sourceId") or "")
        definition = sources.get(source_id)
        if definition is None or source_id in carried:
            raise SnapshotCompositionError(
                f"base snapshot has an unknown or duplicate source: {source_id}"
            )
        filename = str(row.get("file") or "")
        if (
            not filename
            or Path(filename).name != filename
            or filename in filenames
            or filename != f"{source_id}.json"
        ):
            raise SnapshotCompositionError(f"base snapshot filename is unsafe: {source_id}")
        filenames.add(filename)
        path = directory / filename
        if (
            path.is_symlink()
            or not path.is_file()
            or path.resolve().parent != resolved_directory
        ):
            raise SnapshotCompositionError(f"base snapshot source file is unsafe: {source_id}")
        data = path.read_bytes()
        _validated_sha256(row.get("sha256"), f"base snapshot file hash for {source_id}")
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
    parser.add_argument(
        "--replacement-acquisition",
        action="append",
        type=Path,
        default=[],
        help=(
            "Full-cohort bounded replacement envelope tied to --base-snapshot; "
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
    if arguments.source_ids is not None:
        selected_ids = arguments.source_ids
    elif arguments.replacement_acquisition:
        selected_ids = []
    else:
        selected_ids = [
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
    if arguments.replacement_acquisition and base_manifest is None:
        parser.error("replacement acquisitions require --base-snapshot")

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

        for replacement_path in arguments.replacement_acquisition:
            try:
                public_result = json.loads(replacement_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise SnapshotCompositionError(
                    f"unable to read replacement acquisition {replacement_path}: {exc}"
                ) from exc
            if not isinstance(public_result, dict):
                raise SnapshotCompositionError(
                    f"malformed replacement acquisition: {replacement_path}"
                )
            provenance = public_result.get("provenance")
            source = provenance.get("source") if isinstance(provenance, Mapping) else None
            source_id = str(source.get("id") or "") if isinstance(source, Mapping) else ""
            if source_id not in sources or source_id not in base_sources:
                raise SnapshotCompositionError(
                    f"replacement acquisition source is not present in the base: {source_id}"
                )
            base_data, _ = base_sources[source_id]
            try:
                base_public_result = json.loads(base_data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise SnapshotCompositionError(
                    f"base acquisition is unreadable for replacement: {source_id}"
                ) from exc
            if not isinstance(base_public_result, dict):
                raise SnapshotCompositionError(
                    f"base acquisition is malformed for replacement: {source_id}"
                )
            change_summary = _validate_bounded_replacement(
                public_result,
                base_public_result,
                source_id,
                base_snapshot_id=str(base_manifest.get("snapshotId") or ""),
            )
            add_public_result(source_id, public_result)
            print(
                f"{source_id}: bounded replacement changed "
                f"{change_summary['changedFields']} fields across "
                f"{change_summary['changedRecords']} records"
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
