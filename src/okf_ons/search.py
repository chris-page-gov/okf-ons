"""Build OKF Explorer's deterministic static-search contract."""

from __future__ import annotations

import heapq
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

RESULT_CHUNK_SIZE = 500
MAX_POSTINGS_PER_TOKEN = 5_000
MISSING_FILTER_VALUE = "__missing__"
SEARCH_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}

WEIGHTS = {
    "title": 20,
    "context": 9,
    "description": 6,
    "topics": 6,
    "statistical": 6,
    "geography_time": 5,
    "producers": 5,
    "record_type": 4,
    "source": 4,
    "standards": 3,
    "identifiers": 3,
}

FIELD_MASKS = {
    "title": 1,
    "context": 2,
    "description": 4,
    "topics": 8,
    "record_type": 16,
    "source": 32,
    "standards": 64,
    "identifiers": 128,
    "statistical": 256,
    "geography_time": 512,
    "producers": 1024,
}

FILTER_FIELDS = (
    "source_surface",
    "record_type",
    "topic",
    "state",
    "frequency",
    "population_type",
    "source_publisher",
    "subtopic",
    "unit_of_measure",
    "geography_level",
    "geography_vintage",
    "derivation_mode",
    "binding_status",
    "metadata_evidence_band",
    "has_methodology",
    "has_quality_documentation",
    "has_alternatives",
)


def search_tokenize(value: Any) -> list[str]:
    """Match the OKF Explorer worker tokenizer exactly."""

    normalised = "".join(
        character
        for character in unicodedata.normalize("NFKD", str(value or ""))
        if not unicodedata.combining(character)
    )
    found: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"[a-z0-9][a-z0-9._-]*", normalised.casefold()):
        token = match.group(0).strip("._-")
        if len(token) < 2 or token in SEARCH_STOP_WORDS or token in seen:
            continue
        found.append(token)
        seen.add(token)
    return found


def search_shard(value: str, length: int = 2) -> str:
    clean = re.sub(r"[^a-z0-9]", "", value.casefold())
    return clean[:length] or "_"


def chunk_rows(
    prefix: str,
    rows: list[dict[str, Any]],
    size: int = RESULT_CHUNK_SIZE,
) -> list[tuple[Path, list[dict[str, Any]]]]:
    if not rows:
        return [(Path(f"data/{prefix}-0.json"), [])]
    return [
        (Path(f"data/{prefix}-{index // size}.json"), rows[index : index + size])
        for index in range(0, len(rows), size)
    ]


def _band(score: float) -> str:
    if score >= 0.8:
        return "high"
    if score >= 0.55:
        return "medium"
    return "low"


def filter_values(record: dict[str, Any], key: str) -> list[str]:
    if key == "topic":
        values = record.get("topics") or []
    elif key == "metadata_evidence_band":
        values = [_band(float(record.get("quality_score") or 0))]
    elif key == "has_methodology":
        values = ["yes" if record.get("methodology_links") else "no"]
    elif key == "has_quality_documentation":
        values = ["yes" if record.get("quality_links") else "no"]
    elif key == "has_alternatives":
        values = ["yes" if record.get("alternatives") else "no"]
    elif key == "source_publisher":
        values = [
            publisher.get("name")
            for publisher in record.get("source_publishers", [])
            if isinstance(publisher, dict)
        ]
    elif key == "geography_level":
        geography = record.get("geography_metadata")
        values = geography.get("levels", []) if isinstance(geography, dict) else []
    elif key == "derivation_mode":
        derivation = record.get("metadata_derivation")
        if isinstance(derivation, dict):
            values = derivation.get("modes", [])
        else:
            values = []
    elif key == "binding_status":
        selection = record.get("selection")
        values = [selection.get("binding_status")] if isinstance(selection, dict) else []
    else:
        raw = record.get(key)
        values = raw if isinstance(raw, list) else [raw]
    return sorted({str(value) for value in values if value not in {None, ""}})


def result_document(record: dict[str, Any], ordinal: int) -> dict[str, Any]:
    return {
        "ordinal": ordinal,
        "record_id": record["id"],
        "name": record["name"],
        "title": record["title"],
        "publisher": record["publisher"],
        "publisher_title": record["publisher_title"],
        "resource_count": record.get("resource_count", 0),
        "formats": record.get("formats", []),
        "tags": record.get("tags", []),
        "record_type": record["record_type"],
        "source_tier": record.get("source_tier", ""),
        "source_adapter": record.get("source_adapter", ""),
        "confidence": record.get("confidence", ""),
        "dcat_type": record.get("dcat_type", ""),
        "source_surface": record["source_surface"],
        "native_id": record["native_id"],
        "canonical_record_id": record["id"],
        "evaluation_aliases": record.get("evaluation_aliases", []),
        "native_aliases": record.get("native_aliases", []),
        "notes": record.get("notes", "")[:2_000],
        "context_note": record.get("context_note", "")[:1_000],
        "topics": record.get("topics", []),
        "state": record.get("state", ""),
        "frequency": record.get("frequency", ""),
        "population_type": record.get("population_type", ""),
        "agency_id": record.get("agency_id", ""),
        "content_source": record.get("content_source", ""),
        "first_released": record.get("first_released", ""),
        "mnemonic": record.get("mnemonic", ""),
        "publisher_uri": record.get("publisher_uri", ""),
        "portal_owner": record.get("portal_owner", ""),
        "source_organisation": record.get("source_organisation", ""),
        "source_publishers": record.get("source_publishers", []),
        "surface_operator": record.get("surface_operator", {}),
        "authority": record.get("authority", {}),
        "assertion_provenance": record.get("assertion_provenance", {}),
        "metadata_modified": record.get("metadata_modified", ""),
        "timestamp": record.get("metadata_modified", ""),
        "quality_score": record.get("quality_score", 0),
        "quality_label": "metadata evidence availability",
        "statistical_accuracy_evaluated": False,
        "alternative_count": record.get("alternative_count", 0),
        "alternatives": record.get("alternatives", []),
        "standards_evidence": record.get("standards_evidence", {}),
        "selection": record.get("selection", {}),
        "measure": record.get("measure", ""),
        "unit_of_measure": record.get("unit_of_measure", ""),
        "subtopic": record.get("subtopic", ""),
        "dataset_family": record.get("dataset_family", ""),
        "geography": record.get("geography", []),
        "geography_metadata": record.get("geography_metadata", {}),
        "geography_vintage": record.get("geography_vintage", ""),
        "time_coverage": record.get("time_coverage", {}),
        "caveats": record.get("caveats", []),
        "statistical_flags": record.get("statistical_flags", {}),
        "metadata_derivation": record.get("metadata_derivation", {}),
        "license_id": record.get("license_id", ""),
        "license_title": record.get("license_title", ""),
        "license_source_id": record.get("license_source_id", ""),
        "documentation": record.get("documentation", ""),
        "protocol": record.get("protocol", []),
        "url": record.get("url", ""),
        "open": record["route"],
    }


def rank_records(
    records: list[dict[str, Any]],
    query: str,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return a deterministic in-process baseline using the static field weights."""

    if limit < 1:
        raise ValueError("limit must be positive")
    query_tokens = set(search_tokenize(query))
    if not query_tokens:
        return records[:limit]
    scored: list[tuple[int, int, str, str, dict[str, Any]]] = []
    for record in records:
        fields = {
            "title": record.get("title", ""),
            "context": record.get("context_note", ""),
            "description": record.get("notes", ""),
            "topics": " ".join(record.get("topics", []) + record.get("tags", [])),
            "statistical": " ".join(
                str(record.get(key, ""))
                for key in ("measure", "unit_of_measure", "frequency", "population_type")
            ),
            "geography_time": " ".join(
                str(record.get(key, ""))
                for key in ("geography", "geography_metadata", "geography_vintage", "time_coverage")
            ),
            "producers": " ".join(
                str(publisher.get("name", ""))
                for publisher in record.get("source_publishers", [])
                if isinstance(publisher, dict)
            ),
            "record_type": record.get("record_type", ""),
            "source": record.get("source_surface", ""),
            "standards": " ".join(record.get("standards_evidence", {})),
            "identifiers": " ".join(
                [
                    str(record.get("id", "")),
                    str(record.get("native_id", "")),
                    str(record.get("agency_id", "")),
                    str(record.get("content_source", "")),
                    str(record.get("mnemonic", "")),
                    str(record.get("publisher_uri", "")),
                    str(record.get("portal_owner", "")),
                    str(record.get("source_organisation", "")),
                    *[str(alias) for alias in record.get("evaluation_aliases", [])],
                    *[str(alias) for alias in record.get("native_aliases", [])],
                ]
            ),
        }
        score = 0
        matched: set[str] = set()
        for field, value in fields.items():
            field_tokens = set(search_tokenize(value))
            field_matches = query_tokens & field_tokens
            score += len(field_matches) * WEIGHTS[field]
            matched.update(field_matches)
        if not matched:
            continue
        scored.append(
            (
                len(matched),
                score,
                str(record.get("title", "")).casefold(),
                str(record.get("id", "")),
                record,
            )
        )
    scored.sort(key=lambda item: (-item[0], -item[1], item[2], item[3]))
    return [item[-1] for item in scored[:limit]]


def build_search(records: list[dict[str, Any]], *, snapshot_id: str) -> dict[str, Any]:
    docs = [result_document(record, ordinal) for ordinal, record in enumerate(records)]
    posting_heaps: dict[str, list[tuple[int, int, int, int]]] = defaultdict(list)
    document_frequency: Counter[str] = Counter()
    for doc in docs:
        fields = {
            "title": doc["title"],
            "context": doc["context_note"],
            "description": doc["notes"],
            "topics": " ".join(doc["topics"] + doc["tags"]),
            "statistical": " ".join(
                str(doc.get(key, ""))
                for key in ("measure", "unit_of_measure", "frequency", "population_type")
            ),
            "geography_time": " ".join(
                str(doc.get(key, ""))
                for key in ("geography", "geography_metadata", "geography_vintage", "time_coverage")
            ),
            "producers": " ".join(
                str(publisher.get("name", ""))
                for publisher in doc.get("source_publishers", [])
                if isinstance(publisher, dict)
            ),
            "record_type": doc["record_type"],
            "source": doc["source_surface"],
            "standards": " ".join(doc["standards_evidence"]),
            "identifiers": " ".join(
                [
                    str(doc["record_id"]),
                    str(doc["native_id"]),
                    str(doc["agency_id"]),
                    str(doc["content_source"]),
                    str(doc["mnemonic"]),
                    str(doc["publisher_uri"]),
                    str(doc["portal_owner"]),
                    str(doc["source_organisation"]),
                    *[str(alias) for alias in doc["evaluation_aliases"]],
                    *[str(alias) for alias in doc["native_aliases"]],
                ]
            ),
        }
        token_scores: dict[str, list[int]] = {}
        for field, value in fields.items():
            for token in search_tokenize(value):
                score, mask = token_scores.get(token, [0, 0])
                token_scores[token] = [score + WEIGHTS[field], mask | FIELD_MASKS[field]]
        for token, (score, mask) in token_scores.items():
            document_frequency[token] += 1
            heap = posting_heaps[token]
            item = (score, -doc["ordinal"], doc["ordinal"], mask)
            if len(heap) < MAX_POSTINGS_PER_TOKEN:
                heapq.heappush(heap, item)
            elif item[:2] > heap[0][:2]:
                heapq.heapreplace(heap, item)

    postings_by_path: dict[str, dict[str, list[list[int]]]] = defaultdict(dict)
    lexicon_rows: list[dict[str, Any]] = []
    for token, heap in sorted(posting_heaps.items()):
        path = f"data/search/postings/{search_shard(token)}.json"
        ranked = sorted(heap, key=lambda item: (-item[0], item[2]))
        postings_by_path[path][token] = [
            [ordinal, score, mask] for score, _negative_ordinal, ordinal, mask in ranked
        ]
        lexicon_rows.append({"token": token, "df": document_frequency[token], "postings": path})

    lexicon: dict[str, list[dict[str, Any]]] = defaultdict(list)
    prefixes: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in lexicon_rows:
        token = row["token"]
        shard = search_shard(token)
        lexicon[shard].append(row)
        for length in range(3, min(8, len(token)) + 1):
            prefix = token[:length]
            prefixes[search_shard(prefix)][prefix].append({"token": token, "df": row["df"]})
    for payload in prefixes.values():
        for prefix, rows in payload.items():
            payload[prefix] = sorted(rows, key=lambda item: (-item["df"], item["token"]))[:16]

    filter_payloads: dict[str, dict[str, Any]] = {}
    facets: dict[str, list[dict[str, Any]]] = {}
    filter_entrypoints: dict[str, str] = {}
    for key in FILTER_FIELDS:
        values: dict[str, list[int]] = defaultdict(list)
        for ordinal, record in enumerate(records):
            record_values = filter_values(record, key) or [MISSING_FILTER_VALUE]
            for value in record_values:
                values[value].append(ordinal)
        path = f"data/search/filters/{key}.json"
        filter_entrypoints[key] = path
        filter_payloads[path] = {
            "schema": "okf-static-filter-postings.v1",
            "key": key,
            "values": dict(sorted(values.items())),
        }
        facets[key] = [
            {"value": value, "label": value, "count": len(ordinals)}
            for value, ordinals in sorted(
                values.items(),
                key=lambda item: (-len(item[1]), item[0]),
            )
            if value != MISSING_FILTER_VALUE
        ]

    result_chunks = chunk_rows("search/results", docs)
    manifest = {
        "schema": "okf-static-search.v2",
        "snapshot": snapshot_id,
        "token_min_length": 2,
        "prefix_min_length": 3,
        "lexicon_shard_length": 2,
        "result_limit": 200,
        "result_doc_chunk_size": RESULT_CHUNK_SIZE,
        "weights": WEIGHTS,
        "field_masks": FIELD_MASKS,
        "counts": {
            "documents": len(docs),
            "tokens": len(lexicon_rows),
            "postings": sum(
                len(rows) for payload in postings_by_path.values() for rows in payload.values()
            ),
            "uncapped_postings": sum(document_frequency.values()),
            "max_postings_per_token": MAX_POSTINGS_PER_TOKEN,
        },
        "entrypoints": {
            "lexicon": {shard: f"data/search/lexicon/{shard}.json" for shard in sorted(lexicon)},
            "prefixes": {shard: f"data/search/prefixes/{shard}.json" for shard in sorted(prefixes)},
            "postings": sorted(postings_by_path),
            "result_docs": [path.as_posix() for path, _rows in result_chunks],
            "facets": "data/facets.json",
            "doc_map": "data/search/doc-map.json",
            "filter_postings": filter_entrypoints,
            "sort_values": "data/search/sort-values.json",
        },
    }
    return {
        "manifest": manifest,
        "lexicon": dict(sorted(lexicon.items())),
        "prefixes": {
            shard: dict(sorted(payload.items())) for shard, payload in sorted(prefixes.items())
        },
        "postings": {
            path: {"tokens": dict(sorted(payload.items()))}
            for path, payload in sorted(postings_by_path.items())
        },
        "result_chunks": result_chunks,
        "doc_map": {str(doc["ordinal"]): doc["open"] for doc in docs},
        "filter_payloads": filter_payloads,
        "sort_values": [
            [
                str(record.get("metadata_modified") or ""),
                record["title"],
                record.get("quality_score", 0),
            ]
            for record in records
        ],
        "facets": facets,
    }
