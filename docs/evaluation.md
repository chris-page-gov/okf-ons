# Evaluating ONS dataset discovery

`okf-ons` evaluates whether a search or selection flow retrieves the intended
ONS dataset, exposes plausible alternatives, explains their important
differences, and supplies enough metadata evidence for a reader to assess
fitness for use.

The evaluation is deterministic and observation-free. It is suitable for
comparing static OKF Explorer ranking changes, MCP selection plans, or another
retrieval implementation against the same frozen bundle.

## Assurance boundary

Metadata completeness is **not** statistical accuracy.

The evaluator can establish that a result exposes a measure, unit, population,
geography, time basis, dimensions, revision state, quality note and
provenance. It cannot establish that:

- an observation value is correct;
- an estimate or calculation follows the published methodology;
- revisions have been applied correctly;
- two series are statistically comparable;
- a user's interpretation is valid.

Every report therefore contains:

```json
{
  "statistical_accuracy": {
    "evaluated": false,
    "score": null
  }
}
```

Observation-level checks against a frozen authoritative ONS release,
methodology and revision history belong in a separate statistical validation
suite. Standards coverage similarly records evidence-backed `aligned` or
`partial` claims; it is not a standards-compliance certification.

## Gold suite

[`evaluation/gold-queries.json`](../evaluation/gold-queries.json) is a
first-release set of deliberately confusable ONS discovery cases. It covers
examples such as:

- CPIH versus CPI and RPI;
- monthly GDP versus quarterly and regional GDP;
- population estimates versus projections and Census counts;
- LFS unemployment versus claimant count and economic inactivity;
- survey crime versus police-recorded crime;
- output per hour versus output per worker and GDP per head;
- deaths by registration date versus occurrence date;
- near-identical Census occupancy variables.

Each query declares:

- a canonical `target_record_id`;
- graded `relevance` for ranking metrics;
- alternatives that must be exposed by a specified rank;
- contrast fields that explain why an alternative is different;
- dotted metadata evidence paths required on the target;
- metadata standards that should be declared on the target.

The canonical IDs are curator aliases. Before enabling a release gate, reconcile
them to the stable IDs in the frozen OKF-ONS bundle and record that change in
the suite version.

## Ranking input

The evaluator accepts `okf-ons-evaluation-rankings.v1` JSON:

```json
{
  "schema": "okf-ons-evaluation-rankings.v1",
  "queries": [
    {
      "query_id": "ONS-Q001",
      "results": [
        {
          "record_id": "consumer-prices-cpih",
          "metadata": {
            "title": "Consumer Prices Index including owner occupiers' housing costs",
            "identity": {
              "dataset_id": "cpih",
              "edition": "time-series",
              "version": "42"
            },
            "provenance": {
              "source_url": "https://www.ons.gov.uk/"
            },
            "publication": {
              "release_date": "2026-07-15",
              "revision_status": "provisional"
            },
            "statistical": {
              "measure": "12-month rate",
              "unit": "percent",
              "population": "UK consumer expenditure",
              "time_coverage": "1989-01/2026-06",
              "frequency": "monthly",
              "dimensions": ["time", "aggregate"],
              "quality_notes": ["Latest period may be revised"]
            }
          },
          "standards": {
            "DCAT-AP": {
              "status": "aligned",
              "evidence": "Dataset discovery fields mapped in the OKF profile"
            },
            "SDMX": {
              "status": "partial",
              "evidence": "Dimensions and codelists retained from the source"
            },
            "ISO 8601": {
              "status": "aligned",
              "evidence": "Machine-readable time intervals"
            },
            "PROV-O": {
              "status": "partial",
              "evidence": "Source and transformation provenance retained"
            }
          },
          "contrast": {}
        },
        {
          "record_id": "consumer-prices-cpi",
          "metadata": {},
          "standards": {},
          "contrast": {
            "measure_concept": "Consumer price inflation excluding OOH",
            "housing_cost_treatment": "Owner occupiers' housing costs excluded",
            "population_scope": "CPI expenditure population"
          }
        }
      ]
    }
  ]
}
```

Results are ranked in array order. Duplicate query or record IDs are rejected.
A missing gold query is allowed and receives zero retrieval and coverage
credit. Additional result properties are ignored, so a search implementation
may retain its native score and diagnostics.

Dotted evidence paths first match an exact metadata key, then traverse nested
objects. Empty strings, empty containers and `null` are missing; numeric zero
and boolean `false` are present values. Standard identifiers are compared
case-insensitively with spaces, underscores and hyphens normalised. A standard
claim is an object whose `status` is exactly one of `aligned`, `partial`,
`not-evaluated`, or `not-applicable`. `aligned` and `partial` claims also
require a non-empty evidence pointer. Only those two evidence-backed states
receive standards-coverage credit; none implies certification.

## Metrics

The report includes per-query diagnostics and aggregate metrics:

- **Recall@k**: the fraction of all records with a positive relevance grade
  present in the first `k` results. Aggregate Recall@k is the macro mean across
  queries.
- **MRR**: reciprocal rank of the first positively relevant result within the
  bounded evaluation depth. `primary_mrr` separately uses the declared target,
  preventing a plausible companion from hiding poor target ranking.
- **nDCG@k**: graded discounted cumulative gain using
  `(2^grade - 1) / log2(rank + 1)`, normalised against the ideal ranking.
- **Alternative-exposure coverage**: alternatives appearing at or before their
  individual `must_expose_by` rank, divided by all expected alternatives.
- **Contrast coverage**: required contrast fields present on alternatives that
  met their exposure deadline, divided by all required contrast fields.
  An absent or late alternative receives no contrast credit.
- **Metadata evidence completeness**: required dotted fields present on the
  target when it appears within the evaluation depth, divided by all required
  fields.
- **Standards coverage**: required standard identifiers with an
  evidence-backed `aligned` or `partial` claim on the exposed target, divided
  by all required standards. `not-evaluated` and `not-applicable` remain
  visible in diagnostics but do not receive coverage credit.

Retrieval metrics are macro-averaged so every user question has equal weight.
Coverage metrics use explicit micro numerators and denominators, which are
included in `coverage_counts`.

The evaluation depth is the larger of the maximum Recall/nDCG cutoff and the
largest alternative-exposure cutoff. This keeps MRR and evidence exposure
bounded and repeatable.

## Running the evaluator

With the repository package installed:

```bash
python -m okf_ons.evaluation \
  --suite evaluation/gold-queries.json \
  --rankings evaluation/results/candidate-rankings.json \
  --output evaluation/results/candidate-report.json
```

The Python API is:

```python
from okf_ons.evaluation import evaluate_rankings, load_gold_suite

suite = load_gold_suite("evaluation/gold-queries.json")
report = evaluate_rankings(suite, rankings)
```

No timestamp is written. The evaluator:

- processes queries in gold-suite order;
- uses fixed suite cutoffs;
- rejects duplicate identifiers and non-finite JSON;
- rounds metrics to six decimal places;
- includes SHA-256 digests of canonical suite and ranking inputs;
- serialises reports with sorted keys through `dumps_report`.

The same inputs consequently produce byte-identical report text.

## Curation and release use

For each frozen bundle release:

1. Reconcile gold aliases with actual bundle record IDs.
2. Review target and alternative judgements with an ONS subject specialist.
3. Add cases for newly discovered source families and observed search failures.
4. Capture rankings from the same frozen bundle for the control and candidate.
5. Compare the complete metric vector; do not optimise nDCG while reducing
   alternatives, contrast, evidence or standards coverage.
6. Run OKF Explorer browser journeys separately for interaction,
   accessibility, deep-link and rendering behaviour.
7. Run separate observation-level validation wherever a claim of statistical
   correctness is required.

The twelve cases are a strong regression seed, not a complete representation
of all ONS user needs. Extend toward the MCP Geo research target of at least 20
canonical tasks, including revision-sensitive and small-area cases, as bundle
coverage stabilises.

## AI-client utility is a separate study

Static ranking quality and agent utility must not be folded into one score.
The provider-neutral harness under
[`evaluation/ai-client/`](../evaluation/ai-client/) measures whether a
particular host/model combination can orient, select, hydrate, preserve
caveats, expose alternatives and prepare an MCP hand-off under a declared
access arm.

Its eight public tasks are a development smoke suite. They do not satisfy the
confirmatory design target of at least 50 unseen subject-reviewed questions,
three access arms, repeated runs and blinded assessment. See the
[agent-access and multi-client evaluation proposal](agent-access-and-evaluation-proposal.md)
for that protocol and the separation between readiness blocks, task failures
and answer-quality scores.
