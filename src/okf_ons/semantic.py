"""Compile ONS discovery relationships into evidence-bearing semantic assertions.

The source adapters deliberately emit narrow relationship observations.  This
module is the one normalisation boundary that assigns semantic identity,
authority, provenance and rights before the same assertions are projected to
the Explorer runtime and the YAML-LD/JSON-LD graph.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import urlsplit

RDF_STATEMENT = "http://www.w3.org/1999/02/22-rdf-syntax-ns#Statement"
RELATIONSHIP_ASSERTION = (
    "https://chris-page-gov.github.io/okf-explorer/ns#RelationshipAssertion"
)


class SemanticRelationshipError(ValueError):
    """Raised when a relationship cannot be projected without guessing."""


RELATIONSHIP_TYPES: dict[str, dict[str, str]] = {
    "alternative": {
        "predicate": "vocab/discoveryAlternative",
        "label": "discovery alternative to",
        "inverse_label": "discovery alternative to",
        "assertion_status": "inferred",
        "derivation": "rules/deterministic-title-topic-similarity-v1",
    },
    "cross-source-alternative": {
        "predicate": "vocab/crossSourceDiscoveryAlternative",
        "label": "cross-source discovery alternative to",
        "inverse_label": "cross-source discovery alternative to",
        "assertion_status": "inferred",
        "derivation": "rules/deterministic-title-topic-similarity-v1",
    },
    "cross-source-representation": {
        "predicate": "vocab/crossSourceRepresentation",
        "label": "cross-source representation of",
        "inverse_label": "has cross-source representation",
        "assertion_status": "normalized",
        "derivation": "rules/shared-declared-table-code-v1",
    },
}


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _absolute_iri(value: Any, context: str) -> str:
    text = str(value or "").strip()
    split = urlsplit(text)
    if not split.scheme or (split.scheme in {"http", "https"} and not split.netloc):
        raise SemanticRelationshipError(f"{context} must be an absolute IRI")
    if any(character.isspace() for character in text):
        raise SemanticRelationshipError(f"{context} must not contain whitespace")
    return text


def _route(value: Any, context: str) -> str:
    text = str(value or "").strip().strip("/")
    split = urlsplit(text)
    if (
        not text
        or split.scheme
        or split.netloc
        or split.query
        or split.fragment
        or any(part in {"", ".", ".."} for part in text.split("/"))
        or text.endswith((".md", ".html"))
    ):
        raise SemanticRelationshipError(f"{context} is not a safe local route: {value!r}")
    return text


def _evidence_time(record: Mapping[str, Any], generated_at: str) -> tuple[str, str]:
    provenance = record.get("provenance")
    provenance = provenance if isinstance(provenance, Mapping) else {}
    for field in ("retrieved_at", "source_commit_as_of", "source_as_of"):
        value = str(provenance.get(field) or "").strip()
        if value:
            return value, f"provenance.{field}"
    return generated_at, "bundle-publication-generated-at; source retrieval not evidenced"


def _record_evidence(
    record: Mapping[str, Any],
    *,
    assertion_id: str,
    side: str,
    source_field: str,
    source_value: Any,
    generated_at: str,
    public_root: str,
) -> dict[str, Any]:
    provenance = record.get("provenance")
    provenance = provenance if isinstance(provenance, Mapping) else {}
    evidence_time, evidence_time_basis = _evidence_time(record, generated_at)
    source_url = str(provenance.get("source_url") or "").strip()
    if not source_url:
        source_url = public_root + "data/governance/release.json"
    source_url = _absolute_iri(source_url, f"{side} evidence URL")
    record_url = str(record.get("url") or "").strip()
    evidence: dict[str, Any] = {
        "@id": f"{assertion_id}/evidence/{side}",
        "type": "frozen-source-metadata",
        "url": source_url,
        "source_artifact": str(provenance.get("source_id") or "frozen-source-record"),
        "source_field": source_field,
        "field_provenance": "frozen source metadata normalised by the declared adapter",
        "source_value_sha256": _canonical_sha256(source_value),
        "source_value_hash_canonicalization": "canonical-json-sort-keys-utf8-sha256",
        "locator": f"record:{record.get('id')}",
        "retrieved_at": evidence_time,
        "retrieved_at_basis": evidence_time_basis,
    }
    if record_url:
        evidence["resource"] = _absolute_iri(record_url, f"{side} evidence resource")
    source_sha256 = str(provenance.get("source_sha256") or "").strip().casefold()
    if len(source_sha256) == 64 and all(c in "0123456789abcdef" for c in source_sha256):
        evidence["source_sha256"] = source_sha256
    return evidence


def _record_rights(record: Mapping[str, Any], public_root: str) -> dict[str, str]:
    status = str(record.get("rights_status") or record.get("license_id") or "not-evaluated")
    source = str(record.get("license_source_id") or "").strip()
    if not source:
        source = public_root + "data/governance/release.json"
    return {
        "status": status,
        "license_id": str(record.get("license_id") or "not-evaluated"),
        "source": _absolute_iri(source, "record rights source"),
    }


def compile_relationships(
    source_relationships: Iterable[Mapping[str, Any]],
    records: Iterable[Mapping[str, Any]],
    *,
    generated_at: str,
    snapshot_id: str,
    public_root: str,
    authority_source: str,
) -> list[dict[str, Any]]:
    """Return runtime rows carrying the full semantic assertion contract."""

    if not generated_at:
        raise SemanticRelationshipError("generated_at must be provided")
    root = _absolute_iri(public_root, "public_root")
    if not root.endswith("/"):
        root += "/"
    authority_source = _absolute_iri(authority_source, "authority_source")
    records_by_route: dict[str, Mapping[str, Any]] = {}
    for record in records:
        route = _route(record.get("route"), "record route")
        if route in records_by_route:
            raise SemanticRelationshipError(f"duplicate record route: {route}")
        records_by_route[route] = record

    activity_id = root + "activity/relationship-projection-" + _canonical_sha256(
        {"snapshot_id": snapshot_id, "generated_at": generated_at}
    )[:24]
    compiled: list[dict[str, Any]] = []
    seen_assertions: set[str] = set()
    seen_triples: set[tuple[str, str, str]] = set()
    for source_relationship in source_relationships:
        source_route = _route(source_relationship.get("source"), "relationship source")
        target_route = _route(source_relationship.get("target"), "relationship target")
        source_record = records_by_route.get(source_route)
        target_record = records_by_route.get(target_route)
        if source_record is None or target_record is None:
            raise SemanticRelationshipError(
                f"relationship endpoints are not both registered: {source_route} -> {target_route}"
            )
        kind = str(source_relationship.get("kind") or "").strip()
        relationship_type = RELATIONSHIP_TYPES.get(kind)
        if relationship_type is None:
            raise SemanticRelationshipError(f"unregistered relationship kind: {kind}")

        source_iri = root + source_route
        target_iri = root + target_route
        predicate = root + relationship_type["predicate"]
        triple = (source_iri, predicate, target_iri)
        if triple in seen_triples:
            raise SemanticRelationshipError(f"duplicate semantic triple: {triple}")
        seen_triples.add(triple)
        assertion_id = root + "assertion/" + _canonical_sha256(
            {"source": source_iri, "predicate": predicate, "target": target_iri}
        )
        if assertion_id in seen_assertions:
            raise SemanticRelationshipError(f"duplicate assertion identity: {assertion_id}")
        seen_assertions.add(assertion_id)

        is_similarity = kind in {"alternative", "cross-source-alternative"}
        if is_similarity:
            source_field = "title,topics,tags"
            source_value = {
                "title": source_record.get("title"),
                "topics": source_record.get("topics") or [],
                "tags": source_record.get("tags") or [],
            }
            target_value = {
                "title": target_record.get("title"),
                "topics": target_record.get("topics") or [],
                "tags": target_record.get("tags") or [],
            }
        else:
            source_field = "declared_table_codes"
            source_value = [source_relationship.get("shared_code")]
            target_value = source_value

        evidence = [
            _record_evidence(
                source_record,
                assertion_id=assertion_id,
                side="source",
                source_field=source_field,
                source_value=source_value,
                generated_at=generated_at,
                public_root=root,
            ),
            _record_evidence(
                target_record,
                assertion_id=assertion_id,
                side="target",
                source_field=source_field,
                source_value=target_value,
                generated_at=generated_at,
                public_root=root,
            ),
        ]
        assertion: dict[str, Any] = {
            **dict(source_relationship),
            "schema": "okf-relationship-assertion.v2",
            "id": assertion_id,
            "@id": assertion_id,
            "@type": [RDF_STATEMENT, RELATIONSHIP_ASSERTION],
            "source": source_route,
            "target": target_route,
            "source_iri": source_iri,
            "target_iri": target_iri,
            "predicate": predicate,
            "label": relationship_type["label"],
            "inverse_label": relationship_type["inverse_label"],
            "assertion_status": relationship_type["assertion_status"],
            "assertion_scope": "real-world",
            "authority": {
                "class": "derived",
                "label": (
                    "OKF ONS deterministic discovery-similarity projection"
                    if is_similarity
                    else "OKF ONS deterministic cross-source reconciliation"
                ),
                "source": authority_source,
            },
            "derivation": root + relationship_type["derivation"],
            "derivation_activity": activity_id,
            "observed_at": generated_at,
            "evidence": evidence,
            "rights": {
                "source": root + "data/governance/release.json",
                "assertion": "mixed-record-level-source-derived-metadata",
                "source_record": _record_rights(source_record, root),
                "target_record": _record_rights(target_record, root),
            },
        }
        if is_similarity:
            score = float(source_relationship.get("score") or 0.0)
            if not 0.0 <= score <= 1.0:
                raise SemanticRelationshipError("similarity score must be between zero and one")
            assertion.update(
                {
                    "rule": assertion["derivation"],
                    "supporting_assertions": [item["@id"] for item in evidence],
                    "confidence_score": score,
                    "review_status": "deterministic-discovery-inference-not-source-reviewed",
                    "discovery_only": True,
                    "statistical_equivalence_asserted": False,
                }
            )
        compiled.append(assertion)

    return sorted(
        compiled,
        key=lambda row: (str(row["source"]), str(row["target"]), str(row["predicate"])),
    )


def semantic_assertion(runtime_assertion: Mapping[str, Any]) -> dict[str, Any]:
    """Project a route-bearing runtime row to an RDF statement node."""

    assertion = dict(runtime_assertion)
    assertion["source_route"] = assertion["source"]
    assertion["target_route"] = assertion["target"]
    assertion["source"] = assertion.pop("source_iri")
    assertion["target"] = assertion.pop("target_iri")
    assertion.pop("id", None)
    return assertion


def add_direct_triples(
    entity_nodes: Iterable[dict[str, Any]],
    relationships: Iterable[Mapping[str, Any]],
) -> None:
    """Mutate entity nodes with direct triples matching every assertion."""

    nodes_by_id = {str(node.get("@id") or ""): node for node in entity_nodes}
    targets_by_subject: dict[tuple[str, str], set[str]] = defaultdict(set)
    for relationship in relationships:
        source = _absolute_iri(relationship.get("source_iri"), "relationship source IRI")
        predicate = _absolute_iri(relationship.get("predicate"), "relationship predicate")
        target = _absolute_iri(relationship.get("target_iri"), "relationship target IRI")
        if source not in nodes_by_id or target not in nodes_by_id:
            raise SemanticRelationshipError("direct triple endpoint has no semantic entity node")
        targets_by_subject[(source, predicate)].add(target)
    for (source, predicate), targets in sorted(targets_by_subject.items()):
        nodes_by_id[source][predicate] = [{"@id": target} for target in sorted(targets)]


def validate_semantic_projection(
    entity_nodes: Iterable[Mapping[str, Any]],
    runtime_relationships: Iterable[Mapping[str, Any]],
    assertion_nodes: Iterable[Mapping[str, Any]],
) -> None:
    """Fail closed unless runtime rows, direct triples and reification agree."""

    entities = list(entity_nodes)
    runtime = list(runtime_relationships)
    assertions = list(assertion_nodes)
    if len(runtime) != len(assertions):
        raise SemanticRelationshipError("runtime and semantic assertion counts differ")
    direct = {
        (str(node.get("@id") or ""), predicate, str(target.get("@id") or ""))
        for node in entities
        for predicate, targets in node.items()
        if isinstance(predicate, str) and predicate.startswith(("http://", "https://"))
        and isinstance(targets, list)
        for target in targets
        if isinstance(target, Mapping) and target.get("@id")
    }
    runtime_triples = {
        (str(row["source_iri"]), str(row["predicate"]), str(row["target_iri"]))
        for row in runtime
    }
    assertion_triples = {
        (str(row["source"]), str(row["predicate"]), str(row["target"]))
        for row in assertions
    }
    if len(runtime_triples) != len(runtime):
        raise SemanticRelationshipError("runtime relationship triples are not unique")
    if runtime_triples != assertion_triples:
        raise SemanticRelationshipError("runtime and reified assertion triples differ")
    if runtime_triples != direct:
        raise SemanticRelationshipError("direct and reified semantic triples differ")
