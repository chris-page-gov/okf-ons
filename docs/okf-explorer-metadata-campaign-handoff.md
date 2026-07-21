# OKF Explorer metadata-campaign handoff

## Decision

OKF Explorer requires updates to realise the full value of OKF-ONS. The bundle
loads through the direct URL today, but it is not registered, it collapses
different evidence states into one gap label, it does not provide a first-class
alternative-comparison workflow or present the newly surfaced
quality/provenance fields as first-class information, and its hydration
strategy is expensive for a corpus of this size.

This handoff generalises the lessons from the timed OKF-ONS metadata-enrichment
campaign. Evidence completeness, applicability, discovery utility and transfer
cost are separate dimensions; improving one must not silently redefine
another.

Canonical access URLs:

- Bundle: <https://chris-page-gov.github.io/okf-ons/okf-explorer.json>
- Direct Explorer view: <https://chris-page-gov.github.io/okf-explorer/?bundle=https%3A%2F%2Fchris-page-gov.github.io%2Fokf-ons%2Fokf-explorer.json>
- Explorer repository: <https://github.com/chris-page-gov/okf-explorer>

## What the campaign demonstrated

- A generic `Not specified (metadata gap)` label does not distinguish absent
  evidence from an inapplicable field, a conflict, or a legacy unknown value.
- Useful source concepts must remain semantically narrow. A geography reference
  date is not statistical time coverage; a source version label is not revision
  status; a quality statement is not methodology.
- Field-level provenance matters. Users and agents need to distinguish
  source-declared values from deterministic extraction, normalisation,
  crosswalks and inference.
- Source quality notes describe data limitations. A metadata-completeness score
  describes evidence availability. They must not share a label or meaning.
- Similarity finds nearby alternatives but does not establish statistical
  equivalence. Safe selection requires visible material differences and a clear
  statement when no difference is evidenced.
- Successful loading is not the same as efficient loading. In the audited r4
  bundle, search-result JSON was about 74.4 MB pretty-printed; compact
  alternative previews contributed about 15.3 MB, or 29.2% of the compact
  search documents. Dataset shards were about 119 MB and resource shards about
  18 MB before parsing.

These measurements are an audited campaign checkpoint, not permanent bundle
size promises.

The final r6 campaign checkpoint contains 44,863 present raw evidence slots out
of 71,358 (62.8703%), up from 33,090 (46.3718%). Its applicability-aware view
contains the same 44,863 present slots out of 65,288 applicable slots
(68.7155%), with 6,070 Open Geography population/time-coverage slots explicitly
not applicable and 20,425 applicable slots not evidenced. Explorer must keep
both measures and their denominators visible; it must not treat the 6,070 state
changes as acquired metadata.

## Required Explorer changes

### P0: register OKF-ONS with a versioned mixed-rights contract

Add OKF-ONS to
[`registry/okf-registry.yamlld`](https://github.com/chris-page-gov/okf-explorer/blob/main/registry/okf-registry.yamlld)
and regenerate the root/static JSON and JSON-LD projections with
[`scripts/build_okf_registry.py`](https://github.com/chris-page-gov/okf-explorer/blob/main/scripts/build_okf_registry.py).
Update the semantic registry test, which currently assumes four bundles, and
surface the canonical URLs in the Explorer README.

The bundle descriptor declares mixed record-level rights, but the semantic
catalogue and local context do not currently expose a root rights term. The
bundle-wiki registry profile also requires a single bundle-level licence.
Coordinate a versioned registry/profile/context contract for mixed rights
before registration; do not label the entire bundle OGL merely to satisfy
registry validation.

Primary targets:

- `registry/okf-registry.yamlld`
- `profiles/bundle-wiki/v1/bundle.schema.json`
- `profiles/bundle-wiki/v1/context.jsonld` or a new versioned profile/context
- `scripts/build_okf_registry.py`
- `tests/test_okf_semantic.py`
- `README.md`

### P0: represent applicability-aware evidence states

Explorer's viewer helper and missing-value facets currently collapse absence,
empty values and sentinels into the same label. Support:

- `present`
- `not-evidenced`
- `not-applicable`
- `conflicted`
- legacy unknown, rendered as `Not specified (metadata gap)`

`not-applicable` must not count as a gap or enter the generic missing facet.
Metadata-quality sorting should use an applicability-aware numerator and
denominator when supplied, while preserving the existing raw `quality.overall`
and adding separately named applicability-aware numerator, denominator and
score fields.

This is a joint contract change: Explorer cannot render authoritative states
until OKF-ONS publishes the versioned record-level `field_states` evidence.

A versioned record-level shape should be supported, for example:

```json
{
  "field_states": {
    "time_coverage": {
      "status": "not-applicable",
      "rule_id": "geospatial-reference-has-no-statistical-time-coverage",
      "rationale": "Reference geography resource, not a statistical time series"
    }
  }
}
```

Primary targets:

- `apps/okf-explorer/src/lib/viewer/helpers.ts`
- `apps/okf-explorer/src/lib/viewer/helpers.test.ts`
- `apps/okf-explorer/src/routes/+page.svelte`
- `apps/okf-explorer/src/lib/types.ts`

### P0: resolve the advertised analysis-contract mismatch

OKF-ONS currently labels its overview `okf-explorer-analysis.v1`, but it does
not contain the generic summary, facet, graph, resource and timeline structures
that Explorer's type expects. Explorer TypeScript-casts the response and catches
the resulting failure, which can trigger avoidable full hydration. Treat this
as release-blocking contract work, not a presentation enhancement.

Choose one explicit contract:

1. OKF-ONS emits and validates the full generic Explorer overview; or
2. OKF-ONS publishes a distinct source-specific schema and Explorer validates
   it, reports unsupported analysis clearly, and retains bounded fallback
   behaviour.

### P1: make alternatives a first-class comparison workflow

OKF-ONS has alternatives for most records, but Explorer currently exposes only
raw arrays and a generic context note. Add `Compare alternatives` to search
cards and dataset details with:

- candidate title, source and type;
- discovery similarity labelled as not statistical equivalence;
- evidence-backed material differences;
- `not_enough_evidence` rendered as `No material difference evidenced`, never
  as a claim that records are the same; and
- pin/link actions for side-by-side comparison.

Add typed alternative structures in `apps/okf-explorer/src/lib/types.ts` and UI
coverage around the search-card and dataset-detail sections of
`apps/okf-explorer/src/routes/+page.svelte`.

### P1: expose selection vocabularies without bloating search

Support an optional integrity-bound selection-options entrypoint. Search and
detail records should carry concept, codelist ID, evidence status, option count
and a compact preview or extent; exact code-label options should load on demand
under a byte budget. Render FREQ as statistical/reference-frequency choices and
TIME as available-period choices—never as update cadence, publication timeline
or dataset revision status. Show upstream `not-evidenced` outcomes explicitly.

### P1: present structure, quality and provenance

Add a `Data structure, quality and provenance` disclosure to dataset detail and
a compact search summary for:

- `geography_reference_date`
- `source_version_label`
- `revision_history_notes`
- `dimensions`
- `quality_notes`
- `methodology_links`
- field-level `metadata_derivation`

For Nomis, render the full FREQ option set and the strict TIME available-period
extent as structured evidence. A multi-option FREQ codelist remains useful even
when the singular `frequency` field is correctly left as a gap. Never present
FREQ as publication/update cadence, TIME extent as a release timeline, or a
TIME-period revision annotation as dataset revision status.

The r6 cohort demonstrates the distinction: 1,530 records have one safe FREQ
option and populate singular `frequency`; 87 retain multiple options without
choosing one. TIME coverage is derived for 1,583 records, while 34 exact
upstream outcomes remain explicitly `not-evidenced`.

Render derivation badges such as `source-declared`, `deterministically
extracted`, `normalised/crosswalked` and `inferred`, with expandable source
field, rule and classifier details.

Presentation must retain these safeguards:

- geography reference/effective dates do not enter the statistical Timeline;
- source version labels and revision-history prose do not establish revision
  status;
- source quality evidence is distinct from metadata completeness;
- dimensions describe selection structure, not observations, and may be
  incomplete.

### P1: make search and hydration byte-bounded

The current worker limits chunks rather than cumulative bytes, and exact-record
actions can hydrate all dataset, resource, publisher and facet shards. Introduce:

- retain the existing `alternative_count`, replace embedded full
  `alternatives` arrays with one to three compact previews;
- a normalised, on-demand alternative-comparison index;
- byte count and SHA-256 in emitted shard metadata, using Explorer's existing
  optional integrity types, and budget enforcement before fetching;
- an aggregate search byte budget;
- exact-record and per-dataset-resource entrypoints; and
- an honestly labelled full-corpus fallback with estimated transfer size.

Primary targets:

- `apps/okf-explorer/src/lib/search/largeSearchContract.ts`
- `apps/okf-explorer/src/workers/largeSearch.worker.ts`
- `apps/okf-explorer/src/lib/sources/largeCorpus.ts`
- `apps/okf-explorer/src/lib/sources/fetch.ts`
- `apps/okf-explorer/src/lib/types.ts`

## OKF-ONS data-side follow-ups

- Publish record-level evidence states and applicability rules in a versioned
  bundle structure; the campaign profiler currently holds this knowledge
  outside the public records.
- Completed in OKF-ONS: resource documents now carry `host` from the already
  public record URL with `public-url-host-v1` field derivation, so Explorer can
  stop showing `unknown host` when it consumes that field.
- Keep the raw fixed evidence score alongside any applicability-aware score.
- Move full alternative evidence to an on-demand index when Explorer supports
  it; retain bounded previews in search documents.
- Resolve the analysis schema choice above before claiming generic analysis
  compatibility.

## Documentation and test work in Explorer

Update:

- `docs/okf-bundle-authoring.md` for evidence states, field provenance, mixed
  rights, date/version semantics and byte-aware entrypoints;
- `docs/static-search-filtering-manual.md` for missing versus not applicable or
  conflicted evidence;
- `docs/explorer-overview-context.md` for validated overview contracts;
- `docs/search-filtering-design.md` for evidence-state and byte-budget design;
- `docs/okf-explorer-persona-manual.md` for comparison workflows;
- `docs/ai-okf-usage.md` for evidence-state handling and bounded hydration; and
- add `docs/metadata-evidence-semantics.md` as a generalised case study.

Test:

- all evidence states plus the legacy missing fallback;
- applicability-aware facets and sorting;
- alternatives and the `not_enough_evidence` wording;
- aggregate search-byte budgeting;
- exact-record loading and the full-corpus fallback;
- mixed record-level rights in the registry;
- a small OKF-ONS-like large-corpus integration fixture, including the existing
  resource-host rendering;
- selection-option previews and on-demand option shards;
- invalid analysis-schema rejection; and
- cumulative, rather than per-chunk, byte limits.

## Agent directions for both repositories

- Preserve `present`, `not-evidenced`, `not-applicable` and `conflicted` as
  distinct states. Never improve completeness by inventing a value or filling
  an inapplicable field.
- Treat `Not specified (metadata gap)` as a legacy fallback, not a universal
  model of absence.
- Report raw and applicability-aware coverage separately with their numerators
  and denominators.
- Preserve field-level provenance and derivation mode.
- Keep catalogue, release, reference, coverage, created and modified dates
  semantically distinct.
- Similarity supports discovery, not equivalence. Alternatives must expose
  material differences and evidence limitations.
- Search previews must be byte-bounded, and exact-record actions must not
  silently hydrate the whole corpus.
- Preserve mixed record-level rights and coordinate the registry, profile,
  context and semantic catalogue contract; never invent a bundle-wide licence.
- Preserve structured option-set evidence even when it cannot safely populate
  a singular display field. Do not collapse FREQ choices or conflate available
  TIME periods with release cadence or dataset revision state.
- Do not claim schema compatibility or bounded transfer unless the published
  contract and tests demonstrate it.

## Delivery boundary

This document is the reviewed handoff from OKF-ONS. No OKF Explorer files were
changed during the campaign. Implement the P0 items first, then alternatives
and byte-bounded hydration together so the UI does not create a second large
payload path. The exact campaign outcome and return-knee decision are preserved
in the OKF-ONS
[`stopping audit`](../evaluation/metadata-completeness/stopping-audit.json).

Register only a deployed immutable OKF-ONS version. The live Pages and Explorer
URLs currently serve v0.2.0; the checked-in campaign successor remains an
undeployed release candidate until the governed release and Pages snapshot are
deliberately switched.
