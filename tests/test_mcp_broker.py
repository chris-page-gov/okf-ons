from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from okf_ons.mcp_broker import (  # noqa: E402
    TOOL_DEFINITIONS,
    MCPBroker,
    _build_identity_index,
    canonical_json,
    handle_line,
    serve,
)
from okf_ons.model import content_sha256  # noqa: E402


@pytest.fixture(scope="module")
def broker() -> MCPBroker:
    return MCPBroker(ROOT)


def _payload(broker: MCPBroker, name: str, arguments: dict) -> dict:
    result = broker.call_tool(name, arguments)
    assert result["isError"] is False, result
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]
    return result["structuredContent"]


def test_descriptor_search_and_exact_hydration_are_metadata_only(
    broker: MCPBroker,
) -> None:
    descriptor = _payload(broker, "okf.descriptor", {})
    assert descriptor["snapshotId"] == "monday-2026-07-17-r2"
    assert descriptor["scope"]["record_count"] == 5_097
    assert descriptor["scope"]["complete_ons_corpus"] is False
    assert descriptor["metadataOnly"] is True
    assert descriptor["observationsIncluded"] is False
    assert descriptor["snapshotSha256"] == content_sha256(broker.corpus.snapshot)
    assert descriptor["networkAccess"] is False
    assert descriptor["liveQueries"] is False

    search = _payload(
        broker,
        "okf.search",
        {
            "query": (
                "monthly Consumer Prices Index including owner occupiers "
                "housing costs CPIH"
            ),
            "limit": 5,
        },
    )
    assert search["candidates"][0]["record_id"] == "ons-data-api:dataset:cpih01"
    assert search["candidates"][0]["native_id"] == "cpih01"
    assert len(search["reducedSetAlternatives"]) > 1
    assert search["reducedSetAlternatives"][0]["record_id"] == (
        "ons-data-api:dataset:cpih01"
    )

    hydrated = _payload(broker, "okf.get_record", {"identifier": "cpih01"})
    assert hydrated["hydration"]["status"] == "complete"
    assert hydrated["record"]["id"] == "ons-data-api:dataset:cpih01"
    assert hydrated["record"]["provenance"]["snapshot_id"] == broker.snapshot_id
    assert hydrated["record"]["selection"]["query_tool"] == "ons_data.query"
    assert hydrated["recordBinding"] == {
        "record_resource": "okf://ons/record/ons-data-api%3Adataset%3Acpih01",
        "record_schema": "okf-ons.mcp-record.v1",
        "record_json_pointer": "/record",
        "canonicalization": "okf-ons.sorted-compact-json.v1",
        "record_sha256": content_sha256(hydrated["record"]),
    }
    assert hydrated["observationsIncluded"] is False
    assert "observation_values" not in canonical_json(hydrated).casefold()


def test_els_indicator_search_alias_and_authority_are_preserved(
    broker: MCPBroker,
) -> None:
    search = _payload(
        broker,
        "okf.search",
        {"query": "Ofcom 4G coverage local authority", "limit": 10},
    )
    assert any(
        candidate["record_id"]
        == "ons-explore-local-statistics:indicator:4g-coverage"
        for candidate in search["candidates"]
    )

    qualified_alias = (
        "ons-explore-local-statistics:indicator:"
        "percentage-of-the-population-aged-0-to-15"
    )
    hydrated = _payload(
        broker,
        "okf.get_record",
        {"identifier": qualified_alias},
    )["record"]
    assert hydrated["id"] == (
        "ons-explore-local-statistics:indicator:percentage-population-aged-0-to-15"
    )
    raw_alias = "percentage-of-the-population-aged-0-to-15"
    raw_hydrated = _payload(
        broker,
        "okf.get_record",
        {"identifier": raw_alias},
    )["record"]
    assert raw_hydrated["id"] == hydrated["id"]
    assert raw_alias in raw_hydrated["native_aliases"]
    assert qualified_alias in raw_hydrated["evaluation_aliases"]
    alias_search = _payload(
        broker,
        "okf.search",
        {"query": raw_alias, "limit": 5},
    )
    assert alias_search["candidates"][0]["record_id"] == hydrated["id"]
    assert hydrated["authority"]["notEndorsedBySource"] is True
    assert hydrated["surface_operator"]["name"] == "Office for National Statistics"
    assert hydrated["metadata_derivation"]["modes"]
    assert hydrated["provenance"]["retrieved_at"] == ""
    assert hydrated["provenance"]["source_commit_as_of"] == "2026-07-17T08:35:03Z"
    assert hydrated["provenance"]["source_commit_as_of_verified"] is True
    plan = _payload(
        broker,
        "okf.prepare_mcp_plan",
        {"record_id": hydrated["id"]},
    )
    assert plan["source_as_of"] == "2026-07-17T08:35:03Z"
    assert plan["source_as_of_basis"] == "provenance.source_commit_as_of"


def test_alias_identity_index_rejects_shadowing_and_cross_record_collisions() -> None:
    canonical_collision = [
        {"id": "record:a", "native_id": "current-a", "native_aliases": ["legacy"]},
        {"id": "record:b", "native_id": "legacy"},
    ]
    with pytest.raises(RuntimeError, match="shadows an existing identity"):
        _build_identity_index(canonical_collision)

    alias_collision = [
        {"id": "record:a", "native_id": "current-a", "native_aliases": ["legacy"]},
        {"id": "record:b", "native_id": "current-b", "native_aliases": ["legacy"]},
    ]
    with pytest.raises(RuntimeError, match="maps to both"):
        _build_identity_index(alias_collision)

    evaluation_collision = [
        {"id": "record:a", "native_id": "current", "evaluation_aliases": []},
        {"id": "record:b", "native_id": "other", "evaluation_aliases": ["current"]},
    ]
    index = _build_identity_index(evaluation_collision)
    assert index["current"] == {"record:a"}


def test_current_els_native_identity_wins_over_legacy_evaluation_alias(
    broker: MCPBroker,
) -> None:
    hydrated = _payload(
        broker,
        "okf.get_record",
        {"identifier": "economic-inactivity-rate"},
    )["record"]
    assert hydrated["id"] == (
        "ons-explore-local-statistics:indicator:economic-inactivity-rate"
    )


def test_search_requires_intent_and_applies_source_filter(broker: MCPBroker) -> None:
    empty = broker.call_tool("okf.search", {"query": ""})
    assert empty["isError"] is True
    assert empty["structuredContent"]["code"] == "INVALID_ARGUMENT"

    stop_words_only = broker.call_tool("okf.search", {"query": "the and of"})
    assert stop_words_only["isError"] is True
    assert stop_words_only["structuredContent"]["code"] == "INVALID_ARGUMENT"

    mismatched = _payload(
        broker,
        "okf.search",
        {"query": "cpih01", "source_surface": "nomis"},
    )
    assert mismatched["candidates"] == []

    unknown_source = broker.call_tool(
        "okf.search",
        {"query": "population", "source_surface": "invented"},
    )
    assert unknown_source["isError"] is True
    assert unknown_source["structuredContent"]["code"] == "INVALID_ARGUMENT"


def test_compare_preserves_cross_source_distinctions(broker: MCPBroker) -> None:
    comparison = _payload(
        broker,
        "okf.compare",
        {
            "record_ids": [
                "ons-data-api:dataset:RM154",
                "nomis:dataset:NM_2254_1",
            ]
        },
    )
    assert comparison["sharedDeclaredTableCodes"] == ["RM154"]
    assert comparison["statisticalEquivalenceAsserted"] is False
    differences = {row["field"] for row in comparison["differences"]}
    assert {"native_id", "source_surface", "record_type"}.issubset(differences)
    assert "reconciliation-not-equivalence" in comparison["materialCaveatIds"]


def test_compare_exposes_els_indicator_disambiguation_fields(broker: MCPBroker) -> None:
    comparison = _payload(
        broker,
        "okf.compare",
        {
            "record_ids": [
                "ons-explore-local-statistics:indicator:population-count",
                "ons-explore-local-statistics:indicator:median-age",
            ]
        },
    )
    rows = {row["field"]: row for row in comparison["fields"]}
    assert {
        "dataset_family",
        "subtopic",
        "measure",
        "unit_of_measure",
        "geography_vintage",
        "source_publishers",
        "metadata_derivation",
    }.issubset(rows)
    assert rows["measure"]["different"] is True
    assert rows["unit_of_measure"]["different"] is True
    assert rows["measure"]["evidence"][0]["json_pointer"] == "/measure"


def test_prepare_mcp_plan_binds_identity_but_never_executes(broker: MCPBroker) -> None:
    plan = _payload(
        broker,
        "okf.prepare_mcp_plan",
        {"record_id": "ons-data-api:dataset:RM154"},
    )
    assert plan["inspection_tool"] == "ons_data.dimensions"
    assert plan["query_tool"] == "ons_data.query"
    assert plan["arguments"] == {
        "dataset": "RM154",
        "edition": "2021",
        "version": "3",
    }
    plan_body = {key: value for key, value in plan.items() if key != "plan_id"}
    assert plan["plan_id"] == "sha256:" + content_sha256(plan_body)
    hydrated = broker.get_record(plan["record_id"])
    assert plan["snapshot_binding"] == {
        "snapshot_id": broker.snapshot_id,
        "snapshot_sha256": broker.snapshot_sha256,
        **hydrated["recordBinding"],
    }
    assert "release_binding" not in plan
    assert plan["source_as_of"] == "2026-07-17T19:22:40.002615Z"
    assert plan["source_as_of_basis"] == "provenance.retrieved_at"
    assert plan["purpose"] is None
    assert plan["purpose_declared"] is False
    assert plan["audience"] is None
    assert plan["audience_declared"] is False
    assert plan["expires_at"] is None
    assert plan["expiry"] == {
        "status": "missing",
        "evaluated": False,
        "required_for_execution": True,
        "evaluation_boundary": "trusted-live-execution-broker",
    }
    assert plan["selection_complete"] is False
    assert plan["frozen_metadata_validated"] is True
    assert plan["live_source_validated"] is False
    assert plan["authorised"] is False
    assert plan["executable"] is False
    assert plan["complete"] is False
    assert plan["unknown_dimensions"]
    assert plan["executed"] is False
    assert plan["validation"]["status"] == "requires-live-inspection"
    assert plan["validation"]["live_validation_performed"] is False

    conflicting = _payload(
        broker,
        "okf.prepare_mcp_plan",
        {
            "record_id": "ons-data-api:dataset:RM154",
            "arguments": {"dataset": "RM154", "edition": "2021", "version": "2"},
        },
    )
    assert conflicting["validation"]["status"] == "invalid-identity"
    assert conflicting["validation"]["identity_binding_valid"] is False
    assert conflicting["frozen_metadata_validated"] is False
    assert conflicting["selection_complete"] is False
    assert conflicting["executable"] is False
    assert conflicting["invalid_options"][0]["argument"] == "version"
    assert conflicting["arguments"]["version"] == "3"

    geography_record = next(
        row for row in broker.records if row["source_surface"] == "ons-open-geography"
    )
    planned = _payload(
        broker,
        "okf.prepare_mcp_plan",
        {"record_id": geography_record["id"]},
    )
    assert planned["validation"]["status"] == "binding-planned"
    assert planned["validation"]["binding_available"] is False
    assert planned["selection_complete"] is False
    assert planned["authorised"] is False
    assert planned["executable"] is False
    assert planned["executed"] is False


def test_prepare_mcp_plan_purpose_and_expiry_are_deterministic(
    broker: MCPBroker,
) -> None:
    first = _payload(
        broker,
        "okf.prepare_mcp_plan",
        {
            "record_id": "ons-data-api:dataset:RM154",
            "audience": "https://example.gov.uk/statistics-query-broker",
            "purpose": "Compare regional population estimates for a research brief",
            "expires_at": "2030-01-01T13:00:00+01:00",
            "arguments": {"time": "latest", "geography": "K02000001"},
        },
    )
    second = _payload(
        broker,
        "okf.prepare_mcp_plan",
        {
            "arguments": {"geography": "K02000001", "time": "latest"},
            "expires_at": "2030-01-01T12:00:00Z",
            "audience": "https://example.gov.uk/statistics-query-broker",
            "purpose": "Compare regional population estimates for a research brief",
            "record_id": "ons-data-api:dataset:RM154",
        },
    )

    assert first == second
    assert first["purpose_declared"] is True
    assert first["audience"] == "https://example.gov.uk/statistics-query-broker"
    assert first["audience_declared"] is True
    assert first["expires_at"] == "2030-01-01T12:00:00Z"
    assert first["expiry"]["status"] == "requires-live-evaluation"
    assert first["expiry"]["evaluated"] is False
    assert first["live_source_validated"] is False
    assert first["authorised"] is False
    assert first["executable"] is False
    assert first["executed"] is False

    changed_purpose = _payload(
        broker,
        "okf.prepare_mcp_plan",
        {
            "record_id": "ons-data-api:dataset:RM154",
            "purpose": "A different declared purpose",
            "expires_at": "2030-01-01T12:00:00Z",
            "arguments": {"time": "latest", "geography": "K02000001"},
        },
    )
    assert changed_purpose["plan_id"] != first["plan_id"]

    definition = next(
        row for row in TOOL_DEFINITIONS if row["name"] == "okf.prepare_mcp_plan"
    )
    assert definition["inputSchema"]["required"] == ["record_id"]
    assert {"audience", "purpose", "expires_at"}.issubset(
        definition["inputSchema"]["properties"]
    )


@pytest.mark.parametrize(
    "arguments",
    [
        {"purpose": "   "},
        {"purpose": "x" * 501},
        {"audience": "   "},
        {"audience": "x" * 501},
        {"expires_at": "2030-01-01T12:00:00"},
        {"expires_at": "20300101T120000Z"},
        {"expires_at": "not-a-date"},
    ],
)
def test_prepare_mcp_plan_rejects_invalid_purpose_or_expiry(
    broker: MCPBroker,
    arguments: dict,
) -> None:
    result = broker.call_tool(
        "okf.prepare_mcp_plan",
        {"record_id": "ons-data-api:dataset:RM154", **arguments},
    )
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == "INVALID_ARGUMENT"


def test_submit_answer_returns_deterministic_non_persisted_receipt(
    broker: MCPBroker,
) -> None:
    submission = {
        "task_id": "AI-SMOKE-006",
        "chosen_record_id": "ons-data-api:dataset:RM154",
        "considered_record_ids": [
            "ons-data-api:dataset:RM154",
            "nomis:dataset:NM_2254_1",
        ],
        "alternatives": [{"record_id": "nomis:dataset:NM_2254_1"}],
        "contrasts": [
            {
                "record_id": "nomis:dataset:NM_2254_1",
                "field": "source_surface",
            }
        ],
        "evidence": [
            {
                "kind": "identity",
                "record_id": "ons-data-api:dataset:RM154",
                "json_pointer": "/id",
            }
        ],
        "caveat_ids": [
            "selection-incomplete-no-execution",
            "reconciliation-not-equivalence",
        ],
        "confidence": 0.9,
        "answer": "RM154 is selected; the plan remains incomplete and was not executed.",
        "mcp_plan": {
            "record_id": "ons-data-api:dataset:RM154",
            "executed": False,
        },
        "substitution": {"used": False, "disclosed": False},
    }
    first = _payload(broker, "okf_eval.submit_answer", submission)
    second = _payload(broker, "okf_eval.submit_answer", submission)
    assert first == second
    assert first["accepted"] is True
    assert first["persisted"] is False
    assert first["hiddenReasoningCollected"] is False
    assert first["assessment"]["status"] == "required"
    assert len(first["submissionSha256"]) == 64
    assert len(first["visibleAnswerSha256"]) == 64


@pytest.mark.parametrize(
    ("arguments", "expected_code"),
    [
        (
            {
                "task_id": "AI-SMOKE-001",
                "chosen_record_id": None,
                "considered_record_ids": [],
                "alternatives": [],
                "evidence": [],
                "caveat_ids": ["metadata-only"],
                "confidence": 0.5,
                "answer": "Visible answer",
                "reasoning": "hidden",
            },
            "PROHIBITED_INPUT",
        ),
        (
            {
                "task_id": "AI-SMOKE-001",
                "chosen_record_id": None,
                "considered_record_ids": [],
                "alternatives": [],
                "evidence": [],
                "caveat_ids": ["metadata-only"],
                "confidence": 0.5,
                "answer": "Token sk-this-must-not-be-collected",
            },
            "PROHIBITED_INPUT",
        ),
    ],
)
def test_submit_answer_rejects_hidden_reasoning_and_credentials(
    broker: MCPBroker,
    arguments: dict,
    expected_code: str,
) -> None:
    result = broker.call_tool("okf_eval.submit_answer", arguments)
    assert result["isError"] is True
    assert result["structuredContent"]["code"] == expected_code


def test_json_lines_transport_supports_mcp_without_stdout_logs(broker: MCPBroker) -> None:
    messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        },
        {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        },
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {"jsonrpc": "2.0", "id": 3, "method": "resources/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "resources/read",
            "params": {"uri": "okf://ons/descriptor"},
        },
        {"jsonrpc": "2.0", "id": 5, "method": "ping", "params": {}},
    ]
    input_stream = io.StringIO(
        "".join(canonical_json(message) + "\n" for message in messages)
    )
    output_stream = io.StringIO()
    assert serve(broker, input_stream=input_stream, output_stream=output_stream) == 0

    responses = [
        json.loads(line) for line in output_stream.getvalue().splitlines()
    ]
    assert [row["id"] for row in responses] == [1, 2, 3, 4, 5]
    assert responses[0]["result"]["serverInfo"]["name"] == "okf-ons-metadata-broker"
    assert responses[0]["result"]["protocolVersion"] == "2025-06-18"
    assert {
        row["name"] for row in responses[1]["result"]["tools"]
    } == {
        "okf.descriptor",
        "okf.search",
        "okf.get_record",
        "okf.compare",
        "okf.prepare_mcp_plan",
        "okf_eval.submit_answer",
    }
    descriptor = json.loads(
        responses[3]["result"]["contents"][0]["text"]
    )
    assert descriptor["metadataOnly"] is True
    assert responses[4]["result"] == {}

    parse_error = json.loads(handle_line(broker, "{not-json") or "")
    assert parse_error["error"]["code"] == -32700

    unsupported = json.loads(
        handle_line(
            broker,
            canonical_json(
                {
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "initialize",
                    "params": {"protocolVersion": "2099-01-01"},
                }
            ),
        )
        or ""
    )
    assert unsupported["result"]["protocolVersion"] == "2025-11-25"

    current = json.loads(
        handle_line(
            broker,
            canonical_json(
                {
                    "jsonrpc": "2.0",
                    "id": 7,
                    "method": "initialize",
                    "params": {"protocolVersion": "2025-11-25"},
                }
            ),
        )
        or ""
    )
    assert current["result"]["protocolVersion"] == "2025-11-25"


def test_submit_answer_schema_matches_runtime_required_fields() -> None:
    definition = next(
        row for row in TOOL_DEFINITIONS if row["name"] == "okf_eval.submit_answer"
    )
    assert "chosen_record_id" in definition["inputSchema"]["required"]


def test_antigravity_workspace_configuration_uses_repo_relative_launcher() -> None:
    config = json.loads((ROOT / ".agents" / "mcp_config.json").read_text())
    server = config["mcpServers"]["okf-ons"]
    assert server == {
        "command": "python3",
        "args": ["scripts/okf_ons_mcp.py"],
        "cwd": ".",
    }
    assert all("/Users/" not in value for value in server["args"])
