#!/usr/bin/env python3
"""Acquire bounded, metadata-only ONS latest-version dimension metadata.

The frozen ONS catalogue supplies the exact 337-record cohort and the exact
``links.latest_version.href`` resource for each record. Raw version responses
are never written. The external cache and emitted replacement envelope retain
only a deeply allowlisted dimension projection which is sufficient to
identify an explicit geography dimension and preserve dimension-level quality
statements.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from okf_ons.model import plain_text  # noqa: E402

SOURCE_ID = "ons-data-api"
SOURCE_ENDPOINT = "https://api.beta.ons.gov.uk/v1/datasets"
DEFAULT_SNAPSHOT = ROOT / "source" / "metadata-enrichment-2026-07-21-r4"
EXPECTED_COHORT_COUNT = 337
MAX_RESPONSE_BYTES = 2_000_000
MAX_CACHE_BYTES = 1_000_000
MAX_BASE_FILE_BYTES = 128_000_000
MIN_PRODUCTION_INTERVAL_SECONDS = 0.2
DEFAULT_REQUEST_INTERVAL_SECONDS = 0.5
USER_AGENT = "okf-ons/ons-version-metadata (metadata-only; no observations)"

_CACHE_SCHEMA = "okf-ons.ons-version-metadata-cache.v1"
_REPLACEMENT_SCHEMA = "okf-ons.bounded-source-replacement.v1"
_ENRICHMENT_SCHEMA = "okf-ons.ons-version-metadata-enrichment.v1"
_ACQUISITION_KEYS = {"schemaVersion", "records", "provenance"}
_BASE_PROVENANCE_KEYS = {
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
_BASE_SOURCE_KEYS = {
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
_BASE_ASSURANCE = {
    "cacheLocationPublished": False,
    "credentialsRequired": False,
    "metadataOnly": True,
    "observationsFetched": False,
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
_CACHE_KEYS = {
    "contentSha256",
    "payload",
    "requestUrl",
    "responseHeaders",
    "responseUrl",
    "retrievedAt",
    "schema",
}
_SAFE_RESPONSE_HEADER_KEYS = {
    "content-type",
    "etag",
    "last-modified",
    "retry-after",
}
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
_VERSION_KEYS = {
    "alerts",
    "collection_id",
    "dimensions",
    "downloads",
    "edition",
    "id",
    "is_based_on",
    "last_updated",
    "latest_changes",
    "links",
    "lowest_geography",
    "release_date",
    "state",
    "type",
    "usage_notes",
    "version",
}
_VERSION_LINK_KEYS = {"dataset", "dimensions", "edition", "self"}
_VERSION_LINK_REQUIRED_KEYS = {"dataset", "edition", "self"}
_LINK_KEYS = {"href", "id"}
_DIMENSION_KEYS = {
    "description",
    "href",
    "id",
    "is_area_type",
    "label",
    "links",
    "name",
    "number_of_options",
    "quality_statement_text",
    "quality_statement_url",
    "variable",
}
_DIMENSION_LINK_KEYS = {"code_list", "options", "version"}
_PROJECTED_DIMENSION_KEYS = {
    "id",
    "isAreaType",
    "label",
    "name",
    "qualityStatementText",
    "qualityStatementUrl",
}
_PROJECTED_PAYLOAD_KEYS = {"dimensions"}
_HEX_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RECORD_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*$")
_EDITION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]*$")
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
_FORBIDDEN_KEYS = {
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
    "features",
    "geometry",
    "observation",
    "observations",
    "obs",
    "option",
    "options",
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


class ONSVersionMetadataError(ValueError):
    """Raised when ONS version metadata cannot be safely acquired or projected."""


@dataclass(frozen=True)
class JsonResponse:
    payload: Any
    final_url: str
    status: int = 200
    headers: Mapping[str, str] | None = None


class JsonTransport(Protocol):
    def get(self, url: str, *, timeout: float) -> JsonResponse: ...


class UrllibJsonTransport:
    """Bounded JSON transport for the public, credential-free ONS API."""

    def get(self, url: str, *, timeout: float) -> JsonResponse:
        request = Request(
            url,
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        )
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                body = response.read(MAX_RESPONSE_BYTES + 1)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise ONSVersionMetadataError(
                        "ONS version response exceeded the byte limit"
                    )
                try:
                    payload = json.loads(body.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ONSVersionMetadataError(
                        "ONS version response was not valid UTF-8 JSON"
                    ) from exc
                headers = {
                    key.casefold(): response.headers[key]
                    for key in ("Content-Type", "ETag", "Last-Modified", "Retry-After")
                    if response.headers.get(key)
                }
                return JsonResponse(
                    payload=payload,
                    final_url=response.geturl(),
                    status=int(response.status),
                    headers=headers,
                )
        except HTTPError as exc:
            headers = {
                key.casefold(): exc.headers[key]
                for key in ("Content-Type", "ETag", "Last-Modified", "Retry-After")
                if exc.headers and exc.headers.get(key)
            }
            return JsonResponse(
                payload=None,
                final_url=exc.geturl(),
                status=int(exc.code),
                headers=headers,
            )
        except URLError as exc:
            raise ONSVersionMetadataError("ONS version request failed") from exc


def canonical_json(value: Any, *, pretty: bool = False) -> str:
    options: dict[str, Any] = {
        "allow_nan": False,
        "ensure_ascii": True,
        "sort_keys": True,
    }
    if pretty:
        options["indent"] = 2
    else:
        options["separators"] = (",", ":")
    return json.dumps(value, **options)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


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
        raise ONSVersionMetadataError(f"{label} has " + "; ".join(detail))


def _validated_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _HEX_SHA256_RE.fullmatch(value):
        raise ONSVersionMetadataError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _validate_utc_timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _UTC_TIMESTAMP_RE.fullmatch(value):
        raise ONSVersionMetadataError(f"{label} must be a UTC ISO 8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ONSVersionMetadataError(f"{label} must be a UTC ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ONSVersionMetadataError(f"{label} must be a UTC ISO 8601 timestamp")
    return value


def _normalised_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def _assert_safe(value: Any, *, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if _normalised_key(key) in _FORBIDDEN_KEYS:
                raise ONSVersionMetadataError(
                    f"ONS version metadata contains unsafe field {key!r} at {path}"
                )
            _assert_safe(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_safe(child, path=f"{path}[{index}]")
    elif isinstance(value, bytes):
        raise ONSVersionMetadataError(f"ONS version metadata contains binary data at {path}")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ONSVersionMetadataError(
            f"ONS version metadata contains a non-finite number at {path}"
        )
    elif isinstance(value, str):
        if _LOCAL_PATH_RE.search(value) or any(
            pattern.search(value) for pattern in _SECRET_VALUE_PATTERNS
        ):
            raise ONSVersionMetadataError(
                f"ONS version metadata contains an unsafe value at {path}"
            )


def _validated_response_headers(
    value: Any, *, require_json_content_type: bool = True
) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ONSVersionMetadataError("ONS version response headers are malformed")
    headers: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        if not isinstance(raw_key, str):
            raise ONSVersionMetadataError("ONS version response headers are malformed")
        key = raw_key.casefold()
        if (
            key != raw_key
            or key not in _SAFE_RESPONSE_HEADER_KEYS
            or key in headers
            or not isinstance(raw_value, str)
            or not raw_value.strip()
            or len(raw_value) > 2_000
            or _LOCAL_PATH_RE.search(raw_value)
            or any(pattern.search(raw_value) for pattern in _SECRET_VALUE_PATTERNS)
        ):
            raise ONSVersionMetadataError("ONS version response headers are unsafe")
        headers[key] = raw_value
    content_type = headers.get("content-type")
    if (
        require_json_content_type
        and content_type is not None
        and not content_type.casefold().startswith("application/json")
    ):
        raise ONSVersionMetadataError("ONS version response content type is not JSON")
    return headers


def _validate_public_url(value: Any) -> str:
    url = plain_text(value, 2_000)
    if not url:
        return ""
    parsed = urlsplit(url)
    query_keys = {key.casefold() for key, _ in parse_qsl(parsed.query)}
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or query_keys.intersection(_SECRET_QUERY_KEYS)
        or _LOCAL_PATH_RE.search(url)
        or any(pattern.search(url) for pattern in _SECRET_VALUE_PATTERNS)
    ):
        return ""
    return url


def _version_identity(url: Any) -> tuple[str, str, int]:
    if not isinstance(url, str):
        raise ONSVersionMetadataError("ONS latest-version URL is malformed")
    parsed = urlsplit(url)
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
        raise ONSVersionMetadataError(
            "latest-version request escaped the exact public ONS API template"
        )
    record_id, edition, raw_version = match.groups()
    if not _RECORD_ID_RE.fullmatch(record_id) or not _EDITION_RE.fullmatch(edition):
        raise ONSVersionMetadataError("ONS latest-version URL identity is malformed")
    return record_id, edition, int(raw_version)


def _validate_link(
    value: Any, *, label: str, allow_empty: bool = False
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not set(value).issubset(_LINK_KEYS):
        raise ONSVersionMetadataError(f"{label} is malformed")
    projected: dict[str, Any] = {}
    if "id" in value:
        identifier = plain_text(value.get("id"), 500)
        if not identifier:
            raise ONSVersionMetadataError(f"{label} is malformed")
        projected["id"] = identifier
    if "href" in value:
        href = _validate_public_url(value.get("href"))
        if not href:
            raise ONSVersionMetadataError(f"{label} is unsafe")
        projected["href"] = href
    if not projected and not allow_empty:
        raise ONSVersionMetadataError(f"{label} is malformed")
    return projected


def _project_dimension(value: Any, *, index: int) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ONSVersionMetadataError(f"ONS dimension {index} is malformed")
    unknown = sorted(set(value) - _DIMENSION_KEYS)
    if unknown:
        raise ONSVersionMetadataError(
            f"ONS dimension {index} has unreviewed field(s): " + ", ".join(unknown)
        )
    for key in ("description", "href", "variable"):
        raw = value.get(key)
        if raw is not None and not isinstance(raw, str):
            raise ONSVersionMetadataError(f"ONS dimension {index}.{key} is malformed")
    links = value.get("links")
    if links is not None:
        if (
            not isinstance(links, Mapping)
            or set(links) - _DIMENSION_LINK_KEYS
        ):
            raise ONSVersionMetadataError(f"ONS dimension {index}.links is malformed")
        for link_name, link_value in links.items():
            _validate_link(
                link_value,
                label=f"ONS dimension {index}.links.{link_name}",
                # ONS emits empty typed link objects where no link is exposed.
                allow_empty=True,
            )
    number_of_options = value.get("number_of_options")
    if number_of_options is not None and (
        isinstance(number_of_options, bool)
        or not isinstance(number_of_options, int)
        or number_of_options < 0
    ):
        raise ONSVersionMetadataError(
            f"ONS dimension {index}.number_of_options is malformed"
        )
    projected: dict[str, Any] = {}
    for key in ("id", "name"):
        if not isinstance(value.get(key), str):
            raise ONSVersionMetadataError(f"ONS dimension {index}.{key} is required")
        text = plain_text(value.get(key), 500)
        if not text:
            raise ONSVersionMetadataError(f"ONS dimension {index}.{key} is required")
        projected[key] = text
    raw_label = value.get("label")
    if raw_label is not None and not isinstance(raw_label, str):
        raise ONSVersionMetadataError(f"ONS dimension {index}.label is malformed")
    if label := plain_text(raw_label, 500):
        projected["label"] = label
    is_area_type = value.get("is_area_type")
    if is_area_type is not None and not isinstance(is_area_type, bool):
        raise ONSVersionMetadataError(
            f"ONS dimension {index}.is_area_type is malformed"
        )
    projected["isAreaType"] = is_area_type is True
    raw_quality_url = value.get("quality_statement_url")
    if raw_quality_url is not None and not isinstance(raw_quality_url, str):
        raise ONSVersionMetadataError(
            f"ONS dimension {index}.quality_statement_url is malformed"
        )
    quality_url = plain_text(raw_quality_url, 2_000)
    if quality_url:
        safe_url = _validate_public_url(quality_url)
        if not safe_url:
            raise ONSVersionMetadataError(
                f"ONS dimension {index}.quality_statement_url is unsafe"
            )
        projected["qualityStatementUrl"] = safe_url
    raw_quality_text = value.get("quality_statement_text")
    if raw_quality_text is not None and not isinstance(raw_quality_text, str):
        raise ONSVersionMetadataError(
            f"ONS dimension {index}.quality_statement_text is malformed"
        )
    quality_text = plain_text(raw_quality_text, 20_000)
    if quality_text:
        projected["qualityStatementText"] = quality_text
    _assert_safe(projected, path=f"$.dimensions[{index}]")
    return projected


def _project_version_payload(
    payload: Any,
    *,
    request_url: str,
    expected_record_id: str,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ONSVersionMetadataError(f"ONS version is malformed for {expected_record_id}")
    unknown = sorted(set(payload) - _VERSION_KEYS)
    if unknown:
        raise ONSVersionMetadataError(
            "ONS version has unreviewed field(s): " + ", ".join(unknown)
        )
    record_id, edition, version = _version_identity(request_url)
    if record_id != expected_record_id:
        raise ONSVersionMetadataError(
            f"ONS version identity mismatch for {expected_record_id}"
        )
    # The version resource's top-level ``id`` is an opaque resource UUID, not
    # the dataset id from the request path. Bind dataset identity through the
    # exact frozen URL and the response's dataset/edition/self links instead.
    version_resource_id = plain_text(payload.get("id"), 500)
    if (
        not version_resource_id
        or payload.get("edition") != edition
        or isinstance(payload.get("version"), bool)
        or payload.get("version") != version
    ):
        raise ONSVersionMetadataError(
            f"ONS version identity mismatch for {expected_record_id}"
        )
    links = payload.get("links")
    if (
        not isinstance(links, Mapping)
        or not _VERSION_LINK_REQUIRED_KEYS.issubset(links)
        or set(links) - _VERSION_LINK_KEYS
    ):
        raise ONSVersionMetadataError("ONS version identity links are malformed")
    safe_links = {
        key: _validate_link(
            value,
            label=f"ONS version links.{key}",
            # The live API legitimately emits an empty dimensions link object;
            # it is not used as identity evidence or followed by this lane.
            allow_empty=key == "dimensions",
        )
        for key, value in links.items()
    }
    if (
        safe_links["dataset"].get("id") != record_id
        or safe_links["edition"].get("id") != edition
        or safe_links["self"].get("href") != request_url
    ):
        raise ONSVersionMetadataError(
            f"ONS version identity mismatch for {expected_record_id}"
        )
    dimensions = payload.get("dimensions")
    if not isinstance(dimensions, list) or not dimensions:
        raise ONSVersionMetadataError(
            f"ONS version dimensions are malformed for {expected_record_id}"
        )
    projected = [
        _project_dimension(dimension, index=index)
        for index, dimension in enumerate(dimensions)
    ]
    dimension_ids = [dimension["id"] for dimension in projected]
    if len(set(dimension_ids)) != len(dimension_ids):
        raise ONSVersionMetadataError(
            f"ONS version has duplicate dimensions for {expected_record_id}"
        )
    safe = {"dimensions": projected}
    _assert_safe(safe)
    return safe


def _validate_projected_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ONSVersionMetadataError("ONS projected version metadata is malformed")
    _validate_exact_keys(payload, _PROJECTED_PAYLOAD_KEYS, "ONS projected metadata")
    dimensions = payload.get("dimensions")
    if not isinstance(dimensions, list) or not dimensions:
        raise ONSVersionMetadataError("ONS projected dimensions are malformed")
    validated: list[dict[str, Any]] = []
    for index, raw in enumerate(dimensions):
        if not isinstance(raw, Mapping):
            raise ONSVersionMetadataError(f"ONS projected dimension {index} is malformed")
        keys = set(raw)
        required = {"id", "name", "isAreaType"}
        if not required.issubset(keys) or not keys.issubset(_PROJECTED_DIMENSION_KEYS):
            raise ONSVersionMetadataError(
                f"ONS projected dimension {index} has unreviewed or missing fields"
            )
        for key in ("id", "name"):
            if not isinstance(raw.get(key), str) or not plain_text(raw.get(key), 500):
                raise ONSVersionMetadataError(
                    f"ONS projected dimension {index}.{key} is malformed"
                )
        if "label" in raw and (
            not isinstance(raw["label"], str)
            or not plain_text(raw["label"], 500)
        ):
            raise ONSVersionMetadataError(
                f"ONS projected dimension {index}.label is malformed"
            )
        if not isinstance(raw.get("isAreaType"), bool):
            raise ONSVersionMetadataError(
                f"ONS projected dimension {index}.isAreaType is malformed"
            )
        if "qualityStatementUrl" in raw and (
            not isinstance(raw["qualityStatementUrl"], str)
            or _validate_public_url(raw["qualityStatementUrl"])
            != raw["qualityStatementUrl"]
        ):
            raise ONSVersionMetadataError(
                f"ONS projected dimension {index} quality URL is unsafe"
            )
        if "qualityStatementText" in raw and (
            not isinstance(raw["qualityStatementText"], str)
            or not plain_text(raw["qualityStatementText"], 20_000)
        ):
            raise ONSVersionMetadataError(
                f"ONS projected dimension {index} quality text is malformed"
            )
        validated.append(dict(raw))
    if len({row["id"] for row in validated}) != len(validated):
        raise ONSVersionMetadataError("ONS projected dimensions contain duplicate ids")
    safe = {"dimensions": validated}
    _assert_safe(safe)
    return safe


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _retry_after_seconds(value: Any, *, current: datetime) -> float:
    if not isinstance(value, str) or not value.strip():
        raise ONSVersionMetadataError("ONS Retry-After header is malformed")
    candidate = value.strip()
    try:
        seconds = float(candidate)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(candidate)
        except (TypeError, ValueError) as exc:
            raise ONSVersionMetadataError("ONS Retry-After header is malformed") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        seconds = max(0.0, (parsed.astimezone(UTC) - current.astimezone(UTC)).total_seconds())
    if not math.isfinite(seconds) or seconds < 0 or seconds > 300:
        raise ONSVersionMetadataError("ONS Retry-After header is outside safe bounds")
    return seconds


def _cache_path(cache_directory: Path, request_url: str) -> Path:
    digest = hashlib.sha256(request_url.encode("utf-8")).hexdigest()
    return cache_directory / "ons-version-metadata" / f"{digest}.json"


def _write_atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True
    )
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical_json(value, pretty=True))
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _load_cache(path: Path, request_url: str, record_id: str) -> dict[str, Any]:
    expected_parent = path.parent.resolve()
    if (
        path.is_symlink()
        or not path.is_file()
        or path.resolve().parent != expected_parent
    ):
        raise ONSVersionMetadataError("ONS version cache entry is not a regular file")
    try:
        payload_bytes = path.read_bytes()
        if len(payload_bytes) > MAX_CACHE_BYTES:
            raise ONSVersionMetadataError("ONS version cache entry exceeds the size limit")
        envelope = json.loads(payload_bytes)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ONSVersionMetadataError("ONS version cache entry is unreadable") from exc
    if not isinstance(envelope, dict):
        raise ONSVersionMetadataError("ONS version cache entry failed validation")
    _validate_exact_keys(envelope, _CACHE_KEYS, "ONS version cache entry")
    if (
        envelope.get("schema") != _CACHE_SCHEMA
        or envelope.get("requestUrl") != request_url
        or envelope.get("responseUrl") != request_url
    ):
        raise ONSVersionMetadataError("ONS version cache entry failed validation")
    cached_id, _, _ = _version_identity(request_url)
    if cached_id != record_id:
        raise ONSVersionMetadataError(f"ONS version identity mismatch for {record_id}")
    _validate_utc_timestamp(envelope.get("retrievedAt"), "ONS version retrieval time")
    envelope["responseHeaders"] = _validated_response_headers(
        envelope.get("responseHeaders")
    )
    envelope["payload"] = _validate_projected_payload(envelope.get("payload"))
    _validated_sha256(envelope.get("contentSha256"), "ONS version content hash")
    if envelope["contentSha256"] != sha256_json(envelope["payload"]):
        raise ONSVersionMetadataError("ONS version cache entry failed validation")
    _assert_safe(envelope)
    return envelope


def _fetch_version_metadata(
    record_id: str,
    request_url: str,
    *,
    cache_directory: Path,
    mode: str,
    transport: JsonTransport,
    timeout_seconds: float,
    retries: int,
    now: Callable[[], datetime],
    sleep: Callable[[float], None],
) -> tuple[dict[str, Any], dict[str, Any]]:
    url_record_id, _, _ = _version_identity(request_url)
    if url_record_id != record_id:
        raise ONSVersionMetadataError(f"ONS version identity mismatch for {record_id}")
    cache_path = _cache_path(cache_directory, request_url)
    if mode != "refresh" and (cache_path.exists() or cache_path.is_symlink()):
        cached = _load_cache(cache_path, request_url, record_id)
        return dict(cached["payload"]), {
            "requestUrl": request_url,
            "responseUrl": cached["responseUrl"],
            "retrievedAt": cached["retrievedAt"],
            "contentSha256": cached["contentSha256"],
            "responseHeaders": cached.get("responseHeaders", {}),
            "cacheHit": True,
            "upstreamRecordCount": 1,
            "normalisedRecordCount": 1,
        }
    if mode == "frozen":
        raise ONSVersionMetadataError(
            f"frozen cache is missing ONS version metadata for {record_id}"
        )

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = transport.get(request_url, timeout=timeout_seconds)
            if response.final_url != request_url:
                raise ONSVersionMetadataError("ONS version response URL changed unexpectedly")
            response_headers = _validated_response_headers(
                response.headers or {},
                require_json_content_type=response.status not in {429, 503},
            )
            if response.status in {429, 503}:
                retry_after = response_headers.get("retry-after")
                if retry_after is None:
                    raise ONSVersionMetadataError(
                        f"ONS returned HTTP {response.status} without Retry-After"
                    )
                if attempt >= retries:
                    raise ONSVersionMetadataError(
                        f"ONS returned HTTP {response.status} after retries"
                    )
                sleep(
                    max(
                        min(2**attempt, 8),
                        _retry_after_seconds(retry_after, current=now()),
                    )
                )
                continue
            if (
                isinstance(response.status, bool)
                or not isinstance(response.status, int)
                or response.status < 200
                or response.status >= 300
            ):
                raise ONSVersionMetadataError(f"ONS returned HTTP {response.status}")
            payload = _project_version_payload(
                response.payload,
                request_url=request_url,
                expected_record_id=record_id,
            )
            retrieved_at = _utc_iso(now())
            _validate_utc_timestamp(retrieved_at, "ONS version retrieval time")
            content_sha256 = sha256_json(payload)
            cached = {
                "schema": _CACHE_SCHEMA,
                "requestUrl": request_url,
                "responseUrl": response.final_url,
                "retrievedAt": retrieved_at,
                "contentSha256": content_sha256,
                "responseHeaders": response_headers,
                "payload": payload,
            }
            _assert_safe(cached)
            _write_atomic_json(cache_path, cached)
            return payload, {
                "requestUrl": request_url,
                "responseUrl": response.final_url,
                "retrievedAt": retrieved_at,
                "contentSha256": content_sha256,
                "responseHeaders": response_headers,
                "cacheHit": False,
                "upstreamRecordCount": 1,
                "normalisedRecordCount": 1,
            }
        except (ONSVersionMetadataError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt < retries:
                sleep(min(2**attempt, 8))
    raise ONSVersionMetadataError(
        f"unable to acquire ONS version metadata for {record_id}: {last_error}"
    ) from last_error


def _validate_string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() or len(item) > 2_000
        for item in value
    ):
        raise ONSVersionMetadataError(f"{label} is malformed")
    return list(value)


def _validate_base_source(value: Any) -> None:
    if not isinstance(value, Mapping):
        raise ONSVersionMetadataError("frozen ONS source declaration is malformed")
    _validate_exact_keys(value, _BASE_SOURCE_KEYS, "frozen ONS source declaration")
    if (
        value.get("id") != SOURCE_ID
        or value.get("endpoint") != SOURCE_ENDPOINT
        or value.get("adapter") != SOURCE_ID
        or value.get("acquisitionMethod") != "http-json"
    ):
        raise ONSVersionMetadataError("frozen ONS source declaration failed validation")
    for key in ("responseFormat", "title"):
        if not plain_text(value.get(key), 2_000):
            raise ONSVersionMetadataError("frozen ONS source declaration is malformed")
    _validate_string_list(value.get("crossReferences"), "frozen ONS cross references")
    _validate_string_list(value.get("identityFields"), "frozen ONS identity fields")
    _validate_string_list(value.get("standards"), "frozen ONS standards")
    publisher = value.get("publisher")
    if not isinstance(publisher, Mapping):
        raise ONSVersionMetadataError("frozen ONS publisher is malformed")
    _validate_exact_keys(publisher, {"name", "url"}, "frozen ONS publisher")
    if not plain_text(publisher.get("name"), 2_000) or not _validate_public_url(
        publisher.get("url")
    ):
        raise ONSVersionMetadataError("frozen ONS publisher is malformed")
    scope = value.get("scope")
    if not isinstance(scope, Mapping):
        raise ONSVersionMetadataError("frozen ONS scope is malformed")
    _validate_exact_keys(scope, {"excludes", "includes"}, "frozen ONS scope")
    _validate_string_list(scope.get("excludes"), "frozen ONS exclusions")
    _validate_string_list(scope.get("includes"), "frozen ONS inclusions")
    _assert_safe(value)


def _load_base_acquisition(snapshot_directory: Path) -> tuple[dict[str, Any], str]:
    if snapshot_directory.is_symlink() or not snapshot_directory.is_dir():
        raise ONSVersionMetadataError("frozen snapshot directory is unsafe")
    resolved_snapshot = snapshot_directory.resolve()
    manifest_path = snapshot_directory / "snapshot.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ONSVersionMetadataError("frozen snapshot manifest is unsafe")
    try:
        manifest_bytes = manifest_path.read_bytes()
        if len(manifest_bytes) > MAX_CACHE_BYTES:
            raise ONSVersionMetadataError("frozen snapshot manifest exceeds the size limit")
        manifest = json.loads(manifest_bytes)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ONSVersionMetadataError("unable to read frozen snapshot manifest") from exc
    if not isinstance(manifest, Mapping):
        raise ONSVersionMetadataError("frozen snapshot manifest is malformed")
    manifest_keys = set(manifest)
    if manifest_keys != _MANIFEST_KEYS and manifest_keys != _MANIFEST_KEYS | {"basedOn"}:
        raise ONSVersionMetadataError("frozen snapshot manifest fields are not allowlisted")
    if (
        manifest.get("schema") != "okf-ons.frozen-snapshot.v1"
        or manifest.get("metadataOnly") is not True
        or manifest.get("observationsIncluded") is not False
        or manifest.get("completeForRegisteredAdapters") is not True
        or not plain_text(manifest.get("claimBoundary"), 10_000)
    ):
        raise ONSVersionMetadataError("frozen snapshot manifest failed safety validation")
    snapshot_id = manifest.get("snapshotId")
    if (
        not isinstance(snapshot_id, str)
        or not snapshot_id
        or Path(snapshot_id).name != snapshot_id
        or snapshot_id in {".", ".."}
    ):
        raise ONSVersionMetadataError("frozen snapshot id is unsafe")
    based_on = manifest.get("basedOn")
    if based_on is not None:
        if not isinstance(based_on, Mapping):
            raise ONSVersionMetadataError("frozen snapshot lineage is malformed")
        _validate_exact_keys(
            based_on, {"manifestSha256", "snapshotId"}, "frozen snapshot lineage"
        )
        if not plain_text(based_on.get("snapshotId"), 500):
            raise ONSVersionMetadataError("frozen snapshot lineage is malformed")
        _validated_sha256(based_on.get("manifestSha256"), "frozen snapshot lineage hash")

    rows = manifest.get("sources")
    if not isinstance(rows, list) or not rows:
        raise ONSVersionMetadataError("frozen snapshot source rows are malformed")
    source_ids: set[str] = set()
    filenames: set[str] = set()
    selected_row: Mapping[str, Any] | None = None
    acquisition_bytes = b""
    for item in rows:
        if not isinstance(item, Mapping):
            raise ONSVersionMetadataError("frozen snapshot source row is malformed")
        row_keys = set(item)
        if row_keys != _MANIFEST_SOURCE_KEYS and row_keys != _MANIFEST_SOURCE_KEYS | {
            "explainedExclusionCount"
        }:
            raise ONSVersionMetadataError(
                "frozen snapshot source row fields are not allowlisted"
            )
        if not isinstance(item.get("coverageComplete"), bool):
            raise ONSVersionMetadataError("frozen snapshot source coverage flag is malformed")
        for key in ("normalisationDroppedCount", "recordCount", "unrepresentedCount"):
            if (
                isinstance(item.get(key), bool)
                or not isinstance(item.get(key), int)
                or item[key] < 0
            ):
                raise ONSVersionMetadataError(
                    f"frozen snapshot source count is malformed: {key}"
                )
        reported_total = item.get("reportedTotal")
        if reported_total is not None and (
            isinstance(reported_total, bool)
            or not isinstance(reported_total, int)
            or reported_total < 0
        ):
            raise ONSVersionMetadataError("frozen snapshot reported total is malformed")
        if "explainedExclusionCount" in item and (
            isinstance(item["explainedExclusionCount"], bool)
            or not isinstance(item["explainedExclusionCount"], int)
            or item["explainedExclusionCount"] < 0
        ):
            raise ONSVersionMetadataError(
                "frozen snapshot explained exclusion count is malformed"
            )
        source_id = item.get("sourceId")
        filename = item.get("file")
        if (
            not isinstance(source_id, str)
            or not source_id
            or source_id in source_ids
            or not isinstance(filename, str)
            or filename != f"{source_id}.json"
            or Path(filename).name != filename
            or filename in filenames
        ):
            raise ONSVersionMetadataError("frozen snapshot source identity is unsafe")
        source_ids.add(source_id)
        filenames.add(filename)
        _validated_sha256(item.get("sha256"), f"frozen source file hash for {source_id}")
        _validated_sha256(
            item.get("recordSetSha256"), f"frozen record-set hash for {source_id}"
        )
        _validated_sha256(
            item.get("snapshotSetSha256"), f"frozen snapshot-set hash for {source_id}"
        )
        acquisition_path = snapshot_directory / filename
        if (
            acquisition_path.is_symlink()
            or not acquisition_path.is_file()
            or acquisition_path.resolve().parent != resolved_snapshot
        ):
            raise ONSVersionMetadataError("frozen snapshot source file is unsafe")
        data = acquisition_path.read_bytes()
        if len(data) > MAX_BASE_FILE_BYTES:
            raise ONSVersionMetadataError(
                "frozen snapshot source file exceeds the size limit"
            )
        if sha256_bytes(data) != item["sha256"]:
            raise ONSVersionMetadataError(
                f"frozen source file hash mismatch for {source_id}"
            )
        if source_id == SOURCE_ID:
            selected_row = item
            acquisition_bytes = data
    if selected_row is None:
        raise ONSVersionMetadataError("frozen snapshot has no ONS Data API cohort")
    try:
        acquisition = json.loads(acquisition_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ONSVersionMetadataError("unable to read frozen ONS acquisition") from exc
    if not isinstance(acquisition, Mapping):
        raise ONSVersionMetadataError("frozen ONS acquisition failed validation")
    _validate_exact_keys(acquisition, _ACQUISITION_KEYS, "frozen ONS acquisition")
    records = acquisition.get("records")
    provenance = acquisition.get("provenance")
    if (
        acquisition.get("schemaVersion") != "okf-ons.source-acquisition.v1"
        or not isinstance(records, list)
        or not isinstance(provenance, Mapping)
    ):
        raise ONSVersionMetadataError("frozen ONS acquisition failed validation")
    _validate_exact_keys(provenance, _BASE_PROVENANCE_KEYS, "frozen ONS provenance")
    for key in (
        "normalisationDroppedCount",
        "normalisedRecordsSeen",
        "pageCount",
        "recordCount",
        "unrepresentedCount",
        "upstreamRecordsSeen",
    ):
        if (
            isinstance(provenance.get(key), bool)
            or not isinstance(provenance.get(key), int)
            or provenance[key] < 0
        ):
            raise ONSVersionMetadataError(f"frozen ONS provenance count is malformed: {key}")
    reported_total = provenance.get("reportedTotal")
    if reported_total is not None and (
        isinstance(reported_total, bool)
        or not isinstance(reported_total, int)
        or reported_total < 0
    ):
        raise ONSVersionMetadataError("frozen ONS reported total is malformed")
    source = provenance.get("source")
    _validate_base_source(source)
    assurance = provenance.get("assurance")
    pages = provenance.get("pages")
    if (
        not isinstance(assurance, Mapping)
        or set(assurance) != set(_BASE_ASSURANCE)
        or any(assurance[key] is not expected for key, expected in _BASE_ASSURANCE.items())
        or not isinstance(pages, list)
        or not pages
        or provenance.get("pageCount") != len(pages)
        or provenance.get("recordCount") != len(records)
        or provenance.get("complete") is not True
        or provenance.get("coverageComplete") is not True
    ):
        raise ONSVersionMetadataError("frozen ONS acquisition failed validation")
    record_set_sha256 = sha256_json(records)
    _validated_sha256(provenance.get("recordSetSha256"), "frozen ONS record-set hash")
    if provenance["recordSetSha256"] != record_set_sha256:
        raise ONSVersionMetadataError("frozen ONS record-set hash mismatch")

    receipts: list[dict[str, str]] = []
    for index, page in enumerate(pages):
        if not isinstance(page, Mapping):
            raise ONSVersionMetadataError("frozen ONS page receipt is malformed")
        _validate_exact_keys(page, _PAGE_KEYS, f"frozen ONS page receipt {index}")
        request_url = page.get("requestUrl")
        response_url = page.get("responseUrl")
        if (
            request_url != f"{SOURCE_ENDPOINT}?limit=1000&offset=0"
            or response_url != request_url
            or not isinstance(page.get("cacheHit"), bool)
            or isinstance(page.get("upstreamRecordCount"), bool)
            or not isinstance(page.get("upstreamRecordCount"), int)
            or page["upstreamRecordCount"] < 0
            or isinstance(page.get("normalisedRecordCount"), bool)
            or not isinstance(page.get("normalisedRecordCount"), int)
            or page["normalisedRecordCount"] < 0
        ):
            raise ONSVersionMetadataError("frozen ONS page receipt failed validation")
        _validate_utc_timestamp(page.get("retrievedAt"), "frozen ONS retrieval time")
        _validated_sha256(page.get("contentSha256"), "frozen ONS page hash")
        _validated_response_headers(page.get("responseHeaders"))
        receipts.append(
            {"requestUrl": request_url, "contentSha256": page["contentSha256"]}
        )
    snapshot_set_sha256 = sha256_json(receipts)
    _validated_sha256(
        provenance.get("snapshotSetSha256"), "frozen ONS snapshot-set hash"
    )
    if provenance["snapshotSetSha256"] != snapshot_set_sha256:
        raise ONSVersionMetadataError("frozen ONS snapshot-set hash mismatch")
    bindings = {
        "coverageComplete": provenance["coverageComplete"],
        "normalisationDroppedCount": provenance["normalisationDroppedCount"],
        "recordCount": provenance["recordCount"],
        "recordSetSha256": record_set_sha256,
        "reportedTotal": provenance["reportedTotal"],
        "snapshotSetSha256": snapshot_set_sha256,
        "unrepresentedCount": provenance["unrepresentedCount"],
    }
    if any(selected_row.get(key) != value for key, value in bindings.items()):
        raise ONSVersionMetadataError("snapshot manifest does not bind the ONS acquisition")
    return dict(acquisition), str(snapshot_id)


def build_enrichment_envelope(
    snapshot_directory: Path,
    *,
    cache_directory: Path,
    limit: int = EXPECTED_COHORT_COUNT,
    expected_cohort_count: int = EXPECTED_COHORT_COUNT,
    mode: str = "prefer-cache",
    request_interval_seconds: float = DEFAULT_REQUEST_INTERVAL_SECONDS,
    timeout_seconds: float = 30.0,
    retries: int = 2,
    transport: JsonTransport | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ONSVersionMetadataError("record limit must be positive")
    if (
        isinstance(expected_cohort_count, bool)
        or not isinstance(expected_cohort_count, int)
        or expected_cohort_count < 1
    ):
        raise ONSVersionMetadataError("expected cohort count must be positive")
    if mode not in {"prefer-cache", "refresh", "frozen"}:
        raise ONSVersionMetadataError("unsupported cache mode")
    if (
        isinstance(request_interval_seconds, bool)
        or not isinstance(request_interval_seconds, (int, float))
        or not math.isfinite(request_interval_seconds)
        or request_interval_seconds < 0
        or request_interval_seconds > 60
    ):
        raise ONSVersionMetadataError(
            "request interval must be between 0 and 60 seconds"
        )
    if (
        mode != "frozen"
        and transport is None
        and request_interval_seconds < MIN_PRODUCTION_INTERVAL_SECONDS
    ):
        raise ONSVersionMetadataError(
            "live ONS acquisition requires a request interval of at least 0.2 seconds"
        )
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
        or timeout_seconds > 300
    ):
        raise ONSVersionMetadataError(
            "timeout must be greater than 0 and at most 300 seconds"
        )
    if isinstance(retries, bool) or not isinstance(retries, int) or retries < 0 or retries > 5:
        raise ONSVersionMetadataError("retries must be between 0 and 5")
    resolved_cache = cache_directory.resolve()
    if resolved_cache == ROOT.resolve() or ROOT.resolve() in resolved_cache.parents:
        raise ONSVersionMetadataError("raw ONS cache must be outside the repository")

    acquisition, snapshot_id = _load_base_acquisition(snapshot_directory)
    base_records = acquisition["records"]
    if len(base_records) != expected_cohort_count:
        raise ONSVersionMetadataError(
            f"frozen ONS cohort must contain exactly {expected_cohort_count} records"
        )
    records_by_id: dict[str, dict[str, Any]] = {}
    request_urls: dict[str, str] = {}
    base_record_ids: list[str] = []
    cohort_bindings: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for raw in base_records:
        if not isinstance(raw, Mapping):
            raise ONSVersionMetadataError("frozen ONS record is malformed")
        record_id = plain_text(raw.get("sourceRecordId"), 300)
        links = raw.get("links")
        latest = links.get("latest_version") if isinstance(links, Mapping) else None
        if (
            not record_id
            or not _RECORD_ID_RE.fullmatch(record_id)
            or raw.get("sourceId") != SOURCE_ID
            or record_id in records_by_id
            or not isinstance(latest, Mapping)
            or set(latest) != {"href", "id"}
        ):
            raise ONSVersionMetadataError("frozen ONS cohort identity is invalid")
        request_url = latest.get("href")
        url_record_id, _, url_version = _version_identity(request_url)
        if (
            url_record_id != record_id
            or latest.get("id") != str(url_version)
            or request_url in seen_urls
        ):
            raise ONSVersionMetadataError("frozen ONS latest-version binding is invalid")
        seen_urls.add(request_url)
        records_by_id[record_id] = dict(raw)
        request_urls[record_id] = request_url
        base_record_ids.append(record_id)
        cohort_bindings.append(
            {"sourceRecordId": record_id, "latestVersionHref": request_url}
        )
    ranked_ids = sorted(
        base_record_ids,
        key=lambda item: (
            hashlib.sha256(item.encode("utf-8")).hexdigest(),
            item.casefold(),
            item,
        ),
    )
    selected_ids = ranked_ids[: min(limit, len(ranked_ids))]
    selected_bindings = [
        {
            "sourceRecordId": record_id,
            "latestVersionHref": request_urls[record_id],
        }
        for record_id in selected_ids
    ]

    receipts: list[dict[str, Any]] = []
    fetcher = transport or UrllibJsonTransport()
    for index, record_id in enumerate(selected_ids):
        if index and request_interval_seconds:
            sleep(request_interval_seconds)
        payload, receipt = _fetch_version_metadata(
            record_id,
            request_urls[record_id],
            cache_directory=resolved_cache,
            mode=mode,
            transport=fetcher,
            timeout_seconds=float(timeout_seconds),
            retries=retries,
            now=now,
            sleep=sleep,
        )
        records_by_id[record_id]["versionDimensions"] = payload["dimensions"]
        receipts.append(receipt)

    records = [records_by_id[record_id] for record_id in base_record_ids]
    provenance = json.loads(json.dumps(acquisition["provenance"]))
    base_record_set_sha256 = str(provenance["recordSetSha256"])
    base_snapshot_set_sha256 = str(provenance["snapshotSetSha256"])
    pages = list(provenance.get("pages", [])) + receipts
    provenance.update(
        {
            "retrievalMode": f"version-metadata-enrichment:{mode}",
            "stopReason": (
                "recordLimit" if len(selected_ids) < len(records) else "sourceExhausted"
            ),
            "recordCount": len(records),
            "recordSetSha256": sha256_json(records),
            "pageCount": len(pages),
            "pages": pages,
            "snapshotSetSha256": sha256_json(
                [
                    {
                        "requestUrl": page["requestUrl"],
                        "contentSha256": page["contentSha256"],
                    }
                    for page in pages
                ]
            ),
            "replacement": {
                "schema": _REPLACEMENT_SCHEMA,
                "baseSnapshotId": snapshot_id,
                "baseRecordSetSha256": base_record_set_sha256,
                "baseSnapshotSetSha256": base_snapshot_set_sha256,
                "allowedRecordFields": ["versionDimensions"],
            },
            "versionMetadataRun": {
                "schema": _ENRICHMENT_SCHEMA,
                "cohortCount": len(records),
                "requestedLimit": limit,
                "selectedCount": len(selected_ids),
                "unselectedCount": len(records) - len(selected_ids),
                "coverageComplete": len(selected_ids) == len(records),
                "selectionOrder": "sha256(sourceRecordId)-ascending",
                "cohortRecordSetSha256": sha256_json(cohort_bindings),
                "selectedRecordSetSha256": sha256_json(selected_bindings),
            },
            "assurance": {
                **dict(provenance.get("assurance", {})),
                "metadataOnly": True,
                "observationsFetched": False,
                "dimensionMetadataFetched": True,
                "dimensionOptionsFetched": False,
                "downloadsFetched": False,
                "credentialsRequired": False,
                "cacheLocationPublished": False,
                "rawResponsesPublished": False,
            },
        }
    )
    envelope = {
        "schemaVersion": "okf-ons.source-acquisition.v1",
        "records": records,
        "provenance": provenance,
    }
    _assert_safe(envelope)
    return envelope


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=EXPECTED_COHORT_COUNT)
    parser.add_argument(
        "--mode", choices=("prefer-cache", "refresh", "frozen"), default="prefer-cache"
    )
    parser.add_argument(
        "--request-interval", type=float, default=DEFAULT_REQUEST_INTERVAL_SECONDS
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--retries", type=int, default=2)
    arguments = parser.parse_args(argv)
    try:
        envelope = build_enrichment_envelope(
            arguments.snapshot_dir,
            cache_directory=arguments.cache_dir,
            limit=arguments.limit,
            mode=arguments.mode,
            request_interval_seconds=arguments.request_interval,
            timeout_seconds=arguments.timeout,
            retries=arguments.retries,
        )
        _write_atomic_json(arguments.output, envelope)
    except (ONSVersionMetadataError, OSError) as exc:
        parser.exit(1, f"ONS version metadata enrichment error: {exc}\n")
    run = envelope["provenance"]["versionMetadataRun"]
    print(
        f"Acquired {run['selectedCount']} of {run['cohortCount']} ranked ONS "
        f"latest-version records into {arguments.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
