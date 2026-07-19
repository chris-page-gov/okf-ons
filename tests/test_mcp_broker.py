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
    canonical_json,
    handle_line,
    serve,
)


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
    assert descriptor["snapshotId"] == "monday-2026-07-17"
    assert descriptor["scope"]["record_count"] == 4_989
    assert descriptor["scope"]["complete_ons_corpus"] is False
    assert descriptor["metadataOnly"] is True
    assert descriptor["observationsIncluded"] is False
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
    assert hydrated["observationsIncluded"] is False
    assert "observation_values" not in canonical_json(hydrated).casefold()


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
    assert planned["executed"] is False


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
    assert unsupported["result"]["protocolVersion"] == "2025-06-18"


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
