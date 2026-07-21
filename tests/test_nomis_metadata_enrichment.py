from __future__ import annotations

import pytest

from okf_ons.model import normalize_acquisition_record


def _normalise_nomis(annotations: list[dict[str, str]]) -> dict[str, object]:
    record = normalize_acquisition_record(
        {
            "sourceId": "nomis-dataset-definitions",
            "sourceRecordId": "NM_TEST_QUALITY",
            "title": "Nomis metadata evidence test",
            "description": "A test dataset.",
            "firstReleased": "2024-01-15 07:00:00",
            "annotations": annotations,
            "links": {
                "apiDefinition": (
                    "https://www.nomisweb.co.uk/api/v01/dataset/"
                    "NM_TEST_QUALITY/def.sdmx.json"
                )
            },
        },
        snapshot_id="snapshot:test",
        provenance={
            "source": {
                "id": "nomis-dataset-definitions",
                "adapter": "nomis-sdmx",
                "endpoint": "https://www.nomisweb.co.uk/api/v01/dataset/def.sdmx.json",
            },
            "pages": [{"retrievedAt": "2026-07-17T08:00:00Z"}],
            "recordSetSha256": "a" * 64,
        },
    )
    assert record is not None
    return record


def test_nomis_annotations_fill_only_explicit_metadata_evidence() -> None:
    quality_url = "https://www.ons.gov.uk/methodologies/census-quality-information"
    record = _normalise_nomis(
        [
            {"title": "contenttype/geoglevel", "text": "oa, ps"},
            {
                "title": "SubDescription",
                "text": "Usual residents aged 16 years and over.",
            },
            {"title": "Status", "text": "Current (being actively updated)"},
            {"title": "MetadataTitle1", "text": "Statistical Disclosure Control"},
            {
                "title": "MetadataText1",
                "text": f"Read the {quality_url}[quality guidance] before use.",
            },
            {"title": "MetadataTitle2", "text": "About this dataset"},
            {
                "title": "MetadataText2",
                "text": "Classification at https://example.org/classification.html.",
            },
        ]
    )

    assert record["geography"] == ["oa", "ps"]
    assert record["population_type"] == "Usual residents aged 16 years and over."
    assert record["quality_links"] == [quality_url]
    assert record["revision_status"] == ""
    evidence = record["quality_evidence"]["evidence"]
    assert evidence["release_or_modified"] is True
    assert evidence["population"] is True
    assert evidence["geography"] is True
    assert evidence["quality_documentation"] is True
    assert evidence["revision_status"] is False
    assert record["metadata_derivation"] == {
        "schema": "okf-ons-field-derivation.v1",
        "modes": ["deterministic-extraction", "source-declared"],
        "fields": {
            "geography": {
                "mode": "source-declared",
                "sourceAnnotation": "contenttype/geoglevel",
            },
            "population_type": {
                "mode": "source-declared",
                "sourceAnnotation": "SubDescription",
            },
            "quality_links": {
                "mode": "deterministic-extraction",
                "sourceAnnotationPattern": "MetadataTextN",
                "classifier": "nomis-quality-context-v1",
            },
        },
    }


@pytest.mark.parametrize("sub_description", ["vat", "previously unavailable"])
def test_nomis_does_not_treat_codes_or_general_urls_as_missing_metadata(
    sub_description: str,
) -> None:
    record = _normalise_nomis(
        [
            {"title": "SubDescription", "text": sub_description},
            {"title": "Units", "text": "Persons"},
            {"title": "Status", "text": "Current"},
            {"title": "MetadataTitle0", "text": "About this dataset"},
            {
                "title": "MetadataText0",
                "text": "Definitions at https://example.org/classification.html.",
            },
        ]
    )

    assert record["population_type"] == ""
    assert record["geography"] == []
    assert record["quality_links"] == []
    assert record["revision_status"] == ""
    assert record["metadata_derivation"] == {}
    assert record["quality_evidence"]["evidence"]["release_or_modified"] is True
    assert record["quality_evidence"]["evidence"]["population"] is False
