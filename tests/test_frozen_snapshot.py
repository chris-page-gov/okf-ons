from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

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


def test_snapshot_files_match_manifest_and_close_registered_denominators() -> None:
    manifest = load_json(SNAPSHOT / "snapshot.json")

    assert manifest["metadataOnly"] is True
    assert manifest["observationsIncluded"] is False
    assert manifest["completeForRegisteredAdapters"] is True
    assert {row["sourceId"] for row in manifest["sources"]} == {
        "ons-data-api",
        "nomis-dataset-definitions",
        "ons-open-geography",
    }

    for source in manifest["sources"]:
        path = SNAPSHOT / source["file"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source["sha256"]
        acquisition = load_json(path)
        provenance = acquisition["provenance"]
        assert len(acquisition["records"]) == source["recordCount"]
        assert provenance["recordCount"] == source["reportedTotal"]
        assert provenance["coverageComplete"] is True
        assert provenance["normalisationDroppedCount"] == 0
        assert provenance["unrepresentedCount"] == 0


def test_snapshot_records_have_unique_native_identity_and_no_data_payloads() -> None:
    for path in sorted(SNAPSHOT.glob("*.json")):
        if path.name == "snapshot.json":
            continue
        acquisition = load_json(path)
        record_ids = [row["sourceRecordId"] for row in acquisition["records"]]
        assert len(record_ids) == len(set(record_ids))
        keys = {key.casefold() for key in nested_keys(acquisition["records"])}
        assert "observations" not in keys
        assert "geometry" not in keys
        serialised = path.read_text(encoding="utf-8").casefold()
        assert "/users/" not in serialised
        assert "/volumes/" not in serialised
        assert "/tmp/" not in serialised
        assert "token=" not in serialised
