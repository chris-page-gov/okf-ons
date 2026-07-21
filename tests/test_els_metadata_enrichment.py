from __future__ import annotations

from typing import Any

from okf_ons.model import normalize_acquisition_record
from okf_ons.search import filter_values, result_document


def _normalise_els(**overrides: Any) -> dict[str, Any]:
    projected: dict[str, Any] = {
        "sourceId": "ons-explore-local-statistics",
        "sourceRecordId": "els-test-indicator",
        "recordKind": "curated-local-indicator",
        "title": "Test local indicator",
        "description": "A source-declared test indicator.",
        "metadataModified": "2026-07-15",
        "releaseFrequency": "annual",
        "links": {
            "metadata": (
                "https://www.ons.gov.uk/explore-local-statistics/"
                "api/v1/metadata/indicators/els-test-indicator"
            ),
            "self": (
                "https://www.ons.gov.uk/explore-local-statistics/"
                "indicators/els-test-indicator"
            ),
        },
        "geography": {
            "countries": ["E", "N", "S", "W"],
            "levels": ["ltla"],
            "vintage": 2025,
            "derivationMode": "inferred-from-area-code-coverage",
        },
        "timeCoverage": {"start": "2024", "end": "2025"},
        "producers": [
            {
                "name": "Example producer",
                "role": "upstream-producer-or-source-attribution",
                "url": "https://example.test/methodology",
            }
        ],
        "derivation": {"mode": "application-curated-extract"},
        "derivedMetadataFlags": {
            "mode": "inferred-from-observation-structure-without-publishing-observations"
        },
        "caveats": [],
    }
    projected.update(overrides)
    record = normalize_acquisition_record(
        projected,
        snapshot_id="snapshot:test",
        provenance={
            "source": {
                "id": "ons-explore-local-statistics",
                "adapter": "els-pinned-application",
                "endpoint": (
                    "https://www.ons.gov.uk/explore-local-statistics/"
                    "api/v1/metadata/indicators"
                ),
            },
            "pages": [{"retrievedAt": "2026-07-17T08:00:00Z"}],
            "recordSetSha256": "c" * 64,
        },
    )
    assert record is not None
    return record


def test_els_extracts_only_explicit_caveat_evidence_links() -> None:
    qmi_url = "https://www.ons.gov.uk/methodologies/example-qmi"
    method_url = "https://www.gov.uk/example-user-guide"
    quality_url = "https://www.gov.uk/example-background-quality-report"
    source_url = "https://example.test/source-dataset"
    caveats = [
        f"Read the [quality and methodology information (QMI)]({qmi_url}).",
        f"The [user guide]({method_url}) describes the estimation approach.",
        f"See the [Background Quality Report]({quality_url}).",
        f"The [source dataset]({source_url}) contains the figures.",
    ]

    record = _normalise_els(caveats=caveats)

    assert record["quality_notes"] == caveats
    assert record["methodology_links"] == [method_url, qmi_url]
    assert record["quality_links"] == [quality_url, qmi_url]
    assert "https://example.test/methodology" not in record["methodology_links"]
    assert source_url not in record["methodology_links"]
    assert source_url not in record["quality_links"]
    evidence = record["quality_evidence"]["evidence"]
    assert evidence["methodology"] is True
    assert evidence["quality_documentation"] is True
    assert filter_values(record, "has_quality_documentation") == ["yes"]


def test_els_maps_only_explicit_explorer_metadata() -> None:
    record = _normalise_els(caveats=["A source-declared limitation without a link."])

    assert record["type"] == "curated-local-indicator"
    assert record["area_served"] == [
        "England",
        "Northern Ireland",
        "Scotland",
        "Wales",
    ]
    assert record["endpoint_host"] == "www.ons.gov.uk"
    assert record["documentation_host"] == "www.ons.gov.uk"
    assert record["resource_hosts"] == ["www.ons.gov.uk"]
    assert record["quality_evidence"]["evidence"]["quality_documentation"] is True
    assert record["quality_evidence"]["evidence"]["methodology"] is False
    assert record["quality_links"] == []
    assert record["methodology_links"] == []

    result = result_document(record, 0)
    assert result["endpoint_host"] == "www.ons.gov.uk"
    assert result["documentation_host"] == "www.ons.gov.uk"

    fields = record["metadata_derivation"]["fields"]
    assert fields["type"] == {
        "mode": "source-declared",
        "sourceField": "recordKind",
    }
    assert fields["quality_notes"] == {
        "mode": "source-declared",
        "sourceField": "caveats",
    }
    assert fields["area_served"]["sourceField"] == "geography.countries"
    assert fields["endpoint_host"]["sourceField"] == "links.metadata"
    assert fields["documentation_host"]["sourceField"] == "links.self"


def test_els_does_not_invent_missing_evidence_or_access_claims() -> None:
    record = _normalise_els(
        caveats=[],
        geography={"countries": ["UK"], "levels": ["ltla"]},
        links={
            "metadata": "https://user:password@example.test/private",
            "self": "not-a-url",
        },
    )

    assert record["quality_notes"] == []
    assert record["methodology_links"] == []
    assert record["quality_links"] == []
    assert record["quality_evidence"]["evidence"]["quality_documentation"] is False
    assert record["area_served"] == []
    assert record["endpoint_host"] == ""
    assert record["documentation_host"] == ""
    assert record["resource_hosts"] == []
    assert "revision_status" in record and record["revision_status"] == ""
    assert record["contacts"] == []
    assert record["population_type"] == ""
    assert record["license_id"] == "not-evaluated"
    assert "access_model" not in record
    assert "visibility" not in record
    assert "private" not in record
    assert "isopen" not in record
    assert filter_values(record, "has_quality_documentation") == ["no"]
