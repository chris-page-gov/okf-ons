from __future__ import annotations

import pytest

from okf_ons.model import normalize_acquisition_record


def _normalise_nomis(
    annotations: list[dict[str, str]],
    *,
    nomis_codelists: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    projected: dict[str, object] = {
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
    }
    if nomis_codelists is not None:
        projected["nomisCodelists"] = nomis_codelists
    record = normalize_acquisition_record(
        projected,
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
    assert record["quality_notes"] == [
        f"Read the {quality_url}[quality guidance] before use."
    ]
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
            "quality_notes": {
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
    assert record["quality_notes"] == []
    assert record["revision_status"] == ""
    assert record["metadata_derivation"] == {}
    assert record["quality_evidence"]["evidence"]["release_or_modified"] is True
    assert record["quality_evidence"]["evidence"]["population"] is False


def test_nomis_unsuffixed_quality_note_is_preserved() -> None:
    record = _normalise_nomis(
        [
            {
                "title": "MetadataText",
                "text": (
                    "Figures have been adjusted to avoid the release of "
                    "confidential data."
                ),
            },
            {"title": "MetadataTitle", "text": "Statistical Disclosure Control"},
        ]
    )

    assert record["quality_notes"] == [
        "Figures have been adjusted to avoid the release of confidential data."
    ]
    assert record["quality_evidence"]["evidence"]["quality_documentation"] is True


def test_nomis_codelists_supply_explicit_frequency_and_time_coverage() -> None:
    record = _normalise_nomis(
        [],
        nomis_codelists=[
            {
                "concept": "FREQ",
                "codeList": "CL_TEST_FREQ",
                "status": "present",
                "codes": [{"value": "A", "label": "Annually"}],
            },
            {
                "concept": "TIME",
                "codeList": "CL_TEST_TIME",
                "status": "present",
                "codes": [
                    {
                        "value": "2011",
                        "label": "2011",
                    },
                    {
                        "value": "2021",
                        "label": "2021",
                        "revisionStatus": "Current",
                    },
                    {
                        "value": "2027",
                        "label": "2027 not yet released",
                        "revisionStatus": "PreRelease",
                    },
                ],
            },
        ],
    )

    assert record["frequency"] == "Annually"
    assert record["time_coverage"] == {
        "start": "2011",
        "end": "2021",
        "startLabel": "2011",
        "endLabel": "2021",
        "availablePeriodCount": 2,
        "sourceCodeList": "CL_TEST_TIME",
    }
    assert record["nomis_codelist_metadata"] == {
        "frequency": {
            "codeList": "CL_TEST_FREQ",
            "codeCount": 1,
            "labels": ["Annually"],
            "singleFrequencyDerived": True,
        },
        "time": {
            "codeList": "CL_TEST_TIME",
            "codeCount": 3,
            "availableCodeCount": 2,
            "coverageDerived": True,
            "periodFormat": "YYYY",
        },
    }
    assert record["quality_evidence"]["evidence"]["frequency"] is True
    assert record["quality_evidence"]["evidence"]["time_coverage"] is True
    assert record["metadata_derivation"]["fields"] == {
        "frequency": {
            "mode": "deterministic-extraction",
            "sourceField": "nomisCodelists[FREQ].codes",
            "rule": "single-explicit-frequency-label-v1",
        },
        "time_coverage": {
            "mode": "deterministic-extraction",
            "sourceField": "nomisCodelists[TIME].codes",
            "rule": "available-time-codelist-range-v1",
        },
    }


def test_nomis_codelist_ambiguity_and_opaque_periods_remain_gaps() -> None:
    record = _normalise_nomis(
        [],
        nomis_codelists=[
            {
                "concept": "FREQ",
                "codeList": "CL_TEST_FREQ",
                "status": "present",
                "codes": [
                    {"value": "A", "label": "Annually"},
                    {"value": "Q", "label": "Quarterly"},
                ],
            },
            {
                "concept": "TIME",
                "codeList": "CL_TEST_TIME",
                "status": "present",
                "codes": [{"value": "latest", "label": "Latest"}],
            },
        ],
    )

    assert record["frequency"] == ""
    assert record["time_coverage"] == {}
    assert record["quality_evidence"]["evidence"]["frequency"] is False
    assert record["quality_evidence"]["evidence"]["time_coverage"] is False


def test_nomis_frequency_requires_one_code_label_option() -> None:
    record = _normalise_nomis(
        [],
        nomis_codelists=[
            {
                "concept": "FREQ",
                "codeList": "CL_TEST_FREQ",
                "status": "present",
                "codes": [
                    {"value": "A", "label": "Annually"},
                    {"value": "ANNUAL", "label": "Annually"},
                ],
            }
        ],
    )

    assert record["frequency"] == ""
    assert record["nomis_codelist_metadata"]["frequency"] == {
        "codeList": "CL_TEST_FREQ",
        "codeCount": 2,
        "labels": ["Annually"],
        "singleFrequencyDerived": False,
    }
    assert record["quality_evidence"]["evidence"]["frequency"] is False


def test_nomis_unavailable_time_codelist_is_preserved_as_not_evidenced() -> None:
    record = _normalise_nomis(
        [],
        nomis_codelists=[
            {
                "concept": "FREQ",
                "codeList": "CL_TEST_FREQ",
                "status": "present",
                "codes": [{"value": "A", "label": "Annually"}],
            },
            {
                "concept": "TIME",
                "codeList": "CL_TEST_TIME",
                "status": "not-evidenced",
                "reason": "upstream-codelist-unavailable",
                "codes": [],
            },
        ],
    )

    assert record["frequency"] == "Annually"
    assert record["time_coverage"] == {}
    assert record["nomis_codelist_metadata"]["notEvidenced"] == [
        {
            "concept": "TIME",
            "codeList": "CL_TEST_TIME",
            "reason": "upstream-codelist-unavailable",
        }
    ]
