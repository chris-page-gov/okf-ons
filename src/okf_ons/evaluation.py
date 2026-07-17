"""Deterministic evaluation for ONS metadata discovery rankings.

The evaluator measures whether a ranking helps a reader find and distinguish
the right ONS dataset and inspect the metadata needed to judge fitness for use.
It deliberately does not score observation values or statistical accuracy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

SUITE_SCHEMA = "okf-ons-evaluation-suite.v1"
RANKINGS_SCHEMA = "okf-ons-evaluation-rankings.v1"
REPORT_SCHEMA = "okf-ons-evaluation-report.v1"
STANDARD_STATUSES = frozenset({"aligned", "partial", "not-evaluated", "not-applicable"})
ACCURACY_BOUNDARY = (
    "Metadata evidence completeness shows whether evidence is available for inspection. "
    "It does not establish that observations, estimates, calculations, or interpretations "
    "are statistically accurate."
)


class EvaluationError(ValueError):
    """Raised when an evaluation input violates the deterministic contract."""


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _require_string(value: object, label: str) -> str:
    if not _is_non_empty_string(value):
        raise EvaluationError(f"{label} must be a non-empty string")
    return str(value).strip()


def _require_string_list(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise EvaluationError(f"{label} must be a non-empty list")
    strings = [_require_string(item, f"{label} item") for item in value]
    if len(set(strings)) != len(strings):
        raise EvaluationError(f"{label} must not contain duplicates")
    return strings


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as error:
        raise EvaluationError(f"evaluation input is not canonical JSON: {error}") from error


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _round(value: float) -> float:
    return round(value, 6)


def _ratio(numerator: int, denominator: int) -> float:
    return _round(numerator / denominator) if denominator else 1.0


def _mean(values: Sequence[float]) -> float:
    return _round(sum(values) / len(values)) if values else 0.0


def _has_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _path_value(values: Mapping[str, Any], path: str) -> object:
    """Resolve a dotted evidence path, preferring an exact top-level key."""

    if path in values:
        return values[path]
    current: object = values
    for segment in path.split("."):
        if not isinstance(current, Mapping) or segment not in current:
            return None
        current = current[segment]
    return current


def _canonical_standard(value: str) -> str:
    return re.sub(r"[-_\s]+", "-", value.strip().casefold())


def _dcg(grades: Sequence[int]) -> float:
    return sum((2**grade - 1) / math.log2(index + 2) for index, grade in enumerate(grades))


def _ndcg(relevance: Mapping[str, int], result_ids: Sequence[str], cutoff: int) -> float:
    actual = [relevance.get(record_id, 0) for record_id in result_ids[:cutoff]]
    ideal = sorted(relevance.values(), reverse=True)[:cutoff]
    ideal_gain = _dcg(ideal)
    return _round(_dcg(actual) / ideal_gain) if ideal_gain else 1.0


def validate_suite(suite: Mapping[str, Any]) -> None:
    """Validate the gold-suite structure and its statistical-accuracy boundary."""

    if suite.get("schema") != SUITE_SCHEMA:
        raise EvaluationError(f"unsupported suite schema: {suite.get('schema')!r}")
    _require_string(suite.get("suite_id"), "suite_id")

    defaults = suite.get("defaults")
    if not isinstance(defaults, Mapping):
        raise EvaluationError("defaults must be an object")
    cutoffs = defaults.get("cutoffs")
    if (
        not isinstance(cutoffs, list)
        or not cutoffs
        or any(
            not isinstance(cutoff, int) or isinstance(cutoff, bool) or cutoff < 1
            for cutoff in cutoffs
        )
        or cutoffs != sorted(set(cutoffs))
    ):
        raise EvaluationError("defaults.cutoffs must be sorted, unique positive integers")

    policy = suite.get("statistical_accuracy_policy")
    if not isinstance(policy, Mapping) or policy.get("evaluated") is not False:
        raise EvaluationError("statistical_accuracy_policy.evaluated must be false")
    _require_string(policy.get("statement"), "statistical_accuracy_policy.statement")

    queries = suite.get("queries")
    if not isinstance(queries, list) or not queries:
        raise EvaluationError("queries must be a non-empty list")

    query_ids: set[str] = set()
    for query_index, query in enumerate(queries):
        label = f"queries[{query_index}]"
        if not isinstance(query, Mapping):
            raise EvaluationError(f"{label} must be an object")
        query_id = _require_string(query.get("id"), f"{label}.id")
        if query_id in query_ids:
            raise EvaluationError(f"duplicate query id: {query_id}")
        query_ids.add(query_id)
        _require_string(query.get("query"), f"{label}.query")
        _require_string(query.get("intent"), f"{label}.intent")
        _require_string(query.get("stratum"), f"{label}.stratum")
        _require_string(query.get("why_confusing"), f"{label}.why_confusing")

        target_id = _require_string(query.get("target_record_id"), f"{label}.target_record_id")
        relevance = query.get("relevance")
        if not isinstance(relevance, Mapping) or not relevance:
            raise EvaluationError(f"{label}.relevance must be a non-empty object")
        for record_id, grade in relevance.items():
            _require_string(record_id, f"{label}.relevance record id")
            if not isinstance(grade, int) or isinstance(grade, bool) or not 1 <= grade <= 3:
                raise EvaluationError(f"{label}.relevance grades must be integers from 1 to 3")
        if target_id not in relevance:
            raise EvaluationError(f"{label}.target_record_id must appear in relevance")
        if relevance[target_id] != max(relevance.values()):
            raise EvaluationError(f"{label}.target_record_id must have the highest relevance grade")

        alternatives = query.get("alternatives")
        if not isinstance(alternatives, list) or not alternatives:
            raise EvaluationError(f"{label}.alternatives must be a non-empty list")
        alternative_ids: set[str] = set()
        for alternative_index, alternative in enumerate(alternatives):
            alternative_label = f"{label}.alternatives[{alternative_index}]"
            if not isinstance(alternative, Mapping):
                raise EvaluationError(f"{alternative_label} must be an object")
            alternative_id = _require_string(
                alternative.get("record_id"), f"{alternative_label}.record_id"
            )
            if alternative_id == target_id or alternative_id in alternative_ids:
                raise EvaluationError(
                    f"{alternative_label}.record_id must be unique and non-target"
                )
            alternative_ids.add(alternative_id)
            cutoff = alternative.get("must_expose_by")
            if not isinstance(cutoff, int) or isinstance(cutoff, bool) or cutoff < 1:
                raise EvaluationError(f"{alternative_label}.must_expose_by must be positive")
            _require_string(alternative.get("reason"), f"{alternative_label}.reason")
            _require_string_list(
                alternative.get("contrast_fields"), f"{alternative_label}.contrast_fields"
            )

        _require_string_list(query.get("required_evidence"), f"{label}.required_evidence")
        _require_string_list(query.get("required_standards"), f"{label}.required_standards")


def validate_rankings(
    rankings: Mapping[str, Any],
    *,
    known_query_ids: set[str],
) -> None:
    """Validate ranked results without requiring every gold query to be present."""

    if rankings.get("schema") != RANKINGS_SCHEMA:
        raise EvaluationError(f"unsupported rankings schema: {rankings.get('schema')!r}")
    rows = rankings.get("queries")
    if not isinstance(rows, list):
        raise EvaluationError("rankings.queries must be a list")

    seen_queries: set[str] = set()
    for query_index, row in enumerate(rows):
        label = f"rankings.queries[{query_index}]"
        if not isinstance(row, Mapping):
            raise EvaluationError(f"{label} must be an object")
        query_id = _require_string(row.get("query_id"), f"{label}.query_id")
        if query_id not in known_query_ids:
            raise EvaluationError(f"{label} refers to unknown query id: {query_id}")
        if query_id in seen_queries:
            raise EvaluationError(f"duplicate ranked query id: {query_id}")
        seen_queries.add(query_id)
        results = row.get("results")
        if not isinstance(results, list):
            raise EvaluationError(f"{label}.results must be a list")
        seen_records: set[str] = set()
        for result_index, result in enumerate(results):
            result_label = f"{label}.results[{result_index}]"
            if not isinstance(result, Mapping):
                raise EvaluationError(f"{result_label} must be an object")
            record_id = _require_string(result.get("record_id"), f"{result_label}.record_id")
            if record_id in seen_records:
                raise EvaluationError(f"{label} contains duplicate record id: {record_id}")
            seen_records.add(record_id)
            for object_field in ("metadata", "contrast"):
                value = result.get(object_field, {})
                if not isinstance(value, Mapping):
                    raise EvaluationError(f"{result_label}.{object_field} must be an object")
            standards = result.get("standards", {})
            if not isinstance(standards, Mapping):
                raise EvaluationError(f"{result_label}.standards must be an object")
            canonical_standards: set[str] = set()
            for standard, claim in standards.items():
                standard_name = _require_string(standard, f"{result_label}.standards identifier")
                canonical_standard = _canonical_standard(standard_name)
                if canonical_standard in canonical_standards:
                    raise EvaluationError(
                        f"{result_label}.standards contains a duplicate normalised "
                        f"identifier: {standard_name}"
                    )
                canonical_standards.add(canonical_standard)
                if not isinstance(claim, Mapping):
                    raise EvaluationError(
                        f"{result_label}.standards.{standard_name} must be an object"
                    )
                status = claim.get("status")
                if status not in STANDARD_STATUSES:
                    raise EvaluationError(
                        f"{result_label}.standards.{standard_name}.status must be one of "
                        f"{sorted(STANDARD_STATUSES)}"
                    )
                if status in {"aligned", "partial"} and not _has_value(claim.get("evidence")):
                    raise EvaluationError(
                        f"{result_label}.standards.{standard_name}.evidence is required "
                        f"for status {status}"
                    )


def load_gold_suite(path: str | Path) -> dict[str, Any]:
    """Load and validate a gold query suite."""

    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise EvaluationError("gold suite root must be an object")
    validate_suite(value)
    return value


def load_rankings(path: str | Path, *, known_query_ids: set[str]) -> dict[str, Any]:
    """Load and validate rankings produced by a search implementation."""

    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise EvaluationError("rankings root must be an object")
    validate_rankings(value, known_query_ids=known_query_ids)
    return value


def _evaluate_query(
    query: Mapping[str, Any],
    results: Sequence[Mapping[str, Any]],
    cutoffs: Sequence[int],
) -> dict[str, Any]:
    relevance = {str(record_id): int(grade) for record_id, grade in query["relevance"].items()}
    alternatives = list(query["alternatives"])
    exposure_depth = max(int(alternative["must_expose_by"]) for alternative in alternatives)
    evaluation_depth = max(max(cutoffs), exposure_depth)
    result_ids = [str(result["record_id"]) for result in results]
    evaluated_ids = result_ids[:evaluation_depth]
    ranked = {
        str(result["record_id"]): (rank, result) for rank, result in enumerate(results, start=1)
    }

    relevant_ids = set(relevance)
    recall_at_k = {
        str(cutoff): _ratio(
            len(relevant_ids.intersection(result_ids[:cutoff])),
            len(relevant_ids),
        )
        for cutoff in cutoffs
    }
    first_relevant_rank = next(
        (
            rank
            for rank, record_id in enumerate(evaluated_ids, start=1)
            if record_id in relevant_ids
        ),
        None,
    )
    reciprocal_rank = _round(1 / first_relevant_rank) if first_relevant_rank else 0.0
    ndcg_at_k = {str(cutoff): _ndcg(relevance, result_ids, cutoff) for cutoff in cutoffs}

    target_id = str(query["target_record_id"])
    target_ranked = ranked.get(target_id)
    target_rank = target_ranked[0] if target_ranked else None
    target_exposed = target_rank is not None and target_rank <= evaluation_depth
    target_result = target_ranked[1] if target_exposed and target_ranked else None
    primary_reciprocal_rank = _round(1 / target_rank) if target_exposed and target_rank else 0.0

    alternative_details: list[dict[str, Any]] = []
    exposed_alternatives = 0
    required_contrast_fields = 0
    present_contrast_fields = 0
    missing_contrast: list[dict[str, str]] = []
    for alternative in alternatives:
        alternative_id = str(alternative["record_id"])
        ranked_alternative = ranked.get(alternative_id)
        rank = ranked_alternative[0] if ranked_alternative else None
        cutoff = int(alternative["must_expose_by"])
        exposed = rank is not None and rank <= cutoff
        if exposed:
            exposed_alternatives += 1
        contrast = (
            ranked_alternative[1].get("contrast", {}) if exposed and ranked_alternative else {}
        )
        present_fields: list[str] = []
        missing_fields: list[str] = []
        for field in alternative["contrast_fields"]:
            required_contrast_fields += 1
            if isinstance(contrast, Mapping) and _has_value(_path_value(contrast, field)):
                present_contrast_fields += 1
                present_fields.append(field)
            else:
                missing_fields.append(field)
                missing_contrast.append({"record_id": alternative_id, "field": field})
        alternative_details.append(
            {
                "record_id": alternative_id,
                "rank": rank,
                "must_expose_by": cutoff,
                "exposed": exposed,
                "present_contrast_fields": present_fields,
                "missing_contrast_fields": missing_fields,
            }
        )

    metadata = target_result.get("metadata", {}) if target_result else {}
    required_evidence = list(query["required_evidence"])
    present_evidence = [
        field
        for field in required_evidence
        if isinstance(metadata, Mapping) and _has_value(_path_value(metadata, field))
    ]
    missing_evidence = [field for field in required_evidence if field not in set(present_evidence)]

    raw_standard_claims = target_result.get("standards", {}) if target_result else {}
    declared_standards = {
        _canonical_standard(str(standard)): claim for standard, claim in raw_standard_claims.items()
    }
    required_standards = list(query["required_standards"])
    standard_claims = []
    for standard in required_standards:
        claim = declared_standards.get(_canonical_standard(standard))
        status = claim.get("status") if isinstance(claim, Mapping) else "missing"
        covered = (
            status in {"aligned", "partial"}
            and isinstance(claim, Mapping)
            and _has_value(claim.get("evidence"))
        )
        standard_claims.append(
            {
                "standard": standard,
                "status": status,
                "covered": covered,
            }
        )
    present_standards = [claim["standard"] for claim in standard_claims if claim["covered"]]
    missing_standards = [
        standard for standard in required_standards if standard not in set(present_standards)
    ]

    return {
        "query_id": query["id"],
        "query": query["query"],
        "stratum": query["stratum"],
        "evaluation_depth": evaluation_depth,
        "submitted_result_count": len(results),
        "retrieved_record_ids": evaluated_ids,
        "target_record_id": target_id,
        "target_rank": target_rank,
        "metrics": {
            "recall_at_k": recall_at_k,
            "mrr": reciprocal_rank,
            "primary_mrr": primary_reciprocal_rank,
            "ndcg_at_k": ndcg_at_k,
            "alternative_exposure_coverage": _ratio(exposed_alternatives, len(alternatives)),
            "contrast_coverage": _ratio(present_contrast_fields, required_contrast_fields),
            "metadata_evidence_completeness": _ratio(len(present_evidence), len(required_evidence)),
            "standards_coverage": _ratio(len(present_standards), len(required_standards)),
        },
        "alternative_exposure": {
            "expected": len(alternatives),
            "exposed": exposed_alternatives,
            "details": alternative_details,
        },
        "contrast": {
            "required_fields": required_contrast_fields,
            "present_fields": present_contrast_fields,
            "missing": missing_contrast,
        },
        "metadata_evidence": {
            "target_exposed": target_exposed,
            "required_fields": required_evidence,
            "present_fields": present_evidence,
            "missing_fields": missing_evidence,
        },
        "standards": {
            "required": required_standards,
            "present": present_standards,
            "missing": missing_standards,
            "claims": standard_claims,
        },
    }


def evaluate_rankings(
    suite: Mapping[str, Any],
    rankings: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate rankings and return a timestamp-free, deterministic report."""

    validate_suite(suite)
    queries = list(suite["queries"])
    known_query_ids = {str(query["id"]) for query in queries}
    validate_rankings(rankings, known_query_ids=known_query_ids)
    cutoffs = [int(cutoff) for cutoff in suite["defaults"]["cutoffs"]]
    rankings_by_query = {str(row["query_id"]): list(row["results"]) for row in rankings["queries"]}

    per_query = [
        _evaluate_query(query, rankings_by_query.get(str(query["id"]), []), cutoffs)
        for query in queries
    ]

    recall_at_k = {
        str(cutoff): _mean([row["metrics"]["recall_at_k"][str(cutoff)] for row in per_query])
        for cutoff in cutoffs
    }
    ndcg_at_k = {
        str(cutoff): _mean([row["metrics"]["ndcg_at_k"][str(cutoff)] for row in per_query])
        for cutoff in cutoffs
    }

    exposure_expected = sum(row["alternative_exposure"]["expected"] for row in per_query)
    exposure_present = sum(row["alternative_exposure"]["exposed"] for row in per_query)
    contrast_required = sum(row["contrast"]["required_fields"] for row in per_query)
    contrast_present = sum(row["contrast"]["present_fields"] for row in per_query)
    evidence_required = sum(len(row["metadata_evidence"]["required_fields"]) for row in per_query)
    evidence_present = sum(len(row["metadata_evidence"]["present_fields"]) for row in per_query)
    standards_required = sum(len(row["standards"]["required"]) for row in per_query)
    standards_present = sum(len(row["standards"]["present"]) for row in per_query)

    return {
        "schema": REPORT_SCHEMA,
        "suite_id": suite["suite_id"],
        "suite_digest_sha256": _digest(suite),
        "rankings_digest_sha256": _digest(rankings),
        "questions_evaluated": len(per_query),
        "cutoffs": cutoffs,
        "metrics": {
            "recall_at_k": recall_at_k,
            "mrr": _mean([row["metrics"]["mrr"] for row in per_query]),
            "primary_mrr": _mean([row["metrics"]["primary_mrr"] for row in per_query]),
            "ndcg_at_k": ndcg_at_k,
            "alternative_exposure_coverage": _ratio(exposure_present, exposure_expected),
            "contrast_coverage": _ratio(contrast_present, contrast_required),
            "metadata_evidence_completeness": _ratio(evidence_present, evidence_required),
            "standards_coverage": _ratio(standards_present, standards_required),
        },
        "coverage_counts": {
            "alternatives": {
                "expected": exposure_expected,
                "exposed": exposure_present,
            },
            "contrast_fields": {
                "required": contrast_required,
                "present": contrast_present,
            },
            "metadata_evidence_fields": {
                "required": evidence_required,
                "present": evidence_present,
            },
            "standards": {
                "required": standards_required,
                "present": standards_present,
            },
        },
        "statistical_accuracy": {
            "evaluated": False,
            "score": None,
            "statement": ACCURACY_BOUNDARY,
        },
        "per_query": per_query,
    }


def dumps_report(report: Mapping[str, Any]) -> str:
    """Serialize a report in a stable representation suitable for CI diffs."""

    return (
        json.dumps(
            report,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", required=True, type=Path)
    parser.add_argument("--rankings", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)

    suite = load_gold_suite(arguments.suite)
    query_ids = {str(query["id"]) for query in suite["queries"]}
    rankings = load_rankings(arguments.rankings, known_query_ids=query_ids)
    report_text = dumps_report(evaluate_rankings(suite, rankings))
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(report_text, encoding="utf-8")
    else:
        print(report_text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
