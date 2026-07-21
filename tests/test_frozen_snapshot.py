from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from okf_ons.build import BuildError, default_inputs, load_frozen_corpus

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "source" / "demo-snapshot"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def nested_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for child in value.values() for key in nested_keys(child)}
    if isinstance(value, list):
        return {key for child in value for key in nested_keys(child)}
    return set()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_snapshot_files_match_manifest_and_close_registered_denominators() -> None:
    manifest = load_json(SNAPSHOT / "snapshot.json")

    assert manifest["metadataOnly"] is True
    assert manifest["observationsIncluded"] is False
    assert manifest["completeForRegisteredAdapters"] is True
    assert {row["sourceId"] for row in manifest["sources"]} == {
        "ons-data-api",
        "ons-explore-local-statistics",
        "nomis-dataset-definitions",
        "ons-open-geography",
    }

    for source in manifest["sources"]:
        path = SNAPSHOT / source["file"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source["sha256"]
        acquisition = load_json(path)
        provenance = acquisition["provenance"]
        assert len(acquisition["records"]) == source["recordCount"]
        assert canonical_sha256(acquisition["records"]) == source["recordSetSha256"]
        assert provenance["recordSetSha256"] == source["recordSetSha256"]
        snapshot_receipts = [
            {
                "requestUrl": page["requestUrl"],
                "contentSha256": page["contentSha256"],
            }
            for page in provenance["pages"]
        ]
        assert canonical_sha256(snapshot_receipts) == source["snapshotSetSha256"]
        assert provenance["snapshotSetSha256"] == source["snapshotSetSha256"]
        assert provenance["recordCount"] == source["reportedTotal"]
        assert provenance["coverageComplete"] is True
        assert provenance["normalisationDroppedCount"] == 0
        assert provenance["unrepresentedCount"] == 0

    els = load_json(SNAPSHOT / "ons-explore-local-statistics.json")["provenance"]
    assert els["recordCount"] == 108
    assert els["explainedExclusionCount"] == 12
    assert len(els["explainedExclusions"]) == 12


def test_snapshot_records_have_unique_native_identity_and_no_data_payloads() -> None:
    for path in sorted(SNAPSHOT.glob("*.json")):
        if path.name == "snapshot.json":
            continue
        acquisition = load_json(path)
        record_ids = [row["sourceRecordId"] for row in acquisition["records"]]
        assert len(record_ids) == len(set(record_ids))
        keys = {key.casefold() for key in nested_keys(acquisition["records"])}
        assert "observations" not in keys
        assert "status" not in keys
        assert "value" not in keys
        assert "valuedomain" not in keys
        assert "geometry" not in keys
        serialised = path.read_text(encoding="utf-8").casefold()
        assert "/users/" not in serialised
        assert "/volumes/" not in serialised
        assert "/tmp/" not in serialised
        assert "token=" not in serialised


def _single_source_snapshot(tmp_path: Path, source_id: str) -> tuple[Path, dict[str, Any]]:
    manifest = load_json(SNAPSHOT / "snapshot.json")
    source = next(row for row in manifest["sources"] if row["sourceId"] == source_id)
    manifest["sources"] = [source]
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()
    shutil.copy2(SNAPSHOT / source["file"], snapshot_dir / source["file"])
    (snapshot_dir / "snapshot.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return snapshot_dir, source


@pytest.mark.parametrize("tamper", ["records", "pages", "manifest-record-digest"])
def test_loader_rejects_tampered_digest_bindings(tmp_path: Path, tamper: str) -> None:
    snapshot_dir, source = _single_source_snapshot(
        tmp_path, "ons-explore-local-statistics"
    )
    acquisition_path = snapshot_dir / source["file"]
    acquisition = load_json(acquisition_path)

    if tamper == "records":
        acquisition["records"][0]["title"] += " tampered"
    elif tamper == "pages":
        acquisition["provenance"]["pages"][0]["requestUrl"] += "?tampered=true"
    else:
        source["recordSetSha256"] = "0" * 64

    if tamper != "manifest-record-digest":
        acquisition_path.write_text(
            json.dumps(acquisition, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        source["sha256"] = hashlib.sha256(acquisition_path.read_bytes()).hexdigest()
    manifest_path = snapshot_dir / "snapshot.json"
    manifest = load_json(manifest_path)
    manifest["sources"] = [source]
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    inputs = replace(default_inputs(ROOT), snapshot_directory=snapshot_dir)
    with pytest.raises(BuildError, match="(?:record|snapshot)-set hash mismatch"):
        load_frozen_corpus(inputs)
