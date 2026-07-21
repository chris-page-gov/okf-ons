from __future__ import annotations

from okf_ons.model import normalize_acquisition_record


def test_ons_catalogue_enrichment_maps_declared_metadata_and_provenance() -> None:
    record = normalize_acquisition_record(
        {
            "sourceId": "ons-data-api",
            "sourceRecordId": "test-dataset",
            "recordKind": "dataset",
            "title": "Test dataset",
            "description": "Test description.",
            "lifecycleState": "published",
            "lastUpdated": "2026-07-21T08:00:00Z",
            "contacts": [
                {
                    "name": "Expert statistical team",
                    "email": "statistics@example.ons.gov.uk",
                    "telephone": "+44 300 123 0000",
                }
            ],
            "isBasedOn": {
                "id": "usual-residents",
                "type": "cantabular_flexible_table",
            },
            "canonicalTopic": "7779",
            "subtopics": ["6885", "7755"],
            "datasetType": "cantabular_flexible_table",
            "survey": "census",
            "licence": "Open Government Licence v3.0",
            "publications": [
                {
                    "title": "Statistical bulletin",
                    "href": "https://www.ons.gov.uk/publication",
                }
            ],
            "relatedContent": [
                {
                    "title": "Related analysis",
                    "href": "https://www.ons.gov.uk/analysis",
                }
            ],
            "links": {
                "self": {"href": "https://api.beta.ons.gov.uk/v1/datasets/test-dataset"}
            },
        },
        snapshot_id="snapshot:test",
        provenance={
            "source": {
                "id": "ons-data-api",
                "adapter": "ons-data-api",
                "endpoint": "https://api.beta.ons.gov.uk/v1/datasets",
                "publisher": {
                    "name": "Office for National Statistics",
                    "url": "https://www.ons.gov.uk/",
                },
            },
            "pages": [{"retrievedAt": "2026-07-21T08:00:00Z"}],
            "recordSetSha256": "a" * 64,
        },
    )

    assert record is not None
    assert record["contacts"][0]["email"] == "statistics@example.ons.gov.uk"
    assert record["population_type"] == "usual-residents"
    assert record["population_type_metadata"] == {
        "id": "usual-residents",
        "type": "cantabular_flexible_table",
    }
    assert record["canonical_topic"] == "7779"
    assert record["subtopic"] == ["6885", "7755"]
    assert record["type"] == "cantabular_flexible_table"
    assert record["survey"] == "census"
    assert record["source_licence"] == "Open Government Licence v3.0"
    assert record["quality_evidence"]["evidence"]["contact"] is True
    assert record["quality_evidence"]["evidence"]["population"] is True
    assert record["metadata_derivation"] == {
        "schema": "okf-ons-field-derivation.v1",
        "modes": ["source-declared"],
        "fields": {
            "contacts": {"mode": "source-declared", "sourceField": "contacts"},
            "population_type": {
                "mode": "source-declared",
                "sourceField": "is_based_on",
            },
            "taxonomy": {
                "mode": "source-declared",
                "sourceFields": ["canonical_topic", "subtopics"],
            },
        },
    }


def test_ons_catalogue_does_not_invent_population_without_identifier() -> None:
    record = normalize_acquisition_record(
        {
            "sourceId": "ons-data-api",
            "sourceRecordId": "test-dataset",
            "title": "Test dataset",
            "isBasedOn": {"type": "cantabular_flexible_table"},
        },
        snapshot_id="snapshot:test",
        provenance={"recordSetSha256": "a" * 64},
    )

    assert record is not None
    assert record["population_type"] == ""
    assert record["quality_evidence"]["evidence"]["population"] is False


def test_nomis_acquisition_description_survives_normalisation() -> None:
    record = normalize_acquisition_record(
        {
            "sourceId": "nomis-dataset-definitions",
            "sourceRecordId": "NM_TEST_1",
            "title": "Test dataset",
            "description": "Authoritative Nomis description.",
            "agencyId": "NOMIS",
            "contentSource": "JSA",
            "firstReleased": "2024-01-15 07:00:00",
            "mnemonic": "jsa",
            "publisherUri": "Nm-test",
            "definitionVersion": "1.0",
            "links": {
                "apiDefinition": (
                    "https://www.nomisweb.co.uk/api/v01/dataset/NM_TEST_1/def.sdmx.json"
                )
            },
            "components": [
                {
                    "kind": "dimension",
                    "concept": "SEX",
                    "codeList": "CL_TEST_SEX",
                    "position": 1,
                },
                {
                    "kind": "timedimension",
                    "concept": "TIME",
                    "codeList": "CL_TEST_TIME",
                    "position": 2,
                },
                {
                    "kind": "primarymeasure",
                    "concept": "OBS_VALUE",
                },
            ],
        },
        snapshot_id="snapshot:test",
        provenance={
            "retrievedAt": "2026-07-17T08:00:00Z",
            "recordSetSha256": "a" * 64,
        },
    )

    assert record is not None
    assert record["description"] == "Authoritative Nomis description."
    assert record["agency_id"] == "NOMIS"
    assert record["content_source"] == "JSA"
    assert record["first_released"] == "2024-01-15 07:00:00"
    assert record["mnemonic"] == "jsa"
    assert record["publisher_uri"] == "Nm-test"
    assert record["publication"]["release_date"] == "2024-01-15 07:00:00"
    assert record["publication"]["release_date"] != record["metadata_modified"]
    assert record["sdmx"]["standardId"] == "sdmx-3-1"
    assert record["sdmx"]["identity"] == {
        "agency": "NOMIS",
        "identifier": "NM_TEST_1",
        "version": "1.0",
        "structureRole": "DataStructureDefinition",
        "sourceStructureType": "keyfamily",
    }
    assert [dimension["position"] for dimension in record["sdmx"]["dimensions"]] == [1, 2]
    assert [component["role"] for component in record["sdmx"]["components"]] == [
        "Dimension",
        "TimeDimension",
        "PrimaryMeasure",
    ]
    assert record["sdmx"]["selectionConstraints"]["complete"] is False
    assert record["sdmx"]["upstreamSdmxVersion"] == "not-evidenced"
    assert record["selection"]["query_tool"] == "nomis_query"
    assert record["selection"]["tool_provider"] == "mcp-geo"
    assert record["selection"]["complete"] is False
