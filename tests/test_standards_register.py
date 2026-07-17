from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
STANDARDS_REGISTER = ROOT / "source" / "standards-register.json"
ONTOLOGY_CROSSWALK = ROOT / "source" / "ontology-crosswalk.json"
SOURCE_REGISTER = ROOT / "source" / "source-register.json"
STANDARDS_DOC = ROOT / "docs" / "standards-register.md"

EVIDENCE_STATUSES = {
    "observed",
    "inferred",
    "not-evidenced",
    "not-applicable",
    "conflicted",
    "stale",
}
PROFILE_STATUSES = {
    "aligned",
    "partial",
    "not-evaluated",
    "not-applicable",
}
REQUIREMENT_LEVELS = {
    "mandatory",
    "conditional",
    "advisory",
    "informative",
}
STANDARD_CATEGORIES = {
    "binding-legislation",
    "statutory-code",
    "official-standard",
    "official-guidance",
    "international-standard",
    "technical-recommendation",
}
PLANNED_RECONCILIATION_LANES = {
    "ons-website-dataset-pages",
    "ons-release-calendar-and-releases",
    "ons-quality-methodology-information",
    "ons-time-series-identifiers",
    "data-gov-uk-ons-records",
}


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def is_absolute_https(value: str) -> bool:
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
    )


def test_standards_register_has_current_code_and_bounded_claim_models() -> None:
    register = load_json(STANDARDS_REGISTER)

    assert register["schemaVersion"] == "okf-ons.standards-register.v1"
    assert register["asOf"] == "2026-07-17"
    assert set(register["categories"]) == STANDARD_CATEGORIES
    assert set(register["claimModel"]["evidenceStatuses"]) == EVIDENCE_STATUSES
    assert set(register["claimModel"]["profileStatuses"]) == PROFILE_STATUSES
    assert register["assuranceBoundary"] == {
        "metadataOnly": True,
        "certifiesStatisticalAccuracy": False,
        "certifiesStandardsCompliance": False,
        "statement": (
            "The register records source evidence and tests the bundle's metadata "
            "mappings. It does not certify an ONS statistical product, observation, "
            "methodology or producer."
        ),
        "absenceRule": (
            "Missing source evidence is recorded as not-evidenced, never as non-compliance."
        ),
        "separationRule": (
            "Bundle profile alignment and source-product evidence are separate "
            "claims with separate status vocabularies."
        ),
    }

    standards = {standard["id"]: standard for standard in register["standards"]}
    assert len(standards) == len(register["standards"])
    assert len(standards) >= 25

    code = standards["uksa-code-3"]
    assert code["currentVersion"] == "3.0"
    assert code["normativeStatus"] == "Current statutory Code, released October 2025"
    assert "Code 2.1 Q1, Q2 and Q3" in code["applicability"]["exclusions"]
    assert {requirement["id"] for requirement in code["requirements"]} >= {
        "code3-release-status-and-revisions",
        "code3-coherence-comparability",
        "code3-quality-and-limitations",
    }

    public_use = standards["uksa-code-3-public-use"]
    assert "replacing the 2022 intelligent-transparency guidance" in public_use["normativeStatus"]
    assert {requirement["theme"] for requirement in public_use["requirements"]} == {
        "Equality of access",
        "Supporting understanding",
        "Decision making and leadership",
    }

    assert standards["govs-010-analysis"]["currentVersion"] == "2.2"
    assert standards["aqua-book-2025"]["currentVersion"] == "July 2025"
    assert standards["sdmx-3-1"]["currentVersion"] == "3.1, released May 2025"
    assert standards["unece-gsbpm-5-2"]["currentVersion"] == "5.2, endorsed June 2025"
    assert standards["unece-gsim-2"]["currentVersion"] == "2.0"
    assert standards["w3c-dqv"]["normativeStatus"] == (
        "W3C Working Group Note, not a W3C Recommendation"
    )


def test_every_standard_is_citable_applicable_and_testable() -> None:
    register = load_json(STANDARDS_REGISTER)
    requirement_ids: set[str] = set()
    seen_levels: set[str] = set()

    for standard in register["standards"]:
        assert standard["category"] in STANDARD_CATEGORIES
        assert standard["authority"].strip()
        assert is_absolute_https(standard["canonicalUri"])
        assert standard["currentVersion"].strip()
        assert standard["currentAsOf"] == register["asOf"]
        assert standard["normativeStatus"].strip()
        assert set(standard["applicability"]) == {
            "scope",
            "conditions",
            "exclusions",
        }
        assert all(standard["applicability"].values())
        assert standard["requirements"]
        assert standard["recordEvidenceFields"]
        assert standard["uiTreatments"]
        assert standard["automatedChecks"]

        for requirement in standard["requirements"]:
            requirement_id = requirement["id"]
            assert requirement_id not in requirement_ids
            requirement_ids.add(requirement_id)
            assert requirement["requirementLevel"] in REQUIREMENT_LEVELS
            seen_levels.add(requirement["requirementLevel"])
            assert requirement["theme"].strip()
            assert requirement["statement"].strip()
            assert requirement["applicability"].strip()
            assert requirement["evidenceFields"]
            assert requirement["evaluation"].strip()

    assert seen_levels == REQUIREMENT_LEVELS


def test_no_certification_or_accuracy_claim_is_encoded_as_a_positive_result() -> None:
    standards = load_json(STANDARDS_REGISTER)
    crosswalk = load_json(ONTOLOGY_CROSSWALK)
    combined = json.dumps(
        {"standards": standards, "crosswalk": crosswalk},
        sort_keys=True,
    ).casefold()

    assert '"certifiesstatisticalaccuracy": true' not in combined
    assert '"certifiesstandardscompliance": true' not in combined
    assert '"status": "compliant"' not in combined
    assert '"status": "certified"' not in combined
    assert "observation accuracy from metadata completeness" in combined
    assert "not-evidenced" in combined


def test_ontology_crosswalk_preserves_identity_and_confusable_alternatives() -> None:
    crosswalk = load_json(ONTOLOGY_CROSSWALK)
    standards = load_json(STANDARDS_REGISTER)
    standard_ids = {standard["id"] for standard in standards["standards"]}

    assert crosswalk["schemaVersion"] == "okf-ons.ontology-crosswalk.v1"
    assert crosswalk["asOf"] == standards["asOf"]
    assert crosswalk["assuranceBoundary"]["sourceNativeIdentityIsCanonical"] is True
    assert crosswalk["assuranceBoundary"]["crosswalkReplacesSourceMeaning"] is False
    assert crosswalk["namespaces"]["dcat"] == "http://www.w3.org/ns/dcat#"
    assert crosswalk["namespaces"]["prov"] == "http://www.w3.org/ns/prov#"
    assert crosswalk["namespaces"]["skos"] == "http://www.w3.org/2004/02/skos/core#"

    fields = {field["field"]: field for field in crosswalk["canonicalFields"]}
    assert len(fields) == len(crosswalk["canonicalFields"])
    assert {
        "identifier",
        "statisticalStatus",
        "version",
        "population",
        "concept",
        "measure",
        "unit",
        "dimensions",
        "geography",
        "methodology",
        "uncertaintyAndLimitations",
        "revision",
        "productionProcess",
        "provenance",
        "relationships",
        "standardsEvidence",
    } <= set(fields)
    assert all(
        fields[name]["decisionSignature"]
        for name in {
            "identifier",
            "statisticalStatus",
            "version",
            "population",
            "concept",
            "measure",
            "unit",
            "dimensions",
            "geography",
            "methodology",
            "uncertaintyAndLimitations",
            "revision",
            "productionProcess",
        }
    )

    for field in fields.values():
        assert field["mappings"]
        for mapping in field["mappings"]:
            assert mapping["standardId"] in standard_ids
            assert mapping["mappingKind"] in crosswalk["mappingKinds"]
            assert mapping["term"].strip()
            assert mapping["notes"].strip()

    policy = crosswalk["relationshipPolicy"]
    rules_text = " ".join(policy["rules"])
    assert "Never infer equivalence from title" in rules_text
    assert "skos:exactMatch only with evidence" in rules_text
    relationships = {item["type"]: item for item in policy["relationshipTypes"]}
    assert {
        "alternative",
        "close-concept",
        "exact-concept",
        "previous-version",
        "successor",
        "derived-from",
        "cross-source-representation",
    } == set(relationships)
    assert relationships["alternative"]["minimumEvidence"] == [
        "shared subject concept",
        "at least one material discriminator",
    ]


def test_reconciliation_ledger_is_planned_and_does_not_add_source_adapters() -> None:
    register = load_json(SOURCE_REGISTER)

    assert {source["id"] for source in register["sources"]} == {
        "ons-data-api",
        "nomis-dataset-definitions",
        "ons-open-geography",
    }

    ledger = register["reconciliationSourceLedger"]
    assert ledger["schemaVersion"] == "okf-ons.reconciliation-source-ledger.v1"
    lanes = {lane["id"]: lane for lane in ledger["lanes"]}
    assert set(lanes) == PLANNED_RECONCILIATION_LANES

    for lane in lanes.values():
        assert lane["status"] == "planned"
        assert lane["implementationStatus"] == "planned-no-adapter"
        assert "adapter" not in lane
        assert is_absolute_https(lane["authority"]["url"])
        assert is_absolute_https(lane["entrypoint"])
        assert lane["reconciliationRole"]
        assert lane["expectedCrossReferences"]
        assert lane["denominatorPlan"].strip()
        assert lane["stoppingRulePlan"].strip()
        assert lane["publicationBoundary"].strip()

    assert (
        "not the producer source of truth" in lanes["data-gov-uk-ons-records"]["authority"]["role"]
    )
    assert "Not yet defined" in lanes["ons-time-series-identifiers"]["stoppingRulePlan"]
    assert "does not contribute to a coverage or completeness claim" in ledger["coverageRule"]


def test_human_register_documents_currentness_and_assurance_boundary() -> None:
    document = STANDARDS_DOC.read_text(encoding="utf-8")

    assert "current to **17 July 2026**" in document
    assert "Code of Practice for Statistics 3.0" in document
    assert "Legacy Code 2.1 `Q1`, `Q2` and `Q3`" in document
    assert "replaced OSR's 2022 intelligent-transparency" in document
    assert "DQV is a W3C Working Group Note" in document
    assert "Absence of evidence is `not-evidenced`" in document
    assert "not a certification scheme" in document
    assert "There is no single opaque" in document
