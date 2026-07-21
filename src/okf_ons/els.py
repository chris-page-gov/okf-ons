"""Project pinned Explore Local Statistics assets into public metadata records.

The Explore Local Statistics (ELS) application bundles a JSON-stat cube and a
separate metadata projection.  This module reads only the pinned metadata,
manifest, and redirect lookup.  It deliberately does not read data downloads,
spreadsheets, geometries, postcode assets, or the observation-bearing cube.

The projector is intentionally strict.  The input shapes and current published
denominators are part of the reviewed contract; an upstream change must be
assessed before it can enter a public OKF snapshot.
"""

from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlsplit

ELS_SOURCE_ID = "ons-explore-local-statistics"
ELS_PUBLISHED_INDICATOR_COUNT = 108
ELS_MANIFEST_EXCLUSION_COUNT = 12
ELS_OPERATOR = {
    "name": "Office for National Statistics",
    "url": "https://www.ons.gov.uk/",
    "role": "service-operator-and-curator",
}
ELS_APP_ROOT = "https://www.ons.gov.uk/explore-local-statistics"
ELS_METADATA_ENDPOINT = f"{ELS_APP_ROOT}/api/v1/metadata/indicators"
ELS_UPSTREAM_REPOSITORY = "https://github.com/ONSdigital/explore-local-statistics-app"

_METADATA_PATH = Path("src/lib/data/json-stat-metadata.json")
_MANIFEST_PATH = Path("scripts/config/manifest_metadata.csv")
_ALIASES_PATH = Path("src/lib/data/indicator_redirects.json")
_INPUT_PATHS = {
    "indicatorMetadata": _METADATA_PATH,
    "indicatorManifest": _MANIFEST_PATH,
    "indicatorAliases": _ALIASES_PATH,
}
_MAX_INPUT_BYTES = {
    "indicatorMetadata": 10_000_000,
    "indicatorManifest": 1_000_000,
    "indicatorAliases": 1_000_000,
}

_COLLECTION_KEYS = {"version", "class", "label", "note", "updated", "link"}
_COLLECTION_LINK_KEYS = {"item"}
_ITEM_KEYS = {
    "version",
    "class",
    "label",
    "note",
    "source",
    "updated",
    "extension",
    "id",
    "size",
    "role",
    "dimension",
    "value",
}
_EXTENSION_KEYS = {
    "canBeNegative",
    "code",
    "confidenceIntervals",
    "dataModified",
    "dataset",
    "decimalPlaces",
    "description",
    "experimentalStatistic",
    "frequency",
    "geography",
    "hasTimeseries",
    "isMultivariate",
    "measure",
    "metadataModified",
    "periodDomain",
    "periodFormat",
    "prefix",
    "slug",
    "source",
    "standardised",
    "subText",
    "subTopic",
    "subtitle",
    "suffix",
    "topic",
    "unit",
    "valueDomain",
    "zeroBaseline",
}
_GEOGRAPHY_KEYS = {"countries", "levels", "types", "year", "initialLevel"}
_DIMENSION_KEYS = {"label", "category"}
_CATEGORY_KEYS = {"index", "label"}
_PRODUCER_KEYS = {"name", "href", "date"}
_ALLOWED_DIMENSION_IDS = {"areacd", "period", "measure", "sex", "age"}
_MANIFEST_FIELDS = ["slug", "topic", "subTopic", "dataset", "code", "include"]
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{40}(?:[0-9a-fA-F]{24})?$")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
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
_SECRET_QUERY_KEYS = {
    "access_token",
    "api_key",
    "apikey",
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
_FORBIDDEN_PUBLIC_KEYS = {
    "accesstoken",
    "apikey",
    "arcs",
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
    "status",
    "token",
    "topology",
    "value",
    "valuedomain",
    "values",
    "xapikey",
}
_PUBLIC_RECORD_KEYS = {
    "aliases",
    "caveats",
    "classificationAssertions",
    "dataModified",
    "derivation",
    "derivedMetadataFlags",
    "description",
    "dimensionOrder",
    "dimensions",
    "geography",
    "indicatorCode",
    "internalDatasetId",
    "keywords",
    "lastUpdated",
    "lifecycleState",
    "links",
    "measure",
    "metadataModified",
    "operator",
    "periodFormat",
    "presentation",
    "producers",
    "recordKind",
    "releaseFrequency",
    "sourceId",
    "sourceRecordId",
    "subtitle",
    "taxonomy",
    "timeCoverage",
    "title",
    "unitOfMeasure",
}
_PUBLIC_PROVENANCE_KEYS = {
    "aliasProjection",
    "assurance",
    "complete",
    "coverageComplete",
    "explainedExclusionCount",
    "explainedExclusions",
    "includedManifestCount",
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
    "sourceManifestCount",
    "stopReason",
    "submodule",
    "unrepresentedCount",
    "upstreamRecordsSeen",
}

# The pinned source contains six redirects to sex-specific indicators that are
# deliberately absent from the published catalogue.  They are excluded from
# projected aliases.  Any different missing target fails closed.
_KNOWN_UNPUBLISHED_ALIASES = {
    "percentage-of-the-population-aged-0-to-15-female": (
        "percentage-population-aged-0-to-15-female"
    ),
    "percentage-of-the-population-aged-0-to-15-male": (
        "percentage-population-aged-0-to-15-male"
    ),
    "percentage-of-the-population-aged-16-to-64-female": (
        "percentage-population-aged-16-to-64-female"
    ),
    "percentage-of-the-population-aged-16-to-64-male": (
        "percentage-population-aged-16-to-64-male"
    ),
    "percentage-of-the-population-aged-64-plus-female": (
        "percentage-population-aged-65-female"
    ),
    "percentage-of-the-population-aged-65-plus-male": (
        "percentage-population-aged-65-male"
    ),
}


class ELSProjectionError(ValueError):
    """Raised when pinned ELS inputs cannot be safely projected."""


class _GitInspectionError(ELSProjectionError):
    """Raised only when Git metadata cannot be inspected."""


def canonical_json(value: Any) -> str:
    """Return deterministic public JSON text."""

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


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        # Match the canonical digest convention used by the HTTP acquisition
        # adapters.  The public JSON remains UTF-8; escaping here affects only
        # the digest input and gives every source lane one validation rule.
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_bytes(_canonical_bytes(value))


def _normalised_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def _plain_text(value: Any, *, limit: int = 10_000, required: bool = False) -> str:
    text = html.unescape(str(value or ""))
    text = _HTML_TAG_RE.sub(" ", text)
    text = _SPACE_RE.sub(" ", text).strip()
    if required and not text:
        raise ELSProjectionError("Required ELS metadata text is empty")
    if len(text) > limit:
        raise ELSProjectionError(f"ELS metadata text exceeds the {limit}-character limit")
    if _LOCAL_PATH_RE.search(text):
        raise ELSProjectionError("ELS metadata contains a machine-local path")
    return text


def _required_text(value: Mapping[str, Any], key: str, *, limit: int = 2_000) -> str:
    if key not in value:
        raise ELSProjectionError(f"ELS metadata is missing required field {key!r}")
    return _plain_text(value[key], limit=limit, required=True)


def _optional_text(value: Mapping[str, Any], key: str, *, limit: int = 2_000) -> str:
    return _plain_text(value.get(key), limit=limit)


def _require_bool(value: Mapping[str, Any], key: str) -> bool:
    result = value.get(key)
    if not isinstance(result, bool):
        raise ELSProjectionError(f"ELS metadata field {key!r} must be boolean")
    return result


def _require_int(value: Mapping[str, Any], key: str) -> int:
    result = value.get(key)
    if isinstance(result, bool) or not isinstance(result, int):
        raise ELSProjectionError(f"ELS metadata field {key!r} must be an integer")
    return result


def _validate_exact_keys(
    value: Mapping[str, Any],
    allowed: set[str],
    label: str,
    *,
    required: set[str] | None = None,
) -> None:
    keys = set(value)
    unknown = sorted(keys - allowed)
    if unknown:
        raise ELSProjectionError(f"{label} has unreviewed field(s): {', '.join(unknown)}")
    missing = sorted((required or allowed) - keys)
    if missing:
        raise ELSProjectionError(f"{label} is missing field(s): {', '.join(missing)}")


def _safe_https_url(value: Any, *, label: str) -> str:
    url = _plain_text(value, limit=4_000, required=True)
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ELSProjectionError(f"{label} must be a credential-free HTTPS URL")
    query_keys = {key.casefold() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}
    if query_keys & _SECRET_QUERY_KEYS:
        raise ELSProjectionError(f"{label} contains a credential-like query parameter")
    return url


def _safe_slug(value: Any, *, label: str) -> str:
    slug = _plain_text(value, limit=300, required=True)
    if not _SLUG_RE.fullmatch(slug):
        raise ELSProjectionError(f"{label} is not a safe stable slug: {slug!r}")
    return slug


def _safe_input_path(root: Path, relative: Path) -> Path:
    resolved_root = root.resolve(strict=True)
    path = (resolved_root / relative).resolve(strict=True)
    if not path.is_relative_to(resolved_root) or not path.is_file():
        raise ELSProjectionError(f"ELS input is not a regular file under the submodule: {relative}")
    return path


def _read_inputs(root: Path) -> tuple[dict[str, bytes], dict[str, dict[str, Any]]]:
    payloads: dict[str, bytes] = {}
    receipts: dict[str, dict[str, Any]] = {}
    for key, relative in _INPUT_PATHS.items():
        path = _safe_input_path(root, relative)
        payload = path.read_bytes()
        if len(payload) > _MAX_INPUT_BYTES[key]:
            raise ELSProjectionError(f"ELS input {relative} exceeds the reviewed size limit")
        payloads[key] = payload
        receipts[key] = {
            "relativePath": relative.as_posix(),
            "contentSha256": _sha256_bytes(payload),
        }
    return payloads, receipts


def _read_json_object(payload: bytes, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ELSProjectionError(f"Unable to parse {label} as JSON") from exc
    if not isinstance(value, dict):
        raise ELSProjectionError(f"{label} must contain a JSON object")
    return value


def _read_manifest(payload: bytes) -> list[dict[str, Any]]:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ELSProjectionError("Unable to decode the ELS indicator manifest") from exc
    reader = csv.DictReader(text.splitlines())
    if reader.fieldnames != _MANIFEST_FIELDS:
        raise ELSProjectionError(
            "ELS manifest fields changed; expected " + ", ".join(_MANIFEST_FIELDS)
        )
    rows: list[dict[str, Any]] = []
    for line_number, raw in enumerate(reader, start=2):
        if None in raw:
            raise ELSProjectionError(f"ELS manifest row {line_number} has extra columns")
        include_text = _plain_text(raw.get("include"), limit=20, required=True).casefold()
        if include_text not in {"true", "false"}:
            raise ELSProjectionError(f"ELS manifest row {line_number} has invalid include value")
        row = {
            "slug": _plain_text(raw.get("slug"), limit=300),
            "topic": _plain_text(raw.get("topic"), limit=300),
            "subTopic": _plain_text(raw.get("subTopic"), limit=300),
            "dataset": _plain_text(raw.get("dataset"), limit=500, required=True),
            "code": _plain_text(raw.get("code"), limit=1_000, required=True),
            "include": include_text == "true",
            "manifestRow": line_number,
        }
        if row["include"]:
            _safe_slug(row["slug"], label=f"manifest row {line_number} slug")
            if not row["topic"] or not row["subTopic"]:
                raise ELSProjectionError(
                    f"Included ELS manifest row {line_number} lacks taxonomy metadata"
                )
        elif row["slug"] or row["topic"] or row["subTopic"]:
            raise ELSProjectionError(
                f"Excluded ELS manifest row {line_number} has unexpected public taxonomy"
            )
        rows.append(row)
    return rows


def _run_git(root: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        raise _GitInspectionError("Unable to inspect the ELS submodule Git revision") from exc
    return completed.stdout.strip()


def _normalise_commit(value: Any) -> str:
    commit = _plain_text(value, limit=100, required=True).lower()
    if not _COMMIT_RE.fullmatch(commit):
        raise ELSProjectionError("ELS submodule commit must be a full 40- or 64-character hash")
    return commit


def _normalise_timestamp(value: Any, *, label: str) -> str:
    text = _plain_text(value, limit=100, required=True)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ELSProjectionError(f"{label} must be ISO 8601") from exc
    if parsed.tzinfo is None:
        raise ELSProjectionError(f"{label} must include a timezone")
    utc = parsed.astimezone(UTC)
    return utc.isoformat(timespec="seconds").replace("+00:00", "Z")


def resolve_submodule_revision(
    root: Path,
    *,
    supplied_commit: str | None = None,
    supplied_commit_as_of: str | None = None,
    supplied_timestamp: str | None = None,
    collection_updated: str | None = None,
) -> dict[str, Any]:
    """Resolve and, when possible, verify the pinned submodule revision."""

    # ``supplied_timestamp`` is retained as a fail-closed compatibility alias
    # for callers of this low-level helper.  It used to be ambiguous and was
    # incorrectly reused as both commit and retrieval time.  New callers must
    # use ``supplied_commit_as_of``; project_els_snapshot handles retrieval time
    # independently.  Collection metadata is intentionally not accepted as
    # evidence of when a Git commit was made.
    if supplied_timestamp:
        if supplied_commit_as_of:
            raise ELSProjectionError(
                "Supply only one ELS commit-as-of timestamp argument"
            )
        supplied_commit_as_of = supplied_timestamp
    del collection_updated

    commit = _normalise_commit(supplied_commit) if supplied_commit else ""
    discovered_commit = ""
    discovered_commit_as_of = ""
    git_available = True
    try:
        discovered_commit = _normalise_commit(_run_git(root, "rev-parse", "--verify", "HEAD"))
    except _GitInspectionError:
        if not supplied_commit:
            raise
        # A copied fixture may have no Git metadata.  Its commit identity and
        # commit time must therefore both be supplied as explicit evidence.
        git_available = False
    else:
        dirty = _run_git(
            root,
            "status",
            "--porcelain",
            "--untracked-files=no",
            "--",
            *[path.as_posix() for path in _INPUT_PATHS.values()],
        )
        if dirty:
            raise ELSProjectionError("Pinned ELS projection inputs have tracked Git modifications")
        if commit and commit != discovered_commit:
            raise ELSProjectionError("Supplied ELS commit does not match the submodule HEAD")
        commit = commit or discovered_commit
        discovered_commit_as_of = _normalise_timestamp(
            _run_git(root, "show", "-s", "--format=%cI", commit),
            label="ELS Git commit time",
        )

    if not commit:
        raise ELSProjectionError("No pinned ELS submodule commit is available")

    explicit_commit_as_of = (
        _normalise_timestamp(
            supplied_commit_as_of,
            label="ELS commit-as-of time",
        )
        if supplied_commit_as_of
        else ""
    )
    if discovered_commit_as_of:
        if explicit_commit_as_of and explicit_commit_as_of != discovered_commit_as_of:
            raise ELSProjectionError(
                "Supplied ELS commit-as-of time does not match the verified Git commit time"
            )
        commit_as_of = discovered_commit_as_of
        commit_as_of_resolution = (
            "supplied-and-git-verified"
            if explicit_commit_as_of
            else "discovered-from-git"
        )
        commit_as_of_verified = True
    elif explicit_commit_as_of:
        commit_as_of = explicit_commit_as_of
        commit_as_of_resolution = "supplied-explicit-evidence"
        commit_as_of_verified = False
    else:
        raise ELSProjectionError(
            "A Git-less ELS checkout requires explicit commit-as-of evidence"
        )

    return {
        "commit": commit,
        "commitResolution": (
            "supplied-and-verified"
            if supplied_commit and git_available
            else "discovered"
            if git_available
            else "supplied"
        ),
        "commitAsOf": commit_as_of,
        "commitAsOfResolution": commit_as_of_resolution,
        "commitAsOfVerified": commit_as_of_verified,
    }


def _validate_metadata_collection(value: Mapping[str, Any]) -> list[dict[str, Any]]:
    _validate_exact_keys(value, _COLLECTION_KEYS, "ELS metadata collection")
    if value.get("class") != "collection" or str(value.get("version")) != "2.0":
        raise ELSProjectionError("ELS metadata is not the reviewed JSON-stat 2.0 collection")
    link = value.get("link")
    if not isinstance(link, Mapping):
        raise ELSProjectionError("ELS metadata collection link must be an object")
    _validate_exact_keys(link, _COLLECTION_LINK_KEYS, "ELS metadata collection link")
    items = link.get("item")
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise ELSProjectionError("ELS metadata collection items must be objects")
    if len(items) != ELS_PUBLISHED_INDICATOR_COUNT:
        raise ELSProjectionError(
            "ELS published indicator count changed: "
            f"expected {ELS_PUBLISHED_INDICATOR_COUNT}, found {len(items)}"
        )
    return items


def _validate_raw_item(item: Mapping[str, Any], *, index: int) -> None:
    _validate_exact_keys(item, _ITEM_KEYS, f"ELS indicator item {index}")
    if item.get("class") != "dataset" or str(item.get("version")) != "2.0":
        raise ELSProjectionError(f"ELS indicator item {index} is not a JSON-stat 2.0 dataset")
    raw_values = item.get("value")
    if raw_values != []:
        raise ELSProjectionError(
            f"ELS metadata item {index} contains a non-empty observation value payload"
        )
    if "status" in item:
        raise ELSProjectionError(f"ELS metadata item {index} contains observation statuses")
    extension = item.get("extension")
    if not isinstance(extension, Mapping):
        raise ELSProjectionError(f"ELS indicator item {index} has no metadata extension")
    _validate_exact_keys(extension, _EXTENSION_KEYS, f"ELS indicator extension {index}")
    geography = extension.get("geography")
    if not isinstance(geography, Mapping):
        raise ELSProjectionError(f"ELS indicator item {index} has no geography metadata")
    _validate_exact_keys(geography, _GEOGRAPHY_KEYS, f"ELS indicator geography {index}")


def _string_list(value: Any, *, label: str, pattern: re.Pattern[str] | None = None) -> list[str]:
    if not isinstance(value, list):
        raise ELSProjectionError(f"{label} must be a list")
    output: list[str] = []
    for raw in value:
        text = _plain_text(raw, limit=500, required=True)
        if pattern and not pattern.fullmatch(text):
            raise ELSProjectionError(f"{label} contains invalid value {text!r}")
        output.append(text)
    if len(output) != len(set(output)):
        raise ELSProjectionError(f"{label} contains duplicate values")
    return output


def _project_producers(value: Any, *, indicator: str) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise ELSProjectionError(f"ELS indicator {indicator!r} has no source attribution")
    producers: list[dict[str, str]] = []
    for source_index, raw in enumerate(value):
        if not isinstance(raw, Mapping):
            raise ELSProjectionError(f"ELS indicator {indicator!r} has malformed producer metadata")
        _validate_exact_keys(
            raw,
            _PRODUCER_KEYS,
            f"ELS indicator {indicator!r} producer {source_index}",
        )
        producers.append(
            {
                "name": _required_text(raw, "name", limit=500),
                "url": _safe_https_url(
                    raw.get("href"),
                    label=f"ELS indicator {indicator!r} producer URL",
                ),
                "publicationDate": _required_text(raw, "date", limit=100),
                "role": "upstream-producer-or-source-attribution",
            }
        )
    return producers


def _project_geography(value: Mapping[str, Any], *, indicator: str) -> dict[str, Any]:
    countries = _string_list(
        value.get("countries"),
        label=f"ELS indicator {indicator!r} geography countries",
        pattern=re.compile(r"^[ENSW]$"),
    )
    levels = _string_list(
        value.get("levels"),
        label=f"ELS indicator {indicator!r} geography levels",
        pattern=_SLUG_RE,
    )
    types = _string_list(
        value.get("types"),
        label=f"ELS indicator {indicator!r} geography types",
        pattern=re.compile(r"^[EKNSW]\d{2}$"),
    )
    year = _require_int(value, "year")
    if year < 1900 or year > 2200:
        raise ELSProjectionError(f"ELS indicator {indicator!r} has invalid geography vintage")
    initial_level = _required_text(value, "initialLevel", limit=100)
    if initial_level not in levels:
        raise ELSProjectionError(
            f"ELS indicator {indicator!r} initial geography level is not in its level list"
        )
    return {
        "countries": countries,
        "levels": levels,
        "codeTypes": types,
        "vintage": year,
        "initialLevel": initial_level,
        "derivationMode": "inferred-from-area-code-coverage",
    }


def _dimension_role(raw_role: Mapping[str, Any], dimension_id: str) -> str:
    roles: list[str] = []
    for role, dimension_ids in raw_role.items():
        if not isinstance(dimension_ids, list) or not all(
            isinstance(item, str) for item in dimension_ids
        ):
            raise ELSProjectionError("ELS JSON-stat dimension roles are malformed")
        if dimension_id in dimension_ids:
            roles.append(_plain_text(role, limit=100, required=True))
    if len(roles) > 1:
        raise ELSProjectionError(f"ELS dimension {dimension_id!r} has multiple semantic roles")
    if roles:
        return roles[0]
    return "measure" if dimension_id == "measure" else "dimension"


def _project_dimensions(item: Mapping[str, Any], *, indicator: str) -> list[dict[str, Any]]:
    ids = item.get("id")
    sizes = item.get("size")
    raw_dimensions = item.get("dimension")
    raw_role = item.get("role")
    if (
        not isinstance(ids, list)
        or not all(isinstance(value, str) for value in ids)
        or not isinstance(sizes, list)
        or not all(isinstance(value, int) and not isinstance(value, bool) for value in sizes)
        or not isinstance(raw_dimensions, Mapping)
        or not isinstance(raw_role, Mapping)
    ):
        raise ELSProjectionError(f"ELS indicator {indicator!r} has malformed dimensions")
    if len(ids) != len(sizes) or len(ids) != len(set(ids)):
        raise ELSProjectionError(f"ELS indicator {indicator!r} has inconsistent dimension order")
    unknown_ids = sorted(set(ids) - _ALLOWED_DIMENSION_IDS)
    if unknown_ids:
        raise ELSProjectionError(
            f"ELS indicator {indicator!r} has unreviewed dimension(s): {', '.join(unknown_ids)}"
        )
    if set(raw_dimensions) != set(ids):
        raise ELSProjectionError(
            f"ELS indicator {indicator!r} dimension lookup does not match id order"
        )

    dimensions: list[dict[str, Any]] = []
    for order, (dimension_id, size) in enumerate(zip(ids, sizes, strict=True)):
        raw = raw_dimensions[dimension_id]
        if not isinstance(raw, Mapping):
            raise ELSProjectionError(f"ELS dimension {dimension_id!r} is not an object")
        _validate_exact_keys(raw, _DIMENSION_KEYS, f"ELS dimension {dimension_id!r}")
        category = raw.get("category")
        if not isinstance(category, Mapping):
            raise ELSProjectionError(f"ELS dimension {dimension_id!r} has no category object")
        _validate_exact_keys(
            category,
            _CATEGORY_KEYS,
            f"ELS dimension {dimension_id!r} category",
            required={"index"},
        )
        index_lookup = category.get("index")
        label_lookup = category.get("label", {})
        if not isinstance(index_lookup, Mapping) or not isinstance(label_lookup, Mapping):
            raise ELSProjectionError(f"ELS dimension {dimension_id!r} category lookup is malformed")
        ordered = sorted(index_lookup.items(), key=lambda pair: pair[1])
        expected_positions = list(range(len(ordered)))
        if [position for _, position in ordered] != expected_positions or size != len(ordered):
            raise ELSProjectionError(
                f"ELS dimension {dimension_id!r} category indexes are inconsistent"
            )
        if set(label_lookup) - set(index_lookup):
            raise ELSProjectionError(
                f"ELS dimension {dimension_id!r} has labels for unknown categories"
            )

        categories: list[dict[str, str]] = []
        for category_id, _ in ordered:
            category_text = _plain_text(category_id, limit=500, required=True)
            projected_category = {"id": category_text}
            if category_id in label_lookup:
                projected_category["label"] = _plain_text(
                    label_lookup[category_id],
                    limit=1_000,
                    required=True,
                )
            categories.append(projected_category)
        dimension = {
            "id": dimension_id,
            "label": _required_text(raw, "label", limit=500),
            "order": order,
            "role": _dimension_role(raw_role, dimension_id),
            "categoryCount": len(categories),
            "categoryProjection": (
                "count-only" if dimension_id in {"areacd", "period"} else "identifiers-and-labels"
            ),
        }
        # Area and period members are high-volume observation-structure metadata.
        # Their declared coverage is projected separately; retaining them here
        # would make individual discovery records exceed common client limits.
        if dimension_id not in {"areacd", "period"}:
            dimension["categories"] = categories
        dimensions.append(dimension)
    return dimensions


def _project_aliases(
    raw_aliases: Mapping[str, Any], published_slugs: set[str]
) -> tuple[dict[str, list[str]], dict[str, Any]]:
    aliases_by_target = {slug: [] for slug in published_slugs}
    missing: dict[str, str] = {}
    for raw_alias, raw_target in raw_aliases.items():
        alias = _safe_slug(raw_alias, label="ELS historical indicator alias")
        target = _safe_slug(raw_target, label=f"ELS alias {alias!r} target")
        if alias == target:
            raise ELSProjectionError(f"ELS alias {alias!r} is a no-op")
        if alias in published_slugs:
            raise ELSProjectionError(f"ELS alias {alias!r} shadows a published indicator")
        if target not in published_slugs:
            missing[alias] = target
            continue
        aliases_by_target[target].append(alias)

    if missing != _KNOWN_UNPUBLISHED_ALIASES:
        unexpected = sorted(set(missing.items()) ^ set(_KNOWN_UNPUBLISHED_ALIASES.items()))
        raise ELSProjectionError(
            "ELS alias targets changed or include an unexplained missing target: "
            + repr(unexpected)
        )
    for aliases in aliases_by_target.values():
        aliases.sort()
    accepted_count = sum(len(aliases) for aliases in aliases_by_target.values())
    details = {
        "inputCount": len(raw_aliases),
        "acceptedCount": accepted_count,
        "excludedCount": len(missing),
        "excluded": [
            {
                "alias": alias,
                "target": target,
                "reason": "known-target-not-published-by-pinned-catalogue",
            }
            for alias, target in sorted(missing.items())
        ],
    }
    return aliases_by_target, details


def _project_record(
    item: Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    aliases: Sequence[str],
    commit: str,
    order: int,
) -> dict[str, Any]:
    extension = item["extension"]
    assert isinstance(extension, Mapping)
    slug = _safe_slug(extension.get("slug"), label="ELS indicator slug")
    title = _required_text(item, "label", limit=1_000)
    period_domain = extension.get("periodDomain")
    if (
        not isinstance(period_domain, list)
        or len(period_domain) != 2
        or not all(isinstance(value, str) and value for value in period_domain)
    ):
        raise ELSProjectionError(f"ELS indicator {slug!r} has invalid period coverage")
    caveats = item.get("note")
    if not isinstance(caveats, list) or not all(isinstance(value, str) for value in caveats):
        raise ELSProjectionError(f"ELS indicator {slug!r} caveats must be a string list")
    decimal_places = _require_int(extension, "decimalPlaces")
    if decimal_places < 0 or decimal_places > 12:
        raise ELSProjectionError(f"ELS indicator {slug!r} has invalid decimal places")

    dimensions = _project_dimensions(item, indicator=slug)
    dimension_ids = [dimension["id"] for dimension in dimensions]
    producers = _project_producers(extension.get("source"), indicator=slug)
    topic = _required_text(extension, "topic", limit=300)
    subtopic = _required_text(extension, "subTopic", limit=300)
    source_dataset = _required_text(extension, "dataset", limit=500)
    indicator_code = _required_text(extension, "code", limit=1_000)
    record = {
        "sourceId": ELS_SOURCE_ID,
        "sourceRecordId": slug,
        "recordKind": "curated-local-indicator",
        "title": title,
        "description": _required_text(extension, "description", limit=10_000),
        "subtitle": _required_text(extension, "subtitle", limit=2_000),
        "caveats": [_plain_text(value, limit=10_000, required=True) for value in caveats],
        "lifecycleState": "published",
        "keywords": list(dict.fromkeys([topic, subtopic])),
        "taxonomy": {
            "scheme": "ONS Explore Local Statistics",
            "topic": topic,
            "subTopic": subtopic,
            "manifestOrder": order,
        },
        "internalDatasetId": source_dataset,
        "indicatorCode": indicator_code,
        "producers": producers,
        "operator": dict(ELS_OPERATOR),
        "lastUpdated": _required_text(item, "updated", limit=100),
        "dataModified": _required_text(extension, "dataModified", limit=100),
        "metadataModified": _required_text(extension, "metadataModified", limit=100),
        "releaseFrequency": _required_text(extension, "frequency", limit=100),
        "periodFormat": _required_text(extension, "periodFormat", limit=100),
        "timeCoverage": {
            "start": _plain_text(period_domain[0], limit=100, required=True),
            "end": _plain_text(period_domain[1], limit=100, required=True),
        },
        "measure": _required_text(extension, "measure", limit=500),
        "unitOfMeasure": _required_text(extension, "unit", limit=500),
        "geography": _project_geography(extension["geography"], indicator=slug),
        "dimensions": dimensions,
        "dimensionOrder": dimension_ids,
        "classificationAssertions": {
            "experimentalStatistic": _require_bool(extension, "experimentalStatistic"),
            "standardised": _require_bool(extension, "standardised"),
            "assertedBy": "ONS Explore Local Statistics metadata",
            "certificationClaimed": False,
        },
        "presentation": {
            "prefix": _optional_text(extension, "prefix", limit=100),
            "suffix": _optional_text(extension, "suffix", limit=100),
            "subText": _optional_text(extension, "subText", limit=500),
            "decimalPlaces": decimal_places,
        },
        "derivedMetadataFlags": {
            "mode": "inferred-from-observation-structure-without-publishing-observations",
            "hasTimeseries": _require_bool(extension, "hasTimeseries"),
            "isMultivariate": _require_bool(extension, "isMultivariate"),
            "confidenceIntervals": _require_bool(extension, "confidenceIntervals"),
        },
        "derivation": {
            "mode": "application-curated-extract",
            "operator": ELS_OPERATOR["name"],
            "internalDatasetId": source_dataset,
            "indicatorCode": indicator_code,
            "sourceEditionVersionAvailable": False,
            "submoduleCommit": commit,
        },
        "aliases": list(aliases),
        "links": {
            "self": f"{ELS_APP_ROOT}/indicators/{slug}",
            "metadata": f"{ELS_METADATA_ENDPOINT}/{slug}",
        },
    }

    comparisons = {
        "slug": slug,
        "topic": topic,
        "subTopic": subtopic,
        "dataset": source_dataset,
        "code": indicator_code,
    }
    for key, actual in comparisons.items():
        if actual != manifest[key]:
            raise ELSProjectionError(
                f"ELS manifest and metadata disagree for {slug!r} field {key!r}: "
                f"{manifest[key]!r} != {actual!r}"
            )
    return record


def _assert_public_safe(value: Any, *, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalised = _normalised_key(key)
            if normalised in _FORBIDDEN_PUBLIC_KEYS:
                raise ELSProjectionError(f"Unsafe field {key!r} survived projection at {path}")
            _assert_public_safe(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_public_safe(child, path=f"{path}[{index}]")
    elif isinstance(value, bytes):
        raise ELSProjectionError(f"Binary content survived projection at {path}")
    elif isinstance(value, float) and not (float("-inf") < value < float("inf")):
        raise ELSProjectionError(f"Non-finite number survived projection at {path}")
    elif isinstance(value, str):
        if _LOCAL_PATH_RE.search(value):
            raise ELSProjectionError(f"Machine-local path survived projection at {path}")
        if any(pattern.search(value) for pattern in _SECRET_VALUE_PATTERNS):
            raise ELSProjectionError(f"Credential-like value survived projection at {path}")


def _projected_mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ELSProjectionError(f"{label} must be an object")
    return value


def _projected_list(value: Any, *, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ELSProjectionError(f"{label} must be an array")
    return value


def _validated_sha256(value: Any, *, label: str) -> str:
    digest = _plain_text(value, limit=64, required=True).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ELSProjectionError(f"{label} must be a SHA-256 digest")
    return digest


def _validate_projected_record(record: Any, *, index: int) -> str:
    row = _projected_mapping(record, label=f"ELS projected record {index}")
    _validate_exact_keys(row, _PUBLIC_RECORD_KEYS, f"ELS projected record {index}")
    if (
        row["sourceId"] != ELS_SOURCE_ID
        or row["recordKind"] != "curated-local-indicator"
    ):
        raise ELSProjectionError(f"ELS projected record {index} has an invalid source identity")
    slug = _safe_slug(row["sourceRecordId"], label=f"ELS projected record {index} identity")

    nested_shapes = {
        "classificationAssertions": {
            "assertedBy",
            "certificationClaimed",
            "experimentalStatistic",
            "standardised",
        },
        "derivation": {
            "indicatorCode",
            "internalDatasetId",
            "mode",
            "operator",
            "sourceEditionVersionAvailable",
            "submoduleCommit",
        },
        "derivedMetadataFlags": {
            "confidenceIntervals",
            "hasTimeseries",
            "isMultivariate",
            "mode",
        },
        "geography": {
            "codeTypes",
            "countries",
            "derivationMode",
            "initialLevel",
            "levels",
            "vintage",
        },
        "links": {"metadata", "self"},
        "operator": {"name", "role", "url"},
        "presentation": {"decimalPlaces", "prefix", "subText", "suffix"},
        "taxonomy": {"manifestOrder", "scheme", "subTopic", "topic"},
        "timeCoverage": {"end", "start"},
    }
    for key, expected in nested_shapes.items():
        child = _projected_mapping(row[key], label=f"ELS projected record {index}.{key}")
        _validate_exact_keys(child, expected, f"ELS projected record {index}.{key}")

    links = _projected_mapping(row["links"], label=f"ELS projected record {index}.links")
    _safe_https_url(links["self"], label=f"ELS projected record {index} self URL")
    _safe_https_url(links["metadata"], label=f"ELS projected record {index} metadata URL")
    operator = _projected_mapping(
        row["operator"], label=f"ELS projected record {index}.operator"
    )
    _safe_https_url(operator["url"], label=f"ELS projected record {index} operator URL")

    producers = _projected_list(row["producers"], label=f"ELS projected record {index}.producers")
    for producer_index, producer in enumerate(producers):
        party = _projected_mapping(
            producer,
            label=f"ELS projected record {index}.producers[{producer_index}]",
        )
        _validate_exact_keys(
            party,
            {"name", "publicationDate", "role", "url"},
            f"ELS projected record {index}.producers[{producer_index}]",
        )
        _safe_https_url(
            party["url"],
            label=f"ELS projected record {index} producer {producer_index} URL",
        )

    dimensions = _projected_list(
        row["dimensions"], label=f"ELS projected record {index}.dimensions"
    )
    for dimension_index, dimension in enumerate(dimensions):
        item = _projected_mapping(
            dimension,
            label=f"ELS projected record {index}.dimensions[{dimension_index}]",
        )
        dimension_keys = {
            "categories",
            "categoryCount",
            "categoryProjection",
            "id",
            "label",
            "order",
            "role",
        }
        _validate_exact_keys(
            item,
            dimension_keys,
            f"ELS projected record {index}.dimensions[{dimension_index}]",
            required=dimension_keys - {"categories"},
        )
        if "categories" in item:
            categories = _projected_list(
                item["categories"],
                label=(
                    f"ELS projected record {index}.dimensions[{dimension_index}].categories"
                ),
            )
            for category_index, category in enumerate(categories):
                category_row = _projected_mapping(
                    category,
                    label=(
                        f"ELS projected record {index}.dimensions[{dimension_index}]"
                        f".categories[{category_index}]"
                    ),
                )
                _validate_exact_keys(
                    category_row,
                    {"id", "label"},
                    (
                        f"ELS projected record {index}.dimensions[{dimension_index}]"
                        f".categories[{category_index}]"
                    ),
                )
    return slug


def validate_els_acquisition_envelope(value: Any) -> None:
    """Fail closed unless *value* is a safe, digest-consistent ELS projection."""

    envelope = _projected_mapping(value, label="ELS projected acquisition")
    _validate_exact_keys(
        envelope,
        {"provenance", "records", "schemaVersion"},
        "ELS projected acquisition",
    )
    if envelope["schemaVersion"] != "okf-ons.source-acquisition.v1":
        raise ELSProjectionError("Unsupported ELS projected acquisition schema")
    _assert_public_safe(envelope)

    records = _projected_list(envelope["records"], label="ELS projected records")
    identities = [
        _validate_projected_record(record, index=index)
        for index, record in enumerate(records)
    ]
    if len(records) != ELS_PUBLISHED_INDICATOR_COUNT:
        raise ELSProjectionError("ELS projected acquisition does not close its denominator")
    if len(identities) != len(set(identities)):
        raise ELSProjectionError("ELS projected acquisition contains duplicate record identities")

    provenance = _projected_mapping(envelope["provenance"], label="ELS provenance")
    _validate_exact_keys(
        provenance,
        _PUBLIC_PROVENANCE_KEYS | {"acquisition"},
        "ELS provenance",
        required=_PUBLIC_PROVENANCE_KEYS,
    )
    expected_counts = {
        "explainedExclusionCount": ELS_MANIFEST_EXCLUSION_COUNT,
        "includedManifestCount": ELS_PUBLISHED_INDICATOR_COUNT,
        "normalisationDroppedCount": 0,
        "normalisedRecordsSeen": ELS_PUBLISHED_INDICATOR_COUNT,
        "recordCount": ELS_PUBLISHED_INDICATOR_COUNT,
        "reportedTotal": ELS_PUBLISHED_INDICATOR_COUNT,
        "sourceManifestCount": ELS_PUBLISHED_INDICATOR_COUNT + ELS_MANIFEST_EXCLUSION_COUNT,
        "unrepresentedCount": 0,
        "upstreamRecordsSeen": ELS_PUBLISHED_INDICATOR_COUNT,
    }
    for key, expected in expected_counts.items():
        if provenance[key] != expected:
            raise ELSProjectionError(f"ELS provenance {key} does not match the reviewed contract")
    if (
        provenance["complete"] is not True
        or provenance["coverageComplete"] is not True
        or provenance["retrievalMode"] != "pinned-submodule-projection"
        or provenance["stopReason"] != "sourceExhausted"
    ):
        raise ELSProjectionError("ELS provenance does not assert a complete pinned projection")

    source = _projected_mapping(provenance["source"], label="ELS provenance source")
    source_keys = {
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
    _validate_exact_keys(source, source_keys, "ELS provenance source")
    if (
        source["id"] != ELS_SOURCE_ID
        or source["adapter"] != "els-metadata-projection"
        or source["endpoint"] != ELS_METADATA_ENDPOINT
    ):
        raise ELSProjectionError("ELS provenance source identity does not match the projector")
    _safe_https_url(source["endpoint"], label="ELS provenance endpoint")
    publisher = _projected_mapping(source["publisher"], label="ELS provenance publisher")
    _validate_exact_keys(publisher, {"name", "url"}, "ELS provenance publisher")
    _safe_https_url(publisher["url"], label="ELS provenance publisher URL")
    scope = _projected_mapping(source["scope"], label="ELS provenance source scope")
    _validate_exact_keys(scope, {"excludes", "includes"}, "ELS provenance source scope")

    expected_assurance = {
        "allowlistProjection": True,
        "binaryPayloadsIncluded": False,
        "cacheLocationPublished": False,
        "credentialsRequired": False,
        "geometryIncluded": False,
        "metadataOnly": True,
        "observationsFetched": False,
    }
    assurance = _projected_mapping(provenance["assurance"], label="ELS assurance")
    _validate_exact_keys(assurance, set(expected_assurance), "ELS assurance")
    if dict(assurance) != expected_assurance:
        raise ELSProjectionError("ELS assurance flags do not match the metadata-only contract")

    explained = _projected_list(
        provenance["explainedExclusions"], label="ELS explained exclusions"
    )
    if len(explained) != ELS_MANIFEST_EXCLUSION_COUNT:
        raise ELSProjectionError("ELS explained exclusions do not match the reviewed denominator")
    for index, exclusion in enumerate(explained):
        row = _projected_mapping(exclusion, label=f"ELS explained exclusion {index}")
        _validate_exact_keys(
            row,
            {
                "denominatorTreatment",
                "indicatorCode",
                "internalDatasetId",
                "manifestRow",
                "nativeIdentity",
                "reason",
            },
            f"ELS explained exclusion {index}",
        )

    alias_projection = _projected_mapping(
        provenance["aliasProjection"], label="ELS alias projection"
    )
    _validate_exact_keys(
        alias_projection,
        {"acceptedCount", "excluded", "excludedCount", "inputCount"},
        "ELS alias projection",
    )
    alias_exclusions = _projected_list(
        alias_projection["excluded"], label="ELS alias exclusions"
    )
    if (
        alias_projection["acceptedCount"] != sum(len(record["aliases"]) for record in records)
        or alias_projection["excludedCount"] != len(alias_exclusions)
        or alias_projection["inputCount"]
        != alias_projection["acceptedCount"] + alias_projection["excludedCount"]
    ):
        raise ELSProjectionError("ELS alias projection counts are inconsistent")
    for index, exclusion in enumerate(alias_exclusions):
        row = _projected_mapping(exclusion, label=f"ELS alias exclusion {index}")
        _validate_exact_keys(row, {"alias", "reason", "target"}, f"ELS alias exclusion {index}")

    submodule = _projected_mapping(provenance["submodule"], label="ELS submodule evidence")
    _validate_exact_keys(
        submodule,
        {
            "commit",
            "commitAsOf",
            "commitAsOfResolution",
            "commitAsOfVerified",
            "commitResolution",
            "inputs",
            "repository",
        },
        "ELS submodule evidence",
    )
    commit = _plain_text(submodule["commit"], limit=64, required=True).lower()
    if not _COMMIT_RE.fullmatch(commit) or submodule["repository"] != ELS_UPSTREAM_REPOSITORY:
        raise ELSProjectionError("ELS submodule revision evidence is invalid")
    _safe_https_url(submodule["repository"], label="ELS submodule repository")
    inputs = _projected_list(submodule["inputs"], label="ELS submodule inputs")
    input_hashes: dict[str, str] = {}
    for index, input_row in enumerate(inputs):
        row = _projected_mapping(input_row, label=f"ELS submodule input {index}")
        _validate_exact_keys(
            row,
            {"repositoryPath", "role", "sha256"},
            f"ELS submodule input {index}",
        )
        role = _plain_text(row["role"], limit=100, required=True)
        if role not in _INPUT_PATHS or row["repositoryPath"] != _INPUT_PATHS[role].as_posix():
            raise ELSProjectionError(f"ELS submodule input {index} is not allowlisted")
        input_hashes[role] = _validated_sha256(
            row["sha256"], label=f"ELS submodule input {index} hash"
        )
    if set(input_hashes) != set(_INPUT_PATHS):
        raise ELSProjectionError("ELS submodule input evidence is incomplete or duplicated")

    pages = _projected_list(provenance["pages"], label="ELS page receipts")
    if provenance["pageCount"] != len(pages) or len(pages) != len(_INPUT_PATHS):
        raise ELSProjectionError("ELS page receipt count is inconsistent")
    raw_repository = ELS_UPSTREAM_REPOSITORY.replace(
        "github.com", "raw.githubusercontent.com"
    )
    expected_base = f"{raw_repository}/{commit}"
    for index, (role, relative) in enumerate(_INPUT_PATHS.items()):
        page = _projected_mapping(pages[index], label=f"ELS page receipt {index}")
        page_keys = {
            "cacheHit",
            "contentSha256",
            "normalisedRecordCount",
            "requestUrl",
            "responseHeaders",
            "responseUrl",
            "retrievedAt",
            "upstreamRecordCount",
        }
        _validate_exact_keys(
            page,
            page_keys,
            f"ELS page receipt {index}",
            required=page_keys - {"retrievedAt"},
        )
        expected_url = f"{expected_base}/{relative.as_posix()}"
        if (
            page["requestUrl"] != expected_url
            or page["responseUrl"] != expected_url
            or page["cacheHit"] is not True
            or page["responseHeaders"] != {}
        ):
            raise ELSProjectionError(f"ELS page receipt {index} is not the pinned safe input")
        _safe_https_url(page["requestUrl"], label=f"ELS page receipt {index} URL")
        if _validated_sha256(
            page["contentSha256"], label=f"ELS page receipt {index} hash"
        ) != input_hashes[role]:
            raise ELSProjectionError(f"ELS page receipt {index} does not match submodule evidence")

    if "acquisition" in provenance:
        acquisition = _projected_mapping(provenance["acquisition"], label="ELS acquisition time")
        _validate_exact_keys(
            acquisition,
            {"retrievedAt", "timestampSource"},
            "ELS acquisition time",
        )

    record_set_sha = _validated_sha256(
        provenance["recordSetSha256"], label="ELS record-set hash"
    )
    if record_set_sha != _sha256_json(records):
        raise ELSProjectionError("ELS projected acquisition record-set hash mismatch")
    receipts = [
        {"requestUrl": page["requestUrl"], "contentSha256": page["contentSha256"]}
        for page in pages
    ]
    snapshot_set_sha = _validated_sha256(
        provenance["snapshotSetSha256"], label="ELS snapshot-set hash"
    )
    if snapshot_set_sha != _sha256_json(receipts):
        raise ELSProjectionError("ELS projected acquisition snapshot-set hash mismatch")


def _validate_expected_hashes(
    receipts: Mapping[str, Mapping[str, Any]], expected_hashes: Mapping[str, str] | None
) -> None:
    if not expected_hashes:
        return
    unknown = sorted(set(expected_hashes) - set(receipts))
    if unknown:
        raise ELSProjectionError("Unknown expected ELS input hash key(s): " + ", ".join(unknown))
    for key, expected in expected_hashes.items():
        normalised = _plain_text(expected, limit=100, required=True).lower()
        if not re.fullmatch(r"[0-9a-f]{64}", normalised):
            raise ELSProjectionError(f"Expected ELS hash for {key} is not SHA-256")
        if receipts[key]["contentSha256"] != normalised:
            raise ELSProjectionError(f"ELS input hash mismatch for {key}")


def project_els_snapshot(
    submodule_directory: Path | str,
    *,
    submodule_commit: str | None = None,
    commit_as_of: str | None = None,
    retrieved_at: str | None = None,
    expected_hashes: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Return a frozen-snapshot-compatible public ELS acquisition envelope."""

    root = Path(submodule_directory)
    payloads, input_receipts = _read_inputs(root)
    _validate_expected_hashes(input_receipts, expected_hashes)
    metadata = _read_json_object(payloads["indicatorMetadata"], label="ELS metadata")
    aliases = _read_json_object(payloads["indicatorAliases"], label="ELS aliases")
    manifest = _read_manifest(payloads["indicatorManifest"])
    items = _validate_metadata_collection(metadata)

    included = [row for row in manifest if row["include"]]
    excluded = [row for row in manifest if not row["include"]]
    if len(included) != ELS_PUBLISHED_INDICATOR_COUNT:
        raise ELSProjectionError(
            "ELS included manifest count changed: "
            f"expected {ELS_PUBLISHED_INDICATOR_COUNT}, found {len(included)}"
        )
    if len(excluded) != ELS_MANIFEST_EXCLUSION_COUNT:
        raise ELSProjectionError(
            "ELS explained manifest exclusion count changed: "
            f"expected {ELS_MANIFEST_EXCLUSION_COUNT}, found {len(excluded)}"
        )
    included_slugs = [str(row["slug"]) for row in included]
    if len(included_slugs) != len(set(included_slugs)):
        raise ELSProjectionError("ELS included manifest contains duplicate slugs")

    raw_items: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(items):
        _validate_raw_item(item, index=index)
        extension = item["extension"]
        slug = _safe_slug(extension.get("slug"), label=f"ELS metadata item {index} slug")
        if slug in raw_items:
            raise ELSProjectionError(f"ELS metadata contains duplicate indicator slug {slug!r}")
        raw_items[slug] = item
    if set(raw_items) != set(included_slugs):
        differences = sorted(set(raw_items) ^ set(included_slugs))
        raise ELSProjectionError(
            "ELS metadata items do not close the included manifest denominator: "
            + ", ".join(differences)
        )

    aliases_by_target, alias_details = _project_aliases(aliases, set(included_slugs))
    revision = resolve_submodule_revision(
        root,
        supplied_commit=submodule_commit,
        supplied_commit_as_of=commit_as_of,
    )
    acquisition_retrieved_at = (
        _normalise_timestamp(
            retrieved_at,
            label="ELS acquisition/retrieval time",
        )
        if retrieved_at
        else None
    )

    records = [
        _project_record(
            raw_items[str(row["slug"])],
            row,
            aliases=aliases_by_target[str(row["slug"])],
            commit=revision["commit"],
            order=order,
        )
        for order, row in enumerate(included, start=1)
    ]
    record_ids = [record["sourceRecordId"] for record in records]
    if len(record_ids) != len(set(record_ids)):
        raise ELSProjectionError("Projected ELS records do not have unique native identities")

    raw_base = (
        "https://raw.githubusercontent.com/ONSdigital/"
        f"explore-local-statistics-app/{revision['commit']}"
    )
    pages: list[dict[str, Any]] = []
    for key, relative in _INPUT_PATHS.items():
        receipt = input_receipts[key]
        upstream_count = (
            len(items)
            if key == "indicatorMetadata"
            else len(manifest)
            if key == "indicatorManifest"
            else len(aliases)
        )
        normalised_count = (
            len(records)
            if key == "indicatorMetadata"
            else len(manifest)
            if key == "indicatorManifest"
            else alias_details["acceptedCount"]
        )
        source_url = f"{raw_base}/{relative.as_posix()}"
        page = {
            "requestUrl": source_url,
            "responseUrl": source_url,
            "contentSha256": receipt["contentSha256"],
            "responseHeaders": {},
            "cacheHit": True,
            "upstreamRecordCount": upstream_count,
            "normalisedRecordCount": normalised_count,
        }
        if acquisition_retrieved_at:
            page["retrievedAt"] = acquisition_retrieved_at
        pages.append(page)

    explained_exclusions = [
        {
            "nativeIdentity": f"{row['dataset']}::{row['code']}",
            "internalDatasetId": row["dataset"],
            "indicatorCode": row["code"],
            "manifestRow": row["manifestRow"],
            "reason": "upstream-manifest-include-false",
            "denominatorTreatment": "outside-published-ELS-indicator-surface",
        }
        for row in excluded
    ]
    record_set_sha = _sha256_json(records)
    snapshot_set_sha = _sha256_json(
        [
            {
                "requestUrl": page["requestUrl"],
                "contentSha256": page["contentSha256"],
            }
            for page in pages
        ]
    )
    provenance = {
        "source": {
            "id": ELS_SOURCE_ID,
            "title": "ONS Explore Local Statistics published indicator catalogue",
            "adapter": "els-metadata-projection",
            "endpoint": ELS_METADATA_ENDPOINT,
            "publisher": {
                "name": ELS_OPERATOR["name"],
                "url": ELS_OPERATOR["url"],
            },
            "responseFormat": "Pinned JSON-stat 2.0 metadata projection",
            "standards": ["JSON-stat 2.0 metadata structure", "HTTPS JSON API"],
            "scope": {
                "includes": [
                    "Published ELS indicator identity and taxonomy",
                    "Source attribution, units, time coverage, dimensions and geography metadata",
                    "Historical aliases whose target remains published",
                ],
                "excludes": [
                    "Observation values, statuses and value domains",
                    "CSV, spreadsheet and other binary data downloads",
                    "Boundaries, coordinates, postcodes and other geometry content",
                    "Analytical area clusters and similarity outputs",
                ],
            },
            "identityFields": ["indicator slug"],
            "crossReferences": [
                "internal dataset slug",
                "indicator code",
                "upstream producer URLs",
                "GSS geography code types",
            ],
        },
        "retrievalMode": "pinned-submodule-projection",
        "complete": True,
        "stopReason": "sourceExhausted",
        "reportedTotal": ELS_PUBLISHED_INDICATOR_COUNT,
        "recordCount": len(records),
        "upstreamRecordsSeen": ELS_PUBLISHED_INDICATOR_COUNT,
        "normalisedRecordsSeen": len(records),
        "normalisationDroppedCount": 0,
        "unrepresentedCount": 0,
        "coverageComplete": True,
        "pageCount": len(pages),
        "recordSetSha256": record_set_sha,
        "snapshotSetSha256": snapshot_set_sha,
        "pages": pages,
        "sourceManifestCount": len(manifest),
        "includedManifestCount": len(included),
        "explainedExclusionCount": len(explained_exclusions),
        "explainedExclusions": explained_exclusions,
        "aliasProjection": alias_details,
        "submodule": {
            "repository": ELS_UPSTREAM_REPOSITORY,
            "commit": revision["commit"],
            "commitResolution": revision["commitResolution"],
            "commitAsOf": revision["commitAsOf"],
            "commitAsOfResolution": revision["commitAsOfResolution"],
            "commitAsOfVerified": revision["commitAsOfVerified"],
            "inputs": [
                {
                    "role": key,
                    "repositoryPath": _INPUT_PATHS[key].as_posix(),
                    "sha256": input_receipts[key]["contentSha256"],
                }
                for key in _INPUT_PATHS
            ],
        },
        "assurance": {
            "metadataOnly": True,
            "observationsFetched": False,
            "binaryPayloadsIncluded": False,
            "geometryIncluded": False,
            "credentialsRequired": False,
            "cacheLocationPublished": False,
            "allowlistProjection": True,
        },
    }
    if acquisition_retrieved_at:
        provenance["acquisition"] = {
            "retrievedAt": acquisition_retrieved_at,
            "timestampSource": "supplied",
        }
    result = {
        "schemaVersion": "okf-ons.source-acquisition.v1",
        "provenance": provenance,
        "records": records,
    }
    validate_els_acquisition_envelope(result)
    return result


__all__ = [
    "ELSProjectionError",
    "ELS_MANIFEST_EXCLUSION_COUNT",
    "ELS_PUBLISHED_INDICATOR_COUNT",
    "canonical_json",
    "project_els_snapshot",
    "resolve_submodule_revision",
    "validate_els_acquisition_envelope",
]
