"""Bounded, resumable acquisition of official ONS catalogue metadata.

The acquisition layer deliberately stops at catalogue metadata.  It does not
call observation endpoints and it projects upstream payloads onto small,
auditable metadata records before they can enter an OKF bundle.

Raw response pages are cached as content-addressed JSON envelopes.  A frozen
run uses those envelopes without network access, making a publication rebuild
deterministic and allowing an interrupted live crawl to resume page by page.
Cache locations are operational inputs only and are never included in the
public result.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import tempfile
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

CacheMode = Literal["prefer-cache", "refresh", "frozen"]

_CACHE_SCHEMA = "okf-ons.source-page.v1"
_PUBLIC_RESULT_SCHEMA = "okf-ons.source-acquisition.v1"
_SUPPORTED_ADAPTERS = {"ons-data-api", "nomis-sdmx", "open-geography-search"}
_SAFE_RESPONSE_HEADERS = ("content-type", "etag", "last-modified")
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
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


class SourceConfigurationError(ValueError):
    """Raised when the checked-in source register is unsafe or malformed."""


class SourceAcquisitionError(RuntimeError):
    """Raised when a source page cannot be acquired or verified."""


@dataclass(frozen=True)
class SourceDefinition:
    """Validated source-register entry used by an adapter."""

    source_id: str
    title: str
    adapter: str
    endpoint: str
    publisher_name: str
    publisher_url: str
    response_format: str
    standards: tuple[str, ...]
    includes: tuple[str, ...]
    excludes: tuple[str, ...]
    identity_fields: tuple[str, ...]
    cross_references: tuple[str, ...]
    default_page_size: int
    maximum_page_size: int

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> SourceDefinition:
        publisher = _require_mapping(value, "publisher")
        scope = _require_mapping(value, "scope")
        pagination = _require_mapping(value, "pagination")
        source = cls(
            source_id=_require_text(value, "id"),
            title=_require_text(value, "title"),
            adapter=_require_text(value, "adapter"),
            endpoint=_require_text(value, "endpoint"),
            publisher_name=_require_text(publisher, "name"),
            publisher_url=_require_text(publisher, "url"),
            response_format=_require_text(value, "responseFormat"),
            standards=_text_tuple(value.get("standards"), "standards"),
            includes=_text_tuple(scope.get("includes"), "scope.includes"),
            excludes=_text_tuple(scope.get("excludes"), "scope.excludes"),
            identity_fields=_text_tuple(value.get("identityFields"), "identityFields"),
            cross_references=_text_tuple(
                value.get("crossReferences"),
                "crossReferences",
            ),
            default_page_size=_positive_int(
                pagination.get("defaultPageSize"),
                "pagination.defaultPageSize",
            ),
            maximum_page_size=_positive_int(
                pagination.get("maximumPageSize"),
                "pagination.maximumPageSize",
            ),
        )
        source.validate()
        return source

    def validate(self) -> None:
        if self.adapter not in _SUPPORTED_ADAPTERS:
            raise SourceConfigurationError(
                f"Source {self.source_id!r} uses unsupported adapter {self.adapter!r}"
            )
        if self.default_page_size > self.maximum_page_size:
            raise SourceConfigurationError(
                f"Source {self.source_id!r} default page size exceeds its maximum"
            )
        endpoint = urlsplit(self.endpoint)
        publisher = urlsplit(self.publisher_url)
        if (
            endpoint.scheme != "https"
            or not endpoint.hostname
            or endpoint.username
            or endpoint.password
        ):
            raise SourceConfigurationError(
                f"Source {self.source_id!r} endpoint must be a credential-free absolute HTTPS URL"
            )
        if (
            publisher.scheme != "https"
            or not publisher.hostname
            or publisher.username
            or publisher.password
        ):
            raise SourceConfigurationError(
                f"Source {self.source_id!r} publisher URL must be a credential-free "
                "absolute HTTPS URL"
            )
        _reject_secret_query(self.endpoint)

    @property
    def allowed_hostname(self) -> str:
        hostname = urlsplit(self.endpoint).hostname
        assert hostname is not None
        return hostname.lower()

    def public_description(self) -> dict[str, Any]:
        return {
            "id": self.source_id,
            "title": self.title,
            "publisher": {
                "name": self.publisher_name,
                "url": self.publisher_url,
            },
            "endpoint": self.endpoint,
            "responseFormat": self.response_format,
            "standards": list(self.standards),
            "scope": {
                "includes": list(self.includes),
                "excludes": list(self.excludes),
            },
            "identityFields": list(self.identity_fields),
            "crossReferences": list(self.cross_references),
        }


@dataclass(frozen=True)
class HttpJsonResponse:
    """Transport-neutral JSON response with a deliberately small header set."""

    payload: Any
    final_url: str
    status: int = 200
    headers: Mapping[str, str] | None = None


class JsonTransport(Protocol):
    """Injectable transport used by the acquisition engine."""

    def get_json(
        self,
        url: str,
        params: Mapping[str, str],
        *,
        timeout: float,
    ) -> HttpJsonResponse:
        """Return a decoded JSON response."""


class UrllibJsonTransport:
    """Dependency-free HTTPS JSON transport with a bounded response body."""

    def __init__(
        self,
        *,
        user_agent: str = "okf-ons-metadata-harvester/0.1",
        maximum_response_bytes: int = 64 * 1024 * 1024,
    ) -> None:
        if maximum_response_bytes < 1:
            raise ValueError("maximum_response_bytes must be positive")
        self.user_agent = user_agent
        self.maximum_response_bytes = maximum_response_bytes

    def get_json(
        self,
        url: str,
        params: Mapping[str, str],
        *,
        timeout: float,
    ) -> HttpJsonResponse:
        request_url = _url_with_params(url, params)
        request = Request(
            request_url,
            headers={
                "Accept": "application/json",
                "User-Agent": self.user_agent,
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=timeout) as response:  # noqa: S310
                body = response.read(self.maximum_response_bytes + 1)
                if len(body) > self.maximum_response_bytes:
                    raise SourceAcquisitionError(
                        "Upstream response exceeded the configured byte limit"
                    )
                try:
                    payload = json.loads(body.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise SourceAcquisitionError(
                        "Upstream returned an invalid UTF-8 JSON response"
                    ) from exc
                headers = {
                    name: response.headers[name]
                    for name in _SAFE_RESPONSE_HEADERS
                    if response.headers.get(name)
                }
                return HttpJsonResponse(
                    payload=payload,
                    final_url=response.geturl(),
                    status=int(response.status),
                    headers=headers,
                )
        except HTTPError as exc:
            raise SourceAcquisitionError(f"Upstream returned HTTP {exc.code}") from exc
        except URLError as exc:
            raise SourceAcquisitionError("Upstream request failed") from exc


@dataclass(frozen=True)
class AcquisitionResult:
    """Normalised records and path-free public provenance."""

    records: tuple[dict[str, Any], ...]
    provenance: dict[str, Any]

    def as_public_dict(self) -> dict[str, Any]:
        # A canonical JSON round trip provides a deep copy and proves the result
        # contains JSON values only.
        value = {
            "schemaVersion": _PUBLIC_RESULT_SCHEMA,
            "records": list(self.records),
            "provenance": self.provenance,
        }
        return json.loads(_canonical_json(value))


@dataclass(frozen=True)
class _PageRequest:
    url: str
    params: tuple[tuple[str, str], ...] = ()

    @classmethod
    def create(
        cls,
        url: str,
        params: Mapping[str, str | int] | None = None,
    ) -> _PageRequest:
        pairs = tuple(
            sorted(
                ((str(key), str(item)) for key, item in (params or {}).items()),
                key=lambda pair: (pair[0], pair[1]),
            )
        )
        return cls(url=url, params=pairs)

    def parameter_mapping(self) -> dict[str, str]:
        return dict(self.params)

    def resolved_url(self) -> str:
        return _url_with_params(self.url, self.parameter_mapping())


@dataclass(frozen=True)
class _CachedPage:
    payload: Any
    retrieved_at: str
    request_url: str
    response_url: str
    content_sha256: str
    response_headers: dict[str, str]
    cache_hit: bool


class _RateLimiter:
    def __init__(
        self,
        interval_seconds: float,
        *,
        monotonic: Callable[[], float],
        sleep: Callable[[float], None],
    ) -> None:
        self.interval_seconds = interval_seconds
        self.monotonic = monotonic
        self.sleep = sleep
        self.last_request_at: float | None = None

    def wait(self) -> None:
        current = self.monotonic()
        if self.last_request_at is not None:
            wait_for = self.interval_seconds - (current - self.last_request_at)
            if wait_for > 0:
                self.sleep(wait_for)
                current = self.monotonic()
        self.last_request_at = current


def load_source_register(path: Path | str) -> dict[str, SourceDefinition]:
    """Load and validate a checked-in source register."""

    register_path = Path(path)
    try:
        raw = json.loads(register_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SourceConfigurationError("Unable to read source register") from exc
    if not isinstance(raw, dict):
        raise SourceConfigurationError("Source register root must be an object")
    sources = raw.get("sources")
    if not isinstance(sources, list) or not sources:
        raise SourceConfigurationError("Source register must contain a non-empty sources array")

    result: dict[str, SourceDefinition] = {}
    for raw_source in sources:
        if not isinstance(raw_source, dict):
            raise SourceConfigurationError("Every source-register entry must be an object")
        source = SourceDefinition.from_mapping(raw_source)
        if source.source_id in result:
            raise SourceConfigurationError(f"Duplicate source-register id {source.source_id!r}")
        result[source.source_id] = source
    return result


def acquire_source(
    source: SourceDefinition,
    *,
    cache_directory: Path | str,
    mode: CacheMode = "prefer-cache",
    transport: JsonTransport | None = None,
    page_size: int | None = None,
    maximum_pages: int = 100,
    maximum_items: int | None = None,
    request_interval_seconds: float = 0.25,
    timeout_seconds: float = 30.0,
    retries: int = 2,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> AcquisitionResult:
    """Acquire one source using cached pages where permitted.

    ``frozen`` mode is network-free and fails if any required page is absent.
    ``prefer-cache`` resumes a partial acquisition.  ``refresh`` replaces every
    page encountered in this run.
    """

    if mode not in {"prefer-cache", "refresh", "frozen"}:
        raise ValueError(f"Unsupported cache mode {mode!r}")
    if maximum_pages < 1:
        raise ValueError("maximum_pages must be positive")
    if maximum_items is not None and maximum_items < 1:
        raise ValueError("maximum_items must be positive when supplied")
    if request_interval_seconds < 0 or request_interval_seconds > 60:
        raise ValueError("request_interval_seconds must be between 0 and 60")
    if timeout_seconds <= 0 or timeout_seconds > 300:
        raise ValueError("timeout_seconds must be greater than 0 and at most 300")
    if retries < 0 or retries > 5:
        raise ValueError("retries must be between 0 and 5")

    requested_page_size = page_size or source.default_page_size
    if requested_page_size < 1 or requested_page_size > source.maximum_page_size:
        raise ValueError(
            f"page_size must be between 1 and {source.maximum_page_size} for {source.source_id}"
        )

    cache_root = Path(cache_directory)
    live_transport = transport or UrllibJsonTransport()
    limiter = _RateLimiter(
        request_interval_seconds,
        monotonic=monotonic,
        sleep=sleep,
    )
    request = _initial_request(source, requested_page_size)
    seen_requests: set[str] = set()
    records_by_id: dict[str, dict[str, Any]] = {}
    receipts: list[dict[str, Any]] = []
    reported_total: int | None = None
    upstream_records_seen = 0
    normalised_records_seen = 0
    complete = False
    stop_reason = "maximumPages"

    for _page_number in range(1, maximum_pages + 1):
        _validate_request(source, request)
        request_url = request.resolved_url()
        if request_url in seen_requests:
            raise SourceAcquisitionError(
                f"Source {source.source_id!r} returned a repeated pagination request"
            )
        seen_requests.add(request_url)

        page = _read_or_fetch_page(
            source,
            request,
            cache_root=cache_root,
            mode=mode,
            transport=live_transport,
            limiter=limiter,
            timeout_seconds=timeout_seconds,
            retries=retries,
            sleep=sleep,
            now=now,
        )
        page_records, page_total = _normalise_page(source, page.payload)
        upstream_record_count = _raw_record_count(source, page.payload)
        upstream_records_seen += upstream_record_count
        normalised_records_seen += len(page_records)
        if page_total is not None:
            reported_total = (
                page_total
                if reported_total is None
                else max(
                    reported_total,
                    page_total,
                )
            )
        receipts.append(
            {
                "requestUrl": page.request_url,
                "responseUrl": page.response_url,
                "retrievedAt": page.retrieved_at,
                "contentSha256": page.content_sha256,
                "responseHeaders": page.response_headers,
                "cacheHit": page.cache_hit,
                "upstreamRecordCount": upstream_record_count,
                "normalisedRecordCount": len(page_records),
            }
        )

        reached_item_bound = False
        for record in page_records:
            record_id = str(record["sourceRecordId"])
            records_by_id.setdefault(record_id, record)
            if maximum_items is not None and len(records_by_id) >= maximum_items:
                reached_item_bound = True
                break
        if reached_item_bound:
            complete = reported_total is not None and len(records_by_id) >= reported_total
            stop_reason = "sourceExhausted" if complete else "maximumItems"
            break

        next_request = _next_request(source, request, page.payload, len(page_records))
        if next_request is None:
            complete = True
            stop_reason = "sourceExhausted"
            break
        request = next_request

    records = tuple(
        records_by_id[key]
        for key in sorted(records_by_id, key=lambda item: (item.casefold(), item))
    )
    record_set_sha = _sha256_json(list(records))
    normalisation_dropped_count = max(
        0,
        upstream_records_seen - normalised_records_seen,
    )
    unrepresented_count = (
        max(0, reported_total - len(records)) if reported_total is not None else None
    )
    coverage_complete = (
        complete
        and normalisation_dropped_count == 0
        and (reported_total is None or len(records) == reported_total)
    )
    snapshot_set_sha = _sha256_json(
        [
            {
                "requestUrl": receipt["requestUrl"],
                "contentSha256": receipt["contentSha256"],
            }
            for receipt in receipts
        ]
    )
    provenance = {
        "source": source.public_description(),
        "retrievalMode": mode,
        "complete": complete,
        "stopReason": stop_reason,
        "reportedTotal": reported_total,
        "recordCount": len(records),
        "upstreamRecordsSeen": upstream_records_seen,
        "normalisedRecordsSeen": normalised_records_seen,
        "normalisationDroppedCount": normalisation_dropped_count,
        "unrepresentedCount": unrepresented_count,
        "coverageComplete": coverage_complete,
        "pageCount": len(receipts),
        "recordSetSha256": record_set_sha,
        "snapshotSetSha256": snapshot_set_sha,
        "pages": receipts,
        "assurance": {
            "metadataOnly": True,
            "observationsFetched": False,
            "credentialsRequired": False,
            "cacheLocationPublished": False,
        },
    }
    return AcquisitionResult(records=records, provenance=provenance)


def acquire_registered_source(
    source_id: str,
    *,
    source_register: Path | str,
    cache_directory: Path | str,
    **kwargs: Any,
) -> AcquisitionResult:
    """Convenience wrapper that resolves a source id from the register."""

    sources = load_source_register(source_register)
    try:
        source = sources[source_id]
    except KeyError as exc:
        raise SourceConfigurationError(f"Unknown source id {source_id!r}") from exc
    return acquire_source(source, cache_directory=cache_directory, **kwargs)


def _initial_request(source: SourceDefinition, page_size: int) -> _PageRequest:
    if source.adapter == "ons-data-api":
        return _PageRequest.create(
            source.endpoint,
            {"limit": page_size, "offset": 0},
        )
    if source.adapter == "nomis-sdmx":
        return _PageRequest.create(source.endpoint)
    if source.adapter == "open-geography-search":
        return _PageRequest.create(
            source.endpoint,
            {
                "limit": page_size,
                # The upstream default ordering is not stable across pages and
                # can repeat hundreds of records during a full crawl.  The
                # official API documents ``sortBy`` and ``properties.title`` is
                # a queryable field, so publication crawls always request an
                # explicit ordering.  Native record ids still provide identity.
                "sortBy": "+properties.title",
            },
        )
    raise AssertionError(f"Unhandled source adapter {source.adapter!r}")


def _next_request(
    source: SourceDefinition,
    current: _PageRequest,
    payload: Any,
    normalised_count: int,
) -> _PageRequest | None:
    if source.adapter == "nomis-sdmx":
        return None
    if not isinstance(payload, dict):
        raise SourceAcquisitionError(f"Source {source.source_id!r} returned a non-object page")
    if source.adapter == "ons-data-api":
        raw_records = payload.get("items")
        if not isinstance(raw_records, list):
            raw_records = payload.get("results")
        if not isinstance(raw_records, list):
            raise SourceAcquisitionError("ONS Data API page has no items or results array")
        total = _first_non_negative_int(
            payload.get("total"),
            payload.get("total_count"),
        )
        offset = _parameter_int(current, "offset", 0)
        if not raw_records:
            return None
        next_offset = offset + len(raw_records)
        if total is not None and next_offset >= total:
            return None
        limit = _parameter_int(current, "limit", len(raw_records))
        return _PageRequest.create(
            source.endpoint,
            {"limit": limit, "offset": next_offset},
        )
    if source.adapter == "open-geography-search":
        next_href = _next_link(payload.get("links"))
        if next_href:
            return _PageRequest.create(next_href)
        raw_features = payload.get("features")
        if not isinstance(raw_features, list):
            raise SourceAcquisitionError("Open Geography search page has no features array")
        if not raw_features:
            return None
        total = _first_non_negative_int(
            payload.get("numberMatched"),
            payload.get("total"),
        )
        start_index = _parameter_int(current, "startindex", 1)
        next_start_index = start_index + len(raw_features)
        if total is None or next_start_index > total:
            return None
        limit = _parameter_int(current, "limit", len(raw_features))
        return _PageRequest.create(
            source.endpoint,
            {"limit": limit, "startindex": next_start_index},
        )
    raise AssertionError(f"Unhandled source adapter {source.adapter!r}")


def _normalise_page(
    source: SourceDefinition,
    payload: Any,
) -> tuple[list[dict[str, Any]], int | None]:
    if not isinstance(payload, dict):
        raise SourceAcquisitionError(
            f"Source {source.source_id!r} returned a non-object JSON payload"
        )
    if source.adapter == "ons-data-api":
        return _normalise_ons_data_api(source, payload)
    if source.adapter == "nomis-sdmx":
        return _normalise_nomis(source, payload)
    if source.adapter == "open-geography-search":
        return _normalise_open_geography(source, payload)
    raise AssertionError(f"Unhandled source adapter {source.adapter!r}")


def _raw_record_count(source: SourceDefinition, payload: Any) -> int:
    if not isinstance(payload, dict):
        return 0
    if source.adapter == "ons-data-api":
        raw = payload.get("items")
        if not isinstance(raw, list):
            raw = payload.get("results")
        return len(raw) if isinstance(raw, list) else 0
    if source.adapter == "nomis-sdmx":
        node: Any = payload.get("structure")
        node = node.get("keyfamilies") if isinstance(node, dict) else None
        node = node.get("keyfamily") if isinstance(node, dict) else None
        if isinstance(node, list):
            return len(node)
        return 1 if isinstance(node, dict) else 0
    if source.adapter == "open-geography-search":
        features = payload.get("features")
        return len(features) if isinstance(features, list) else 0
    raise AssertionError(f"Unhandled source adapter {source.adapter!r}")


def _normalise_ons_data_api(
    source: SourceDefinition,
    payload: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], int | None]:
    raw_records = payload.get("items")
    if not isinstance(raw_records, list):
        raw_records = payload.get("results")
    if not isinstance(raw_records, list):
        raise SourceAcquisitionError("ONS Data API page has no items or results array")
    records: list[dict[str, Any]] = []
    for raw in raw_records:
        if not isinstance(raw, dict):
            continue
        record_id = _extract_text(raw.get("id"))
        title = _extract_text(raw.get("title"))
        if not record_id or not title:
            continue
        record: dict[str, Any] = {
            "sourceId": source.source_id,
            "sourceRecordId": record_id,
            "recordKind": _extract_text(raw.get("kind")) or "dataset",
            "title": title,
        }
        _set_if_text(record, "description", raw.get("description"))
        _set_if_text(record, "lifecycleState", raw.get("state"))
        last_updated = _normalise_timestamp(raw.get("last_updated"))
        if last_updated:
            record["lastUpdated"] = last_updated
        _set_if_text(record, "nextRelease", raw.get("next_release"))
        _set_if_text(record, "releaseFrequency", raw.get("release_frequency"))
        _set_if_text(record, "unitOfMeasure", raw.get("unit_of_measure"))
        national_statistic = raw.get("national_statistic")
        if isinstance(national_statistic, bool):
            record["nationalStatistic"] = national_statistic
        keywords = _normalise_keywords(raw.get("keywords"))
        if keywords:
            record["keywords"] = keywords
        links = _normalise_links(raw.get("links"))
        if links:
            record["links"] = links
        themes = _first_present(raw, ("themes", "topic", "topics", "taxonomies"))
        if themes is not None:
            record["themes"] = _json_metadata(themes)
        methodologies = _normalise_references(raw.get("methodologies"))
        if methodologies:
            record["methodologies"] = methodologies
        qmi = _normalise_references(raw.get("qmi"))
        if qmi:
            record["qualityMethodologyInformation"] = qmi
        related_datasets = _normalise_references(raw.get("related_datasets"))
        if related_datasets:
            record["relatedDatasets"] = related_datasets
        records.append(record)
    return records, _first_non_negative_int(
        payload.get("total"),
        payload.get("total_count"),
    )


def _normalise_nomis(
    source: SourceDefinition,
    payload: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], int | None]:
    node: Any = payload.get("structure")
    node = node.get("keyfamilies") if isinstance(node, dict) else None
    node = node.get("keyfamily") if isinstance(node, dict) else None
    if isinstance(node, dict):
        keyfamilies: Sequence[Any] = [node]
    elif isinstance(node, list):
        keyfamilies = node
    else:
        raise SourceAcquisitionError("Nomis SDMX response has no structure.keyfamilies.keyfamily")

    records: list[dict[str, Any]] = []
    for raw in keyfamilies:
        if not isinstance(raw, dict):
            continue
        record_id = _extract_text(raw.get("id"))
        if not record_id:
            continue
        title = _extract_text(raw.get("name")) or record_id
        annotations = _normalise_sdmx_annotations(raw.get("annotations"))
        annotation_map = {
            str(item["title"]): str(item["text"])
            for item in annotations
            if item.get("title") and item.get("text")
        }
        record: dict[str, Any] = {
            "sourceId": source.source_id,
            "sourceRecordId": record_id,
            "recordKind": "dataset-definition",
            "title": title,
            "links": {
                "apiDefinition": (
                    f"https://www.nomisweb.co.uk/api/v01/dataset/{record_id}/def.sdmx.json"
                )
            },
        }
        description = (
            _extract_text(raw.get("description"))
            or annotation_map.get("SubDescription")
            or annotation_map.get("MetadataText0")
        )
        if description:
            record["description"] = description
        _set_if_text(record, "agencyId", raw.get("agencyid"))
        _set_if_text(record, "definitionVersion", raw.get("version"))
        _set_if_text(record, "publisherUri", raw.get("uri"))
        status = annotation_map.get("Status")
        if status:
            record["lifecycleState"] = status
        for public_key, annotation_title in (
            ("unitOfMeasure", "Units"),
            ("mnemonic", "Mnemonic"),
            ("firstReleased", "FirstReleased"),
            ("lastUpdated", "LastUpdated"),
            ("contentSource", "contenttype/sources"),
        ):
            value = annotation_map.get(annotation_title)
            if value:
                record[public_key] = value
        keywords = _normalise_keywords(annotation_map.get("Keywords"))
        if keywords:
            record["keywords"] = keywords
        if annotations:
            record["annotations"] = annotations
        components = _normalise_sdmx_components(raw.get("components"))
        if components:
            record["components"] = components
        records.append(record)
    return records, len(keyfamilies)


def _normalise_open_geography(
    source: SourceDefinition,
    payload: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], int | None]:
    features = payload.get("features")
    if not isinstance(features, list):
        raise SourceAcquisitionError("Open Geography search page has no features array")
    records: list[dict[str, Any]] = []
    for feature in features:
        if not isinstance(feature, dict):
            continue
        properties = feature.get("properties")
        if not isinstance(properties, dict):
            properties = {}
        record_id = _extract_text(feature.get("id")) or _extract_text(properties.get("id"))
        title = _extract_text(properties.get("title")) or _extract_text(properties.get("name"))
        if not record_id or not title:
            continue
        record: dict[str, Any] = {
            "sourceId": source.source_id,
            "sourceRecordId": record_id,
            "recordKind": "geospatial-dataset",
            "title": title,
        }
        description = _strip_html(_extract_text(properties.get("description")))
        if description:
            record["description"] = description
        for public_key, upstream_key in (
            ("itemType", "type"),
            ("owner", "owner"),
            ("access", "access"),
            ("accessInformation", "accessInformation"),
            ("licence", "licenseInfo"),
            ("culture", "culture"),
            ("snippet", "snippet"),
            ("source", "source"),
        ):
            _set_if_text(record, public_key, properties.get(upstream_key))
        for public_key, upstream_key in (
            ("created", "created"),
            ("modified", "modified"),
        ):
            timestamp = _normalise_timestamp(properties.get(upstream_key))
            if timestamp:
                record[public_key] = timestamp
        keywords = _normalise_keywords(
            list(_iter_scalars(properties.get("tags")))
            + list(_iter_scalars(properties.get("typeKeywords")))
        )
        if keywords:
            record["keywords"] = keywords
        links: dict[str, Any] = {}
        item_url = _safe_public_link(properties.get("url"))
        if item_url:
            links["item"] = item_url
        feature_links = _normalise_feature_links(feature.get("links"))
        if feature_links:
            links["related"] = feature_links
        if links:
            record["links"] = links
        bbox = feature.get("bbox")
        if _is_numeric_bbox(bbox):
            record["spatialEnvelope"] = list(bbox)
        for public_key, upstream_key in (
            ("categories", "categories"),
            ("classification", "classification"),
            ("documentation", "documentation"),
            ("languages", "languages"),
            ("portalExtent", "extent"),
            ("spatialReference", "spatialReference"),
        ):
            value = properties.get(upstream_key)
            if value not in (None, "", [], {}):
                record[public_key] = _json_metadata(value)
        temporal_extent = feature.get("time")
        if temporal_extent not in (None, "", [], {}):
            record["temporalExtent"] = _json_metadata(temporal_extent)
        # ``geometry`` is intentionally not copied: this is a metadata index,
        # not a mirror of spatial data.
        records.append(record)
    total = _first_non_negative_int(
        payload.get("numberMatched"),
        payload.get("total"),
    )
    return records, total


def _normalise_sdmx_annotations(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, dict):
        return []
    raw = value.get("annotation")
    annotations = raw if isinstance(raw, list) else [raw]
    result: list[dict[str, str]] = []
    for item in annotations:
        if not isinstance(item, dict):
            continue
        title = _extract_text(item.get("annotationtitle"))
        text = _extract_text(item.get("annotationtext"))
        annotation_type = _extract_text(item.get("annotationtype"))
        if not title and not text:
            continue
        normalised: dict[str, str] = {}
        if title:
            normalised["title"] = title
        if text:
            normalised["text"] = text
        if annotation_type:
            normalised["type"] = annotation_type
        result.append(normalised)
    return sorted(
        result,
        key=lambda item: (
            item.get("title", "").casefold(),
            item.get("text", "").casefold(),
        ),
    )


def _normalise_sdmx_components(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    result: list[dict[str, Any]] = []
    dimension_position = 0
    for component_kind in (
        "dimension",
        "timedimension",
        "attribute",
        "primarymeasure",
    ):
        raw_components = value.get(component_kind)
        if isinstance(raw_components, dict):
            components: Sequence[Any] = [raw_components]
        elif isinstance(raw_components, list):
            components = raw_components
        else:
            continue
        for raw in components:
            if not isinstance(raw, dict):
                continue
            component: dict[str, Any] = {"kind": component_kind}
            for public_key, upstream_key in (
                ("concept", "conceptref"),
                ("codeList", "codelist"),
                ("role", "role"),
                ("attachmentLevel", "attachmentlevel"),
                ("assignmentStatus", "assignmentstatus"),
            ):
                _set_if_text(component, public_key, raw.get(upstream_key))
            if len(component) > 1:
                if component_kind in {"dimension", "timedimension"}:
                    dimension_position += 1
                    component["position"] = dimension_position
                result.append(component)
    # Dimension order is part of SDMX DSD identity. Preserve the provider's
    # sequence instead of alphabetically sorting components for convenience.
    return result


def _read_or_fetch_page(
    source: SourceDefinition,
    request: _PageRequest,
    *,
    cache_root: Path,
    mode: CacheMode,
    transport: JsonTransport,
    limiter: _RateLimiter,
    timeout_seconds: float,
    retries: int,
    sleep: Callable[[float], None],
    now: Callable[[], datetime],
) -> _CachedPage:
    request_url = request.resolved_url()
    cache_path = _cache_path(cache_root, source.source_id, request_url)
    if mode != "refresh" and cache_path.is_file():
        return _load_cached_page(cache_path, source, request_url)
    if mode == "frozen":
        raise SourceAcquisitionError(
            f"Frozen snapshot is incomplete for source {source.source_id!r}"
        )

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        limiter.wait()
        try:
            response = transport.get_json(
                request.url,
                request.parameter_mapping(),
                timeout=timeout_seconds,
            )
            if response.status < 200 or response.status >= 300:
                raise SourceAcquisitionError(f"Upstream returned HTTP {response.status}")
            _validate_response_url(source, response.final_url)
            retrieved_at = _as_utc_iso(now())
            headers = _safe_headers(response.headers)
            page = _CachedPage(
                payload=response.payload,
                retrieved_at=retrieved_at,
                request_url=request_url,
                response_url=response.final_url,
                content_sha256=_sha256_json(response.payload),
                response_headers=headers,
                cache_hit=False,
            )
            _write_cached_page(cache_path, source, page)
            return page
        except (SourceAcquisitionError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt >= retries:
                break
            sleep(min(2**attempt, 8))
    raise SourceAcquisitionError(
        f"Failed to acquire metadata page for source {source.source_id!r}"
    ) from last_error


def _cache_path(cache_root: Path, source_id: str, request_url: str) -> Path:
    digest = hashlib.sha256(request_url.encode("utf-8")).hexdigest()
    return cache_root / source_id / f"{digest}.json"


def _write_cached_page(
    path: Path,
    source: SourceDefinition,
    page: _CachedPage,
) -> None:
    envelope = {
        "schemaVersion": _CACHE_SCHEMA,
        "sourceId": source.source_id,
        "requestUrl": page.request_url,
        "responseUrl": page.response_url,
        "retrievedAt": page.retrieved_at,
        "contentSha256": page.content_sha256,
        "responseHeaders": page.response_headers,
        "payload": page.payload,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    serialised = json.dumps(
        envelope,
        ensure_ascii=True,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    )
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(serialised)
            handle.write("\n")
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _load_cached_page(
    path: Path,
    source: SourceDefinition,
    request_url: str,
) -> _CachedPage:
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SourceAcquisitionError(
            f"Cached page for source {source.source_id!r} is unreadable"
        ) from exc
    if not isinstance(envelope, dict):
        raise SourceAcquisitionError("Cached page envelope must be an object")
    if envelope.get("schemaVersion") != _CACHE_SCHEMA:
        raise SourceAcquisitionError("Cached page uses an unsupported schema")
    if envelope.get("sourceId") != source.source_id:
        raise SourceAcquisitionError("Cached page source id does not match")
    if envelope.get("requestUrl") != request_url:
        raise SourceAcquisitionError("Cached page request URL does not match")
    payload = envelope.get("payload")
    expected_sha = _extract_text(envelope.get("contentSha256"))
    actual_sha = _sha256_json(payload)
    if expected_sha != actual_sha:
        raise SourceAcquisitionError("Cached page content hash does not match")
    response_url = _extract_text(envelope.get("responseUrl"))
    retrieved_at = _extract_text(envelope.get("retrievedAt"))
    if not response_url or not retrieved_at:
        raise SourceAcquisitionError("Cached page provenance is incomplete")
    _validate_response_url(source, response_url)
    return _CachedPage(
        payload=payload,
        retrieved_at=retrieved_at,
        request_url=request_url,
        response_url=response_url,
        content_sha256=actual_sha,
        response_headers=_safe_headers(envelope.get("responseHeaders")),
        cache_hit=True,
    )


def _validate_request(source: SourceDefinition, request: _PageRequest) -> None:
    _validate_response_url(source, request.resolved_url())


def _validate_response_url(source: SourceDefinition, url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname is None or parsed.username or parsed.password:
        raise SourceAcquisitionError("Source request must use a credential-free absolute HTTPS URL")
    if parsed.hostname.lower() != source.allowed_hostname:
        raise SourceAcquisitionError(
            f"Source pagination escaped the registered host for {source.source_id!r}"
        )
    _reject_secret_query(url)


def _reject_secret_query(url: str) -> None:
    query_keys = {key.casefold() for key, _ in parse_qsl(urlsplit(url).query)}
    forbidden = sorted(query_keys.intersection(_SECRET_QUERY_KEYS))
    if forbidden:
        raise SourceConfigurationError(
            "Source URL must not contain credential query parameters: " + ", ".join(forbidden)
        )


def _url_with_params(url: str, params: Mapping[str, str]) -> str:
    parsed = urlsplit(url)
    existing = parse_qsl(parsed.query, keep_blank_values=True)
    merged = existing + sorted(params.items(), key=lambda pair: (pair[0], pair[1]))
    query = urlencode(merged, doseq=True)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment))


def _next_link(value: Any) -> str | None:
    if isinstance(value, dict):
        return _extract_text(value.get("next"))
    if not isinstance(value, list):
        return None
    for item in value:
        if not isinstance(item, dict):
            continue
        relation = _extract_text(item.get("rel"))
        if relation and relation.casefold() == "next":
            return _extract_text(item.get("href"))
    return None


def _normalise_links(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, Any] = {}
    for relation in sorted(value, key=lambda item: str(item).casefold()):
        raw = value[relation]
        if isinstance(raw, dict):
            link: dict[str, str] = {}
            for key in ("href", "id"):
                text = (
                    _safe_public_link(raw.get(key))
                    if key == "href"
                    else _extract_text(raw.get(key))
                )
                if text:
                    link[key] = text
            if link:
                result[str(relation)] = link
        else:
            text = _extract_text(raw)
            if text and urlsplit(text).scheme in {"http", "https"}:
                text = _safe_public_link(text)
            if text:
                result[str(relation)] = text
    return result


def _normalise_feature_links(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, str]] = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        item: dict[str, str] = {}
        for key in ("rel", "href", "type", "title"):
            text = _safe_public_link(raw.get(key)) if key == "href" else _extract_text(raw.get(key))
            if text:
                item[key] = text
        if item:
            result.append(item)
    return sorted(
        result,
        key=lambda item: (
            item.get("rel", "").casefold(),
            item.get("href", ""),
        ),
    )


def _normalise_references(value: Any) -> list[dict[str, str]]:
    if isinstance(value, dict):
        raw_references: Sequence[Any] = [value]
    elif isinstance(value, list):
        raw_references = value
    else:
        return []
    result: list[dict[str, str]] = []
    for raw in raw_references:
        if not isinstance(raw, dict):
            continue
        reference: dict[str, str] = {}
        for key in ("id", "title", "href"):
            text = _safe_public_link(raw.get(key)) if key == "href" else _extract_text(raw.get(key))
            if text:
                reference[key] = text
        if reference:
            result.append(reference)
    return sorted(
        result,
        key=lambda item: (
            item.get("title", "").casefold(),
            item.get("href", ""),
            item.get("id", ""),
        ),
    )


def _json_metadata(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [_json_metadata(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _json_metadata(value[key])
            for key in sorted(value, key=lambda item: str(item).casefold())
        }
    return str(value)


def _safe_headers(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    lowered = {str(key).casefold(): str(item) for key, item in value.items()}
    return {name: lowered[name] for name in _SAFE_RESPONSE_HEADERS if name in lowered}


def _normalise_keywords(value: Any) -> list[str]:
    if isinstance(value, str):
        candidates: Iterable[Any] = re.split(r"[,;|]", value)
    else:
        candidates = _iter_scalars(value)
    unique: dict[str, str] = {}
    for candidate in candidates:
        text = _extract_text(candidate)
        if not text:
            continue
        unique.setdefault(text.casefold(), text)
    return [unique[key] for key in sorted(unique, key=lambda item: (item.casefold(), item))]


def _iter_scalars(value: Any) -> Iterable[Any]:
    if isinstance(value, (list, tuple)):
        yield from value
    elif value is not None:
        yield value


def _extract_text(value: Any) -> str | None:
    if isinstance(value, str):
        text = _SPACE_RE.sub(" ", value).strip()
        return text or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, dict):
        for key in ("value", "#text", "text"):
            if key in value:
                return _extract_text(value[key])
    return None


def _safe_public_link(value: Any) -> str | None:
    text = _extract_text(value)
    if not text:
        return None
    parsed = urlsplit(text)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    if parsed.username or parsed.password:
        return None
    query_keys = {key.casefold() for key, _ in parse_qsl(parsed.query)}
    if query_keys.intersection(_SECRET_QUERY_KEYS):
        return None
    return text


def _strip_html(value: str | None) -> str | None:
    if not value:
        return None
    text = html.unescape(value)
    text = _HTML_TAG_RE.sub(" ", text)
    return _SPACE_RE.sub(" ", text).strip() or None


def _normalise_timestamp(value: Any) -> str | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = float(value)
        if seconds > 10_000_000_000:
            seconds /= 1000
        try:
            return (
                datetime.fromtimestamp(seconds, tz=UTC)
                .isoformat()
                .replace(
                    "+00:00",
                    "Z",
                )
            )
        except (OSError, OverflowError, ValueError):
            return None
    return _extract_text(value)


def _is_numeric_bbox(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) in {4, 6}
        and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value)
    )


def _set_if_text(target: dict[str, Any], key: str, value: Any) -> None:
    text = _extract_text(value)
    if text:
        target[key] = text


def _first_present(value: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in value:
            return value[key]
    return None


def _parameter_int(request: _PageRequest, key: str, default: int) -> int:
    parameters = dict(parse_qsl(urlsplit(request.url).query, keep_blank_values=True))
    parameters.update(request.parameter_mapping())
    try:
        return int(parameters.get(key, default))
    except (TypeError, ValueError):
        return default


def _optional_non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _first_non_negative_int(*values: Any) -> int | None:
    for value in values:
        result = _optional_non_negative_int(value)
        if result is not None:
            return result
    return None


def _require_mapping(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    result = value.get(key)
    if not isinstance(result, dict):
        raise SourceConfigurationError(f"{key} must be an object")
    return result


def _require_text(value: Mapping[str, Any], key: str) -> str:
    result = _extract_text(value.get(key))
    if not result:
        raise SourceConfigurationError(f"{key} must be a non-empty string")
    return result


def _text_tuple(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise SourceConfigurationError(f"{label} must be a non-empty string array")
    result = tuple(item for item in (_extract_text(item) for item in value) if item)
    if len(result) != len(value):
        raise SourceConfigurationError(f"{label} must contain only non-empty strings")
    return result


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise SourceConfigurationError(f"{label} must be a positive integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise SourceConfigurationError(f"{label} must be a positive integer") from exc
    if result < 1:
        raise SourceConfigurationError(f"{label} must be a positive integer")
    return result


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _as_utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
