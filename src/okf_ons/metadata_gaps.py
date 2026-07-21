"""Reproducible metadata-gap profiling for generated OKF bundles."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .search import FILTER_FIELDS, filter_values

EVIDENCE_FIELD_ORDER = (
    "identity",
    "description",
    "publisher",
    "licence",
    "contact",
    "release_or_modified",
    "frequency",
    "population",
    "geography",
    "time_coverage",
    "methodology",
    "quality_documentation",
    "revision_status",
    "provenance",
)

_MISSING_STRINGS = {"none", "null", "not-specified", "__missing__"}

# Fixed fields currently rendered through OKF Explorer's gap-label helpers.
# Keys include the view/section because some values are rendered twice.
DATASET_DISPLAY_FIELDS: dict[str, tuple[tuple[str, ...], ...]] = {
    "overview.record_type": (("record_type",), ("type",)),
    "overview.source_adapter": (("source_adapter",),),
    "overview.source_tier": (("source_tier",),),
    "overview.confidence": (("confidence",),),
    "overview.licence": (("license_title",), ("license_id",)),
    "overview.concept_id": (("concept_id",),),
    "overview.access_model": (("access_model",),),
    "overview.visibility": (("visibility",),),
    "overview.contract_status": (("contract_status",),),
    "overview.dcat_type": (("dcat_type",),),
    "overview.openapi_type": (("openapi_type",),),
    "overview.lifecycle": (("lifecycle_status",), ("state",)),
    "overview.area_served": (("area_served",), ("areaServed",)),
    "overview.url": (("url",),),
    "overview.documentation": (("documentation",),),
    "normal.id": (("id",),),
    "normal.state": (("state",),),
    "normal.type": (("type",),),
    "normal.protocol": (("protocol",),),
    "normal.isopen": (("isopen",),),
    "normal.private": (("private",),),
    "normal.metadata_created": (("metadata_created",),),
    "normal.metadata_modified": (("metadata_modified",),),
    "normal.timestamp": (("timestamp",),),
    "normal.formats": (("formats",),),
    "normal.topics": (("topics",),),
    "normal.publisher_concept_id": (("publisher_concept_id",),),
    "normal.groups": (("groups",),),
    "normal.resource_hosts": (("resource_hosts",),),
    "standards.dcat_term": (("standards_alignment", "dcat", "term"), ("dcat_type",)),
    "standards.dcat_export_status": (
        ("standards_alignment", "dcat", "export_status"),
        ("dcat_export_status",),
    ),
    "standards.openapi_term": (
        ("standards_alignment", "openapi", "term"),
        ("openapi_type",),
    ),
    "standards.openapi_export_status": (
        ("standards_alignment", "openapi", "export_status"),
        ("openapi_export_status",),
    ),
    "standards.openapi_security_scheme": (
        ("standards_alignment", "openapi", "security_scheme_type"),
        ("openapi_security_scheme",),
    ),
}

RESOURCE_DISPLAY_FIELDS = tuple(
    "source_format concept_id url govuk_content_path state position created "
    "last_modified metadata_modified size hash schema_url schema_type".split()
)

SEARCH_DISPLAY_FIELDS: dict[str, tuple[tuple[str, ...], ...]] = {
    "record_type": (("record_type",),),
    "source_adapter": (("source_adapter",),),
    "confidence": (("confidence",),),
    "licence": (("license_title",), ("license_id",)),
    "protocol": (("protocol",),),
    "topics": (("topics",),),
    "endpoint_host": (("endpoint_host",),),
    "documentation_host": (("documentation_host",),),
    "access_model": (("access_model",),),
    "contract_status": (("contract_status",),),
    "dcat_type": (("dcat_type",),),
    "openapi_type": (("openapi_type",),),
    "url": (("url",),),
    "documentation": (("documentation",),),
    "timestamp": (("timestamp",),),
}

PUBLISHER_DISPLAY_FIELDS = ("concept_id", "id", "type", "approval_status")


def is_metadata_gap(value: Any) -> bool:
    """Return whether Explorer renders ``value`` as a metadata gap."""

    if value is None or value == "":
        return True
    if isinstance(value, list):
        return not value
    if isinstance(value, str):
        return value.strip().casefold() in _MISSING_STRINGS
    return False


def _nested(record: Mapping[str, Any], path: Sequence[str]) -> Any:
    value: Any = record
    for key in path:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value


def _fallback_value(
    record: Mapping[str, Any], alternatives: Sequence[Sequence[str]]
) -> Any:
    for path in alternatives:
        value = _nested(record, path)
        if not is_metadata_gap(value):
            return value
    return None


def _record_id(record: Mapping[str, Any]) -> str:
    return str(record.get("record_id") or record.get("id") or record.get("name") or "")


def _source(record: Mapping[str, Any]) -> str:
    return str(record.get("source_surface") or record.get("source_adapter") or "not-specified")


def _rate(present: int, possible: int) -> float:
    return round(present / possible, 6) if possible else 0.0


def _field_profile(
    records: Sequence[Mapping[str, Any]],
    fields: Sequence[str],
    present: Callable[[Mapping[str, Any], str], bool],
    *,
    sample_limit: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for field in fields:
        missing_by_source: Counter[str] = Counter()
        samples: list[str] = []
        present_count = 0
        for record in records:
            if present(record, field):
                present_count += 1
                continue
            missing_by_source[_source(record)] += 1
            record_id = _record_id(record)
            if record_id and len(samples) < sample_limit:
                samples.append(record_id)
        missing_count = len(records) - present_count
        rows.append(
            {
                "field": field,
                "present": present_count,
                "missing": missing_count,
                "completeness": _rate(present_count, len(records)),
                "missingBySource": dict(sorted(missing_by_source.items())),
                "sampleMissingRecordIds": samples,
            }
        )
    return rows


def _metric(
    records: Sequence[Mapping[str, Any]],
    fields: Sequence[str],
    present: Callable[[Mapping[str, Any], str], bool],
    *,
    definition: str,
    sample_limit: int,
) -> dict[str, Any]:
    rows = _field_profile(records, fields, present, sample_limit=sample_limit)
    present_count = sum(row["present"] for row in rows)
    possible = len(records) * len(fields)
    return {
        "definition": definition,
        "rowCount": len(records),
        "fieldCount": len(fields),
        "present": present_count,
        "possible": possible,
        "missing": possible - present_count,
        "completeness": _rate(present_count, possible),
        "byField": rows,
    }


def _evidence_present(record: Mapping[str, Any], field: str) -> bool:
    quality = record.get("quality_evidence")
    evidence = quality.get("evidence") if isinstance(quality, Mapping) else None
    return isinstance(evidence, Mapping) and evidence.get(field) is True


def _dataset_display_present(record: Mapping[str, Any], field: str) -> bool:
    if field == "normal.source_licence":
        return any(
            not is_metadata_gap(record.get(key))
            for key in ("license_source_id", "license_source_title")
        )
    return not is_metadata_gap(_fallback_value(record, DATASET_DISPLAY_FIELDS[field]))


def _direct_present(record: Mapping[str, Any], field: str) -> bool:
    return not is_metadata_gap(record.get(field))


def _search_display_present(record: Mapping[str, Any], field: str) -> bool:
    return not is_metadata_gap(_fallback_value(record, SEARCH_DISPLAY_FIELDS[field]))


def _facet_present(record: Mapping[str, Any], field: str) -> bool:
    values = filter_values(dict(record), field)
    return any(not is_metadata_gap(value) for value in values)


def _dynamic_provenance_metric(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    provenance_maps = [
        record.get("provenance")
        if isinstance(record.get("provenance"), Mapping)
        else {}
        for record in records
    ]
    values = [value for provenance in provenance_maps for value in list(provenance.values())[:14]]
    missing = sum(is_metadata_gap(value) for value in values)
    return {
        "definition": (
            "Values in the dynamic provenance rows rendered by Explorer (up to 14 per record)."
        ),
        "present": len(values) - missing,
        "possible": len(values),
        "missing": missing,
        "completeness": _rate(len(values) - missing, len(values)),
    }


def profile_records(
    records: Iterable[Mapping[str, Any]], *, sample_limit: int = 10
) -> dict[str, Any]:
    """Profile canonical evidence, dataset-display, and search-facet gaps."""

    materialised = list(records)
    evidence_fields = list(EVIDENCE_FIELD_ORDER)
    evidence_rows = _field_profile(
        materialised, evidence_fields, _evidence_present, sample_limit=sample_limit
    )

    source_accumulator: dict[str, dict[str, int]] = defaultdict(
        lambda: {"records": 0, "present": 0, "possible": 0}
    )
    score_distribution: Counter[str] = Counter()
    for record in materialised:
        source = _source(record)
        source_accumulator[source]["records"] += 1
        for field in evidence_fields:
            source_accumulator[source]["possible"] += 1
            source_accumulator[source]["present"] += int(_evidence_present(record, field))
        quality = record.get("quality_evidence")
        score = quality.get("score") if isinstance(quality, Mapping) else None
        score_distribution[str(score if score is not None else "not-specified")] += 1

    evidence_present = sum(row["present"] for row in evidence_rows)
    evidence_possible = len(materialised) * len(evidence_fields)
    evidence_missing = evidence_possible - evidence_present
    by_source = []
    for source, values in sorted(source_accumulator.items()):
        possible = values["possible"]
        present_count = values["present"]
        by_source.append(
            {
                "source": source,
                **values,
                "missing": possible - present_count,
                "completeness": _rate(present_count, possible),
            }
        )

    dataset_fields = list(DATASET_DISPLAY_FIELDS)
    dataset_fields.insert(
        dataset_fields.index("normal.publisher_concept_id"), "normal.source_licence"
    )
    return {
        "schema": "okf-ons-metadata-gap-profile.v1",
        "recordCount": len(materialised),
        "evidenceSlotMetric": {
            "definition": (
                "Population of the 14 existing quality_evidence boolean slots across every "
                "record; this is evidence availability, not statistical accuracy."
            ),
            "present": evidence_present,
            "possible": evidence_possible,
            "missing": evidence_missing,
            "completeness": _rate(evidence_present, evidence_possible),
            "halfRemainingGapSlots": evidence_missing // 2,
            "halfRemainingTargetPresent": evidence_present + evidence_missing // 2,
            "halfRemainingTargetCompleteness": _rate(
                evidence_present + evidence_missing // 2, evidence_possible
            ),
            "byField": evidence_rows,
            "bySource": by_source,
            "recordScoreDistribution": dict(
                sorted(score_distribution.items(), key=lambda item: item[0])
            ),
        },
        "explorerDatasetDisplayMetric": _metric(
            materialised,
            dataset_fields,
            _dataset_display_present,
            definition=(
                "Fixed dataset-detail fields that Explorer can render as a metadata gap. "
                "This diagnostic includes duplicated and inapplicable generic fields."
            ),
            sample_limit=sample_limit,
        ),
        "explorerDatasetDynamicProvenanceMetric": _dynamic_provenance_metric(materialised),
        "explorerSearchFacetMetric": _metric(
            materialised,
            list(FILTER_FIELDS),
            _facet_present,
            definition=(
                "Bundle static-search facet fields whose missing value is shown as Not specified. "
                "This metric preserves nested OKF-ONS field semantics."
            ),
            sample_limit=sample_limit,
        ),
    }


def _load_chunks(bundle_dir: Path, paths: Sequence[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for relative in paths:
        payload = json.loads((bundle_dir / relative).read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"Bundle chunk is not an array: {relative}")
        records.extend(row for row in payload if isinstance(row, dict))
    return records


def load_bundle_records(bundle_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    descriptor = json.loads((bundle_dir / "okf-explorer.json").read_text(encoding="utf-8"))
    manifest = json.loads((bundle_dir / "data/manifest.json").read_text(encoding="utf-8"))
    records = _load_chunks(bundle_dir, manifest.get("chunks", {}).get("datasets", []))
    return descriptor, records


def profile_bundle(bundle_dir: Path, *, sample_limit: int = 10) -> dict[str, Any]:
    descriptor, records = load_bundle_records(bundle_dir)
    manifest = json.loads((bundle_dir / "data/manifest.json").read_text(encoding="utf-8"))
    resources = _load_chunks(bundle_dir, manifest.get("chunks", {}).get("resources", []))
    publishers = _load_chunks(bundle_dir, manifest.get("chunks", {}).get("publishers", []))
    search_manifest = json.loads(
        (bundle_dir / "data/search/manifest.json").read_text(encoding="utf-8")
    )
    search_results = _load_chunks(
        bundle_dir, search_manifest.get("entrypoints", {}).get("result_docs", [])
    )

    profile = profile_records(records, sample_limit=sample_limit)
    profile["explorerResourceDisplayMetric"] = _metric(
        resources,
        list(RESOURCE_DISPLAY_FIELDS),
        _direct_present,
        definition=(
            "Fixed resource-detail fields that Explorer can render as a metadata gap. "
            "Most are generic catalogue fields and can be inapplicable to source links."
        ),
        sample_limit=sample_limit,
    )
    profile["explorerResourceDynamicProvenanceMetric"] = _dynamic_provenance_metric(resources)
    profile["explorerSearchResultDisplayMetric"] = _metric(
        search_results,
        list(SEARCH_DISPLAY_FIELDS),
        _search_display_present,
        definition=(
            "Fixed search-result fields that Explorer can render as a metadata gap. "
            "These duplicate canonical records and are not added to the evidence KPI."
        ),
        sample_limit=sample_limit,
    )
    profile["explorerPublisherDisplayMetric"] = _metric(
        publishers,
        list(PUBLISHER_DISPLAY_FIELDS),
        _direct_present,
        definition="Fixed publisher-detail fields that Explorer can render as a metadata gap.",
        sample_limit=sample_limit,
    )
    profile["bundle"] = {
        "version": descriptor.get("version"),
        "snapshot": descriptor.get("snapshot"),
        "recordCount": descriptor.get("counts", {}).get("records"),
    }
    return profile
