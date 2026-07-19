from __future__ import annotations

import copy
import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from okf_ons.ai_evaluation import (  # noqa: E402
    LOCAL_CLIENT_PROBES,
    AIEvaluationError,
    build_report,
    create_run_template,
    dumps_json,
    load_harness,
    score_run,
    validate_research_artifacts,
    validate_run,
)

ASSESSMENT_PROVENANCE = hashlib.sha256(b"okf-ons-validated-test-assessor-v1").hexdigest()


def _trace_reference(relative: str) -> dict:
    return {
        "schema": "okf-ons.enforcement-evidence-reference.v1",
        "trace_path": relative,
        "trace_sha256": hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(),
    }


@pytest.fixture(scope="module")
def harness() -> dict:
    return load_harness(ROOT)


def _complete_run(harness: dict, *, run_id: str = "test-cpih") -> dict:
    run = create_run_template(
        harness,
        run_id=run_id,
        client_profile="codex-cli",
        arm_id="okf-bundle",
        delivery_mode="controlled-broker",
        task_id="AI-SMOKE-003",
        replicate=1,
    )
    run["status"] = "completed"
    run["access"]["enforcement"] = "enforced"
    run["access"]["evidence"] = [
        _trace_reference(
            "evaluation/ai-client/fixtures/access-okf-bundle-enforced.json"
        )
    ]
    run["capture"]["fidelity"] = "fixture-replay"
    run["answer"] = {
        "chosen_record_id": "ons-data-api:dataset:cpih01",
        "chosen_native_id": "cpih01",
        "chosen_source_surface": "ons-data-api",
        "chosen_edition": "time-series",
        "chosen_version": "67",
        "considered_record_ids": ["ons-data-api:dataset:cpih01"],
        "alternatives": [],
        "evidence": [
            {"kind": "identity", "json_pointer": "/identity", "claim": "Exact identity"},
            {
                "kind": "provenance",
                "json_pointer": "/provenance",
                "claim": "Source evidence",
            },
            {"kind": "quality", "json_pointer": "/quality_evidence", "claim": "Boundary"},
        ],
        "caveat_ids": [
            "accuracy-not-evaluated",
            "evidence-not-fitness-certification",
        ],
        "hydration": {"status": "complete"},
        "mcp_plan": None,
        "substitution": {"used": False, "disclosed": False},
        "confidence": 0.98,
        "answer": (
            "The exact CPIH record, its identity and provenance are cited. "
            "Metadata evidence does not evaluate statistical accuracy or certify "
            "fitness for use."
        ),
    }
    run["assessment"] = {
        "method": "validated-fixture",
        "assessor_alias": "test-assessor",
        "independent_of_client": True,
        "provenance_sha256": ASSESSMENT_PROVENANCE,
        "visible_answer_sha256": hashlib.sha256(
            run["answer"]["answer"].encode("utf-8")
        ).hexdigest(),
        "supported_caveat_ids": [
            "accuracy-not-evaluated",
            "evidence-not-fitness-certification",
        ],
        "supported_evidence_kinds": ["identity", "provenance", "quality"],
        "unsupported_claims": [],
        "evidence_spans": [
            {"criterion": "caveat:accuracy-not-evaluated", "quote": "does not evaluate"},
            {
                "criterion": "caveat:evidence-not-fitness-certification",
                "quote": "or certify fitness for use",
            },
            {"criterion": "evidence:identity", "quote": "identity"},
            {"criterion": "evidence:provenance", "quote": "provenance"},
            {"criterion": "evidence:quality", "quote": "Metadata evidence"},
        ],
    }
    validate_run(run, harness)
    return run


def test_committed_harness_is_cross_validated_and_has_three_arms(harness: dict) -> None:
    assert harness["study"]["study_id"] == "okf-ons-ai-client-smoke-v1"
    assert set(harness["_ids"]["arms"]) == {"okf-bundle", "open-web", "raw-api"}
    assert len(harness["_ids"]["modes"]) == 2
    assert len(harness["_ids"]["tasks"]) == 8
    assert len(harness["_ids"]["profiles"]) >= 14
    assert len(harness["_ids"]["journeys"]) == 8
    assert len(harness["_ids"]["issues"]) == 10
    assert set(harness["_ids"]["profiles"]) == set(LOCAL_CLIENT_PROBES)
    assert harness["tasks"]["confirmatory_eligible"] is False
    assert harness["expected"]["statistical_accuracy"]["evaluated"] is False


def test_research_sources_are_hash_pinned_and_docx_is_safe() -> None:
    report = validate_research_artifacts(ROOT)

    assert report["trial_count"] == 3
    assert report["authoritative_artifact"] == (
        "2026-07-18-claude-desktop-cowork-fable-5-okf-ons-access-trace.md"
    )
    assert report["docx_structurally_valid"] is True
    assert report["docx_macros_present"] is False
    assert report["docx_page_field_present"] is True
    assert report["docx_public_metadata_safe"] is True
    assert len(report["docx_artifacts"]) == 3
    assert all(
        row["public_inspection"]["public_metadata_safe"]
        for row in report["docx_artifacts"]
    )
    assert {row["path"] for row in report["artifacts"]} == {
        "2026-07-18-claude-desktop-cowork-fable-5-okf-ons-access-trace.md",
        (
            "2026-07-18-claude-desktop-cowork-fable-5-"
            "okf-ons-access-trace-public-sanitized.docx"
        ),
        "2026-07-18-antigravity-cli-gemini-3-1-pro-okf-ons-postmortem.md",
        "2026-07-18-antigravity-cli-gemini-3-1-pro-okf-ons-briefing.md",
        (
            "2026-07-18-m365-copilot-researcher-"
            "okf-ons-access-briefing-public-sanitized.docx"
        ),
        (
            "2026-07-18-m365-copilot-researcher-"
            "okf-hosting-research-public-sanitized.docx"
        ),
    }


def test_run_template_is_deterministic_and_unstarted(harness: dict) -> None:
    arguments = {
        "run_id": "deterministic-run",
        "client_profile": "claude-code",
        "arm_id": "raw-api",
        "delivery_mode": "native-access",
        "task_id": "AI-SMOKE-004",
        "replicate": 2,
    }
    first = create_run_template(harness, **arguments)
    second = create_run_template(harness, **arguments)

    assert dumps_json(first) == dumps_json(second)
    assert first["status"] == "not-run"
    assert first["answer"] is None
    assert first["capture"]["hidden_reasoning_collected"] is False


def test_perfect_cpih_run_passes_strict_primary_outcome(harness: dict) -> None:
    score = score_run(_complete_run(harness), harness)

    assert score["eligible"] is True
    assert score["validation_eligible"] is True
    assert score["comparative_eligible"] is False
    assert score["comparative_exclusion_reason"] == "fixture-replay"
    assert score["safe_exact_selection"] == 1.0
    assert score["all_applicable_components_pass"] is True
    assert score["components"]["hydration"]["score"] == 1.0
    assert score["components"]["caveat_fidelity"]["score"] == 1.0
    assert score["statistical_accuracy"]["evaluated"] is False


def test_missing_caveat_and_critical_claim_fail_without_hiding_diagnostics(
    harness: dict,
) -> None:
    run = _complete_run(harness)
    run["assessment"]["supported_caveat_ids"] = ["accuracy-not-evaluated"]
    run["assessment"]["unsupported_claims"] = [
        {"claim": "Aligned means certified.", "severity": "critical"}
    ]
    run["answer"]["answer"] += " Aligned means certified."
    run["assessment"]["visible_answer_sha256"] = hashlib.sha256(
        run["answer"]["answer"].encode("utf-8")
    ).hexdigest()
    run["assessment"]["evidence_spans"].append(
        {"criterion": "unsupported:0", "quote": "Aligned means certified."}
    )

    score = score_run(run, harness)

    assert score["safe_exact_selection"] == 0.0
    assert score["components"]["caveat_fidelity"]["score"] == 0.5
    assert score["components"]["unsupported_claim_safety"]["critical_count"] == 1


def test_missing_assessment_cannot_receive_a_safety_pass(harness: dict) -> None:
    run = _complete_run(harness)
    run["access"]["enforcement"] = "self-reported"
    run["access"]["evidence"] = []
    run["assessment"] = None

    score = score_run(run, harness)

    assert score["components"]["assessment_present"]["score"] == 0.0
    assert score["components"]["unsupported_claim_safety"]["score"] == 0.0
    assert score["components"]["caveat_fidelity"]["score"] == 0.0
    assert score["safe_exact_selection"] == 0.0


def test_blocked_readiness_is_excluded_instead_of_scored_zero(harness: dict) -> None:
    blocked = create_run_template(
        harness,
        run_id="blocked-client",
        client_profile="claude-desktop",
        arm_id="okf-bundle",
        delivery_mode="controlled-broker",
        task_id="AI-SMOKE-003",
        replicate=1,
    )
    blocked["status"] = "blocked"
    blocked["failures"] = [
        {"code": "CLIENT_NOT_READY", "stage": "readiness", "detail": "No broker"}
    ]

    report = build_report([_complete_run(harness), blocked], harness)

    assert report["aggregate"]["run_count"] == 2
    assert report["aggregate"]["eligible_run_count"] == 0
    assert report["aggregate"]["blocked_run_count"] == 1
    assert report["aggregate"]["safe_exact_selection"] == {
        "mean": None,
        "denominator": 0,
    }
    assert report["validation_aggregate"]["eligible_run_count"] == 1
    assert report["validation_aggregate"]["safe_exact_selection"] == {
        "mean": 1.0,
        "denominator": 1,
    }
    assert report["descriptive_aggregate"]["eligible_run_count"] == 1
    assert report["failure_summary"] == [
        {
            "code": "CLIENT_NOT_READY",
            "count": 1,
            "issue_ids": ["AI-ISSUE-006"],
        }
    ]
    assert all(
        coverage == {
            "known_run_count": 0,
            "exact_run_count": 0,
            "qualified_run_count": 0,
            "unknown_or_missing_run_count": 2,
        }
        for coverage in report["efficiency"]["telemetry_coverage"].values()
    )


def test_failure_codes_must_be_stable_identifiers(harness: dict) -> None:
    run = _complete_run(harness)
    run["failures"] = [{"code": "server-not-ready", "stage": "readiness"}]

    with pytest.raises(AIEvaluationError, match="uppercase stable identifier"):
        validate_run(run, harness)

    run["failures"] = [{"code": "CLIENT_NOT_REDAY", "stage": "readiness"}]
    with pytest.raises(AIEvaluationError, match="is not registered"):
        validate_run(run, harness)


def test_arm_violation_is_invalid_but_retained_in_report(harness: dict) -> None:
    run = _complete_run(harness)
    run["access"]["violations"] = [
        {
            "code": "DENIED_ORIGIN",
            "origin": "https://api.beta.ons.gov.uk",
        }
    ]

    score = score_run(run, harness)

    assert score["eligible"] is False
    assert score["exclusion_reason"] == "arm-violation"
    assert score["safe_exact_selection"] == 0.0


def test_self_reported_arm_is_descriptive_not_comparative(harness: dict) -> None:
    run = _complete_run(harness)
    run["access"]["enforcement"] = "self-reported"
    run["access"]["evidence"] = []

    score = score_run(run, harness)
    report = build_report([run], harness)

    assert score["eligible"] is True
    assert score["validation_eligible"] is False
    assert score["comparative_eligible"] is False
    assert score["comparative_exclusion_reason"] == "arm-not-enforced"
    assert report["aggregate"]["safe_exact_selection"]["denominator"] == 0
    assert report["validation_aggregate"]["safe_exact_selection"]["denominator"] == 0
    assert report["descriptive_aggregate"]["safe_exact_selection"]["denominator"] == 1


def test_enforced_access_rejects_placeholder_evidence(harness: dict) -> None:
    run = _complete_run(harness)
    run["access"]["evidence"] = [None]

    with pytest.raises(AIEvaluationError, match=r"access-policy evidence\[0\]"):
        validate_run(run, harness)


def test_fault_profile_must_be_applied_and_evidenced(harness: dict) -> None:
    run = create_run_template(
        harness,
        run_id="constrained-cpih",
        client_profile="codex-cli",
        arm_id="okf-bundle",
        delivery_mode="controlled-broker",
        task_id="AI-SMOKE-007",
        replicate=1,
    )
    source = _complete_run(harness)
    run["status"] = "completed"
    run["access"]["enforcement"] = "enforced"
    run["access"]["evidence"] = [
        _trace_reference(
            "evaluation/ai-client/fixtures/access-okf-bundle-constrained-cpih.json"
        )
    ]
    run["capture"] = source["capture"]
    run["answer"] = source["answer"]
    run["assessment"] = source["assessment"]

    unbound = score_run(run, harness)
    assert unbound["eligible"] is False
    assert unbound["exclusion_reason"] == "constraints-not-evidenced"

    run["constraints"]["enforcement"] = "observed"
    with pytest.raises(AIEvaluationError, match="requires typed trace evidence"):
        validate_run(run, harness)

    run["constraints"]["evidence"] = [
        _trace_reference(
            "evaluation/ai-client/fixtures/constraints-ai-smoke-007-enforced.json"
        )
    ]
    observed = score_run(run, harness)
    assert observed["eligible"] is True
    assert observed["comparative_eligible"] is False
    assert observed["comparative_exclusion_reason"] == "constraints-not-enforced"

    run["constraints"]["enforcement"] = "enforced"
    enforced = score_run(run, harness)
    assert enforced["validation_eligible"] is True
    assert enforced["comparative_eligible"] is False
    assert enforced["comparative_exclusion_reason"] == "fixture-replay"


def test_enforcement_trace_is_bound_to_exact_run_and_capture(harness: dict) -> None:
    run = _complete_run(harness)
    run["run_id"] = "relabelled-run"

    with pytest.raises(AIEvaluationError, match="not bound to this run and capture"):
        validate_run(run, harness)


def test_mcp_plan_validates_identity_tools_arguments_and_non_execution(harness: dict) -> None:
    run = create_run_template(
        harness,
        run_id="rm154-plan",
        client_profile="codex-cli",
        arm_id="okf-bundle",
        delivery_mode="controlled-broker",
        task_id="AI-SMOKE-006",
        replicate=1,
    )
    run["status"] = "completed"
    run["access"]["enforcement"] = "enforced"
    run["access"]["evidence"] = [
        _trace_reference(
            "evaluation/ai-client/fixtures/access-okf-bundle-rm154-plan.json"
        )
    ]
    run["capture"]["fidelity"] = "fixture-replay"
    events_path = "evaluation/ai-client/fixtures/mcp-plan-inspection-only.jsonl"
    events_sha256 = hashlib.sha256((ROOT / events_path).read_bytes()).hexdigest()
    run["capture"]["events_path"] = events_path
    run["capture"]["events_sha256"] = events_sha256
    run["answer"] = {
        "chosen_record_id": "ons-data-api:dataset:RM154",
        "chosen_native_id": "RM154",
        "chosen_source_surface": "ons-data-api",
        "chosen_edition": "2021",
        "chosen_version": "3",
        "considered_record_ids": ["ons-data-api:dataset:RM154"],
        "alternatives": [],
        "evidence": [{"kind": "identity"}, {"kind": "mcp-selection"}],
        "caveat_ids": ["selection-incomplete-no-execution"],
        "hydration": {"status": "complete"},
        "mcp_plan": {
            "source": "ons-data-api",
            "record_id": "ons-data-api:dataset:RM154",
            "inspection_tool": "ons_data.dimensions",
            "query_tool": "ons_data.query",
            "arguments": {"dataset": "RM154", "edition": "2021", "version": "3"},
            "complete": False,
            "unknown_dimensions": [
                {
                    "dimension": "dataset-specific dimension options",
                    "record_id": "ons-data-api:dataset:RM154",
                    "json_pointer": "/selection/reason",
                }
            ],
            "executed": False,
            "execution_evidence": {
                "events_sha256": events_sha256,
                "query_tool_call_count": 0,
            },
        },
        "substitution": {"used": False, "disclosed": False},
        "confidence": 0.9,
        "answer": "The plan is incomplete and was not executed.",
    }
    run["assessment"] = {
        "method": "validated-fixture",
        "assessor_alias": "test-assessor",
        "independent_of_client": True,
        "provenance_sha256": ASSESSMENT_PROVENANCE,
        "visible_answer_sha256": hashlib.sha256(
            run["answer"]["answer"].encode("utf-8")
        ).hexdigest(),
        "supported_caveat_ids": ["selection-incomplete-no-execution"],
        "supported_evidence_kinds": ["identity", "mcp-selection"],
        "unsupported_claims": [],
        "evidence_spans": [
            {
                "criterion": "caveat:selection-incomplete-no-execution",
                "quote": "incomplete and was not executed",
            },
            {"criterion": "evidence:identity", "quote": "plan"},
            {"criterion": "evidence:mcp-selection", "quote": "plan"},
        ],
    }

    assert score_run(run, harness)["components"]["mcp_plan"]["score"] == 1.0
    run["answer"]["mcp_plan"]["arguments"]["version"] = "2"
    assert score_run(run, harness)["components"]["mcp_plan"]["score"] == 0.0
    run["answer"]["mcp_plan"]["arguments"]["version"] = "3"
    run["answer"]["mcp_plan"]["arguments"]["geography"] = "invented"
    assert score_run(run, harness)["components"]["mcp_plan"]["score"] == 0.0


def test_client_self_assessment_method_is_rejected(harness: dict) -> None:
    run = _complete_run(harness)
    run["assessment"]["method"] = "client-self-assessment"

    with pytest.raises(AIEvaluationError, match="method must be"):
        validate_run(run, harness)


def test_estimated_telemetry_cannot_be_relabelled_exact(harness: dict) -> None:
    run = _complete_run(harness)
    run["telemetry"] = {
        "provider_input_tokens": {
            "value": 2000,
            "unit": "tokens",
            "exact": True,
            "source": "estimated from characters",
            "scope": "native provider telemetry only; null when not exposed",
        }
    }

    with pytest.raises(AIEvaluationError, match="cannot label an estimate as exact"):
        validate_run(run, harness)


def test_telemetry_names_units_and_scopes_follow_the_study(harness: dict) -> None:
    run = _complete_run(harness)
    run["telemetry"] = {
        "invented_metric": {
            "value": 1,
            "unit": "widgets",
            "exact": True,
            "source": "test",
            "scope": "one run",
        }
    }
    with pytest.raises(AIEvaluationError, match="unregistered measures"):
        validate_run(run, harness)

    run["telemetry"] = {
        "elapsed_time": {
            "value": 1,
            "unit": "fortnights",
            "exact": True,
            "source": "monotonic clock",
            "scope": "task start to submitted visible structured answer",
        }
    }
    with pytest.raises(AIEvaluationError, match="unit must be 'milliseconds'"):
        validate_run(run, harness)


def test_public_run_rejects_secrets_machine_paths_and_hidden_reasoning(harness: dict) -> None:
    run = _complete_run(harness)
    run["answer"]["answer"] += " Trace stored at /Users/example/private/run.json"
    run["assessment"]["visible_answer_sha256"] = hashlib.sha256(
        run["answer"]["answer"].encode("utf-8")
    ).hexdigest()
    with pytest.raises(AIEvaluationError, match="prohibited pattern"):
        validate_run(run, harness)

    run = _complete_run(harness)
    run["answer"]["chain_of_thought"] = "private"
    with pytest.raises(AIEvaluationError, match="forbidden key"):
        validate_run(run, harness)


def test_report_is_byte_deterministic(harness: dict) -> None:
    run = _complete_run(harness)
    run["telemetry"] = {
        "elapsed_time": {
            "value": 1250,
            "unit": "milliseconds",
            "exact": True,
            "source": "monotonic clock",
            "scope": "task start to submitted visible structured answer",
        }
    }

    first = build_report([run], harness)
    second = build_report([copy.deepcopy(run)], harness)

    assert dumps_json(first) == dumps_json(second)
    assert "generated_at" not in first
    assert first["interpretation"]["blocked_is_not_zero"] is True
    assert len(first["personas_and_journeys_digest_sha256"]) == 64
    assert len(first["issue_register_digest_sha256"]) == 64
    assert set(first["efficiency"]["telemetry_coverage"]) == {
        row["id"] for row in harness["study"]["efficiency_outcomes"]["measures"]
    }
    elapsed = first["efficiency"]["measures"]["elapsed_time"]
    assert elapsed["coverage"]["exact_run_count"] == 1
    assert elapsed["measurements"][0]["value"] == 1250
    assert elapsed["measurements"][0]["source"] == "monotonic clock"
    assert elapsed["measurements"][0]["comparative_eligible"] is False
    assert elapsed["comparative_cells"] == []
