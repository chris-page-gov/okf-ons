from __future__ import annotations

from typing import Any

from okf_ons.model import normalize_acquisition_record


def _provenance() -> dict[str, Any]:
    return {
        "source": {
            "id": "ons-data-api",
            "adapter": "ons-data-api",
            "endpoint": "https://api.beta.ons.gov.uk/v1/datasets",
        },
        "pages": [{"retrievedAt": "2026-07-21T13:00:00Z"}],
        "recordSetSha256": "a" * 64,
    }


def _normalise(dimensions: list[dict[str, Any]]) -> dict[str, Any]:
    record = normalize_acquisition_record(
        {
            "sourceId": "ons-data-api",
            "sourceRecordId": "example-dataset",
            "recordKind": "dataset",
            "title": "Example dataset",
            "description": "Source-declared description.",
            "links": {
                "self": {
                    "href": "https://api.beta.ons.gov.uk/v1/datasets/example-dataset"
                },
                "latest_version": {
                    "href": (
                        "https://api.beta.ons.gov.uk/v1/datasets/example-dataset/"
                        "editions/2021/versions/1"
                    ),
                    "id": "1",
                },
            },
            "versionDimensions": dimensions,
        },
        snapshot_id="snapshot:test",
        provenance=_provenance(),
    )
    assert record is not None
    return record


def test_ons_version_dimensions_add_only_explicit_geography_and_quality() -> None:
    quality_url = (
        "https://www.ons.gov.uk/peoplepopulationandcommunity/"
        "methodologies/examplequalityinformation"
    )
    record = _normalise(
        [
            {
                "id": "ltla",
                "name": "ltla",
                "label": "Lower tier local authorities",
                "description": "ONS lower tier local authority geography.",
                "href": "https://api.beta.ons.gov.uk/v1/code-lists/ltla",
                "is_area_type": True,
                "number_of_options": 331,
            },
            {
                "id": "accommodation_type_2a",
                "name": "accommodation_type_2a",
                "label": "Accommodation type",
                "is_area_type": False,
                "quality_statement_text": "Take care when comparing with 2011.",
                "quality_statement_url": quality_url,
            },
        ]
    )

    assert record["geography"] == ["Lower tier local authorities"]
    assert record["geography_metadata"]["dimensions"][0]["id"] == "ltla"
    assert record["dimension_count"] == 2
    assert record["dimensions"][1]["label"] == "Accommodation type"
    assert record["quality_links"] == [quality_url]
    assert record["quality_notes"] == ["Take care when comparing with 2011."]
    assert record["quality_evidence"]["evidence"]["geography"] is True
    assert record["quality_evidence"]["evidence"]["quality_documentation"] is True
    assert record["quality_evidence"]["evidence"]["time_coverage"] is False
    assert record["quality_evidence"]["evidence"]["revision_status"] is False
    assert record["methodology_links"] == []
    fields = record["metadata_derivation"]["fields"]
    assert fields["geography"]["rule"] == (
        "is-area-type-or-exact-geography-name-v1"
    )
    assert fields["quality_links"]["mode"] == "source-declared"


def test_ons_non_census_exact_geography_name_is_accepted() -> None:
    record = _normalise(
        [
            {
                "id": "administrative-geography",
                "name": "geography",
                "label": "Geography",
                "is_area_type": False,
            },
            {
                "id": "country-of-birth",
                "name": "countryofbirth",
                "label": "Country of birth",
                "description": "A subject classification, not coverage.",
            },
        ]
    )

    assert record["geography"] == ["Geography"]
    assert [row["id"] for row in record["geography_metadata"]["dimensions"]] == [
        "administrative-geography"
    ]


def test_ons_version_dimensions_drop_unsafe_urls_and_malformed_values() -> None:
    record = _normalise(
        [
            {
                "id": "subject",
                "name": "subject",
                "label": "Subject",
                "href": "https://user:password@example.test/codes",
                "quality_statement_url": "https://example.test/quality?token=secret",
                "is_area_type": "true",
                "number_of_options": True,
            },
            {"quality_statement_text": "Missing dimension identity."},
        ]
    )

    assert record["dimension_count"] == 1
    assert record["dimensions"] == [
        {"id": "subject", "label": "Subject", "name": "subject"}
    ]
    assert record["geography"] == []
    assert record["quality_links"] == []
    assert record["quality_notes"] == []
    assert record["quality_evidence"]["evidence"]["geography"] is False
    assert record["quality_evidence"]["evidence"]["quality_documentation"] is False
