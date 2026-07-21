from __future__ import annotations

from typing import Any

import pytest

from okf_ons.model import normalize_acquisition_record
from okf_ons.search import result_document


def _normalise_ogp(**overrides: Any) -> dict[str, Any]:
    projected: dict[str, Any] = {
        "sourceId": "ons-open-geography",
        "sourceRecordId": "ogp-test-record",
        "recordKind": "geospatial-dataset",
        "title": "Output Areas (December 2021) Boundaries UK",
        "description": "This source is issued quarterly.",
        "created": "2022-01-10T09:30:00Z",
        "modified": "2025-03-04T12:00:00Z",
        "access": "public",
        "keywords": ["UK", "EN", "Boundary"],
        "links": {"item": "https://example.test/ogp-test-record"},
        "portalExtent": {"type": "Polygon", "coordinates": []},
    }
    projected.update(overrides)
    record = normalize_acquisition_record(
        projected,
        snapshot_id="snapshot:test",
        provenance={
            "source": {
                "id": "ons-open-geography",
                "adapter": "ogc-records",
                "endpoint": "https://geoportal.statistics.gov.uk/api/search/v1",
            },
            "pages": [{"retrievedAt": "2026-07-17T08:00:00Z"}],
            "recordSetSha256": "b" * 64,
        },
    )
    assert record is not None
    return record


def test_ogp_maps_only_bounded_source_and_derived_metadata() -> None:
    record = _normalise_ogp()

    assert record["metadata_created"] == "2022-01-10T09:30:00Z"
    assert record["type"] == "geospatial-dataset"
    assert record["access_model"] == "public"
    assert record["visibility"] == "public"
    assert record["private"] is False
    assert "isopen" not in record
    assert record["area_served"] == ["England", "United Kingdom"]
    assert record["geography_vintage"] == 2021
    assert record["frequency"] == "quarterly"
    assert record["geography"] == []
    assert record["quality_evidence"]["evidence"]["geography"] is True
    assert record["quality_evidence"]["evidence"]["frequency"] is True

    derivation = record["metadata_derivation"]
    assert derivation["schema"] == "okf-ons-field-derivation.v1"
    assert derivation["modes"] == [
        "controlled-vocabulary-crosswalk",
        "deterministic-extraction",
        "deterministic-normalisation",
        "source-declared",
    ]
    assert derivation["fields"]["metadata_created"] == {
        "mode": "source-declared",
        "sourceField": "created",
    }
    assert derivation["fields"]["geography_vintage"]["sourceField"] == "title"
    assert derivation["fields"]["area_served"]["sourceField"] == "keywords"

    result = result_document(record, 0)
    assert result["access_model"] == "public"


@pytest.mark.parametrize(
    ("description", "frequency"),
    [
        ("This source is issued quarterly.", "quarterly"),
        ("The lookup is refreshed every 6 weeks.", "every 6 weeks"),
        ("The product is published annually.", "annually"),
        ("The product covers the first quarter.", ""),
    ],
)
def test_ogp_frequency_requires_an_explicit_cadence_phrase(
    description: str,
    frequency: str,
) -> None:
    record = _normalise_ogp(description=description)

    assert record["frequency"] == frequency


def test_ogp_leaves_ambiguous_or_unsupported_derivations_unset() -> None:
    record = _normalise_ogp(
        title="Boundary changes between 2011 and 2021",
        description="The product covers the first quarter.",
        access="restricted",
        keywords=["Public Health England Regions", "GBR"],
        portalExtent={},
    )

    assert record["geography_vintage"] == ""
    assert record["frequency"] == ""
    assert record["area_served"] == []
    assert "access_model" not in record
    assert "visibility" not in record
    assert "private" not in record
    assert "isopen" not in record
    assert record["quality_evidence"]["evidence"]["geography"] is False


def test_ogp_uses_snippet_only_when_description_is_missing() -> None:
    fallback = _normalise_ogp(description="", snippet="Source catalogue summary")
    preferred = _normalise_ogp(
        description="Full source description",
        snippet="Source catalogue summary",
    )

    assert fallback["notes"] == "Source catalogue summary"
    assert fallback["metadata_derivation"]["fields"]["description"] == {
        "mode": "source-declared-fallback",
        "sourceField": "snippet",
    }
    assert preferred["notes"] == "Full source description"
    assert "description" not in preferred["metadata_derivation"]["fields"]
