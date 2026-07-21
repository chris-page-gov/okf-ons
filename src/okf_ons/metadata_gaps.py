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

EXPLORER_METRIC_KEYS = (
    "explorerDatasetDisplayMetric",
    "explorerDatasetDynamicProvenanceMetric",
    "explorerResourceDisplayMetric",
    "explorerResourceDynamicProvenanceMetric",
    "explorerSearchResultDisplayMetric",
    "explorerPublisherDisplayMetric",
    "explorerSearchFacetMetric",
)

# These exclusions are deliberately narrow. A field is removed from the
# applicable denominator only when the record class makes the concept itself
# inapplicable; uncertainty remains ``not-evidenced``.
EVIDENCE_NOT_APPLICABLE_RULES = (
    {
        "ruleId": "geospatial-reference-has-no-statistical-universe",
        "sourceSurface": "ons-open-geography",
        "field": "population",
        "rationale": (
            "An Open Geography boundary, code or lookup asset is a geospatial "
            "reference product, not a statistical population or universe."
        ),
    },
)


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


def _evidence_state(record: Mapping[str, Any], field: str) -> str:
    if _evidence_present(record, field):
        return "present"
    for rule in EVIDENCE_NOT_APPLICABLE_RULES:
        if (
            record.get("source_surface") == rule["sourceSurface"]
            and field == rule["field"]
        ):
            return "not-applicable"
    conflicts = record.get("metadata_conflicts")
    if isinstance(conflicts, Mapping) and conflicts.get(field):
        return "conflicted"
    return "not-evidenced"


def _applicability_metric(
    records: Sequence[Mapping[str, Any]], fields: Sequence[str]
) -> dict[str, Any]:
    state_names = ("present", "not-applicable", "not-evidenced", "conflicted")
    by_field = []
    by_source_counts: dict[str, Counter[str]] = defaultdict(Counter)
    total: Counter[str] = Counter()
    for field in fields:
        counts: Counter[str] = Counter()
        for record in records:
            state = _evidence_state(record, field)
            counts[state] += 1
            by_source_counts[_source(record)][state] += 1
        total.update(counts)
        by_field.append(
            {
                "field": field,
                **{state: counts[state] for state in state_names},
                "applicablePossible": len(records) - counts["not-applicable"],
            }
        )
    applicable_possible = len(records) * len(fields) - total["not-applicable"]
    return {
        "definition": (
            "The same evidence inventory with only explicit record-class exclusions removed "
            "from the denominator. Uncertain applicability remains not-evidenced."
        ),
        "present": total["present"],
        "applicablePossible": applicable_possible,
        "completeness": _rate(total["present"], applicable_possible),
        "states": {state: total[state] for state in state_names},
        "rules": list(EVIDENCE_NOT_APPLICABLE_RULES),
        "byField": by_field,
        "bySource": [
            {
                "source": source,
                **{state: counts[state] for state in state_names},
                "applicablePossible": sum(counts.values()) - counts["not-applicable"],
            }
            for source, counts in sorted(by_source_counts.items())
        ],
    }


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


def _index_rows(rows: Any, key: str) -> dict[str, Mapping[str, Any]]:
    if not isinstance(rows, list):
        return {}
    return {
        str(row[key]): row
        for row in rows
        if isinstance(row, Mapping) and row.get(key) is not None
    }


def _metric_delta(
    baseline: Mapping[str, Any], current: Mapping[str, Any]
) -> dict[str, Any]:
    baseline_possible = int(baseline.get("possible") or 0)
    current_possible = int(current.get("possible") or 0)
    if baseline_possible != current_possible:
        raise ValueError(
            "Cannot compare metadata metrics with different denominators: "
            f"{baseline_possible} != {current_possible}"
        )
    baseline_present = int(baseline.get("present") or 0)
    current_present = int(current.get("present") or 0)
    added = current_present - baseline_present
    return {
        "baselinePresent": baseline_present,
        "currentPresent": current_present,
        "possible": current_possible,
        "addedPresent": added,
        "remainingMissing": current_possible - current_present,
        "percentagePointChange": round(100 * added / current_possible, 6)
        if current_possible
        else 0.0,
    }


def compare_profiles(
    baseline: Mapping[str, Any],
    current: Mapping[str, Any],
    *,
    elapsed_seconds: float | None = None,
) -> dict[str, Any]:
    """Compare two fixed-denominator profiles and report enrichment yield."""

    baseline_records = int(baseline.get("recordCount") or 0)
    current_records = int(current.get("recordCount") or 0)
    if baseline_records != current_records:
        raise ValueError(
            "Cannot compare profiles with different record counts: "
            f"{baseline_records} != {current_records}"
        )

    baseline_evidence = baseline.get("evidenceSlotMetric")
    current_evidence = current.get("evidenceSlotMetric")
    if not isinstance(baseline_evidence, Mapping) or not isinstance(
        current_evidence, Mapping
    ):
        raise ValueError("Both profiles must contain evidenceSlotMetric")
    evidence_delta = _metric_delta(baseline_evidence, current_evidence)
    baseline_missing = int(baseline_evidence.get("missing") or 0)
    evidence_delta["baselineMissingClosed"] = (
        round(evidence_delta["addedPresent"] / baseline_missing, 6)
        if baseline_missing
        else 0.0
    )
    if elapsed_seconds is not None:
        if elapsed_seconds <= 0:
            raise ValueError("elapsed_seconds must be greater than zero")
        evidence_delta["elapsedSeconds"] = round(elapsed_seconds, 3)
        evidence_delta["slotsPerHour"] = round(
            evidence_delta["addedPresent"] * 3600 / elapsed_seconds, 3
        )

    field_baseline = _index_rows(baseline_evidence.get("byField"), "field")
    field_current = _index_rows(current_evidence.get("byField"), "field")
    evidence_delta["byField"] = [
        {
            "field": field,
            "addedPresent": int(field_current[field].get("present") or 0)
            - int(field_baseline[field].get("present") or 0),
            "remainingMissing": int(field_current[field].get("missing") or 0),
        }
        for field in EVIDENCE_FIELD_ORDER
        if field in field_baseline and field in field_current
    ]

    source_baseline = _index_rows(baseline_evidence.get("bySource"), "source")
    source_current = _index_rows(current_evidence.get("bySource"), "source")
    evidence_delta["bySource"] = [
        {
            "source": source,
            "addedPresent": int(source_current[source].get("present") or 0)
            - int(source_baseline[source].get("present") or 0),
            "remainingMissing": int(source_current[source].get("missing") or 0),
        }
        for source in sorted(source_baseline.keys() & source_current.keys())
    ]

    explorer_deltas = {}
    for key in EXPLORER_METRIC_KEYS:
        baseline_metric = baseline.get(key)
        current_metric = current.get(key)
        if isinstance(baseline_metric, Mapping) and isinstance(current_metric, Mapping):
            explorer_deltas[key] = _metric_delta(baseline_metric, current_metric)

    applicability_delta = None
    baseline_applicability = baseline.get("applicabilityAwareEvidenceMetric")
    current_applicability = current.get("applicabilityAwareEvidenceMetric")
    if isinstance(baseline_applicability, Mapping) and isinstance(
        current_applicability, Mapping
    ):
        applicability_delta = _metric_delta(
            {
                "present": baseline_applicability.get("present"),
                "possible": baseline_applicability.get("applicablePossible"),
            },
            {
                "present": current_applicability.get("present"),
                "possible": current_applicability.get("applicablePossible"),
            },
        )
        baseline_states = baseline_applicability.get("states")
        current_states = current_applicability.get("states")
        if isinstance(baseline_states, Mapping) and isinstance(current_states, Mapping):
            applicability_delta["stateChanges"] = {
                state: int(current_states.get(state) or 0)
                - int(baseline_states.get(state) or 0)
                for state in (
                    "present",
                    "not-applicable",
                    "not-evidenced",
                    "conflicted",
                )
            }

    result = {
        "schema": "okf-ons-metadata-gap-comparison.v1",
        "recordCount": current_records,
        "baselineBundle": baseline.get("bundle", {}),
        "currentBundle": current.get("bundle", {}),
        "evidenceSlotDelta": evidence_delta,
        "explorerMetricDeltas": explorer_deltas,
    }
    if applicability_delta is not None:
        result["applicabilityAwareDelta"] = applicability_delta
    return result


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
        "applicabilityAwareEvidenceMetric": _applicability_metric(
            materialised, evidence_fields
        ),
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
