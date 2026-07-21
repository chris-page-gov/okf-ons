from __future__ import annotations

import copy
import hashlib
import json
import runpy
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "acquire_snapshot.py"
ACQUISITION_SCRIPT = ROOT / "scripts" / "acquire_nomis_codelists.py"
REGISTER = ROOT / "source" / "source-register.json"
R5_SNAPSHOT = ROOT / "source" / "metadata-enrichment-2026-07-21-r5"
SOURCE_ID = "nomis-dataset-definitions"


def _namespace() -> dict[str, Any]:
    return runpy.run_path(str(SCRIPT), run_name="nomis_codelist_composition_test")


def _replacement(
    namespace: dict[str, Any],
    *,
    limit: int = 2,
    mode: str = "prefer-cache",
    null_projection: Callable[[str, str], bool] | None = None,
    persistent_http_error: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    base = json.loads((R5_SNAPSHOT / f"{SOURCE_ID}.json").read_text(encoding="utf-8"))
    replacement = copy.deepcopy(base)
    cohort = [
        namespace["_nomis_codelist_cohort_item"](record, SOURCE_ID)
        for record in base["records"]
    ]
    ranked = sorted(
        cohort,
        key=lambda row: (
            hashlib.sha256(row["sourceRecordId"].encode("utf-8")).hexdigest(),
            row["sourceRecordId"].casefold(),
            row["sourceRecordId"],
        ),
    )
    selected = ranked[: min(limit, len(ranked))]
    selected_ids = [row["sourceRecordId"] for row in selected]
    records = {record["sourceRecordId"]: record for record in replacement["records"]}
    pages = copy.deepcopy(base["provenance"]["pages"])
    references: list[dict[str, str]] = []
    not_evidenced_count = 0
    for row in selected:
        projected = [
            {
                "concept": "FREQ",
                "codeList": row["codelists"][0]["codeList"],
                "status": "present",
                "codes": [{"value": "A", "label": "Annually"}],
            },
            {
                "concept": "TIME",
                "codeList": row["codelists"][1]["codeList"],
                "status": "present",
                "codes": [
                    {
                        "value": "2011",
                        "label": "2011",
                        "revisionStatus": "Live",
                    }
                ],
            },
        ]
        records[row["sourceRecordId"]]["nomisCodelists"] = projected
        for item, expected in zip(projected, row["codelists"], strict=True):
            is_persistent_error = (
                persistent_http_error
                and row["sourceRecordId"] == "NM_17_1"
                and item["concept"] == "TIME"
            )
            is_null_projection = bool(
                null_projection
                and null_projection(row["sourceRecordId"], item["concept"])
            )
            if is_persistent_error or is_null_projection:
                item["status"] = "not-evidenced"
                item["codes"] = []
                item["reason"] = "upstream-codelist-unavailable"
                not_evidenced_count += 1
            references.append(
                {
                    "sourceRecordId": row["sourceRecordId"],
                    "concept": item["concept"],
                    "codeList": item["codeList"],
                }
            )
            pages.append(
                {
                    "requestUrl": expected["requestUrl"],
                    "responseUrl": expected["requestUrl"],
                    "retrievedAt": "2026-07-21T15:30:00Z",
                    "contentSha256": namespace["sha256_json"](
                        {
                            "codeList": item["codeList"],
                            "status": item["status"],
                            "codes": item["codes"],
                            **(
                                {"reason": item["reason"]}
                                if item["status"] == "not-evidenced"
                                else {}
                            ),
                        }
                    ),
                    "responseHeaders": {"content-type": "application/json"},
                    "cacheHit": mode != "refresh",
                    "upstreamRecordCount": 0 if is_persistent_error else 1,
                    "normalisedRecordCount": 1,
                    "attemptCount": 3 if item["status"] == "not-evidenced" else 1,
                    "acquisitionStatus": item["status"],
                    "httpStatus": 500 if is_persistent_error else 200,
                    "failureReason": (
                        "upstream-codelist-unavailable"
                        if item["status"] == "not-evidenced"
                        else None
                    ),
                }
            )

    provenance = replacement["provenance"]
    provenance["assurance"] = {
        "cacheLocationPublished": False,
        "codelistsFetched": True,
        "credentialsRequired": False,
        "metadataOnly": True,
        "observationsFetched": False,
        "projectedCacheOnly": True,
        "rawResponsesCached": False,
        "rawResponsesPublished": False,
    }
    provenance["enrichmentRun"] = {
        "schema": "okf-ons.nomis-codelist-enrichment.v1",
        "cohortCount": len(cohort),
        "requestedLimit": limit,
        "selectedCount": len(selected),
        "unselectedCount": len(cohort) - len(selected),
        "coverageComplete": len(selected) == len(cohort),
        "selectionOrder": "sha256(sourceRecordId)-ascending",
        "selectedRecordSetSha256": namespace["sha256_json"](selected_ids),
        "selectedCodelistCount": len(references),
        "notEvidencedCodelistCount": not_evidenced_count,
        "selectedCodelistReferenceSetSha256": namespace["sha256_json"](references),
        "concepts": ["FREQ", "TIME"],
        "endpointTemplate": (
            "https://www.nomisweb.co.uk/api/v01/codelist/"
            "{codelistId}.def.sdmx.json"
        ),
    }
    provenance["replacement"] = {
        "schema": "okf-ons.bounded-source-replacement.v1",
        "baseSnapshotId": R5_SNAPSHOT.name,
        "baseRecordSetSha256": base["provenance"]["recordSetSha256"],
        "baseSnapshotSetSha256": base["provenance"]["snapshotSetSha256"],
        "allowedRecordFields": ["nomisCodelists"],
    }
    provenance["pageCount"] = len(pages)
    provenance["pages"] = pages
    provenance["recordSetSha256"] = namespace["sha256_json"](
        replacement["records"]
    )
    provenance["retrievalMode"] = f"codelist-enrichment:{mode}"
    provenance["snapshotSetSha256"] = namespace["sha256_json"](
        [
            {"requestUrl": page["requestUrl"], "contentSha256": page["contentSha256"]}
            for page in pages
        ]
    )
    provenance["stopReason"] = (
        "sourceExhausted" if len(selected) == len(cohort) else "recordLimit"
    )
    return replacement, base


def _validate(
    namespace: dict[str, Any], replacement: dict[str, Any], base: dict[str, Any]
) -> dict[str, int]:
    return namespace["_validate_bounded_replacement"](
        replacement,
        base,
        SOURCE_ID,
        base_snapshot_id=R5_SNAPSHOT.name,
    )


def test_nomis_codelist_replacement_is_exact_r5_ranked_metadata_prefix() -> None:
    namespace = _namespace()
    replacement, base = _replacement(namespace)

    assert _validate(namespace, replacement, base) == {
        "changedRecords": 2,
        "changedFields": 2,
    }
    run = replacement["provenance"]["enrichmentRun"]
    assert run["cohortCount"] == 1_617
    assert run["selectedCount"] == 2
    assert run["selectedCodelistCount"] == 4
    assert run["coverageComplete"] is False


def test_real_acquirer_prefix_passes_composer_without_network(tmp_path: Path) -> None:
    acquisition = runpy.run_path(
        str(ACQUISITION_SCRIPT), run_name="nomis_codelist_composition_integration"
    )

    class FakeTransport:
        def get(self, url: str, *, timeout: float) -> Any:
            del timeout
            codelist_id = url.rsplit("/", 1)[-1].removesuffix(".def.sdmx.json")
            _, numeric_id, version, concept = codelist_id.split("_")
            record_id = f"NM_{numeric_id}_{version}"
            return acquisition["JsonResponse"](
                payload={
                    "structure": {
                        "codelists": {
                            "codelist": [
                                {
                                    "agencyid": "NOMIS",
                                    "id": codelist_id,
                                    "code": [
                                        {
                                            "description": {
                                                "value": (
                                                    "Annually"
                                                    if concept == "FREQ"
                                                    else "2011"
                                                ),
                                                "lang": "en",
                                            },
                                            "value": "A" if concept == "FREQ" else "2011",
                                        }
                                    ],
                                    "name": {"value": concept, "lang": "en"},
                                    "uri": "",
                                }
                            ]
                        },
                        "header": {
                            "id": record_id,
                            "prepared": "2026-07-21T15:30:00Z",
                            "sender": {"id": "NOMIS"},
                            "test": "false",
                        },
                        "common": "common",
                        "schemalocation": "schema",
                        "structure": "structure",
                        "xmlns": "xmlns",
                        "xsi": "xsi",
                    }
                },
                final_url=url,
                status=200,
                headers={"content-type": "application/json"},
            )

    replacement = acquisition["build_enrichment_envelope"](
        R5_SNAPSHOT,
        cache_directory=tmp_path / "external-cache",
        limit=2,
        request_interval_seconds=0,
        retries=0,
        transport=FakeTransport(),
    )
    base = json.loads((R5_SNAPSHOT / f"{SOURCE_ID}.json").read_text(encoding="utf-8"))
    composer = _namespace()

    assert _validate(composer, replacement, base) == {
        "changedRecords": 2,
        "changedFields": 2,
    }


def test_http_200_null_freq_and_time_projections_pass_as_not_evidenced() -> None:
    namespace = _namespace()
    replacement, base = _replacement(
        namespace,
        null_projection=lambda _record_id, _concept: True,
    )

    assert _validate(namespace, replacement, base) == {
        "changedRecords": 2,
        "changedFields": 2,
    }
    run = replacement["provenance"]["enrichmentRun"]
    assert run["notEvidencedCodelistCount"] == 4


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("upstreamRecordCount", 0, "not-evidenced state is invalid"),
        ("normalisedRecordCount", 0, "counts are invalid"),
        ("httpStatus", 201, "not-evidenced state is invalid"),
        ("acquisitionStatus", "present", "counts are invalid"),
        ("failureReason", None, "not-evidenced state is invalid"),
    ],
)
def test_http_200_null_projection_requires_matching_receipt_evidence(
    field: str, value: Any, message: str
) -> None:
    namespace = _namespace()
    replacement, base = _replacement(
        namespace,
        null_projection=lambda _record_id, _concept: True,
    )
    first_enrichment_page = len(base["provenance"]["pages"])
    replacement["provenance"]["pages"][first_enrichment_page][field] = value

    with pytest.raises(namespace["SnapshotCompositionError"], match=message):
        _validate(namespace, replacement, base)


def test_full_cohort_measures_not_evidenced_projections() -> None:
    namespace = _namespace()
    replacement, base = _replacement(
        namespace,
        limit=1_617,
        null_projection=lambda record_id, concept: (
            concept == "FREQ"
            and int(record_id.removeprefix("NM_").split("_", 1)[0]) % 257 == 0
        ),
        persistent_http_error=True,
    )

    assert _validate(namespace, replacement, base) == {
        "changedRecords": 1_617,
        "changedFields": 1_617,
    }
    run = replacement["provenance"]["enrichmentRun"]
    assert run["coverageComplete"] is True
    assert run["selectedCodelistCount"] == 3_234
    measured = sum(
        item["status"] == "not-evidenced"
        for record in replacement["records"]
        for item in record.get("nomisCodelists", [])
    )
    assert measured > 0
    assert run["notEvidencedCodelistCount"] == measured


Mutation = Callable[[dict[str, Any], dict[str, Any]], None]


def _protected_change(replacement: dict[str, Any], _: dict[str, Any]) -> None:
    replacement["records"][0]["title"] = "tampered"


def _wrong_codelist(replacement: dict[str, Any], _: dict[str, Any]) -> None:
    record = next(row for row in replacement["records"] if row.get("nomisCodelists"))
    record["nomisCodelists"][0]["codeList"] = "CL_1_1_FREQ"


def _observation_like_code(replacement: dict[str, Any], _: dict[str, Any]) -> None:
    record = next(row for row in replacement["records"] if row.get("nomisCodelists"))
    record["nomisCodelists"][0]["codes"][0]["observation"] = 42


def _status_on_frequency(replacement: dict[str, Any], _: dict[str, Any]) -> None:
    record = next(row for row in replacement["records"] if row.get("nomisCodelists"))
    item = record["nomisCodelists"][0]
    item["status"] = "not-evidenced"
    item["codes"] = []
    item["reason"] = "upstream-codelist-unavailable"


def _escape_endpoint(replacement: dict[str, Any], base: dict[str, Any]) -> None:
    page = replacement["provenance"]["pages"][len(base["provenance"]["pages"])]
    page["requestUrl"] += "?uid=secret"
    page["responseUrl"] = page["requestUrl"]


def _stale_projection_hash(replacement: dict[str, Any], base: dict[str, Any]) -> None:
    replacement["provenance"]["pages"][len(base["provenance"]["pages"])][
        "contentSha256"
    ] = "0" * 64


def _wrong_reference_hash(replacement: dict[str, Any], _: dict[str, Any]) -> None:
    replacement["provenance"]["enrichmentRun"][
        "selectedCodelistReferenceSetSha256"
    ] = "0" * 64


def _weaken_assurance(replacement: dict[str, Any], _: dict[str, Any]) -> None:
    replacement["provenance"]["assurance"]["rawResponsesCached"] = True


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (_protected_change, "changed protected fields"),
        (_wrong_codelist, "codelist identity is invalid"),
        (_observation_like_code, "unreviewed or missing fields"),
        (_status_on_frequency, "counts are invalid"),
        (_escape_endpoint, "invalid response identity"),
        (_stale_projection_hash, "projected response hash is invalid"),
        (_wrong_reference_hash, "run denominator is invalid"),
        (_weaken_assurance, "projected metadata-only assurance"),
    ],
)
def test_nomis_codelist_composer_rejects_untrusted_changes(
    mutation: Mutation, message: str
) -> None:
    namespace = _namespace()
    replacement, base = _replacement(namespace)
    mutation(replacement, base)

    with pytest.raises(namespace["SnapshotCompositionError"], match=message):
        _validate(namespace, replacement, base)


def test_r5_composition_carries_other_sources_byte_identically(tmp_path: Path) -> None:
    namespace = _namespace()
    replacement, _ = _replacement(namespace)
    replacement_path = tmp_path / "nomis-codelist-prefix.json"
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
                "test-r6",
                "--base-snapshot",
                str(R5_SNAPSHOT),
                "--replacement-acquisition",
                str(replacement_path),
                "--require-complete",
            ]
        )
        == 0
    )

    composed = output / "test-r6"
    manifest = json.loads((composed / "snapshot.json").read_text(encoding="utf-8"))
    assert manifest["basedOn"]["snapshotId"] == R5_SNAPSHOT.name
    assert manifest["completeForRegisteredAdapters"] is True
    for source_id in (
        "ons-data-api",
        "ons-explore-local-statistics",
        "ons-open-geography",
    ):
        filename = f"{source_id}.json"
        assert (composed / filename).read_bytes() == (R5_SNAPSHOT / filename).read_bytes()
