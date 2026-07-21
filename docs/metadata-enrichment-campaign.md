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

Each machine profile also contains `halfRemaining*` fields calculated from that
profile's own point-in-time gap count. Those are local diagnostics, not the
campaign target. Progress in this report always uses the baseline profile's
fixed 52,224-cell target.

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

The applicability-aware companion measure uses four states: `present`,
`not-applicable`, `not-evidenced`, and `conflicted`. Its two deliberately
narrow rules exclude statistical population/universe and statistical time
coverage for the 3,035 Open Geography reference assets. Their geography
reference or effective dates are not observation coverage. It does not assume
that missing cadence, methodology or contact evidence is inapplicable. After
Batch 09 this measure is 44,863 of 65,288 applicable slots (68.7155%); 6,070
raw slots are not applicable, 20,425 are not evidenced, and none are recorded
as conflicted.

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
| 02 | Frozen Open Geography metadata normalised | 7 min 51 sec | 835 | 52.6150% | 6,382 slots/hour |
| 03 | Live ONS catalogue, then frozen | 9 min 30 sec | 624 | 53.4894% | 3,941 slots/hour |
| 04 | Frozen Explore Local Statistics caveats normalised | 14 min 18 sec | 135 | 53.6786% | 566 slots/hour |
| 05 | Frozen Open Geography utility evidence surfaced | 40 min 37 sec | 325 | 54.1341% | 480 slots/hour |
| 06 | Live Nomis compact overviews, then frozen | 11 min 11 sec | 1,849 | 56.7252% | 9,920 slots/hour |
| 07 | Frozen Nomis quality notes normalised | 15 min 56 sec | 653 | 57.6403% | 2,459 slots/hour |
| 08 | Live ONS latest-version dimensions, then frozen | 31 min 58 sec | 619 | 58.5078% | 1,162 slots/hour |
| 09 | Live Nomis FREQ/TIME codelists, then frozen | 47 min 08 sec | 3,113 | 62.8703% | 3,963 slots/hour |

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

Batch 02 added geography evidence (+524), explicit product cadence (+310), and
one source snippet used as a description fallback. It also mapped declared
public access, source creation date, product type, controlled area keywords and
single-year title vintages with field-level derivation. This removed 17,902
dataset-detail gap cells, 6,069 search-facet gap cells and 3,035 search-result
gap cells. Cumulative raw evidence progress is 4,455 slots: 11.6416% of the
original gaps and 23.2832% of the halfway milestone. Marginal yield remains
well above the stopping threshold.

Batch 03 made one metadata-only request to the official ONS Data API. The
request completed in 5.9 seconds and returned the same 337 record identities as
the r2 snapshot. It supplied a public contact for all 337 records and an
explicit `is_based_on` population-type link for 287. The acquisition was frozen
as immutable snapshot `metadata-enrichment-2026-07-21-r3`; the other three
source envelopes are byte-identical to r2 and the new manifest records the r2
manifest digest without a filesystem path. No observations, geometry,
credentials or cache paths are present in the projected snapshot.

Batch 03 added 298 dataset-detail type cells and 910 search-facet cells in
addition to its 624 evidence slots. Cumulative raw progress is 5,079 cells:
13.2722% of the original gaps and 26.5444% of the halfway milestone. Yield is
declining across batches but remains more than eleven times the continuation
threshold.

Batch 04 used only the already frozen Explore Local Statistics projection. It
treated 102 source-declared caveat collections as quality or limitation
documentation and extracted explicitly labelled methodology links for 33
records. It did not infer licence, contact, population or revision evidence.
The same explicit projection supplied 108 record types, 108 country-code
crosswalks and 108 public resource hosts to dataset details, plus 108 endpoint
hosts and 108 documentation hosts to search results. This removed 324 dataset
display gaps and 216 search-result gaps without synthesising resources.

Its 566-slot/hour marginal yield is still above the 357-slot/hour stopping
threshold, but only by 1.59 times; this is the first batch close to the return
knee. The 14 minute 18 second wall time includes the concurrent design and
validation of the next bounded Nomis acquisition, so it is conservative as an
ELS-only productivity measure. Cumulative raw progress is now 5,214 cells:
13.6250% of the original gaps and 27.2499% of the halfway milestone.

Batch 05 re-examined the already frozen Open Geography descriptions and links.
It accepted only explicit methodology language (+168), explicit quality or
limitations text (+139), and an exact `every 12 weeks` cadence (+18). It also
surfaced useful fields that are deliberately outside the fixed evidence KPI:
informative category facets, exact endpoint and documentation hosts, source
version labels, revision-history notes and 2,462 geography reference dates.
The latter are reference or effective dates for geography products, not
statistical time coverage; a title such as `(V2)` is likewise not evidence of
revision status.

This removed 5,328 dataset-detail gaps, 17,704 resource-detail gaps, 6,070
search-result gaps and 2,356 search-facet gaps. The 40 minute 37 second elapsed
time is conservative shared wall time from the Batch 04 checkpoint through
integration: the hardened Nomis acquisition capability was developed in
parallel, while only Open Geography's 325 evidence cells are counted in this
batch's numerator. Even on that basis the 480-slot/hour yield remains above the
continuation threshold. Cumulative raw progress is 5,539 cells: 14.4742% of
the original gaps and 28.9485% of the fixed halfway milestone.

Batch 06 made a bounded metadata-only request for each record in the frozen
1,617-record Nomis cohort. The successful acquisition took 8 minutes 42
seconds; the reported 11 minute 11 second end-to-end wall time also includes a
restricted-network retry, immutable composition, bundle compilation and
profiling. One hundred responses were already in the external cache. The
completed run made 1,517 live requests sequentially with a minimum 0.2-second
interval. It requested only `DatasetInfo`, `Coverage`, `DateMetadata` and
`Contact`; no observations or codelists were fetched, and neither raw responses
nor the cache location are present in r4.

Every Nomis record now has a source-declared public contact and compact coverage
metadata. This adds contact evidence for 1,617 records and geography evidence
for the 232 records that did not already have it through their frozen
annotations. The source also supplied 97 `lastRevised` dates and three
`nextUpdate` dates. They are preserved for display and provenance but do not
claim that a dataset has a particular revision status. The resulting immutable
snapshot is `metadata-enrichment-2026-07-21-r4`; its ONS Data API, Explore Local
Statistics and Open Geography source files are byte-identical to r3.

The batch also removed 1,617 dataset-detail gaps and 111 search-facet gaps. Its
9,920-slot/hour marginal yield is well above the continuation threshold.
Cumulative raw progress is now 7,388 cells: 19.3059% of the original gaps and
38.6119% of the fixed halfway milestone. Reaching the milestone would still
require 11,746 additional source-backed evidence cells; the next-source audit
therefore tests availability rather than projecting Batch 06's exceptional
contact yield across unrelated fields.

Batch 07 revisited the frozen Nomis annotations after the full-cohort audit. It
found 653 records with substantive source notes explicitly labelled or worded
as statistical disclosure control, uncertainty, data quality or limitations.
The earlier extractor retained only linked quality documents and required a
numeric `MetadataTextN` suffix, so it missed both unlinked evidence and the
valid unsuffixed `MetadataText` form. The revised extractor requires a paired
quality title or an explicit quality signal in a substantive note; general
dataset descriptions and unlabelled URLs still do not qualify.

The 15 minute 56 second elapsed time is conservative shared wall time from the
r4 checkpoint through the remaining-gap audits and implementation; the ONS
version-resource acquisition was designed in parallel. Batch 07 adds 653
quality-documentation evidence cells at 2,459 slots/hour. Cumulative raw
progress is 8,041 cells: 21.0123% of the original gaps and 42.0247% of the fixed
halfway milestone. Another 11,093 source-backed cells would be needed to reach
that milestone.

Batch 08 followed the exact `links.latest_version.href` frozen for every one of
the 337 ONS Data API records. A 20-record pilot failed closed on genuine API
shape variants before the contract was corrected: the top-level version ID is
opaque rather than the dataset ID, typed link objects may be empty or absent,
and dimension labels may be absent. Identity remains bound to the exact request
URL plus dataset, edition and self links; missing labels remain missing. The
full run was sequential at a 0.5-second interval and cached only the projected
dimension identities, explicit `isAreaType` flag, and quality statements.
Options, codelists, observations, downloads, raw responses and cache paths are
not present in the snapshot.

All 337 records supplied explicit geography evidence and 282 supplied a
dimension quality statement. The 31 minute 58 second conservative wall time
runs from the Batch 07 checkpoint through design, pilots, fail-closed schema
learning, full acquisition, immutable composition, bundle compilation and
profiling. The resulting r5 snapshot carries the other three source envelopes
byte-identically from r4. Its 1,162-slot/hour yield remains above the numerical
continuation threshold.

Cumulative Batches 01–08 took 2 hours 16 minutes 34 seconds and added 8,660
source-backed evidence cells. That closes 22.6299% of the original gaps and
45.2597% of the fixed halfway milestone. Raw completeness is 41,750 of 71,358
(58.5078%), leaving 29,608 raw gaps and 10,474 cells still needed for the fixed
halfway target. Including the 14-minute baseline inventory, measured campaign
work was 2 hours 30 minutes 34 seconds.

Batch 09 reopened the stopping audit after it identified one unmeasured bounded
route in the frozen Nomis definitions: every one of the 1,617 records has an
exact FREQ and TIME codelist reference. A deterministic 54-record semantics
pilot covered the source families, followed by a 20-record pilot of the exact
direct endpoint and replacement composer. The production acquisition then
followed all 3,234 exact metadata-only endpoints sequentially and retained an
explicit outcome for every reference. It found 34 TIME codelists that were null
or remained unavailable after retries; those are frozen as receipt-bound `not-evidenced`
outcomes rather than removed from the denominator.

The full cohort added 1,530 unambiguous singular frequency values and 1,583
strict time extents. Multiple FREQ options remain structured evidence and are
not collapsed. TIME extents require unique homogeneous `YYYY` or `YYYY-MM`
codes and exclude explicitly unavailable or prerelease periods. Optional
release annotations, per-period revision status and malformed unused timestamp
text do not become publication cadence or dataset revision status.

The 47 minute 08 second measured wall interval includes route reopening,
contract and edge-shape tests, resumable full acquisition, immutable r6
composition, bundle compilation and profiling. Its 3,963-slot/hour yield is
well above the continuation threshold. Raw completeness is now 44,863 of
71,358 (62.8703%), leaving 26,495 raw gaps. Applicability-aware completeness is
44,863 of 65,288 (68.7155%), leaving 20,425 applicable gaps.

Cumulative Batches 01–09 took 3 hours 03 minutes 42 seconds and added 11,773
source-backed evidence cells. That closes 30.7646% of the original gaps and
61.5292% of the fixed halfway milestone. Another 7,361 cells would be needed to
reach the fixed 52,224-present target. Including the 14-minute baseline
inventory, summed measured campaign work is 3 hours 17 minutes 42 seconds; this
is a sum of recorded batch intervals, not an end-to-end calendar duration.

## Stopping decision

The campaign stops after Batch 09 under the stopping rule's evidence-availability
and marginal-return clauses, not because Batch 09 itself was slow. Its exact
Nomis cohort is exhausted. The 20,425 remaining applicable gaps comprise 5,097
revision-status gaps for which narrower date/version proxies were rejected, 371
time-coverage gaps (34 explicit Nomis upstream failures and 337 ONS records),
and 14,957 other cells for which the audited bounded sources do not expose
qualifying record-level evidence.

The only remaining deterministic source/endpoint pair with a credible generic
field mapping was piloted before stopping. Fifty ONS records have an exact
`time` dimension-options endpoint. An eight-family edge pilot made 8 requests,
validated 640 option items without an identity or schema failure, and found a
46-cell parser-safe family ceiling. The absolute 50-cell ceiling is only
0.0701 raw percentage points. At 357 cells/hour, a governed full acquisition,
composer, model, tests, profile and documentation would need to ship in under 8
minutes 24 seconds (7 minutes 44 seconds at the conservative 46-cell ceiling),
which is not credible. That route is therefore `measured-rejected`, not
unpiloted. Other next routes require expanded source contracts, unbounded
document crawling or unsupported record-by-record judgement.

The fixed halfway milestone was not reached. Reusing Batch 09's marginal rate
would imply about 1.86 hours for the remaining 7,361 cells, but that is not a
defensible ETA because its finite route is exhausted and the next bounded route
falls below threshold. The return knee first appeared in Batches 04–05, was
temporarily lifted by four finite high-yield lanes, and is now reached after the
last credible bounded route was measured. The machine-readable
[`stopping audit`](../evaluation/metadata-completeness/stopping-audit.json)
preserves the remaining-gap matrix, route inventory and decision basis.

The machine-readable baseline is
[`evaluation/metadata-completeness/baseline.json`](../evaluation/metadata-completeness/baseline.json).
Batch 01 has a
[`profile`](../evaluation/metadata-completeness/batch-01-frozen-nomis.json) and
[`comparison`](../evaluation/metadata-completeness/batch-01-comparison.json).
Batch 02 likewise has a
[`profile`](../evaluation/metadata-completeness/batch-02-frozen-open-geography.json)
and
[`comparison`](../evaluation/metadata-completeness/batch-02-comparison.json).
Batch 03 has a
[`profile`](../evaluation/metadata-completeness/batch-03-live-ons-catalogue.json)
and
[`comparison`](../evaluation/metadata-completeness/batch-03-comparison.json).
Batch 04 has a
[`profile`](../evaluation/metadata-completeness/batch-04-frozen-els.json) and
[`comparison`](../evaluation/metadata-completeness/batch-04-comparison.json).
Batch 05 has a
[`profile`](../evaluation/metadata-completeness/batch-05-frozen-ogp-utility.json)
and
[`comparison`](../evaluation/metadata-completeness/batch-05-comparison.json).
Batch 06 has a
[`profile`](../evaluation/metadata-completeness/batch-06-live-nomis-overviews.json)
and
[`comparison`](../evaluation/metadata-completeness/batch-06-comparison.json).
Batch 07 has a
[`profile`](../evaluation/metadata-completeness/batch-07-frozen-nomis-quality-notes.json)
and
[`comparison`](../evaluation/metadata-completeness/batch-07-comparison.json).
Batch 08 has a
[`profile`](../evaluation/metadata-completeness/batch-08-live-ons-version-metadata.json)
and
[`comparison`](../evaluation/metadata-completeness/batch-08-comparison.json).
Batch 09 has a
[`profile`](../evaluation/metadata-completeness/batch-09-live-nomis-codelists.json)
and
[`comparison`](../evaluation/metadata-completeness/batch-09-comparison.json).
Regenerate and compare profiles with:

```bash
python scripts/build_bundle.py \
  --snapshot-dir source/metadata-enrichment-2026-07-21-r6 \
  --output bundle
python scripts/profile_metadata_gaps.py \
  --bundle bundle \
  --output /tmp/okf-ons-r6-profile.json
cmp /tmp/okf-ons-r6-profile.json \
  evaluation/metadata-completeness/batch-09-live-nomis-codelists.json
python scripts/compare_metadata_gaps.py \
  evaluation/metadata-completeness/batch-08-live-ons-version-metadata.json \
  /tmp/okf-ons-r6-profile.json \
  --started-at 2026-07-21T14:06:05Z \
  --completed-at 2026-07-21T14:53:13Z \
  --clock-basis "UTC wall clock; route reopening through full acquisition, r6 composition, bundle compilation and profile" \
  --output /tmp/okf-ons-batch-09-comparison.json
cmp /tmp/okf-ons-batch-09-comparison.json \
  evaluation/metadata-completeness/batch-09-comparison.json
```
