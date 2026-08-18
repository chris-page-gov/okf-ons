from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_publication_contract as MODULE  # noqa: E402


def load_contract() -> dict[str, object]:
    return json.loads((ROOT / "okf.publication.json").read_text(encoding="utf-8"))


def test_repository_contract_has_valid_local_references() -> None:
    assert MODULE.validate_document(load_contract()) == []


def test_unknown_command_fails_closed() -> None:
    document = copy.deepcopy(load_contract())
    document["planes"][0]["command_ids"].append("not-declared")
    assert any("unknown command" in error for error in MODULE.validate_document(document))


def test_plane_cycle_is_rejected() -> None:
    document = copy.deepcopy(load_contract())
    document["planes"][0]["depends_on"] = [document["planes"][-1]["id"]]
    assert any("cycle" in error for error in MODULE.validate_document(document))


def test_contract_is_documented_in_lockstep_surfaces() -> None:
    for path in ("README.md", "AGENTS.md", "CHANGELOG.md"):
        assert "okf.publication.json" in (ROOT / path).read_text(encoding="utf-8"), path
