from __future__ import annotations

import hashlib
import json
import runpy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "acquire_nomis_codelists.py"
SNAPSHOT = ROOT / "source" / "metadata-enrichment-2026-07-21-r5"


def _namespace() -> dict[str, Any]:
    return runpy.run_path(str(SCRIPT), run_name="nomis_codelist_enrichment_test")


def _record_id(codelist_id: str) -> str:
    parts = codelist_id.split("_")
    return f"NM_{parts[1]}_{parts[2]}"


def _raw_payload(
    codelist_id: str,
    *,
    null_codelist: bool = False,
    unknown_structure_field: bool = False,
) -> dict[str, Any]:
    record_id = _record_id(codelist_id)
    structure: dict[str, Any] = {
        "codelists": None,
        "header": {
            "id": record_id,
            "prepared": "2026-07-21T15:03:31Z",
            "sender": {"id": "NOMIS"},
            "test": "false",
        },
        "xmlns": "http://www.SDMX.org/resources/SDMXML/schemas/v2_0/message",
        "common": "http://www.SDMX.org/resources/SDMXML/schemas/v2_0/common",
        "structure": "http://www.SDMX.org/resources/SDMXML/schemas/v2_0/structure",
        "xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "schemalocation": "http://sdmx.org/docs/2_0/SDMXMessage.xsd",
    }
    if not null_codelist:
        is_time = codelist_id.endswith("_TIME")
        codes: list[dict[str, Any]]
        if is_time:
            codes = [
                {
                    "description": {"value": 2020, "lang": "en"},
                    "value": 2020,
                    "annotations": {
                        "annotation": [
                            {
                                "annotationtitle": "CurrentRevisionStatus",
                                "annotationtext": "Live",
                            },
                            {
                                "annotationtitle": "CurrentRevisionReleased",
                                "annotationtext": "2024-08-13 07:00:0",
                            },
                            {
                                "annotationtitle": "MetadataCount",
                                "annotationtext": 1,
                            },
                        ]
                    },
                },
                {
                    "description": {"value": "2021", "lang": "en"},
                    "value": "2021",
                    "annotations": {
                        "annotation": {
                            "annotationtitle": "CurrentRevisionStatus",
                            "annotationtext": "Scheduled",
                        }
                    },
                },
            ]
        else:
            codes = [
                {
                    "description": {"value": "Annually", "lang": "en"},
                    "value": "A",
                }
            ]
        structure["codelists"] = {
            "codelist": [
                {
                    "agencyid": "NOMIS",
                    "id": codelist_id,
                    "code": codes,
                    "name": {
                        "value": "date" if is_time else "Frequency code list",
                        "lang": "en",
                    },
                    "uri": "",
                }
            ]
        }
    if unknown_structure_field:
        structure["observations"] = []
    return {"structure": structure}


class FakeTransport:
    def __init__(self, response_type: type[Any]) -> None:
        self.response_type = response_type
        self.calls: list[str] = []

    def get(self, url: str, *, timeout: float) -> Any:
        self.calls.append(url)
        codelist_id = url.rsplit("/", maxsplit=1)[-1].split(
            ".def.sdmx.json", maxsplit=1
        )[0]
        return self.response_type(
            payload=_raw_payload(codelist_id),
            final_url=url,
            status=200,
            headers={"content-type": "application/json"},
        )


class NullTransport(FakeTransport):
    def get(self, url: str, *, timeout: float) -> Any:
        self.calls.append(url)
        codelist_id = url.rsplit("/", maxsplit=1)[-1].split(
            ".def.sdmx.json", maxsplit=1
        )[0]
        return self.response_type(
            payload=_raw_payload(codelist_id, null_codelist=True),
            final_url=url,
            status=200,
            headers={"content-type": "application/json"},
        )


class ErrorTransport(FakeTransport):
    def get(self, url: str, *, timeout: float) -> Any:
        self.calls.append(url)
        return self.response_type(
            payload=None,
            final_url=url,
            status=500,
            headers={"retry-after": "0"},
        )


class ScalarErrorTransport(FakeTransport):
    def get(self, url: str, *, timeout: float) -> Any:
        self.calls.append(url)
        return self.response_type(
            payload="upstream SDMX conversion error",
            final_url=url,
            status=200,
            headers={"content-type": "application/json"},
        )


def _fixed_now() -> datetime:
    return datetime(2026, 7, 21, 15, 10, tzinfo=UTC)


def test_exact_r5_cohort_has_unique_freq_and_time_references() -> None:
    namespace = _namespace()
    acquisition, snapshot_id = namespace["_load_exact_base"](SNAPSHOT)
    record_ids, references = namespace["_cohort_references"](
        acquisition["records"]
    )

    assert snapshot_id == "metadata-enrichment-2026-07-21-r5"
    assert len(record_ids) == 1_617
    assert len({item for pair in references.values() for item in pair}) == 3_234
    assert all(pair[0].endswith("_FREQ") for pair in references.values())
    assert all(pair[1].endswith("_TIME") for pair in references.values())


def test_envelope_is_ranked_projected_cached_and_replayable(tmp_path: Path) -> None:
    namespace = _namespace()
    transport = FakeTransport(namespace["JsonResponse"])
    cache = tmp_path / "external-cache"
    envelope = namespace["build_enrichment_envelope"](
        SNAPSHOT,
        cache_directory=cache,
        limit=2,
        mode="prefer-cache",
        request_interval_seconds=0,
        retries=0,
        transport=transport,
        now=_fixed_now,
    )

    base = json.loads(
        (SNAPSHOT / "nomis-dataset-definitions.json").read_text(encoding="utf-8")
    )
    selected_ids = sorted(
        (record["sourceRecordId"] for record in base["records"]),
        key=lambda item: (
            hashlib.sha256(item.encode("utf-8")).hexdigest(),
            item.casefold(),
            item,
        ),
    )[:2]
    expected_urls = [
        "https://www.nomisweb.co.uk/api/v01/codelist/"
        f"CL_{record_id.split('_')[1]}_{record_id.split('_')[2]}_{concept}"
        ".def.sdmx.json"
        for record_id in selected_ids
        for concept in ("FREQ", "TIME")
    ]
    assert transport.calls == expected_urls

    records = {record["sourceRecordId"]: record for record in envelope["records"]}
    first = records[selected_ids[0]]["nomisCodelists"]
    assert first == [
        {
            "concept": "FREQ",
            "codeList": first[0]["codeList"],
            "status": "present",
            "codes": [{"value": "A", "label": "Annually"}],
        },
        {
            "concept": "TIME",
            "codeList": first[1]["codeList"],
            "status": "present",
            "codes": [
                {
                    "value": "2020",
                    "label": "2020",
                    "revisionStatus": "Live",
                },
                {
                    "value": "2021",
                    "label": "2021",
                    "revisionStatus": "Scheduled",
                },
            ],
        },
    ]
    assert "nomisCodelists" not in records[selected_ids[2]] if len(selected_ids) > 2 else True

    cache_files = list((cache / "nomis-codelist-v2").glob("*.json"))
    assert len(cache_files) == 4
    for cache_file in cache_files:
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        assert cached["schema"] == "okf-ons.nomis-codelist-cache.v2"
        assert set(cached["payload"]) == {"codeList", "codes", "status"}
        rendered = json.dumps(cached, sort_keys=True)
        assert '"structure"' not in rendered
        assert '"header"' not in rendered
        assert str(cache) not in rendered

    run = envelope["provenance"]["enrichmentRun"]
    assert run == {
        "schema": "okf-ons.nomis-codelist-enrichment.v1",
        "cohortCount": 1_617,
        "requestedLimit": 2,
        "selectedCount": 2,
        "unselectedCount": 1_615,
        "coverageComplete": False,
        "selectionOrder": "sha256(sourceRecordId)-ascending",
        "selectedRecordSetSha256": namespace["sha256_json"](selected_ids),
        "selectedCodelistCount": 4,
        "notEvidencedCodelistCount": 0,
        "selectedCodelistReferenceSetSha256": run[
            "selectedCodelistReferenceSetSha256"
        ],
        "concepts": ["FREQ", "TIME"],
        "endpointTemplate": (
            "https://www.nomisweb.co.uk/api/v01/codelist/"
            "{codelistId}.def.sdmx.json"
        ),
    }
    pages = envelope["provenance"]["pages"][-4:]
    assert [page["requestUrl"] for page in pages] == expected_urls
    assert all(page["attemptCount"] == 1 for page in pages)
    assert all(page["acquisitionStatus"] == "present" for page in pages)
    assert all(page["failureReason"] is None for page in pages)
    assert all(page["normalisedRecordCount"] == 1 for page in pages)

    replay_transport = FakeTransport(namespace["JsonResponse"])
    replay = namespace["build_enrichment_envelope"](
        SNAPSHOT,
        cache_directory=cache,
        limit=2,
        mode="frozen",
        request_interval_seconds=0,
        retries=0,
        transport=replay_transport,
        now=_fixed_now,
    )
    assert replay_transport.calls == []
    assert replay["provenance"]["recordSetSha256"] == envelope["provenance"][
        "recordSetSha256"
    ]
    assert all(page["cacheHit"] for page in replay["provenance"]["pages"][-4:])


@pytest.mark.parametrize(
    (
        "record_id",
        "concept",
        "codelist_id",
        "transport_class",
        "http_status",
        "upstream_count",
        "expected_sleeps",
    ),
    [
        (
            "NM_1234_1",
            "TIME",
            "CL_1234_1_TIME",
            NullTransport,
            200,
            1,
            [1, 2],
        ),
        (
            "NM_673_1",
            "FREQ",
            "CL_673_1_FREQ",
            NullTransport,
            200,
            1,
            [1, 2],
        ),
        ("NM_17_1", "TIME", "CL_17_1_TIME", ErrorTransport, 500, 0, [0, 0]),
        (
            "NM_17_1",
            "TIME",
            "CL_17_1_TIME",
            ScalarErrorTransport,
            200,
            1,
            [1, 2],
        ),
    ],
)
def test_audited_upstream_failures_are_retried_and_explicitly_represented(
    tmp_path: Path,
    record_id: str,
    concept: str,
    codelist_id: str,
    transport_class: type[FakeTransport],
    http_status: int,
    upstream_count: int,
    expected_sleeps: list[float],
) -> None:
    namespace = _namespace()
    transport = transport_class(namespace["JsonResponse"])
    sleeps: list[float] = []
    payload, receipt = namespace["_fetch_codelist"](
        record_id,
        concept,
        codelist_id,
        cache_directory=tmp_path / "external-cache",
        mode="refresh",
        transport=transport,
        timeout_seconds=5,
        retries=2,
        now=_fixed_now,
        sleep=sleeps.append,
        before_live_request=lambda: None,
    )

    assert len(transport.calls) == 3
    assert sleeps == expected_sleeps
    assert payload == {
        "codeList": codelist_id,
        "codes": [],
        "status": "not-evidenced",
        "reason": "upstream-codelist-unavailable",
    }
    assert receipt["attemptCount"] == 3
    assert receipt["acquisitionStatus"] == "not-evidenced"
    assert receipt["httpStatus"] == http_status
    assert receipt["failureReason"] == "upstream-codelist-unavailable"
    assert receipt["upstreamRecordCount"] == upstream_count
    assert receipt["normalisedRecordCount"] == 1
    assert receipt["contentSha256"] == namespace["sha256_json"](payload)


def test_unreviewed_failure_or_payload_shape_fails_closed(tmp_path: Path) -> None:
    namespace = _namespace()
    with pytest.raises(namespace["NomisCodelistError"], match="malformed"):
        namespace["_fetch_codelist"](
            "NM_673_1",
            "TIME",
            "CL_673_1_TIME",
            cache_directory=tmp_path / "external-cache",
            mode="refresh",
            transport=ScalarErrorTransport(namespace["JsonResponse"]),
            timeout_seconds=5,
            retries=0,
            now=_fixed_now,
            sleep=lambda _: None,
            before_live_request=lambda: None,
        )

    with pytest.raises(namespace["NomisCodelistError"], match="unreviewed field"):
        namespace["_validate_raw_payload"](
            _raw_payload(
                "CL_673_1_TIME", unknown_structure_field=True
            ),
            record_id="NM_673_1",
            concept="TIME",
            codelist_id="CL_673_1_TIME",
        )

    assert namespace["_validate_projected_payload"](
        {
            "codeList": "CL_673_1_TIME",
            "codes": [],
            "status": "not-evidenced",
            "reason": "upstream-codelist-unavailable",
        },
        "CL_673_1_TIME",
    )["status"] == "not-evidenced"

    with pytest.raises(namespace["NomisCodelistError"], match="unavailable"):
        namespace["_validate_projected_payload"](
            {
                "codeList": "CL_673_1_TIME",
                "codes": [],
                "status": "not-evidenced",
                "reason": "unsupported-reason",
            },
            "CL_673_1_TIME",
        )

    with pytest.raises(namespace["NomisCodelistError"], match="HTTP 500"):
        namespace["_fetch_codelist"](
            "NM_673_1",
            "TIME",
            "CL_673_1_TIME",
            cache_directory=tmp_path / "other-cache",
            mode="refresh",
            transport=ErrorTransport(namespace["JsonResponse"]),
            timeout_seconds=5,
            retries=0,
            now=_fixed_now,
            sleep=lambda _: None,
            before_live_request=lambda: None,
        )


def test_url_cache_boundary_and_live_rate_guard_are_strict(tmp_path: Path) -> None:
    namespace = _namespace()
    request_url = namespace["_codelist_url"]("CL_673_1_TIME")
    cache_path = namespace["_cache_path"](
        tmp_path / "external-cache", request_url
    )
    assert cache_path.parent.name == "nomis-codelist-v2"
    assert cache_path.parent != tmp_path / "external-cache" / "nomis-codelist"
    with pytest.raises(namespace["NomisCodelistError"], match="metadata-only"):
        namespace["_validate_request_url"](
            "https://www.nomisweb.co.uk/api/v01/codelist/"
            "CL_673_1_TIME.def.sdmx.json?token=secret",
            expected_codelist_id="CL_673_1_TIME",
        )
    with pytest.raises(namespace["NomisCodelistError"], match="outside"):
        namespace["build_enrichment_envelope"](
            SNAPSHOT,
            cache_directory=ROOT / ".cache-test",
            limit=1,
            mode="frozen",
        )
    with pytest.raises(namespace["NomisCodelistError"], match="at least 0.2"):
        namespace["build_enrichment_envelope"](
            SNAPSHOT,
            cache_directory=tmp_path / "external-cache",
            limit=1,
            mode="refresh",
            request_interval_seconds=0,
        )
