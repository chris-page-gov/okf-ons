from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from okf_ons.els import (  # noqa: E402
    ELS_MANIFEST_EXCLUSION_COUNT,
    ELS_PUBLISHED_INDICATOR_COUNT,
    ELSProjectionError,
    project_els_snapshot,
    validate_els_acquisition_envelope,
)

ELS = ROOT / "vendor" / "explore-local-statistics-app"
ELS_COMMIT = "795eaf204f47986f6be248a63f857a42afe4fdf2"
COMMIT_AS_OF = "2026-07-17T08:35:03Z"
FROZEN_RETRIEVED_AT = "2026-07-21T09:10:11Z"
INPUTS = (
    Path("src/lib/data/json-stat-metadata.json"),
    Path("scripts/config/manifest_metadata.csv"),
    Path("src/lib/data/indicator_redirects.json"),
)
FORBIDDEN_KEYS = {
    "arcs",
    "binary",
    "blob",
    "coordinates",
    "data",
    "features",
    "geometry",
    "observation",
    "observations",
    "status",
    "topology",
    "value",
    "valuedomain",
    "values",
}


def nested_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return {
            "".join(character for character in str(key).casefold() if character.isalnum())
            for key in value
        } | {key for child in value.values() for key in nested_keys(child)}
    if isinstance(value, list):
        return {key for child in value for key in nested_keys(child)}
    return set()


def copied_inputs(tmp_path: Path) -> Path:
    checkout = tmp_path / "els"
    for relative in INPUTS:
        target = checkout / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ELS / relative, target)
    return checkout


def project(path: Path = ELS) -> dict[str, Any]:
    return project_els_snapshot(
        path,
        submodule_commit=ELS_COMMIT,
        commit_as_of=COMMIT_AS_OF,
        retrieved_at=FROZEN_RETRIEVED_AT,
    )


def test_real_pinned_projection_closes_denominator_and_is_metadata_only() -> None:
    result = project()
    provenance = result["provenance"]
    records = result["records"]

    assert result["schemaVersion"] == "okf-ons.source-acquisition.v1"
    assert len(records) == ELS_PUBLISHED_INDICATOR_COUNT
    assert provenance["reportedTotal"] == ELS_PUBLISHED_INDICATOR_COUNT
    assert provenance["recordCount"] == ELS_PUBLISHED_INDICATOR_COUNT
    assert provenance["coverageComplete"] is True
    assert provenance["unrepresentedCount"] == 0
    assert provenance["normalisationDroppedCount"] == 0
    assert provenance["explainedExclusionCount"] == ELS_MANIFEST_EXCLUSION_COUNT


    assert len(provenance["explainedExclusions"]) == ELS_MANIFEST_EXCLUSION_COUNT
    assert provenance["assurance"]["metadataOnly"] is True
    assert provenance["assurance"]["observationsFetched"] is False
    assert provenance["submodule"]["commit"] == ELS_COMMIT
    assert provenance["submodule"]["commitAsOf"] == COMMIT_AS_OF
    assert provenance["submodule"]["commitAsOfVerified"] is True
    assert provenance["acquisition"] == {
        "retrievedAt": FROZEN_RETRIEVED_AT,
        "timestampSource": "supplied",
    }
    assert {
        page["retrievedAt"] for page in provenance["pages"]
    } == {FROZEN_RETRIEVED_AT}
    assert "projectionTimestamp" not in provenance["submodule"]
    assert "projectionTimestampSource" not in provenance["submodule"]
    assert provenance["source"]["adapter"] == "els-metadata-projection"

    record_ids = [record["sourceRecordId"] for record in records]
    assert len(record_ids) == len(set(record_ids))
    assert not (nested_keys(result) & FORBIDDEN_KEYS)
    serialised = json.dumps(result, sort_keys=True)
    assert str(ROOT) not in serialised
    assert "/Users/" not in serialised
    assert "/tmp/" not in serialised

    population = next(
        record for record in records if record["sourceRecordId"] == "population-by-age-and-sex"
    )
    assert population["dimensionOrder"] == ["areacd", "period", "sex", "age", "measure"]
    area_dimension = next(
        dimension for dimension in population["dimensions"] if dimension["id"] == "areacd"
    )
    sex_dimension = next(
        dimension for dimension in population["dimensions"] if dimension["id"] == "sex"
    )
    assert area_dimension["categoryProjection"] == "count-only"
    assert area_dimension["categoryCount"] == 413
    assert "categories" not in area_dimension
    assert sex_dimension["categoryProjection"] == "identifiers-and-labels"
    assert [category["id"] for category in sex_dimension["categories"]] == [
        "all",
        "female",
        "male",
    ]
    assert population["operator"]["name"] == "Office for National Statistics"
    assert population["producers"]
    assert population["derivation"]["mode"] == "application-curated-extract"
    assert population["derivation"]["sourceEditionVersionAvailable"] is False


def test_projected_envelope_validator_rejects_unsafe_fields_and_digest_tampering() -> None:
    valid = project()
    validate_els_acquisition_envelope(valid)

    observations = json.loads(json.dumps(valid))
    observations["records"][0]["observations"] = [1]
    with pytest.raises(ELSProjectionError, match="Unsafe field 'observations'"):
        validate_els_acquisition_envelope(observations)

    credential = json.loads(json.dumps(valid))
    credential["records"][0]["description"] = "ghp_abcdefghijklmnopqrstuvwxyz123456"
    with pytest.raises(ELSProjectionError, match="Credential-like value"):
        validate_els_acquisition_envelope(credential)

    unexpected = json.loads(json.dumps(valid))
    unexpected["records"][0]["unreviewedMetadata"] = "must not pass"
    with pytest.raises(ELSProjectionError, match="unreviewed field"):
        validate_els_acquisition_envelope(unexpected)

    record_tamper = json.loads(json.dumps(valid))
    record_tamper["records"][0]["title"] += " tampered"
    with pytest.raises(ELSProjectionError, match="record-set hash mismatch"):
        validate_els_acquisition_envelope(record_tamper)

    receipt_tamper = json.loads(json.dumps(valid))
    receipt_tamper["provenance"]["snapshotSetSha256"] = "0" * 64
    with pytest.raises(ELSProjectionError, match="snapshot-set hash mismatch"):
        validate_els_acquisition_envelope(receipt_tamper)


def test_acquisition_cli_fail_closes_on_unsafe_projected_envelope(tmp_path: Path) -> None:
    register = json.loads((ROOT / "source/source-register.json").read_text(encoding="utf-8"))
    register["sources"] = [
        source
        for source in register["sources"]
        if source["id"] == "ons-explore-local-statistics"
    ]
    register_path = tmp_path / "source-register.json"
    register_path.write_text(json.dumps(register), encoding="utf-8")

    unsafe = project()
    unsafe["records"][0]["credentials"] = "must-not-publish"
    projected_path = tmp_path / "unsafe-projection.json"
    projected_path.write_text(json.dumps(unsafe), encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/acquire_snapshot.py"),
            "--source-register",
            str(register_path),
            "--cache-dir",
            str(tmp_path / "cache"),
            "--output-dir",
            str(tmp_path / "snapshots"),
            "--snapshot-id",
            "unsafe",
            "--projected-acquisition",
            str(projected_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "unsafe projected acquisition" in completed.stderr
    assert "Unsafe field 'credentials'" in completed.stderr


def test_projection_is_deterministic_and_aliases_only_target_published_records() -> None:
    first = project()
    second = project()
    assert first == second
    assert first["provenance"]["recordSetSha256"] == second["provenance"]["recordSetSha256"]

    records = first["records"]
    aliases = [alias for record in records for alias in record["aliases"]]
    assert len(aliases) == 46
    assert len(aliases) == len(set(aliases))
    assert first["provenance"]["aliasProjection"]["inputCount"] == 52
    assert first["provenance"]["aliasProjection"]["acceptedCount"] == 46
    assert first["provenance"]["aliasProjection"]["excludedCount"] == 6


def test_default_projection_uses_commit_time_only_as_commit_evidence() -> None:
    first = project_els_snapshot(ELS, submodule_commit=ELS_COMMIT)
    second = project_els_snapshot(ELS, submodule_commit=ELS_COMMIT)

    assert first == second
    provenance = first["provenance"]
    assert provenance["submodule"]["commitAsOf"] == COMMIT_AS_OF
    assert provenance["submodule"]["commitAsOfResolution"] == "discovered-from-git"
    assert provenance["submodule"]["commitAsOfVerified"] is True
    assert "acquisition" not in provenance
    assert all("retrievedAt" not in page for page in provenance["pages"])


def test_projection_fails_if_metadata_count_no_longer_matches_manifest(tmp_path: Path) -> None:
    checkout = copied_inputs(tmp_path)
    path = checkout / "src/lib/data/json-stat-metadata.json"
    metadata = json.loads(path.read_text(encoding="utf-8"))
    metadata["link"]["item"].pop()
    path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ELSProjectionError, match="published indicator count changed"):
        project(checkout)


@pytest.mark.parametrize(
    ("field", "payload", "message"),
    [
        ("value", [123], "non-empty observation value payload"),
        ("status", {"0": "confidential"}, "unreviewed field"),
        ("geometry", {"coordinates": [[0, 0]]}, "unreviewed field"),
    ],
)
def test_projection_fails_closed_on_observation_or_geometry_content(
    tmp_path: Path,
    field: str,
    payload: Any,
    message: str,
) -> None:
    checkout = copied_inputs(tmp_path)
    path = checkout / "src/lib/data/json-stat-metadata.json"
    metadata = json.loads(path.read_text(encoding="utf-8"))
    metadata["link"]["item"][0][field] = payload
    path.write_text(json.dumps(metadata), encoding="utf-8")

    with pytest.raises(ELSProjectionError, match=message):
        project(checkout)


def test_projection_fails_on_unexplained_missing_alias_target(tmp_path: Path) -> None:
    checkout = copied_inputs(tmp_path)
    path = checkout / "src/lib/data/indicator_redirects.json"
    aliases = json.loads(path.read_text(encoding="utf-8"))
    aliases["unexpected-old-indicator"] = "unexpected-missing-target"
    path.write_text(json.dumps(aliases), encoding="utf-8")

    with pytest.raises(ELSProjectionError, match="unexplained missing target"):
        project(checkout)


def test_projection_verifies_expected_input_hashes() -> None:
    with pytest.raises(ELSProjectionError, match="hash mismatch"):
        project_els_snapshot(
            ELS,
            submodule_commit=ELS_COMMIT,
            commit_as_of=COMMIT_AS_OF,
            retrieved_at=FROZEN_RETRIEVED_AT,
            expected_hashes={"indicatorMetadata": "0" * 64},
        )


def test_projection_rejects_supplied_commit_that_differs_from_checkout() -> None:
    with pytest.raises(ELSProjectionError, match="does not match the submodule HEAD"):
        project_els_snapshot(
            ELS,
            submodule_commit="0" * 40,
            commit_as_of=COMMIT_AS_OF,
            retrieved_at=FROZEN_RETRIEVED_AT,
        )


def test_projection_rejects_commit_as_of_that_differs_from_git() -> None:
    with pytest.raises(ELSProjectionError, match="does not match the verified Git commit time"):
        project_els_snapshot(
            ELS,
            submodule_commit=ELS_COMMIT,
            commit_as_of="2026-07-18T08:35:03Z",
        )


def test_gitless_fixture_requires_separate_commit_as_of_evidence(tmp_path: Path) -> None:
    checkout = copied_inputs(tmp_path)

    with pytest.raises(ELSProjectionError, match="requires explicit commit-as-of evidence"):
        project_els_snapshot(
            checkout,
            submodule_commit=ELS_COMMIT,
            retrieved_at=FROZEN_RETRIEVED_AT,
        )

    result = project_els_snapshot(
        checkout,
        submodule_commit=ELS_COMMIT,
        commit_as_of=COMMIT_AS_OF,
        retrieved_at=FROZEN_RETRIEVED_AT,
    )
    submodule = result["provenance"]["submodule"]
    assert submodule["commitAsOf"] == COMMIT_AS_OF
    assert submodule["commitAsOfResolution"] == "supplied-explicit-evidence"
    assert submodule["commitAsOfVerified"] is False
    assert result["provenance"]["acquisition"]["retrievedAt"] == FROZEN_RETRIEVED_AT


def test_cli_writes_standalone_acquisition_envelope(tmp_path: Path) -> None:
    output = tmp_path / "els-projection.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/project_els_snapshot.py"),
            "--submodule-dir",
            str(ELS),
            "--submodule-commit",
            ELS_COMMIT,
            "--commit-as-of",
            COMMIT_AS_OF,
            "--retrieved-at",
            FROZEN_RETRIEVED_AT,
            "--output",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["provenance"]["recordCount"] == ELS_PUBLISHED_INDICATOR_COUNT
    assert result["provenance"]["submodule"]["commitAsOf"] == COMMIT_AS_OF
    assert result["provenance"]["acquisition"]["retrievedAt"] == FROZEN_RETRIEVED_AT
    assert "108 records" in completed.stdout
    assert "explained exclusions 12" in completed.stdout
