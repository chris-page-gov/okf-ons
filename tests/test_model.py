from __future__ import annotations

from okf_ons.model import normalize_acquisition_record


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
