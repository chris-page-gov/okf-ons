from __future__ import annotations

from okf_ons.search import search_tokenize


def test_static_search_tokenizer_matches_explorer_identifiers_and_terms() -> None:
    assert search_tokenize("NM_66_1 data for the UK") == ["nm_66_1", "data", "uk"]
    assert search_tokenize("Population.population -- population") == [
        "population.population",
        "population",
    ]
    assert search_tokenize("Café") == ["cafe"]
