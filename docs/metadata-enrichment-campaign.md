# Metadata enrichment campaign

This campaign measures and reduces metadata gaps in the generated OKF-ONS
bundle without treating metadata completeness as statistical accuracy. It began
at `2026-07-21T10:50:28Z` on branch `codex/metadata-gap-enrichment`.

## Baseline and target

The frozen v0.2.0 bundle contains 5,097 records and 71,358 possible evidence
slots: 14 existing `quality_evidence` fields per record. At baseline, 33,090
slots are populated and 38,268 are missing, for 46.3718% completeness.

The requested halfway milestone is therefore 19,134 newly populated,
source-backed slots: 52,224 of 71,358 populated, or 73.1859% completeness.
This fixed-denominator measure will be retained throughout the campaign so a
change in scoring rules cannot masquerade as enrichment.

`Not specified (metadata gap)` is also a generic OKF Explorer display label.
The profiler separately counts each Explorer view because dataset details,
resources and search results duplicate records and use different generic
schemas. Those raw UI counts are diagnostics, not one combined KPI:

| Explorer surface | Present | Possible | Missing | Complete |
| --- | ---: | ---: | ---: | ---: |
| Dataset detail fields | 86,122 | 178,395 | 92,273 | 48.2760% |
| Dataset dynamic provenance | 51,186 | 51,294 | 108 | 99.7894% |
| Resource detail fields | 10,194 | 66,261 | 56,067 | 15.3846% |
| Resource dynamic provenance | 51,186 | 51,294 | 108 | 99.7894% |
| Search-result fields | 50,551 | 76,455 | 25,904 | 66.1186% |
| Publisher fields | 24 | 96 | 72 | 25.0000% |
| OKF-ONS static-search facets | 53,475 | 86,649 | 33,174 | 61.7145% |

Fields such as an OpenAPI object type, a CKAN resource hash or a statistical
unit for a boundary asset can be inapplicable. An inapplicable field will not
be filled with an invented value merely to improve a percentage. The fixed
14-slot evidence metric remains the campaign's comparable raw measure while an
applicability-aware measure is developed alongside it.

The largest genuine evidence gaps at baseline are contact, population and
revision evidence (5,097 records each), methodology (5,088), quality
documentation (5,048), time coverage (4,989) and frequency (4,941). These
counts identify evidence availability; they do not imply that every field
applies to every source record.

## Stopping rule

Work proceeds in timed, source-specific batches. Each batch records elapsed
time, slots added, percentage-point change, slots per engineering hour,
remaining gaps, provenance and validation. Continue while a batch either:

- adds at least 0.5 percentage points per engineering hour (357 evidence slots
  per hour at this denominator); or
- unlocks a reusable acquisition or validation capability that is expected to
  exceed that rate in the next batch.

Stop after two consecutive completed batches fall below both conditions, or
earlier when the remaining fields are predominantly not applicable, require
unsupported record-by-record judgement, or lack authoritative public evidence.

## Progress

| Batch | Result | Elapsed | Slots added | Completeness | Yield |
| --- | --- | ---: | ---: | ---: | ---: |
| Baseline | Reproducible inventory established | 14 min | — | 46.3718% | — |
| 01 | Frozen Nomis annotations normalised | 5 min 13 sec | 3,620 | 51.4448% | 41,636 slots/hour |

Batch 01 closed 9.4596% of the original 38,268 gaps and completed 18.9192%
of the 19,134-slot halfway milestone. The evidence gains were population or
universe (+1,460), source-declared geography (+1,385), and conservatively
classified quality-documentation links (+775). A semantic guard rejected 109
Nomis `SubDescription` values that were gap sentinels or legacy codes rather
than population descriptions. No network acquisition was required.

The OKF-ONS static-search facet metric gained 4,306 populated cells, from
61.7145% to 66.6840%. The additional facet gain includes the explicit
field-derivation mode attached to source-normalised records. Fixed Explorer
dataset and search-result display rows did not move because those views do not
render the newly populated statistical fields; the facets and dataset decision
signature do.

The machine-readable baseline is
[`evaluation/metadata-completeness/baseline.json`](../evaluation/metadata-completeness/baseline.json).
Batch 01 has a
[`profile`](../evaluation/metadata-completeness/batch-01-frozen-nomis.json) and
[`comparison`](../evaluation/metadata-completeness/batch-01-comparison.json).
Regenerate and compare profiles with:

```bash
python scripts/profile_metadata_gaps.py \
  --bundle bundle \
  --output evaluation/metadata-completeness/baseline.json
python scripts/compare_metadata_gaps.py \
  evaluation/metadata-completeness/baseline.json \
  evaluation/metadata-completeness/batch-01-frozen-nomis.json \
  --elapsed-seconds 313
```
