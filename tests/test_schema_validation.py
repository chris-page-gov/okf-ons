from __future__ import annotations

import copy
import gzip
import hashlib
from pathlib import Path

import pytest

from okf_ons.build import deterministic_gzip
from okf_ons.schema_validation import (
    SHARED_SCHEMA_METADATA_SHA256,
    SHARED_SCHEMA_SHA256,
    SemanticSchemaError,
    load_pinned_schema,
    validate_assertions,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "semantic-assertion.schema.json"
METADATA = ROOT / "schemas" / "semantic-assertion.schema.metadata.json"


def _assertion() -> dict:
    assertion_id = "https://example.test/assertion/1"
    return {
        "@id": assertion_id,
        "@type": [
            "http://www.w3.org/1999/02/22-rdf-syntax-ns#Statement",
            "https://chris-page-gov.github.io/okf-explorer/ns#RelationshipAssertion",
        ],
        "source": "https://example.test/entity/source",
        "predicate": "https://example.test/vocab/relatedTo",
        "target": "https://example.test/entity/target",
        "kind": "cross-source-representation",
        "label": "is represented by",
        "inverse_label": "represents",
        "assertion_status": "normalized",
        "assertion_scope": "real-world",
        "authority": {
            "class": "derived",
            "label": "Deterministic test normalization",
            "source": "https://example.test/rules/normalization",
        },
        "derivation": "https://example.test/rules/normalization",
        "observed_at": "2026-08-09T12:00:00Z",
        "evidence": [
            {
                "@id": f"{assertion_id}/evidence/1",
                "type": "frozen-source-metadata",
                "url": "https://example.test/source.json",
                "source_field": "declared_code",
                "source_value_sha256": "a" * 64,
                "retrieved_at": "2026-08-09T12:00:00Z",
            }
        ],
        "rights": {
            "source": "https://example.test/rights",
            "assertion": "source-derived metadata",
        },
    }


def test_vendored_schema_is_digest_pinned_and_validates_both_planes() -> None:
    _, provenance = load_pinned_schema(SCHEMA, METADATA)
    assert provenance["sha256"] == SHARED_SCHEMA_SHA256
    assert provenance["metadataSha256"] == SHARED_SCHEMA_METADATA_SHA256
    assertion = _assertion()
    report = validate_assertions(
        [assertion],
        [copy.deepcopy(assertion)],
        schema_path=SCHEMA,
        metadata_path=METADATA,
    )
    assert report["status"] == "conformant"
    assert report["counts"] == {
        "semanticAssertionsValidated": 1,
        "runtimeRowsMappedAndValidated": 1,
        "validationFailures": 0,
    }


@pytest.mark.parametrize(
    "mutate",
    [
        lambda row: row.pop("evidence"),
        lambda row: row.pop("label"),
        lambda row: row["authority"].update({"class": "official"}),
        lambda row: row.update({"observed_at": "not-a-date"}),
        lambda row: row["evidence"][0].update({"source_value_sha256": "not-a-digest"}),
    ],
)
def test_schema_validation_rejects_nonconforming_assertions(mutate) -> None:
    assertion = _assertion()
    mutate(assertion)
    with pytest.raises(SemanticSchemaError, match="failed the pinned schema"):
        validate_assertions(
            [assertion],
            [copy.deepcopy(assertion)],
            schema_path=SCHEMA,
            metadata_path=METADATA,
        )


def test_inferred_assertion_requires_derivation_evidence_fields() -> None:
    assertion = _assertion()
    assertion["assertion_status"] = "inferred"
    with pytest.raises(SemanticSchemaError, match="supporting_assertions"):
        validate_assertions(
            [assertion],
            [copy.deepcopy(assertion)],
            schema_path=SCHEMA,
            metadata_path=METADATA,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("authority", "javascript:alert(1)"),
        ("authority", "https://user:pass@example.test/rules"),
        ("authority", "https:///missing-host"),
        ("authority", "https://example.test:0/rules"),
        ("authority", "https://example.test:65536/rules"),
        ("evidence-url", "https://example.test/bad%escape"),
        ("evidence-resource", "https://example.test/a<bad>"),
        ("rights", "https://example.test/path with space"),
    ],
)
def test_schema_validation_rejects_noncanonical_web_urls(field: str, value: str) -> None:
    assertion = _assertion()
    if field == "authority":
        assertion["authority"]["source"] = value
    elif field == "evidence-url":
        assertion["evidence"][0]["url"] = value
    elif field == "evidence-resource":
        assertion["evidence"][0]["resource"] = value
    else:
        assertion["rights"]["source"] = value
    with pytest.raises(SemanticSchemaError, match="failed the pinned schema"):
        validate_assertions(
            [assertion],
            [copy.deepcopy(assertion)],
            schema_path=SCHEMA,
            metadata_path=METADATA,
        )


def test_schema_validation_accepts_boundary_port_and_ipv6_web_urls() -> None:
    assertion = _assertion()
    assertion["authority"]["source"] = "https://example.test:65535/rules"
    assertion["rights"]["source"] = "http://[2001:db8::1]:1/rights"
    report = validate_assertions(
        [assertion],
        [copy.deepcopy(assertion)],
        schema_path=SCHEMA,
        metadata_path=METADATA,
    )
    assert report["status"] == "conformant"


def test_schema_and_metadata_byte_changes_fail_the_pins(tmp_path: Path) -> None:
    changed_schema = tmp_path / "schema.json"
    changed_schema.write_bytes(SCHEMA.read_bytes() + b"\n")
    with pytest.raises(SemanticSchemaError, match="schema digest"):
        load_pinned_schema(changed_schema, METADATA)

    changed_metadata = tmp_path / "metadata.json"
    changed_metadata.write_bytes(METADATA.read_bytes() + b"\n")
    with pytest.raises(SemanticSchemaError, match="metadata digest"):
        load_pinned_schema(SCHEMA, changed_metadata)


def test_deterministic_gzip_has_canonical_rfc1952_header_and_bytes() -> None:
    compressed = deterministic_gzip(b"hello")
    assert compressed.hex() == "1f8b08000000000002ffcb48cdc9c9070086a6103605000000"
    assert hashlib.sha256(compressed).hexdigest() == (
        "3223ab15154bd181c783e5b434b108c68f5798bf10be7eb681faba9b6668bc65"
    )
    assert compressed[4:8] == b"\x00\x00\x00\x00"
    assert compressed[9] == 255
    assert gzip.decompress(compressed) == b"hello"
