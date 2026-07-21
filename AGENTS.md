# OKF ONS Repository Guide

## Purpose

This repository publishes a metadata-only Open Knowledge Format bundle for
discovering Office for National Statistics data. It must support both people
and agents in finding the exact dataset, understanding nearby alternatives,
and producing a structurally valid MCP selection plan.

## Non-negotiable contracts

- Never store observation values, secrets, credentials, or machine-specific
  cache paths in the public bundle.
- Never claim complete ONS coverage without a source-by-source coverage ledger
  whose unexplained omission count is zero.
- Preserve source identifiers, dataset editions, versions, release dates,
  geography vintages, derivation modes, and provenance.
- Treat metadata completeness as evidence availability, not as proof that
  statistics are accurate or methodologically sound.
- Similar datasets must expose evidence-backed differences before selection.
- Standards claims must be one of `aligned`, `partial`, `not-evaluated`, or
  `not-applicable`; do not imply certification.

## Source and build boundaries

- Raw and frozen acquisitions belong in an external cache selected with
  `--cache-dir`. EXTSSD is an acquisition cache, not a publication source of
  truth.
- Checked-in source material is limited to source registers, frozen manifests,
  reconciliation evidence, evaluation fixtures, and bounded projected
  metadata snapshots. Raw live responses and resumable caches remain external;
  a validated, allowlisted projected envelope may be frozen when it is bound to
  exact source and base-snapshot digests.
- Generated public output lives under `bundle/`.
- Make generation deterministic from a frozen snapshot. Live acquisition and
  bundle compilation are separate commands.

## Metadata-enrichment campaigns

- Treat `Not specified (metadata gap)` as a diagnostic about a particular
  view, not an instruction to invent a value. Profile the fixed evidence slots,
  dataset details, resources, search results, publishers and facets separately.
- Establish a fixed baseline denominator and target before changing adapters.
  Keep point-in-time “half remaining” diagnostics distinct from that campaign
  target.
- Work in source-specific timed batches. Record elapsed seconds, exact cells
  added, percentage-point change, Explorer-surface changes and remaining gaps
  in machine-readable profiles and comparisons.
- Record UTC `startedAt` and `completedAt` values and the clock basis as well as
  elapsed seconds. A caller-supplied duration without its endpoints is not
  independently auditable; describe sums of batch timers separately from total
  campaign wall time.
- Use an explicit continuation threshold. The current campaign continues at
  0.5 percentage points per engineering hour (357 fixed evidence cells/hour),
  or for a reusable capability expected to exceed that rate in the next batch.
  Stop when evidence is unavailable, semantically inapplicable, or would need
  unsupported record-by-record judgement.
- A plausible API route is an opportunity ceiling, not evidence and not an
  ETA. Pilot edge families, measure the exact full cohort, and never extrapolate
  a high-yield contact batch across unrelated fields.
- Before declaring a stopping point, maintain a machine-readable inventory of
  every known bounded source route and its measured, rejected or exhausted
  status. Do not claim zero immediate bounded gain while a deterministic
  cohort/endpoint pair remains unpiloted.
- When applicability rules change, comparisons must report both the old and
  new denominators and the denominator change. Never present a rule change as
  newly acquired evidence.

## Enrichment semantics

- Count only explicit source evidence. Preserve useful narrower concepts in
  their own fields instead of coercing them into a completeness metric.
- A geography reference/effective date is not statistical `time_coverage`.
- A source version label or revision-history note is not `revision_status`.
  Likewise, a `lastRevised` date says when, not what revision status applies.
- A dimension named `time` does not state the covered period, and a unit
  dimension does not state which unit values occur.
- A Nomis TIME codelist can evidence the available-period extent only when its
  exact selectable codes form one homogeneous, validated period shape. Compute
  chronological bounds from parsed codes, not response order; an individual
  period's revision status is not dataset revision status.
- Nomis FREQ codes are statistical/reference-frequency options, not
  publication or update cadence. Populate a singular frequency only for one
  unambiguous code-label pair; preserve multiple options without choosing the
  first, finest or most convenient value.
- For ONS version metadata, geography requires `is_area_type: true` or an exact
  geography dimension name or label. Dimension-level `quality_statement_*` is
  quality evidence, not methodology evidence.
- Keep `present`, `not-applicable`, `not-evidenced`, and `conflicted` distinct.
  Only remove a field from the applicability denominator when the record class
  makes the concept itself inapplicable.

## Bounded replacement acquisitions

- Derive the cohort independently from a validated frozen source envelope.
  Validate the base manifest, file hashes, envelope hashes, source identity and
  exact metadata-only endpoint before making requests.
- Use deterministic selection, exact top-level and deep allowlists, bounded
  scalar lengths, public-URL checks, secret/path scans, safe response-header
  allowlists, sequential rate limiting and `Retry-After` handling.
- Cache all response material externally; prefer a deeply allowlisted projected
  cache when raw responses are unnecessary. A checked-in replacement must
  contain the full original cohort, change only declared metadata fields, bind
  itself to the base digests, and publish explicit
  no-observation/no-raw-response assurance.
- Version and namespace every projected-cache schema. When an allowlist,
  projection or interpretation changes, bump the schema and ignore incompatible
  entries; never reinterpret an old cache under new semantics.
- A deterministic pilot can establish the contract, but a completed cohort run
  must retain an explicit outcome for every selected record and reference.
  Preserve exhausted failures as `not-evidenced` with exact identity, attempts,
  HTTP status and reason; never drop failures or shrink the denominator.
- Compose to a new immutable snapshot ID. Confirm unrelated source envelopes
  are byte-identical. Do not chain replacement-enriched acquisitions unless a
  source-specific validator explicitly supports and tests that lineage.
- A version number, codelist reference, URL label or other proxy must not be
  promoted merely to improve the score.
- Pilot the real endpoint before the full cohort and encode observed optionality
  in fixtures. For the ONS version endpoint, the top-level `id` is an opaque
  resource identity; bind the dataset through the exact frozen URL and its
  dataset, edition and self links. Typed link objects can be empty or absent,
  and dimension labels can be absent. Do not manufacture those missing values.
- Do not relax a validator merely because a live shape differs. Inspect the
  smallest failing allowlisted projection, establish the upstream semantics,
  retain exact identity and safety checks, then add a regression test before
  resuming from the external cache.
- Optional upstream fields that do not support published semantics should be
  bounded and ignored, not promoted or used to loosen validation.
- Structured option evidence remains useful when a generic singular field is
  unresolved. Preserve its vocabulary and provenance rather than replacing it
  with a gap label.

## Explorer compatibility

- Preserve applicability states and the raw evidence denominator in public
  contracts. `Not specified (metadata gap)` is a legacy fallback, not the only
  representation of absence.
- Similarity supports discovery, not statistical equivalence. Alternatives
  must expose material differences and the absence of sufficient evidence.
- Keep search previews and hydration byte-bounded. An exact-record action must
  not silently require every corpus shard.
- Preserve mixed record-level rights; never invent a bundle-wide licence for a
  registry or UI constraint.
- Derived display fields such as a resource host must retain a field-level rule
  and source-field declaration; a useful UI fix is still evidence-bearing data.
- Do not claim generic analysis-schema compatibility, bounded transfer or
  first-class presentation until the Explorer contract and tests demonstrate
  it. Track required Explorer work in
  `docs/okf-explorer-metadata-campaign-handoff.md`.

## Validation

Run before publishing:

```bash
python -m pytest -q
python -m ruff check .
python scripts/build_bundle.py --snapshot-dir source/demo-snapshot --output bundle
python scripts/build_bundle.py \
  --snapshot-dir source/demo-snapshot \
  --output bundle \
  --check
node --check pages/app.js
```

Run this matrix against both the stable demo snapshot and the exact
release-candidate snapshot. The Pages-selected snapshot must match governed
release metadata. The Pages workflow must validate before uploading `bundle/`.
