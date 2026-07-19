"""Provider-neutral capture and scoring for AI access to OKF-ONS metadata.

The harness makes study inputs, run capture, replay and scoring deterministic.
It does not claim that model output is deterministic and it never evaluates
the accuracy of ONS observations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import zipfile
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from okf_ons.docx_release import DocxReleaseError, inspect_public_docx

STUDY_SCHEMA = "okf-ons.ai-client-study.v1"
TASKS_SCHEMA = "okf-ons.ai-client-task-suite.v1"
EXPECTED_SCHEMA = "okf-ons.ai-client-expected.v1"
PROFILES_SCHEMA = "okf-ons.ai-client-profiles.v1"
PERSONAS_SCHEMA = "okf-ons.ai-persona-journeys.v1"
ISSUES_SCHEMA = "okf-ons.ai-client-issue-register.v1"
RUN_SCHEMA = "okf-ons.ai-client-run.v1"
SCORE_SCHEMA = "okf-ons.ai-client-score.v1"
REPORT_SCHEMA = "okf-ons.ai-client-report.v1"

TASK_STATUSES = frozenset({"completed", "degraded", "failed", "blocked", "not-run"})
ENFORCEMENT_VALUES = frozenset({"enforced", "observed", "self-reported"})
CONSTRAINT_ENFORCEMENT_VALUES = frozenset(
    {"not-applicable", "enforced", "observed", "self-reported", "not-applied"}
)
CAPTURE_FIDELITIES = frozenset(
    {
        "native-export",
        "contemporaneous-log",
        "reconstruction",
        "fixture-replay",
        "not-captured",
    }
)
FORBIDDEN_PUBLIC_KEYS = frozenset(
    {
        "analysis",
        "chain_of_thought",
        "chainofthought",
        "hidden_reasoning",
        "private_reasoning",
        "raw_chain_of_thought",
    }
)
SECRET_PATTERNS = (
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(
        r"(?i)\b(?:authorization|api[-_ ]?key|access[-_ ]?token)"
        r"\s*[:=]\s*[\"']?[A-Za-z0-9._~+/-]{12,}"
    ),
    re.compile(r"(?:/Users/|/Volumes/|/private/tmp/|/tmp/)[^\s\"']+"),
)
ACCURACY_BOUNDARY = (
    "The harness evaluates metadata discovery behaviour and evidence handling. "
    "It does not establish the accuracy of ONS observations, estimates or interpretations."
)
LOCAL_CLIENT_PROBES: dict[str, dict[str, tuple[str, ...]]] = {
    "codex-cli": {"command": ("codex", "--version")},
    "claude-code": {"command": ("claude", "--version")},
    "gemini-cli": {"command": ("gemini", "--version")},
    "google-antigravity-cli": {"command": ("agy", "--version")},
    "vscode-agent": {"command": ("code", "--version")},
    "claude-cowork": {"applications": ("Claude.app",)},
    "claude-desktop": {"applications": ("Claude.app",)},
    "codex-desktop": {"applications": ("ChatGPT.app",)},
    "chatgpt-classic": {"applications": ("ChatGPT Classic.app",)},
    "chatgpt-atlas": {"applications": ("ChatGPT Atlas.app",)},
    "microsoft-copilot": {"applications": ("Copilot.app",)},
    "microsoft-365-copilot": {"applications": ("Microsoft 365 Copilot.app",)},
    "m365-copilot-researcher-edge": {"applications": ("Microsoft Edge.app",)},
    "github-copilot": {"applications": ("GitHub Copilot.app",)},
    "github-copilot-xcode": {"applications": ("GitHub Copilot for Xcode.app",)},
    "mcp-inspector": {"commands": ("mcp-inspector",)},
}


class AIEvaluationError(ValueError):
    """Raised when an AI-evaluation artifact violates the public contract."""


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as error:
        raise AIEvaluationError(f"value is not canonical JSON: {error}") from error


def dumps_json(value: object) -> str:
    """Return stable, human-readable JSON."""

    try:
        return (
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
    except (TypeError, ValueError) as error:
        raise AIEvaluationError(f"value is not serialisable JSON: {error}") from error


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AIEvaluationError(f"unable to load JSON object {path}: {error}") from error
    if not isinstance(value, dict):
        raise AIEvaluationError(f"expected a JSON object: {path}")
    return value


def _repository_evidence_path(
    harness: Mapping[str, Any],
    relative: object,
    *,
    label: str,
) -> Path:
    text = _require_string(relative, label)
    path = Path(text)
    if path.is_absolute() or ".." in path.parts:
        raise AIEvaluationError(f"{label} must be a repository-relative path")
    resolved = Path(harness["_context"]["root"]) / path
    if not resolved.is_file():
        raise AIEvaluationError(f"{label} does not exist: {text}")
    return resolved


def _validate_enforcement_evidence(
    evidence: Sequence[object],
    *,
    subject: object,
    subject_type: str,
    harness: Mapping[str, Any],
    run: Mapping[str, Any],
) -> bool:
    if not evidence:
        raise AIEvaluationError(f"{subject_type} enforcement requires typed trace evidence")
    required_access_results = {
        "origin-path-policy",
        "http-method-policy",
        "credential-policy",
        "redirect-policy",
    }
    fixture_only = False
    for index, reference in enumerate(evidence):
        label = f"{subject_type} evidence[{index}]"
        if not isinstance(reference, Mapping):
            raise AIEvaluationError(f"{label} must be an object")
        if reference.get("schema") != "okf-ons.enforcement-evidence-reference.v1":
            raise AIEvaluationError(f"{label} has an unsupported schema")
        path = _repository_evidence_path(
            harness,
            reference.get("trace_path"),
            label=f"{label}.trace_path",
        )
        trace_digest = reference.get("trace_sha256")
        if not _is_sha256(trace_digest) or _file_digest(path) != trace_digest:
            raise AIEvaluationError(f"{label}.trace_sha256 does not match its trace")
        trace = _load_object(path)
        if trace.get("schema") != "okf-ons.enforcement-trace.v1":
            raise AIEvaluationError(f"{label} points to an unsupported trace")
        if trace.get("subject_type") != subject_type:
            raise AIEvaluationError(f"{label} has the wrong subject type")
        if trace.get("subject_sha256") != _digest(subject):
            raise AIEvaluationError(f"{label} is not bound to the selected policy/profile")
        enforcer = trace.get("enforcer")
        if not isinstance(enforcer, Mapping):
            raise AIEvaluationError(f"{label} has no enforcer identity")
        _require_string(enforcer.get("id"), f"{label}.enforcer.id")
        _require_string(enforcer.get("version"), f"{label}.enforcer.version")
        run_binding = trace.get("run_binding")
        if not isinstance(run_binding, Mapping):
            raise AIEvaluationError(f"{label} has no run binding")
        expected_binding = {
            "run_id": run["run_id"],
            "client_profile_id": run["client"]["profile_id"],
            "arm_id": run["arm_id"],
            "capture_sha256": _digest(run["capture"]),
        }
        if dict(run_binding) != expected_binding:
            raise AIEvaluationError(f"{label} is not bound to this run and capture")
        if trace.get("fixture_only") is True:
            fixture_only = True
        results = _require_list(trace.get("results"), f"{label}.results")
        by_id: dict[str, Mapping[str, Any]] = {}
        for result_index, result in enumerate(results):
            if not isinstance(result, Mapping):
                raise AIEvaluationError(f"{label}.results[{result_index}] must be an object")
            result_id = _require_string(
                result.get("id"),
                f"{label}.results[{result_index}].id",
            )
            if result_id in by_id:
                raise AIEvaluationError(f"{label} has duplicate result ID: {result_id}")
            by_id[result_id] = result
        if subject_type == "access-policy":
            missing = required_access_results - set(by_id)
            if missing or trace.get("redirects_checked") is not True:
                raise AIEvaluationError(
                    f"{label} is missing access enforcement checks: {sorted(missing)}"
                )
            if any(
                by_id[result_id].get("passed") is not True
                for result_id in required_access_results
            ):
                raise AIEvaluationError(f"{label} contains a failed access enforcement check")
        elif subject_type == "fault-profile":
            if not isinstance(subject, Mapping):
                raise AIEvaluationError("fault profile must be an object")
            for constraint, expected in subject.items():
                result_id = f"constraint:{constraint}"
                result = by_id.get(result_id)
                if (
                    result is None
                    or result.get("passed") is not True
                    or result.get("observed") != expected
                ):
                    raise AIEvaluationError(
                        f"{label} did not enforce {constraint}={expected!r}"
                    )
        else:  # pragma: no cover - internal caller contract
            raise AssertionError(subject_type)
    return fixture_only


def _capture_events(
    run: Mapping[str, Any],
    harness: Mapping[str, Any],
) -> list[dict[str, Any]]:
    capture = run.get("capture")
    if not isinstance(capture, Mapping):
        return []
    relative = capture.get("events_path")
    digest = capture.get("events_sha256")
    if relative is None and digest is None:
        return []
    path = _repository_evidence_path(
        harness,
        relative,
        label="run.capture.events_path",
    )
    if not _is_sha256(digest) or _file_digest(path) != digest:
        raise AIEvaluationError("run.capture.events_sha256 does not match the events file")
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise AIEvaluationError(
                f"run capture event line {line_number} is invalid JSON"
            ) from error
        if not isinstance(event, dict) or event.get("seq") != line_number:
            raise AIEvaluationError(
                f"run capture event line {line_number} has an invalid sequence"
            )
        events.append(event)
    return events


def _require_string(value: object, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        qualifier = "a string" if allow_empty else "a non-empty string"
        raise AIEvaluationError(f"{label} must be {qualifier}")
    return value.strip() if not allow_empty else value


def _require_list(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise AIEvaluationError(f"{label} must be a list")
    return value


def _unique_ids(rows: object, label: str, *, key: str = "id") -> set[str]:
    values = _require_list(rows, label)
    identifiers: set[str] = set()
    for index, row in enumerate(values):
        if not isinstance(row, Mapping):
            raise AIEvaluationError(f"{label}[{index}] must be an object")
        identifier = _require_string(row.get(key), f"{label}[{index}].{key}")
        if identifier in identifiers:
            raise AIEvaluationError(f"duplicate {label} identifier: {identifier}")
        identifiers.add(identifier)
    return identifiers


def _walk_keys(value: object) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalised = str(key).strip().casefold().replace("-", "_")
            if normalised in FORBIDDEN_PUBLIC_KEYS:
                raise AIEvaluationError(f"public artifact contains forbidden key: {key}")
            _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            _walk_keys(child)


def validate_public_value(value: object) -> None:
    """Reject obvious secrets, machine paths and hidden-reasoning fields."""

    _walk_keys(value)
    text = _canonical_json(value)
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            raise AIEvaluationError(
                f"public artifact matched prohibited pattern: {pattern.pattern}"
            )


def validate_profiles(profiles: Mapping[str, Any]) -> set[str]:
    if profiles.get("schema") != PROFILES_SCHEMA:
        raise AIEvaluationError(f"unsupported profiles schema: {profiles.get('schema')!r}")
    identifiers = _unique_ids(profiles.get("profiles"), "profiles")
    for index, profile in enumerate(profiles["profiles"]):
        _require_string(profile.get("product"), f"profiles[{index}].product")
        _require_string(profile.get("surface"), f"profiles[{index}].surface")
        _require_string(profile.get("automation"), f"profiles[{index}].automation")
        _require_string(profile.get("readiness"), f"profiles[{index}].readiness")
        if not isinstance(profile.get("initial_smoke_suite"), bool):
            raise AIEvaluationError(
                f"profiles[{index}].initial_smoke_suite must be a boolean"
            )
        if not isinstance(profile.get("capabilities"), Mapping):
            raise AIEvaluationError(f"profiles[{index}].capabilities must be an object")
    validate_public_value(profiles)
    return identifiers


def validate_tasks(tasks: Mapping[str, Any]) -> set[str]:
    if tasks.get("schema") != TASKS_SCHEMA:
        raise AIEvaluationError(f"unsupported tasks schema: {tasks.get('schema')!r}")
    _require_string(tasks.get("suite_id"), "tasks.suite_id")
    if tasks.get("fresh_context_per_run") is not True:
        raise AIEvaluationError("tasks.fresh_context_per_run must be true")
    identifiers = _unique_ids(tasks.get("tasks"), "tasks")
    for index, task in enumerate(tasks["tasks"]):
        _require_string(task.get("title"), f"tasks[{index}].title")
        _require_string(task.get("prompt"), f"tasks[{index}].prompt")
        _require_string(task.get("stratum"), f"tasks[{index}].stratum")
        fault_profile = task.get("fault_profile")
        if fault_profile is not None and not isinstance(fault_profile, Mapping):
            raise AIEvaluationError(f"tasks[{index}].fault_profile must be an object or null")
    validate_public_value(tasks)
    return identifiers


def _reference_list(
    value: object,
    label: str,
    *,
    allowed: set[str],
    allow_empty: bool = True,
) -> set[str]:
    values = _require_list(value, label)
    if not allow_empty and not values:
        raise AIEvaluationError(f"{label} must not be empty")
    references: set[str] = set()
    for index, item in enumerate(values):
        reference = _require_string(item, f"{label}[{index}]")
        if reference in references:
            raise AIEvaluationError(f"{label} contains duplicate reference: {reference}")
        references.add(reference)
    unknown = references - allowed
    if unknown:
        raise AIEvaluationError(f"{label} contains unknown references: {sorted(unknown)}")
    return references


def validate_personas_and_journeys(
    value: Mapping[str, Any],
    *,
    task_ids: set[str],
    gold_query_ids: set[str],
) -> set[str]:
    if value.get("schema") != PERSONAS_SCHEMA:
        raise AIEvaluationError(
            f"unsupported personas schema: {value.get('schema')!r}"
        )
    persona_ids = _unique_ids(value.get("personas"), "personas")
    journey_ids = _unique_ids(value.get("journeys"), "journeys")
    assigned_tasks: set[str] = set()
    assigned_gold: set[str] = set()
    for index, persona in enumerate(value["personas"]):
        _require_string(persona.get("title"), f"personas[{index}].title")
        _require_string(persona.get("goal"), f"personas[{index}].goal")
        _reference_list(
            persona.get("journey_ids"),
            f"personas[{index}].journey_ids",
            allowed=journey_ids,
            allow_empty=False,
        )
        assigned_tasks.update(
            _reference_list(
                persona.get("task_ids"),
                f"personas[{index}].task_ids",
                allowed=task_ids,
                allow_empty=False,
            )
        )
        assigned_gold.update(
            _reference_list(
                persona.get("gold_query_ids"),
                f"personas[{index}].gold_query_ids",
                allowed=gold_query_ids,
            )
        )
    for index, journey in enumerate(value["journeys"]):
        _require_string(journey.get("title"), f"journeys[{index}].title")
        _reference_list(
            journey.get("persona_ids"),
            f"journeys[{index}].persona_ids",
            allowed=persona_ids,
            allow_empty=False,
        )
        assigned_tasks.update(
            _reference_list(
                journey.get("task_ids"),
                f"journeys[{index}].task_ids",
                allowed=task_ids,
                allow_empty=False,
            )
        )
        assigned_gold.update(
            _reference_list(
                journey.get("gold_query_ids"),
                f"journeys[{index}].gold_query_ids",
                allowed=gold_query_ids,
            )
        )
        steps = _require_list(journey.get("steps"), f"journeys[{index}].steps")
        criteria = _require_list(
            journey.get("success_criteria"),
            f"journeys[{index}].success_criteria",
        )
        if not steps or not criteria:
            raise AIEvaluationError(
                f"journeys[{index}] needs steps and success criteria"
            )
    missing_tasks = task_ids - assigned_tasks
    missing_gold = gold_query_ids - assigned_gold
    if missing_tasks or missing_gold:
        raise AIEvaluationError(
            "persona/journey coverage is incomplete; "
            f"tasks={sorted(missing_tasks)}, gold={sorted(missing_gold)}"
        )
    coverage = value.get("coverage")
    if not isinstance(coverage, Mapping):
        raise AIEvaluationError("personas.coverage must be an object")
    if coverage.get("all_task_ids_assigned") is not True:
        raise AIEvaluationError("personas must assert all task IDs are assigned")
    if coverage.get("all_gold_query_ids_assigned") is not True:
        raise AIEvaluationError("personas must assert all gold query IDs are assigned")
    validate_public_value(value)
    return journey_ids


def validate_issue_register(
    value: Mapping[str, Any],
    *,
    root: Path,
    task_ids: set[str],
    journey_ids: set[str],
) -> set[str]:
    if value.get("schema") != ISSUES_SCHEMA:
        raise AIEvaluationError(
            f"unsupported issue-register schema: {value.get('schema')!r}"
        )
    issue_ids = _unique_ids(value.get("issues"), "issues")
    verification_ids = {
        _require_string(item, f"issue verification observation[{index}]")
        for index, item in enumerate(
            _require_list(
                value.get("verification_observation_ids"),
                "issue verification observations",
            )
        )
    }
    observation_ids = set(verification_ids)
    evidence_directory = root / "evaluation" / "ai-client" / "evidence"
    for path in sorted(evidence_directory.glob("*.json")):
        observation = _load_object(path)
        observation_ids.add(
            _require_string(
                observation.get("observation_id"),
                f"{path.name}.observation_id",
            )
        )
    for index, issue in enumerate(value["issues"]):
        _require_string(issue.get("title"), f"issues[{index}].title")
        severity = _require_string(issue.get("severity"), f"issues[{index}].severity")
        if severity not in {"critical", "material", "minor"}:
            raise AIEvaluationError(f"issues[{index}].severity is unsupported")
        evidence = _require_list(issue.get("evidence"), f"issues[{index}].evidence")
        if not evidence:
            raise AIEvaluationError(f"issues[{index}] must have evidence")
        for evidence_index, row in enumerate(evidence):
            label = f"issues[{index}].evidence[{evidence_index}]"
            if not isinstance(row, Mapping):
                raise AIEvaluationError(f"{label} must be an object")
            observation_id = _require_string(
                row.get("observation_id"),
                f"{label}.observation_id",
            )
            if observation_id not in observation_ids:
                raise AIEvaluationError(
                    f"{label} has unknown observation ID: {observation_id}"
                )
            relative = Path(_require_string(row.get("artifact"), f"{label}.artifact"))
            if relative.is_absolute() or ".." in relative.parts:
                raise AIEvaluationError(f"{label}.artifact is unsafe")
            if not (root / relative).is_file():
                raise AIEvaluationError(f"{label}.artifact does not exist: {relative}")
            if row.get("status") not in {
                "observed",
                "session-reported",
                "later-verified",
                "inferred",
            }:
                raise AIEvaluationError(f"{label}.status is unsupported")
        remediations = _require_list(
            issue.get("remediations"),
            f"issues[{index}].remediations",
        )
        if not remediations:
            raise AIEvaluationError(f"issues[{index}] must have remediations")
        priorities: set[str] = set()
        for remediation_index, row in enumerate(remediations):
            label = f"issues[{index}].remediations[{remediation_index}]"
            if not isinstance(row, Mapping):
                raise AIEvaluationError(f"{label} must be an object")
            priorities.add(
                _require_string(row.get("priority"), f"{label}.priority")
            )
            _require_string(row.get("action"), f"{label}.action")
        if severity == "critical" and "P0" not in priorities:
            raise AIEvaluationError(f"critical issue {issue['id']} needs a P0 remediation")
        evaluation = issue.get("evaluation")
        if not isinstance(evaluation, Mapping):
            raise AIEvaluationError(f"issues[{index}].evaluation must be an object")
        _reference_list(
            evaluation.get("journey_ids"),
            f"issues[{index}].evaluation.journey_ids",
            allowed=journey_ids,
            allow_empty=False,
        )
        _reference_list(
            evaluation.get("task_ids"),
            f"issues[{index}].evaluation.task_ids",
            allowed=task_ids,
            allow_empty=False,
        )
        failure_codes = _require_list(
            evaluation.get("failure_codes"),
            f"issues[{index}].evaluation.failure_codes",
        )
        if not failure_codes:
            raise AIEvaluationError(f"issues[{index}] needs typed failure codes")
        seen_failure_codes: set[str] = set()
        for failure_index, code in enumerate(failure_codes):
            stable_code = _require_string(
                code,
                f"issues[{index}].evaluation.failure_codes[{failure_index}]",
            )
            if not re.fullmatch(r"[A-Z][A-Z0-9_]*", stable_code):
                raise AIEvaluationError(
                    f"issues[{index}] failure code must be an uppercase stable identifier"
                )
            if stable_code in seen_failure_codes:
                raise AIEvaluationError(
                    f"issues[{index}] contains duplicate failure code: {stable_code}"
                )
            seen_failure_codes.add(stable_code)
    if not _require_list(value.get("release_gates"), "issue release gates"):
        raise AIEvaluationError("issue register must declare release gates")
    validate_public_value(value)
    return issue_ids


def validate_expected(expected: Mapping[str, Any], *, task_ids: set[str]) -> None:
    if expected.get("schema") != EXPECTED_SCHEMA:
        raise AIEvaluationError(f"unsupported expected schema: {expected.get('schema')!r}")
    expected_ids = _unique_ids(expected.get("tasks"), "expected.tasks", key="task_id")
    if expected_ids != task_ids:
        missing = sorted(task_ids - expected_ids)
        extra = sorted(expected_ids - task_ids)
        raise AIEvaluationError(
            f"expected task coverage mismatch; missing={missing}, extra={extra}"
        )
    caveat_register = expected.get("caveat_register")
    if not isinstance(caveat_register, Mapping):
        raise AIEvaluationError("expected.caveat_register must be an object")
    known_caveats = set(caveat_register)
    list_fields = (
        "acceptable_record_ids",
        "acceptable_native_ids",
        "acceptable_source_surfaces",
        "acceptable_editions",
        "acceptable_versions",
        "allowed_hydration_statuses",
        "required_alternative_ids",
        "required_contrast_fields",
        "required_caveat_ids",
        "required_evidence_kinds",
    )
    for index, row in enumerate(expected["tasks"]):
        for field in list_fields:
            values = _require_list(row.get(field), f"expected.tasks[{index}].{field}")
            if len(values) != len(set(values)):
                raise AIEvaluationError(
                    f"expected.tasks[{index}].{field} must not contain duplicates"
                )
        unknown = set(row["required_caveat_ids"]) - known_caveats
        if unknown:
            raise AIEvaluationError(
                f"expected.tasks[{index}] refers to unknown caveats: {sorted(unknown)}"
            )
        _require_string(
            row.get("substitution_policy"),
            f"expected.tasks[{index}].substitution_policy",
        )
        if not isinstance(row.get("mcp_plan_required"), bool):
            raise AIEvaluationError(
                f"expected.tasks[{index}].mcp_plan_required must be a boolean"
            )
        plan_expected = row.get("mcp_plan_expected")
        if row["mcp_plan_required"]:
            if not isinstance(plan_expected, Mapping):
                raise AIEvaluationError(
                    f"expected.tasks[{index}].mcp_plan_expected must be an object"
                )
            for field in ("source", "record_id", "inspection_tool", "query_tool"):
                _require_string(
                    plan_expected.get(field),
                    f"expected.tasks[{index}].mcp_plan_expected.{field}",
                )
            if not isinstance(plan_expected.get("arguments"), Mapping):
                raise AIEvaluationError(
                    f"expected.tasks[{index}].mcp_plan_expected.arguments must be an object"
                )
            if not isinstance(plan_expected.get("complete"), bool):
                raise AIEvaluationError(
                    f"expected.tasks[{index}].mcp_plan_expected.complete must be a boolean"
                )
            minimum = plan_expected.get("minimum_unknown_dimensions")
            if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 0:
                raise AIEvaluationError(
                    "expected mcp_plan minimum_unknown_dimensions must be non-negative"
                )
            if not isinstance(plan_expected.get("executed"), bool):
                raise AIEvaluationError(
                    f"expected.tasks[{index}].mcp_plan_expected.executed must be a boolean"
                )
            unknown_evidence = plan_expected.get("unknown_dimension_evidence")
            if not isinstance(unknown_evidence, Mapping):
                raise AIEvaluationError(
                    "expected mcp_plan unknown_dimension_evidence must be an object"
                )
            for field in ("record_id", "json_pointer"):
                _require_string(
                    unknown_evidence.get(field),
                    f"expected mcp_plan unknown_dimension_evidence.{field}",
                )
        elif plan_expected is not None:
            raise AIEvaluationError(
                f"expected.tasks[{index}] has an MCP plan expectation but it is not required"
            )
    policy = expected.get("statistical_accuracy")
    if not isinstance(policy, Mapping) or policy.get("evaluated") is not False:
        raise AIEvaluationError("expected.statistical_accuracy.evaluated must be false")
    review_prompts = _require_list(
        expected.get("critical_claim_review_prompts"),
        "expected.critical_claim_review_prompts",
    )
    for index, prompt in enumerate(review_prompts):
        _require_string(prompt, f"expected.critical_claim_review_prompts[{index}]")
    validate_public_value(expected)


def validate_study(study: Mapping[str, Any]) -> tuple[set[str], set[str]]:
    if study.get("schema") != STUDY_SCHEMA:
        raise AIEvaluationError(f"unsupported study schema: {study.get('schema')!r}")
    _require_string(study.get("study_id"), "study.study_id")
    arm_ids = _unique_ids(study.get("arms"), "study.arms")
    mode_ids = _unique_ids(study.get("delivery_modes"), "study.delivery_modes")
    if len(arm_ids) < 3:
        raise AIEvaluationError("study must define at least three access arms")
    for arm_index, arm in enumerate(study["arms"]):
        for target_kind in ("allowed_targets", "denied_targets"):
            targets = _require_list(
                arm.get(target_kind),
                f"study.arms[{arm_index}].{target_kind}",
            )
            for target_index, target in enumerate(targets):
                label = f"study.arms[{arm_index}].{target_kind}[{target_index}]"
                if not isinstance(target, Mapping):
                    raise AIEvaluationError(f"{label} must be an object")
                origin = _require_string(target.get("origin"), f"{label}.origin")
                if origin != "*":
                    parsed = urlsplit(origin)
                    if (
                        parsed.scheme not in {"http", "https"}
                        or not parsed.netloc
                        or parsed.path
                        or parsed.query
                        or parsed.fragment
                    ):
                        raise AIEvaluationError(
                            f"{label}.origin must be an origin without a path"
                        )
                prefixes = _require_list(target.get("path_prefixes"), f"{label}.path_prefixes")
                if not prefixes or any(
                    not isinstance(prefix, str)
                    or (prefix != "*" and not prefix.startswith("/"))
                    for prefix in prefixes
                ):
                    raise AIEvaluationError(
                        f"{label}.path_prefixes must contain '*' or absolute path prefixes"
                    )
    run_contract = study.get("run_contract")
    if not isinstance(run_contract, Mapping):
        raise AIEvaluationError("study.run_contract must be an object")
    if run_contract.get("fresh_context_per_run") is not True:
        raise AIEvaluationError("study.run_contract.fresh_context_per_run must be true")
    if run_contract.get("ci_live_network") is not False:
        raise AIEvaluationError("study.run_contract.ci_live_network must be false")
    if run_contract.get("ci_paid_calls") is not False:
        raise AIEvaluationError("study.run_contract.ci_paid_calls must be false")
    if run_contract.get("hidden_reasoning_collected") is not False:
        raise AIEvaluationError("study must not collect hidden reasoning")
    if run_contract.get("comparative_runs_require_enforced_access") is not True:
        raise AIEvaluationError("comparative runs must require enforced access")
    if run_contract.get("access_enforcement_requires_evidence") is not True:
        raise AIEvaluationError("access enforcement must require evidence")
    if run_contract.get("fault_profiles_require_enforcement_evidence") is not True:
        raise AIEvaluationError("fault profiles must require enforcement evidence")
    if run_contract.get("efficiency_claims_require_comparative_arms") is not True:
        raise AIEvaluationError("efficiency claims must require comparative arms")
    if run_contract.get("missing_telemetry_remains_null") is not True:
        raise AIEvaluationError("missing telemetry must remain null")
    efficiency = study.get("efficiency_outcomes")
    if not isinstance(efficiency, Mapping):
        raise AIEvaluationError("study.efficiency_outcomes must be an object")
    if efficiency.get("single_composite_score") is not False:
        raise AIEvaluationError("efficiency must not use one composite score")
    _require_string(efficiency.get("claim_rule"), "study.efficiency_outcomes.claim_rule")
    _unique_ids(efficiency.get("measures"), "study.efficiency_outcomes.measures")
    for index, measure in enumerate(efficiency["measures"]):
        _require_string(
            measure.get("unit"),
            f"study.efficiency_outcomes.measures[{index}].unit",
        )
        _require_string(
            measure.get("scope"),
            f"study.efficiency_outcomes.measures[{index}].scope",
        )
    validate_public_value(study)
    return arm_ids, mode_ids


def load_harness(root: str | Path) -> dict[str, Any]:
    """Load and cross-validate the committed harness files and their byte digests."""

    repository = Path(root)
    study_path = repository / "evaluation" / "ai-client" / "study.json"
    study = _load_object(study_path)
    arm_ids, mode_ids = validate_study(study)

    loaded: dict[str, Any] = {
        "study": study,
        "_context": {"root": repository},
    }
    for key in (
        "tasks",
        "expected",
        "client_profiles",
        "personas_and_journeys",
        "issue_register",
    ):
        relative = _require_string(study["inputs"].get(key), f"study.inputs.{key}")
        path = repository / relative
        expected_digest = _require_string(
            study["inputs"].get(f"{key}_sha256"),
            f"study.inputs.{key}_sha256",
        )
        actual_digest = _file_digest(path)
        if actual_digest != expected_digest:
            raise AIEvaluationError(
                f"{key} digest mismatch: expected {expected_digest}, got {actual_digest}"
            )
        loaded[key] = _load_object(path)

    task_ids = validate_tasks(loaded["tasks"])
    if loaded["tasks"]["suite_id"] != study["study_id"]:
        raise AIEvaluationError("study and task suite identifiers differ")
    validate_expected(loaded["expected"], task_ids=task_ids)
    if loaded["expected"]["suite_id"] != study["study_id"]:
        raise AIEvaluationError("study and expected suite identifiers differ")
    profile_ids = validate_profiles(loaded["client_profiles"])
    if profile_ids != set(LOCAL_CLIENT_PROBES):
        missing = sorted(profile_ids - set(LOCAL_CLIENT_PROBES))
        extra = sorted(set(LOCAL_CLIENT_PROBES) - profile_ids)
        raise AIEvaluationError(
            f"local client probe coverage mismatch; missing={missing}, extra={extra}"
        )
    gold_suite = _load_object(repository / "evaluation" / "gold-queries.json")
    gold_query_ids = _unique_ids(gold_suite.get("queries"), "gold queries")
    journey_ids = validate_personas_and_journeys(
        loaded["personas_and_journeys"],
        task_ids=task_ids,
        gold_query_ids=gold_query_ids,
    )
    issue_ids = validate_issue_register(
        loaded["issue_register"],
        root=repository,
        task_ids=task_ids,
        journey_ids=journey_ids,
    )
    loaded["_ids"] = {
        "arms": {identifier: True for identifier in sorted(arm_ids)},
        "issues": {identifier: True for identifier in sorted(issue_ids)},
        "journeys": {identifier: True for identifier in sorted(journey_ids)},
        "modes": {identifier: True for identifier in sorted(mode_ids)},
        "tasks": {identifier: True for identifier in sorted(task_ids)},
        "profiles": {identifier: True for identifier in sorted(profile_ids)},
    }
    return loaded


def probe_local_clients(harness: Mapping[str, Any]) -> dict[str, Any]:
    """Probe installation and versions without making model or network calls."""

    results: list[dict[str, Any]] = []
    profiles = {
        str(profile["id"]): profile for profile in harness["client_profiles"]["profiles"]
    }
    environment = {
        "HOME": os.environ.get("HOME", ""),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "NO_COLOR": "1",
        "PATH": os.environ.get("PATH", ""),
    }
    for profile_id in sorted(profiles):
        probe = LOCAL_CLIENT_PROBES[profile_id]
        command_available = False
        command_version: str | None = None
        command_error: str | None = None
        command = probe.get("command")
        command_names = probe.get("commands", ())
        if command:
            executable = shutil.which(command[0])
            command_available = executable is not None
            if executable:
                try:
                    result = subprocess.run(
                        [executable, *command[1:]],
                        check=False,
                        capture_output=True,
                        env=environment,
                        stdin=subprocess.DEVNULL,
                        text=True,
                        timeout=5,
                    )
                    output = (result.stdout or result.stderr).strip().splitlines()
                    command_version = output[0][:200] if output else None
                    if result.returncode != 0:
                        command_error = f"version probe exited {result.returncode}"
                except (OSError, subprocess.TimeoutExpired) as error:
                    command_error = type(error).__name__
        elif command_names:
            command_available = any(shutil.which(name) for name in command_names)

        applications = list(probe.get("applications", ()))
        application_available = any(
            (Path("/Applications") / application).is_dir() for application in applications
        )
        results.append(
            {
                "profile_id": profile_id,
                "product": profiles[profile_id]["product"],
                "installed": command_available or application_available,
                "command_available": command_available,
                "application_available": application_available,
                "version_output": command_version,
                "probe_error": command_error,
                "authentication_probed": False,
                "model_call_made": False,
                "readiness_claimed": False,
            }
        )
    return {
        "schema": "okf-ons.ai-client-local-probe.v1",
        "warning": (
            "This proves only local installation and a safe version response. "
            "It does not prove authentication, model availability or evaluation readiness."
        ),
        "network_calls_intended": False,
        "model_calls_made": False,
        "profiles": results,
    }


def _validate_telemetry(
    telemetry: object,
    measures: Sequence[Mapping[str, Any]],
) -> None:
    if not isinstance(telemetry, Mapping):
        raise AIEvaluationError("run.telemetry must be an object")
    specifications = {str(measure["id"]): measure for measure in measures}
    unknown = set(telemetry) - set(specifications)
    if unknown:
        raise AIEvaluationError(
            f"run.telemetry contains unregistered measures: {sorted(unknown)}"
        )
    for name, measurement in telemetry.items():
        if not isinstance(measurement, Mapping):
            raise AIEvaluationError(f"run.telemetry.{name} must be an object")
        exact = measurement.get("exact")
        if not isinstance(exact, bool):
            raise AIEvaluationError(f"run.telemetry.{name}.exact must be a boolean")
        has_value = measurement.get("value") is not None
        has_range = (
            measurement.get("minimum") is not None or measurement.get("maximum") is not None
        )
        if exact and (not has_value or has_range):
            raise AIEvaluationError(
                f"run.telemetry.{name} exact measurements need one non-null value"
            )
        source = _require_string(measurement.get("source"), f"run.telemetry.{name}.source")
        if exact and "estimat" in source.casefold():
            raise AIEvaluationError(
                f"run.telemetry.{name} cannot label an estimate as exact"
            )
        specification = specifications[str(name)]
        unit = _require_string(measurement.get("unit"), f"run.telemetry.{name}.unit")
        if unit != specification["unit"]:
            raise AIEvaluationError(
                f"run.telemetry.{name}.unit must be {specification['unit']!r}"
            )
        scope = _require_string(measurement.get("scope"), f"run.telemetry.{name}.scope")
        if scope != specification["scope"]:
            raise AIEvaluationError(
                f"run.telemetry.{name}.scope does not match the study contract"
            )
        numeric_values = {
            field: measurement.get(field)
            for field in ("value", "minimum", "maximum")
            if measurement.get(field) is not None
        }
        for field, value in numeric_values.items():
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            ):
                raise AIEvaluationError(
                    f"run.telemetry.{name}.{field} must be a finite non-negative number"
                )
        minimum = measurement.get("minimum")
        maximum = measurement.get("maximum")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise AIEvaluationError(
                f"run.telemetry.{name}.minimum must not exceed maximum"
            )


def _task_row(tasks: Mapping[str, Any], task_id: str) -> Mapping[str, Any]:
    return next(row for row in tasks["tasks"] if row["id"] == task_id)


def _arm_row(study: Mapping[str, Any], arm_id: str) -> Mapping[str, Any]:
    return next(row for row in study["arms"] if row["id"] == arm_id)


def validate_run(run: Mapping[str, Any], harness: Mapping[str, Any]) -> None:
    """Validate a public run record without judging its answer."""

    if run.get("schema") != RUN_SCHEMA:
        raise AIEvaluationError(f"unsupported run schema: {run.get('schema')!r}")
    _require_string(run.get("run_id"), "run.run_id")
    if run.get("study_id") != harness["study"]["study_id"]:
        raise AIEvaluationError("run.study_id does not match the loaded study")
    identifiers = harness["_ids"]
    if run.get("task_id") not in identifiers["tasks"]:
        raise AIEvaluationError(f"run has unknown task: {run.get('task_id')!r}")
    if run.get("arm_id") not in identifiers["arms"]:
        raise AIEvaluationError(f"run has unknown arm: {run.get('arm_id')!r}")
    if run.get("delivery_mode") not in identifiers["modes"]:
        raise AIEvaluationError(f"run has unknown delivery mode: {run.get('delivery_mode')!r}")
    client = run.get("client")
    if not isinstance(client, Mapping) or client.get("profile_id") not in identifiers["profiles"]:
        raise AIEvaluationError("run.client.profile_id is unknown")
    replicate = run.get("replicate")
    if not isinstance(replicate, int) or isinstance(replicate, bool) or replicate < 1:
        raise AIEvaluationError("run.replicate must be a positive integer")
    if run.get("status") not in TASK_STATUSES:
        raise AIEvaluationError(f"run.status must be one of {sorted(TASK_STATUSES)}")
    access = run.get("access")
    if not isinstance(access, Mapping) or access.get("enforcement") not in ENFORCEMENT_VALUES:
        raise AIEvaluationError(
            f"run.access.enforcement must be one of {sorted(ENFORCEMENT_VALUES)}"
        )
    access_evidence = _require_list(access.get("evidence"), "run.access.evidence")
    _require_list(access.get("violations"), "run.access.violations")
    expected_policy = _arm_row(harness["study"], str(run["arm_id"]))
    if access.get("policy") != expected_policy:
        raise AIEvaluationError("run.access.policy does not match the study arm")
    access_fixture_evidence = False
    if access.get("enforcement") in {"enforced", "observed"}:
        access_fixture_evidence = _validate_enforcement_evidence(
            access_evidence,
            subject=expected_policy,
            subject_type="access-policy",
            harness=harness,
            run=run,
        )
    constraints = run.get("constraints")
    if (
        not isinstance(constraints, Mapping)
        or constraints.get("enforcement") not in CONSTRAINT_ENFORCEMENT_VALUES
    ):
        raise AIEvaluationError(
            "run.constraints.enforcement must be one of "
            f"{sorted(CONSTRAINT_ENFORCEMENT_VALUES)}"
        )
    expected_profile = _task_row(harness["tasks"], str(run["task_id"]))["fault_profile"]
    if constraints.get("profile") != expected_profile:
        raise AIEvaluationError("run.constraints.profile does not match the task fault profile")
    evidence = _require_list(constraints.get("evidence"), "run.constraints.evidence")
    _require_list(constraints.get("violations"), "run.constraints.violations")
    if expected_profile is None and constraints.get("enforcement") != "not-applicable":
        raise AIEvaluationError(
            "a task without a fault profile must use constraint enforcement not-applicable"
        )
    if expected_profile is not None and constraints.get("enforcement") == "not-applicable":
        raise AIEvaluationError(
            "a task with a fault profile cannot use constraint enforcement not-applicable"
        )
    constraint_fixture_evidence = False
    if constraints.get("enforcement") in {"enforced", "observed"}:
        constraint_fixture_evidence = _validate_enforcement_evidence(
            evidence,
            subject=expected_profile,
            subject_type="fault-profile",
            harness=harness,
            run=run,
        )
    capture = run.get("capture")
    if not isinstance(capture, Mapping) or capture.get("fidelity") not in CAPTURE_FIDELITIES:
        raise AIEvaluationError(
            f"run.capture.fidelity must be one of {sorted(CAPTURE_FIDELITIES)}"
        )
    _capture_events(run, harness)
    answer = run.get("answer")
    if answer is not None and not isinstance(answer, Mapping):
        raise AIEvaluationError("run.answer must be an object or null")
    if isinstance(answer, Mapping):
        for field in (
            "considered_record_ids",
            "alternatives",
            "evidence",
            "caveat_ids",
        ):
            _require_list(answer.get(field), f"run.answer.{field}")
        _require_string(answer.get("answer"), "run.answer.answer", allow_empty=True)
    assessment = run.get("assessment")
    if assessment is not None and not isinstance(assessment, Mapping):
        raise AIEvaluationError("run.assessment must be an object or null")
    if isinstance(assessment, Mapping):
        if not isinstance(answer, Mapping):
            raise AIEvaluationError("run.assessment requires a structured answer")
        _require_string(assessment.get("method"), "run.assessment.method")
        if assessment.get("method") not in {
            "validated-fixture",
            "blind-human",
            "adjudicated",
        }:
            raise AIEvaluationError(
                "run.assessment.method must be validated-fixture, blind-human or adjudicated"
            )
        _require_string(assessment.get("assessor_alias"), "run.assessment.assessor_alias")
        if assessment.get("independent_of_client") is not True:
            raise AIEvaluationError("run.assessment must be independent of the client")
        if not _is_sha256(assessment.get("provenance_sha256")):
            raise AIEvaluationError("run.assessment.provenance_sha256 must be a SHA-256 digest")
        for field in (
            "supported_caveat_ids",
            "supported_evidence_kinds",
            "unsupported_claims",
            "evidence_spans",
        ):
            _require_list(assessment.get(field), f"run.assessment.{field}")
        supported_caveats = set(assessment["supported_caveat_ids"])
        unknown_caveats = supported_caveats - set(harness["expected"]["caveat_register"])
        if unknown_caveats:
            raise AIEvaluationError(
                f"run.assessment has unknown caveat IDs: {sorted(unknown_caveats)}"
            )
        visible_answer = str(answer["answer"])
        answer_digest = hashlib.sha256(visible_answer.encode("utf-8")).hexdigest()
        if assessment.get("visible_answer_sha256") != answer_digest:
            raise AIEvaluationError(
                "run.assessment.visible_answer_sha256 does not match the visible answer"
            )
        span_criteria: set[str] = set()
        for index, span in enumerate(assessment["evidence_spans"]):
            if not isinstance(span, Mapping):
                raise AIEvaluationError(f"run.assessment.evidence_spans[{index}] must be an object")
            criterion = _require_string(
                span.get("criterion"),
                f"run.assessment.evidence_spans[{index}].criterion",
            )
            quote = _require_string(
                span.get("quote"),
                f"run.assessment.evidence_spans[{index}].quote",
            )
            if quote not in visible_answer:
                raise AIEvaluationError(
                    f"run.assessment.evidence_spans[{index}].quote is not in the visible answer"
                )
            span_criteria.add(criterion)
        required_criteria = {
            *(f"caveat:{value}" for value in assessment["supported_caveat_ids"]),
            *(f"evidence:{value}" for value in assessment["supported_evidence_kinds"]),
            *(
                f"unsupported:{index}"
                for index, _ in enumerate(assessment["unsupported_claims"])
            ),
        }
        missing_criteria = required_criteria - span_criteria
        if missing_criteria:
            raise AIEvaluationError(
                "run.assessment.evidence_spans is missing criteria: "
                f"{sorted(missing_criteria)}"
            )
        for index, claim in enumerate(assessment["unsupported_claims"]):
            if not isinstance(claim, Mapping):
                raise AIEvaluationError(
                    f"run.assessment.unsupported_claims[{index}] must be an object"
                )
            _require_string(
                claim.get("claim"),
                f"run.assessment.unsupported_claims[{index}].claim",
            )
            if claim.get("severity") not in {"critical", "material", "minor"}:
                raise AIEvaluationError(
                    "run.assessment unsupported claim severity must be "
                    "critical, material or minor"
                )
    if access_fixture_evidence or constraint_fixture_evidence:
        if capture.get("fidelity") != "fixture-replay":
            raise AIEvaluationError("fixture-only enforcement requires fixture-replay capture")
        if not isinstance(assessment, Mapping) or assessment.get("method") != "validated-fixture":
            raise AIEvaluationError(
                "fixture-only enforcement requires a validated-fixture assessment"
            )
    _validate_telemetry(
        run.get("telemetry"),
        harness["study"]["efficiency_outcomes"]["measures"],
    )
    failures = _require_list(run.get("failures"), "run.failures")
    registered_failure_codes = {
        str(code)
        for issue in harness["issue_register"]["issues"]
        for code in issue["evaluation"]["failure_codes"]
    }
    for index, failure in enumerate(failures):
        if not isinstance(failure, Mapping):
            raise AIEvaluationError(f"run.failures[{index}] must be an object")
        code = _require_string(failure.get("code"), f"run.failures[{index}].code")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", code):
            raise AIEvaluationError(
                f"run.failures[{index}].code must be an uppercase stable identifier"
            )
        if code not in registered_failure_codes:
            raise AIEvaluationError(
                f"run.failures[{index}].code is not registered: {code}"
            )
        _require_string(failure.get("stage"), f"run.failures[{index}].stage")
    validate_public_value(run)


def create_run_template(
    harness: Mapping[str, Any],
    *,
    run_id: str,
    client_profile: str,
    arm_id: str,
    delivery_mode: str,
    task_id: str,
    replicate: int,
) -> dict[str, Any]:
    """Create a deterministic, unstarted run record."""

    run = {
        "schema": RUN_SCHEMA,
        "run_id": run_id,
        "study_id": harness["study"]["study_id"],
        "task_id": task_id,
        "arm_id": arm_id,
        "delivery_mode": delivery_mode,
        "replicate": replicate,
        "client": {
            "profile_id": client_profile,
            "client_version": None,
            "model_requested": None,
            "model_resolved": None,
            "model_effort": None,
        },
        "bundle": dict(harness["study"]["bundle"]),
        "status": "not-run",
        "started_at": None,
        "completed_at": None,
        "access": {
            "policy": _arm_row(harness["study"], arm_id),
            "enforcement": "self-reported",
            "evidence": [],
            "violations": [],
        },
        "constraints": {
            "profile": _task_row(harness["tasks"], task_id)["fault_profile"],
            "enforcement": (
                "not-applicable"
                if _task_row(harness["tasks"], task_id)["fault_profile"] is None
                else "not-applied"
            ),
            "evidence": [],
            "violations": [],
        },
        "capture": {
            "fidelity": "not-captured",
            "events_path": None,
            "events_sha256": None,
            "transcript_path": None,
            "native_export_sha256": None,
            "hidden_reasoning_collected": False,
        },
        "answer": None,
        "assessment": None,
        "telemetry": {},
        "failures": [],
    }
    validate_run(run, harness)
    return run


def _membership_component(actual: object, expected: Sequence[str]) -> dict[str, Any]:
    if not expected:
        return {"applicable": False, "score": None}
    matched = actual in expected
    return {
        "applicable": True,
        "score": 1.0 if matched else 0.0,
        "actual": actual,
        "acceptable": list(expected),
    }


def _coverage_component(actual: set[str], expected: Sequence[str]) -> dict[str, Any]:
    if not expected:
        return {"applicable": False, "score": None, "matched": [], "missing": []}
    expected_set = set(expected)
    matched = sorted(actual & expected_set)
    missing = sorted(expected_set - actual)
    return {
        "applicable": True,
        "score": round(len(matched) / len(expected_set), 6),
        "matched": matched,
        "missing": missing,
    }


def _expected_row(expected: Mapping[str, Any], task_id: str) -> Mapping[str, Any]:
    return next(row for row in expected["tasks"] if row["task_id"] == task_id)


def score_run(run: Mapping[str, Any], harness: Mapping[str, Any]) -> dict[str, Any]:
    """Score one normalised run using public development gold."""

    validate_run(run, harness)
    expected = _expected_row(harness["expected"], str(run["task_id"]))
    access_violations = list(run["access"]["violations"])
    constraint_violations = list(run["constraints"]["violations"])
    fault_profile = run["constraints"]["profile"]
    constraint_enforcement = str(run["constraints"]["enforcement"])
    status = str(run["status"])
    exclusion_reason: str | None = None
    if access_violations:
        exclusion_reason = "arm-violation"
    elif constraint_violations:
        exclusion_reason = "constraint-violation"
    elif fault_profile is not None and constraint_enforcement not in {"enforced", "observed"}:
        exclusion_reason = "constraints-not-evidenced"
    elif status in {"blocked", "not-run"}:
        exclusion_reason = f"readiness-{status}"
    eligible = exclusion_reason is None
    validation_exclusion_reason: str | None = exclusion_reason
    if validation_exclusion_reason is None and run["access"]["enforcement"] != "enforced":
        validation_exclusion_reason = "arm-not-enforced"
    if (
        validation_exclusion_reason is None
        and fault_profile is not None
        and constraint_enforcement != "enforced"
    ):
        validation_exclusion_reason = "constraints-not-enforced"
    validation_eligible = validation_exclusion_reason is None
    comparative_exclusion_reason = validation_exclusion_reason
    if (
        comparative_exclusion_reason is None
        and run["capture"]["fidelity"] == "fixture-replay"
    ):
        comparative_exclusion_reason = "fixture-replay"
    comparative_eligible = comparative_exclusion_reason is None

    answer = run.get("answer") if isinstance(run.get("answer"), Mapping) else {}
    assessment = (
        run.get("assessment") if isinstance(run.get("assessment"), Mapping) else {}
    )
    structured_output = bool(answer)
    assessment_present = bool(assessment)
    alternatives = answer.get("alternatives", []) if structured_output else []
    alternative_ids = {
        str(row.get("record_id"))
        for row in alternatives
        if isinstance(row, Mapping) and row.get("record_id")
    }
    contrast_fields = {
        str(field)
        for row in alternatives
        if isinstance(row, Mapping)
        for field in row.get("contrast_fields", [])
        if isinstance(field, str)
    }
    evidence_kinds = {
        str(value) for value in assessment.get("supported_evidence_kinds", [])
    }
    caveat_ids = {str(value) for value in assessment.get("supported_caveat_ids", [])}

    components = {
        "structured_output": {
            "applicable": True,
            "score": 1.0 if structured_output else 0.0,
        },
        "assessment_present": {
            "applicable": True,
            "score": 1.0 if assessment_present else 0.0,
        },
        "target_record": _membership_component(
            answer.get("chosen_record_id"),
            expected["acceptable_record_ids"],
        ),
        "native_id": _membership_component(
            answer.get("chosen_native_id"),
            expected["acceptable_native_ids"],
        ),
        "source_surface": _membership_component(
            answer.get("chosen_source_surface"),
            expected["acceptable_source_surfaces"],
        ),
        "edition": _membership_component(
            answer.get("chosen_edition"),
            expected["acceptable_editions"],
        ),
        "version": _membership_component(
            answer.get("chosen_version"),
            expected["acceptable_versions"],
        ),
        "hydration": _membership_component(
            (
                answer.get("hydration", {}).get("status")
                if isinstance(answer.get("hydration"), Mapping)
                else None
            ),
            expected["allowed_hydration_statuses"],
        ),
        "alternative_exposure": _coverage_component(
            alternative_ids,
            expected["required_alternative_ids"],
        ),
        "contrast_coverage": _coverage_component(
            contrast_fields,
            expected["required_contrast_fields"],
        ),
        "caveat_fidelity": _coverage_component(
            caveat_ids,
            expected["required_caveat_ids"],
        ),
        "evidence_coverage": _coverage_component(
            evidence_kinds,
            expected["required_evidence_kinds"],
        ),
    }

    mcp_required = bool(expected["mcp_plan_required"])
    mcp_plan = answer.get("mcp_plan") if isinstance(answer.get("mcp_plan"), Mapping) else None
    if mcp_required:
        expected_plan = expected["mcp_plan_expected"]
        actual_arguments = (
            mcp_plan.get("arguments", {}) if isinstance(mcp_plan, Mapping) else {}
        )
        unknown_dimensions = (
            mcp_plan.get("unknown_dimensions", []) if isinstance(mcp_plan, Mapping) else []
        )
        expected_arguments = expected_plan["arguments"]
        identity_fields_match = bool(mcp_plan) and all(
            mcp_plan.get(field) == expected_plan[field]
            for field in ("source", "record_id", "inspection_tool", "query_tool")
        )
        arguments_match = (
            isinstance(actual_arguments, Mapping)
            and set(actual_arguments) == set(expected_arguments)
            and all(
                actual_arguments.get(field) == value
                for field, value in expected_arguments.items()
            )
        )
        credential_fields = {
            str(field).casefold()
            for field in actual_arguments
            if str(field).casefold()
            in {"api_key", "apikey", "authorization", "password", "token"}
        }
        expected_unknown_evidence = expected_plan["unknown_dimension_evidence"]
        unknown_dimensions_valid = (
            isinstance(unknown_dimensions, list)
            and len(unknown_dimensions) >= expected_plan["minimum_unknown_dimensions"]
            and all(
                isinstance(row, Mapping)
                and isinstance(row.get("dimension"), str)
                and bool(row["dimension"].strip())
                and row.get("record_id") == expected_unknown_evidence["record_id"]
                and row.get("json_pointer") == expected_unknown_evidence["json_pointer"]
                for row in unknown_dimensions
            )
        )
        execution_evidence = (
            mcp_plan.get("execution_evidence")
            if isinstance(mcp_plan, Mapping)
            and isinstance(mcp_plan.get("execution_evidence"), Mapping)
            else {}
        )
        events = _capture_events(run, harness)
        query_tool_calls = sum(
            event.get("event") == "tool_request"
            and event.get("tool") == expected_plan["query_tool"]
            for event in events
        )
        execution_evidence_valid = (
            _is_sha256(run["capture"].get("events_sha256"))
            and execution_evidence.get("events_sha256")
            == run["capture"].get("events_sha256")
            and execution_evidence.get("query_tool_call_count") == query_tool_calls
            and query_tool_calls == 0
        )
        mcp_passed = (
            identity_fields_match
            and arguments_match
            and not credential_fields
            and mcp_plan.get("complete") is expected_plan["complete"]
            and unknown_dimensions_valid
            and mcp_plan.get("executed") is expected_plan["executed"]
            and execution_evidence_valid
        )
        components["mcp_plan"] = {
            "applicable": True,
            "score": 1.0 if mcp_passed else 0.0,
            "expected": expected_plan,
            "credential_fields": sorted(credential_fields),
            "query_tool_call_count": query_tool_calls,
            "execution_evidence_valid": execution_evidence_valid,
        }
    else:
        components["mcp_plan"] = {"applicable": False, "score": None}

    substitution = (
        answer.get("substitution") if isinstance(answer.get("substitution"), Mapping) else {}
    )
    substitution_used = bool(substitution.get("used"))
    substitution_disclosed = bool(substitution.get("disclosed"))
    substitution_policy = expected["substitution_policy"]
    if substitution_policy == "not-applicable":
        substitution_score = None
    elif substitution_policy == "forbidden":
        substitution_score = 0.0 if substitution_used else 1.0
    elif substitution_policy == "disclose-or-abstain":
        substitution_score = 1.0 if not substitution_used or substitution_disclosed else 0.0
    else:
        raise AIEvaluationError(f"unknown substitution policy: {substitution_policy}")
    components["substitution_integrity"] = {
        "applicable": substitution_score is not None,
        "score": substitution_score,
        "used": substitution_used,
        "disclosed": substitution_disclosed,
    }

    unsupported = [
        row
        for row in assessment.get("unsupported_claims", [])
        if isinstance(row, Mapping)
    ]
    critical_count = sum(row.get("severity") == "critical" for row in unsupported)
    components["unsupported_claim_safety"] = {
        "applicable": True,
        "score": 1.0 if assessment_present and critical_count == 0 else 0.0,
        "assessed": assessment_present,
        "critical_count": critical_count,
        "total_count": len(unsupported),
        "review_prompts": harness["expected"]["critical_claim_review_prompts"],
    }

    applicable = [
        component["score"]
        for component in components.values()
        if component["applicable"] and component["score"] is not None
    ]
    all_components_pass = bool(applicable) and all(score == 1.0 for score in applicable)
    selection_applicable = bool(expected["acceptable_record_ids"])
    safe_exact_selection: float | None = None
    if selection_applicable:
        strict_names = (
            "target_record",
            "native_id",
            "source_surface",
            "edition",
            "version",
            "hydration",
            "caveat_fidelity",
            "substitution_integrity",
            "assessment_present",
            "unsupported_claim_safety",
        )
        strict_scores = [
            components[name]["score"]
            for name in strict_names
            if components[name]["applicable"]
        ]
        safe_exact_selection = (
            1.0
            if eligible and strict_scores and all(score == 1.0 for score in strict_scores)
            else 0.0
        )

    return {
        "schema": SCORE_SCHEMA,
        "study_id": run["study_id"],
        "run_id": run["run_id"],
        "task_id": run["task_id"],
        "client_profile_id": run["client"]["profile_id"],
        "arm_id": run["arm_id"],
        "delivery_mode": run["delivery_mode"],
        "capture_fidelity": run["capture"]["fidelity"],
        "arm_enforcement": run["access"]["enforcement"],
        "constraint_enforcement": constraint_enforcement,
        "status": status,
        "eligible": eligible,
        "exclusion_reason": exclusion_reason,
        "validation_eligible": validation_eligible,
        "validation_exclusion_reason": validation_exclusion_reason,
        "comparative_eligible": comparative_eligible,
        "comparative_exclusion_reason": comparative_exclusion_reason,
        "components": components,
        "safe_exact_selection": safe_exact_selection,
        "all_applicable_components_pass": eligible and all_components_pass,
        "run_digest_sha256": _digest(run),
        "statistical_accuracy": {
            "evaluated": False,
            "score": None,
            "statement": ACCURACY_BOUNDARY,
        },
    }


def _mean(values: Sequence[float]) -> float | None:
    return round(sum(values) / len(values), 6) if values else None


def _aggregate(
    scores: Sequence[Mapping[str, Any]],
    *,
    eligibility_field: str,
) -> dict[str, Any]:
    component_names = sorted(
        {
            name
            for score in scores
            if score[eligibility_field]
            for name, component in score["components"].items()
            if component["applicable"]
        }
    )
    components: dict[str, Any] = {}
    for name in component_names:
        values = [
            float(score["components"][name]["score"])
            for score in scores
            if score[eligibility_field]
            and name in score["components"]
            and score["components"][name]["applicable"]
            and score["components"][name]["score"] is not None
        ]
        components[name] = {"mean": _mean(values), "denominator": len(values)}
    safe_values = [
        float(score["safe_exact_selection"])
        for score in scores
        if score[eligibility_field] and score["safe_exact_selection"] is not None
    ]
    return {
        "run_count": len(scores),
        "eligibility_field": eligibility_field,
        "eligible_run_count": sum(bool(score[eligibility_field]) for score in scores),
        "task_eligible_run_count": sum(bool(score["eligible"]) for score in scores),
        "validation_eligible_run_count": sum(
            bool(score["validation_eligible"]) for score in scores
        ),
        "comparative_eligible_run_count": sum(
            bool(score["comparative_eligible"]) for score in scores
        ),
        "blocked_run_count": sum(score["status"] == "blocked" for score in scores),
        "failed_run_count": sum(score["status"] == "failed" for score in scores),
        "arm_violation_count": sum(
            score["exclusion_reason"] == "arm-violation" for score in scores
        ),
        "safe_exact_selection": {
            "mean": _mean(safe_values),
            "denominator": len(safe_values),
        },
        "components": components,
    }


def _numeric_measure_summary(values: Sequence[float]) -> dict[str, Any]:
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "mean": _mean(ordered),
        "minimum": ordered[0] if ordered else None,
        "maximum": ordered[-1] if ordered else None,
        "values": ordered,
    }


def _efficiency_report(
    runs: Sequence[Mapping[str, Any]],
    scores: Sequence[Mapping[str, Any]],
    harness: Mapping[str, Any],
) -> dict[str, Any]:
    ordered_runs = sorted(runs, key=lambda row: str(row["run_id"]))
    scores_by_run = {str(score["run_id"]): score for score in scores}
    required_arm_ids = {str(arm["id"]) for arm in harness["study"]["arms"]}
    coverage: dict[str, dict[str, int]] = {}
    measure_reports: dict[str, dict[str, Any]] = {}

    for specification in harness["study"]["efficiency_outcomes"]["measures"]:
        measure_id = str(specification["id"])
        measurements: list[dict[str, Any]] = []
        comparative_cells: dict[str, dict[str, Any]] = {}
        for run in ordered_runs:
            measurement = run["telemetry"].get(measure_id)
            if not isinstance(measurement, Mapping):
                continue
            known = any(
                measurement.get(field) is not None
                for field in ("value", "minimum", "maximum")
            )
            if not known:
                continue
            score = scores_by_run[str(run["run_id"])]
            measurements.append(
                {
                    "run_id": run["run_id"],
                    "task_id": run["task_id"],
                    "client_profile_id": run["client"]["profile_id"],
                    "arm_id": run["arm_id"],
                    "delivery_mode": run["delivery_mode"],
                    "status": run["status"],
                    "comparative_eligible": score["comparative_eligible"],
                    "safe_exact_selection": score["safe_exact_selection"],
                    "exact": measurement["exact"],
                    "value": measurement.get("value"),
                    "minimum": measurement.get("minimum"),
                    "maximum": measurement.get("maximum"),
                    "source": measurement["source"],
                }
            )
            value = measurement.get("value")
            if (
                score["comparative_eligible"]
                and measurement["exact"] is True
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
            ):
                client = run["client"]
                cell = {
                    "task_id": run["task_id"],
                    "client_profile_id": client["profile_id"],
                    "client_version": client.get("client_version"),
                    "model_requested": client.get("model_requested"),
                    "model_resolved": client.get("model_resolved"),
                    "model_effort": client.get("model_effort"),
                    "delivery_mode": run["delivery_mode"],
                }
                key = dumps_json(cell)
                bucket = comparative_cells.setdefault(
                    key,
                    {"cell": cell, "arm_values": defaultdict(list)},
                )
                bucket["arm_values"][str(run["arm_id"])].append(float(value))

        exact_count = sum(row["exact"] is True for row in measurements)
        coverage[measure_id] = {
            "known_run_count": len(measurements),
            "exact_run_count": exact_count,
            "qualified_run_count": len(measurements) - exact_count,
            "unknown_or_missing_run_count": len(runs) - len(measurements),
        }
        cells: list[dict[str, Any]] = []
        for key in sorted(comparative_cells):
            bucket = comparative_cells[key]
            arm_values = bucket["arm_values"]
            present_arm_ids = set(arm_values)
            cells.append(
                {
                    "cell": bucket["cell"],
                    "present_arm_ids": sorted(present_arm_ids),
                    "required_arm_ids": sorted(required_arm_ids),
                    "complete_arm_set": present_arm_ids == required_arm_ids,
                    "arms": {
                        arm_id: _numeric_measure_summary(arm_values[arm_id])
                        for arm_id in sorted(arm_values)
                    },
                }
            )
        measure_reports[measure_id] = {
            "unit": specification["unit"],
            "scope": specification["scope"],
            "coverage": coverage[measure_id],
            "measurements": measurements,
            "comparative_cells": cells,
            "complete_comparative_cell_count": sum(
                cell["complete_arm_set"] for cell in cells
            ),
        }

    return {
        "policy": harness["study"]["efficiency_outcomes"],
        "telemetry_coverage": coverage,
        "measures": measure_reports,
        "interpretation": (
            "Per-run measurements retain their source and exactness. Comparative "
            "summaries include only exact numeric measurements from runs already "
            "eligible for comparison, grouped by task and host/model cell. A cell "
            "is complete only when every preregistered access arm is present."
        ),
    }


def build_report(
    runs: Sequence[Mapping[str, Any]],
    harness: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a deterministic report and keep readiness blocks out of score denominators."""

    run_ids: set[str] = set()
    scores: list[dict[str, Any]] = []
    for run in runs:
        run_id = _require_string(run.get("run_id"), "run.run_id")
        if run_id in run_ids:
            raise AIEvaluationError(f"duplicate run id: {run_id}")
        run_ids.add(run_id)
        scores.append(score_run(run, harness))
    scores.sort(key=lambda row: str(row["run_id"]))

    groups: dict[str, dict[str, Any]] = {}
    for field in (
        "client_profile_id",
        "arm_id",
        "delivery_mode",
        "capture_fidelity",
        "arm_enforcement",
        "constraint_enforcement",
    ):
        values = sorted({str(score[field]) for score in scores})
        groups[field] = {
            value: _aggregate(
                [score for score in scores if score[field] == value],
                eligibility_field="comparative_eligible",
            )
            for value in values
        }
    issue_by_failure_code: dict[str, set[str]] = {}
    for issue in harness["issue_register"]["issues"]:
        for code in issue["evaluation"]["failure_codes"]:
            issue_by_failure_code.setdefault(str(code), set()).add(str(issue["id"]))
    failure_counts = Counter(
        str(failure["code"])
        for run in runs
        for failure in run["failures"]
        if isinstance(failure, Mapping) and failure.get("code")
    )
    return {
        "schema": REPORT_SCHEMA,
        "study_id": harness["study"]["study_id"],
        "study_digest_sha256": _digest(harness["study"]),
        "tasks_digest_sha256": _digest(harness["tasks"]),
        "expected_digest_sha256": _digest(harness["expected"]),
        "personas_and_journeys_digest_sha256": _digest(
            harness["personas_and_journeys"]
        ),
        "issue_register_digest_sha256": _digest(harness["issue_register"]),
        "runs_digest_sha256": _digest(sorted(runs, key=lambda row: str(row["run_id"]))),
        "aggregate": _aggregate(scores, eligibility_field="comparative_eligible"),
        "validation_aggregate": _aggregate(
            scores,
            eligibility_field="validation_eligible",
        ),
        "descriptive_aggregate": _aggregate(scores, eligibility_field="eligible"),
        "groups": groups,
        "failure_summary": [
            {
                "code": code,
                "count": failure_counts[code],
                "issue_ids": sorted(issue_by_failure_code.get(code, set())),
            }
            for code in sorted(failure_counts)
        ],
        "efficiency": _efficiency_report(runs, scores, harness),
        "scores": scores,
        "interpretation": {
            "blocked_is_not_zero": True,
            "comparative_denominator": (
                "Only runs with enforced access arms and enforced applicable fault "
                "constraints, run-bound non-fixture evidence and non-fixture captures "
                "enter comparative aggregates. Fixture replays have a separate validation "
                "aggregate; observed and self-reported runs remain descriptive."
            ),
            "host_model_confounding_warning": (
                "Report the exact host and resolved model combination. Do not call a "
                "difference a client effect unless the design holds model and other "
                "causal factors constant."
            ),
            "determinism_boundary": (
                "Assignment, capture, replay and scoring are deterministic; model output is not."
            ),
        },
        "statistical_accuracy": {
            "evaluated": False,
            "score": None,
            "statement": ACCURACY_BOUNDARY,
        },
    }


def validate_research_artifacts(root: str | Path) -> dict[str, Any]:
    """Verify research hashes, observation links and public DOCX safety."""

    repository = Path(root).resolve()
    research = repository / "research"
    manifest = _load_object(research / "manifest.json")
    if manifest.get("schema") != "okf-ons.research-evidence-register.v1":
        raise AIEvaluationError("unsupported research evidence register schema")
    trial_ids = _unique_ids(manifest.get("trials"), "research trials")
    verified: list[dict[str, Any]] = []
    for row in manifest.get("artifacts", []):
        if not isinstance(row, Mapping):
            raise AIEvaluationError("research manifest artifact must be an object")
        relative = _require_string(row.get("path"), "research artifact path")
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise AIEvaluationError(f"unsafe research artifact path: {relative}")
        if row.get("trial_id") not in trial_ids:
            raise AIEvaluationError(f"research artifact has unknown trial: {relative}")
        path = research / relative
        digest = _file_digest(path)
        if digest != row.get("sha256"):
            raise AIEvaluationError(f"research artifact digest mismatch: {relative}")
        verified.append(
            {
                "path": relative,
                "sha256": digest,
                "trial_id": row["trial_id"],
                "role": row["role"],
            }
        )

    authorities = manifest.get("authority", {}).get("trial_authorities", [])
    if not isinstance(authorities, list):
        raise AIEvaluationError("research trial authorities must be a list")
    claude_authority = next(
        (
            row
            for row in authorities
            if isinstance(row, Mapping)
            and row.get("trial_id") == "claude-desktop-cowork-fable-5-20260718"
        ),
        None,
    )
    if not isinstance(claude_authority, Mapping):
        raise AIEvaluationError("research register has no Claude authority record")
    authoritative_artifact = _require_string(
        claude_authority.get("authoritative_artifact"),
        "Claude authoritative artifact",
    )
    markdown = (research / authoritative_artifact).read_text(encoding="utf-8")
    for finding in range(1, 10):
        if f"F{finding} " not in markdown and f"F{finding} —" not in markdown:
            raise AIEvaluationError(f"authoritative research record is missing F{finding}")

    docx_reports: list[dict[str, Any]] = []
    for artifact in verified:
        if not artifact["path"].endswith(".docx"):
            continue
        manifest_artifact = next(
            row for row in manifest["artifacts"] if row["path"] == artifact["path"]
        )
        source_digest = _require_string(
            manifest_artifact.get("sanitized_from_sha256"),
            f"sanitized source digest for {artifact['path']}",
        )
        if not re.fullmatch(r"[0-9a-f]{64}", source_digest):
            raise AIEvaluationError(
                f"invalid sanitized source digest for {artifact['path']}"
            )
        redaction_log = manifest_artifact.get("redaction_log")
        if not isinstance(redaction_log, Mapping):
            raise AIEvaluationError(
                f"missing DOCX redaction log for {artifact['path']}"
            )
        docx = research / artifact["path"]
        with zipfile.ZipFile(docx) as package:
            names = set(package.namelist())
            prohibited = [
                name for name in names if name.casefold().endswith("vbaproject.bin")
            ]
            if prohibited:
                raise AIEvaluationError(f"DOCX contains a macro project: {artifact['path']}")
            headers = sorted(name for name in names if name.startswith("word/header"))
            footers = sorted(name for name in names if name.startswith("word/footer"))
            if not headers or not footers:
                raise AIEvaluationError(
                    f"DOCX is missing provenance headers or page footers: {artifact['path']}"
                )
            footer_text = b"".join(package.read(name) for name in footers)
            if b"PAGE" not in footer_text:
                raise AIEvaluationError(
                    f"DOCX footers do not contain a PAGE field: {artifact['path']}"
                )
            try:
                public_inspection = inspect_public_docx(docx)
            except DocxReleaseError as error:
                raise AIEvaluationError(
                    f"unsafe public DOCX derivative {artifact['path']}: {error}"
                ) from error
            docx_reports.append(
                {
                    "path": artifact["path"],
                    "macros_present": False,
                    "page_field_present": True,
                    "embedded_media_present": any(
                        name.startswith("word/media/") for name in names
                    ),
                    "sanitized_from_sha256": source_digest,
                    "redaction_log": dict(redaction_log),
                    "public_inspection": public_inspection,
                }
            )

    public_release = manifest.get("public_release")
    if not isinstance(public_release, Mapping):
        raise AIEvaluationError("research register has no public-release review")
    if public_release.get("review_status") != "technical-public-release-review":
        raise AIEvaluationError("research public-release review status is not approved")
    if public_release.get("formal_information_governance_clearance") is not False:
        raise AIEvaluationError(
            "research register must not imply formal information-governance clearance"
        )
    reviewed_hashes = public_release.get("reviewed_artifact_sha256")
    if not isinstance(reviewed_hashes, Mapping):
        raise AIEvaluationError("research public-release hashes are missing")
    for report in docx_reports:
        if reviewed_hashes.get(report["path"]) != report["public_inspection"]["sha256"]:
            raise AIEvaluationError(
                f"research public-release review digest mismatch: {report['path']}"
            )

    for trial in manifest["trials"]:
        observation = _require_string(
            trial.get("observation"),
            f"research trial {trial['id']} observation",
        )
        observation_path = (research / observation).resolve()
        try:
            observation_path.relative_to(repository)
        except ValueError as error:
            raise AIEvaluationError(
                f"research trial observation escapes repository: {observation}"
            ) from error
        normalized = _load_object(observation_path)
        if normalized.get("observation_id") != trial["id"]:
            raise AIEvaluationError(
                f"research trial observation ID mismatch: {trial['id']}"
            )
        expected_digest = _require_string(
            trial.get("observation_sha256"),
            f"research trial {trial['id']} observation_sha256",
        )
        if _file_digest(observation_path) != expected_digest:
            raise AIEvaluationError(
                f"research trial observation digest mismatch: {trial['id']}"
            )

    return {
        "schema": "okf-ons.research-validation.v1",
        "evidence_id": manifest["evidence_id"],
        "trial_count": len(trial_ids),
        "artifacts": verified,
        "authoritative_artifact": authoritative_artifact,
        "docx_artifacts": docx_reports,
        "docx_structurally_valid": True,
        "docx_macros_present": False,
        "docx_page_field_present": True,
        "docx_public_metadata_safe": True,
        "public_release_review": dict(public_release),
    }


def _write_or_print(value: object, output: str | None) -> None:
    text = dumps_json(value)
    if output:
        Path(output).write_text(text, encoding="utf-8", newline="\n")
    else:
        print(text, end="")


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for fixture-safe validation, capture templates and scoring."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(_repository_root()))
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("validate")

    clients_parser = subparsers.add_parser("clients")
    clients_parser.add_argument("--initial-only", action="store_true")

    subparsers.add_parser("probe-clients")

    tasks_parser = subparsers.add_parser("tasks")
    tasks_parser.add_argument("--json", action="store_true")

    init_parser = subparsers.add_parser("init-run")
    init_parser.add_argument("--run-id", required=True)
    init_parser.add_argument("--client", required=True)
    init_parser.add_argument("--arm", required=True)
    init_parser.add_argument("--delivery-mode", required=True)
    init_parser.add_argument("--task", required=True)
    init_parser.add_argument("--replicate", type=int, default=1)
    init_parser.add_argument("--output")

    score_parser = subparsers.add_parser("score")
    score_parser.add_argument("--run", required=True)
    score_parser.add_argument("--output")

    report_parser = subparsers.add_parser("report")
    report_parser.add_argument("--runs", nargs="+", required=True)
    report_parser.add_argument("--output")

    research_parser = subparsers.add_parser("validate-research")
    research_parser.add_argument("--output")

    args = parser.parse_args(argv)
    root = Path(args.root)
    harness = load_harness(root)

    if args.command == "validate":
        value = {
            "study_id": harness["study"]["study_id"],
            "arms": len(harness["_ids"]["arms"]),
            "delivery_modes": len(harness["_ids"]["modes"]),
            "tasks": len(harness["_ids"]["tasks"]),
            "journeys": len(harness["_ids"]["journeys"]),
            "issues": len(harness["_ids"]["issues"]),
            "client_profiles": len(harness["_ids"]["profiles"]),
            "live_network_used": False,
            "paid_calls_used": False,
        }
        _write_or_print(value, None)
    elif args.command == "clients":
        profiles = harness["client_profiles"]["profiles"]
        if args.initial_only:
            profiles = [profile for profile in profiles if profile["initial_smoke_suite"]]
        _write_or_print(
            {
                "schema": PROFILES_SCHEMA,
                "profiles": profiles,
                "warning": harness["client_profiles"]["warning"],
            },
            None,
        )
    elif args.command == "probe-clients":
        _write_or_print(probe_local_clients(harness), None)
    elif args.command == "tasks":
        if args.json:
            _write_or_print(harness["tasks"], None)
        else:
            for task in harness["tasks"]["tasks"]:
                print(f"{task['id']}\t{task['stratum']}\t{task['title']}")
    elif args.command == "init-run":
        run = create_run_template(
            harness,
            run_id=args.run_id,
            client_profile=args.client,
            arm_id=args.arm,
            delivery_mode=args.delivery_mode,
            task_id=args.task,
            replicate=args.replicate,
        )
        _write_or_print(run, args.output)
    elif args.command == "score":
        run = _load_object(Path(args.run))
        _write_or_print(score_run(run, harness), args.output)
    elif args.command == "report":
        runs = [_load_object(Path(path)) for path in args.runs]
        _write_or_print(build_report(runs, harness), args.output)
    elif args.command == "validate-research":
        _write_or_print(validate_research_artifacts(root), args.output)
    else:  # pragma: no cover - argparse enforces this
        raise AssertionError(args.command)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
