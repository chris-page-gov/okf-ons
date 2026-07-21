from __future__ import annotations

from okf_ons.search import build_search, filter_values, rank_records, search_tokenize


def test_static_search_tokenizer_matches_explorer_identifiers_and_terms() -> None:
    assert search_tokenize("NM_66_1 data for the UK") == ["nm_66_1", "data", "uk"]
    assert search_tokenize("Population.population -- population") == [
        "population.population",
        "population",
    ]
    assert search_tokenize("Café") == ["cafe"]


def test_statistical_producer_and_geography_fields_are_searchable_and_filterable() -> None:
    records = [
        {
            "id": "els:4g",
            "title": "Mobile coverage",
            "source_surface": "ons-explore-local-statistics",
            "record_type": "indicator",
            "source_publishers": [{"name": "Ofcom"}],
            "measure": "Percentage of premises",
            "unit_of_measure": "%",
            "geography": ["ltla"],
            "geography_metadata": {"levels": ["ltla"], "vintage": 2025},
            "geography_vintage": 2025,
            "time_coverage": {"start": "2025", "end": "2025"},
            "metadata_derivation": {
                "modes": ["inferred-from-observation-structure-without-publishing-observations"]
            },
        },
        {
            "id": "other",
            "title": "Mobile coverage",
            "source_surface": "other",
            "record_type": "dataset",
        },
    ]

    assert rank_records(records, "Ofcom percentage 2025", limit=1)[0]["id"] == "els:4g"
    assert filter_values(records[0], "source_publisher") == ["Ofcom"]
    assert filter_values(records[0], "geography_level") == ["ltla"]
    assert filter_values(records[0], "geography_vintage") == ["2025"]
    assert filter_values(records[0], "derivation_mode") == [
        "inferred-from-observation-structure-without-publishing-observations"
    ]


def test_native_aliases_are_kept_in_result_documents_and_search_postings() -> None:
    record = {
        "id": "els:indicator:current",
        "name": "current",
        "title": "Current indicator title",
        "publisher": "source-producer",
        "publisher_title": "Source producer",
        "record_type": "indicator",
        "source_surface": "ons-explore-local-statistics",
        "native_id": "current",
        "route": "dataset/current",
        "native_aliases": ["historical-indicator-slug"],
    }
    assert rank_records([record], "historical-indicator-slug", limit=1)[0]["id"] == record["id"]

    search = build_search([record], snapshot_id="test-snapshot")
    result = search["result_chunks"][0][1][0]
    assert result["native_aliases"] == ["historical-indicator-slug"]
    postings = search["postings"]["data/search/postings/hi.json"]["tokens"]
    assert postings["historical-indicator-slug"][0][0] == 0
