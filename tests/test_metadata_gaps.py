import pytest

from okf_ons.metadata_gaps import compare_profiles, is_metadata_gap, profile_records


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


def test_applicability_metric_excludes_only_explicit_record_class_rules():
    fields = {
        field: field in {"identity", "description", "publisher", "provenance"}
        for field in (
            "identity",
            "description",
            "publisher",
            "licence",
            "contact",
            "release_or_modified",
            "frequency",
            "population",
            "geography",
            "time_coverage",
            "methodology",
            "quality_documentation",
            "revision_status",
            "provenance",
        )
    }
    profile = profile_records(
        [
            _record("geography", "ons-open-geography", fields),
            _record("statistics", "nomis", fields),
        ]
    )
    metric = profile["applicabilityAwareEvidenceMetric"]

    assert metric["states"] == {
        "present": 8,
        "not-applicable": 2,
        "not-evidenced": 18,
        "conflicted": 0,
    }
    assert metric["applicablePossible"] == 26
    assert metric["completeness"] == pytest.approx(8 / 26)
    population = next(row for row in metric["byField"] if row["field"] == "population")
    assert population == {
        "field": "population",
        "present": 0,
        "not-applicable": 1,
        "not-evidenced": 1,
        "conflicted": 0,
        "applicablePossible": 1,
    }
    time_coverage = next(
        row for row in metric["byField"] if row["field"] == "time_coverage"
    )
    assert time_coverage["not-applicable"] == 1
    assert time_coverage["not-evidenced"] == 1


def test_compare_profiles_reports_fixed_denominator_yield():
    fields = {
        field: field in {"identity", "description", "publisher", "provenance"}
        for field in (
            "identity",
            "description",
            "publisher",
            "licence",
            "contact",
            "release_or_modified",
            "frequency",
            "population",
            "geography",
            "time_coverage",
            "methodology",
            "quality_documentation",
            "revision_status",
            "provenance",
        )
    }
    baseline = profile_records([_record("one", "alpha", fields)])
    current = profile_records(
        [_record("one", "alpha", {**fields, "geography": True, "population": True})]
    )

    comparison = compare_profiles(baseline, current, elapsed_seconds=1800)
    evidence = comparison["evidenceSlotDelta"]
    assert evidence["addedPresent"] == 2
    assert evidence["remainingMissing"] == 8
    assert evidence["percentagePointChange"] == pytest.approx(14.285714)
    assert evidence["slotsPerHour"] == 4
    assert next(row for row in evidence["byField"] if row["field"] == "geography") == {
        "field": "geography",
        "addedPresent": 1,
        "remainingMissing": 0,
    }
    assert comparison["applicabilityAwareDelta"]["addedPresent"] == 2
    assert comparison["applicabilityAwareDelta"]["stateChanges"] == {
        "present": 2,
        "not-applicable": 0,
        "not-evidenced": -2,
        "conflicted": 0,
    }


def test_compare_profiles_rejects_denominator_changes():
    fields = {field: False for field in (
        "identity", "description", "publisher", "licence", "contact",
        "release_or_modified", "frequency", "population", "geography",
        "time_coverage", "methodology", "quality_documentation",
        "revision_status", "provenance",
    )}
    baseline = profile_records([_record("one", "alpha", fields)])
    current = profile_records(
        [_record("one", "alpha", fields), _record("two", "alpha", fields)]
    )
    with pytest.raises(ValueError, match="different record counts"):
        compare_profiles(baseline, current)


def test_compare_profiles_exposes_applicability_denominator_changes():
    fields = {
        field: field in {"identity", "description", "publisher", "provenance"}
        for field in (
            "identity",
            "description",
            "publisher",
            "licence",
            "contact",
            "release_or_modified",
            "frequency",
            "population",
            "geography",
            "time_coverage",
            "methodology",
            "quality_documentation",
            "revision_status",
            "provenance",
        )
    }
    baseline = profile_records([_record("one", "alpha", fields)])
    current = profile_records([_record("one", "alpha", fields)])
    applicability = current["applicabilityAwareEvidenceMetric"]
    applicability["applicablePossible"] -= 1
    applicability["states"]["not-applicable"] += 1
    applicability["states"]["not-evidenced"] -= 1

    delta = compare_profiles(baseline, current)["applicabilityAwareDelta"]
    assert delta["baselinePossible"] == 14
    assert delta["currentPossible"] == 13
    assert delta["denominatorChange"] == -1
    assert delta["addedPresent"] == 0
    assert delta["percentagePointChange"] == pytest.approx(2.197802)
