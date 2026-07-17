"""Compile a frozen ONS metadata snapshot into a deterministic OKF bundle."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import tempfile
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .evaluation import evaluate_rankings, load_gold_suite
from .model import (
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
        if provenance.get("recordCount") != len(source_records):
            raise BuildError(f"Acquisition record count mismatch: {filename}")
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
            "documentation": record.get("documentation", ""),
            "format": next(iter(record.get("formats", [])), "Metadata"),
            "formats": record.get("formats", []),
            "protocol": record.get("protocol", []),
            "resource_type": "metadata",
            "position": 0,
            "source_surface": record.get("source_surface"),
            "selection": record.get("selection", {}),
            "provenance": record.get("provenance", {}),
            "metadata_only": True,
        }
        for record in records
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
    for source in ("nomis", "ons-open-geography"):
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
    report["release_gate"] = {
        "enabled": False,
        "reason": (
            "The baseline runs all questions, but 18 curated aliases are explicitly "
            "unresolved by the three implemented source lanes."
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
    generated_at = _generated_at(corpus)
    source_counts = _source_counts(corpus.records)
    record_type_counts = dict(
        sorted(Counter(record["record_type"] for record in corpus.records).items())
    )

    dataset_chunks = _chunks(writer, "datasets", corpus.records)
    resource_chunks = _chunks(writer, "resources", resources)
    relationship_chunks = _chunks(writer, "relationships", relationships)
    publisher_chunks = _chunks(
        writer,
        "publishers",
        [
            {
                "id": "office-for-national-statistics",
                "name": "office-for-national-statistics",
                "title": "Office for National Statistics",
                "route": "publisher/office-for-national-statistics",
                "url": "https://www.ons.gov.uk/",
                "dataset_count": len(corpus.records),
                "resource_count": len(resources),
                "description": (
                    "Publisher aggregation for the three implemented ONS metadata lanes."
                ),
            }
        ],
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
        },
    )
    writer.write_json("data/coverage/ledger.json", coverage)
    writer.write_json("data/standards/evaluation.json", standards_evaluation)
    writer.write_json("data/standards/register.json", corpus.standards_register)
    writer.write_json("data/standards/ontology-crosswalk.json", corpus.ontology_crosswalk)
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
            "publishers": 1,
            "resources": len(resources),
            "relationships": len(relationships),
            "records": len(corpus.records),
        },
        "indexes": {
            "overview": "data/overview.json",
            "analysis": "data/analysis/overview.json",
            "facets": "data/facets.json",
            "search": "data/search/manifest.json",
            "coverage": "data/coverage/ledger.json",
            "reconciliation": "data/reconciliation/report.json",
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
            "dcat": "http://www.w3.org/ns/dcat#",
            "dct": "http://purl.org/dc/terms/",
            "dqv": "http://www.w3.org/ns/dqv#",
            "prov": "http://www.w3.org/ns/prov#",
            "skos": "http://www.w3.org/2004/02/skos/core#",
            "Dataset": "dcat:Dataset",
            "title": "dct:title",
            "description": "dct:description",
            "identifier": "dct:identifier",
            "publisher": {"@id": "dct:publisher", "@type": "@id"},
            "landingPage": {"@id": "dcat:landingPage", "@type": "@id"},
            "conformsTo": {"@id": "dct:conformsTo", "@type": "@id"},
            "wasDerivedFrom": {"@id": "prov:wasDerivedFrom", "@type": "@id"},
        }
    }
    writer.write_json("context/okf-ons.jsonld", context)
    semantic_bundle = {
        "@context": f"{PUBLIC_ROOT}context/okf-ons.jsonld",
        "@id": f"{PUBLIC_ROOT}okf-bundle.jsonld",
        "@type": "dcat:Catalog",
        "title": "ONS data discovery OKF",
        "description": (
            "Metadata-only demonstrator built from three official ONS catalogue lanes."
        ),
        "publisher": "https://www.ons.gov.uk/",
        "conformsTo": [
            "https://www.w3.org/TR/vocab-dcat-3/",
            "https://www.w3.org/TR/prov-o/",
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
        "version": "0.1.0",
        "snapshot": corpus.snapshot["snapshotId"],
        "generated_at": generated_at,
        "status": "bounded-demonstrator",
        "publisher": "https://github.com/chris-page-gov",
        "license": "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
        "semantic_descriptor": f"{PUBLIC_ROOT}okf-bundle.yamlld",
        "counts": {
            "datasets": len(corpus.records),
            "records": len(corpus.records),
            "publishers": 1,
            "resources": len(resources),
            "relationships": len(relationships),
            "sources": len(source_counts),
            "standards": standards_evaluation["standardCount"],
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
            "evaluation": "data/evaluation/report.json",
            "mcp_bindings": "data/ons/mcp-bindings.json",
            "spatial_index": "data/ons/spatial-index.json",
            "viewer": EXPLORER_ROOT,
        },
        "extensions": {
            "okf-ons-discovery.v1": {
                "mode": "metadata-only-demonstrator",
                "all_ons_metadata_claim": False,
                "compare_alternatives": True,
                "statistical_accuracy_evaluated": False,
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
            "okf-ons-geography.v1": {
                "entrypoint": "spatial_index",
                "geometry_included": False,
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
