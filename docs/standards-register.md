# Standards and assurance register

The OKF ONS bundle uses official statistical, analytical, catalogue,
provenance, accessibility and geospatial standards to make source metadata
easier to find, compare and use. The machine-readable register is
[`source/standards-register.json`](../source/standards-register.json); the
field-level semantic mapping is
[`source/ontology-crosswalk.json`](../source/ontology-crosswalk.json).

The register is current to **24 July 2026**. Existing entries retain their own
earlier review dates when they were not re-reviewed. It is an implementation and
evaluation contract, not a certification scheme.

## Assurance boundary

The bundle can establish that:

- a source publishes evidence about a requirement or quality dimension;
- the bundle preserved that evidence and its provenance;
- a generated record satisfies the declared OKF or metadata-profile rules;
- search exposes plausible alternatives and material differences; and
- the frozen metadata build is deterministic and internally consistent.

It cannot establish that an observation is accurate, a producer complies with
legislation or the Code, a methodology was correctly executed, or two series
are statistically comparable. Absence of evidence is `not-evidenced`, never a
finding of non-compliance.

There are consequently two deliberately separate status vocabularies:

| Claim | Allowed statuses | Meaning |
| --- | --- | --- |
| Requirement evidence | `observed`, `inferred`, `not-evidenced`, `not-applicable`, `conflicted`, `stale` | What evidence the harvested official sources support |
| Bundle profile mapping | `aligned`, `partial`, `not-evaluated`, `not-applicable` | How completely the generated OKF record maps to a declared metadata profile |

`aligned` applies only to the bundle mapping. It must never be presented as
accreditation, producer compliance or statistical-quality certification.

## Open Knowledge Format 0.2

The portable knowledge layer conforms structurally to
[OKF 0.2](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/3fcbb9f828c2f23d109c855ee403c3a4c81f3a96/okf/SPEC.md).
The root `index.md` declares the version, every non-reserved Markdown document
has parseable frontmatter and a non-empty `type`, and generated concepts use
the v0.2 `generated` and `sources` families.

The migration keeps `timestamp` and `# Citations` as additive v0.1 fallbacks.
Unknown concept types and fields remain permitted, which is how the Explorer
large-corpus profile, YAML-LD, federation, facets, integrity catalogues and
provider datapacks stay available without becoming core OKF requirements.

No `verified` event or `stale_after` value is emitted without governed
evidence. The generated
[`data/standards/okf-v0.2.json`](../bundle/data/standards/okf-v0.2.json)
report records structural conformance, concept counts, derived trust tiers and
lifecycle counts. It does not certify upstream source statistics.

Every requirement-evidence claim has:

```text
standardUri
requirementId
status
evidenceUrl
evidenceType
retrievedAt
sourceModifiedAt
contentDigest
notes
```

An `inferred` claim identifies the deterministic inference and is visually
distinct from a producer assertion. A `conflicted` claim retains every
material source rather than silently selecting one value. A `stale` claim
retains the earlier evidence and states the freshness rule that failed.

## Current UK requirements and guidance

The authoritative statistical baseline is the
[Statistics and Registration Service Act 2007](https://www.legislation.gov.uk/ukpga/2007/18/contents)
and the UK Statistics Authority's
[Code of Practice for Statistics 3.0](https://code.statisticsauthority.gov.uk/standards-of-the-code-of-practice/standards-for-official-statistics-with-required-practices/).
Code 3.0 was released in October 2025. Legacy Code 2.1 `Q1`, `Q2` and `Q3`
labels must not be used as the current requirement structure.

The current intelligent-transparency baseline is the Code 3.0
[Standards for Public Use](https://code.statisticsauthority.gov.uk/standards-of-the-code-of-practice/standards-for-the-public-use-of-statistics-data-and-wider-analysis-with-required-practices/).
They cover equality of access, supporting understanding, and decision making
and leadership. They replaced OSR's 2022 intelligent-transparency regulatory
guidance in May 2026.

Source-product evidence should preserve:

- statistical status, release calendars, versions, revisions and corrections;
- suitable source data, source changes, methods and validation evidence;
- classifications, definitions, harmonisation and documented deviations;
- coherence and comparability across time, products and geographies;
- uncertainty, error, bias, confidence, representativeness and limitations;
- related or alternative statistics and risks of misinterpretation;
- accessibility, reusable metadata and persistent access; and
- the exact evidence URL, date and source version for each claim.

ONS-specific quality evidence is structured using
[Quality and Methodology Information](https://www.ons.gov.uk/methodology/methodologytopicsandstatisticalconcepts/qualityinofficialstatistics/qualityandmethodologyinformation):
relevance; accuracy; timeliness and punctuality; accessibility and clarity; and
coherence and comparability. The
[ONS revisions guide](https://www.ons.gov.uk/methodology/methodologytopicsandstatisticalconcepts/revisions/guidetostatisticalrevisions)
is used to distinguish a quality-improving revision from a correction of a
mistake.

For products using administrative data, preserve the four evidence areas in
OSR's current
[Administrative Data Quality Assurance Toolkit](https://osr.statisticsauthority.gov.uk/publication/administrative-data-quality-assurance-toolkit/pages/3/):
operational context and collection, communication with supply partners,
suppliers' quality assurance, and the producer's investigations and
documentation. Never infer an A0 to A3 assurance level.

The build and evaluation pipeline follows:

- [GovS 010 Analysis v2.2](https://www.gov.uk/government/publications/government-analysis-functional-standard--2/government-functional-standard-govs-010-analysis),
  retaining its distinction between mandatory `shall` and advisory `should`;
- [The Aqua Book, July 2025](https://www.gov.uk/guidance/the-aqua-book),
  keeping verification separate from validation and assurance proportionate;
- the [Reproducible Analytical Pipelines Strategy](https://analysisfunction.civilservice.gov.uk/policy-store/reproducible-analytical-pipelines-strategy/);
  and
- the [Government Data Quality Framework](https://www.gov.uk/government/publications/the-government-data-quality-framework/the-government-data-quality-framework),
  covering completeness, uniqueness, consistency, timeliness, validity and
  accuracy.

Metadata tests can partly evaluate the first five government data-quality
dimensions. They cannot establish observation accuracy; accuracy remains
`not-evidenced` without independent or producer-supplied evidence.

## Catalogue and semantic model

The canonical catalogue stack is the UK government's
[DCAT 3 recommendation](https://www.gov.uk/government/publications/recommended-open-standards-for-government/using-metadata-to-describe-data-assets-in-a-data-catalogue),
the [UK Cross-Government Metadata Exchange Model](https://co-cddo.github.io/ukgov-metadata-exchange-model/)
and the W3C [DCAT 3 Recommendation](https://www.w3.org/TR/vocab-dcat-3/).
It distinguishes a dataset, dataset series, distribution, data service and
catalogue record and preserves version and qualified relationships.

Other standards have specific roles:

- [SKOS](https://www.w3.org/TR/skos-reference/) represents concepts, labels,
  hierarchies and mapping strength. `exactMatch` requires evidence of semantic
  identity; `closeMatch` is appropriate for close but non-equivalent concepts.
- [PROV-O](https://www.w3.org/TR/prov-o/) represents sources, production and
  bundle activities, agents, derivation and retrieval provenance.
- [DQV](https://www.w3.org/TR/vocab-dqv/) represents evidence-backed quality
  metrics and annotations. DQV is a W3C Working Group Note, not a W3C
  Recommendation.
- [RDF Data Cube](https://www.w3.org/TR/vocab-data-cube/) represents dimensions,
  measures, attributes and code-list references. The bundle never creates
  observation resources.
- [SDMX 3.1](https://sdmx.org/standards-2/), released in May 2025, represents
  dataflows, structures, concepts, code lists and content constraints. These
  constraints should drive valid MCP selection rather than a generic parameter
  elicitation.
- [DDI Common Core](https://ddialliance.org/ddi-common-core) and
  [GSIM 2.0](https://unece.org/statistics/modernstats/gsim) provide mappings for
  universes, concepts, represented variables and value domains.
- [GSBPM 5.2](https://unece.org/statistics/gsbpm-v5.2), endorsed in June 2025,
  provides the current process vocabulary for explaining how statistics are
  produced.
- [CSVW](https://www.w3.org/TR/tabular-metadata/) describes actual tabular
  distributions without storing their rows.

[DCAT-AP 3.0.1](https://semiceu.github.io/DCAT-AP/releases/3.0.1/) is an
optional European federation/export profile. It is not the canonical UK model,
and a DCAT-AP validation result must not be used as a statistical-quality
claim.

### SDMX implementation boundary

SDMX is implemented in three deliberately separate places:

1. `sdmx-3-1` is an international-standard register entry with one
   executable-structure requirement.
2. The ontology crosswalk maps exactly seven canonical fields: `concept`,
   `dimensions`, `codeLists`, `selectionConstraints`, `frequency`, `measure`
   and `unit`. SDMX agency, identifier, version, dimension order and DSD
   component role remain explicit.
3. The Nomis source lane preserves SDMX structure metadata for all frozen
   Nomis records. Every binding remains `complete: false` until dimensions and
   codelist values are selected; completed execution is delegated to
   MCP-Geo's `nomis_query`.

The generated `data/standards/sdmx.json` makes those claims and their
denominators machine-readable. The bundle itself remains JSON-LD using DCAT 3,
SKOS, PROV-O and RDF Data Cube terms. Its JSON-LD context intentionally has no
SDMX namespace. Crosswalks support discovery and exchange; they do not certify
upstream ONS or Nomis conformance.

## Geospatial metadata

For spatial records, preserve geography level, GSS code family, reference
vintage, CRS, spatial extent, boundary variant, lineage and quality evidence.
The relevant sources are the
[UK GEMINI metadata guidance](https://www.gov.uk/government/publications/making-your-geospatial-data-easy-to-find-metadata-best-practice-guide-for-data-publishers/making-your-data-easy-to-find-metadata-best-practice-guide-for-data-publishers),
[ISO 19115-1](https://www.iso.org/standard/53798.html) and
[ISO 19157-1:2023](https://www.iso.org/standard/78900.html).

The [INSPIRE Regulations 2009](https://www.legislation.gov.uk/uksi/2009/3157/contents)
and GEMINI validation apply conditionally to in-scope spatial assets. A dataset
with a geography dimension is not automatically an INSPIRE dataset, and a
valid bounding box is not evidence of positional accuracy.

## Human and agent discovery contract

Every result should expose a compact decision signature:

```text
population or universe
concept and measure
unit, denominator or adjustment basis
geography level, code family and vintage
reference period and frequency
source and method
edition, version, provisional state and statistical status
```

Similar records remain in the candidate set. A **Compare alternatives** view
must explain at least one material difference before selection; title
similarity is never equivalence evidence. The same contrasts are available as
typed, field-provenanced data to an agent.

Recommended record views are:

1. Overview and decision signature.
2. Compare alternatives.
3. Quality and methodology.
4. How produced, using PROV and evidenced GSBPM mappings.
5. Versions, revisions and corrections.
6. Dimensions, code lists and valid combinations.
7. Geography and map, with an equivalent accessible table.
8. Access and read-only MCP selection plan.
9. Standards evidence.

An MCP plan is executable only after the exact dataset edition/version,
required dimensions, code-list options and published constraints validate.
The static Pages site never receives or stores an API key.

## Evaluation requirements

The standards register drives these independently reported checks:

1. **Coverage and denominator:** expected, discovered, represented, aliased,
   excluded and errored records by official source lane; unexplained omissions
   must be zero for a complete-snapshot claim.
2. **Reproducibility:** frozen source manifest, deterministic canonical output,
   pinned dependencies, logs, tests, CI and secret scanning.
3. **Profile validation:** JSON Schema, JSON-LD expansion and SHACL for the
   declared OKF, UK/DCAT and optional export profiles.
4. **Semantic integrity:** unique identifiers, classification and code-list
   versions, SKOS mapping integrity, reciprocal relations and acyclic
   single-current version chains.
5. **Confusability retrieval:** ambiguous human and agent queries scored using
   Recall@k, MRR or nDCG, alternative exposure and material contrast coverage.
6. **Cross-source consistency:** reconcile catalogue, website, release, QMI,
   time-series, API, download and data.gov.uk identifiers, titles, dates,
   versions, dimensions and geographies. Preserve discrepancies as evidence.
7. **Quality evidence:** report Code 3.0, QMI, revision, harmonisation and DQV
   coverage with explicit denominators; do not infer accuracy.
8. **Process evidence:** PROV and GSBPM coverage and QAAD's four areas where
   administrative data is used.
9. **SDMX and MCP:** validate version-specific dimensions, code lists and
   constraints; block impossible or ambiguous plans without calling the data
   endpoint.
10. **Accessibility:** WCAG 2.2 AA automation plus keyboard, zoom, focus,
    contrast, screen-reader and map-alternative testing.
11. **Drift:** URL, MIME type, source modification, digest, redirect, tombstone
    and version-change checks.

Reports include machine-readable JSON or JUnit and a human-readable summary
with methods, denominators, dates and evidence. There is no single opaque
standards or statistical-quality score.

## Maintaining the register

For each update:

1. Verify currentness from the authority's primary source.
2. Record version, release/update date, normative status and applicability.
3. Separate legal or mandatory requirements from conditional, advisory and
   informative guidance.
4. Update the crosswalk and tests when a term, version or profile changes.
5. Preserve superseded evidence with a `stale` status rather than rewriting
   history.
6. Re-run standards-register, source-register and complete bundle validation.
