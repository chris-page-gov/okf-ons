from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from okf_ons.build import check_bundle, compile_bundle, default_inputs  # noqa: E402


def test_full_frozen_bundle_is_deterministic_and_keeps_claim_boundaries(
    tmp_path: Path,
) -> None:
    inputs = default_inputs(ROOT)
    output = tmp_path / "bundle"
    result = compile_bundle(inputs, output)
    check_bundle(inputs, output)

    descriptor = result["descriptor"]
    coverage = result["coverage"]
    reconciliation = result["reconciliation"]
    evaluation = result["evaluation"]

    assert descriptor["schema"] == "okf-explorer-large-corpus.v1"
    assert descriptor["counts"]["records"] == 4_989
    assert descriptor["scope"]["complete_ons_corpus"] is False
    assert coverage["implementedScope"]["represented"] == 4_989
    assert coverage["implementedScope"]["implementedLaneUnexplainedOmissions"] == 0
    assert coverage["unexplained_omissions"] is None
    assert coverage["releaseGate"]["passed"] is False
    assert reconciliation["anchor_codes_detected"] == 284
    assert reconciliation["matched_code_count"] == 283
    assert reconciliation["title_aligned_code_count"] == 280
    assert reconciliation["title_conflicted_code_count"] == 3
    assert reconciliation["unmatched_anchor_codes"] == ["RM010"]
    assert evaluation["statistical_accuracy"]["evaluated"] is False
    assert evaluation["release_gate"]["enabled"] is False

    required = (
        "okf-explorer.json",
        "okf-bundle.jsonld",
        "okf-bundle.yamlld",
        "data/manifest.json",
        "data/search/manifest.json",
        "data/demo/contrast-records.json",
        "data/coverage/ledger.json",
        "data/standards/evaluation.json",
        "data/evaluation/report.json",
        "data/ons/mcp-bindings.json",
        "data/ons/spatial-index.json",
        "checksums.json",
    )
    assert all((output / path).is_file() for path in required)

    search_manifest = json.loads((output / "data/search/manifest.json").read_text())
    assert search_manifest["snapshot"] == descriptor["snapshot"]
    search_entrypoints = search_manifest["entrypoints"]
    assert all((output / path).is_file() for path in search_entrypoints["result_docs"])
    assert all((output / path).is_file() for path in search_entrypoints["lexicon"].values())
    assert all((output / path).is_file() for path in search_entrypoints["prefixes"].values())
    assert all((output / path).is_file() for path in search_entrypoints["postings"])
    assert (output / search_entrypoints["doc_map"]).is_file()

    data_manifest = json.loads((output / "data/manifest.json").read_text())
    overview = json.loads((output / "data/overview.json").read_text())
    analysis = json.loads((output / "data/analysis/overview.json").read_text())
    assert data_manifest["title"] == descriptor["title"]
    assert data_manifest["snapshot"] == descriptor["snapshot"]
    assert overview["snapshot"] == descriptor["snapshot"]
    assert analysis["snapshot"] == descriptor["snapshot"]
    dataset_rows = [
        row
        for path in data_manifest["chunks"]["datasets"]
        for row in json.loads((output / path).read_text())
    ]
    dataset_names = {row["name"] for row in dataset_rows}
    resource_datasets = {
        row["dataset"]
        for path in data_manifest["chunks"]["resources"]
        for row in json.loads((output / path).read_text())
    }
    assert resource_datasets == dataset_names
    publisher_rows = [
        row
        for path in data_manifest["chunks"]["publishers"]
        for row in json.loads((output / path).read_text())
    ]
    assert publisher_rows[0]["resource_count"] == len(resource_datasets)

    for key in (
        "metadata_evidence_band",
        "has_methodology",
        "has_quality_documentation",
        "has_alternatives",
    ):
        postings = json.loads((output / search_entrypoints["filter_postings"][key]).read_text())
        ordinal_sets = {value: set(ordinals) for value, ordinals in postings["values"].items()}
        assert all(ordinal in ordinal_sets[row[key]] for ordinal, row in enumerate(dataset_rows))

    lexicon_tokens = {
        row["token"]
        for shard in ("nm", "uk")
        for row in json.loads((output / search_entrypoints["lexicon"][shard]).read_text())
    }
    assert {"nm_66_1", "uk"}.issubset(lexicon_tokens)

    mcp_bindings = json.loads((output / "data/ons/mcp-bindings.json").read_text())
    spatial_index = json.loads((output / "data/ons/spatial-index.json").read_text())
    record_ids = {row["id"] for row in dataset_rows}
    assert all(row["record_id"] in record_ids for row in mcp_bindings["bindings"])
    assert mcp_bindings["availableBindingCount"] == 1_954
    assert mcp_bindings["plannedBindingCount"] == 3_035
    available_tools = {
        row.get("tool") for row in mcp_bindings["bindings"] if row.get("mcp_available") is True
    }
    assert available_tools == {"ons_data.dimensions", "nomis.datasets"}
    assert all(
        isinstance(row["arguments"]["version"], str)
        for row in mcp_bindings["bindings"]
        if row.get("tool") == "ons_data.dimensions"
    )
    assert all(
        row.get("tool") is None and row.get("binding_status") == "planned"
        for row in mcp_bindings["bindings"]
        if row.get("source_surface") == "ons-open-geography"
    )
    assert all(row["record_id"] in record_ids for row in spatial_index["records"])
    assert spatial_index["recordsWithBbox"] == 2_687
    explorer_bbox_rows = [row for row in dataset_rows if row.get("bbox")]
    assert len(explorer_bbox_rows) == 2_687
    assert all(row["bbox_evidence"] == "source-portal-extent" for row in explorer_bbox_rows)
    assert all(
        len(row["bbox"]) == 4
        for row in spatial_index["records"]
        if row["bbox_evidence"] == "portal-extent"
    )

    nomis_rows = [row for row in dataset_rows if row["source_surface"] == "nomis"]
    assert any(row.get("content_source") for row in nomis_rows)
    assert any(row.get("first_released") for row in nomis_rows)
    assert any(row.get("mnemonic") for row in nomis_rows)
    assert any(row.get("publisher_uri") for row in nomis_rows)
    assert all(
        row["publication"]["release_date"] == row.get("first_released", "") for row in nomis_rows
    )
    geography_rows = [row for row in dataset_rows if row["source_surface"] == "ons-open-geography"]
    assert any(row.get("portal_owner") for row in geography_rows)
    assert any(row.get("source_organisation") for row in geography_rows)

    semantic_bundle = json.loads((output / "okf-bundle.jsonld").read_text())
    assert semantic_bundle["conformsTo"]
    assert "do not assert" in semantic_bundle["alignmentClaim"]
    assert all("conformsTo" not in row for row in semantic_bundle["dataset"])

    checksums = json.loads((output / "checksums.json").read_text())
    for row in checksums["files"]:
        data = (output / row["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == row["sha256"]


def test_public_bundle_has_no_credentials_or_machine_paths(tmp_path: Path) -> None:
    output = tmp_path / "bundle"
    compile_bundle(default_inputs(ROOT), output)
    prohibited = (b"/Users/", b"/Volumes/", b"/tmp/", b"token=", b"api_key=")
    for path in output.rglob("*"):
        if path.is_file():
            data = path.read_bytes()
            assert all(value not in data for value in prohibited), path
