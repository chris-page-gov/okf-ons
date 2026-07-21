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
