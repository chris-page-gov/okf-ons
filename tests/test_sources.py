from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from okf_ons.sources import (  # noqa: E402
    HttpJsonResponse,
    SourceAcquisitionError,
    SourceConfigurationError,
    acquire_source,
    load_source_register,
)

REGISTER = ROOT / "source" / "source-register.json"


def fixed_now() -> datetime:
    return datetime(2026, 7, 17, 12, 0, tzinfo=UTC)


class FakeTransport:
    def __init__(self, handler: Any) -> None:
        self.handler = handler
        self.calls: list[tuple[str, dict[str, str], float]] = []

    def get_json(
        self,
        url: str,
        params: dict[str, str],
        *,
        timeout: float,
    ) -> HttpJsonResponse:
        self.calls.append((url, dict(params), timeout))
        return self.handler(url, dict(params))


class NoNetworkTransport:
    def get_json(
        self,
        url: str,
        params: dict[str, str],
        *,
        timeout: float,
    ) -> HttpJsonResponse:
        raise AssertionError(f"Frozen acquisition attempted network access: {url}")


def test_source_register_is_official_metadata_only_and_secret_free() -> None:
    raw = json.loads(REGISTER.read_text(encoding="utf-8"))
    sources = load_source_register(REGISTER)

    assert set(sources) == {
        "ons-data-api",
        "nomis-dataset-definitions",
        "ons-open-geography",
    }
    assert all(source.endpoint.startswith("https://") for source in sources.values())
    assert all(source.excludes for source in sources.values())
    assert all(
        any("observation" in exclusion.casefold() for exclusion in source.excludes)
        for source in sources.values()
    )
    serialised = json.dumps(raw).casefold()
    assert "api_key" not in serialised
    assert "password" not in serialised
    assert "/users/" not in serialised
    assert "/tmp/" not in serialised


def test_register_rejects_credential_query_parameters(tmp_path: Path) -> None:
    raw = json.loads(REGISTER.read_text(encoding="utf-8"))
    raw["sources"][0]["endpoint"] += "?api_key=not-allowed"
    unsafe = tmp_path / "source-register.json"
    unsafe.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(SourceConfigurationError, match="credential query"):
        load_source_register(unsafe)


def test_ons_pages_resume_and_replay_deterministically(
    tmp_path: Path,
) -> None:
    source = load_source_register(REGISTER)["ons-data-api"]
    clock = {"value": 0.0}
    sleeps: list[float] = []

    def monotonic() -> float:
        return clock["value"]

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["value"] += seconds

    def handler(url: str, params: dict[str, str]) -> HttpJsonResponse:
        assert url == source.endpoint
        offset = int(params["offset"])
        if offset == 0:
            payload = {
                "results": [
                    {
                        "id": "beta",
                        "title": "Beta dataset",
                        "description": "Second alphabetically",
                        "keywords": ["Population"],
                        "state": "published",
                        "last_updated": "2026-07-17T08:00:00Z",
                        "release_frequency": "Quarterly",
                        "unit_of_measure": "Percentage",
                        "national_statistic": True,
                        "methodologies": [
                            {
                                "title": "Technical report",
                                "href": "https://www.ons.gov.uk/methodology",
                            }
                        ],
                        "qmi": {"href": "https://www.ons.gov.uk/qmi"},
                        "related_datasets": [
                            {
                                "title": "Related series",
                                "href": "https://www.ons.gov.uk/related",
                            }
                        ],
                        "links": {
                            "self": {"href": "https://api.beta.ons.gov.uk/v1/datasets/beta"},
                            "unsafe": {"href": "https://example.test/data?token=must-not-publish"},
                        },
                        "observations": [999],
                    },
                    {
                        "id": "alpha",
                        "title": "Alpha dataset",
                        "state": "published",
                    },
                ],
                "total_count": 3,
            }
        else:
            assert offset == 2
            payload = {
                "results": [
                    {
                        "id": "gamma",
                        "title": "Gamma dataset",
                        "state": "published",
                    }
                ],
                "total_count": 3,
            }
        return HttpJsonResponse(
            payload=payload,
            final_url=(f"{source.endpoint}?limit={params['limit']}&offset={params['offset']}"),
            headers={"ETag": f'"page-{offset}"', "Authorization": "must-not-leak"},
        )

    transport = FakeTransport(handler)
    live = acquire_source(
        source,
        cache_directory=tmp_path / "raw-cache",
        transport=transport,
        page_size=2,
        request_interval_seconds=0.5,
        retries=0,
        monotonic=monotonic,
        sleep=sleep,
        now=fixed_now,
    )

    assert len(transport.calls) == 2
    assert sleeps == [0.5]
    assert [record["sourceRecordId"] for record in live.records] == [
        "alpha",
        "beta",
        "gamma",
    ]
    assert all("observations" not in json.dumps(record).casefold() for record in live.records)
    assert "must-not-publish" not in json.dumps(live.as_public_dict())
    assert live.provenance["complete"] is True
    assert live.provenance["coverageComplete"] is True
    assert live.provenance["reportedTotal"] == 3
    assert live.provenance["upstreamRecordsSeen"] == 3
    assert live.provenance["normalisationDroppedCount"] == 0
    assert live.provenance["unrepresentedCount"] == 0
    assert live.provenance["pages"][0]["responseHeaders"] == {"etag": '"page-0"'}
    beta = next(record for record in live.records if record["sourceRecordId"] == "beta")
    assert beta["releaseFrequency"] == "Quarterly"
    assert beta["unitOfMeasure"] == "Percentage"
    assert beta["nationalStatistic"] is True
    assert beta["methodologies"][0]["title"] == "Technical report"
    assert beta["qualityMethodologyInformation"][0]["href"].endswith("/qmi")
    assert beta["relatedDatasets"][0]["title"] == "Related series"

    frozen_one = acquire_source(
        source,
        cache_directory=tmp_path / "raw-cache",
        mode="frozen",
        transport=NoNetworkTransport(),
        page_size=2,
        request_interval_seconds=0,
    )
    frozen_two = acquire_source(
        source,
        cache_directory=tmp_path / "raw-cache",
        mode="frozen",
        transport=NoNetworkTransport(),
        page_size=2,
        request_interval_seconds=0,
    )
    assert frozen_one.as_public_dict() == frozen_two.as_public_dict()
    assert frozen_one.records == live.records
    public_json = json.dumps(frozen_one.as_public_dict(), sort_keys=True)
    assert str(tmp_path) not in public_json
    assert frozen_one.provenance["assurance"] == {
        "metadataOnly": True,
        "observationsFetched": False,
        "credentialsRequired": False,
        "cacheLocationPublished": False,
    }


def test_page_bound_is_reported_as_incomplete(tmp_path: Path) -> None:
    source = load_source_register(REGISTER)["ons-data-api"]

    def handler(url: str, params: dict[str, str]) -> HttpJsonResponse:
        return HttpJsonResponse(
            payload={
                "items": [{"id": "one", "title": "One"}],
                "total": 2,
            },
            final_url=f"{url}?limit={params['limit']}&offset={params['offset']}",
        )

    result = acquire_source(
        source,
        cache_directory=tmp_path / "cache",
        transport=FakeTransport(handler),
        page_size=1,
        maximum_pages=1,
        request_interval_seconds=0,
        retries=0,
        now=fixed_now,
    )
    assert result.provenance["complete"] is False
    assert result.provenance["coverageComplete"] is False
    assert result.provenance["stopReason"] == "maximumPages"
    assert result.provenance["recordCount"] == 1
    assert result.provenance["reportedTotal"] == 2


def test_normalisation_omission_is_explicit_not_hidden_as_complete(
    tmp_path: Path,
) -> None:
    source = load_source_register(REGISTER)["ons-data-api"]
    payload = {
        "items": [
            {"id": "represented", "title": "Represented"},
            {"id": "missing-title"},
        ],
        "total_count": 2,
    }
    result = acquire_source(
        source,
        cache_directory=tmp_path / "cache",
        transport=FakeTransport(
            lambda url, params: HttpJsonResponse(
                payload=payload,
                final_url=f"{url}?limit={params['limit']}&offset={params['offset']}",
            )
        ),
        page_size=2,
        request_interval_seconds=0,
        retries=0,
        now=fixed_now,
    )

    assert result.provenance["complete"] is True
    assert result.provenance["coverageComplete"] is False
    assert result.provenance["upstreamRecordsSeen"] == 2
    assert result.provenance["normalisedRecordsSeen"] == 1
    assert result.provenance["normalisationDroppedCount"] == 1
    assert result.provenance["unrepresentedCount"] == 1


def test_frozen_mode_fails_on_missing_page(tmp_path: Path) -> None:
    source = load_source_register(REGISTER)["ons-data-api"]

    with pytest.raises(SourceAcquisitionError, match="Frozen snapshot is incomplete"):
        acquire_source(
            source,
            cache_directory=tmp_path / "missing",
            mode="frozen",
            transport=NoNetworkTransport(),
            request_interval_seconds=0,
        )


def test_nomis_projection_preserves_sdmx_cross_references_not_values(
    tmp_path: Path,
) -> None:
    source = load_source_register(REGISTER)["nomis-dataset-definitions"]
    payload = {
        "structure": {
            "keyfamilies": {
                "keyfamily": [
                    {
                        "id": "NM_1_1",
                        "name": {"value": "Census population"},
                        "description": {"value": "The authoritative long description."},
                        "agencyid": "NOMIS",
                        "uri": "Nm-1d1",
                        "version": 1.0,
                        "annotations": {
                            "annotation": [
                                {
                                    "annotationtitle": "Status",
                                    "annotationtext": "Current",
                                },
                                {
                                    "annotationtitle": "SubDescription",
                                    "annotationtext": "Usual resident population.",
                                },
                                {
                                    "annotationtitle": "Keywords",
                                    "annotationtext": "Census, population",
                                },
                                {
                                    "annotationtitle": "Units",
                                    "annotationtext": "Persons",
                                },
                                {
                                    "annotationtitle": "LastUpdated",
                                    "annotationtext": "2026-07-17 08:00:00",
                                },
                            ]
                        },
                        "components": {
                            "dimension": [
                                {
                                    "conceptref": "GEOGRAPHY",
                                    "codelist": "CL_1_1_GEOGRAPHY",
                                },
                                {
                                    "conceptref": "SEX",
                                    "codelist": "CL_1_1_SEX",
                                },
                            ],
                            "primarymeasure": {"conceptref": "OBS_VALUE"},
                        },
                        "value": [100, 200],
                    }
                ]
            }
        },
        "dataset": {"value": [100, 200]},
    }

    transport = FakeTransport(lambda url, params: HttpJsonResponse(payload=payload, final_url=url))
    result = acquire_source(
        source,
        cache_directory=tmp_path / "cache",
        transport=transport,
        request_interval_seconds=0,
        retries=0,
        now=fixed_now,
    )

    assert len(result.records) == 1
    record = result.records[0]
    assert record["sourceRecordId"] == "NM_1_1"
    assert record["title"] == "Census population"
    assert record["description"] == "The authoritative long description."
    assert record["lifecycleState"] == "Current"
    assert record["keywords"] == ["Census", "population"]
    assert record["unitOfMeasure"] == "Persons"
    assert record["agencyId"] == "NOMIS"
    assert record["definitionVersion"] == "1.0"
    assert {item.get("codeList") for item in record["components"]} == {
        "CL_1_1_GEOGRAPHY",
        "CL_1_1_SEX",
        None,
    }
    public_json = json.dumps(result.as_public_dict())
    assert '"value": [100, 200]' not in public_json
    assert "OBS_VALUE" in public_json


def test_open_geography_projection_drops_feature_geometry(
    tmp_path: Path,
) -> None:
    source = load_source_register(REGISTER)["ons-open-geography"]
    payload = {
        "type": "FeatureCollection",
        "numberMatched": 1,
        "numberReturned": 1,
        "features": [
            {
                "type": "Feature",
                "id": "abc123",
                "bbox": [-5.8, 49.8, 1.8, 55.9],
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [1, 1], [0, 0]]],
                },
                "properties": {
                    "title": "Local Authority Districts (December 2025)",
                    "description": "<p>Boundaries for statistical reporting.</p>",
                    "type": "Feature Service",
                    "owner": "ONSGeography",
                    "created": 1760000000000,
                    "modified": 1761000000000,
                    "tags": ["LAD", "GSS"],
                    "typeKeywords": ["Data", "Boundary"],
                    "licenseInfo": "Open Government Licence",
                    "url": "https://example.maps.arcgis.com/example",
                },
                "links": [
                    {
                        "rel": "self",
                        "href": (
                            "https://geoportal.statistics.gov.uk/api/search/v1/"
                            "collections/dataset/items/abc123"
                        ),
                    }
                ],
            }
        ],
    }
    transport = FakeTransport(
        lambda url, params: HttpJsonResponse(
            payload=payload,
            final_url=f"{url}?limit={params['limit']}",
            headers={"Last-Modified": "Fri, 17 Jul 2026 12:00:00 GMT"},
        )
    )
    result = acquire_source(
        source,
        cache_directory=tmp_path / "cache",
        transport=transport,
        request_interval_seconds=0,
        retries=0,
        now=fixed_now,
    )

    assert len(result.records) == 1
    record = result.records[0]
    assert record["description"] == "Boundaries for statistical reporting."
    assert record["spatialEnvelope"] == [-5.8, 49.8, 1.8, 55.9]
    assert record["licence"] == "Open Government Licence"
    assert record["keywords"] == ["Boundary", "Data", "GSS", "LAD"]
    public_json = json.dumps(result.as_public_dict())
    assert "coordinates" not in public_json
    assert '"geometry"' not in public_json
    assert result.provenance["complete"] is True
    assert result.provenance["coverageComplete"] is True


def test_open_geography_follows_official_startindex_next_link(
    tmp_path: Path,
) -> None:
    source = load_source_register(REGISTER)["ons-open-geography"]
    next_url = f"{source.endpoint}?limit=1&startindex=2"

    def feature(record_id: str, title: str) -> dict[str, Any]:
        return {
            "type": "Feature",
            "id": record_id,
            "geometry": None,
            "properties": {"title": title},
        }

    def handler(url: str, params: dict[str, str]) -> HttpJsonResponse:
        if url == source.endpoint:
            assert params == {"limit": "1", "sortBy": "+properties.title"}
            return HttpJsonResponse(
                payload={
                    "type": "FeatureCollection",
                    "numberMatched": 2,
                    "numberReturned": 1,
                    "features": [feature("z", "Last alphabetically")],
                    "links": [{"rel": "next", "href": next_url}],
                },
                final_url=f"{source.endpoint}?limit=1",
            )
        assert url == next_url
        assert params == {}
        return HttpJsonResponse(
            payload={
                "type": "FeatureCollection",
                "numberMatched": 2,
                "numberReturned": 1,
                "features": [feature("a", "First alphabetically")],
                "links": [],
            },
            final_url=next_url,
        )

    transport = FakeTransport(handler)
    result = acquire_source(
        source,
        cache_directory=tmp_path / "cache",
        transport=transport,
        page_size=1,
        request_interval_seconds=0,
        retries=0,
        now=fixed_now,
    )

    assert len(transport.calls) == 2
    assert result.provenance["complete"] is True
    assert result.provenance["coverageComplete"] is True
    assert result.provenance["reportedTotal"] == 2
    assert [record["sourceRecordId"] for record in result.records] == ["a", "z"]
