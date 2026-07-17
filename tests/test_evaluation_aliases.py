from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_every_gold_alias_is_resolved_or_explained_once() -> None:
    suite = json.loads((ROOT / "evaluation" / "gold-queries.json").read_text())
    register = json.loads((ROOT / "source" / "evaluation-aliases.json").read_text())
    required = {query["target_record_id"] for query in suite["queries"]} | {
        alternative["record_id"]
        for query in suite["queries"]
        for alternative in query["alternatives"]
    }
    resolved = set(register["aliases"])
    unresolved = {row["alias"] for row in register["unresolved"]}

    assert resolved.isdisjoint(unresolved)
    assert resolved | unresolved == required
    assert len(unresolved) == len(register["unresolved"])
    assert all(row["reason"] and row["neededSourceLane"] for row in register["unresolved"])


def test_aliases_are_source_qualified_and_claim_no_equivalence() -> None:
    register = json.loads((ROOT / "source" / "evaluation-aliases.json").read_text())
    assert register["policy"]["statisticalEquivalenceAsserted"] is False
    assert all(value.count(":") >= 2 for value in register["aliases"].values())
