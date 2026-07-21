from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from okf_ons.build import _resource_rows
from okf_ons.model import _contrast_values, normalize_acquisition_record
from okf_ons.search import result_document

ROOT = Path(__file__).resolve().parents[1]
OGP_R3 = ROOT / "source/metadata-enrichment-2026-07-21-r3/ons-open-geography.json"


def _provenance() -> dict[str, Any]:
    return {
        "source": {
            "id": "ons-open-geography",
            "adapter": "ogc-records",
            "endpoint": "https://geoportal.statistics.gov.uk/api/search/v1",
        },
        "pages": [{"retrievedAt": "2026-07-17T08:00:00Z"}],
        "recordSetSha256": "c" * 64,
    }


def _normalise_ogp(**overrides: Any) -> dict[str, Any]:
    native_id = "ogp-utility-record"
    projected: dict[str, Any] = {
        "sourceId": "ons-open-geography",
        "sourceRecordId": native_id,
        "recordKind": "geospatial-dataset",
        "title": "National Statistics UPRN Lookup (December 2024) User Guide (V2)",
        "description": (
            "This guide describes the lookup as at December 2024 and is issued "
            "every 12 weeks. The methodology used is documented at "
            "https://www.ons.gov.uk/methodology/geography/example-method. "
            "Data quality and limitations are documented for users. "
            "This file has been updated to correct a field label."
        ),
        "created": "2024-12-10T09:30:00Z",
        "modified": "2025-03-04T12:00:00Z",
        "access": "public",
        "itemType": "CSV Collection",
        "keywords": ["UK", "Postcodes"],
        "categories": [
            "/Categories/ONS Geography Open Data",
            "/Categories/Postcode Products/User Guides",
        ],
        "links": {
            "item": "https://services.example.test/example/FeatureServer",
            "related": [
                {
                    "rel": "self",
                    "href": (
                        "https://geoportal.statistics.gov.uk/api/search/v1/"
                        f"collections/dataset/items/{native_id}"
                    ),
                }
            ],
        },
    }
    projected.update(overrides)
    record = normalize_acquisition_record(
        projected,
        snapshot_id="snapshot:test",
        provenance=_provenance(),
    )
    assert record is not None
    return record


def test_ogp_adds_only_explicit_utility_evidence() -> None:
    record = _normalise_ogp()
    self_url = (
        "https://geoportal.statistics.gov.uk/api/search/v1/collections/"
        "dataset/items/ogp-utility-record"
    )
    method_url = "https://www.ons.gov.uk/methodology/geography/example-method"

    assert record["frequency"] == "every 12 weeks"
    assert record["methodology_links"] == sorted([method_url, self_url])
    assert "Data quality and limitations" in record["quality_notes"][0]
    assert record["geography_reference_date"] == "December 2024"
    assert record["geography_metadata"] == {
        "referenceDate": "December 2024",
        "referenceDateSemantics": (
            "source-declared geography resource reference/effective date"
        ),
        "derivationMode": "deterministic-extraction",
    }
    assert record["source_version_label"] == "V2"
    assert "This file has been updated" in record["revision_history_notes"][0]

    assert record["groups"] == ["/Categories/Postcode Products/User Guides"]
    assert record["subtopic"] == ["Postcode Products/User Guides"]
    assert record["url"] == "https://services.example.test/example/FeatureServer"
    assert record["documentation"] == self_url
    assert record["endpoint_host"] == "services.example.test"
    assert record["documentation_host"] == "geoportal.statistics.gov.uk"
    assert record["resource_hosts"] == [
        "geoportal.statistics.gov.uk",
        "services.example.test",
    ]

    evidence = record["quality_evidence"]["evidence"]
    assert evidence["frequency"] is True
    assert evidence["methodology"] is True
    assert evidence["quality_documentation"] is True
    assert evidence["time_coverage"] is False
    assert evidence["revision_status"] is False
    assert record["time_coverage"] == {}
    assert record["revision_status"] == ""
    assert record["contacts"] == []
    assert not record.get("unit_of_measure")

    fields = record["metadata_derivation"]["fields"]
    assert fields["geography_reference_date"]["semantics"] == (
        "geography-resource-reference-date"
    )
    assert fields["revision_history_notes"]["doesNotImply"] == "revision_status"
    assert fields["documentation_host"]["rule"] == "exact-self-host-v1"
    assert "metadata derivation" not in _contrast_values(record)

    search_result = result_document(record, 0)
    assert search_result["geography_reference_date"] == "December 2024"
    assert search_result["source_version_label"] == "V2"
    assert search_result["revision_history_notes"] == record["revision_history_notes"]


def test_ogp_semantic_guards_reject_ambiguous_or_mismatched_evidence() -> None:
    record = _normalise_ogp(
        title="Boundary changes between 2011 and 2021 (V2) User Guide",
        description=(
            "This guide mentions a methodology team, general quality aspirations, "
            "and was approximately refreshed every twelve weeks. The resource was "
            "as at December 2021."
        ),
        categories=[
            "/Categories/ONS Geography Open Data",
            "/Categories/LATEST",
        ],
        links={
            "item": "https://services.example.test/data?token=secret",
            "related": [
                {
                    "rel": "self",
                    "href": (
                        "https://geoportal.statistics.gov.uk/api/search/v1/"
                        "collections/dataset/items/a-different-record"
                    ),
                }
            ],
        },
    )

    assert record["frequency"] == ""
    assert record["methodology_links"] == []
    assert record["quality_notes"] == []
    assert record["geography_reference_date"] == ""
    assert record["source_version_label"] == "V2"
    assert record["revision_history_notes"] == []
    assert record["groups"] == []
    assert record["subtopic"] == []
    assert record["endpoint_host"] == ""
    assert record["documentation_host"] == ""
    assert record["resource_hosts"] == []
    assert record["time_coverage"] == {}
    assert record["revision_status"] == ""


def test_frozen_ogp_r3_has_exact_conservative_whole_snapshot_deltas() -> None:
    envelope = json.loads(OGP_R3.read_text())
    records = [
        normalize_acquisition_record(
            projected,
            snapshot_id="snapshot:ogp-r3-test",
            provenance=envelope["provenance"],
        )
        for projected in envelope["records"]
    ]
    assert all(record is not None for record in records)
    normalised = [record for record in records if record is not None]

    assert len(normalised) == 3_035
    assert sum(bool(record["methodology_links"]) for record in normalised) == 168
    assert sum(bool(record["quality_notes"]) for record in normalised) == 139
    assert sum(record["frequency"] == "every 12 weeks" for record in normalised) == 18
    assert 168 + 139 + 18 == 325

    assert sum(bool(record["geography_reference_date"]) for record in normalised) == 2_462
    assert sum(bool(record["source_version_label"]) for record in normalised) == 223
    assert sum(bool(record["revision_history_notes"]) for record in normalised) == 64
    assert sum(bool(record["groups"]) for record in normalised) == 2_293
    assert sum(bool(record["subtopic"]) for record in normalised) == 2_293

    for field in ("endpoint_host", "documentation_host", "resource_hosts"):
        assert sum(bool(record[field]) for record in normalised) == 3_035
    for field in ("time_coverage", "revision_status", "contacts", "unit_of_measure"):
        assert sum(bool(record.get(field)) for record in normalised) == 0

    resource_rows = _resource_rows(normalised)
    for field in ("source_format", "created", "last_modified", "metadata_modified"):
        assert sum(bool(resource[field]) for resource in resource_rows) == 3_035
