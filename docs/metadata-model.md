# Metadata model

## Stable identity

Identifiers are source-qualified and never inferred from display titles:

- `ons-data-api:dataset:{dataset}`
- `ons-data-api:edition:{dataset}:{edition}`
- `ons-data-api:version:{dataset}:{edition}:{version}`
- `ons-data-api:dimension:{dataset}:{edition}:{version}:{dimension}`
- `ons-data-api:option:{dataset}:{edition}:{version}:{dimension}:{option}`
- `nomis:dataset:{native-id}`
- `ons-open-geography:dataset:{item-id}`
- `ons-explore-local-statistics:indicator:{indicator-slug}`

Cross-source equivalence is represented by a relationship with evidence; it
does not replace native identity.

## Record layers

- **Discovery record:** compact title, description, topic, source, state,
  coverage, update and quality-evidence summary.
- **Version record:** edition/version, release and revision metadata,
  dimensions, methodology and selection constraints.
- **Code-list record:** reusable option vocabulary with native codes and
  hierarchy.
- **Distribution record:** API endpoint, download or service metadata.
- **Evidence record:** methodology, QMI, publication, standards mapping or
  provenance activity.

Observation combinations are never materialised.

## Evidence states and semantic boundaries

Metadata completeness measures the availability of evidence, not statistical
accuracy. The applicability-aware companion distinguishes `present`,
`not-applicable`, `not-evidenced` and `conflicted`; uncertainty stays
`not-evidenced` unless the record class makes a concept inapplicable.

Narrow source concepts remain narrow. Geography reference/effective dates are
not statistical time coverage. Version labels, revision-history notes and
`lastRevised` dates are not revision status. A time dimension does not state a
covered period, and a unit dimension does not identify the unit values present
in a dataset.

## Bounded ONS version dimensions

The ONS catalogue record supplies the exact latest-version URL. A bounded
enrichment may follow that URL once per frozen record and project only
`versionDimensions`: dimension `id`, `name`, optional `label`, explicit `isAreaType`,
and explicit `qualityStatementUrl` or `qualityStatementText`. Dimension options,
codelists, observations, downloads and unknown response fields are excluded.

Geography evidence requires `isAreaType: true` or an exact dimension name or
label of `geography`; subject dimensions such as “Country of birth” do not
qualify. Dimension quality statements remain associated with their dimension
and supply quality evidence only. They do not imply methodology, time coverage
or revision status.

## Bounded Nomis overviews and notes

Nomis compact overviews contribute only public contact, declared coverage and
date metadata to the frozen dataset-definition cohort. The date fields are
preserved without manufacturing revision status. Frozen `MetadataText` and
`MetadataTextN` annotations contribute quality notes only when the note itself
has an explicit quality, uncertainty, limitations or disclosure-control signal,
or when its paired `MetadataTitle` explicitly supplies that context.

## Bounded Nomis frequency and time codelists

The exact frozen Nomis dataset-definition envelope supplies each dataset
identity and its native `FREQ` and `TIME` codelist references. A bounded
replacement follows only the corresponding metadata-only endpoint,
`/api/v01/codelist/{codelistId}.def.sdmx.json`, and projects code values, labels
and explicit TIME-period revision-status annotations. Raw SDMX responses remain
external and are discarded after validation; the projected cache and frozen
replacement are content hashed, bound to the base digests and prohibited from
containing observations.

`FREQ` values describe statistical or reference-frequency options. They do not
describe publication or update cadence. All explicit options remain available
in `nomis_codelist_metadata`; the singular `frequency` field is populated only
when there is one unambiguous, non-placeholder code-label option. Multiple
options remain unresolved rather than being ordered or collapsed.

`TIME` values can evidence available-period extent only when all eligible,
unique codes have one strict shape: either `YYYY` or `YYYY-MM` with a valid
month. Explicit pre-release, future, unavailable or unreleased periods are
excluded. Bounds are computed chronologically from the parsed codes, never from
response order. A period's revision-status annotation remains period-level
filtering evidence and never populates dataset `revision_status`.

Each projected codelist is explicitly `present` or `not-evidenced`. An audited
upstream null or failed response is preserved with an empty code list and the
reason `upstream-codelist-unavailable`; opaque, mixed or duplicate TIME shapes
likewise leave `time_coverage` empty. No fallback value is manufactured to
improve completeness.

## Required provenance

Every harvested record carries source URL, native identifier, retrieval time,
snapshot identifier, source adapter, upstream modified/release date where
available, content hash and licence evidence. Local cache paths are prohibited
from public output.

## Qualified authority

Source attribution is not bundle endorsement. Each generated record separates:

- `sourcePublisher`: the producer or producers named by the frozen metadata;
- `surfaceOperator`: the organisation operating or curating the discovery
  surface;
- `bundlePublisher`: the independent publisher of this OKF release;
- `semanticAuthority`: authority only for the claims made by this release;
- `reviewedBy`: empty until an evidenced review is recorded; and
- `notEndorsedBySource`: always true for this experimental release.

Operational authority remains with a separate live-data service and decision
authority remains with the accountable person or institution. The generated
qualified-provenance object labels transformed fields as deterministically
normalised and carries source and transformation evidence; it does not turn a
derived assertion into an official source statement.

## Explore Local Statistics indicators

ELS records preserve the public indicator slug, internal dataset family,
indicator code, producer links and dates, ONS operator role, taxonomy, caveats,
measure, unit, frequency, dimensions and geography vintage. Historical slugs
are aliases only when their target remains in the pinned 108-indicator
catalogue. Both the raw historical slug and its source-qualified OKF alias are
indexed for exact lookup, while the canonical record identity remains
source-qualified; broker indexing fails closed if a raw native alias would
shadow another identity or map to more than one record. Fields inferred by the
application from observation structure are explicitly labelled with their
derivation mode. Observation values, statuses, value domains, high-volume
area/time members, binaries and geometry are not projected.
