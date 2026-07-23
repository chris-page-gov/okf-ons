from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from okf_ons.build import (
    BuildError,
    build_provider_datapacks,
    canonical_json,
    default_inputs,
    load_frozen_corpus,
)

ROOT = Path(__file__).resolve().parents[1]
PACK_ID = "ons-explore-local-statistics"
AVERAGE_HOUSE_PRICE = "ons-explore-local-statistics:indicator:average-house-price"


def _corpus():
    return load_frozen_corpus(default_inputs(ROOT))


def _copied_pack_directory(tmp_path: Path) -> Path:
    target = tmp_path / "provider-datapacks"
    shutil.copytree(ROOT / "source" / "provider-datapacks", target)
    return target


def test_els_provider_datapack_separates_governed_snapshot_and_live_reference() -> None:
    corpus = _corpus()
    packs, manifest = build_provider_datapacks(corpus, ROOT / "source" / "provider-datapacks")
    [pack] = packs
    pack_sha256 = hashlib.sha256(canonical_json(pack).encode("utf-8")).hexdigest()

    assert manifest == {
        "schema": "okf-explorer-provider-datapack-manifest.v1",
        "snapshot": corpus.snapshot["snapshotId"],
        "packCount": 1,
        "packs": [
            {
                "id": PACK_ID,
                "selector": {
                    "field": "source_surface",
                    "operator": "equals",
                    "value": PACK_ID,
                },
                "path": f"data/providers/{PACK_ID}.json",
                "sha256": pack_sha256,
                "status": "known-drift",
                "lastChecked": "2026-07-23",
            }
        ],
    }

    assert pack["schema"] == "okf-explorer-provider-datapack.v1"
    assert pack["snapshot"] == manifest["snapshot"]
    assert pack["selector"] == manifest["packs"][0]["selector"]
    governed = pack["governedSnapshot"]
    assert governed["status"] == "governed-pinned-snapshot"
    assert governed["recordCount"] == 108
    assert governed["sourceCommit"] == "795eaf204f47986f6be248a63f857a42afe4fdf2"
    assert governed["sourceCommitShort"] == "795eaf2"
    assert governed["sourceAsOf"] == "2026-07-17T08:35:03Z"
    assert governed["metadataOnly"] is True
    assert governed["observationsIncluded"] is False

    live = pack["reviewedLiveReference"]
    assert live["status"] == "reviewed-reference-not-live-validated"
    assert live["lastChecked"] == "2026-07-23"
    assert live["network"] == "external"
    assert live["sourceCommit"] == "d5f0ac948f8f2f5da2dacd0011ef4e4778918b01"
    assert live["sourceCommitShort"] == "d5f0ac9"

    comparison = pack["comparison"]
    assert comparison["status"] == "known-drift"
    assert comparison["evidenceScope"] == "reviewed-record-examples"
    assert comparison["exhaustive"] is False
    assert comparison["executionRequiresLiveValidation"] is True
    [difference] = comparison["differences"]
    assert difference["recordId"] == AVERAGE_HOUSE_PRICE
    assert difference["fields"][0] == {
        "field": "timeCoverage.end",
        "snapshot": "2026-04-01/P1M",
        "reviewedLiveReference": "2026-05-01/P1M",
    }
    assert {row["recordId"]: row["timeCoverageEnd"] for row in governed["records"]} == {
        AVERAGE_HOUSE_PRICE: "2026-04-01/P1M"
    }
    assert {row["recordId"]: row["timeCoverageEnd"] for row in live["records"]} == {
        AVERAGE_HOUSE_PRICE: "2026-05-01/P1M"
    }

    presentation = pack["presentation"]
    assert presentation["snapshotLabel"] == "Governed snapshot"
    assert presentation["liveLabel"] == "Reviewed live reference"
    assert "not live-validated" in presentation["lastCheckedWording"]
    assert presentation["actions"][0] == {
        "id": "open-live-indicator",
        "label": "Open live indicator",
        "kind": "external-link",
        "urlTemplate": ("https://www.ons.gov.uk/explore-local-statistics/indicators/{native_id}"),
        "network": "external",
    }
    assert presentation["actions"][1] == {
        "id": "open-live-service",
        "label": "Open live service",
        "kind": "external-link",
        "urlTemplate": "https://www.ons.gov.uk/explore-local-statistics/",
        "network": "external",
    }


def test_provider_datapack_fails_closed_if_frozen_example_no_longer_matches(
    tmp_path: Path,
) -> None:
    directory = _copied_pack_directory(tmp_path)
    path = directory / f"{PACK_ID}.json"
    source = json.loads(path.read_text(encoding="utf-8"))
    source["snapshotExpectations"]["records"][0]["timeCoverageEnd"] = "2026-05-01/P1M"
    path.write_text(json.dumps(source), encoding="utf-8")

    with pytest.raises(
        BuildError,
        match=(
            "frozen ons-explore-local-statistics:indicator:average-house-price "
            "timeCoverageEnd changed"
        ),
    ):
        build_provider_datapacks(_corpus(), directory)


def test_provider_datapack_cannot_claim_an_exhaustive_live_comparison(
    tmp_path: Path,
) -> None:
    directory = _copied_pack_directory(tmp_path)
    path = directory / f"{PACK_ID}.json"
    source = json.loads(path.read_text(encoding="utf-8"))
    source["comparison"]["exhaustive"] = True
    path.write_text(json.dumps(source), encoding="utf-8")

    with pytest.raises(BuildError, match="must be explicitly non-exhaustive"):
        build_provider_datapacks(_corpus(), directory)


def test_provider_datapack_rejects_unsafe_action_urls_and_identifiers(
    tmp_path: Path,
) -> None:
    directory = _copied_pack_directory(tmp_path)
    path = directory / f"{PACK_ID}.json"
    source = json.loads(path.read_text(encoding="utf-8"))
    source["presentation"]["actions"][0]["urlTemplate"] = (
        "https://user:secret@example.com/indicators/{native_id}"
    )
    path.write_text(json.dumps(source), encoding="utf-8")

    with pytest.raises(BuildError, match="absolute HTTPS URL without credentials"):
        build_provider_datapacks(_corpus(), directory)

    source["presentation"]["actions"][0]["urlTemplate"] = (
        "https://www.ons.gov.uk/explore-local-statistics/indicators/{native_id}"
    )
    source["presentation"]["actions"][0]["id"] = "open live indicator"
    path.write_text(json.dumps(source), encoding="utf-8")

    with pytest.raises(BuildError, match="must be a safe identifier"):
        build_provider_datapacks(_corpus(), directory)


def test_provider_datapack_rejects_unsafe_selector_fields(tmp_path: Path) -> None:
    directory = _copied_pack_directory(tmp_path)
    path = directory / f"{PACK_ID}.json"
    source = json.loads(path.read_text(encoding="utf-8"))
    source["selector"]["field"] = "source.surface"
    path.write_text(json.dumps(source), encoding="utf-8")

    with pytest.raises(BuildError, match="must be a safe record field"):
        build_provider_datapacks(_corpus(), directory)


def test_provider_datapack_requires_consistent_selected_source_provenance() -> None:
    corpus = _corpus()
    selected = next(
        record for record in corpus.records if record.get("source_surface") == PACK_ID
    )
    selected["provenance"]["source_as_of"] = "2026-07-18T00:00:00Z"

    with pytest.raises(
        BuildError,
        match="source provenance differs across selected records",
    ):
        build_provider_datapacks(corpus, ROOT / "source" / "provider-datapacks")
