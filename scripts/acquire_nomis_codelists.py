#!/usr/bin/env python3
"""Acquire bounded projected Nomis FREQ and TIME codelist metadata.

The exact frozen r5 Nomis cohort supplies dataset and codelist identity.  Two
metadata-only codelists are requested for each SHA-256-ranked record.  Raw SDMX
responses are validated in memory and discarded; the external cache and the
replacement envelope contain only bounded code values, labels and explicit
TIME revision evidence.  Observation endpoints are never permitted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ID = "nomis-dataset-definitions"
SOURCE_ENDPOINT = "https://www.nomisweb.co.uk/api/v01/dataset/def.sdmx.json"
CODELIST_ENDPOINT_TEMPLATE = (
    "https://www.nomisweb.co.uk/api/v01/codelist/{codelistId}.def.sdmx.json"
)
DEFAULT_SNAPSHOT = ROOT / "source" / "metadata-enrichment-2026-07-21-r5"
EXPECTED_SNAPSHOT_ID = "metadata-enrichment-2026-07-21-r5"
EXPECTED_MANIFEST_SHA256 = (
    "d6659db23f4b1bf190eefade0aa2aaacf22f0c4aef5eacd20b4b00dd1ba9871d"
)
EXPECTED_NOMIS_FILE_SHA256 = (
    "58aecb59cf32386b8c2a4d236070f43fd0e044c42ed44587de1e9012bf365622"
)
EXPECTED_RECORD_SET_SHA256 = (
    "df138d06a2627c3ddd3a0e47c4e482e3c9dde6ef371893f76f6242926a15b30a"
)
EXPECTED_SNAPSHOT_SET_SHA256 = (
    "32d03c8315e05208abadd14c2c9050d13ee0ee0f97dae93fff9e403727f67cfe"
)
EXPECTED_COHORT_COUNT = 1_617
CONCEPTS = ("FREQ", "TIME")
MAX_MANIFEST_BYTES = 1_000_000
MAX_BASE_FILE_BYTES = 128_000_000
MAX_RESPONSE_BYTES = 2_000_000
MAX_CACHE_BYTES = 4_000_000
MAX_CODE_COUNT = 20_000
MAX_SCALAR_LENGTH = 20_000
MIN_PRODUCTION_INTERVAL_SECONDS = 0.2
_CACHE_SCHEMA = "okf-ons.nomis-codelist-cache.v2"
_REPLACEMENT_SCHEMA = "okf-ons.bounded-source-replacement.v1"
_ENRICHMENT_SCHEMA = "okf-ons.nomis-codelist-enrichment.v1"
_ACQUISITION_KEYS = {"schemaVersion", "records", "provenance"}
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
    "acquisitionStatus",
    "attemptCount",
    "contentSha256",
    "failureReason",
    "httpStatus",
    "payload",
    "requestUrl",
    "responseHeaders",
    "responseUrl",
    "retrievedAt",
    "schema",
}
_PROJECTED_KEYS = {"codeList", "codes", "status"}
_PROJECTED_FAILURE_KEYS = _PROJECTED_KEYS | {"reason", "status"}
_PROJECTED_CODE_REQUIRED_KEYS = {"label", "value"}
_PROJECTED_CODE_OPTIONAL_KEYS = {"revisionStatus"}
_RAW_STRUCTURE_KEYS = {
    "codelists",
    "common",
    "header",
    "schemalocation",
    "structure",
    "xmlns",
    "xsi",
}
_RAW_HEADER_KEYS = {"id", "prepared", "sender", "test"}
_RAW_SENDER_KEYS = {"contact", "id"}
_RAW_CONTACT_KEYS = {"email", "name", "telephone", "uri"}
_RAW_CODELIST_KEYS = {"agencyid", "code", "id", "name", "uri"}
_RAW_CODE_KEYS = {"annotations", "description", "value"}
_RAW_TEXT_KEYS = {"lang", "value"}
_RAW_ANNOTATION_KEYS = {
    "annotationtext",
    "annotationtitle",
    "annotationtype",
    "annotationurl",
}
_SAFE_RESPONSE_HEADER_KEYS = {"content-type", "etag", "last-modified"}
_HEX_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_NOMIS_ID_RE = re.compile(r"^NM_([0-9]+)_([0-9]+)$")
_CODELIST_ID_RE = re.compile(r"^CL_([0-9]+)_([0-9]+)_(FREQ|TIME)$")
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
    "clientsecret",
    "credential",
    "credentials",
    "observation",
    "observations",
    "obsvalue",
    "password",
    "secret",
    "token",
    "xapikey",
}
_FAILURE_REASON = "upstream-codelist-unavailable"
_AUDITED_SCALAR_CODELISTS = {
    ("NM_17_1", "TIME", "CL_17_1_TIME"),
}


class NomisCodelistError(ValueError):
    """Raised when codelist acquisition cannot remain fail-closed."""


@dataclass(frozen=True)
class JsonResponse:
    payload: Any
    final_url: str
    status: int = 200
    headers: Mapping[str, str] | None = None


class JsonTransport(Protocol):
    def get(self, url: str, *, timeout: float) -> JsonResponse: ...


class UrllibJsonTransport:
    """Bounded JSON transport for public Nomis structural metadata."""

    def get(self, url: str, *, timeout: float) -> JsonResponse:
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "okf-ons/nomis-codelist",
            },
        )
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                body = response.read(MAX_RESPONSE_BYTES + 1)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise NomisCodelistError(
                        "Nomis codelist exceeded the response byte limit"
                    )
                try:
                    payload = json.loads(body.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise NomisCodelistError(
                        "Nomis codelist was not valid UTF-8 JSON"
                    ) from exc
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
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            headers = {"retry-after": retry_after} if retry_after else {}
            return JsonResponse(
                payload=None,
                final_url=exc.geturl(),
                status=int(exc.code),
                headers=headers,
            )
        except URLError as exc:
            raise OSError("Nomis codelist request failed") from exc


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
        details = []
        if unknown:
            details.append("unreviewed field(s): " + ", ".join(unknown))
        if missing:
            details.append("missing field(s): " + ", ".join(missing))
        raise NomisCodelistError(f"{label} has " + "; ".join(details))


def _normalised_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def _assert_safe(value: Any, *, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if _normalised_key(key) in _FORBIDDEN_KEYS:
                raise NomisCodelistError(f"unsafe field {key!r} at {path}")
            _assert_safe(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_safe(child, path=f"{path}[{index}]")
    elif isinstance(value, bytes):
        raise NomisCodelistError(f"binary data at {path}")
    elif isinstance(value, float) and not math.isfinite(value):
        raise NomisCodelistError(f"non-finite number at {path}")
    elif isinstance(value, str):
        if len(value) > MAX_SCALAR_LENGTH:
            raise NomisCodelistError(f"oversized scalar at {path}")
        if _LOCAL_PATH_RE.search(value) or any(
            pattern.search(value) for pattern in _SECRET_VALUE_PATTERNS
        ):
            raise NomisCodelistError(f"unsafe value at {path}")


def _bounded_text(value: Any, limit: int, label: str) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise NomisCodelistError(f"{label} must be a scalar string or number")
    if isinstance(value, float) and not math.isfinite(value):
        raise NomisCodelistError(f"{label} must be finite")
    text = str(value).strip()
    if not text or len(text) > limit:
        raise NomisCodelistError(f"{label} is empty or exceeds its size limit")
    _assert_safe(text, path=label)
    return text


def _validated_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or _HEX_SHA256_RE.fullmatch(value) is None:
        raise NomisCodelistError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _validate_utc_timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str) or _UTC_TIMESTAMP_RE.fullmatch(value) is None:
        raise NomisCodelistError(f"{label} must be a UTC ISO 8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise NomisCodelistError(f"{label} is not a valid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise NomisCodelistError(f"{label} must be UTC")
    return value


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _validated_response_headers(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise NomisCodelistError("Nomis codelist response headers are malformed")
    headers: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        if not isinstance(raw_key, str):
            raise NomisCodelistError("Nomis codelist response headers are malformed")
        key = raw_key.casefold()
        if (
            key != raw_key
            or key not in _SAFE_RESPONSE_HEADER_KEYS
            or key in headers
            or not isinstance(raw_value, str)
            or not raw_value.strip()
            or len(raw_value) > 2_000
        ):
            raise NomisCodelistError("Nomis codelist response headers are unsafe")
        _assert_safe(raw_value, path=f"responseHeaders.{key}")
        headers[key] = raw_value
    content_type = headers.get("content-type")
    if content_type is not None and not content_type.casefold().startswith(
        "application/json"
    ):
        raise NomisCodelistError("Nomis codelist response content type is not JSON")
    return headers


def _codelist_url(codelist_id: str) -> str:
    if _CODELIST_ID_RE.fullmatch(codelist_id) is None:
        raise NomisCodelistError("Nomis codelist identity is invalid")
    return CODELIST_ENDPOINT_TEMPLATE.format(
        codelistId=quote(codelist_id, safe="")
    )


def _validate_request_url(url: str, *, expected_codelist_id: str) -> str:
    parsed = urlsplit(url)
    match = re.fullmatch(
        r"/api/v01/codelist/(CL_[0-9]+_[0-9]+_(?:FREQ|TIME))\.def\.sdmx\.json",
        parsed.path,
    )
    if (
        parsed.scheme != "https"
        or parsed.netloc != "www.nomisweb.co.uk"
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or match is None
        or match.group(1) != expected_codelist_id
    ):
        raise NomisCodelistError(
            "codelist request escaped the metadata-only Nomis template"
        )
    return match.group(1)


def _validate_text_object(value: Any, label: str) -> str:
    if not isinstance(value, Mapping):
        raise NomisCodelistError(f"{label} is malformed")
    if not {"value"}.issubset(value) or set(value) - _RAW_TEXT_KEYS:
        raise NomisCodelistError(f"{label} has unreviewed or missing fields")
    if "lang" in value and value["lang"] not in {"en", "EN", None}:
        raise NomisCodelistError(f"{label} has an unsupported language")
    return _bounded_text(value["value"], 500, f"{label}.value")


def _annotation_rows(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, Mapping):
        raise NomisCodelistError(f"{label} is malformed")
    _validate_exact_keys(value, {"annotation"}, label)
    raw_rows = value["annotation"]
    if isinstance(raw_rows, Mapping):
        rows: list[Any] = [raw_rows]
    elif isinstance(raw_rows, list):
        rows = raw_rows
    else:
        raise NomisCodelistError(f"{label} is malformed")
    validated: list[Mapping[str, Any]] = []
    for index, row in enumerate(rows):
        if (
            not isinstance(row, Mapping)
            or not {"annotationtext", "annotationtitle"}.issubset(row)
            or set(row) - _RAW_ANNOTATION_KEYS
        ):
            raise NomisCodelistError(f"{label}[{index}] is malformed")
        for key, child in row.items():
            _bounded_text(child, 20_000, f"{label}[{index}].{key}")
        validated.append(row)
    return validated


def _selected_annotation(
    rows: Sequence[Mapping[str, Any]], title: str, label: str
) -> str | None:
    values = {
        _bounded_text(row["annotationtext"], 500, label)
        for row in rows
        if _bounded_text(row["annotationtitle"], 500, label) == title
    }
    if len(values) > 1:
        raise NomisCodelistError(f"{label} has conflicting {title} annotations")
    return next(iter(values), None)


def _validate_raw_payload(
    payload: Any,
    *,
    record_id: str,
    concept: str,
    codelist_id: str,
) -> dict[str, Any] | None:
    if not isinstance(payload, Mapping):
        raise NomisCodelistError(f"Nomis {concept} codelist is malformed")
    _validate_exact_keys(payload, {"structure"}, "Nomis codelist payload")
    structure = payload["structure"]
    if not isinstance(structure, Mapping):
        raise NomisCodelistError("Nomis codelist structure is malformed")
    _validate_exact_keys(structure, _RAW_STRUCTURE_KEYS, "Nomis codelist structure")

    header = structure["header"]
    if not isinstance(header, Mapping):
        raise NomisCodelistError("Nomis codelist header is malformed")
    _validate_exact_keys(header, _RAW_HEADER_KEYS, "Nomis codelist header")
    if header["id"] != record_id or header["test"] not in {"false", False}:
        raise NomisCodelistError("Nomis codelist dataset identity mismatch")
    _validate_utc_timestamp(header["prepared"], "Nomis codelist preparation time")
    sender = header["sender"]
    if (
        not isinstance(sender, Mapping)
        or not {"id"}.issubset(sender)
        or set(sender) - _RAW_SENDER_KEYS
        or sender["id"] != "NOMIS"
    ):
        raise NomisCodelistError("Nomis codelist sender is malformed")
    contact = sender.get("contact")
    if contact is not None:
        if not isinstance(contact, Mapping) or set(contact) - _RAW_CONTACT_KEYS:
            raise NomisCodelistError("Nomis codelist sender contact is malformed")
        for key, value in contact.items():
            _bounded_text(value, 2_000, f"Nomis sender contact {key}")

    for key in _RAW_STRUCTURE_KEYS - {"codelists", "header"}:
        if not isinstance(structure[key], str):
            raise NomisCodelistError(f"Nomis codelist namespace {key} is malformed")
        _bounded_text(structure[key], 1_000, f"Nomis codelist namespace {key}")

    codelists = structure["codelists"]
    if codelists is None:
        _assert_safe(payload)
        return None
    if not isinstance(codelists, Mapping):
        raise NomisCodelistError("Nomis codelist collection is malformed")
    _validate_exact_keys(codelists, {"codelist"}, "Nomis codelist collection")
    raw_codelists = codelists["codelist"]
    if not isinstance(raw_codelists, list) or len(raw_codelists) != 1:
        raise NomisCodelistError("Nomis codelist collection must contain exactly one list")
    raw_codelist = raw_codelists[0]
    if not isinstance(raw_codelist, Mapping):
        raise NomisCodelistError("Nomis codelist is malformed")
    _validate_exact_keys(raw_codelist, _RAW_CODELIST_KEYS, "Nomis codelist")
    if raw_codelist["agencyid"] != "NOMIS" or raw_codelist["id"] != codelist_id:
        raise NomisCodelistError("Nomis codelist identity mismatch")
    _validate_text_object(raw_codelist["name"], "Nomis codelist name")
    if not isinstance(raw_codelist["uri"], str):
        raise NomisCodelistError("Nomis codelist URI is malformed")

    raw_codes = raw_codelist["code"]
    if (
        not isinstance(raw_codes, list)
        or not raw_codes
        or len(raw_codes) > MAX_CODE_COUNT
    ):
        raise NomisCodelistError("Nomis codelist code collection is invalid")
    projected_codes: list[dict[str, str]] = []
    seen_values: set[str] = set()
    for index, raw_code in enumerate(raw_codes):
        if (
            not isinstance(raw_code, Mapping)
            or not {"description", "value"}.issubset(raw_code)
            or set(raw_code) - _RAW_CODE_KEYS
        ):
            raise NomisCodelistError(f"Nomis codelist code {index} is malformed")
        code_value = _bounded_text(
            raw_code["value"], 500, f"Nomis codelist code {index} value"
        )
        if code_value in seen_values:
            raise NomisCodelistError("Nomis codelist contains duplicate code values")
        seen_values.add(code_value)
        projected_code = {
            "value": code_value,
            "label": _validate_text_object(
                raw_code["description"], f"Nomis codelist code {index} description"
            ),
        }
        annotations: list[Mapping[str, Any]] = []
        if "annotations" in raw_code:
            annotations = _annotation_rows(
                raw_code["annotations"], f"Nomis codelist code {index} annotations"
            )
        revision_status = _selected_annotation(
            annotations,
            "CurrentRevisionStatus",
            f"Nomis codelist code {index} revision status",
        )
        if concept == "FREQ" and revision_status:
            raise NomisCodelistError(
                "Nomis FREQ codelist unexpectedly contains TIME revision evidence"
            )
        if revision_status:
            projected_code["revisionStatus"] = revision_status
        projected_codes.append(projected_code)

    _assert_safe(payload)
    return {"codeList": codelist_id, "codes": projected_codes, "status": "present"}


def _validate_projected_payload(value: Any, codelist_id: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise NomisCodelistError("projected Nomis codelist is malformed")
    keys = set(value)
    if keys != _PROJECTED_KEYS and keys != _PROJECTED_FAILURE_KEYS:
        raise NomisCodelistError(
            "projected Nomis codelist has unreviewed or missing fields"
        )
    if value["codeList"] != codelist_id:
        raise NomisCodelistError("projected Nomis codelist identity mismatch")
    codes = value["codes"]
    is_failure = keys == _PROJECTED_FAILURE_KEYS
    if not isinstance(codes, list) or len(codes) > MAX_CODE_COUNT:
        raise NomisCodelistError("projected Nomis codelist codes are malformed")
    if is_failure:
        if (
            codes
            or value["status"] != "not-evidenced"
            or value["reason"] != _FAILURE_REASON
        ):
            raise NomisCodelistError(
                "projected unavailable Nomis codelist is malformed"
            )
        projected_failure = {
            "codeList": codelist_id,
            "codes": [],
            "status": "not-evidenced",
            "reason": _FAILURE_REASON,
        }
        _assert_safe(projected_failure)
        return projected_failure
    if not codes:
        raise NomisCodelistError(
            "projected available Nomis codelist must contain codes"
        )
    if value["status"] != "present":
        raise NomisCodelistError(
            "projected available Nomis codelist status must be present"
        )
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, code in enumerate(codes):
        if (
            not isinstance(code, Mapping)
            or not _PROJECTED_CODE_REQUIRED_KEYS.issubset(code)
            or set(code)
            - (_PROJECTED_CODE_REQUIRED_KEYS | _PROJECTED_CODE_OPTIONAL_KEYS)
        ):
            raise NomisCodelistError(f"projected Nomis codelist code {index} is malformed")
        projected = {
            "value": _bounded_text(code["value"], 500, "projected code value"),
            "label": _bounded_text(code["label"], 500, "projected code label"),
        }
        if projected["value"] in seen:
            raise NomisCodelistError("projected Nomis codelist has duplicate values")
        seen.add(projected["value"])
        if "revisionStatus" in code:
            projected["revisionStatus"] = _bounded_text(
                code["revisionStatus"], 500, "projected revision status"
            )
        output.append(projected)
    projected_payload = {
        "codeList": codelist_id,
        "codes": output,
        "status": "present",
    }
    _assert_safe(projected_payload)
    return projected_payload


def _cache_path(cache_directory: Path, request_url: str) -> Path:
    digest = hashlib.sha256(request_url.encode("utf-8")).hexdigest()
    return cache_directory / "nomis-codelist-v2" / f"{digest}.json"


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


def _load_cache(path: Path, request_url: str, codelist_id: str) -> dict[str, Any]:
    expected_parent = path.parent.resolve()
    if path.is_symlink() or not path.is_file() or path.resolve().parent != expected_parent:
        raise NomisCodelistError("Nomis codelist cache entry is not a regular file")
    try:
        data = path.read_bytes()
        if len(data) > MAX_CACHE_BYTES:
            raise NomisCodelistError("Nomis codelist cache entry exceeds the size limit")
        envelope = json.loads(data)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NomisCodelistError("Nomis codelist cache entry is unreadable") from exc
    if not isinstance(envelope, Mapping):
        raise NomisCodelistError("Nomis codelist cache entry is malformed")
    _validate_exact_keys(envelope, _CACHE_KEYS, "Nomis codelist cache entry")
    if (
        envelope["schema"] != _CACHE_SCHEMA
        or envelope["requestUrl"] != request_url
        or envelope["responseUrl"] != request_url
    ):
        raise NomisCodelistError("Nomis codelist cache entry failed validation")
    _validate_request_url(request_url, expected_codelist_id=codelist_id)
    _validate_utc_timestamp(envelope["retrievedAt"], "Nomis codelist retrieval time")
    headers = _validated_response_headers(envelope["responseHeaders"])
    payload = _validate_projected_payload(envelope["payload"], codelist_id)
    attempt_count = envelope["attemptCount"]
    http_status = envelope["httpStatus"]
    acquisition_status = envelope["acquisitionStatus"]
    failure_reason = envelope["failureReason"]
    if (
        isinstance(attempt_count, bool)
        or not isinstance(attempt_count, int)
        or attempt_count < 1
        or attempt_count > 6
        or isinstance(http_status, bool)
        or not isinstance(http_status, int)
        or http_status < 200
        or http_status > 599
        or acquisition_status != payload["status"]
        or failure_reason != payload.get("reason")
        or (payload["status"] == "present" and not 200 <= http_status < 300)
        or (
            payload["status"] == "not-evidenced"
            and http_status != 200
            and http_status not in {408, 425, 429}
            and not 500 <= http_status < 600
        )
    ):
        raise NomisCodelistError("Nomis codelist cache outcome evidence is invalid")
    digest = _validated_sha256(
        envelope["contentSha256"], "Nomis codelist projected content hash"
    )
    if digest != sha256_json(payload):
        raise NomisCodelistError("Nomis codelist cache content hash mismatch")
    result = dict(envelope)
    result["responseHeaders"] = headers
    result["payload"] = payload
    _assert_safe(result)
    return result


def _retry_after_seconds(value: Any, now: datetime) -> float | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    try:
        seconds = float(raw)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(raw)
        except (TypeError, ValueError, OverflowError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        seconds = (parsed.astimezone(UTC) - now.astimezone(UTC)).total_seconds()
    if not math.isfinite(seconds):
        return None
    return min(max(seconds, 0.0), 60.0)


def _fetch_codelist(
    record_id: str,
    concept: str,
    codelist_id: str,
    *,
    cache_directory: Path,
    mode: str,
    transport: JsonTransport,
    timeout_seconds: float,
    retries: int,
    now: Callable[[], datetime],
    sleep: Callable[[float], None],
    before_live_request: Callable[[], None],
) -> tuple[dict[str, Any], dict[str, Any]]:
    request_url = _codelist_url(codelist_id)
    _validate_request_url(request_url, expected_codelist_id=codelist_id)
    cache_path = _cache_path(cache_directory, request_url)
    if mode != "refresh" and (cache_path.exists() or cache_path.is_symlink()):
        cached = _load_cache(cache_path, request_url, codelist_id)
        return dict(cached["payload"]), {
            "requestUrl": request_url,
            "responseUrl": cached["responseUrl"],
            "retrievedAt": cached["retrievedAt"],
            "contentSha256": cached["contentSha256"],
            "responseHeaders": cached["responseHeaders"],
            "cacheHit": True,
            "upstreamRecordCount": 1 if cached["httpStatus"] == 200 else 0,
            "normalisedRecordCount": 1,
            "attemptCount": cached["attemptCount"],
            "acquisitionStatus": cached["acquisitionStatus"],
            "httpStatus": cached["httpStatus"],
            "failureReason": cached["failureReason"],
        }
    if mode == "frozen":
        raise NomisCodelistError(f"frozen cache is missing codelist {codelist_id}")

    for attempt in range(retries + 1):
        try:
            before_live_request()
            response = transport.get(request_url, timeout=timeout_seconds)
            if (
                isinstance(response.status, bool)
                or not isinstance(response.status, int)
                or response.status < 100
                or response.status > 599
            ):
                raise NomisCodelistError("Nomis codelist response status is malformed")
            if response.final_url != request_url:
                raise NomisCodelistError(
                    "Nomis codelist response URL changed unexpectedly"
                )
            _validate_request_url(
                response.final_url, expected_codelist_id=codelist_id
            )

            payload: dict[str, Any] | None = None
            failure_reason: str | None = None
            upstream_record_count = 1
            if response.status < 200 or response.status >= 300:
                retryable = response.status in {408, 425, 429} or response.status >= 500
                if retryable and attempt < retries:
                    retry_after = _retry_after_seconds(
                        (response.headers or {}).get("retry-after"), now()
                    )
                    sleep(
                        retry_after
                        if retry_after is not None
                        else min(2**attempt, 8)
                    )
                    continue
                if not retryable:
                    raise NomisCodelistError(
                        f"Nomis returned HTTP {response.status} for {codelist_id}"
                    )
                payload = {
                    "codeList": codelist_id,
                    "codes": [],
                    "status": "not-evidenced",
                    "reason": _FAILURE_REASON,
                }
                failure_reason = _FAILURE_REASON
                upstream_record_count = 0
            else:
                audited_scalar_error = (
                    (record_id, concept, codelist_id)
                    in _AUDITED_SCALAR_CODELISTS
                    and not isinstance(response.payload, Mapping)
                )
                if audited_scalar_error:
                    _assert_safe(response.payload, path="audited upstream scalar")
                    if attempt < retries:
                        sleep(min(2**attempt, 8))
                        continue
                    payload = {
                        "codeList": codelist_id,
                        "codes": [],
                        "status": "not-evidenced",
                        "reason": _FAILURE_REASON,
                    }
                    failure_reason = _FAILURE_REASON
                else:
                    payload = _validate_raw_payload(
                        response.payload,
                        record_id=record_id,
                        concept=concept,
                        codelist_id=codelist_id,
                    )
                if payload is None:
                    if attempt < retries:
                        sleep(min(2**attempt, 8))
                        continue
                    payload = {
                        "codeList": codelist_id,
                        "codes": [],
                        "status": "not-evidenced",
                        "reason": _FAILURE_REASON,
                    }
                    failure_reason = _FAILURE_REASON
            payload = _validate_projected_payload(payload, codelist_id)
            safe_response_headers = {
                key: value
                for key, value in (response.headers or {}).items()
                if key in _SAFE_RESPONSE_HEADER_KEYS
            }
            headers = _validated_response_headers(safe_response_headers)
            retrieved_at = _utc_iso(now())
            _validate_utc_timestamp(retrieved_at, "Nomis codelist retrieval time")
            content_sha256 = sha256_json(payload)
            cached = {
                "schema": _CACHE_SCHEMA,
                "requestUrl": request_url,
                "responseUrl": response.final_url,
                "retrievedAt": retrieved_at,
                "contentSha256": content_sha256,
                "responseHeaders": headers,
                "payload": payload,
                "attemptCount": attempt + 1,
                "acquisitionStatus": payload["status"],
                "httpStatus": response.status,
                "failureReason": failure_reason,
            }
            _assert_safe(cached)
            _write_atomic_json(cache_path, cached)
            return payload, {
                "requestUrl": request_url,
                "responseUrl": response.final_url,
                "retrievedAt": retrieved_at,
                "contentSha256": content_sha256,
                "responseHeaders": headers,
                "cacheHit": False,
                "upstreamRecordCount": upstream_record_count,
                "normalisedRecordCount": 1,
                "attemptCount": attempt + 1,
                "acquisitionStatus": payload["status"],
                "httpStatus": response.status,
                "failureReason": failure_reason,
            }
        except (TimeoutError, OSError) as exc:
            if attempt < retries:
                sleep(min(2**attempt, 8))
                continue
            if (record_id, concept, codelist_id) not in _AUDITED_SCALAR_CODELISTS:
                raise NomisCodelistError(
                    f"unable to acquire Nomis codelist {codelist_id}: {exc}"
                ) from exc
            raise NomisCodelistError(
                "audited upstream-error codelist did not return an HTTP status"
            ) from exc
    raise NomisCodelistError(f"unable to acquire Nomis codelist {codelist_id}")


def _validate_base_receipt_url(value: Any) -> str:
    if not isinstance(value, str):
        raise NomisCodelistError("frozen Nomis receipt URL is malformed")
    if value == SOURCE_ENDPOINT:
        return value
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "www.nomisweb.co.uk"
        or parsed.username
        or parsed.password
        or parsed.fragment
        or re.fullmatch(
            r"/api/v01/dataset/NM_[0-9]+_[0-9]+\.overview\.json", parsed.path
        )
        is None
        or parsed.query
        != "select=DatasetInfo%2CCoverage%2CDateMetadata%2CContact"
    ):
        raise NomisCodelistError("frozen Nomis receipt escaped its metadata endpoint")
    return value


def _load_exact_base(snapshot_directory: Path) -> tuple[dict[str, Any], str]:
    if snapshot_directory.is_symlink() or not snapshot_directory.is_dir():
        raise NomisCodelistError("frozen r5 snapshot directory is unsafe")
    resolved = snapshot_directory.resolve()
    manifest_path = snapshot_directory / "snapshot.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise NomisCodelistError("frozen r5 manifest is unsafe")
    manifest_bytes = manifest_path.read_bytes()
    if len(manifest_bytes) > MAX_MANIFEST_BYTES:
        raise NomisCodelistError("frozen r5 manifest exceeds the size limit")
    if sha256_bytes(manifest_bytes) != EXPECTED_MANIFEST_SHA256:
        raise NomisCodelistError("frozen snapshot is not the exact audited r5 manifest")
    try:
        manifest = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NomisCodelistError("frozen r5 manifest is unreadable") from exc
    if (
        not isinstance(manifest, Mapping)
        or manifest.get("snapshotId") != EXPECTED_SNAPSHOT_ID
        or manifest.get("schema") != "okf-ons.frozen-snapshot.v1"
        or manifest.get("metadataOnly") is not True
        or manifest.get("observationsIncluded") is not False
        or manifest.get("completeForRegisteredAdapters") is not True
    ):
        raise NomisCodelistError("frozen r5 manifest failed safety validation")
    source_rows = manifest.get("sources")
    if not isinstance(source_rows, list):
        raise NomisCodelistError("frozen r5 source ledger is malformed")
    matching = [
        row
        for row in source_rows
        if isinstance(row, Mapping) and row.get("sourceId") == SOURCE_ID
    ]
    if len(matching) != 1:
        raise NomisCodelistError("frozen r5 has no unique Nomis source row")
    source_row = matching[0]
    if (
        source_row.get("file") != f"{SOURCE_ID}.json"
        or source_row.get("recordCount") != EXPECTED_COHORT_COUNT
        or source_row.get("reportedTotal") != EXPECTED_COHORT_COUNT
        or source_row.get("coverageComplete") is not True
        or source_row.get("unrepresentedCount") != 0
        or source_row.get("normalisationDroppedCount") != 0
        or source_row.get("sha256") != EXPECTED_NOMIS_FILE_SHA256
        or source_row.get("recordSetSha256") != EXPECTED_RECORD_SET_SHA256
        or source_row.get("snapshotSetSha256") != EXPECTED_SNAPSHOT_SET_SHA256
    ):
        raise NomisCodelistError("frozen r5 Nomis source row is not the audited cohort")
    acquisition_path = snapshot_directory / f"{SOURCE_ID}.json"
    if (
        acquisition_path.is_symlink()
        or not acquisition_path.is_file()
        or acquisition_path.resolve().parent != resolved
    ):
        raise NomisCodelistError("frozen r5 Nomis source file is unsafe")
    acquisition_bytes = acquisition_path.read_bytes()
    if len(acquisition_bytes) > MAX_BASE_FILE_BYTES:
        raise NomisCodelistError("frozen r5 Nomis source file exceeds the size limit")
    if sha256_bytes(acquisition_bytes) != EXPECTED_NOMIS_FILE_SHA256:
        raise NomisCodelistError("frozen r5 Nomis source file hash mismatch")
    try:
        acquisition = json.loads(acquisition_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NomisCodelistError("frozen r5 Nomis source file is unreadable") from exc
    if not isinstance(acquisition, Mapping):
        raise NomisCodelistError("frozen r5 Nomis acquisition is malformed")
    _validate_exact_keys(acquisition, _ACQUISITION_KEYS, "frozen Nomis acquisition")
    records = acquisition.get("records")
    provenance = acquisition.get("provenance")
    if (
        acquisition.get("schemaVersion") != "okf-ons.source-acquisition.v1"
        or not isinstance(records, list)
        or len(records) != EXPECTED_COHORT_COUNT
        or not isinstance(provenance, Mapping)
        or provenance.get("recordCount") != EXPECTED_COHORT_COUNT
        or provenance.get("reportedTotal") != EXPECTED_COHORT_COUNT
        or provenance.get("complete") is not True
        or provenance.get("coverageComplete") is not True
        or provenance.get("unrepresentedCount") != 0
        or provenance.get("normalisationDroppedCount") != 0
        or provenance.get("recordSetSha256") != EXPECTED_RECORD_SET_SHA256
        or provenance.get("snapshotSetSha256") != EXPECTED_SNAPSHOT_SET_SHA256
    ):
        raise NomisCodelistError("frozen r5 Nomis acquisition failed validation")
    source = provenance.get("source")
    assurance = provenance.get("assurance")
    if (
        not isinstance(source, Mapping)
        or source.get("id") != SOURCE_ID
        or source.get("endpoint") != SOURCE_ENDPOINT
        or not isinstance(assurance, Mapping)
        or assurance.get("metadataOnly") is not True
        or assurance.get("observationsFetched") is not False
        or assurance.get("credentialsRequired") is not False
        or assurance.get("cacheLocationPublished") is not False
        or assurance.get("rawResponsesPublished") is not False
    ):
        raise NomisCodelistError("frozen r5 Nomis provenance failed safety validation")
    if sha256_json(records) != EXPECTED_RECORD_SET_SHA256:
        raise NomisCodelistError("frozen r5 Nomis record-set hash mismatch")
    pages = provenance.get("pages")
    if (
        not isinstance(pages, list)
        or provenance.get("pageCount") != len(pages)
        or not pages
    ):
        raise NomisCodelistError("frozen r5 Nomis receipts are malformed")
    snapshot_receipts: list[dict[str, str]] = []
    for index, page in enumerate(pages):
        if not isinstance(page, Mapping):
            raise NomisCodelistError(f"frozen Nomis receipt {index} is malformed")
        _validate_exact_keys(page, _PAGE_KEYS, f"frozen Nomis receipt {index}")
        request_url = _validate_base_receipt_url(page["requestUrl"])
        if page["responseUrl"] != request_url or not isinstance(page["cacheHit"], bool):
            raise NomisCodelistError(f"frozen Nomis receipt {index} identity mismatch")
        for key in ("upstreamRecordCount", "normalisedRecordCount"):
            if isinstance(page[key], bool) or not isinstance(page[key], int) or page[key] < 0:
                raise NomisCodelistError(f"frozen Nomis receipt {index} count is malformed")
        _validate_utc_timestamp(page["retrievedAt"], "frozen Nomis retrieval time")
        _validated_sha256(page["contentSha256"], "frozen Nomis receipt hash")
        _validated_response_headers(page["responseHeaders"])
        snapshot_receipts.append(
            {"requestUrl": request_url, "contentSha256": page["contentSha256"]}
        )
    if sha256_json(snapshot_receipts) != EXPECTED_SNAPSHOT_SET_SHA256:
        raise NomisCodelistError("frozen r5 Nomis snapshot-set hash mismatch")
    return dict(acquisition), EXPECTED_SNAPSHOT_ID


def _cohort_references(
    records: Sequence[Any],
) -> tuple[list[str], dict[str, tuple[str, str]]]:
    record_ids: list[str] = []
    references: dict[str, tuple[str, str]] = {}
    seen_codelists: set[str] = set()
    for raw in records:
        if not isinstance(raw, Mapping):
            raise NomisCodelistError("frozen Nomis record is malformed")
        record_id = raw.get("sourceRecordId")
        match = _NOMIS_ID_RE.fullmatch(record_id) if isinstance(record_id, str) else None
        if (
            match is None
            or raw.get("sourceId") != SOURCE_ID
            or record_id in references
            or "nomisCodelists" in raw
        ):
            raise NomisCodelistError("frozen Nomis cohort identity is invalid")
        components = raw.get("components")
        if not isinstance(components, list):
            raise NomisCodelistError(f"frozen Nomis components are missing for {record_id}")
        record_references: list[str] = []
        for concept in CONCEPTS:
            expected_kind = "dimension" if concept == "FREQ" else "timedimension"
            matches = [
                item
                for item in components
                if isinstance(item, Mapping)
                and item.get("concept") == concept
                and item.get("kind") == expected_kind
            ]
            if len(matches) != 1:
                raise NomisCodelistError(
                    f"{record_id} must have exactly one {concept} codelist reference"
                )
            codelist_id = matches[0].get("codeList")
            expected_id = f"CL_{match.group(1)}_{match.group(2)}_{concept}"
            if codelist_id != expected_id or _CODELIST_ID_RE.fullmatch(expected_id) is None:
                raise NomisCodelistError(
                    f"{record_id} has an invalid {concept} codelist reference"
                )
            if codelist_id in seen_codelists:
                raise NomisCodelistError("Nomis cohort reuses a FREQ/TIME codelist identity")
            seen_codelists.add(codelist_id)
            record_references.append(codelist_id)
        record_ids.append(record_id)
        references[record_id] = (record_references[0], record_references[1])
    if len(record_ids) != EXPECTED_COHORT_COUNT:
        raise NomisCodelistError("Nomis cohort count changed from the audited r5 cohort")
    return record_ids, references


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
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise NomisCodelistError("record limit must be positive")
    if mode not in {"prefer-cache", "refresh", "frozen"}:
        raise NomisCodelistError("unsupported cache mode")
    if (
        isinstance(request_interval_seconds, bool)
        or not isinstance(request_interval_seconds, (int, float))
        or not math.isfinite(request_interval_seconds)
        or request_interval_seconds < 0
        or request_interval_seconds > 60
    ):
        raise NomisCodelistError("request interval must be between 0 and 60 seconds")
    if (
        mode != "frozen"
        and transport is None
        and request_interval_seconds < MIN_PRODUCTION_INTERVAL_SECONDS
    ):
        raise NomisCodelistError(
            "live Nomis acquisition requires a request interval of at least 0.2 seconds"
        )
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
        or timeout_seconds > 300
    ):
        raise NomisCodelistError("timeout must be greater than 0 and at most 300 seconds")
    if isinstance(retries, bool) or not isinstance(retries, int) or retries < 0 or retries > 5:
        raise NomisCodelistError("retries must be between 0 and 5")
    resolved_cache = cache_directory.resolve()
    if (
        cache_directory.is_symlink()
        or resolved_cache == ROOT.resolve()
        or ROOT.resolve() in resolved_cache.parents
    ):
        raise NomisCodelistError("projected codelist cache must be outside the repository")

    acquisition, snapshot_id = _load_exact_base(snapshot_directory)
    base_records = acquisition["records"]
    base_record_ids, references = _cohort_references(base_records)
    ranked_ids = sorted(
        base_record_ids,
        key=lambda item: (
            hashlib.sha256(item.encode("utf-8")).hexdigest(),
            item.casefold(),
            item,
        ),
    )
    selected_ids = ranked_ids[: min(limit, len(ranked_ids))]
    selected_references = [
        {"sourceRecordId": record_id, "concept": concept, "codeList": codelist_id}
        for record_id in selected_ids
        for concept, codelist_id in zip(CONCEPTS, references[record_id], strict=True)
    ]
    records_by_id = {
        str(record["sourceRecordId"]): dict(record) for record in base_records
    }
    receipts: list[dict[str, Any]] = []
    fetcher = transport or UrllibJsonTransport()
    last_live_request: list[float | None] = [None]

    def before_live_request() -> None:
        current = monotonic()
        previous = last_live_request[0]
        if previous is not None:
            remaining = float(request_interval_seconds) - (current - previous)
            if remaining > 0:
                sleep(remaining)
                current = monotonic()
        last_live_request[0] = current

    for record_id in selected_ids:
        projected_lists: list[dict[str, Any]] = []
        for concept, codelist_id in zip(CONCEPTS, references[record_id], strict=True):
            payload, receipt = _fetch_codelist(
                record_id,
                concept,
                codelist_id,
                cache_directory=resolved_cache,
                mode=mode,
                transport=fetcher,
                timeout_seconds=float(timeout_seconds),
                retries=retries,
                now=now,
                sleep=sleep,
                before_live_request=before_live_request,
            )
            projected_lists.append({"concept": concept, **payload})
            receipts.append(receipt)
        records_by_id[record_id]["nomisCodelists"] = projected_lists

    records = [records_by_id[record_id] for record_id in base_record_ids]
    provenance = json.loads(json.dumps(acquisition["provenance"]))
    base_record_set_sha256 = str(provenance["recordSetSha256"])
    base_snapshot_set_sha256 = str(provenance["snapshotSetSha256"])
    pages = list(provenance["pages"]) + receipts
    assurance = dict(provenance["assurance"])
    assurance.update(
        {
            "cacheLocationPublished": False,
            "codelistsFetched": True,
            "credentialsRequired": False,
            "metadataOnly": True,
            "observationsFetched": False,
            "projectedCacheOnly": True,
            "rawResponsesCached": False,
            "rawResponsesPublished": False,
        }
    )
    not_evidenced_count = sum(
        1
        for record_id in selected_ids
        for item in records_by_id[record_id]["nomisCodelists"]
        if item["status"] == "not-evidenced"
    )
    provenance.update(
        {
            "retrievalMode": f"codelist-enrichment:{mode}",
            "stopReason": "recordLimit" if len(selected_ids) < len(records) else "sourceExhausted",
            "recordCount": len(records),
            "recordSetSha256": sha256_json(records),
            "pageCount": len(pages),
            "pages": pages,
            "snapshotSetSha256": sha256_json(
                [
                    {"requestUrl": page["requestUrl"], "contentSha256": page["contentSha256"]}
                    for page in pages
                ]
            ),
            "replacement": {
                "schema": _REPLACEMENT_SCHEMA,
                "baseSnapshotId": snapshot_id,
                "baseRecordSetSha256": base_record_set_sha256,
                "baseSnapshotSetSha256": base_snapshot_set_sha256,
                "allowedRecordFields": ["nomisCodelists"],
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
                "selectedCodelistCount": len(selected_references),
                "notEvidencedCodelistCount": not_evidenced_count,
                "selectedCodelistReferenceSetSha256": sha256_json(selected_references),
                "concepts": list(CONCEPTS),
                "endpointTemplate": CODELIST_ENDPOINT_TEMPLATE,
            },
            "assurance": assurance,
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
    except (NomisCodelistError, OSError) as exc:
        parser.exit(1, f"Nomis codelist enrichment error: {exc}\n")
    run = envelope["provenance"]["enrichmentRun"]
    print(
        f"Acquired {run['selectedCodelistCount']} projected FREQ/TIME codelists "
        f"for {run['selectedCount']} of {run['cohortCount']} ranked Nomis records "
        f"into {arguments.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
