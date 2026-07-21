#!/usr/bin/env python3
"""Acquire bounded metadata-only Nomis compact overviews.

The checked-in frozen Nomis acquisition supplies the cohort and remains the
source of dataset identity and SDMX structure. Raw overview responses are
stored only below ``--cache-dir``. The emitted standard acquisition envelope
contains the full frozen cohort plus bounded contact, geographic coverage and
date metadata for a deterministic SHA-256-ranked selection of source records.
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
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, urlencode, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from okf_ons.model import plain_text  # noqa: E402

SOURCE_ID = "nomis-dataset-definitions"
SOURCE_ENDPOINT = "https://www.nomisweb.co.uk/api/v01/dataset/def.sdmx.json"
OVERVIEW_ROOT = "https://www.nomisweb.co.uk/api/v01/dataset"
SELECT_TERMS = ("DatasetInfo", "Coverage", "DateMetadata", "Contact")
DEFAULT_SNAPSHOT = ROOT / "source" / "metadata-enrichment-2026-07-21-r3"
MAX_RESPONSE_BYTES = 512_000
MAX_CACHE_BYTES = 1_000_000
MAX_BASE_FILE_BYTES = 128_000_000
MIN_PRODUCTION_INTERVAL_SECONDS = 0.2
_CACHE_SCHEMA = "okf-ons.nomis-overview-cache.v1"
_REPLACEMENT_SCHEMA = "okf-ons.bounded-source-replacement.v1"
_ENRICHMENT_SCHEMA = "okf-ons.nomis-overview-enrichment.v1"
_DATE_FIELDS = {
    "firstreleased": "firstReleased",
    "lastrevised": "lastRevised",
    "lastupdated": "lastUpdated",
    "nextupdate": "nextUpdate",
}
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
_OVERVIEW_KEYS = {
    "analysisname",
    "analysisnumber",
    "contact",
    "coverage",
    "datasetnumber",
    "description",
    "firstreleased",
    "id",
    "lastrevised",
    "lastupdated",
    "mnemonic",
    "name",
    "nextupdate",
    "provider",
    "restricted",
    "status",
    "subdescription",
}
_CONTACT_KEYS = {"email", "name", "telephone", "uri"}
_PROVIDER_KEYS = {"digest", "name", "url"}
_OVERVIEW_INTEGER_KEYS = {"analysisnumber", "datasetnumber"}
_HEX_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_NOMIS_ID_RE = re.compile(r"^NM_[0-9]+_[0-9]+$")
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
_FORBIDDEN_CACHE_KEYS = {
    "accesstoken",
    "apikey",
    "authorization",
    "binary",
    "blob",
    "clientsecret",
    "codelist",
    "codelists",
    "codes",
    "coordinates",
    "credential",
    "credentials",
    "data",
    "features",
    "geometry",
    "observation",
    "observations",
    "obs",
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


class NomisOverviewError(ValueError):
    """Raised when overview enrichment cannot be safely acquired or projected."""


@dataclass(frozen=True)
class JsonResponse:
    payload: Any
    final_url: str
    status: int = 200
    headers: Mapping[str, str] | None = None


class JsonTransport(Protocol):
    def get(self, url: str, *, timeout: float) -> JsonResponse: ...


class UrllibJsonTransport:
    """Small bounded JSON transport for credential-free Nomis metadata."""

    def get(self, url: str, *, timeout: float) -> JsonResponse:
        request = Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "okf-ons/nomis-overview"},
        )
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                body = response.read(MAX_RESPONSE_BYTES + 1)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise NomisOverviewError("Nomis overview exceeded the response byte limit")
                try:
                    payload = json.loads(body.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise NomisOverviewError("Nomis overview was not valid UTF-8 JSON") from exc
                headers = {
                    key.casefold(): response.headers[key]
                    for key in ("Content-Type", "ETag", "Last-Modified")
                    if response.headers.get(key)
                }
                return JsonResponse(
                    payload=payload,
                    final_url=response.geturl(),
                    status=int(response.status),
                    headers=headers,
                )
        except HTTPError as exc:
            raise NomisOverviewError(f"Nomis returned HTTP {exc.code}") from exc
        except URLError as exc:
            raise NomisOverviewError("Nomis overview request failed") from exc


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
        raise NomisOverviewError(f"{label} has " + "; ".join(detail))


def _validated_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _HEX_SHA256_RE.fullmatch(value):
        raise NomisOverviewError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _validate_utc_timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _UTC_TIMESTAMP_RE.fullmatch(value):
        raise NomisOverviewError(f"{label} must be a UTC ISO 8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise NomisOverviewError(f"{label} must be a UTC ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise NomisOverviewError(f"{label} must be a UTC ISO 8601 timestamp")
    return value


def _normalised_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def _assert_cache_safe(value: Any, *, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if _normalised_key(key) in _FORBIDDEN_CACHE_KEYS:
                raise NomisOverviewError(
                    f"Nomis overview cache contains unsafe field {key!r} at {path}"
                )
            _assert_cache_safe(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_cache_safe(child, path=f"{path}[{index}]")
    elif isinstance(value, bytes):
        raise NomisOverviewError(f"Nomis overview cache contains binary data at {path}")
    elif isinstance(value, float) and not (float("-inf") < value < float("inf")):
        raise NomisOverviewError(
            f"Nomis overview cache contains a non-finite number at {path}"
        )
    elif isinstance(value, str):
        if _LOCAL_PATH_RE.search(value) or any(
            pattern.search(value) for pattern in _SECRET_VALUE_PATTERNS
        ):
            raise NomisOverviewError(
                f"Nomis overview cache contains an unsafe value at {path}"
            )


def _validated_response_headers(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise NomisOverviewError("Nomis overview response headers are malformed")
    headers: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        if not isinstance(raw_key, str):
            raise NomisOverviewError("Nomis overview response headers are malformed")
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
            raise NomisOverviewError("Nomis overview response headers are unsafe")
        headers[key] = raw_value
    content_type = headers.get("content-type")
    if content_type is not None and not content_type.casefold().startswith(
        "application/json"
    ):
        raise NomisOverviewError("Nomis overview response content type is not JSON")
    return headers


def _validate_overview_payload(payload: Any, record_id: str) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise NomisOverviewError(f"Nomis overview is malformed for {record_id}")
    _validate_exact_keys(payload, {"overview"}, "Nomis overview payload")
    overview = payload.get("overview")
    if not isinstance(overview, Mapping):
        raise NomisOverviewError(f"Nomis overview is malformed for {record_id}")
    unknown = sorted(set(overview) - _OVERVIEW_KEYS)
    if unknown:
        raise NomisOverviewError(
            "Nomis overview has unreviewed field(s): " + ", ".join(unknown)
        )
    if overview.get("id") != record_id or _NOMIS_ID_RE.fullmatch(record_id) is None:
        raise NomisOverviewError(f"Nomis overview identity mismatch for {record_id}")
    for key, value in overview.items():
        if key in {"contact", "provider"}:
            continue
        if key in _OVERVIEW_INTEGER_KEYS:
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int)
            ):
                raise NomisOverviewError(
                    f"Nomis overview field {key!r} has an invalid type"
                )
        elif value is not None and (
            not isinstance(value, str) or len(value) > 20_000
        ):
            raise NomisOverviewError(f"Nomis overview field {key!r} has an invalid type")
        if key in _DATE_FIELDS and value is not None:
            if not _NOMIS_DATE_RE.fullmatch(value):
                raise NomisOverviewError(
                    f"Nomis overview date field {key!r} has an invalid shape"
                )
            try:
                datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            except ValueError as exc:
                raise NomisOverviewError(
                    f"Nomis overview date field {key!r} is not a valid timestamp"
                ) from exc

    contact = overview.get("contact")
    if contact is not None:
        if not isinstance(contact, Mapping) or set(contact) - _CONTACT_KEYS:
            raise NomisOverviewError("Nomis overview contact is malformed")
        for key, value in contact.items():
            if value is not None and (
                not isinstance(value, str) or len(value) > 2_000
            ):
                raise NomisOverviewError("Nomis overview contact is malformed")
            if key == "uri" and value and _validate_public_url(value) != value:
                raise NomisOverviewError("Nomis overview contact URI is unsafe")

    provider = overview.get("provider")
    if provider is not None:
        if not isinstance(provider, Mapping) or set(provider) - _PROVIDER_KEYS:
            raise NomisOverviewError("Nomis overview provider is malformed")
        for key, value in provider.items():
            if value is not None and (
                not isinstance(value, str) or len(value) > 2_000
            ):
                raise NomisOverviewError("Nomis overview provider is malformed")
            if key == "url" and value and _validate_public_url(value) != value:
                raise NomisOverviewError("Nomis overview provider URL is unsafe")
    safe_payload = {"overview": dict(overview)}
    _assert_cache_safe(safe_payload)
    return safe_payload


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _overview_url(record_id: str) -> str:
    query = urlencode({"select": ",".join(SELECT_TERMS)})
    return f"{OVERVIEW_ROOT}/{quote(record_id, safe='')}.overview.json?{query}"


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
    ):
        return ""
    return url


def _validate_request_url(url: str, *, expected_record_id: str | None = None) -> str:
    parsed = urlsplit(url)
    path_match = re.fullmatch(
        r"/api/v01/dataset/(NM_[0-9]+_[0-9]+)\.overview\.json", parsed.path
    )
    if (
        parsed.scheme != "https"
        or parsed.netloc != "www.nomisweb.co.uk"
        or parsed.username
        or parsed.password
        or parsed.fragment
        or path_match is None
        or parse_qsl(parsed.query, keep_blank_values=True)
        != [("select", ",".join(SELECT_TERMS))]
    ):
        raise NomisOverviewError("overview request escaped the metadata-only Nomis template")
    record_id = path_match.group(1)
    if expected_record_id is not None and record_id != expected_record_id:
        raise NomisOverviewError(f"Nomis overview identity mismatch for {expected_record_id}")
    return record_id


def _project_overview(payload: Any, record_id: str) -> dict[str, Any]:
    safe_payload = _validate_overview_payload(payload, record_id)
    overview = safe_payload["overview"]

    projected: dict[str, Any] = {}
    coverage = plain_text(overview.get("coverage"), 500)
    if coverage:
        projected["geographicCoverage"] = coverage

    raw_contact = overview.get("contact")
    if isinstance(raw_contact, Mapping):
        contact = {
            key: value
            for key, upstream_key in (
                ("name", "name"),
                ("email", "email"),
                ("telephone", "telephone"),
            )
            if (value := plain_text(raw_contact.get(upstream_key), 300))
        }
        contact_url = _validate_public_url(raw_contact.get("uri"))
        if contact_url:
            contact["url"] = contact_url
        if contact:
            projected["contacts"] = [contact]

    for upstream_key, public_key in _DATE_FIELDS.items():
        value = plain_text(overview.get(upstream_key), 100)
        if value:
            projected[public_key] = value
    return projected


def _cache_path(cache_directory: Path, request_url: str) -> Path:
    digest = hashlib.sha256(request_url.encode("utf-8")).hexdigest()
    return cache_directory / "nomis-overview" / f"{digest}.json"


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
        raise NomisOverviewError("Nomis overview cache entry is not a regular file")
    try:
        payload_bytes = path.read_bytes()
        if len(payload_bytes) > MAX_CACHE_BYTES:
            raise NomisOverviewError("Nomis overview cache entry exceeds the size limit")
        envelope = json.loads(payload_bytes)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NomisOverviewError("Nomis overview cache entry is unreadable") from exc
    if not isinstance(envelope, dict):
        raise NomisOverviewError("Nomis overview cache entry failed validation")
    _validate_exact_keys(envelope, _CACHE_KEYS, "Nomis overview cache entry")
    if envelope.get("schema") != _CACHE_SCHEMA:
        raise NomisOverviewError("Nomis overview cache entry failed validation")
    if envelope.get("requestUrl") != request_url or envelope.get("responseUrl") != request_url:
        raise NomisOverviewError("Nomis overview cache entry failed validation")
    _validate_request_url(request_url, expected_record_id=record_id)
    _validate_utc_timestamp(envelope.get("retrievedAt"), "Nomis overview retrieval time")
    envelope["responseHeaders"] = _validated_response_headers(
        envelope.get("responseHeaders")
    )
    envelope["payload"] = _validate_overview_payload(envelope.get("payload"), record_id)
    _validated_sha256(envelope.get("contentSha256"), "Nomis overview content hash")
    if envelope["contentSha256"] != sha256_json(envelope["payload"]):
        raise NomisOverviewError("Nomis overview cache entry failed validation")
    _assert_cache_safe(envelope)
    return envelope


def _fetch_overview(
    record_id: str,
    *,
    cache_directory: Path,
    mode: str,
    transport: JsonTransport,
    timeout_seconds: float,
    retries: int,
    now: Callable[[], datetime],
    sleep: Callable[[float], None],
) -> tuple[dict[str, Any], dict[str, Any]]:
    request_url = _overview_url(record_id)
    _validate_request_url(request_url, expected_record_id=record_id)
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
        raise NomisOverviewError(f"frozen cache is missing overview for {record_id}")

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = transport.get(request_url, timeout=timeout_seconds)
            if (
                isinstance(response.status, bool)
                or not isinstance(response.status, int)
                or response.status < 200
                or response.status >= 300
            ):
                raise NomisOverviewError(f"Nomis returned HTTP {response.status}")
            if response.final_url != request_url:
                raise NomisOverviewError("Nomis overview response URL changed unexpectedly")
            _validate_request_url(response.final_url, expected_record_id=record_id)
            payload = _validate_overview_payload(response.payload, record_id)
            response_headers = _validated_response_headers(response.headers or {})
            retrieved_at = _utc_iso(now())
            _validate_utc_timestamp(retrieved_at, "Nomis overview retrieval time")
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
            _assert_cache_safe(cached)
            _write_atomic_json(cache_path, cached)
            return payload, {
                "requestUrl": request_url,
                "responseUrl": response.final_url,
                "retrievedAt": cached["retrievedAt"],
                "contentSha256": content_sha256,
                "responseHeaders": cached["responseHeaders"],
                "cacheHit": False,
                "upstreamRecordCount": 1,
                "normalisedRecordCount": 1,
            }
        except (NomisOverviewError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt < retries:
                sleep(min(2**attempt, 8))
    raise NomisOverviewError(
        f"unable to acquire Nomis overview for {record_id}: {last_error}"
    ) from last_error


def _load_base_acquisition(snapshot_directory: Path) -> tuple[dict[str, Any], str]:
    if snapshot_directory.is_symlink() or not snapshot_directory.is_dir():
        raise NomisOverviewError("frozen snapshot directory is unsafe")
    resolved_snapshot = snapshot_directory.resolve()
    manifest_path = snapshot_directory / "snapshot.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise NomisOverviewError("frozen snapshot manifest is unsafe")
    try:
        manifest_bytes = manifest_path.read_bytes()
        if len(manifest_bytes) > MAX_CACHE_BYTES:
            raise NomisOverviewError("frozen snapshot manifest exceeds the size limit")
        manifest = json.loads(manifest_bytes)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NomisOverviewError("unable to read frozen snapshot manifest") from exc
    if not isinstance(manifest, Mapping):
        raise NomisOverviewError("frozen snapshot manifest is malformed")
    manifest_keys = set(manifest)
    if manifest_keys != _MANIFEST_KEYS and manifest_keys != _MANIFEST_KEYS | {"basedOn"}:
        raise NomisOverviewError("frozen snapshot manifest fields are not allowlisted")
    if (
        manifest.get("schema") != "okf-ons.frozen-snapshot.v1"
        or manifest.get("metadataOnly") is not True
        or manifest.get("observationsIncluded") is not False
        or manifest.get("completeForRegisteredAdapters") is not True
        or not isinstance(manifest.get("claimBoundary"), str)
        or not manifest["claimBoundary"].strip()
    ):
        raise NomisOverviewError("frozen snapshot manifest failed safety validation")
    snapshot_id = manifest.get("snapshotId")
    if (
        not isinstance(snapshot_id, str)
        or not snapshot_id
        or Path(snapshot_id).name != snapshot_id
        or snapshot_id in {".", ".."}
    ):
        raise NomisOverviewError("frozen snapshot id is unsafe")
    based_on = manifest.get("basedOn")
    if based_on is not None:
        if not isinstance(based_on, Mapping):
            raise NomisOverviewError("frozen snapshot lineage is malformed")
        _validate_exact_keys(
            based_on, {"manifestSha256", "snapshotId"}, "frozen snapshot lineage"
        )
        if not isinstance(based_on["snapshotId"], str) or not based_on["snapshotId"]:
            raise NomisOverviewError("frozen snapshot lineage is malformed")
        _validated_sha256(based_on["manifestSha256"], "frozen snapshot lineage hash")

    rows = manifest.get("sources")
    if not isinstance(rows, list) or not rows:
        raise NomisOverviewError("frozen snapshot source rows are malformed")
    source_ids: set[str] = set()
    filenames: set[str] = set()
    row: Mapping[str, Any] | None = None
    acquisition_bytes = b""
    for item in rows:
        if not isinstance(item, Mapping):
            raise NomisOverviewError("frozen snapshot source row is malformed")
        row_keys = set(item)
        if row_keys != _MANIFEST_SOURCE_KEYS and row_keys != _MANIFEST_SOURCE_KEYS | {
            "explainedExclusionCount"
        }:
            raise NomisOverviewError("frozen snapshot source row fields are not allowlisted")
        if not isinstance(item.get("coverageComplete"), bool):
            raise NomisOverviewError("frozen snapshot source coverage flag is malformed")
        for key in (
            "normalisationDroppedCount",
            "recordCount",
            "unrepresentedCount",
        ):
            if (
                isinstance(item.get(key), bool)
                or not isinstance(item.get(key), int)
                or item[key] < 0
            ):
                raise NomisOverviewError(f"frozen snapshot source count is malformed: {key}")
        reported_total = item.get("reportedTotal")
        if reported_total is not None and (
            isinstance(reported_total, bool)
            or not isinstance(reported_total, int)
            or reported_total < 0
        ):
            raise NomisOverviewError("frozen snapshot reported total is malformed")
        if "explainedExclusionCount" in item and (
            isinstance(item["explainedExclusionCount"], bool)
            or not isinstance(item["explainedExclusionCount"], int)
            or item["explainedExclusionCount"] < 0
        ):
            raise NomisOverviewError(
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
            raise NomisOverviewError("frozen snapshot source identity is unsafe")
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
            raise NomisOverviewError("frozen snapshot source file is unsafe")
        data = acquisition_path.read_bytes()
        if len(data) > MAX_BASE_FILE_BYTES:
            raise NomisOverviewError("frozen snapshot source file exceeds the size limit")
        if sha256_bytes(data) != item["sha256"]:
            raise NomisOverviewError(f"frozen source file hash mismatch for {source_id}")
        if source_id == SOURCE_ID:
            row = item
            acquisition_bytes = data
    if row is None:
        raise NomisOverviewError("frozen snapshot has no Nomis cohort")
    try:
        acquisition = json.loads(acquisition_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NomisOverviewError("unable to read frozen Nomis acquisition") from exc
    if not isinstance(acquisition, Mapping):
        raise NomisOverviewError("frozen Nomis acquisition failed validation")
    _validate_exact_keys(acquisition, _ACQUISITION_KEYS, "frozen Nomis acquisition")
    records = acquisition.get("records")
    provenance = acquisition.get("provenance")
    if (
        acquisition.get("schemaVersion") != "okf-ons.source-acquisition.v1"
        or not isinstance(records, list)
        or not isinstance(provenance, Mapping)
    ):
        raise NomisOverviewError("frozen Nomis acquisition failed validation")
    for key in (
        "normalisationDroppedCount",
        "normalisedRecordsSeen",
        "unrepresentedCount",
        "upstreamRecordsSeen",
    ):
        if (
            isinstance(provenance.get(key), bool)
            or not isinstance(provenance.get(key), int)
            or provenance[key] < 0
        ):
            raise NomisOverviewError(f"frozen Nomis provenance count is malformed: {key}")
    reported_total = provenance.get("reportedTotal")
    if reported_total is not None and (
        isinstance(reported_total, bool)
        or not isinstance(reported_total, int)
        or reported_total < 0
    ):
        raise NomisOverviewError("frozen Nomis reported total is malformed")
    _validate_exact_keys(provenance, _BASE_PROVENANCE_KEYS, "frozen Nomis provenance")
    source = provenance.get("source")
    assurance = provenance.get("assurance")
    pages = provenance.get("pages")
    if (
        not isinstance(source, Mapping)
        or source.get("id") != SOURCE_ID
        or source.get("endpoint") != SOURCE_ENDPOINT
        or source.get("adapter") not in {None, "nomis-sdmx"}
        or not isinstance(assurance, Mapping)
        or set(assurance) != set(_BASE_ASSURANCE)
        or any(
            assurance[key] is not expected
            for key, expected in _BASE_ASSURANCE.items()
        )
        or not isinstance(pages, list)
        or not pages
        or isinstance(provenance.get("pageCount"), bool)
        or not isinstance(provenance.get("pageCount"), int)
        or provenance.get("pageCount") != len(pages)
        or isinstance(provenance.get("recordCount"), bool)
        or not isinstance(provenance.get("recordCount"), int)
        or provenance.get("recordCount") != len(records)
        or provenance.get("complete") is not True
        or provenance.get("coverageComplete") is not True
    ):
        raise NomisOverviewError("frozen Nomis acquisition failed validation")
    record_set_sha256 = sha256_json(records)
    _validated_sha256(provenance.get("recordSetSha256"), "frozen Nomis record-set hash")
    if provenance["recordSetSha256"] != record_set_sha256:
        raise NomisOverviewError("frozen Nomis record-set hash mismatch")

    receipts: list[dict[str, str]] = []
    for index, page in enumerate(pages):
        if not isinstance(page, Mapping):
            raise NomisOverviewError("frozen Nomis page receipt is malformed")
        _validate_exact_keys(page, _PAGE_KEYS, f"frozen Nomis page receipt {index}")
        request_url = page.get("requestUrl")
        response_url = page.get("responseUrl")
        if (
            request_url != SOURCE_ENDPOINT
            or response_url != request_url
            or not isinstance(page.get("cacheHit"), bool)
            or isinstance(page.get("upstreamRecordCount"), bool)
            or not isinstance(page.get("upstreamRecordCount"), int)
            or page["upstreamRecordCount"] < 0
            or isinstance(page.get("normalisedRecordCount"), bool)
            or not isinstance(page.get("normalisedRecordCount"), int)
            or page["normalisedRecordCount"] < 0
        ):
            raise NomisOverviewError("frozen Nomis page receipt failed validation")
        _validate_utc_timestamp(page.get("retrievedAt"), "frozen Nomis retrieval time")
        _validated_sha256(page.get("contentSha256"), "frozen Nomis page hash")
        _validated_response_headers(page.get("responseHeaders"))
        receipts.append(
            {
                "requestUrl": request_url,
                "contentSha256": page["contentSha256"],
            }
        )
    snapshot_set_sha256 = sha256_json(receipts)
    _validated_sha256(
        provenance.get("snapshotSetSha256"), "frozen Nomis snapshot-set hash"
    )
    if provenance["snapshotSetSha256"] != snapshot_set_sha256:
        raise NomisOverviewError("frozen Nomis snapshot-set hash mismatch")
    bindings = {
        "coverageComplete": provenance["coverageComplete"],
        "normalisationDroppedCount": provenance["normalisationDroppedCount"],
        "recordCount": provenance["recordCount"],
        "recordSetSha256": record_set_sha256,
        "reportedTotal": provenance["reportedTotal"],
        "snapshotSetSha256": snapshot_set_sha256,
        "unrepresentedCount": provenance["unrepresentedCount"],
    }
    if any(row.get(key) != value for key, value in bindings.items()):
        raise NomisOverviewError("snapshot manifest does not bind the Nomis acquisition")
    return dict(acquisition), snapshot_id


def build_enrichment_envelope(
    snapshot_directory: Path,
    *,
    cache_directory: Path,
    limit: int = 100,
    mode: str = "prefer-cache",
    request_interval_seconds: float = 0.2,
    timeout_seconds: float = 30.0,
    retries: int = 2,
    transport: JsonTransport | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise NomisOverviewError("record limit must be positive")
    if mode not in {"prefer-cache", "refresh", "frozen"}:
        raise NomisOverviewError("unsupported cache mode")
    if (
        isinstance(request_interval_seconds, bool)
        or not isinstance(request_interval_seconds, (int, float))
        or not math.isfinite(request_interval_seconds)
        or request_interval_seconds < 0
        or request_interval_seconds > 60
    ):
        raise NomisOverviewError("request interval must be between 0 and 60 seconds")
    if (
        mode != "frozen"
        and transport is None
        and request_interval_seconds < MIN_PRODUCTION_INTERVAL_SECONDS
    ):
        raise NomisOverviewError(
            "live Nomis acquisition requires a request interval of at least 0.2 seconds"
        )
    if timeout_seconds <= 0 or timeout_seconds > 300:
        raise NomisOverviewError("timeout must be greater than 0 and at most 300 seconds")
    if retries < 0 or retries > 5:
        raise NomisOverviewError("retries must be between 0 and 5")
    resolved_cache = cache_directory.resolve()
    if resolved_cache == ROOT.resolve() or ROOT.resolve() in resolved_cache.parents:
        raise NomisOverviewError("raw overview cache must be outside the repository")

    acquisition, snapshot_id = _load_base_acquisition(snapshot_directory)
    base_records = acquisition["records"]
    records_by_id: dict[str, dict[str, Any]] = {}
    base_record_ids: list[str] = []
    for raw in base_records:
        if not isinstance(raw, Mapping):
            raise NomisOverviewError("frozen Nomis record is malformed")
        record_id = plain_text(raw.get("sourceRecordId"), 300)
        if (
            not record_id
            or _NOMIS_ID_RE.fullmatch(record_id) is None
            or raw.get("sourceId") != SOURCE_ID
            or record_id in records_by_id
        ):
            raise NomisOverviewError("frozen Nomis cohort identity is invalid")
        records_by_id[record_id] = dict(raw)
        base_record_ids.append(record_id)
    ranked_ids = sorted(
        base_record_ids,
        key=lambda item: (
            hashlib.sha256(item.encode("utf-8")).hexdigest(),
            item.casefold(),
            item,
        ),
    )
    selected_ids = ranked_ids[: min(limit, len(ranked_ids))]

    receipts: list[dict[str, Any]] = []
    fetcher = transport or UrllibJsonTransport()
    for index, record_id in enumerate(selected_ids):
        if index and request_interval_seconds:
            sleep(request_interval_seconds)
        payload, receipt = _fetch_overview(
            record_id,
            cache_directory=resolved_cache,
            mode=mode,
            transport=fetcher,
            timeout_seconds=timeout_seconds,
            retries=retries,
            now=now,
            sleep=sleep,
        )
        enrichment = _project_overview(payload, record_id)
        records_by_id[record_id].update(enrichment)
        receipts.append(receipt)

    records = [records_by_id[record_id] for record_id in base_record_ids]
    provenance = json.loads(json.dumps(acquisition["provenance"]))
    base_record_set_sha256 = str(provenance["recordSetSha256"])
    base_snapshot_set_sha256 = str(provenance["snapshotSetSha256"])
    pages = list(provenance.get("pages", [])) + receipts
    provenance.update(
        {
            "retrievalMode": f"overview-enrichment:{mode}",
            "stopReason": "recordLimit" if len(selected_ids) < len(records) else "sourceExhausted",
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
                "allowedRecordFields": [
                    "contacts",
                    "firstReleased",
                    "geographicCoverage",
                    "lastRevised",
                    "lastUpdated",
                    "nextUpdate",
                ],
            },
            "enrichmentRun": {
                "schema": _ENRICHMENT_SCHEMA,
                "cohortCount": len(records),
                "requestedLimit": limit,
                "selectedCount": len(selected_ids),
                "unselectedCount": len(records) - len(selected_ids),
                "coverageComplete": len(selected_ids) == len(records),
                "selectionOrder": "sha256(sourceRecordId)-ascending",
                "selectedRecordSetSha256": sha256_json(selected_ids),
                "select": list(SELECT_TERMS),
            },
            "assurance": {
                **dict(provenance.get("assurance", {})),
                "metadataOnly": True,
                "observationsFetched": False,
                "codelistsFetched": False,
                "credentialsRequired": False,
                "cacheLocationPublished": False,
                "rawResponsesPublished": False,
            },
        }
    )
    return {
        "schemaVersion": "okf-ons.source-acquisition.v1",
        "records": records,
        "provenance": provenance,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument(
        "--mode", choices=("prefer-cache", "refresh", "frozen"), default="prefer-cache"
    )
    parser.add_argument("--request-interval", type=float, default=0.2)
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
    except (NomisOverviewError, OSError) as exc:
        parser.exit(1, f"Nomis overview enrichment error: {exc}\n")
    run = envelope["provenance"]["enrichmentRun"]
    print(
        f"Acquired {run['selectedCount']} of {run['cohortCount']} ranked Nomis "
        f"overviews into {arguments.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
