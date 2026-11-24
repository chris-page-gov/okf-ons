from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from okf_ons.build import _core_explorer_projection

SPEC = importlib.util.spec_from_file_location(
    "core_projection", Path(__file__).resolve().parents[1] / "scripts/check_core_projection.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fixture(tmp_path: Path):
    source = b"---\ntitle: Example\ntype: concept\n---\nAn exact source body.\n"
    (tmp_path / "concept.md").write_bytes(source)
    node = {
        "frontmatter": {"title": "Example", "type": "concept"},
        "body": "An exact source body.\n", "source_path": "concept.md",
        "source_bytes": len(source), "source_sha256": hashlib.sha256(source).hexdigest(),
    }
    projection = tmp_path / "independent.json"
    projection.write_text(json.dumps({"nodes": {"concept.md": node}, "edges": []}))
    descriptor = {
        "schema": "okf-explorer-bundle.v0",
        "bundle_id": "https://chris-page-gov.github.io/okf-ons/okf-core-explorer.json",
        "version": "0.3.0",
        "snapshot": "monday-2026-07-17-r2",
        "nodes": {"concept.md": node},
        "edges": [],
    }
    (tmp_path / "okf-core-explorer.json").write_text(json.dumps(descriptor))
    return projection, descriptor


def test_full_source_parity(tmp_path):
    projection, _ = fixture(tmp_path)
    assert MODULE.check(projection, tmp_path)["concepts"] == 1


def test_reader_body_boundary_rule_keeps_original_source_identity():
    documents = {"index.md": '---\nokf_version: "0.3"\n---\n\n# Index\n'}
    for index in range(12):
        documents[f"concept-{index}.md"] = (
            '---\ntype: "concept"\ntitle: "Example"\n---\n\n'
            '# Exact body\n\n  Indented internal content.\n\n'
        )
    result = _core_explorer_projection(
        documents,
        bundle_id="https://chris-page-gov.github.io/okf-ons/okf-core-explorer.json",
        version="0.3.0",
        snapshot="monday-2026-07-17-r2",
    )
    for route, node in result["nodes"].items():
        assert node["body"] == '# Exact body\n\n  Indented internal content.'
        raw = documents[route].encode()
        assert node["source_bytes"] == len(raw)
        assert node["source_sha256"] == hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize("damage", ["body", "frontmatter", "coverage", "edge", "source-bytes"])
def test_reject_projection_or_source_drift(tmp_path, damage):
    projection, descriptor = fixture(tmp_path)
    node = descriptor["nodes"]["concept.md"]
    if damage == "body":
        node["body"] = "A changed body"
    elif damage == "frontmatter":
        node["frontmatter"]["title"] = "A changed title"
    elif damage == "coverage":
        descriptor["nodes"] = {}
    elif damage == "edge":
        descriptor["edges"] = [{"source": "concept.md", "target": "concept.md"}]
    else:
        (tmp_path / "concept.md").write_text("Changed source bytes")
    (tmp_path / "okf-core-explorer.json").write_text(json.dumps(descriptor))
    with pytest.raises(ValueError):
        MODULE.check(projection, tmp_path)
