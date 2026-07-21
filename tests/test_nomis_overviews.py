from __future__ import annotations

import hashlib
import json
import runpy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from okf_ons.model import normalize_acquisition_record

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "acquire_nomis_overviews.py"
SNAPSHOT_SCRIPT = ROOT / "scripts" / "acquire_snapshot.py"
REGISTER = ROOT / "source" / "source-register.json"


def _namespace() -> dict[str, Any]:
    return runpy.run_path(str(SCRIPT), run_name="nomis_overview_enrichment_test")


def _snapshot_namespace() -> dict[str, Any]:
    return runpy.run_path(str(SNAPSHOT_SCRIPT), run_name="bounded_replacement_test")


def _write_base_snapshot(directory: Path, namespace: dict[str, Any]) -> Path:
    records = [
        {
            "sourceId": "nomis-dataset-definitions",
            "sourceRecordId": record_id,
            "recordKind": "dataset-definition",
            "title": record_id,
        }
        for record_id in ("NM_30_1", "NM_10_1", "NM_20_1")
    ]
    page_receipts = [
        {
            "requestUrl": "https://www.nomisweb.co.uk/api/v01/dataset/def.sdmx.json",
            "responseUrl": "https://www.nomisweb.co.uk/api/v01/dataset/def.sdmx.json",
            "retrievedAt": "2026-07-17T08:00:00Z",
            "contentSha256": "b" * 64,
            "responseHeaders": {},
            "cacheHit": True,
            "upstreamRecordCount": 3,
            "normalisedRecordCount": 3,
        }
    ]
    record_set_sha256 = namespace["sha256_json"](records)
    acquisition = {
        "schemaVersion": "okf-ons.source-acquisition.v1",
        "records": records,
        "provenance": {
            "source": {
                "id": "nomis-dataset-definitions",
                "endpoint": "https://www.nomisweb.co.uk/api/v01/dataset/def.sdmx.json",
            },
            "recordCount": 3,
            "reportedTotal": 3,
            "complete": True,
            "normalisationDroppedCount": 0,
            "normalisedRecordsSeen": 3,
            "pageCount": 1,
            "recordSetSha256": record_set_sha256,
            "snapshotSetSha256": namespace["sha256_json"](
                [
                    {
                        "requestUrl": page_receipts[0]["requestUrl"],
                        "contentSha256": page_receipts[0]["contentSha256"],
                    }
                ]
            ),
            "pages": page_receipts,
            "coverageComplete": True,
            "retrievalMode": "prefer-cache",
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
    acquisition_path = directory / "nomis-dataset-definitions.json"
    acquisition_bytes = json.dumps(acquisition).encode("utf-8")
    acquisition_path.write_bytes(acquisition_bytes)
    (directory / "snapshot.json").write_text(
        json.dumps(
            {
                "schema": "okf-ons.frozen-snapshot.v1",
                "snapshotId": "test-r3",
                "metadataOnly": True,
                "observationsIncluded": False,
                "sources": [
                    {
                        "sourceId": "nomis-dataset-definitions",
                        "file": acquisition_path.name,
                        "reportedTotal": 3,
                        "recordCount": 3,
                        "coverageComplete": True,
                        "unrepresentedCount": 0,
                        "normalisationDroppedCount": 0,
                        "recordSetSha256": record_set_sha256,
                        "snapshotSetSha256": acquisition["provenance"][
                            "snapshotSetSha256"
                        ],
                        "sha256": hashlib.sha256(acquisition_bytes).hexdigest(),
                    }
                ],
                "completeForRegisteredAdapters": True,
                "claimBoundary": "Test fixture covers its registered Nomis cohort.",
            }
        ),
        encoding="utf-8",
    )
    return directory


class FakeTransport:
    def __init__(self, response_type: type[Any]) -> None:
        self.response_type = response_type
        self.calls: list[str] = []

    def get(self, url: str, *, timeout: float) -> Any:
        self.calls.append(url)
        record_id = url.split("/")[-1].split(".overview.json", maxsplit=1)[0]
        return self.response_type(
            payload={
                "overview": {
                    "id": record_id,
                    "contact": {
                        "name": "Nomis",
                        "email": "support@nomisweb.co.uk",
                        "uri": "https://www.nomisweb.co.uk",
                    },
                    "coverage": "United Kingdom",
                    "firstreleased": "2004-06-16 09:30:00",
                    "lastrevised": "2023-01-27 10:00:00",
                    "lastupdated": "2026-07-21 07:00:00",
                    "nextupdate": None,
                    "analysisname": "must not be projected",
                    "provider": {"name": "must not be projected"},
                }
            },
            final_url=url,
            headers={"content-type": "application/json"},
        )


def _replacement_context(
    tmp_path: Path, *, limit: int = 2
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    namespace = _namespace()
    composer = _snapshot_namespace()
    snapshot = _write_base_snapshot(tmp_path / "snapshot", namespace)
    replacement = namespace["build_enrichment_envelope"](
        snapshot,
        cache_directory=tmp_path / "external-cache",
        limit=limit,
        request_interval_seconds=0,
        retries=0,
        transport=FakeTransport(namespace["JsonResponse"]),
        now=lambda: datetime(2026, 7, 21, 12, 0, tzinfo=UTC),
    )
    base = json.loads(
        (snapshot / "nomis-dataset-definitions.json").read_text(encoding="utf-8")
    )
    return namespace, composer, replacement, base


def test_enrichment_is_ranked_bounded_cached_and_metadata_only(tmp_path: Path) -> None:
    namespace = _namespace()
    snapshot = _write_base_snapshot(tmp_path / "snapshot", namespace)
    transport = FakeTransport(namespace["JsonResponse"])
    cache = tmp_path / "external-cache"

    def fixed_now() -> datetime:
        return datetime(2026, 7, 21, 12, 0, tzinfo=UTC)

    envelope = namespace["build_enrichment_envelope"](
        snapshot,
        cache_directory=cache,
        limit=2,
        mode="prefer-cache",
        request_interval_seconds=0,
        retries=0,
        transport=transport,
        now=fixed_now,
    )

    selected_ids = sorted(
        ("NM_10_1", "NM_20_1", "NM_30_1"),
        key=lambda item: hashlib.sha256(item.encode("utf-8")).hexdigest(),
    )[:2]
    assert [url.split("/")[-1].split(".")[0] for url in transport.calls] == selected_ids
    records = {record["sourceRecordId"]: record for record in envelope["records"]}
    assert records["NM_10_1"]["contacts"] == [
        {
            "name": "Nomis",
            "email": "support@nomisweb.co.uk",
            "url": "https://www.nomisweb.co.uk",
        }
    ]
    assert records["NM_10_1"]["geographicCoverage"] == "United Kingdom"
    assert records["NM_10_1"]["lastRevised"] == "2023-01-27 10:00:00"
    assert "nextUpdate" not in records["NM_10_1"]
    assert records["NM_30_1"] == {
        "sourceId": "nomis-dataset-definitions",
        "sourceRecordId": "NM_30_1",
        "recordKind": "dataset-definition",
        "title": "NM_30_1",
    }
    rendered = json.dumps(envelope, sort_keys=True)
    assert "must not be projected" not in rendered
    assert str(cache) not in rendered
    assert len(list((cache / "nomis-overview").glob("*.json"))) == 2

    run = envelope["provenance"]["enrichmentRun"]
    assert run == {
        "schema": "okf-ons.nomis-overview-enrichment.v1",
        "cohortCount": 3,
        "requestedLimit": 2,
        "selectedCount": 2,
        "unselectedCount": 1,
        "coverageComplete": False,
        "selectionOrder": "sha256(sourceRecordId)-ascending",
        "selectedRecordSetSha256": namespace["sha256_json"](selected_ids),
        "select": ["DatasetInfo", "Coverage", "DateMetadata", "Contact"],
    }
    assert envelope["provenance"]["assurance"]["observationsFetched"] is False
    assert envelope["provenance"]["assurance"]["codelistsFetched"] is False
    assert len(envelope["provenance"]["pages"]) == 3
    for receipt in envelope["provenance"]["pages"][1:]:
        assert len(receipt["contentSha256"]) == 64
        assert receipt["requestUrl"].endswith(
            "?select=DatasetInfo%2CCoverage%2CDateMetadata%2CContact"
        )

    frozen_transport = FakeTransport(namespace["JsonResponse"])
    frozen = namespace["build_enrichment_envelope"](
        snapshot,
        cache_directory=cache,
        limit=2,
        mode="frozen",
        request_interval_seconds=0,
        retries=0,
        transport=frozen_transport,
        now=fixed_now,
    )
    assert frozen_transport.calls == []
    assert frozen["provenance"]["recordSetSha256"] == envelope["provenance"][
        "recordSetSha256"
    ]
    assert all(page["cacheHit"] for page in frozen["provenance"]["pages"][1:])


def test_enrichment_rejects_repository_cache_and_identity_mismatch(tmp_path: Path) -> None:
    namespace = _namespace()
    snapshot = _write_base_snapshot(tmp_path / "snapshot", namespace)

    with pytest.raises(namespace["NomisOverviewError"], match="outside the repository"):
        namespace["build_enrichment_envelope"](
            snapshot,
            cache_directory=ROOT / ".unsafe-cache",
            limit=1,
        )

    class WrongIdentityTransport(FakeTransport):
        def get(self, url: str, *, timeout: float) -> Any:
            response = super().get(url, timeout=timeout)
            response.payload["overview"]["id"] = "NM_WRONG_1"
            return response

    with pytest.raises(namespace["NomisOverviewError"], match="identity mismatch"):
        namespace["build_enrichment_envelope"](
            snapshot,
            cache_directory=tmp_path / "external-cache",
            limit=1,
            request_interval_seconds=0,
            retries=0,
            transport=WrongIdentityTransport(namespace["JsonResponse"]),
        )


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("obs", "unreviewed field.*obs"),
        ("codes", "unreviewed field.*codes"),
        ("date-shape", "date field.*invalid shape"),
        ("date-value", "not a valid timestamp"),
        ("authorization-header", "response headers are unsafe"),
        ("redirect", "response URL changed unexpectedly"),
        ("secret-query", "contact URI is unsafe"),
        ("local-path", "unsafe value"),
        ("secret-value", "unsafe value"),
    ],
)
def test_live_enrichment_rejects_unreviewed_or_unsafe_metadata(
    tmp_path: Path, case: str, message: str
) -> None:
    namespace = _namespace()
    snapshot = _write_base_snapshot(tmp_path / "snapshot", namespace)

    class UnsafeTransport(FakeTransport):
        def get(self, url: str, *, timeout: float) -> Any:
            response = super().get(url, timeout=timeout)
            overview = response.payload["overview"]
            if case == "obs":
                overview["obs"] = [123]
            elif case == "codes":
                overview["codes"] = ["A"]
            elif case == "date-shape":
                overview["lastupdated"] = "21 July 2026"
            elif case == "date-value":
                overview["lastupdated"] = "2026-02-30 12:00:00"
            elif case == "authorization-header":
                response.headers["authorization"] = (
                    "Bearer abcdefghijklmnopqrstuvwxyz"
                )
            elif case == "redirect":
                object.__setattr__(response, "final_url", f"{url}&access_token=secret")
            elif case == "secret-query":
                overview["contact"]["uri"] = (
                    "https://www.nomisweb.co.uk/?client_secret=secret"
                )
            elif case == "local-path":
                overview["description"] = "/Users/alice/private/cache.json"
            elif case == "secret-value":
                overview["description"] = "Bearer abcdefghijklmnopqrstuvwxyz"
            return response

    with pytest.raises(namespace["NomisOverviewError"], match=message):
        namespace["build_enrichment_envelope"](
            snapshot,
            cache_directory=tmp_path / "external-cache",
            limit=1,
            request_interval_seconds=0,
            retries=0,
            transport=UnsafeTransport(namespace["JsonResponse"]),
        )


@pytest.mark.parametrize("interval", [0, 0.1])
def test_live_enrichment_requires_a_safe_production_interval(
    tmp_path: Path, interval: float
) -> None:
    namespace = _namespace()
    snapshot = _write_base_snapshot(tmp_path / "snapshot", namespace)
    with pytest.raises(namespace["NomisOverviewError"], match="at least 0.2 seconds"):
        namespace["build_enrichment_envelope"](
            snapshot,
            cache_directory=tmp_path / "external-cache",
            limit=1,
            mode="prefer-cache",
            request_interval_seconds=interval,
        )


def test_frozen_cache_requires_exact_safe_envelope(tmp_path: Path) -> None:
    namespace = _namespace()
    snapshot = _write_base_snapshot(tmp_path / "snapshot", namespace)
    cache = tmp_path / "external-cache"
    namespace["build_enrichment_envelope"](
        snapshot,
        cache_directory=cache,
        limit=1,
        request_interval_seconds=0,
        retries=0,
        transport=FakeTransport(namespace["JsonResponse"]),
        now=lambda: datetime(2026, 7, 21, 12, 0, tzinfo=UTC),
    )
    cache_path = next((cache / "nomis-overview").glob("*.json"))
    original = json.loads(cache_path.read_text(encoding="utf-8"))

    cases: list[tuple[dict[str, Any], str]] = []
    extra = json.loads(json.dumps(original))
    extra["token"] = "not-public"
    cases.append((extra, "cache entry has unreviewed field"))
    bad_timestamp = json.loads(json.dumps(original))
    bad_timestamp["retrievedAt"] = "yesterday"
    cases.append((bad_timestamp, "UTC ISO 8601 timestamp"))
    bad_header = json.loads(json.dumps(original))
    bad_header["responseHeaders"]["x-api-key"] = "secret-value"
    cases.append((bad_header, "response headers are unsafe"))
    bad_url = json.loads(json.dumps(original))
    bad_url["responseUrl"] += "&sig=secret"
    cases.append((bad_url, "cache entry failed validation"))
    observation = json.loads(json.dumps(original))
    observation["payload"]["overview"]["observations"] = [1]
    cases.append((observation, "unreviewed field.*observations"))
    local_path = json.loads(json.dumps(original))
    local_path["payload"]["overview"]["description"] = "/tmp/private.json"
    cases.append((local_path, "unsafe value"))

    for candidate, message in cases:
        cache_path.write_text(json.dumps(candidate), encoding="utf-8")
        with pytest.raises(namespace["NomisOverviewError"], match=message):
            namespace["build_enrichment_envelope"](
                snapshot,
                cache_directory=cache,
                limit=1,
                mode="frozen",
                request_interval_seconds=0,
                retries=0,
            )


def test_frozen_cache_rejects_symlink_entries(tmp_path: Path) -> None:
    namespace = _namespace()
    snapshot = _write_base_snapshot(tmp_path / "snapshot", namespace)
    cache = tmp_path / "external-cache"
    namespace["build_enrichment_envelope"](
        snapshot,
        cache_directory=cache,
        limit=1,
        request_interval_seconds=0,
        retries=0,
        transport=FakeTransport(namespace["JsonResponse"]),
    )
    cache_path = next((cache / "nomis-overview").glob("*.json"))
    target = cache_path.with_suffix(".real.json")
    cache_path.rename(target)
    cache_path.symlink_to(target.name)
    with pytest.raises(namespace["NomisOverviewError"], match="regular file"):
        namespace["build_enrichment_envelope"](
            snapshot,
            cache_directory=cache,
            limit=1,
            mode="frozen",
            request_interval_seconds=0,
            retries=0,
        )


@pytest.mark.parametrize(
    "case", ["manifest-extra", "file-hash", "snapshot-set", "duplicate", "symlink"]
)
def test_base_snapshot_validation_fails_closed(tmp_path: Path, case: str) -> None:
    namespace = _namespace()
    snapshot = _write_base_snapshot(tmp_path / "snapshot", namespace)
    manifest_path = snapshot / "snapshot.json"
    acquisition_path = snapshot / "nomis-dataset-definitions.json"
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
        acquisition_bytes = json.dumps(acquisition).encode("utf-8")
        acquisition_path.write_bytes(acquisition_bytes)
        manifest["sources"][0]["snapshotSetSha256"] = "0" * 64
        manifest["sources"][0]["sha256"] = hashlib.sha256(
            acquisition_bytes
        ).hexdigest()
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    elif case == "duplicate":
        manifest["sources"].append(json.loads(json.dumps(manifest["sources"][0])))
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    elif case == "symlink":
        target = snapshot / "nomis-real.json"
        acquisition_path.rename(target)
        acquisition_path.symlink_to(target.name)

    with pytest.raises(namespace["NomisOverviewError"]):
        namespace["build_enrichment_envelope"](
            snapshot,
            cache_directory=tmp_path / "external-cache",
            limit=1,
            request_interval_seconds=0,
            retries=0,
            transport=FakeTransport(namespace["JsonResponse"]),
        )


def test_composer_base_loader_rejects_symlink_sources(tmp_path: Path) -> None:
    namespace = _namespace()
    composer = _snapshot_namespace()
    snapshot = _write_base_snapshot(tmp_path / "snapshot", namespace)
    registered = composer["load_source_register"](REGISTER)
    sources = {"nomis-dataset-definitions": registered["nomis-dataset-definitions"]}

    manifest, carried, manifest_sha256 = composer["_load_base_snapshot"](
        snapshot, sources, require_complete=True
    )
    assert manifest["snapshotId"] == "test-r3"
    assert set(carried) == set(sources)
    assert len(manifest_sha256) == 64

    acquisition_path = snapshot / "nomis-dataset-definitions.json"
    target = snapshot / "nomis-real.json"
    acquisition_path.rename(target)
    acquisition_path.symlink_to(target.name)
    with pytest.raises(composer["SnapshotCompositionError"], match="source file is unsafe"):
        composer["_load_base_snapshot"](snapshot, sources, require_complete=True)


def test_bounded_replacement_is_bound_to_base_and_allowlisted(tmp_path: Path) -> None:
    namespace = _namespace()
    composer = _snapshot_namespace()
    snapshot = _write_base_snapshot(tmp_path / "snapshot", namespace)
    transport = FakeTransport(namespace["JsonResponse"])
    replacement = namespace["build_enrichment_envelope"](
        snapshot,
        cache_directory=tmp_path / "external-cache",
        limit=2,
        request_interval_seconds=0,
        retries=0,
        transport=transport,
        now=lambda: datetime(2026, 7, 21, 12, 0, tzinfo=UTC),
    )
    base = json.loads(
        (snapshot / "nomis-dataset-definitions.json").read_text(encoding="utf-8")
    )

    summary = composer["_validate_bounded_replacement"](
        replacement,
        base,
        "nomis-dataset-definitions",
        base_snapshot_id="test-r3",
    )
    assert summary == {"changedRecords": 2, "changedFields": 10}

    protected_change = json.loads(json.dumps(replacement))
    protected_change["records"][0]["title"] = "tampered"
    with pytest.raises(
        composer["SnapshotCompositionError"], match="changed protected fields"
    ):
        composer["_validate_bounded_replacement"](
            protected_change,
            base,
            "nomis-dataset-definitions",
            base_snapshot_id="test-r3",
        )

    null_unsupported = json.loads(json.dumps(replacement))
    null_unsupported["records"][0]["credentials"] = None
    with pytest.raises(
        composer["SnapshotCompositionError"], match="changed protected fields"
    ):
        composer["_validate_bounded_replacement"](
            null_unsupported,
            base,
            "nomis-dataset-definitions",
            base_snapshot_id="test-r3",
        )

    wrong_base = json.loads(json.dumps(replacement))
    wrong_base["provenance"]["replacement"]["baseRecordSetSha256"] = "0" * 64
    with pytest.raises(
        composer["SnapshotCompositionError"], match="not bound to its base"
    ):
        composer["_validate_bounded_replacement"](
            wrong_base,
            base,
            "nomis-dataset-definitions",
            base_snapshot_id="test-r3",
        )


def test_bounded_replacement_rejects_unsafe_contact_url(tmp_path: Path) -> None:
    namespace = _namespace()
    composer = _snapshot_namespace()
    snapshot = _write_base_snapshot(tmp_path / "snapshot", namespace)
    replacement = namespace["build_enrichment_envelope"](
        snapshot,
        cache_directory=tmp_path / "external-cache",
        limit=1,
        request_interval_seconds=0,
        retries=0,
        transport=FakeTransport(namespace["JsonResponse"]),
    )
    base = json.loads(
        (snapshot / "nomis-dataset-definitions.json").read_text(encoding="utf-8")
    )
    escaped_endpoint = json.loads(json.dumps(replacement))
    overview_page = escaped_endpoint["provenance"]["pages"][1]
    overview_page["requestUrl"] = overview_page["requestUrl"].replace(
        ".overview.json", ".jsonstat.json"
    )
    overview_page["responseUrl"] = overview_page["requestUrl"]
    with pytest.raises(
        composer["SnapshotCompositionError"], match="metadata-only endpoint"
    ):
        composer["_validate_bounded_replacement"](
            escaped_endpoint,
            base,
            "nomis-dataset-definitions",
            base_snapshot_id="test-r3",
        )

    enriched = next(record for record in replacement["records"] if record.get("contacts"))
    enriched["contacts"][0]["url"] = "https://example.org/contact?uid=secret"
    with pytest.raises(composer["SnapshotCompositionError"], match="unsafe contact URL"):
        composer["_validate_bounded_replacement"](
            replacement,
            base,
            "nomis-dataset-definitions",
            base_snapshot_id="test-r3",
        )


def test_composer_fail_closes_on_unreviewed_replacement_shapes(
    tmp_path: Path,
) -> None:
    _, composer, replacement, base = _replacement_context(tmp_path)

    cases: list[tuple[dict[str, Any], str]] = []

    top_level_observations = json.loads(json.dumps(replacement))
    top_level_observations["observations"] = [1]
    cases.append((top_level_observations, "acquisition has unreviewed field"))

    provenance_token = json.loads(json.dumps(replacement))
    provenance_token["provenance"]["token"] = "not-public"
    cases.append((provenance_token, "provenance has unreviewed field"))

    run_token = json.loads(json.dumps(replacement))
    run_token["provenance"]["enrichmentRun"]["token"] = "not-public"
    cases.append((run_token, "enrichment run has unreviewed field"))

    replacement_extra = json.loads(json.dumps(replacement))
    replacement_extra["provenance"]["replacement"]["rawCache"] = "/tmp/cache"
    cases.append((replacement_extra, "declaration has unreviewed field"))

    assurance_extra = json.loads(json.dumps(replacement))
    assurance_extra["provenance"]["assurance"]["token"] = "not-public"
    cases.append((assurance_extra, "metadata-only assurance"))

    base_page_bearer = json.loads(json.dumps(replacement))
    base_page_bearer["provenance"]["pages"][0]["responseHeaders"] = {
        "authorization": "Bearer abcdefghijklmnopqrstuvwxyz"
    }
    cases.append((base_page_bearer, "changed base page lineage"))

    new_page_bearer = json.loads(json.dumps(replacement))
    new_page_bearer["provenance"]["pages"][1]["responseHeaders"] = {
        "authorization": "Bearer abcdefghijklmnopqrstuvwxyz"
    }
    cases.append((new_page_bearer, "page headers are unsafe"))

    for candidate, message in cases:
        with pytest.raises(composer["SnapshotCompositionError"], match=message):
            composer["_validate_bounded_replacement"](
                candidate,
                base,
                "nomis-dataset-definitions",
                base_snapshot_id="test-r3",
            )


def test_composer_recomputes_nomis_endpoint_selection_and_lineage(
    tmp_path: Path,
) -> None:
    _, composer, replacement, base = _replacement_context(tmp_path)

    cases: list[tuple[dict[str, Any], str]] = []

    unknown_schema = json.loads(json.dumps(replacement))
    unknown_schema["provenance"]["enrichmentRun"]["schema"] = "unknown.v1"
    cases.append((unknown_schema, "schema is unsupported"))

    changed_reported_total = json.loads(json.dumps(replacement))
    changed_reported_total["provenance"]["reportedTotal"] = 999
    cases.append((changed_reported_total, "changed unrelated base provenance"))

    malformed_timestamp = json.loads(json.dumps(replacement))
    malformed_timestamp["provenance"]["pages"][1]["retrievedAt"] = "next Tuesday"
    cases.append((malformed_timestamp, "UTC ISO 8601 timestamp"))

    malformed_hash = json.loads(json.dumps(replacement))
    malformed_hash["provenance"]["pages"][1]["contentSha256"] = "A" * 64
    cases.append((malformed_hash, "lowercase SHA-256 digest"))

    malformed_cache_hit = json.loads(json.dumps(replacement))
    malformed_cache_hit["provenance"]["pages"][1]["cacheHit"] = "false"
    cases.append((malformed_cache_hit, "page counts are invalid"))

    malformed_count = json.loads(json.dumps(replacement))
    malformed_count["provenance"]["pages"][1]["upstreamRecordCount"] = True
    cases.append((malformed_count, "page counts are invalid"))

    extra_page_field = json.loads(json.dumps(replacement))
    extra_page_field["provenance"]["pages"][1]["token"] = "not-public"
    cases.append((extra_page_field, "enrichment page 0 has unreviewed field"))

    wrong_path = json.loads(json.dumps(replacement))
    wrong_path["provenance"]["pages"][1]["requestUrl"] = wrong_path["provenance"][
        "pages"
    ][1]["requestUrl"].replace("/api/v01/dataset/", "/api/v01/not-dataset/")
    wrong_path["provenance"]["pages"][1]["responseUrl"] = wrong_path["provenance"][
        "pages"
    ][1]["requestUrl"]
    cases.append((wrong_path, "metadata-only endpoint"))

    secret_query = json.loads(json.dumps(replacement))
    secret_query["provenance"]["pages"][1]["requestUrl"] += "&access_token=secret"
    secret_query["provenance"]["pages"][1]["responseUrl"] = secret_query[
        "provenance"
    ]["pages"][1]["requestUrl"]
    cases.append((secret_query, "metadata-only endpoint"))

    wrong_count = json.loads(json.dumps(replacement))
    wrong_count["provenance"]["enrichmentRun"]["selectedCount"] = 1
    wrong_count["provenance"]["enrichmentRun"]["unselectedCount"] = 2
    cases.append((wrong_count, "denominator is invalid"))

    wrong_hash = json.loads(json.dumps(replacement))
    wrong_hash["provenance"]["enrichmentRun"]["selectedRecordSetSha256"] = "0" * 64
    cases.append((wrong_hash, "deterministic selection is invalid"))

    wrong_rank = json.loads(json.dumps(replacement))
    pages = wrong_rank["provenance"]["pages"]
    pages[1], pages[2] = pages[2], pages[1]
    cases.append((wrong_rank, "deterministic selection is invalid"))

    malformed_projected_date = json.loads(json.dumps(replacement))
    enriched = next(
        record for record in malformed_projected_date["records"] if record.get("lastUpdated")
    )
    enriched["lastUpdated"] = "July 2026"
    cases.append((malformed_projected_date, "date metadata is malformed"))

    false_frozen_receipt = json.loads(json.dumps(replacement))
    false_frozen_receipt["provenance"]["retrievalMode"] = "overview-enrichment:frozen"
    cases.append((false_frozen_receipt, "receipts contradict retrieval mode"))

    false_refresh_receipt = json.loads(json.dumps(replacement))
    false_refresh_receipt["provenance"]["retrievalMode"] = "overview-enrichment:refresh"
    false_refresh_receipt["provenance"]["pages"][1]["cacheHit"] = True
    cases.append((false_refresh_receipt, "receipts contradict retrieval mode"))

    for candidate, message in cases:
        with pytest.raises(composer["SnapshotCompositionError"], match=message):
            composer["_validate_bounded_replacement"](
                candidate,
                base,
                "nomis-dataset-definitions",
                base_snapshot_id="test-r3",
            )


def test_composer_recomputes_full_cohort_coverage(tmp_path: Path) -> None:
    _, composer, replacement, base = _replacement_context(tmp_path, limit=99)
    run = replacement["provenance"]["enrichmentRun"]
    assert run["selectedCount"] == 3
    assert run["coverageComplete"] is True
    assert replacement["provenance"]["stopReason"] == "sourceExhausted"
    assert composer["_validate_bounded_replacement"](
        replacement,
        base,
        "nomis-dataset-definitions",
        base_snapshot_id="test-r3",
    ) == {"changedRecords": 3, "changedFields": 15}

    false_full_set = json.loads(json.dumps(replacement))
    false_full_set["provenance"]["enrichmentRun"]["requestedLimit"] = 2
    with pytest.raises(
        composer["SnapshotCompositionError"], match="denominator is invalid"
    ):
        composer["_validate_bounded_replacement"](
            false_full_set,
            base,
            "nomis-dataset-definitions",
            base_snapshot_id="test-r3",
        )


def test_nomis_overview_metadata_is_mapped_without_inventing_revision_status() -> None:
    record = normalize_acquisition_record(
        {
            "sourceId": "nomis-dataset-definitions",
            "sourceRecordId": "NM_TEST_OVERVIEW",
            "recordKind": "dataset-definition",
            "title": "Nomis overview mapping test",
            "description": "A dataset with compact overview metadata.",
            "contacts": [
                {
                    "name": "Nomis",
                    "email": "support@nomisweb.co.uk",
                    "telephone": "01234 567890",
                    "url": "https://www.nomisweb.co.uk",
                }
            ],
            "geographicCoverage": "United Kingdom",
            "lastRevised": "2025-10-28 09:30:00",
            "nextUpdate": "2026-08-01 07:00:00",
            "annotations": [
                {"title": "LastRevised", "text": "2020-01-01 09:30:00"},
                {"title": "Status", "text": "Current (being actively updated)"},
            ],
        },
        snapshot_id="snapshot:test-r4",
        provenance={
            "source": {
                "id": "nomis-dataset-definitions",
                "adapter": "nomis-sdmx",
                "endpoint": "https://www.nomisweb.co.uk/api/v01/dataset/def.sdmx.json",
            },
            "pages": [{"retrievedAt": "2026-07-21T12:00:00Z"}],
            "recordSetSha256": "a" * 64,
        },
    )

    assert record is not None
    assert record["contacts"] == [
        {
            "name": "Nomis",
            "email": "support@nomisweb.co.uk",
            "telephone": "01234 567890",
            "url": "https://www.nomisweb.co.uk",
        }
    ]
    assert record["geography"] == []
    assert record["geographic_coverage"] == "United Kingdom"
    assert record["area_served"] == ["United Kingdom"]
    assert record["geography_metadata"] == {
        "levels": [],
        "coverage": "United Kingdom",
        "derivationMode": "source-declared",
    }
    assert record["revision_status"] == ""
    assert record["last_revised"] == "2025-10-28 09:30:00"
    assert record["next_update"] == "2026-08-01 07:00:00"
    assert record["publication"] == {
        "release_date": "",
        "revision_status": "",
        "revision_date": "2025-10-28 09:30:00",
        "next_update": "2026-08-01 07:00:00",
        "state": "published",
    }
    evidence = record["quality_evidence"]["evidence"]
    assert evidence["contact"] is True
    assert evidence["geography"] is True
    # A source-declared revision date is useful publication metadata, but it is
    # not evidence of a current revision status. Keep the fixed campaign metric
    # semantically stable rather than counting an adjacent field as complete.
    assert evidence["revision_status"] is False
    assert record["metadata_derivation"]["fields"] == {
        "area_served": {
            "mode": "source-declared",
            "sourceField": "overview.coverage",
        },
        "contacts": {
            "mode": "source-declared",
            "sourceField": "overview.contact",
        },
        "last_revised": {
            "mode": "source-declared",
            "sourceField": "overview.lastrevised",
        },
        "next_update": {
            "mode": "source-declared",
            "sourceField": "overview.nextupdate",
        },
    }
