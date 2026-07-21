from __future__ import annotations

import hashlib
import json
import runpy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "acquire_ons_version_metadata.py"
R4 = ROOT / "source" / "metadata-enrichment-2026-07-21-r4"


def _namespace() -> dict[str, Any]:
    return runpy.run_path(str(SCRIPT), run_name="ons_version_metadata_test")


def _source_declaration() -> dict[str, Any]:
    return {
        "acquisitionMethod": "http-json",
        "adapter": "ons-data-api",
        "crossReferences": ["links.latest_version"],
        "endpoint": "https://api.beta.ons.gov.uk/v1/datasets",
        "id": "ons-data-api",
        "identityFields": ["id"],
        "publisher": {
            "name": "Office for National Statistics",
            "url": "https://www.ons.gov.uk/",
        },
        "responseFormat": "ONS Data API JSON",
        "scope": {
            "excludes": ["Observations", "Dimension option values"],
            "includes": ["Dataset identities and official links"],
        },
        "standards": ["HTTPS JSON API"],
        "title": "ONS Data API dataset catalogue",
    }


def _write_base_snapshot(directory: Path, namespace: dict[str, Any]) -> Path:
    records = []
    for record_id, edition, version in (
        ("dataset-c", "time-series", 3),
        ("dataset-a", "2021", 1),
        ("dataset-b", "PWT24", 2),
    ):
        records.append(
            {
                "sourceId": "ons-data-api",
                "sourceRecordId": record_id,
                "recordKind": "dataset",
                "title": record_id,
                "links": {
                    "self": {
                        "href": f"https://api.beta.ons.gov.uk/v1/datasets/{record_id}"
                    },
                    "latest_version": {
                        "href": (
                            "https://api.beta.ons.gov.uk/v1/datasets/"
                            f"{record_id}/editions/{edition}/versions/{version}"
                        ),
                        "id": str(version),
                    },
                },
            }
        )
    page_receipts = [
        {
            "requestUrl": "https://api.beta.ons.gov.uk/v1/datasets?limit=1000&offset=0",
            "responseUrl": "https://api.beta.ons.gov.uk/v1/datasets?limit=1000&offset=0",
            "retrievedAt": "2026-07-21T11:33:37Z",
            "contentSha256": "b" * 64,
            "responseHeaders": {"content-type": "application/json"},
            "cacheHit": True,
            "upstreamRecordCount": 3,
            "normalisedRecordCount": 3,
        }
    ]
    record_set_sha256 = namespace["sha256_json"](records)
    snapshot_set_sha256 = namespace["sha256_json"](
        [
            {
                "requestUrl": page_receipts[0]["requestUrl"],
                "contentSha256": page_receipts[0]["contentSha256"],
            }
        ]
    )
    acquisition = {
        "schemaVersion": "okf-ons.source-acquisition.v1",
        "records": records,
        "provenance": {
            "source": _source_declaration(),
            "recordCount": 3,
            "reportedTotal": 3,
            "complete": True,
            "normalisationDroppedCount": 0,
            "normalisedRecordsSeen": 3,
            "pageCount": 1,
            "recordSetSha256": record_set_sha256,
            "snapshotSetSha256": snapshot_set_sha256,
            "pages": page_receipts,
            "coverageComplete": True,
            "retrievalMode": "refresh",
            "stopReason": "sourceExhausted",
            "unrepresentedCount": 0,
            "upstreamRecordsSeen": 3,
            "assurance": {
                "cacheLocationPublished": False,
                "credentialsRequired": False,
                "metadataOnly": True,
                "observationsFetched": False,
            },
        },
    }
    directory.mkdir()
    acquisition_path = directory / "ons-data-api.json"
    acquisition_bytes = json.dumps(acquisition).encode("utf-8")
    acquisition_path.write_bytes(acquisition_bytes)
    (directory / "snapshot.json").write_text(
        json.dumps(
            {
                "schema": "okf-ons.frozen-snapshot.v1",
                "snapshotId": "test-r4",
                "metadataOnly": True,
                "observationsIncluded": False,
                "sources": [
                    {
                        "sourceId": "ons-data-api",
                        "file": acquisition_path.name,
                        "reportedTotal": 3,
                        "recordCount": 3,
                        "coverageComplete": True,
                        "unrepresentedCount": 0,
                        "normalisationDroppedCount": 0,
                        "recordSetSha256": record_set_sha256,
                        "snapshotSetSha256": snapshot_set_sha256,
                        "sha256": hashlib.sha256(acquisition_bytes).hexdigest(),
                    }
                ],
                "completeForRegisteredAdapters": True,
                "claimBoundary": "Test fixture covers its registered ONS cohort.",
            }
        ),
        encoding="utf-8",
    )
    return directory


def _version_payload(namespace: dict[str, Any], url: str) -> dict[str, Any]:
    record_id, edition, version = namespace["_version_identity"](url)
    return {
        "alerts": [],
        "collection_id": "",
        "dimensions": [
            {
                "id": "sex",
                "name": "Sex",
                "label": "Sex",
                "is_area_type": None,
                "number_of_options": 3,
                "variable": "sex",
                "links": {
                    "code_list": {
                        "href": "https://api.beta.ons.gov.uk/v1/code-lists/sex"
                    }
                },
                "description": "not projected",
            },
            {
                "id": "geography",
                "name": "Geography",
                "label": "Geography",
                "is_area_type": True,
                "number_of_options": 100,
                "quality_statement_text": "Geographic boundaries use the stated vintage.",
                "quality_statement_url": "https://www.ons.gov.uk/methodology/geography",
            },
        ],
        "downloads": {"csv": {"href": "https://download.ons.gov.uk/file.csv"}},
        "edition": edition,
        # ONS uses an opaque resource UUID here; dataset identity is carried by
        # the request path and links.dataset.id.
        "id": "3a801cac-9803-465f-b8e1-d7d80423fe4c",
        "last_updated": "2026-07-21T12:00:00Z",
        "latest_changes": [{"description": "raw marker must not be retained"}],
        "links": {
            "dataset": {
                "id": record_id,
                "href": f"https://api.beta.ons.gov.uk/v1/datasets/{record_id}",
            },
            "dimensions": {},
            "edition": {
                "id": edition,
                "href": (
                    "https://api.beta.ons.gov.uk/v1/datasets/"
                    f"{record_id}/editions/{edition}"
                ),
            },
            "self": {"href": url},
        },
        "release_date": "2026-07-21T12:00:00Z",
        "state": "published",
        "usage_notes": [],
        "version": version,
    }


class FakeTransport:
    def __init__(self, namespace: dict[str, Any]) -> None:
        self.namespace = namespace
        self.calls: list[str] = []

    def get(self, url: str, *, timeout: float) -> Any:
        self.calls.append(url)
        return self.namespace["JsonResponse"](
            payload=_version_payload(self.namespace, url),
            final_url=url,
            headers={"content-type": "application/json"},
        )


def _build(
    tmp_path: Path,
    *,
    limit: int = 2,
    transport: Any | None = None,
) -> tuple[dict[str, Any], dict[str, Any], Path, Any]:
    namespace = _namespace()
    snapshot = _write_base_snapshot(tmp_path / "snapshot", namespace)
    active_transport = transport or FakeTransport(namespace)
    envelope = namespace["build_enrichment_envelope"](
        snapshot,
        cache_directory=tmp_path / "external-cache",
        limit=limit,
        expected_cohort_count=3,
        request_interval_seconds=0,
        retries=0,
        transport=active_transport,
        now=lambda: datetime(2026, 7, 21, 12, 0, tzinfo=UTC),
    )
    return namespace, envelope, snapshot, active_transport


def test_enrichment_is_ranked_digest_bound_cached_and_projection_only(
    tmp_path: Path,
) -> None:
    namespace, envelope, snapshot, transport = _build(tmp_path)
    base = json.loads((snapshot / "ons-data-api.json").read_text(encoding="utf-8"))
    ranked = sorted(
        [record["sourceRecordId"] for record in base["records"]],
        key=lambda value: (hashlib.sha256(value.encode()).hexdigest(), value, value),
    )
    assert [namespace["_version_identity"](url)[0] for url in transport.calls] == ranked[:2]
    assert [record["sourceRecordId"] for record in envelope["records"]] == [
        "dataset-c",
        "dataset-a",
        "dataset-b",
    ]
    records = {record["sourceRecordId"]: record for record in envelope["records"]}
    selected = records[ranked[0]]["versionDimensions"]
    assert selected == [
        {"id": "sex", "name": "Sex", "label": "Sex", "isAreaType": False},
        {
            "id": "geography",
            "name": "Geography",
            "label": "Geography",
            "isAreaType": True,
            "qualityStatementText": "Geographic boundaries use the stated vintage.",
            "qualityStatementUrl": "https://www.ons.gov.uk/methodology/geography",
        },
    ]
    assert "versionDimensions" not in records[ranked[2]]
    rendered = json.dumps(envelope, sort_keys=True)
    assert "raw marker" not in rendered
    assert "https://download.ons.gov.uk/file.csv" not in rendered
    assert "number_of_options" not in rendered
    assert str(tmp_path / "external-cache") not in rendered

    run = envelope["provenance"]["versionMetadataRun"]
    cohort_bindings = [
        {
            "sourceRecordId": record["sourceRecordId"],
            "latestVersionHref": record["links"]["latest_version"]["href"],
        }
        for record in base["records"]
    ]
    selected_bindings = sorted(
        cohort_bindings,
        key=lambda row: (
            hashlib.sha256(row["sourceRecordId"].encode()).hexdigest(),
            row["sourceRecordId"],
            row["sourceRecordId"],
        ),
    )[:2]
    assert run == {
        "schema": "okf-ons.ons-version-metadata-enrichment.v1",
        "cohortCount": 3,
        "requestedLimit": 2,
        "selectedCount": 2,
        "unselectedCount": 1,
        "coverageComplete": False,
        "selectionOrder": "sha256(sourceRecordId)-ascending",
        "cohortRecordSetSha256": namespace["sha256_json"](cohort_bindings),
        "selectedRecordSetSha256": namespace["sha256_json"](selected_bindings),
    }
    assert envelope["provenance"]["replacement"]["allowedRecordFields"] == [
        "versionDimensions"
    ]
    assert envelope["provenance"]["assurance"] == {
        "cacheLocationPublished": False,
        "credentialsRequired": False,
        "metadataOnly": True,
        "observationsFetched": False,
        "dimensionMetadataFetched": True,
        "dimensionOptionsFetched": False,
        "downloadsFetched": False,
        "rawResponsesPublished": False,
    }
    receipts = envelope["provenance"]["pages"][1:]
    for receipt, record_id in zip(receipts, ranked[:2], strict=True):
        assert receipt["requestUrl"] == receipt["responseUrl"]
        assert receipt["requestUrl"] == next(
            binding["latestVersionHref"]
            for binding in cohort_bindings
            if binding["sourceRecordId"] == record_id
        )
        assert receipt["contentSha256"] == namespace["sha256_json"](
            {"dimensions": records[record_id]["versionDimensions"]}
        )

    cache_files = list((tmp_path / "external-cache" / "ons-version-metadata").glob("*.json"))
    assert len(cache_files) == 2
    for cache_file in cache_files:
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        assert set(cached["payload"]) == {"dimensions"}
        assert "raw marker" not in json.dumps(cached)

    frozen_transport = FakeTransport(namespace)
    frozen = namespace["build_enrichment_envelope"](
        snapshot,
        cache_directory=tmp_path / "external-cache",
        limit=2,
        expected_cohort_count=3,
        mode="frozen",
        request_interval_seconds=0,
        retries=0,
        transport=frozen_transport,
    )
    assert frozen_transport.calls == []
    assert frozen["provenance"]["recordSetSha256"] == envelope["provenance"][
        "recordSetSha256"
    ]
    assert all(page["cacheHit"] for page in frozen["provenance"]["pages"][1:])


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("redirect", "response URL changed unexpectedly"),
        ("wrong-dataset-link", "identity mismatch"),
        ("unknown-top", "unreviewed field.*observations"),
        ("unknown-dimension", "unreviewed field.*options"),
        ("dimension-type", "dimension 0.id is required"),
        ("secret-url", "quality_statement_url is unsafe"),
        ("local-path", "unsafe value"),
        ("secret-value", "unsafe value"),
        ("duplicate", "duplicate dimensions"),
        ("authorization-header", "response headers are unsafe"),
    ],
)
def test_live_response_fails_closed_on_url_schema_secret_and_path_cases(
    tmp_path: Path, case: str, message: str
) -> None:
    namespace = _namespace()
    snapshot = _write_base_snapshot(tmp_path / "snapshot", namespace)

    class UnsafeTransport(FakeTransport):
        def get(self, url: str, *, timeout: float) -> Any:
            response = super().get(url, timeout=timeout)
            if case == "redirect":
                object.__setattr__(response, "final_url", f"{url}?token=secret")
            elif case == "wrong-dataset-link":
                response.payload["links"]["dataset"]["id"] = "different-dataset"
            elif case == "unknown-top":
                response.payload["observations"] = [1]
            elif case == "unknown-dimension":
                response.payload["dimensions"][0]["options"] = ["female"]
            elif case == "dimension-type":
                response.payload["dimensions"][0]["id"] = ["sex"]
            elif case == "secret-url":
                response.payload["dimensions"][1]["quality_statement_url"] = (
                    "https://example.org/quality?access_token=secret"
                )
            elif case == "local-path":
                response.payload["dimensions"][0]["quality_statement_text"] = (
                    "/Users/alice/private.json"
                )
            elif case == "secret-value":
                response.payload["dimensions"][0]["quality_statement_text"] = (
                    "Bearer abcdefghijklmnopqrstuvwxyz"
                )
            elif case == "duplicate":
                response.payload["dimensions"].append(
                    json.loads(json.dumps(response.payload["dimensions"][0]))
                )
            elif case == "authorization-header":
                response.headers["authorization"] = (
                    "Bearer abcdefghijklmnopqrstuvwxyz"
                )
            return response

    with pytest.raises(namespace["ONSVersionMetadataError"], match=message):
        namespace["build_enrichment_envelope"](
            snapshot,
            cache_directory=tmp_path / "external-cache",
            limit=1,
            expected_cohort_count=3,
            request_interval_seconds=0,
            retries=0,
            transport=UnsafeTransport(namespace),
        )


def test_rate_limit_honours_retry_after_before_retrying(tmp_path: Path) -> None:
    namespace = _namespace()
    snapshot = _write_base_snapshot(tmp_path / "snapshot", namespace)
    calls = 0

    class RateLimitedTransport(FakeTransport):
        def get(self, url: str, *, timeout: float) -> Any:
            nonlocal calls
            calls += 1
            if calls == 1:
                return namespace["JsonResponse"](
                    payload=None,
                    final_url=url,
                    status=429,
                    headers={
                        "content-type": "text/plain",
                        "retry-after": "3",
                    },
                )
            return super().get(url, timeout=timeout)

    sleeps: list[float] = []
    namespace["build_enrichment_envelope"](
        snapshot,
        cache_directory=tmp_path / "external-cache",
        limit=1,
        expected_cohort_count=3,
        request_interval_seconds=0,
        retries=1,
        transport=RateLimitedTransport(namespace),
        sleep=sleeps.append,
        now=lambda: datetime(2026, 7, 21, 12, 0, tzinfo=UTC),
    )
    assert calls == 2
    assert sleeps == [3.0]


@pytest.mark.parametrize("interval", [0, 0.1])
def test_production_transport_enforces_minimum_interval(
    tmp_path: Path, interval: float
) -> None:
    namespace = _namespace()
    snapshot = _write_base_snapshot(tmp_path / "snapshot", namespace)
    with pytest.raises(namespace["ONSVersionMetadataError"], match="at least 0.2 seconds"):
        namespace["build_enrichment_envelope"](
            snapshot,
            cache_directory=tmp_path / "external-cache",
            limit=1,
            expected_cohort_count=3,
            request_interval_seconds=interval,
        )


def test_repository_cache_and_unsafe_latest_version_urls_are_rejected(
    tmp_path: Path,
) -> None:
    namespace = _namespace()
    snapshot = _write_base_snapshot(tmp_path / "snapshot", namespace)
    with pytest.raises(namespace["ONSVersionMetadataError"], match="outside the repository"):
        namespace["build_enrichment_envelope"](
            snapshot,
            cache_directory=ROOT / ".unsafe-cache",
            limit=1,
            expected_cohort_count=3,
        )

    acquisition_path = snapshot / "ons-data-api.json"
    manifest_path = snapshot / "snapshot.json"
    acquisition = json.loads(acquisition_path.read_text(encoding="utf-8"))
    acquisition["records"][0]["links"]["latest_version"]["href"] += (
        "?access_token=secret"
    )
    acquisition["provenance"]["recordSetSha256"] = namespace["sha256_json"](
        acquisition["records"]
    )
    acquisition_bytes = json.dumps(acquisition).encode()
    acquisition_path.write_bytes(acquisition_bytes)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    row = manifest["sources"][0]
    row["recordSetSha256"] = acquisition["provenance"]["recordSetSha256"]
    row["sha256"] = hashlib.sha256(acquisition_bytes).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(namespace["ONSVersionMetadataError"], match="exact public ONS API"):
        namespace["build_enrichment_envelope"](
            snapshot,
            cache_directory=tmp_path / "external-cache",
            limit=1,
            expected_cohort_count=3,
            request_interval_seconds=0,
            retries=0,
            transport=FakeTransport(namespace),
        )


def test_frozen_cache_rejects_extra_fields_hashes_secrets_and_symlinks(
    tmp_path: Path,
) -> None:
    namespace, _, snapshot, _ = _build(tmp_path, limit=1)
    cache_path = next(
        (tmp_path / "external-cache" / "ons-version-metadata").glob("*.json")
    )
    original = json.loads(cache_path.read_text(encoding="utf-8"))
    cases: list[tuple[dict[str, Any], str]] = []
    extra = json.loads(json.dumps(original))
    extra["rawCache"] = "/tmp/private"
    cases.append((extra, "unreviewed field"))
    bad_hash = json.loads(json.dumps(original))
    bad_hash["contentSha256"] = "0" * 64
    cases.append((bad_hash, "failed validation"))
    secret = json.loads(json.dumps(original))
    secret["payload"]["dimensions"][0]["qualityStatementText"] = (
        "Bearer abcdefghijklmnopqrstuvwxyz"
    )
    cases.append((secret, "unsafe value"))
    unknown_dimension = json.loads(json.dumps(original))
    unknown_dimension["payload"]["dimensions"][0]["options"] = ["female"]
    cases.append((unknown_dimension, "unreviewed or missing fields"))

    for candidate, message in cases:
        cache_path.write_text(json.dumps(candidate), encoding="utf-8")
        with pytest.raises(namespace["ONSVersionMetadataError"], match=message):
            namespace["build_enrichment_envelope"](
                snapshot,
                cache_directory=tmp_path / "external-cache",
                limit=1,
                expected_cohort_count=3,
                mode="frozen",
                request_interval_seconds=0,
                retries=0,
            )
    cache_path.write_text(json.dumps(original), encoding="utf-8")
    target = cache_path.with_suffix(".real.json")
    cache_path.rename(target)
    cache_path.symlink_to(target.name)
    with pytest.raises(namespace["ONSVersionMetadataError"], match="regular file"):
        namespace["build_enrichment_envelope"](
            snapshot,
            cache_directory=tmp_path / "external-cache",
            limit=1,
            expected_cohort_count=3,
            mode="frozen",
            request_interval_seconds=0,
            retries=0,
        )


@pytest.mark.parametrize(
    "case",
    [
        "manifest-extra",
        "file-hash",
        "snapshot-set",
        "duplicate-source",
        "source-symlink",
        "wrong-cohort-count",
        "duplicate-record",
    ],
)
def test_base_snapshot_and_cohort_validation_fail_closed(
    tmp_path: Path, case: str
) -> None:
    namespace = _namespace()
    snapshot = _write_base_snapshot(tmp_path / "snapshot", namespace)
    manifest_path = snapshot / "snapshot.json"
    acquisition_path = snapshot / "ons-data-api.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    if case == "manifest-extra":
        manifest["token"] = "not-public"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    elif case == "file-hash":
        acquisition_path.write_text(
            acquisition_path.read_text(encoding="utf-8") + "\n", encoding="utf-8"
        )
    elif case == "snapshot-set":
        acquisition = json.loads(acquisition_path.read_text(encoding="utf-8"))
        acquisition["provenance"]["snapshotSetSha256"] = "0" * 64
        acquisition_bytes = json.dumps(acquisition).encode()
        acquisition_path.write_bytes(acquisition_bytes)
        row = manifest["sources"][0]
        row["snapshotSetSha256"] = "0" * 64
        row["sha256"] = hashlib.sha256(acquisition_bytes).hexdigest()
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    elif case == "duplicate-source":
        manifest["sources"].append(json.loads(json.dumps(manifest["sources"][0])))
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    elif case == "source-symlink":
        target = snapshot / "ons-real.json"
        acquisition_path.rename(target)
        acquisition_path.symlink_to(target.name)
    elif case == "wrong-cohort-count":
        pass
    elif case == "duplicate-record":
        acquisition = json.loads(acquisition_path.read_text(encoding="utf-8"))
        acquisition["records"][1] = json.loads(json.dumps(acquisition["records"][0]))
        acquisition["provenance"]["recordSetSha256"] = namespace["sha256_json"](
            acquisition["records"]
        )
        acquisition_bytes = json.dumps(acquisition).encode()
        acquisition_path.write_bytes(acquisition_bytes)
        row = manifest["sources"][0]
        row["recordSetSha256"] = acquisition["provenance"]["recordSetSha256"]
        row["sha256"] = hashlib.sha256(acquisition_bytes).hexdigest()
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    expected_count = 4 if case == "wrong-cohort-count" else 3
    with pytest.raises(namespace["ONSVersionMetadataError"]):
        namespace["build_enrichment_envelope"](
            snapshot,
            cache_directory=tmp_path / "external-cache",
            limit=1,
            expected_cohort_count=expected_count,
            request_interval_seconds=0,
            retries=0,
            transport=FakeTransport(namespace),
        )


def test_checked_in_r4_has_exact_digest_bound_337_record_cohort(
    tmp_path: Path,
) -> None:
    namespace = _namespace()
    acquisition, snapshot_id = namespace["_load_base_acquisition"](R4)
    assert snapshot_id == "metadata-enrichment-2026-07-21-r4"
    assert len(acquisition["records"]) == 337
    assert acquisition["provenance"]["recordSetSha256"] == (
        "272d4b675e746aa93083f076422a591065cb5ac53e8737fbd79b2f67d8d996ee"
    )
    bindings = []
    urls = set()
    for record in acquisition["records"]:
        url = record["links"]["latest_version"]["href"]
        record_id, _, version = namespace["_version_identity"](url)
        assert record_id == record["sourceRecordId"]
        assert str(version) == record["links"]["latest_version"]["id"]
        assert url not in urls
        urls.add(url)
        bindings.append(
            {"sourceRecordId": record_id, "latestVersionHref": url}
        )
    assert len(urls) == 337
    assert namespace["sha256_json"](bindings) == (
        "a68d67e2a0375f353fa4f3888e0b0050650dda45690972625c1b8ecb9fb0de03"
    )

    # A full fake-transport pass proves the production default selects every
    # frozen identity without making a network call.
    transport = FakeTransport(namespace)
    envelope = namespace["build_enrichment_envelope"](
        R4,
        cache_directory=tmp_path / "external-cache",
        request_interval_seconds=0,
        retries=0,
        transport=transport,
        now=lambda: datetime(2026, 7, 21, 12, 0, tzinfo=UTC),
    )
    run = envelope["provenance"]["versionMetadataRun"]
    assert run["cohortCount"] == run["selectedCount"] == 337
    assert run["unselectedCount"] == 0
    assert run["coverageComplete"] is True
    assert run["cohortRecordSetSha256"] == namespace["sha256_json"](bindings)
    assert len(transport.calls) == 337
