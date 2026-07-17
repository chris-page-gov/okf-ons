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
