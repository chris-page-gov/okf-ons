from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from okf_ons.evaluation import (  # noqa: E402
    ACCURACY_BOUNDARY,
    EvaluationError,
    dumps_report,
    evaluate_rankings,
    load_gold_suite,
)

GOLD_SUITE = ROOT / "evaluation" / "gold-queries.json"


def _minimal_suite() -> dict:
    return {
        "schema": "okf-ons-evaluation-suite.v1",
        "suite_id": "test-suite",
        "defaults": {"cutoffs": [1, 3]},
        "statistical_accuracy_policy": {
            "evaluated": False,
            "statement": "Metadata-only evaluation; statistical accuracy is out of scope.",
        },
        "queries": [
            {
                "id": "Q1",
                "query": "target measure",
                "intent": "Retrieve the target and distinguish its alternative.",
                "stratum": "confusable-measure",
                "why_confusing": "The candidate titles overlap.",
                "target_record_id": "target",
                "relevance": {"target": 3, "companion": 1},
                "alternatives": [
                    {
                        "record_id": "alternative",
                        "must_expose_by": 1,
                        "reason": "Related concept with a different denominator.",
                        "contrast_fields": ["measure_concept", "denominator"],
                    }
                ],
                "required_evidence": ["title", "statistical.measure"],
                "required_standards": ["DCAT-AP", "SDMX"],
            }
        ],
    }


def _perfect_rankings(suite: dict) -> dict:
    ranked_queries = []
    for query in suite["queries"]:
        target_id = query["target_record_id"]
        ordered_relevant = sorted(
            query["relevance"],
            key=lambda record_id: (
                -query["relevance"][record_id],
                record_id,
            ),
        )
        results = [
            {
                "record_id": record_id,
                "metadata": (
                    {field: "present" for field in query["required_evidence"]}
                    if record_id == target_id
                    else {}
                ),
                "standards": (
                    {
                        standard: {
                            "status": "aligned",
                            "evidence": "Profile mapping and source field",
                        }
                        for standard in query["required_standards"]
                    }
                    if record_id == target_id
                    else {}
                ),
                "contrast": {},
            }
            for record_id in ordered_relevant
        ]
        for alternative in query["alternatives"]:
            results.append(
                {
                    "record_id": alternative["record_id"],
                    "metadata": {},
                    "standards": {},
                    "contrast": {field: "explained" for field in alternative["contrast_fields"]},
                }
            )
        ranked_queries.append({"query_id": query["id"], "results": results})
    return {
        "schema": "okf-ons-evaluation-rankings.v1",
        "queries": ranked_queries,
    }


class GoldSuiteTest(unittest.TestCase):
    def test_gold_suite_is_valid_and_covers_confusable_ons_cases(self):
        suite = load_gold_suite(GOLD_SUITE)

        self.assertEqual(len(suite["queries"]), 12)
        self.assertEqual(len({query["id"] for query in suite["queries"]}), 12)
        self.assertFalse(suite["statistical_accuracy_policy"]["evaluated"])
        self.assertTrue(all(query["alternatives"] for query in suite["queries"]))
        strata = {query["stratum"] for query in suite["queries"]}
        self.assertGreaterEqual(
            strata,
            {
                "measure-definition",
                "time-granularity",
                "estimate-projection-census",
                "survey-administrative",
                "productivity-denominator",
                "event-time-basis",
                "census-variable",
            },
        )

    def test_suite_rejects_any_claim_to_evaluate_statistical_accuracy(self):
        suite = _minimal_suite()
        suite["statistical_accuracy_policy"]["evaluated"] = True

        with self.assertRaisesRegex(
            EvaluationError,
            "statistical_accuracy_policy.evaluated must be false",
        ):
            evaluate_rankings(
                suite,
                {"schema": "okf-ons-evaluation-rankings.v1", "queries": []},
            )


class MetricsTest(unittest.TestCase):
    def test_perfect_rankings_score_one_but_never_claim_statistical_accuracy(self):
        suite = load_gold_suite(GOLD_SUITE)
        report = evaluate_rankings(suite, _perfect_rankings(suite))

        self.assertEqual(
            report["metrics"]["recall_at_k"],
            {"1": 1.0, "3": 1.0, "5": 1.0, "10": 1.0},
        )
        self.assertEqual(report["metrics"]["mrr"], 1.0)
        self.assertEqual(report["metrics"]["primary_mrr"], 1.0)
        self.assertEqual(
            report["metrics"]["ndcg_at_k"],
            {"1": 1.0, "3": 1.0, "5": 1.0, "10": 1.0},
        )
        self.assertEqual(report["metrics"]["alternative_exposure_coverage"], 1.0)
        self.assertEqual(report["metrics"]["contrast_coverage"], 1.0)
        self.assertEqual(report["metrics"]["metadata_evidence_completeness"], 1.0)
        self.assertEqual(report["metrics"]["standards_coverage"], 1.0)
        self.assertEqual(
            report["statistical_accuracy"],
            {
                "evaluated": False,
                "score": None,
                "statement": ACCURACY_BOUNDARY,
            },
        )

    def test_partial_ranking_has_exact_retrieval_contrast_and_evidence_scores(self):
        suite = _minimal_suite()
        rankings = {
            "schema": "okf-ons-evaluation-rankings.v1",
            "queries": [
                {
                    "query_id": "Q1",
                    "results": [
                        {
                            "record_id": "alternative",
                            "contrast": {"measure_concept": "different"},
                        },
                        {
                            "record_id": "target",
                            "metadata": {
                                "title": "Target",
                                "statistical": {"measure": ""},
                            },
                            "standards": {
                                "dcat_ap": {
                                    "status": "partial",
                                    "evidence": "Mapped discovery fields",
                                }
                            },
                        },
                        {"record_id": "irrelevant"},
                    ],
                }
            ],
        }

        report = evaluate_rankings(suite, rankings)
        query = report["per_query"][0]

        self.assertEqual(query["target_rank"], 2)
        self.assertEqual(query["metrics"]["recall_at_k"], {"1": 0.0, "3": 0.5})
        self.assertEqual(query["metrics"]["mrr"], 0.5)
        self.assertEqual(query["metrics"]["primary_mrr"], 0.5)
        self.assertEqual(query["metrics"]["ndcg_at_k"]["1"], 0.0)
        self.assertAlmostEqual(query["metrics"]["ndcg_at_k"]["3"], 0.578764, places=6)
        self.assertEqual(query["metrics"]["alternative_exposure_coverage"], 1.0)
        self.assertEqual(query["metrics"]["contrast_coverage"], 0.5)
        self.assertEqual(query["metrics"]["metadata_evidence_completeness"], 0.5)
        self.assertEqual(query["metrics"]["standards_coverage"], 0.5)
        self.assertEqual(query["metadata_evidence"]["missing_fields"], ["statistical.measure"])
        self.assertEqual(query["standards"]["present"], ["DCAT-AP"])

    def test_missing_query_receives_zero_credit_instead_of_being_dropped(self):
        report = evaluate_rankings(
            _minimal_suite(),
            {"schema": "okf-ons-evaluation-rankings.v1", "queries": []},
        )

        self.assertEqual(report["questions_evaluated"], 1)
        self.assertEqual(report["metrics"]["recall_at_k"], {"1": 0.0, "3": 0.0})
        self.assertEqual(report["metrics"]["mrr"], 0.0)
        self.assertEqual(report["metrics"]["ndcg_at_k"], {"1": 0.0, "3": 0.0})
        self.assertEqual(report["metrics"]["alternative_exposure_coverage"], 0.0)
        self.assertEqual(report["metrics"]["contrast_coverage"], 0.0)
        self.assertEqual(report["metrics"]["metadata_evidence_completeness"], 0.0)
        self.assertEqual(report["metrics"]["standards_coverage"], 0.0)

    def test_duplicate_ranked_record_is_rejected(self):
        rankings = {
            "schema": "okf-ons-evaluation-rankings.v1",
            "queries": [
                {
                    "query_id": "Q1",
                    "results": [
                        {"record_id": "target"},
                        {"record_id": "target"},
                    ],
                }
            ],
        }

        with self.assertRaisesRegex(EvaluationError, "duplicate record id: target"):
            evaluate_rankings(_minimal_suite(), rankings)

    def test_standard_claims_require_bounded_status_and_evidence(self):
        rankings = {
            "schema": "okf-ons-evaluation-rankings.v1",
            "queries": [
                {
                    "query_id": "Q1",
                    "results": [
                        {
                            "record_id": "target",
                            "standards": {
                                "SDMX": {
                                    "status": "certified",
                                    "evidence": "Unsupported assertion",
                                }
                            },
                        }
                    ],
                }
            ],
        }
        with self.assertRaisesRegex(EvaluationError, "status must be one of"):
            evaluate_rankings(_minimal_suite(), rankings)

        rankings["queries"][0]["results"][0]["standards"]["SDMX"] = {"status": "aligned"}
        with self.assertRaisesRegex(EvaluationError, "evidence is required"):
            evaluate_rankings(_minimal_suite(), rankings)

        rankings["queries"][0]["results"][0]["standards"]["SDMX"] = {"status": "not-evaluated"}
        report = evaluate_rankings(_minimal_suite(), rankings)
        self.assertEqual(report["metrics"]["standards_coverage"], 0.0)
        claims = report["per_query"][0]["standards"]["claims"]
        self.assertEqual(
            claims,
            [
                {"standard": "DCAT-AP", "status": "missing", "covered": False},
                {"standard": "SDMX", "status": "not-evaluated", "covered": False},
            ],
        )

    def test_report_is_timestamp_free_and_byte_deterministic(self):
        suite = load_gold_suite(GOLD_SUITE)
        rankings = _perfect_rankings(suite)

        first = evaluate_rankings(suite, rankings)
        second = evaluate_rankings(copy.deepcopy(suite), copy.deepcopy(rankings))

        self.assertEqual(dumps_report(first), dumps_report(second))
        self.assertEqual(len(first["suite_digest_sha256"]), 64)
        self.assertEqual(len(first["rankings_digest_sha256"]), 64)
        self.assertNotIn("generated_at", json.loads(dumps_report(first)))


if __name__ == "__main__":
    unittest.main()
