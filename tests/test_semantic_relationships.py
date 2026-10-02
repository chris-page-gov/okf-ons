from __future__ import annotations

import pytest

from okf_ons.semantic import (
    RELATIONSHIP_ASSERTION,
    SemanticRelationshipError,
    add_direct_triples,
    compile_relationships,
    semantic_assertion,
    validate_semantic_projection,
)

PUBLIC_ROOT = "https://example.org/okf-ons/"


def _record(record_id: str, route: str, *, retrieved_at: str = "") -> dict:
    source_as_of = retrieved_at or "2026-07-17T08:35:03Z"
    return {
        "id": record_id,
        "route": route,
        "title": record_id,
        "topics": ["population"],
        "tags": ["census"],
        "url": f"https://example.org/source/{record_id}",
        "license_id": "not-evaluated" if not retrieved_at else "open-government-licence-v3",
        "license_source_id": (
            "" if not retrieved_at else "https://example.org/source/rights"
        ),
        "rights_status": "not-evaluated" if not retrieved_at else "declared",
        "provenance": {
            "source_id": f"source-{record_id}",
            "source_url": f"https://example.org/catalogue/{record_id}",
            "source_sha256": "a" * 64,
            "retrieved_at": retrieved_at,
            "source_commit_as_of": source_as_of if not retrieved_at else "",
        },
    }


def test_similarity_is_a_rich_inferred_discovery_assertion() -> None:
    records = [
        _record("left", "dataset/left", retrieved_at="2026-07-17T10:00:00Z"),
        _record("right", "dataset/right"),
    ]
    relationships = compile_relationships(
        [
            {
                "source": "dataset/left",
                "target": "dataset/right",
                "kind": "alternative",
                "score": 0.75,
                "shared_terms": ["population"],
                "differences": [],
                "statistical_equivalence_asserted": False,
            }
        ],
        records,
        generated_at="2026-07-25T11:08:21Z",
        snapshot_id="fixture-snapshot",
        public_root=PUBLIC_ROOT,
        authority_source="https://github.com/example/okf-ons",
    )

    assertion = relationships[0]
    assert assertion["id"].startswith(PUBLIC_ROOT + "assertion/")
    assert assertion["source"] == "dataset/left"
    assert assertion["target"] == "dataset/right"
    assert assertion["source_iri"] == PUBLIC_ROOT + "dataset/left"
    assert assertion["target_iri"] == PUBLIC_ROOT + "dataset/right"
    assert assertion["predicate"] == PUBLIC_ROOT + "vocab/discoveryAlternative"
    assert assertion["assertion_status"] == "inferred"
    assert assertion["authority"]["class"] == "derived"
    assert assertion["discovery_only"] is True
    assert assertion["statistical_equivalence_asserted"] is False
    assert assertion["confidence_score"] == 0.75
    assert assertion["supporting_assertions"] == [
        evidence["@id"] for evidence in assertion["evidence"]
    ]
    assert assertion["evidence"][0]["retrieved_at_basis"] == (
        "provenance.retrieved_at"
    )
    assert assertion["evidence"][1]["retrieved_at_basis"] == (
        "provenance.source_commit_as_of"
    )
    assert assertion["rights"]["target_record"]["status"] == "not-evaluated"

    entity_nodes = [
        {"@id": PUBLIC_ROOT + "dataset/left", "route": "dataset/left"},
        {"@id": PUBLIC_ROOT + "dataset/right", "route": "dataset/right"},
    ]
    add_direct_triples(entity_nodes, relationships)
    semantic_assertions = [semantic_assertion(assertion)]
    validate_semantic_projection(entity_nodes, relationships, semantic_assertions)
    semantic = semantic_assertions[0]
    assert RELATIONSHIP_ASSERTION in semantic["@type"]
    assert semantic["source"] == PUBLIC_ROOT + "dataset/left"
    assert semantic["source_route"] == "dataset/left"
    assert entity_nodes[0][assertion["predicate"]] == [
        {"@id": PUBLIC_ROOT + "dataset/right"}
    ]


def test_declared_table_code_is_normalized_without_equivalence_claim() -> None:
    records = [_record("left", "dataset/left"), _record("right", "dataset/right")]
    relationship = compile_relationships(
        [
            {
                "source": "dataset/left",
                "target": "dataset/right",
                "kind": "cross-source-representation",
                "shared_code": "RM001",
                "statistical_equivalence_asserted": False,
            }
        ],
        records,
        generated_at="2026-07-25T11:08:21Z",
        snapshot_id="fixture-snapshot",
        public_root=PUBLIC_ROOT,
        authority_source="https://github.com/example/okf-ons",
    )[0]

    assert relationship["assertion_status"] == "normalized"
    assert relationship["predicate"].endswith("/vocab/crossSourceRepresentation")
    assert relationship["statistical_equivalence_asserted"] is False
    assert "confidence_score" not in relationship
    assert all(
        evidence["source_field"] == "declared_table_codes"
        for evidence in relationship["evidence"]
    )


def test_relationship_projection_fails_closed_for_unknown_routes() -> None:
    with pytest.raises(SemanticRelationshipError, match="not both registered"):
        compile_relationships(
            [{"source": "dataset/left", "target": "dataset/missing", "kind": "alternative"}],
            [_record("left", "dataset/left")],
            generated_at="2026-07-25T11:08:21Z",
            snapshot_id="fixture-snapshot",
            public_root=PUBLIC_ROOT,
            authority_source="https://github.com/example/okf-ons",
        )
