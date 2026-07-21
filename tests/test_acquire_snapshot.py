from __future__ import annotations

import json
import runpy
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "acquire_snapshot.py"
REGISTER = ROOT / "source" / "source-register.json"
BASE_SNAPSHOT = ROOT / "source" / "demo-snapshot"


def _script_namespace() -> dict[str, Any]:
    return runpy.run_path(str(SCRIPT), run_name="acquire_snapshot_test")


def test_canonical_json_is_stable_and_strict() -> None:
    namespace = _script_namespace()
    first = namespace["canonical_json"]({"b": 2, "a": ["£", 1]})
    second = namespace["canonical_json"]({"a": ["£", 1], "b": 2})

    assert first == second
    assert first.endswith("\n")
    assert json.loads(first) == {"a": ["£", 1], "b": 2}
    assert namespace["sha256_text"](first) == namespace["sha256_text"](second)


def test_base_snapshot_is_fully_validated() -> None:
    namespace = _script_namespace()
    sources = namespace["load_source_register"](REGISTER)

    manifest, carried, manifest_sha256 = namespace["_load_base_snapshot"](
        BASE_SNAPSHOT,
        sources,
        require_complete=True,
    )

    assert manifest["snapshotId"] == "monday-2026-07-17-r2"
    assert set(carried) == set(sources)
    assert len(manifest_sha256) == 64


def test_successor_snapshot_is_atomic_complete_and_non_overwriting(
    tmp_path: Path,
) -> None:
    namespace = _script_namespace()
    ons_result = json.loads(
        (BASE_SNAPSHOT / "ons-data-api.json").read_text(encoding="utf-8")
    )
    calls: list[dict[str, Any]] = []

    class FrozenResult:
        def as_public_dict(self) -> dict[str, Any]:
            return ons_result

    def fake_acquire_source(*args: Any, **kwargs: Any) -> FrozenResult:
        calls.append(kwargs)
        return FrozenResult()

    namespace["main"].__globals__["acquire_source"] = fake_acquire_source
    output_dir = tmp_path / "snapshots"
    arguments = [
        "--source-register",
        str(REGISTER),
        "--cache-dir",
        str(tmp_path / "external-cache"),
        "--output-dir",
        str(output_dir),
        "--snapshot-id",
        "test-r3",
        "--base-snapshot",
        str(BASE_SNAPSHOT),
        "--source",
        "ons-data-api",
        "--mode",
        "refresh",
        "--page-size",
        "1000",
        "--maximum-pages",
        "1",
        "--require-complete",
    ]

    assert namespace["main"](arguments) == 0

    target = output_dir / "test-r3"
    manifest = json.loads((target / "snapshot.json").read_text(encoding="utf-8"))
    assert manifest["completeForRegisteredAdapters"] is True
    assert {row["sourceId"] for row in manifest["sources"]} == {
        "ons-data-api",
        "ons-explore-local-statistics",
        "nomis-dataset-definitions",
        "ons-open-geography",
    }
    assert manifest["basedOn"]["snapshotId"] == "monday-2026-07-17-r2"
    assert calls == [
        {
            "cache_directory": tmp_path / "external-cache",
            "mode": "refresh",
            "page_size": 1000,
            "maximum_pages": 1,
            "request_interval_seconds": 0.2,
        }
    ]
    for source_id in (
        "ons-explore-local-statistics",
        "nomis-dataset-definitions",
        "ons-open-geography",
    ):
        filename = f"{source_id}.json"
        assert (target / filename).read_bytes() == (BASE_SNAPSHOT / filename).read_bytes()
    assert not list(output_dir.glob(".test-r3.*.tmp"))

    with pytest.raises(SystemExit):
        namespace["main"](arguments)
    assert len(calls) == 1
