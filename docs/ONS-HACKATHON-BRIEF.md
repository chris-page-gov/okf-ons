# ONS OKF discovery demonstrator

## One-page overview for the ONS hackathon

**Proposal:** use an Open Knowledge Format (OKF) bundle as the inspectable,
versioned discovery and evidence layer for ONS data, then use MCP as the
controlled execution layer once a person or agent has selected the right
dataset, version, dimensions and options.

The desired interaction is:

> **browse → reduce → compare → configure → execute**

The problem is not merely finding a title containing the right words. ONS
publishes related products that can look interchangeable while differing in
population, measure, denominator, method, geography, reference period,
frequency, adjustment, revision status or statistical status. The
demonstrator therefore keeps plausible alternatives visible and shows the
evidence needed to distinguish them before it produces an MCP request plan.

## What is available

- [GitHub repository](https://github.com/chris-page-gov/okf-ons)
- [Human discovery demonstrator](https://chris-page-gov.github.io/okf-ons/)
- [OKF bundle descriptor](https://chris-page-gov.github.io/okf-ons/okf-explorer.json)
- [Open the bundle in OKF Explorer](https://chris-page-gov.github.io/okf-explorer/?bundle=https%3A%2F%2Fchris-page-gov.github.io%2Fokf-ons%2Fokf-explorer.json)
- [Machine-readable coverage ledger](https://chris-page-gov.github.io/okf-ons/data/coverage/ledger.json)
- [Evaluation report](https://chris-page-gov.github.io/okf-ons/data/evaluation/report.json)
- [AI-system MCP rollout guide](mcp-client-rollout.md)
- [Cross-client trial analysis](ai-client-trial-analysis.md)

These URLs become live from the repository's Pages deployment. No API key,
observation values or private data are included.

## Monday demonstrator

The checked-in frozen snapshot represents metadata from three official source
lanes:

| Source lane | Upstream denominator | Represented | What it contributes |
|---|---:|---:|---|
| ONS Data API products | 337 | 337 | dataset identities, lifecycle, links and API selection starting points |
| Nomis definitions | 1,617 | 1,617 | SDMX-style dataset structures, concepts, dimensions and code-list references |
| ONS Open Geography | 3,035 | 3,035 | geography products, vintages, variants, spatial envelopes and resource links |
| **Implemented-lane total** | **4,989** | **4,989** | non-additive catalogue representations; not 4,989 unique statistical concepts |

The broader claim “all ONS metadata” is deliberately not made yet. The
coverage ledger identifies ONS website datasets and releases, time-series and
downloads, QMI and methodology enrichment, and cross-portal reconciliation as
planned lanes. Counts across lanes cannot simply be added because one
statistical product may appear in several catalogues.

## What to demonstrate

1. Search for an intent, not an identifier—for example “latest local authority
   population estimate by age and sex”.
2. Reduce the result set using source and statistical metadata facets.
3. Select a candidate and open **Compare alternatives**.
4. Inspect differences in source, measure, geography, time basis, frequency,
   version and available quality evidence.
5. Open **Quality & methodology** and **Standards evidence**. Missing evidence
   is shown as `not-evidenced`; it is never converted into a claim of failure
   or compliance.
6. Open **Access via MCP**. For ONS Data API and Nomis, the bundle identifies
   an existing discovery/definition tool and the remaining dimensions. MCP
   performs a live query only after the selection is complete; no unknown
   dimension silently receives its first value. Open Geography records state
   that the general catalogue-item MCP binding is planned rather than naming a
   tool that does not exist.
7. Open the same static descriptor in OKF Explorer to show that the corpus is
   portable and agent-readable.

## Why OKF and MCP belong together

| OKF bundle | MCP server |
|---|---|
| Stable, content-addressed metadata snapshot | Current upstream interaction |
| Search, facets and comparison | Dataset-specific elicitation |
| Provenance and source receipts | Validation against live dimensions/options |
| Quality, methodology and standards evidence | Read-only query execution |
| Versioned selection-plan contract | Normalised results and upstream errors |
| Deterministic evaluation fixtures | Live integration and round-trip tests |

OKF prevents the MCP interaction from starting as an open-ended conversation
with thousands of poorly distinguished choices. MCP prevents the static
catalogue from pretending that versions, codelists and availability never
change.

## AI-system access boundary

The repository includes a local, provider-neutral MCP broker for bounded
descriptor, search, exact-record, comparison and non-executing selection-plan
operations over the frozen metadata. It has a committed AGY workspace example;
the rollout guide records separate configuration and readiness for Codex,
Claude, Gemini, VS Code/Copilot, ChatGPT, Microsoft 365 and MCP Inspector.

This is not a live-data or hosted remote server. ChatGPT custom apps require a
future supported remote or tunnel route; Claude Research, remote-session Cowork
and M365 Copilot Researcher require a future authenticated remote deployment.
The M365 federated connector is documented but not deployed. A separate
downstream ONS or Nomis MCP integration would execute a validated plan and
return observations.

## Standards and statistical-quality position

The model preserves and links evidence relevant to:

- Code of Practice for Statistics 3.0 and Standards for Public Use;
- ONS Quality and Methodology Information and revisions guidance;
- Government Functional Standard GovS 010, the Aqua Book, RAP and the
  Government Data Quality Framework;
- GSS classifications, harmonised standards and geography codes;
- UK DCAT 3 guidance and the Cross-Government Metadata Exchange Model;
- DCAT 3, SKOS, PROV-O, DQV, RDF Data Cube, SDMX, GSBPM, GSIM and DDI;
- accessibility, privacy and applicable geospatial metadata requirements.

Every standards claim has an applicability state and source evidence. Bundle
profile conformance is kept separate from evidence about a statistical
product. Metadata coverage can show whether accuracy evidence is available; it
cannot establish that the underlying observations are statistically accurate.

## Evaluation

The repository contains a reproducible gold suite of 12 deliberately
confusable statistical-data questions. It measures:

- Recall@k, MRR and nDCG for the intended product;
- whether important alternatives are exposed early enough;
- whether each alternative has the required contrast fields;
- metadata-evidence and standards-evidence coverage;
- source denominators, unexplained omissions and normalisation drops;
- deterministic frozen rebuilds and output checksums;
- cross-source table-code reconciliation and conflicts;
- MCP selection completeness and the statistical-accuracy assurance boundary;
- public-output secret/path checks and browser accessibility checks.

Some gold aliases are intentionally unresolved by the three implemented source
lanes. They remain visible gaps rather than being attached to the nearest
title. That makes the evaluation useful for deciding which source lane to add
next.

The first reconciliation pass also found a particularly useful evidence path:
284 ONS Data API records use Census table codes; 283 have an exact code
counterpart in Nomis. Of those, 280 titles agree after conservative
normalisation, while RM166, RM181 and RM196 retain explicit title differences.
RM010 has no exact Nomis code counterpart in the snapshot. The bundle publishes
the code links and differences without asserting that two distributions are
statistically equivalent.

## Recommended work package

**Evidence-aware ONS data discovery and executable selection**

1. Complete the source census and denominator ledger across ONS catalogues,
   releases, downloads, QMI/methodology and data.gov.uk representations.
2. Establish evidence-backed cross-source identities, version/succession
   chains and production-process links; preserve conflicts rather than
   overwriting them.
3. Enrich decision signatures with population, concept, unit, geography
   vintage, time, frequency, source/method, adjustment and statistical status.
4. Extend OKF Explorer comparison, geography/map and dimension-configuration
   views.
5. Round-trip a complete selection plan through the MCP server and verify that
   the returned dataset/version/dimensions match the selection.
6. Run the discovery, reconciliation, drift, accessibility and evidence suite
   in CI and publish both human and machine-readable reports.

The success criterion is not “the agent returned a dataset”. It is:

> The person or agent selected the intended statistical product, saw the
> plausible alternatives and material differences, inspected the available
> evidence and produced a valid, reproducible MCP request without a silent
> assumption.

## Questions for ONS

- Which catalogue or internal identifier should anchor cross-surface identity?
- Which product distinctions most often cause user or analyst error?
- Which quality, revisions and production-process evidence can be linked
  consistently at dataset/version level?
- Can content constraints or dimension dependencies be exposed in a
  machine-readable form before an observation query?
- What benchmark questions and wrong-but-plausible alternatives should ONS
  statisticians add to the gold suite?
- Which of these artifacts could be generated at source as part of a
  reproducible publication pipeline?
