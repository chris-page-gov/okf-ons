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
