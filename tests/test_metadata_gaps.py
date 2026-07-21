from okf_ons.metadata_gaps import is_metadata_gap, profile_records


def _record(record_id: str, source: str, evidence: dict[str, bool], **values):
    return {
        "record_id": record_id,
        "source_surface": source,
        "quality_evidence": {
            "evidence": evidence,
            "score": sum(evidence.values()) / len(evidence),
        },
        **values,
    }


def test_is_metadata_gap_matches_explorer_sentinels():
    for value in (None, "", [], "None", "NULL", "not-specified", "__missing__"):
        assert is_metadata_gap(value)
    for value in (0, False, {}, ["value"], "unknown", "n/a"):
        assert not is_metadata_gap(value)


def test_profile_records_counts_evidence_display_and_facet_gaps():
    fields = {
        "identity": True,
        "description": True,
        "publisher": True,
        "licence": False,
        "contact": False,
        "release_or_modified": False,
        "frequency": False,
        "population": False,
        "geography": False,
        "time_coverage": False,
        "methodology": False,
        "quality_documentation": False,
        "revision_status": False,
        "provenance": True,
    }
    records = [
        _record(
            "one",
            "alpha",
            fields,
            publisher_title="Publisher",
            record_type="Dataset",
            license_id="not-specified",
        ),
        _record(
            "two",
            "beta",
            {**fields, "licence": True},
            publisher="Publisher",
            record_type="Dataset",
            license_id="ogl-v3",
        ),
    ]

    profile = profile_records(records, sample_limit=1)
    evidence = profile["evidenceSlotMetric"]
    assert evidence["possible"] == 28
    assert evidence["present"] == 9
    assert evidence["missing"] == 19
    assert evidence["halfRemainingGapSlots"] == 9
    licence = next(row for row in evidence["byField"] if row["field"] == "licence")
    assert licence["present"] == 1
    assert licence["missingBySource"] == {"alpha": 1}
    assert licence["sampleMissingRecordIds"] == ["one"]
    display = profile["explorerDatasetDisplayMetric"]
    licence_display = next(
        row for row in display["byField"] if row["field"] == "overview.licence"
    )
    assert licence_display["present"] == 1
    assert licence_display["missing"] == 1
    facets = profile["explorerSearchFacetMetric"]
    population = next(row for row in facets["byField"] if row["field"] == "population_type")
    assert population["missing"] == 2
