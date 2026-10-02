"""Offline validation for the pinned Explorer semantic-assertion schema.

The producer intentionally has no runtime package dependencies.  This module
implements every validation keyword used by the exact vendored Draft 2020-12
schema and rejects a schema that introduces an unsupported keyword.  That
keeps bundle builds offline, locked and fail-closed without resolving the
schema's public identifier over the network.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

SHARED_SCHEMA_ID = (
    "https://chris-page-gov.github.io/okf-explorer/profile/"
    "bundle-wiki/v1/semantic-assertion.schema.json"
)
SHARED_SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"
SHARED_SCHEMA_SHA256 = "f69480328db4b64d678d9c50b6534d808000f7fb50a30e8cc9e3bf2facbcb8bc"
SHARED_SCHEMA_METADATA_SHA256 = (
    "0f909037d8691fd08413d15bff5f74fe5c2f69f93f13aa51bd4f50972669a89c"
)
VALIDATOR_ID = "okf-ons.offline-draft-2020-12-schema-validator.v1"

_VALIDATION_KEYWORDS = {
    "$defs",
    "$id",
    "$ref",
    "$schema",
    "additionalProperties",
    "allOf",
    "const",
    "enum",
    "format",
    "if",
    "items",
    "maximum",
    "minimum",
    "minItems",
    "minLength",
    "oneOf",
    "pattern",
    "properties",
    "required",
    "then",
    "title",
    "type",
    "uniqueItems",
}


class SemanticSchemaError(ValueError):
    """Raised when the pinned schema or an assertion does not conform."""


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _load_object(path: Path, description: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise SemanticSchemaError(f"unable to read {description}: {path}") from exc
    if not isinstance(value, dict):
        raise SemanticSchemaError(f"{description} must be a JSON object: {path}")
    return value, raw


def _check_supported_schema(schema: Mapping[str, Any], path: str = "$") -> None:
    unsupported = sorted(set(schema) - _VALIDATION_KEYWORDS)
    if unsupported:
        raise SemanticSchemaError(
            f"{path} uses unsupported schema keyword(s): {', '.join(unsupported)}"
        )
    properties = schema.get("properties")
    if isinstance(properties, Mapping):
        for name, child in properties.items():
            if isinstance(child, Mapping):
                _check_supported_schema(child, f"{path}.properties[{name!r}]")
    definitions = schema.get("$defs")
    if isinstance(definitions, Mapping):
        for name, child in definitions.items():
            if isinstance(child, Mapping):
                _check_supported_schema(child, f"{path}.$defs[{name!r}]")
    for keyword in ("items", "if", "then", "additionalProperties"):
        child = schema.get(keyword)
        if isinstance(child, Mapping):
            _check_supported_schema(child, f"{path}.{keyword}")
    for keyword in ("allOf", "oneOf"):
        children = schema.get(keyword)
        if isinstance(children, list):
            for index, child in enumerate(children):
                if isinstance(child, Mapping):
                    _check_supported_schema(child, f"{path}.{keyword}[{index}]")


def load_pinned_schema(
    schema_path: Path,
    metadata_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load and integrity-check the local schema and its provenance metadata."""

    schema, schema_bytes = _load_object(schema_path, "semantic assertion schema")
    metadata, metadata_bytes = _load_object(metadata_path, "schema metadata")
    digest = _sha256(schema_bytes)
    metadata_digest = _sha256(metadata_bytes)
    if digest != SHARED_SCHEMA_SHA256:
        raise SemanticSchemaError(
            f"vendored semantic assertion schema digest is {digest}, "
            f"expected {SHARED_SCHEMA_SHA256}"
        )
    if metadata_digest != SHARED_SCHEMA_METADATA_SHA256:
        raise SemanticSchemaError(
            f"semantic assertion schema metadata digest is {metadata_digest}, "
            f"expected {SHARED_SCHEMA_METADATA_SHA256}"
        )
    expected_metadata = {
        "draft": SHARED_SCHEMA_DRAFT,
        "network_resolution_allowed": False,
        "sha256": SHARED_SCHEMA_SHA256,
        "source": SHARED_SCHEMA_ID,
    }
    for key, expected in expected_metadata.items():
        if metadata.get(key) != expected:
            raise SemanticSchemaError(
                f"schema metadata {key!r} is {metadata.get(key)!r}, expected {expected!r}"
            )
    if schema.get("$schema") != SHARED_SCHEMA_DRAFT:
        raise SemanticSchemaError("vendored semantic assertion schema draft changed")
    if schema.get("$id") != SHARED_SCHEMA_ID:
        raise SemanticSchemaError("vendored semantic assertion schema identity changed")
    _check_supported_schema(schema)
    provenance = {
        "id": SHARED_SCHEMA_ID,
        "draft": SHARED_SCHEMA_DRAFT,
        "localPath": "schemas/semantic-assertion.schema.json",
        "metadataPath": "schemas/semantic-assertion.schema.metadata.json",
        "sha256": digest,
        "metadataSha256": metadata_digest,
        "networkResolutionAllowed": False,
    }
    return schema, provenance


def _is_type(instance: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(instance, Mapping)
    if expected == "array":
        return isinstance(instance, list)
    if expected == "string":
        return isinstance(instance, str)
    if expected == "number":
        return isinstance(instance, (int, float)) and not isinstance(instance, bool)
    if expected == "integer":
        return isinstance(instance, int) and not isinstance(instance, bool)
    if expected == "boolean":
        return isinstance(instance, bool)
    if expected == "null":
        return instance is None
    return False


def _format_valid(instance: str, format_name: str) -> bool:
    if format_name == "uri":
        parsed = urlsplit(instance)
        return bool(parsed.scheme) and not any(character.isspace() for character in instance)
    if format_name == "date-time":
        try:
            parsed = datetime.fromisoformat(instance.replace("Z", "+00:00"))
        except ValueError:
            return False
        return "T" in instance and parsed.tzinfo is not None
    return False


def _resolve_ref(root: Mapping[str, Any], reference: str) -> Mapping[str, Any]:
    if not reference.startswith("#/"):
        raise SemanticSchemaError(f"remote or non-local schema reference is forbidden: {reference}")
    current: Any = root
    for raw_part in reference[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, Mapping) or part not in current:
            raise SemanticSchemaError(f"unresolvable local schema reference: {reference}")
        current = current[part]
    if not isinstance(current, Mapping):
        raise SemanticSchemaError(f"schema reference is not an object: {reference}")
    return current


def _errors(
    instance: Any,
    schema: Mapping[str, Any],
    root: Mapping[str, Any],
    path: str,
) -> list[str]:
    reference = schema.get("$ref")
    if isinstance(reference, str):
        return _errors(instance, _resolve_ref(root, reference), root, path)

    failures: list[str] = []
    expected_type = schema.get("type")
    if isinstance(expected_type, str) and not _is_type(instance, expected_type):
        return [f"{path}: expected {expected_type}"]

    if "const" in schema and instance != schema["const"]:
        failures.append(f"{path}: value does not match const")
    enum = schema.get("enum")
    if isinstance(enum, list) and instance not in enum:
        failures.append(f"{path}: value is outside enum")

    one_of = schema.get("oneOf")
    if isinstance(one_of, list):
        matches = sum(not _errors(instance, child, root, path) for child in one_of)
        if matches != 1:
            failures.append(f"{path}: expected exactly one matching oneOf branch, found {matches}")

    all_of = schema.get("allOf")
    if isinstance(all_of, list):
        for child in all_of:
            failures.extend(_errors(instance, child, root, path))

    condition = schema.get("if")
    consequent = schema.get("then")
    if isinstance(condition, Mapping) and isinstance(consequent, Mapping):
        if not _errors(instance, condition, root, path):
            failures.extend(_errors(instance, consequent, root, path))

    if isinstance(instance, Mapping):
        required = schema.get("required")
        if isinstance(required, list):
            for name in required:
                if name not in instance:
                    failures.append(f"{path}: missing required property {name!r}")
        properties = schema.get("properties")
        properties = properties if isinstance(properties, Mapping) else {}
        for name, child in properties.items():
            if name in instance and isinstance(child, Mapping):
                failures.extend(_errors(instance[name], child, root, f"{path}.{name}"))
        if schema.get("additionalProperties") is False:
            for name in sorted(set(instance) - set(properties)):
                failures.append(f"{path}: additional property {name!r} is forbidden")

    if isinstance(instance, list):
        minimum_items = schema.get("minItems")
        if isinstance(minimum_items, int) and len(instance) < minimum_items:
            failures.append(f"{path}: expected at least {minimum_items} item(s)")
        if schema.get("uniqueItems") is True:
            canonical_items = [_canonical(item) for item in instance]
            if len(canonical_items) != len(set(canonical_items)):
                failures.append(f"{path}: array items are not unique")
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for index, item in enumerate(instance):
                failures.extend(_errors(item, item_schema, root, f"{path}[{index}]"))

    if isinstance(instance, str):
        minimum_length = schema.get("minLength")
        if isinstance(minimum_length, int) and len(instance) < minimum_length:
            failures.append(f"{path}: string is shorter than {minimum_length}")
        pattern = schema.get("pattern")
        if isinstance(pattern, str) and re.search(pattern, instance) is None:
            failures.append(f"{path}: string does not match required pattern")
        format_name = schema.get("format")
        if isinstance(format_name, str) and not _format_valid(instance, format_name):
            failures.append(f"{path}: string is not a valid {format_name}")

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, (int, float)) and instance < minimum:
            failures.append(f"{path}: value is below minimum {minimum}")
        if isinstance(maximum, (int, float)) and instance > maximum:
            failures.append(f"{path}: value is above maximum {maximum}")
    return failures


def validate_assertions(
    semantic_assertions: Iterable[Mapping[str, Any]],
    runtime_assertions_as_semantic: Iterable[Mapping[str, Any]],
    *,
    schema_path: Path,
    metadata_path: Path,
) -> dict[str, Any]:
    """Exhaustively validate semantic nodes and mapped runtime rows."""

    schema, provenance = load_pinned_schema(schema_path, metadata_path)
    semantic = list(semantic_assertions)
    runtime = list(runtime_assertions_as_semantic)
    for plane, assertions in (("semantic", semantic), ("runtime-mapped", runtime)):
        seen: set[str] = set()
        for index, assertion in enumerate(assertions):
            assertion_id = str(assertion.get("@id") or "")
            if assertion_id in seen:
                raise SemanticSchemaError(
                    f"{plane} assertion {index} duplicates identity {assertion_id!r}"
                )
            seen.add(assertion_id)
            failures = _errors(assertion, schema, schema, f"{plane}[{index}]")
            if failures:
                sample = "; ".join(failures[:5])
                raise SemanticSchemaError(
                    f"{plane} assertion {assertion_id or index!r} "
                    f"failed the pinned schema: {sample}"
                )
    semantic_digest = _sha256(
        _canonical(sorted(str(row["@id"]) for row in semantic)).encode("utf-8")
    )
    runtime_digest = _sha256(
        _canonical(sorted(str(row["@id"]) for row in runtime)).encode("utf-8")
    )
    if len(semantic) != len(runtime) or semantic_digest != runtime_digest:
        raise SemanticSchemaError("semantic and runtime-mapped validated assertion sets differ")
    return {
        "schema": "okf-ons-semantic-assertion-validation.v1",
        "status": "conformant",
        "validator": {
            "id": VALIDATOR_ID,
            "offline": True,
            "failOnUnsupportedSchemaKeyword": True,
            "formatAssertionsEnabled": True,
        },
        "schemaBinding": provenance,
        "counts": {
            "semanticAssertionsValidated": len(semantic),
            "runtimeRowsMappedAndValidated": len(runtime),
            "validationFailures": 0,
        },
        "assertionIdentitySetSha256": semantic_digest,
    }
