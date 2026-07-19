"""Dependency-free, metadata-only MCP broker for the frozen OKF-ONS corpus.

The broker deliberately has no network or live-query code. It exposes a small,
portable MCP surface over JSON-lines stdio so an AI client can orient, search,
hydrate, compare and prepare a *non-executing* MCP hand-off from the checked-in
frozen metadata snapshot.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TextIO
from urllib.parse import quote, unquote

from .build import default_inputs, load_frozen_corpus
from .model import build_cross_source_reconciliation, tokenize
from .search import rank_records, search_tokenize

PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "okf-ons-metadata-broker"
SERVER_VERSION = "0.1.0"

MATERIAL_CAVEATS = {
    "metadata-only": "The broker returns metadata and never observation values.",
    "incomplete-ons-corpus": (
        "The frozen demonstrator represents three ONS metadata lanes, not all ONS data."
    ),
    "accuracy-not-evaluated": (
        "Metadata evidence availability does not establish statistical accuracy."
    ),
    "alignment-not-certification": (
        "Vocabulary or profile alignment is not conformance or product certification."
    ),
    "evidence-not-fitness-certification": (
        "Evidence availability does not establish methodological quality or fitness for use."
    ),
    "reconciliation-not-equivalence": (
        "A shared code or cross-source match does not prove statistical equivalence."
    ),
    "selection-incomplete-no-execution": (
        "Missing dimensions and options remain explicit and no live query is executed."
    ),
    "substitution-disclosed": (
        "Any substitute example must be named and distinguished from the requested record."
    ),
}

_FORBIDDEN_INPUT_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "chain_of_thought",
    "credential",
    "credentials",
    "hidden_reasoning",
    "observation",
    "observation_values",
    "observations",
    "password",
    "private_reasoning",
    "reasoning",
    "secret",
    "secrets",
    "thoughts",
}
_PROHIBITED_TEXT = (
    re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]{12,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{30,}\b"),
    re.compile(r"(?i)(?:/Users/|/Volumes/|[A-Z]:\\\\Users\\\\)"),
)
_CONTRAST_FIELDS = (
    ("native_id", "/native_id"),
    ("source_surface", "/source_surface"),
    ("record_type", "/record_type"),
    ("frequency", "/frequency"),
    ("population_type", "/population_type"),
    ("geography", "/geography"),
    ("time_coverage", "/time_coverage"),
    ("latest_edition", "/latest_edition"),
    ("latest_version", "/latest_version"),
    ("state", "/state"),
    ("metadata_modified", "/metadata_modified"),
    ("methodology_links", "/methodology_links"),
    ("quality_links", "/quality_links"),
    ("revision_status", "/revision_status"),
)


class BrokerToolError(ValueError):
    """A safe, structured tool error that may be returned to a client."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


def canonical_json(value: Any) -> str:
    """Return deterministic compact JSON for the wire protocol and digests."""

    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _normalise_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).casefold()).strip("_")


def _validate_safe_input(value: object) -> None:
    """Reject credentials, hidden reasoning and machine-local paths."""

    if isinstance(value, Mapping):
        for key, child in value.items():
            normalised = _normalise_key(key)
            if normalised in _FORBIDDEN_INPUT_KEYS:
                raise BrokerToolError(
                    "PROHIBITED_INPUT",
                    f"Input field {key!r} is not accepted by this metadata-only broker.",
                )
            _validate_safe_input(child)
    elif isinstance(value, list):
        for child in value:
            _validate_safe_input(child)
    elif isinstance(value, str):
        if any(pattern.search(value) for pattern in _PROHIBITED_TEXT):
            raise BrokerToolError(
                "PROHIBITED_INPUT",
                "Input contains a credential-like value or machine-local path.",
            )


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BrokerToolError("INVALID_ARGUMENT", f"{label} must be an object.")
    return value


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BrokerToolError("INVALID_ARGUMENT", f"{label} must be a non-empty string.")
    return value.strip()


def _tool_definition(
    name: str,
    title: str,
    description: str,
    input_schema: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "name": name,
        "title": title,
        "description": description,
        "inputSchema": dict(input_schema),
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    }


TOOL_DEFINITIONS = [
    _tool_definition(
        "okf.descriptor",
        "Orient to the frozen OKF-ONS corpus",
        (
            "Return the pinned metadata-only corpus descriptor, scope boundaries, "
            "entrypoints, outcome codes and material caveats. Makes no network request."
        ),
        {"type": "object", "properties": {}, "additionalProperties": False},
    ),
    _tool_definition(
        "okf.search",
        "Search frozen ONS metadata",
        (
            "Rank compact candidates from a non-empty intent or identifier query and "
            "show nearby alternatives before selection."
        ),
        {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 10},
                "source_surface": {"type": "string"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    ),
    _tool_definition(
        "okf.get_record",
        "Hydrate one exact ONS metadata record",
        (
            "Resolve an exact stable ID, native ID, route or declared evaluation alias "
            "and return the complete frozen metadata record."
        ),
        {
            "type": "object",
            "properties": {"identifier": {"type": "string", "minLength": 1}},
            "required": ["identifier"],
            "additionalProperties": False,
        },
    ),
    _tool_definition(
        "okf.compare",
        "Compare exact ONS metadata records",
        (
            "Return evidence-backed field contrasts for two to five exact records. "
            "Never asserts statistical equivalence."
        ),
        {
            "type": "object",
            "properties": {
                "record_ids": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "minItems": 2,
                    "maxItems": 5,
                    "uniqueItems": True,
                }
            },
            "required": ["record_ids"],
            "additionalProperties": False,
        },
    ),
    _tool_definition(
        "okf.prepare_mcp_plan",
        "Prepare a non-executing MCP selection plan",
        (
            "Bind the exact frozen identity to its inspection/query tools, preserve "
            "unresolved dimensions and reject credential fields. Never executes a query."
        ),
        {
            "type": "object",
            "properties": {
                "record_id": {"type": "string", "minLength": 1},
                "arguments": {"type": "object", "default": {}},
            },
            "required": ["record_id"],
            "additionalProperties": False,
        },
    ),
    _tool_definition(
        "okf_eval.submit_answer",
        "Normalise an AI evaluation answer",
        (
            "Validate and return a deterministic, non-persisted evaluation envelope. "
            "Accepts visible answers, evidence and caveats, never hidden reasoning."
        ),
        {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "minLength": 1},
                "chosen_record_id": {
                    "oneOf": [{"type": "string", "minLength": 1}, {"type": "null"}]
                },
                "considered_record_ids": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "uniqueItems": True,
                },
                "alternatives": {"type": "array", "items": {}},
                "contrasts": {"type": "array", "items": {"type": "object"}},
                "evidence": {"type": "array", "items": {"type": "object"}},
                "caveat_ids": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "uniqueItems": True,
                },
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "answer": {"type": "string", "maxLength": 20_000},
                "mcp_plan": {"type": "object"},
                "substitution": {"type": "object"},
            },
            "required": [
                "task_id",
                "chosen_record_id",
                "considered_record_ids",
                "alternatives",
                "evidence",
                "caveat_ids",
                "confidence",
                "answer",
            ],
            "additionalProperties": False,
        },
    ),
]


class MCPBroker:
    """Read-only operations over one checked-in frozen corpus."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or Path(__file__).resolve().parents[2]).resolve()
        self.corpus = load_frozen_corpus(default_inputs(self.root))
        self.records = self.corpus.records

        # This fast reconciliation pass annotates observed table codes. The
        # expensive all-record similarity pass is intentionally lazy below.
        build_cross_source_reconciliation(self.records)
        self.records_by_id = {str(record["id"]): record for record in self.records}
        self.identity_index: dict[str, set[str]] = defaultdict(set)
        for record in self.records:
            identities = (
                record.get("id"),
                record.get("native_id"),
                record.get("name"),
                record.get("route"),
                record.get("open"),
                *record.get("evaluation_aliases", []),
            )
            for identity in identities:
                if identity not in {None, ""}:
                    self.identity_index[str(identity).casefold()].add(str(record["id"]))

        self.token_sets: list[set[str]] = []
        self.inverted_tokens: dict[str, list[int]] = defaultdict(list)
        self.record_ordinals: dict[str, int] = {}
        for ordinal, record in enumerate(self.records):
            self.record_ordinals[str(record["id"])] = ordinal
            tokens = set(
                tokenize(
                    record.get("title"),
                    " ".join(record.get("topics") or []),
                    " ".join(record.get("tags") or []),
                )
            )
            self.token_sets.append(tokens)
            for token in tokens:
                self.inverted_tokens[token].append(ordinal)
        self.alternative_cache: dict[str, list[dict[str, Any]]] = {}

        self.task_ids: set[str] = set()
        self.material_caveats = dict(MATERIAL_CAVEATS)
        tasks_path = self.root / "evaluation" / "ai-client" / "tasks.json"
        if tasks_path.is_file():
            task_document = json.loads(tasks_path.read_text(encoding="utf-8"))
            self.task_ids = {
                str(row["id"])
                for row in task_document.get("tasks", [])
                if isinstance(row, Mapping) and row.get("id")
            }
        expected_path = self.root / "evaluation" / "ai-client" / "expected.json"
        if expected_path.is_file():
            expected_document = json.loads(expected_path.read_text(encoding="utf-8"))
            caveat_register = expected_document.get("caveat_register")
            if isinstance(caveat_register, Mapping):
                self.material_caveats.update(
                    {
                        str(caveat_id): str(description)
                        for caveat_id, description in caveat_register.items()
                    }
                )

    @property
    def snapshot_id(self) -> str:
        return str(self.corpus.snapshot["snapshotId"])

    def _resolve_record(self, identifier: object) -> dict[str, Any]:
        text = _require_string(identifier, "identifier")
        exact = self.records_by_id.get(text)
        if exact is not None:
            return exact
        matches = sorted(self.identity_index.get(text.casefold(), set()))
        if not matches:
            raise BrokerToolError(
                "NOT_FOUND",
                f"No exact frozen metadata record matches {text!r}.",
                details={"identifier": text},
            )
        if len(matches) > 1:
            raise BrokerToolError(
                "AMBIGUOUS",
                f"Identifier {text!r} matches more than one frozen record.",
                details={"identifier": text, "record_ids": matches},
            )
        return self.records_by_id[matches[0]]

    @staticmethod
    def _contrast_values(record: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "source_surface": record.get("source_surface") or "",
            "record_type": record.get("record_type") or "",
            "frequency": record.get("frequency") or "",
            "population_type": record.get("population_type") or "",
            "geography": record.get("geography") or [],
            "time_coverage": record.get("time_coverage") or {},
            "latest_edition": record.get("latest_edition") or "",
            "latest_version": record.get("latest_version") or "",
            "state": record.get("state") or "",
            "metadata_modified": record.get("metadata_modified") or "",
            "methodology_links": record.get("methodology_links") or [],
            "quality_links": record.get("quality_links") or [],
            "revision_status": record.get("revision_status") or "",
        }

    def _alternatives_for(
        self,
        record: Mapping[str, Any],
        *,
        limit: int = 4,
        threshold: float = 0.32,
    ) -> list[dict[str, Any]]:
        record_id = str(record["id"])
        cached = self.alternative_cache.get(record_id)
        if cached is not None:
            return cached[:limit]
        ordinal = self.record_ordinals[record_id]
        tokens = self.token_sets[ordinal]
        candidate_ordinals: set[int] = set()
        for token in tokens:
            if len(self.inverted_tokens[token]) <= 500:
                candidate_ordinals.update(self.inverted_tokens[token])
        candidate_ordinals.discard(ordinal)

        title_tokens = set(tokenize(record.get("title")))
        scored: list[tuple[float, int, list[str]]] = []
        for other_ordinal in candidate_ordinals:
            other_tokens = self.token_sets[other_ordinal]
            union = tokens | other_tokens
            if not union:
                continue
            shared = sorted(tokens & other_tokens)
            other_title_tokens = set(tokenize(self.records[other_ordinal].get("title")))
            title_union = title_tokens | other_title_tokens
            title_score = (
                len(title_tokens & other_title_tokens) / len(title_union)
                if title_union
                else 0.0
            )
            score = 0.75 * title_score + 0.25 * (len(shared) / len(union))
            if score >= threshold:
                scored.append((score, other_ordinal, shared))
        scored.sort(
            key=lambda item: (
                -item[0],
                str(self.records[item[1]]["title"]),
                str(self.records[item[1]]["id"]),
            )
        )

        left = self._contrast_values(record)
        alternatives: list[dict[str, Any]] = []
        for score, other_ordinal, shared in scored[:4]:
            other = self.records[other_ordinal]
            right = self._contrast_values(other)
            differences = [
                {
                    "field": field,
                    "selected": left[field],
                    "alternative": right[field],
                }
                for field in left
                if left[field] != right[field]
                and (
                    left[field] not in (None, "", [], {})
                    or right[field] not in (None, "", [], {})
                )
            ]
            alternatives.append(
                {
                    "record_id": other["id"],
                    "title": other["title"],
                    "source_surface": other["source_surface"],
                    "record_type": other["record_type"],
                    "relationship_type": (
                        "cross-source-alternative"
                        if record.get("source_surface") != other.get("source_surface")
                        else "alternative"
                    ),
                    "similarity": round(score, 3),
                    "shared_terms": shared[:12],
                    "differences": differences,
                    "not_enough_evidence": not bool(differences),
                    "statistical_equivalence_asserted": False,
                }
            )
        self.alternative_cache[record_id] = alternatives
        return alternatives[:limit]

    def descriptor(self) -> dict[str, Any]:
        source_counts = dict(
            sorted(Counter(str(row["source_surface"]) for row in self.records).items())
        )
        standards = self.corpus.standards_register.get("standards", [])
        return {
            "schema": "okf-ons.mcp-descriptor.v1",
            "title": "ONS data discovery OKF metadata broker",
            "snapshotId": self.snapshot_id,
            "snapshotSha256": hashlib.sha256(
                canonical_json(self.corpus.snapshot).encode("utf-8")
            ).hexdigest(),
            "metadataOnly": True,
            "observationsIncluded": False,
            "networkAccess": False,
            "liveQueries": False,
            "credentialsStored": False,
            "scope": {
                "status": "bounded-demonstrator",
                "complete_ons_corpus": False,
                "record_count": len(self.records),
                "source_counts": source_counts,
                "implemented_source_lanes": len(source_counts),
                "standards_registered": len(standards),
            },
            "entrypoints": {
                "orientation": "okf://ons/descriptor",
                "agent_profile": "okf://ons/agent-profile",
                "selection_contract": "okf://ons/selection-contract",
                "exact_record_template": "okf://ons/record/{percent-encoded-record-id}",
            },
            "tools": [definition["name"] for definition in TOOL_DEFINITIONS],
            "orientation": [
                "Read scope and caveats before interpreting results.",
                "Search by user intent; do not choose the first convenient record.",
                "Compare nearby or cross-source alternatives before selection.",
                "Hydrate the exact record before making identity or provenance claims.",
                "Prepare an incomplete hand-off for live MCP validation; do not execute here.",
            ],
            "outcomeCodes": [
                "NOT_FOUND",
                "AMBIGUOUS",
                "INVALID_ARGUMENT",
                "BINDING_PLANNED",
                "REQUIRES_LIVE_INSPECTION",
                "PROHIBITED_INPUT",
            ],
            "materialCaveats": self.material_caveats,
            "claimBoundary": (
                "The broker exposes frozen metadata evidence and alignment claims. "
                "It does not certify statistical accuracy, fitness, legal compliance "
                "or equivalence between records."
            ),
        }

    def agent_profile(self) -> dict[str, Any]:
        return {
            "schema": "okf-ons.mcp-agent-profile.v1",
            "snapshotId": self.snapshot_id,
            "transport": "json-lines-stdio",
            "access": {
                "read_only": True,
                "offline": True,
                "authentication": "none",
                "cookies": False,
                "secrets": False,
                "observations": False,
            },
            "lookupKeys": ["stable record ID", "native ID", "viewer route", "evaluation alias"],
            "selectionFlow": [
                "descriptor",
                "search",
                "compare",
                "get_record",
                "prepare_mcp_plan",
                "submit_answer",
            ],
            "fallbackRule": (
                "If the requested exact record cannot be hydrated, return NOT_FOUND or "
                "AMBIGUOUS. Never silently replace it with another record."
            ),
            "submissionRule": (
                "Submit only the visible answer and source-qualified evidence. "
                "Hidden reasoning is prohibited and submissions are not persisted."
            ),
        }

    def _compact_candidate(self, record: Mapping[str, Any]) -> dict[str, Any]:
        provenance = record.get("provenance") or {}
        selection = record.get("selection") or {}
        return {
            "record_id": record["id"],
            "native_id": record.get("native_id"),
            "title": record.get("title"),
            "source_surface": record.get("source_surface"),
            "record_type": record.get("record_type"),
            "route": record.get("route"),
            "edition": record.get("latest_edition") or None,
            "version": record.get("latest_version") or None,
            "frequency": record.get("frequency") or None,
            "population_type": record.get("population_type") or None,
            "state": record.get("state") or None,
            "selection": {
                "binding_status": selection.get("binding_status"),
                "inspection_tool": selection.get("tool"),
                "query_tool": selection.get("query_tool"),
                "complete": selection.get("complete") is True,
            },
            "alternatives": self._alternatives_for(record, limit=3),
            "evidence": {
                "record_resource": (
                    "okf://ons/record/" + quote(str(record["id"]), safe="")
                ),
                "source_url": provenance.get("source_url"),
                "source_sha256": provenance.get("source_sha256"),
                "snapshot_id": provenance.get("snapshot_id"),
            },
        }

    def search(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        query = _require_string(arguments.get("query"), "query")
        limit_value = arguments.get("limit", 10)
        if (
            isinstance(limit_value, bool)
            or not isinstance(limit_value, int)
            or not 1 <= limit_value <= 20
        ):
            raise BrokerToolError("INVALID_ARGUMENT", "limit must be an integer from 1 to 20.")
        source_surface = arguments.get("source_surface")
        if source_surface is not None:
            source_surface = _require_string(source_surface, "source_surface")
            known_sources = {str(row["source_surface"]) for row in self.records}
            if source_surface not in known_sources:
                raise BrokerToolError(
                    "INVALID_ARGUMENT",
                    f"Unknown source_surface {source_surface!r}.",
                    details={"allowed": sorted(known_sources)},
                )
        exact_matches = self.identity_index.get(query.casefold(), set())
        if len(exact_matches) == 1:
            exact = self.records_by_id[next(iter(exact_matches))]
            ranked = (
                [exact]
                if source_surface is None or exact.get("source_surface") == source_surface
                else []
            )
        else:
            if not search_tokenize(query):
                raise BrokerToolError(
                    "INVALID_ARGUMENT",
                    "query must contain a searchable term or an exact record identifier.",
                )
            searchable = (
                self.records
                if source_surface is None
                else [
                    row for row in self.records if row.get("source_surface") == source_surface
                ]
            )
            ranked = rank_records(searchable, query, limit=limit_value)
        candidates = [self._compact_candidate(record) for record in ranked[:limit_value]]
        return {
            "schema": "okf-ons.mcp-search-result.v1",
            "snapshotId": self.snapshot_id,
            "metadataOnly": True,
            "query": query,
            "source_surface": source_surface,
            "returned": len(candidates),
            "candidates": candidates,
            "reducedSetAlternatives": [
                {
                    "record_id": candidate["record_id"],
                    "native_id": candidate["native_id"],
                    "title": candidate["title"],
                    "source_surface": candidate["source_surface"],
                    "record_type": candidate["record_type"],
                    "edition": candidate["edition"],
                    "version": candidate["version"],
                }
                for candidate in candidates
            ],
            "selectionGuidance": (
                "Treat the returned reduced set as alternatives, review any evidence-backed "
                "record alternatives, and hydrate the exact record before selection. A high "
                "rank is discovery evidence, not proof of fitness."
            ),
        }

    def get_record(self, identifier: object) -> dict[str, Any]:
        record = self._resolve_record(identifier)
        hydrated = dict(record)
        alternatives = self._alternatives_for(record)
        hydrated["alternatives"] = alternatives
        hydrated["alternative_count"] = len(alternatives)
        return {
            "schema": "okf-ons.mcp-record.v1",
            "snapshotId": self.snapshot_id,
            "metadataOnly": True,
            "observationsIncluded": False,
            "hydration": {
                "status": "complete",
                "resolved_by": "exact-identity",
                "record_resource": (
                    "okf://ons/record/" + quote(str(record["id"]), safe="")
                ),
            },
            "record": hydrated,
            "materialCaveatIds": [
                "metadata-only",
                "accuracy-not-evaluated",
                "evidence-not-fitness-certification",
                "alignment-not-certification",
            ],
        }

    def compare(self, identifiers: object) -> dict[str, Any]:
        if not isinstance(identifiers, list) or not 2 <= len(identifiers) <= 5:
            raise BrokerToolError(
                "INVALID_ARGUMENT", "record_ids must contain two to five exact identifiers."
            )
        records = [self._resolve_record(identifier) for identifier in identifiers]
        record_ids = [str(record["id"]) for record in records]
        if len(record_ids) != len(set(record_ids)):
            raise BrokerToolError(
                "INVALID_ARGUMENT", "record_ids must resolve to distinct records."
            )
        comparison_rows: list[dict[str, Any]] = []
        for field, pointer in _CONTRAST_FIELDS:
            values = [
                {"record_id": record["id"], "value": record.get(field) or None}
                for record in records
            ]
            distinct = {canonical_json(row["value"]) for row in values}
            comparison_rows.append(
                {
                    "field": field,
                    "different": len(distinct) > 1,
                    "values": values,
                    "evidence": [
                        {"record_id": record["id"], "json_pointer": pointer}
                        for record in records
                    ],
                }
            )
        declared_code_sets = [
            set(str(code) for code in record.get("declared_table_codes", []))
            for record in records
        ]
        shared_codes = (
            sorted(set.intersection(*declared_code_sets)) if declared_code_sets else []
        )
        return {
            "schema": "okf-ons.mcp-comparison.v1",
            "snapshotId": self.snapshot_id,
            "metadataOnly": True,
            "records": [
                {
                    "record_id": record["id"],
                    "native_id": record.get("native_id"),
                    "title": record.get("title"),
                    "source_surface": record.get("source_surface"),
                }
                for record in records
            ],
            "fields": comparison_rows,
            "differences": [row for row in comparison_rows if row["different"]],
            "sharedDeclaredTableCodes": shared_codes,
            "statisticalEquivalenceAsserted": False,
            "materialCaveatIds": [
                "reconciliation-not-equivalence",
                "evidence-not-fitness-certification",
            ],
        }

    @staticmethod
    def _dimension_names(record: Mapping[str, Any]) -> list[tuple[str, str]]:
        names: list[tuple[str, str]] = []
        for index, dimension in enumerate(record.get("dimensions") or []):
            if isinstance(dimension, Mapping):
                name = next(
                    (
                        str(dimension[key])
                        for key in ("id", "name", "label", "concept")
                        if dimension.get(key)
                    ),
                    f"dimension-{index + 1}",
                )
            else:
                name = str(dimension)
            names.append((name, f"/dimensions/{index}"))
        return names

    def prepare_mcp_plan(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        record = self._resolve_record(arguments.get("record_id"))
        proposed = arguments.get("arguments", {})
        proposed = _require_mapping(proposed, "arguments")
        binding = record.get("selection") if isinstance(record.get("selection"), Mapping) else {}
        fixed = (
            dict(binding.get("arguments") or {})
            if isinstance(binding.get("arguments"), Mapping)
            else {}
        )
        conflicts = [
            {
                "argument": key,
                "expected": value,
                "provided": proposed[key],
                "reason": "frozen-identity-mismatch",
            }
            for key, value in fixed.items()
            if key in proposed and proposed[key] != value
        ]
        unvalidated = {
            key: value
            for key, value in proposed.items()
            if key not in fixed
        }
        available = binding.get("mcp_available") is True
        dimension_names = self._dimension_names(record)
        unknown_dimensions = [
            {
                "dimension": name,
                "record_id": record["id"],
                "json_pointer": pointer,
            }
            for name, pointer in dimension_names
        ]
        if available and not unknown_dimensions:
            unknown_dimensions = [
                {
                    "dimension": "dataset-specific dimension options",
                    "record_id": record["id"],
                    "json_pointer": "/selection/reason",
                }
            ]
        if conflicts:
            status = "invalid-identity"
        elif not available:
            status = "binding-planned"
        else:
            status = "requires-live-inspection"
        return {
            "schema": "okf-ons-selection-plan.v1",
            "snapshotId": self.snapshot_id,
            "source": record.get("source_surface"),
            "record_id": record["id"],
            "native_id": record.get("native_id"),
            "inspection_tool": binding.get("tool"),
            "query_tool": binding.get("query_tool"),
            "arguments": fixed,
            "proposed_unvalidated_arguments": unvalidated,
            "complete": False,
            "unknown_dimensions": unknown_dimensions,
            "invalid_options": conflicts,
            "validation": {
                "status": status,
                "identity_binding_valid": not conflicts,
                "binding_available": available,
                "live_validation_performed": False,
                "reason": binding.get("reason")
                or "No live MCP binding is published for this source surface.",
            },
            "executed": False,
            "executionBoundary": (
                "A trusted live MCP server must validate the current version, "
                "dimensions and options. This broker cannot execute the plan."
            ),
            "materialCaveatIds": ["selection-incomplete-no-execution"],
        }

    def _validate_answer_record_references(self, submission: Mapping[str, Any]) -> None:
        chosen = submission.get("chosen_record_id")
        chosen_id: str | None = None
        if chosen is not None:
            chosen_id = str(self._resolve_record(chosen)["id"])
        considered = submission.get("considered_record_ids")
        if not isinstance(considered, list):
            raise BrokerToolError(
                "INVALID_ARGUMENT", "considered_record_ids must be an array."
            )
        considered_ids = [
            str(self._resolve_record(record_id)["id"]) for record_id in considered
        ]
        if len(considered_ids) != len(set(considered_ids)):
            raise BrokerToolError(
                "INVALID_ARGUMENT",
                "considered_record_ids must not resolve to duplicate records.",
            )
        if chosen_id is not None and chosen_id not in considered_ids:
            raise BrokerToolError(
                "INVALID_ARGUMENT",
                "chosen_record_id must also appear in considered_record_ids.",
            )
        alternatives = submission.get("alternatives")
        if not isinstance(alternatives, list):
            raise BrokerToolError("INVALID_ARGUMENT", "alternatives must be an array.")
        alternative_ids: list[str] = []
        for alternative in alternatives:
            if isinstance(alternative, str):
                alternative_ids.append(str(self._resolve_record(alternative)["id"]))
            elif isinstance(alternative, Mapping) and alternative.get("record_id"):
                alternative_ids.append(
                    str(self._resolve_record(alternative["record_id"])["id"])
                )
            else:
                raise BrokerToolError(
                    "INVALID_ARGUMENT",
                    "Each alternative must be a record ID or an object with record_id.",
                )
        if len(alternative_ids) != len(set(alternative_ids)):
            raise BrokerToolError(
                "INVALID_ARGUMENT", "alternatives must not resolve to duplicate records."
            )
        for collection_name in ("contrasts", "evidence"):
            collection = submission.get(collection_name) or []
            if not isinstance(collection, list):
                raise BrokerToolError(
                    "INVALID_ARGUMENT", f"{collection_name} must be an array."
                )
            for row in collection:
                if not isinstance(row, Mapping):
                    raise BrokerToolError(
                        "INVALID_ARGUMENT",
                        f"Each {collection_name} row must be an object.",
                    )
                if row.get("record_id"):
                    self._resolve_record(row["record_id"])

    def submit_answer(self, submission: Mapping[str, Any]) -> dict[str, Any]:
        required_fields = (
            "task_id",
            "chosen_record_id",
            "considered_record_ids",
            "alternatives",
            "evidence",
            "caveat_ids",
            "confidence",
            "answer",
        )
        missing = [field for field in required_fields if field not in submission]
        if missing:
            raise BrokerToolError(
                "INVALID_ARGUMENT",
                "Submission is missing required fields.",
                details={"missing": missing},
            )
        task_id = _require_string(submission.get("task_id"), "task_id")
        if self.task_ids and task_id not in self.task_ids:
            raise BrokerToolError(
                "INVALID_ARGUMENT",
                f"Unknown public evaluation task {task_id!r}.",
                details={"allowed_task_ids": sorted(self.task_ids)},
            )
        self._validate_answer_record_references(submission)
        caveat_ids = submission.get("caveat_ids")
        if not isinstance(caveat_ids, list) or any(
            not isinstance(value, str) for value in caveat_ids
        ):
            raise BrokerToolError("INVALID_ARGUMENT", "caveat_ids must be an array of strings.")
        if len(caveat_ids) != len(set(caveat_ids)):
            raise BrokerToolError("INVALID_ARGUMENT", "caveat_ids must not contain duplicates.")
        unknown_caveats = sorted(set(caveat_ids) - set(self.material_caveats))
        if unknown_caveats:
            raise BrokerToolError(
                "INVALID_ARGUMENT",
                "Submission refers to unknown material caveats.",
                details={"unknown_caveat_ids": unknown_caveats},
            )
        confidence = submission.get("confidence")
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(confidence)
            or not 0 <= confidence <= 1
        ):
            raise BrokerToolError(
                "INVALID_ARGUMENT", "confidence must be a number from 0 through 1."
            )
        visible_answer = submission.get("answer")
        if (
            not isinstance(visible_answer, str)
            or not visible_answer.strip()
            or len(visible_answer) > 20_000
        ):
            raise BrokerToolError(
                "INVALID_ARGUMENT",
                "answer must be a non-empty string of at most 20,000 characters.",
            )
        mcp_plan = submission.get("mcp_plan")
        if mcp_plan is not None and not isinstance(mcp_plan, Mapping):
            raise BrokerToolError("INVALID_ARGUMENT", "mcp_plan must be an object.")
        if isinstance(mcp_plan, Mapping):
            if mcp_plan.get("record_id"):
                self._resolve_record(mcp_plan["record_id"])
            if mcp_plan.get("executed") is True:
                raise BrokerToolError(
                    "PROHIBITED_INPUT",
                    "A metadata-only broker submission cannot claim an executed live plan.",
                )
        substitution = submission.get("substitution")
        if substitution is not None and not isinstance(substitution, Mapping):
            raise BrokerToolError("INVALID_ARGUMENT", "substitution must be an object.")
        normalised = json.loads(canonical_json(submission))
        submission_sha256 = hashlib.sha256(
            canonical_json(normalised).encode("utf-8")
        ).hexdigest()
        visible_answer_sha256 = hashlib.sha256(
            visible_answer.encode("utf-8")
        ).hexdigest()
        return {
            "schema": "okf-ons.ai-answer-receipt.v1",
            "accepted": True,
            "task_id": task_id,
            "snapshotId": self.snapshot_id,
            "persisted": False,
            "hiddenReasoningCollected": False,
            "submissionSha256": submission_sha256,
            "visibleAnswerSha256": visible_answer_sha256,
            "submission": normalised,
            "assessment": {
                "status": "required",
                "independent": True,
                "rule": (
                    "The submitted answer is evidence, not its own score. Bind an "
                    "independent assessment to visibleAnswerSha256."
                ),
            },
        }

    def call_tool(self, name: object, arguments: object) -> dict[str, Any]:
        try:
            tool_name = _require_string(name, "tool name")
            tool_arguments = _require_mapping(arguments, "arguments")
            _validate_safe_input(tool_arguments)
            if tool_name == "okf.descriptor":
                if tool_arguments:
                    raise BrokerToolError(
                        "INVALID_ARGUMENT", "okf.descriptor accepts no arguments."
                    )
                return _tool_success(self.descriptor())
            if tool_name == "okf.search":
                return _tool_success(self.search(tool_arguments))
            if tool_name == "okf.get_record":
                return _tool_success(self.get_record(tool_arguments.get("identifier")))
            if tool_name == "okf.compare":
                return _tool_success(self.compare(tool_arguments.get("record_ids")))
            if tool_name == "okf.prepare_mcp_plan":
                return _tool_success(self.prepare_mcp_plan(tool_arguments))
            if tool_name == "okf_eval.submit_answer":
                return _tool_success(self.submit_answer(tool_arguments))
            raise BrokerToolError("NOT_FOUND", f"Unknown MCP tool {tool_name!r}.")
        except BrokerToolError as error:
            return _tool_error(error)

    def read_resource(self, uri_value: object) -> tuple[str, dict[str, Any]]:
        uri = _require_string(uri_value, "uri")
        if uri == "okf://ons/descriptor":
            return uri, self.descriptor()
        if uri == "okf://ons/agent-profile":
            return uri, self.agent_profile()
        if uri == "okf://ons/selection-contract":
            return uri, {
                "schema": "okf-ons.mcp-selection-contract.v1",
                "metadataOnly": True,
                "readOnly": True,
                "executionAllowed": False,
                "rules": [
                    "Resolve an exact frozen record identity.",
                    "Preserve native dataset, edition and version identifiers.",
                    "Inspect the live MCP schema before selecting dimensions or options.",
                    "Leave unvalidated dimensions explicit.",
                    "Never pass credentials to this broker.",
                    "Never claim that a plan was executed by this broker.",
                ],
            }
        prefix = "okf://ons/record/"
        if uri.startswith(prefix):
            identifier = unquote(uri[len(prefix) :])
            return uri, self.get_record(identifier)
        raise BrokerToolError("NOT_FOUND", f"Unknown MCP resource {uri!r}.")


def _tool_success(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(payload)
    return {
        "content": [{"type": "text", "text": canonical_json(value)}],
        "structuredContent": value,
        "isError": False,
    }


def _tool_error(error: BrokerToolError) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "isError": True,
        "code": error.code,
        "message": error.message,
    }
    if error.details:
        payload["details"] = error.details
    return {
        "content": [{"type": "text", "text": canonical_json(payload)}],
        "structuredContent": payload,
        "isError": True,
    }


def _jsonrpc_error(
    request_id: object,
    code: int,
    message: str,
) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def handle_message(broker: MCPBroker, message: object) -> dict[str, Any] | None:
    """Dispatch one decoded JSON-RPC message."""

    if not isinstance(message, Mapping) or message.get("jsonrpc") != "2.0":
        return _jsonrpc_error(
            message.get("id") if isinstance(message, Mapping) else None,
            -32600,
            "Invalid Request",
        )
    request_id = message.get("id")
    method = message.get("method")
    if not isinstance(method, str):
        return None if "id" not in message else _jsonrpc_error(
            request_id, -32600, "Invalid Request"
        )
    if "id" not in message:
        # MCP notifications never receive a response. The broker has no
        # notification-triggered mutation or other side effect.
        return None
    params = message.get("params", {})
    if not isinstance(params, Mapping):
        return _jsonrpc_error(request_id, -32602, "Invalid params")
    try:
        if method == "initialize":
            requested = params.get("protocolVersion")
            protocol = (
                requested
                if isinstance(requested, str) and requested == PROTOCOL_VERSION
                else PROTOCOL_VERSION
            )
            result = {
                "protocolVersion": protocol,
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False},
                },
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": (
                    "Metadata-only frozen ONS discovery. Orient, search, compare, "
                    "hydrate, then prepare a non-executing hand-off."
                ),
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOL_DEFINITIONS}
        elif method == "tools/call":
            result = broker.call_tool(params.get("name"), params.get("arguments", {}))
        elif method == "resources/list":
            result = {
                "resources": [
                    {
                        "uri": "okf://ons/descriptor",
                        "name": "OKF-ONS descriptor",
                        "description": "Pinned scope, orientation and caveat contract.",
                        "mimeType": "application/json",
                    },
                    {
                        "uri": "okf://ons/agent-profile",
                        "name": "OKF-ONS agent profile",
                        "description": "Read-only access and selection workflow.",
                        "mimeType": "application/json",
                    },
                    {
                        "uri": "okf://ons/selection-contract",
                        "name": "OKF-ONS selection contract",
                        "description": "Rules for a non-executing MCP hand-off.",
                        "mimeType": "application/json",
                    },
                ],
            }
        elif method == "resources/read":
            uri, payload = broker.read_resource(params.get("uri", params.get("name")))
            result = {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "application/json",
                        "text": canonical_json(payload),
                    }
                ]
            }
        else:
            return _jsonrpc_error(request_id, -32601, "Method not found")
    except BrokerToolError as error:
        return _jsonrpc_error(request_id, -32602, f"{error.code}: {error.message}")
    except Exception:
        # Never expose paths, stack traces or input data on the wire.
        return _jsonrpc_error(request_id, -32603, "Internal error")
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def handle_line(broker: MCPBroker, line: str) -> str | None:
    """Decode and dispatch one JSON line."""

    if not line.strip():
        return None
    try:
        message = json.loads(line)
    except json.JSONDecodeError:
        return canonical_json(_jsonrpc_error(None, -32700, "Parse error"))
    response = handle_message(broker, message)
    return canonical_json(response) if response is not None else None


def serve(
    broker: MCPBroker,
    *,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> int:
    """Serve JSON-lines MCP on stdio without writing logs to stdout."""

    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    for line in input_stream:
        response = handle_line(broker, line)
        if response is None:
            continue
        output_stream.write(response)
        output_stream.write("\n")
        output_stream.flush()
    return 0
