"""Normalize ONS metadata into stable, provenance-bearing discovery records."""

from __future__ import annotations

import hashlib
import html
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import urlparse

STOP_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "by",
    "data",
    "dataset",
    "for",
    "from",
    "in",
    "of",
    "on",
    "statistics",
    "the",
    "to",
    "uk",
    "united",
    "kingdom",
    "with",
}

ONS_API_ROOT = "https://api.beta.ons.gov.uk/v1"
NOMIS_ROOT = "https://www.nomisweb.co.uk/api/v01"
OGP_ROOT = "https://geoportal.statistics.gov.uk"
_NATIVE_TABLE_CODE_RE = re.compile(r"^[A-Z]{2}\d{3}$", re.IGNORECASE)
_TITLE_TABLE_CODE_RE = re.compile(
    r"^\s*([A-Z]{2}\d{3}[A-Z]*)\s*(?:[-:–—]|$)",
    re.IGNORECASE,
)


def plain_text(value: Any, limit: int = 10_000) -> str:
    """Return bounded plain text from inconsistent upstream metadata."""

    text = html.unescape(str(value or ""))
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = text.replace("\\r\\n", " ").replace("\\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def slugify(value: Any, fallback: str = "record") -> str:
    text = plain_text(value, 500).casefold()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    if not text:
        text = fallback
    return text[:180].rstrip("-")


def tokenize(*values: Any) -> list[str]:
    text = " ".join(plain_text(value, 50_000).casefold() for value in values)
    return [
        token
        for token in re.findall(r"[a-z0-9][a-z0-9'-]+", text)
        if len(token) >= 2 and token not in STOP_WORDS
    ]


def content_sha256(value: Any) -> str:
    import json

    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _link(value: Any, *keys: str) -> str:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    if isinstance(current, dict):
        current = current.get("href") or current.get("url") or current.get("id")
    return str(current or "")


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        rows = value
    elif value is None or value == "":
        rows = []
    else:
        rows = [value]
    return sorted({plain_text(row, 300) for row in rows if plain_text(row, 300)})


def _contacts(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    output: list[dict[str, str]] = []
    for row in value:
        if not isinstance(row, dict):
            continue
        contact = {
            key: plain_text(row.get(key), 300)
            for key in ("name", "email", "telephone")
            if row.get(key)
        }
        if contact:
            output.append(contact)
    return output


def _version_identity(link: str) -> tuple[str, str, str]:
    match = re.search(r"/datasets/([^/]+)/editions/([^/]+)/versions/([^/?#]+)", link)
    return match.groups() if match else ("", "", "")


def _quality_evidence(record: dict[str, Any]) -> dict[str, Any]:
    evidence = {
        "identity": bool(record.get("native_id") and record.get("source_surface")),
        "description": bool(record.get("notes")),
        "publisher": bool(record.get("publisher_title")),
        "licence": bool(record.get("license_id")),
        "contact": bool(record.get("contacts")),
        "release_or_modified": bool(record.get("metadata_modified")),
        "frequency": bool(record.get("frequency")),
        "population": bool(record.get("population_type")),
        "geography": bool(record.get("geography")),
        "time_coverage": bool(record.get("time_coverage")),
        "methodology": bool(record.get("methodology_links")),
        "quality_documentation": bool(record.get("quality_links")),
        "revision_status": bool(record.get("revision_status")),
        "provenance": bool(record.get("provenance")),
    }
    total = len(evidence)
    present = sum(evidence.values())
    return {
        "schema": "okf-metadata-evidence.v1",
        "label": "metadata evidence availability",
        "score": round(present / total, 3),
        "present": present,
        "possible": total,
        "evidence": evidence,
        "statistical_accuracy_evaluated": False,
        "warning": (
            "This score measures discoverable metadata evidence. It does not "
            "certify statistical accuracy, methodological quality, or fitness for use."
        ),
    }


def _standards_evidence(record: dict[str, Any]) -> dict[str, Any]:
    has_method = bool(record.get("methodology_links"))
    has_quality = bool(record.get("quality_links"))
    has_release = bool(record.get("metadata_modified"))
    has_provenance = bool(record.get("provenance"))
    has_dimensions = bool(record.get("dimensions") or record.get("dimension_count"))
    return {
        "schema": "okf-ons-standards-evidence.v1",
        "claims_are_alignment_not_certification": True,
        "code-of-practice-3.0": {
            "status": "partial",
            "evidence": {
                "trustworthiness": has_release and has_provenance,
                "quality": has_method or has_quality,
                "value": bool(record.get("notes") and record.get("topics")),
            },
        },
        "dcat-3": {
            "status": "aligned",
            "mapped_type": "dcat:Dataset",
            "evidence": bool(record.get("title") and record.get("url")),
        },
        "dqv": {
            "status": "partial",
            "evidence": bool(record.get("quality_evidence")),
        },
        "prov-o": {
            "status": "aligned" if has_provenance else "partial",
            "evidence": has_provenance,
        },
        "sdmx": {
            "status": "aligned" if record.get("source_surface") == "nomis" else "not-applicable",
            "evidence": has_dimensions,
        },
        "data-cube": {
            "status": "partial" if has_dimensions else "not-evaluated",
            "evidence": has_dimensions,
        },
    }


def _base_record(
    *,
    record_id: str,
    native_id: str,
    source_surface: str,
    title: str,
    description: str,
    url: str,
    record_type: str,
    snapshot_id: str,
    retrieved_at: str,
    source_url: str,
    source_sha256: str,
) -> dict[str, Any]:
    name = slugify(record_id)
    host = urlparse(url).hostname or ""
    return {
        "id": record_id,
        "record_id": record_id,
        "native_id": native_id,
        "name": name,
        "title": plain_text(title, 1_000) or native_id,
        "notes": plain_text(description),
        "description": plain_text(description),
        "record_type": record_type,
        "source_surface": source_surface,
        "publisher": "office-for-national-statistics",
        "publisher_title": "Office for National Statistics",
        "route": f"dataset/{name}",
        "open": f"dataset/{name}",
        "url": url,
        "documentation": url,
        "host": host,
        "formats": ["REST/HTTP"],
        "protocol": ["REST/HTTP"],
        "topics": [],
        "tags": [],
        "contacts": [],
        "license_id": "open-government-licence-v3",
        "license_title": "Open Government Licence v3.0",
        "license_source_id": "https://www.ons.gov.uk/help/terms-and-conditions",
        "metadata_modified": "",
        "frequency": "",
        "population_type": "",
        "geography": [],
        "time_coverage": {},
        "methodology_links": [],
        "quality_links": [],
        "revision_status": "",
        "dimension_count": 0,
        "dimensions": [],
        "resource_count": 1,
        "dcat_type": "dcat:Dataset",
        "source_adapter": source_surface,
        "source_tier": "official-provider-metadata",
        "confidence": "declared",
        "provenance": {
            "schema": "okf-provenance.v1",
            "source_url": source_url,
            "source_adapter": source_surface,
            "snapshot_id": snapshot_id,
            "retrieved_at": retrieved_at,
            "source_sha256": source_sha256,
            "native_id": native_id,
        },
    }


def normalize_ons_dataset(
    row: dict[str, Any],
    *,
    snapshot_id: str,
    retrieved_at: str,
    source_sha256: str,
) -> dict[str, Any] | None:
    dataset_id = plain_text(row.get("id"), 300)
    if not dataset_id:
        return None
    self_url = _link(row, "links", "self") or f"{ONS_API_ROOT}/datasets/{dataset_id}"
    record = _base_record(
        record_id=f"ons-data-api:dataset:{dataset_id}",
        native_id=dataset_id,
        source_surface="ons-data-api",
        title=plain_text(row.get("title"), 1_000) or dataset_id,
        description=plain_text(row.get("description")),
        url=self_url,
        record_type="ONS Dataset",
        snapshot_id=snapshot_id,
        retrieved_at=retrieved_at,
        source_url=f"{ONS_API_ROOT}/datasets",
        source_sha256=source_sha256,
    )
    latest_url = _link(row, "links", "latest_version")
    _, edition, version = _version_identity(latest_url)
    based_on = row.get("is_based_on") if isinstance(row.get("is_based_on"), dict) else {}
    if edition and version:
        selection_tool = "ons_data.dimensions"
        selection_arguments = {
            "dataset": dataset_id,
            "edition": edition,
            "version": version,
        }
        selection_reason = "Dataset-specific dimension options must be selected before querying."
    elif edition:
        selection_tool = "ons_data.versions"
        selection_arguments = {"dataset": dataset_id, "edition": edition}
        selection_reason = "Select an exact version before inspecting dimensions."
    else:
        selection_tool = "ons_data.editions"
        selection_arguments = {"dataset": dataset_id}
        selection_reason = "Select an exact edition and version before inspecting dimensions."
    record.update(
        {
            "topics": _string_list(row.get("keywords")),
            "tags": _string_list(row.get("keywords")),
            "contacts": _contacts(row.get("contacts")),
            "metadata_modified": plain_text(row.get("last_updated"), 100),
            "frequency": plain_text(row.get("release_frequency"), 200),
            "population_type": plain_text(based_on.get("id"), 300),
            "state": plain_text(row.get("state"), 100) or "published",
            "canonical_topic": plain_text(row.get("canonical_topic"), 200),
            "latest_edition": edition,
            "latest_version": version,
            "latest_version_url": latest_url,
            "dimensions": row.get("dimensions") if isinstance(row.get("dimensions"), list) else [],
            "dimension_count": int(row.get("dimension_count") or 0),
            "methodology_links": _string_list(row.get("methodology_links")),
            "quality_links": _string_list(row.get("quality_links")),
            "selection": {
                "schema": "okf-ons-selection-binding.v1",
                "tool": selection_tool,
                "arguments": selection_arguments,
                "query_tool": "ons_data.query",
                "mcp_available": True,
                "binding_status": "available",
                "complete": False,
                "reason": selection_reason,
            },
        }
    )
    record["quality_evidence"] = _quality_evidence(record)
    record["quality"] = {
        "overall": record["quality_evidence"]["score"],
        "label": "metadata evidence availability",
        "statistical_accuracy_evaluated": False,
    }
    record["quality_score"] = record["quality"]["overall"]
    record["standards_evidence"] = _standards_evidence(record)
    return record


def _nomis_value(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("value", "#text", "text", "name"):
            if value.get(key):
                return plain_text(value[key])
    return plain_text(value)


def normalize_nomis_dataset(
    row: dict[str, Any],
    *,
    snapshot_id: str,
    retrieved_at: str,
    source_sha256: str,
) -> dict[str, Any] | None:
    dataset_id = plain_text(row.get("id") or row.get("agencyid"), 300)
    if not dataset_id:
        return None
    title = _nomis_value(row.get("name")) or dataset_id
    annotations = row.get("annotations", {}).get("annotation", [])
    if isinstance(annotations, dict):
        annotations = [annotations]
    annotation_text = " ".join(
        _nomis_value(annotation.get("annotationtext"))
        for annotation in annotations
        if isinstance(annotation, dict)
    )
    description = plain_text(row.get("description")) or annotation_text
    url = f"{NOMIS_ROOT}/dataset/{dataset_id}.overview.json"
    record = _base_record(
        record_id=f"nomis:dataset:{dataset_id}",
        native_id=dataset_id,
        source_surface="nomis",
        title=title,
        description=description,
        url=url,
        record_type="Nomis Dataset",
        snapshot_id=snapshot_id,
        retrieved_at=retrieved_at,
        source_url=f"{NOMIS_ROOT}/dataset/def.sdmx.json",
        source_sha256=source_sha256,
    )
    record.update(
        {
            "formats": ["SDMX-JSON", "JSON", "CSV", "XLS"],
            "protocol": ["SDMX", "REST/HTTP"],
            "topics": _string_list(row.get("keywords")),
            "tags": ["nomis", "sdmx"],
            "state": "published",
            "selection": {
                "schema": "okf-ons-selection-binding.v1",
                "tool": "nomis.datasets",
                "arguments": {"dataset": dataset_id},
                "query_tool": "nomis.query",
                "mcp_available": True,
                "binding_status": "available",
                "complete": False,
                "reason": "Nomis dimensions and codelist values must be selected before querying.",
            },
        }
    )
    record["quality_evidence"] = _quality_evidence(record)
    record["quality"] = {
        "overall": record["quality_evidence"]["score"],
        "label": "metadata evidence availability",
        "statistical_accuracy_evaluated": False,
    }
    record["quality_score"] = record["quality"]["overall"]
    record["standards_evidence"] = _standards_evidence(record)
    return record


def normalize_ogp_dataset(
    feature: dict[str, Any],
    *,
    snapshot_id: str,
    retrieved_at: str,
    source_sha256: str,
) -> dict[str, Any] | None:
    properties = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
    item_id = plain_text(feature.get("id") or properties.get("id"), 500)
    if not item_id:
        return None
    title = plain_text(properties.get("title") or properties.get("name"), 1_000) or item_id
    description = plain_text(
        properties.get("description") or properties.get("snippet") or properties.get("summary")
    )
    url = plain_text(
        properties.get("url")
        or properties.get("landingPage")
        or properties.get("landing_page")
        or f"{OGP_ROOT}/datasets/{item_id}"
    )
    record = _base_record(
        record_id=f"ons-open-geography:dataset:{item_id}",
        native_id=item_id,
        source_surface="ons-open-geography",
        title=title,
        description=description,
        url=url,
        record_type="ONS Geography Dataset",
        snapshot_id=snapshot_id,
        retrieved_at=retrieved_at,
        source_url=f"{OGP_ROOT}/api/search/v1/collections/dataset/items",
        source_sha256=source_sha256,
    )
    bbox = feature.get("bbox") or properties.get("bbox") or []
    if isinstance(bbox, list) and len(bbox) >= 4:
        bbox = [float(value) for value in bbox[:4]]
    else:
        bbox = []
    modified = (
        properties.get("modified")
        or properties.get("updated")
        or properties.get("modified_at")
        or feature.get("time")
        or ""
    )
    keywords = properties.get("keywords") or properties.get("tags") or []
    record.update(
        {
            "topics": _string_list(keywords) or ["Geography"],
            "tags": _string_list(keywords) + ["open-geography"],
            "metadata_modified": plain_text(modified, 100),
            "state": plain_text(properties.get("status"), 100) or "published",
            "geography": _string_list(
                properties.get("geography")
                or properties.get("spatial")
                or properties.get("coverage")
            ),
            "spatial": {"bbox": bbox, "crs": "EPSG:4326"} if bbox else {},
            "formats": _string_list(properties.get("formats")) or ["Download/Service"],
            "selection": {
                "schema": "okf-ons-selection-binding.v1",
                "arguments": {},
                "mcp_available": False,
                "binding_status": "planned",
                "complete": False,
                "read_only": True,
                "direct_metadata_url": url,
                "reason": (
                    "The current MCP-Geo server has no general Open Geography catalogue "
                    "item tool. Use the source URL for metadata; an MCP binding is planned."
                ),
            },
        }
    )
    record["quality_evidence"] = _quality_evidence(record)
    record["quality"] = {
        "overall": record["quality_evidence"]["score"],
        "label": "metadata evidence availability",
        "statistical_accuracy_evaluated": False,
    }
    record["quality_score"] = record["quality"]["overall"]
    record["standards_evidence"] = _standards_evidence(record)
    return record


def _reference_links(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted(
        {
            plain_text(item.get("href"), 2_000)
            for item in value
            if isinstance(item, Mapping) and item.get("href")
        }
    )


def _projected_url(record: Mapping[str, Any], *relations: str) -> str:
    links = record.get("links")
    if not isinstance(links, Mapping):
        return ""
    for relation in relations:
        value = links.get(relation)
        if isinstance(value, Mapping):
            url = value.get("href")
        else:
            url = value
        if url:
            return plain_text(url, 2_000)
    return ""


def _retrieved_at(provenance: Mapping[str, Any]) -> str:
    pages = provenance.get("pages")
    if not isinstance(pages, list):
        return ""
    timestamps = sorted(
        plain_text(page.get("retrievedAt"), 100)
        for page in pages
        if isinstance(page, Mapping) and page.get("retrievedAt")
    )
    return timestamps[-1] if timestamps else ""


def _finalise_projected_record(
    record: dict[str, Any],
    projected: Mapping[str, Any],
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    """Attach acquisition provenance and evidence fields to a canonical record."""

    source = provenance.get("source")
    source = source if isinstance(source, Mapping) else {}
    native_id = plain_text(projected.get("sourceRecordId"), 500)
    record["source_adapter"] = plain_text(source.get("adapter"), 200) or record["source_surface"]
    record["source_record_kind"] = plain_text(projected.get("recordKind"), 200) or "dataset"
    record["provenance"] = {
        "schema": "okf-provenance.v1",
        "source_url": plain_text(source.get("endpoint"), 2_000)
        or record["provenance"]["source_url"],
        "source_adapter": record["source_adapter"],
        "source_id": plain_text(source.get("id"), 300) or record["source_surface"],
        "snapshot_id": record["provenance"]["snapshot_id"],
        "retrieved_at": record["provenance"]["retrieved_at"],
        "source_sha256": plain_text(provenance.get("recordSetSha256"), 200)
        or record["provenance"]["source_sha256"],
        "native_id": native_id,
    }
    record["identity"] = {
        "dataset_id": native_id,
        "edition": record.get("latest_edition") or "",
        "version": record.get("latest_version") or "",
    }
    record["publication"] = {
        "release_date": record.get("first_released") or "",
        "revision_status": record.get("revision_status") or "",
        "state": record.get("state") or "",
    }
    record["statistical"] = {
        "measure": record.get("measure") or "",
        "unit": record.get("unit_of_measure") or "",
        "population": record.get("population_type") or "",
        "geography": record.get("geography") or [],
        "time_coverage": record.get("time_coverage") or {},
        "frequency": record.get("frequency") or "",
        "dimensions": record.get("dimensions") or [],
        "revision_status": record.get("revision_status") or "",
        "quality_notes": sorted(
            {
                *record.get("methodology_links", []),
                *record.get("quality_links", []),
            }
        ),
    }
    record["quality_evidence"] = _quality_evidence(record)
    record["quality"] = {
        "overall": record["quality_evidence"]["score"],
        "label": "metadata evidence availability",
        "statistical_accuracy_evaluated": False,
    }
    record["quality_score"] = record["quality"]["overall"]
    record["standards_evidence"] = _standards_evidence(record)
    return record


def normalize_acquisition_record(
    projected: Mapping[str, Any],
    *,
    snapshot_id: str,
    provenance: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Compile a public ``AcquisitionResult`` projection into an Explorer record."""

    source_id = plain_text(projected.get("sourceId"), 300)
    native_id = plain_text(projected.get("sourceRecordId"), 500)
    if not source_id or not native_id:
        return None
    retrieved_at = _retrieved_at(provenance)
    source_sha256 = plain_text(provenance.get("recordSetSha256"), 200)
    title = plain_text(projected.get("title"), 1_000) or native_id
    description = plain_text(projected.get("description"))
    keywords = _string_list(projected.get("keywords"))

    if source_id == "ons-data-api":
        raw = {
            "id": native_id,
            "title": title,
            "description": description,
            "state": projected.get("lifecycleState"),
            "last_updated": projected.get("lastUpdated"),
            "release_frequency": projected.get("releaseFrequency"),
            "keywords": keywords,
            "links": projected.get("links"),
            "methodology_links": _reference_links(projected.get("methodologies")),
            "quality_links": _reference_links(projected.get("qualityMethodologyInformation")),
        }
        record = normalize_ons_dataset(
            raw,
            snapshot_id=snapshot_id,
            retrieved_at=retrieved_at,
            source_sha256=source_sha256,
        )
        if record is None:
            return None
        record.update(
            {
                "unit_of_measure": plain_text(projected.get("unitOfMeasure"), 300),
                "next_release": plain_text(projected.get("nextRelease"), 100),
                "national_statistic": projected.get("nationalStatistic"),
                "related_datasets": projected.get("relatedDatasets", []),
                "themes": projected.get("themes", []),
            }
        )
    elif source_id == "nomis-dataset-definitions":
        raw = {
            "id": native_id,
            "name": title,
            "description": description,
            "agencyid": projected.get("agencyId"),
            "keywords": keywords,
        }
        record = normalize_nomis_dataset(
            raw,
            snapshot_id=snapshot_id,
            retrieved_at=retrieved_at,
            source_sha256=source_sha256,
        )
        if record is None:
            return None
        components = (
            projected.get("components") if isinstance(projected.get("components"), list) else []
        )
        dimensions = [
            component
            for component in components
            if isinstance(component, Mapping)
            and component.get("kind") in {"dimension", "timedimension"}
        ]
        record.update(
            {
                "metadata_modified": plain_text(projected.get("lastUpdated"), 100),
                "unit_of_measure": plain_text(projected.get("unitOfMeasure"), 300),
                "dimensions": dimensions,
                "dimension_count": len(dimensions),
                "definition_version": plain_text(projected.get("definitionVersion"), 100),
                "agency_id": plain_text(projected.get("agencyId"), 200),
                "content_source": plain_text(projected.get("contentSource"), 500),
                "first_released": plain_text(projected.get("firstReleased"), 100),
                "mnemonic": plain_text(projected.get("mnemonic"), 300),
                "publisher_uri": plain_text(projected.get("publisherUri"), 1_000),
                "annotations": projected.get("annotations", []),
            }
        )
    elif source_id == "ons-open-geography":
        item_url = _projected_url(projected, "item")
        feature = {
            "id": native_id,
            "bbox": projected.get("spatialEnvelope", []),
            "properties": {
                "title": title,
                "description": description,
                "url": item_url,
                "modified": projected.get("modified"),
                "created": projected.get("created"),
                "keywords": keywords,
                "status": projected.get("lifecycleState"),
                "formats": [projected.get("itemType")] if projected.get("itemType") else [],
                "geography": projected.get("classification") or projected.get("categories"),
            },
        }
        record = normalize_ogp_dataset(
            feature,
            snapshot_id=snapshot_id,
            retrieved_at=retrieved_at,
            source_sha256=source_sha256,
        )
        if record is None:
            return None
        record.update(
            {
                "access": plain_text(projected.get("access"), 500),
                "access_information": plain_text(projected.get("accessInformation"), 2_000),
                "source_licence": plain_text(projected.get("licence"), 2_000),
                "portal_owner": plain_text(projected.get("owner"), 500),
                "source_organisation": plain_text(projected.get("source"), 500),
                "spatial_reference": projected.get("spatialReference", {}),
                "portal_extent": projected.get("portalExtent", {}),
                "temporal_extent": projected.get("temporalExtent", {}),
            }
        )
    else:
        raise ValueError(f"Unsupported acquisition source id {source_id!r}")

    return _finalise_projected_record(record, projected, provenance)


def _contrast_values(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "source surface": record.get("source_surface") or "",
        "record type": record.get("record_type") or "",
        "frequency": record.get("frequency") or "",
        "population": record.get("population_type") or "",
        "geography": record.get("geography") or [],
        "time coverage": record.get("time_coverage") or {},
        "edition": record.get("latest_edition") or "",
        "version": record.get("latest_version") or "",
        "release state": record.get("state") or "",
        "last updated": record.get("metadata_modified") or "",
        "methodology evidence": bool(record.get("methodology_links")),
        "quality documentation": bool(record.get("quality_links")),
    }


def _has_contrast_value(value: Any) -> bool:
    return value not in (None, "", [], {})


def declared_table_codes(record: Mapping[str, Any]) -> list[str]:
    """Return table codes observed in native identity or a title prefix."""

    codes: set[str] = set()
    native_id = plain_text(record.get("native_id"), 200).upper()
    if _NATIVE_TABLE_CODE_RE.fullmatch(native_id):
        codes.add(native_id)
    title_match = _TITLE_TABLE_CODE_RE.match(plain_text(record.get("title"), 1_000))
    if title_match:
        codes.add(title_match.group(1).upper())
    return sorted(codes)


def _normalised_table_title(title: str) -> str:
    without_code = _TITLE_TABLE_CODE_RE.sub("", plain_text(title, 1_000), count=1)
    words = without_code.casefold().replace("&", "and")
    return re.sub(r"[^a-z0-9]+", " ", words).strip()


def build_cross_source_reconciliation(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Link cross-source representations only when a declared table code agrees."""

    by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        codes = declared_table_codes(record)
        record["declared_table_codes"] = codes
        for code in codes:
            by_code[code].append(record)

    relationships: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    matched_codes: list[str] = []
    title_aligned_codes: list[str] = []
    title_conflicted_codes: list[dict[str, Any]] = []
    disambiguated_candidates: list[dict[str, Any]] = []
    anchor_codes = {
        code
        for code, rows in by_code.items()
        if any(row.get("source_surface") == "ons-data-api" for row in rows)
    }
    unmatched_codes: list[str] = []
    for code in sorted(anchor_codes):
        rows = by_code[code]
        anchors = [row for row in rows if row.get("source_surface") == "ons-data-api"]
        if len(anchors) != 1:
            conflicts.append(
                {
                    "code": code,
                    "reason": "ambiguous-anchor-source",
                    "source": "ons-data-api",
                    "record_ids": sorted(str(row["id"]) for row in anchors),
                }
            )
            continue
        anchor = anchors[0]
        candidates = [row for row in rows if row.get("source_surface") != "ons-data-api"]
        if not candidates:
            unmatched_codes.append(code)
            continue

        anchor_title = _normalised_table_title(str(anchor.get("title") or ""))
        exact_title_candidates = [
            row
            for row in candidates
            if _normalised_table_title(str(row.get("title") or "")) == anchor_title
        ]
        if len(exact_title_candidates) == 1:
            candidate = exact_title_candidates[0]
            if len(candidates) > 1:
                disambiguated_candidates.append(
                    {
                        "code": code,
                        "selected_record_id": candidate["id"],
                        "evidence": "unique-normalised-title-match",
                        "rejected_record_ids": sorted(
                            str(row["id"]) for row in candidates if row is not candidate
                        ),
                    }
                )
        elif len(candidates) == 1:
            candidate = candidates[0]
        else:
            conflicts.append(
                {
                    "code": code,
                    "reason": "ambiguous-cross-source-candidates",
                    "anchor_record_id": anchor["id"],
                    "candidate_record_ids": sorted(str(row["id"]) for row in candidates),
                    "normalised_title_match_count": len(exact_title_candidates),
                }
            )
            continue

        matched_codes.append(code)
        candidate_title = _normalised_table_title(str(candidate.get("title") or ""))
        title_alignment = (
            "normalised-identical" if anchor_title == candidate_title else "conflicted"
        )
        if title_alignment == "normalised-identical":
            title_aligned_codes.append(code)
        else:
            title_conflicted_codes.append(
                {
                    "code": code,
                    "source_title": anchor["title"],
                    "target_title": candidate["title"],
                }
            )
        relationships.append(
            {
                "source": anchor["route"],
                "target": candidate["route"],
                "kind": "cross-source-representation",
                "confidence": "observed-identifier",
                "evidence_type": "shared-declared-statistical-table-code",
                "shared_code": code,
                "source_native_id": anchor["native_id"],
                "target_native_id": candidate["native_id"],
                "source_record_id": anchor["id"],
                "target_record_id": candidate["id"],
                "title_alignment": title_alignment,
                "statistical_equivalence_asserted": False,
                "note": (
                    "The shared declared table code supports cross-source "
                    "reconciliation, not statistical equivalence."
                ),
            }
        )

    report = {
        "schema": "okf-ons-cross-source-reconciliation.v1",
        "method": "declared-native-id-or-title-prefix-table-code",
        "statistical_equivalence_asserted": False,
        "anchor_source": "ons-data-api",
        "anchor_codes_detected": len(anchor_codes),
        "matched_codes": matched_codes,
        "matched_code_count": len(matched_codes),
        "title_aligned_code_count": len(set(title_aligned_codes)),
        "title_conflicted_code_count": len(title_conflicted_codes),
        "title_conflicts": title_conflicted_codes,
        "unmatched_anchor_codes": unmatched_codes,
        "unmatched_anchor_code_count": len(unmatched_codes),
        "relationship_count": len(relationships),
        "candidate_disambiguation_count": len(disambiguated_candidates),
        "candidate_disambiguations": disambiguated_candidates,
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
    }
    return relationships, report


def build_alternatives(
    records: list[dict[str, Any]],
    *,
    limit: int = 4,
    threshold: float = 0.32,
) -> list[dict[str, Any]]:
    """Attach deterministic, evidence-backed alternatives to records."""

    token_sets: list[set[str]] = []
    inverted: dict[str, list[int]] = defaultdict(list)
    for ordinal, record in enumerate(records):
        tokens = set(
            tokenize(
                record.get("title"),
                " ".join(record.get("topics") or []),
                " ".join(record.get("tags") or []),
            )
        )
        token_sets.append(tokens)
        for token in tokens:
            inverted[token].append(ordinal)

    relationships: list[dict[str, Any]] = []
    for ordinal, record in enumerate(records):
        tokens = token_sets[ordinal]
        candidates: set[int] = set()
        for token in tokens:
            if len(inverted[token]) <= 500:
                candidates.update(inverted[token])
        candidates.discard(ordinal)
        scored: list[tuple[float, int, list[str]]] = []
        for other_ordinal in candidates:
            other = token_sets[other_ordinal]
            union = tokens | other
            if not union:
                continue
            shared = sorted(tokens & other)
            title_a = set(tokenize(record.get("title")))
            title_b = set(tokenize(records[other_ordinal].get("title")))
            title_union = title_a | title_b
            title_score = len(title_a & title_b) / len(title_union) if title_union else 0.0
            score = 0.75 * title_score + 0.25 * (len(shared) / len(union))
            if score >= threshold:
                scored.append((score, other_ordinal, shared))
        scored.sort(key=lambda item: (-item[0], records[item[1]]["title"], records[item[1]]["id"]))

        alternatives: list[dict[str, Any]] = []
        left = _contrast_values(record)
        for score, other_ordinal, shared in scored[:limit]:
            other_record = records[other_ordinal]
            right = _contrast_values(other_record)
            differences = [
                {"field": field, "selected": left[field], "alternative": right[field]}
                for field in left
                if left[field] != right[field]
                and (_has_contrast_value(left[field]) or _has_contrast_value(right[field]))
            ]
            relationship_type = (
                "cross-source-alternative"
                if record.get("source_surface") != other_record.get("source_surface")
                else "alternative"
            )
            alternative = {
                "record_id": other_record["id"],
                "title": other_record["title"],
                "route": other_record["route"],
                "source_surface": other_record["source_surface"],
                "record_type": other_record["record_type"],
                "relationship_type": relationship_type,
                "similarity": round(score, 3),
                "shared_terms": shared[:12],
                "differences": differences,
                "not_enough_evidence": not bool(differences),
            }
            alternatives.append(alternative)
            relationships.append(
                {
                    "source": record["route"],
                    "target": other_record["route"],
                    "kind": relationship_type,
                    "confidence": "inferred",
                    "evidence_type": "deterministic-title-topic-similarity",
                    "score": round(score, 3),
                    "shared_terms": shared[:12],
                    "differences": differences,
                    "statistical_equivalence_asserted": False,
                }
            )
        record["alternatives"] = alternatives
        record["alternative_count"] = len(alternatives)
        if alternatives:
            titles = "; ".join(row["title"] for row in alternatives[:3])
            record["context_note"] = f"Compare before selecting: {titles}."
        else:
            record["context_note"] = "No close alternative was identified from available metadata."
    return relationships


def unique_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for record in records:
        record_id = str(record.get("id") or "")
        if record_id and record_id not in by_id:
            by_id[record_id] = record
    return sorted(
        by_id.values(),
        key=lambda row: (
            str(row.get("source_surface") or ""),
            str(row.get("title") or "").casefold(),
            str(row.get("id") or ""),
        ),
    )
