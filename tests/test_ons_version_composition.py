from __future__ import annotations

import copy
import hashlib
import json
import runpy
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "acquire_snapshot.py"
ACQUISITION_SCRIPT = ROOT / "scripts" / "acquire_ons_version_metadata.py"
REGISTER = ROOT / "source" / "source-register.json"
R4_SNAPSHOT = ROOT / "source" / "metadata-enrichment-2026-07-21-r4"
SOURCE_ID = "ons-data-api"


def _namespace() -> dict[str, Any]:
    return runpy.run_path(str(SCRIPT), run_name="ons_version_composition_test")


def _version_dimensions() -> list[dict[str, Any]]:
    return [
        {
            "id": "geography",
            "name": "geography",
            "label": "Geography",
            "isAreaType": True,
            "qualityStatementUrl": "https://www.ons.gov.uk/methodology",
            "qualityStatementText": "Quality information supplied with the dimension.",
        },
        {
            "id": "sex",
            "name": "sex",
            "label": "Sex",
            "isAreaType": False,
        },
    ]


def _latest_version_pair(record: dict[str, Any]) -> dict[str, str]:
    return {
        "sourceRecordId": record["sourceRecordId"],
        "latestVersionHref": record["links"]["latest_version"]["href"],
    }


def _replacement(
    namespace: dict[str, Any],
    *,
    limit: int = 2,
    mode: str = "prefer-cache",
) -> tuple[dict[str, Any], dict[str, Any]]:
    base = json.loads((R4_SNAPSHOT / f"{SOURCE_ID}.json").read_text(encoding="utf-8"))
    replacement = copy.deepcopy(base)
    cohort_pairs = [_latest_version_pair(record) for record in base["records"]]
    ranked_pairs = sorted(
        cohort_pairs,
        key=lambda row: (
            hashlib.sha256(row["sourceRecordId"].encode("utf-8")).hexdigest(),
            row["sourceRecordId"].casefold(),
            row["sourceRecordId"],
        ),
    )
    selected_pairs = ranked_pairs[: min(limit, len(ranked_pairs))]
    selected_ids = {row["sourceRecordId"] for row in selected_pairs}
    records = {
        record["sourceRecordId"]: record for record in replacement["records"]
    }
    pages = copy.deepcopy(base["provenance"]["pages"])
    for pair in selected_pairs:
        dimensions = _version_dimensions()
        records[pair["sourceRecordId"]]["versionDimensions"] = dimensions
        pages.append(
            {
                "requestUrl": pair["latestVersionHref"],
                "responseUrl": pair["latestVersionHref"],
                "retrievedAt": "2026-07-21T14:00:00Z",
                "contentSha256": namespace["sha256_json"](
                    {"dimensions": dimensions}
                ),
                "responseHeaders": {"content-type": "application/json"},
                "cacheHit": mode != "refresh",
                "upstreamRecordCount": 1,
                "normalisedRecordCount": 1,
            }
        )

    provenance = replacement["provenance"]
    provenance["assurance"] = {
        "cacheLocationPublished": False,
        "credentialsRequired": False,
        "dimensionMetadataFetched": True,
        "dimensionOptionsFetched": False,
        "downloadsFetched": False,
        "metadataOnly": True,
        "observationsFetched": False,
        "rawResponsesPublished": False,
    }
    provenance["pageCount"] = len(pages)
    provenance["pages"] = pages
    provenance["recordSetSha256"] = namespace["sha256_json"](
        replacement["records"]
    )
    provenance["retrievalMode"] = f"version-metadata-enrichment:{mode}"
    provenance["snapshotSetSha256"] = namespace["sha256_json"](
        [
            {
                "requestUrl": page["requestUrl"],
                "contentSha256": page["contentSha256"],
            }
            for page in pages
        ]
    )
    provenance["stopReason"] = (
        "sourceExhausted" if len(selected_pairs) == len(cohort_pairs) else "recordLimit"
    )
    provenance["replacement"] = {
        "schema": "okf-ons.bounded-source-replacement.v1",
        "baseSnapshotId": "metadata-enrichment-2026-07-21-r4",
        "baseRecordSetSha256": base["provenance"]["recordSetSha256"],
        "baseSnapshotSetSha256": base["provenance"]["snapshotSetSha256"],
        "allowedRecordFields": ["versionDimensions"],
    }
    provenance["versionMetadataRun"] = {
        "schema": "okf-ons.ons-version-metadata-enrichment.v1",
        "cohortCount": len(cohort_pairs),
        "requestedLimit": limit,
        "selectedCount": len(selected_pairs),
        "unselectedCount": len(cohort_pairs) - len(selected_pairs),
        "coverageComplete": len(selected_pairs) == len(cohort_pairs),
        "selectionOrder": "sha256(sourceRecordId)-ascending",
        "cohortRecordSetSha256": namespace["sha256_json"](cohort_pairs),
        "selectedRecordSetSha256": namespace["sha256_json"](selected_pairs),
    }
    assert {
        record["sourceRecordId"]
        for record in replacement["records"]
        if "versionDimensions" in record
    } == selected_ids
    return replacement, base


def _validate(
    namespace: dict[str, Any], replacement: dict[str, Any], base: dict[str, Any]
) -> dict[str, int]:
    return namespace["_validate_bounded_replacement"](
        replacement,
        base,
        SOURCE_ID,
        base_snapshot_id="metadata-enrichment-2026-07-21-r4",
    )


def test_ons_version_replacement_is_a_ranked_metadata_only_prefix() -> None:
    namespace = _namespace()
    replacement, base = _replacement(namespace)

    assert _validate(namespace, replacement, base) == {
        "changedRecords": 2,
        "changedFields": 2,
    }
    run = replacement["provenance"]["versionMetadataRun"]
    assert run["cohortCount"] == 337
    assert run["selectedCount"] == 2
    assert run["coverageComplete"] is False
    projected = [
        record["versionDimensions"]
        for record in replacement["records"]
        if "versionDimensions" in record
    ]
    assert len(projected) == 2
    assert all(
        set(dimension)
        <= {
            "id",
            "name",
            "label",
            "isAreaType",
            "qualityStatementUrl",
            "qualityStatementText",
        }
        for dimensions in projected
        for dimension in dimensions
    )


def test_real_acquirer_prefix_passes_composer_without_network(tmp_path: Path) -> None:
    acquisition = runpy.run_path(
        str(ACQUISITION_SCRIPT), run_name="ons_version_composition_integration"
    )

    class FakeTransport:
        def get(self, url: str, *, timeout: float) -> Any:
            record_id, edition, version = acquisition["_version_identity"](url)
            return acquisition["JsonResponse"](
                payload={
                    "id": record_id,
                    "edition": edition,
                    "version": version,
                    "dimensions": [
                        {
                            "id": "geography",
                            "name": "Geography",
                            "label": "Geography",
                            "is_area_type": True,
                        }
                    ],
                    "links": {
                        "dataset": {"id": record_id},
                        "dimensions": {"href": f"{url}/dimensions"},
                        "edition": {"id": edition},
                        "self": {"href": url},
                    },
                },
                final_url=url,
                headers={"content-type": "application/json"},
            )

    replacement = acquisition["build_enrichment_envelope"](
        R4_SNAPSHOT,
        cache_directory=tmp_path / "external-cache",
        limit=2,
        request_interval_seconds=0,
        retries=0,
        transport=FakeTransport(),
        now=lambda: datetime(2026, 7, 21, 14, 0, tzinfo=UTC),
    )
    base = json.loads(
        (R4_SNAPSHOT / f"{SOURCE_ID}.json").read_text(encoding="utf-8")
    )
    composer = _namespace()

    assert _validate(composer, replacement, base) == {
        "changedRecords": 2,
        "changedFields": 2,
    }


Mutation = Callable[[dict[str, Any], dict[str, Any]], None]


def _change_title(replacement: dict[str, Any], _: dict[str, Any]) -> None:
    replacement["records"][0]["title"] = "tampered"


def _reorder_records(replacement: dict[str, Any], _: dict[str, Any]) -> None:
    replacement["records"][0], replacement["records"][1] = (
        replacement["records"][1],
        replacement["records"][0],
    )


def _escape_receipt(replacement: dict[str, Any], _: dict[str, Any]) -> None:
    page = replacement["provenance"]["pages"][1]
    page["requestUrl"] += "?access_token=secret"
    page["responseUrl"] = page["requestUrl"]


def _redirect_response(replacement: dict[str, Any], _: dict[str, Any]) -> None:
    replacement["provenance"]["pages"][1]["responseUrl"] = (
        "https://example.org/version"
    )


def _add_dimension_values(replacement: dict[str, Any], _: dict[str, Any]) -> None:
    selected = next(
        record for record in replacement["records"] if "versionDimensions" in record
    )
    selected["versionDimensions"][0]["values"] = ["forbidden"]


def _remove_dimension_identity(replacement: dict[str, Any], _: dict[str, Any]) -> None:
    selected = next(
        record for record in replacement["records"] if "versionDimensions" in record
    )
    del selected["versionDimensions"][0]["isAreaType"]


def _unsafe_quality_url(replacement: dict[str, Any], _: dict[str, Any]) -> None:
    selected = next(
        record for record in replacement["records"] if "versionDimensions" in record
    )
    selected["versionDimensions"][0]["qualityStatementUrl"] = (
        "https://example.org/quality?token=not-public"
    )


def _stale_response_hash(replacement: dict[str, Any], _: dict[str, Any]) -> None:
    replacement["provenance"]["pages"][1]["contentSha256"] = "0" * 64


def _wrong_selection_hash(replacement: dict[str, Any], _: dict[str, Any]) -> None:
    replacement["provenance"]["versionMetadataRun"][
        "selectedRecordSetSha256"
    ] = "0" * 64


def _add_run_field(replacement: dict[str, Any], _: dict[str, Any]) -> None:
    replacement["provenance"]["versionMetadataRun"]["rawCache"] = "/tmp/cache"


def _weaken_assurance(replacement: dict[str, Any], _: dict[str, Any]) -> None:
    replacement["provenance"]["assurance"]["dimensionOptionsFetched"] = True


def _change_unselected_record(replacement: dict[str, Any], _: dict[str, Any]) -> None:
    selected_ids = {
        record["sourceRecordId"]
        for record in replacement["records"]
        if "versionDimensions" in record
    }
    record = next(
        item
        for item in replacement["records"]
        if item["sourceRecordId"] not in selected_ids
    )
    record["versionDimensions"] = _version_dimensions()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (_change_title, "changed protected fields"),
        (_reorder_records, "reordered the ONS source-record cohort"),
        (_escape_receipt, "invalid response identity"),
        (_redirect_response, "invalid response identity"),
        (_add_dimension_values, "unreviewed or missing fields"),
        (_remove_dimension_identity, "unreviewed or missing fields"),
        (_unsafe_quality_url, "public URL is unsafe"),
        (_stale_response_hash, "response hash is invalid"),
        (_wrong_selection_hash, "enrichment denominator is invalid"),
        (_add_run_field, "ONS version run has unreviewed field"),
        (_weaken_assurance, "metadata-only assurance"),
        (_change_unselected_record, "outside its ONS selection"),
    ],
)
def test_ons_version_composer_rejects_untrusted_changes(
    mutation: Mutation, message: str
) -> None:
    namespace = _namespace()
    replacement, base = _replacement(namespace)
    mutation(replacement, base)

    with pytest.raises(namespace["SnapshotCompositionError"], match=message):
        _validate(namespace, replacement, base)


def test_real_r4_composition_carries_other_sources_byte_identically(
    tmp_path: Path,
) -> None:
    namespace = _namespace()
    replacement, _ = _replacement(namespace)
    replacement_path = tmp_path / "ons-version-prefix.json"
    replacement_path.write_text(json.dumps(replacement), encoding="utf-8")
    output = tmp_path / "snapshots"

    assert (
        namespace["main"](
            [
                "--source-register",
                str(REGISTER),
                "--cache-dir",
                str(tmp_path / "external-cache"),
                "--output-dir",
                str(output),
                "--snapshot-id",
                "test-r5",
                "--base-snapshot",
                str(R4_SNAPSHOT),
                "--replacement-acquisition",
                str(replacement_path),
                "--require-complete",
            ]
        )
        == 0
    )

    composed = output / "test-r5"
    manifest = json.loads((composed / "snapshot.json").read_text(encoding="utf-8"))
    assert manifest["basedOn"]["snapshotId"] == R4_SNAPSHOT.name
    assert manifest["completeForRegisteredAdapters"] is True
    for source_id in (
        "nomis-dataset-definitions",
        "ons-explore-local-statistics",
        "ons-open-geography",
    ):
        filename = f"{source_id}.json"
        assert (composed / filename).read_bytes() == (R4_SNAPSHOT / filename).read_bytes()
    ons = json.loads((composed / f"{SOURCE_ID}.json").read_text(encoding="utf-8"))
    assert ons["provenance"]["versionMetadataRun"]["selectedCount"] == 2
