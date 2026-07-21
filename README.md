# ONS Open Knowledge Format

`okf-ons` is a metadata-only discovery layer for public statistics exposed
through Office for National Statistics services. It is designed to help a
person or an agent find the exact dataset, see easily confused alternatives,
understand the statistical-quality evidence that is available, and prepare a
non-executing candidate plan that a downstream service must live-validate and
authorise before retrieval.

The project deliberately separates four jobs:

1. **The static OKF bundle discovers and explains** datasets, versions,
   dimensions, provenance, standards evidence, and alternatives.
2. **OKF Explorer narrows and compares** a large static corpus without an LLM
   or a hosted search service.
3. **The repository's local MCP broker gives AI clients bounded access** to
   the same frozen metadata and prepares a non-executing selection plan.
4. **A downstream live-data MCP server executes** an ONS or Nomis query only
   after the required dataset-specific choices are complete.

The local broker is not the downstream live-data server: it makes no network
calls and returns no observation values. No observations, API keys, or private
data are stored in the bundle.

## Access and documentation

These are the canonical entry points for release `v0.2.0`. The Pages site
tracks the most recently deployed `main`; use the tagged release downloads when
an immutable copy is required.

### Live and machine-readable access

| Resource | URL |
| --- | --- |
| Human discovery UI | <https://chris-page-gov.github.io/okf-ons/> |
| Open this bundle directly in OKF Explorer | <https://chris-page-gov.github.io/okf-explorer/?bundle=https%3A%2F%2Fchris-page-gov.github.io%2Fokf-ons%2Fokf-explorer.json> |
| OKF Explorer without a preloaded bundle | <https://chris-page-gov.github.io/okf-explorer/> |
| OKF bundle descriptor | <https://chris-page-gov.github.io/okf-ons/okf-explorer.json> |
| Semantic JSON-LD bundle | <https://chris-page-gov.github.io/okf-ons/okf-bundle.jsonld> |
| Semantic YAML-LD bundle | <https://chris-page-gov.github.io/okf-ons/okf-bundle.yamlld> |
| Pinned local JSON-LD context | <https://chris-page-gov.github.io/okf-ons/context/okf-ons.jsonld> |
| Data and shard manifest | <https://chris-page-gov.github.io/okf-ons/data/manifest.json> |
| Overview index | <https://chris-page-gov.github.io/okf-ons/data/overview.json> |
| Analysis overview | <https://chris-page-gov.github.io/okf-ons/data/analysis/overview.json> |
| Coverage ledger | <https://chris-page-gov.github.io/okf-ons/data/coverage/ledger.json> |
| Cross-source reconciliation | <https://chris-page-gov.github.io/okf-ons/data/reconciliation/report.json> |
| Governed release metadata | <https://chris-page-gov.github.io/okf-ons/data/governance/release.json> |
| Digest-bound context set | <https://chris-page-gov.github.io/okf-ons/data/governance/context-set.json> |
| Checksums | <https://chris-page-gov.github.io/okf-ons/checksums.json> |
| Search manifest | <https://chris-page-gov.github.io/okf-ons/data/search/manifest.json> |
| Standards evaluation | <https://chris-page-gov.github.io/okf-ons/data/standards/evaluation.json> |
| SDMX evidence | <https://chris-page-gov.github.io/okf-ons/data/standards/sdmx.json> |
| Evaluation report | <https://chris-page-gov.github.io/okf-ons/data/evaluation/report.json> |
| MCP binding index | <https://chris-page-gov.github.io/okf-ons/data/ons/mcp-bindings.json> |
| Spatial index | <https://chris-page-gov.github.io/okf-ons/data/ons/spatial-index.json> |
| Live demo guide | <https://chris-page-gov.github.io/okf-ons/demo-guide.html> |
| Accessibility statement | <https://chris-page-gov.github.io/okf-ons/accessibility.html> |

Subordinate dataset, resource, search and selection-option shards are discovered
through the data and search manifests above; their generated paths are not
independent stable entry points.

### Repositories, release and provenance

- [OKF-ONS repository](https://github.com/chris-page-gov/okf-ons),
  [all GitHub Releases](https://github.com/chris-page-gov/okf-ons/releases), and
  [release v0.2.0](https://github.com/chris-page-gov/okf-ons/releases/tag/v0.2.0)
- Immutable v0.2.0 downloads:
  [bundle ZIP](https://github.com/chris-page-gov/okf-ons/releases/download/v0.2.0/okf-ons-v0.2.0-bundle.zip) and
  [SHA-256 digest](https://github.com/chris-page-gov/okf-ons/releases/download/v0.2.0/okf-ons-v0.2.0-bundle.zip.sha256)
- [OKF Explorer repository](https://github.com/chris-page-gov/okf-explorer)
- [Pinned ONSdigital Explore Local Statistics commit](https://github.com/ONSdigital/explore-local-statistics-app/commit/795eaf204f47986f6be248a63f857a42afe4fdf2)
- [Source register](source/source-register.json),
  [release snapshot manifest](source/demo-snapshot/snapshot.json),
  [current enrichment snapshot manifest](source/metadata-enrichment-2026-07-21-r6/snapshot.json), and
  [release changelog](CHANGELOG.md)

### Documentation map

- Product and demonstration:
  [demo guide](docs/demo-guide.md),
  [product contract](docs/product-contract.md),
  [ONS hackathon brief](docs/ONS-HACKATHON-BRIEF.md), and
  [accessibility statement](accessibility.md)
- Repository operation:
  [repository guide](AGENTS.md),
  [security policy](SECURITY.md),
  [release changelog](CHANGELOG.md), and
  [CI publication workflow](.github/workflows/pages.yml); the
  [AI-client change fragment](changelog.d/20260718-ai-client-harness.md) is
  retained as pre-release history
- Metadata and assurance:
  [metadata model](docs/metadata-model.md),
  [scope and denominator](docs/scope-and-denominator.md), and
  [standards register](docs/standards-register.md), plus the
  [timed metadata-enrichment campaign](docs/metadata-enrichment-campaign.md)
  and the
  [OKF Explorer campaign handoff](docs/okf-explorer-metadata-campaign-handoff.md),
  with the machine-readable
  [stopping audit](evaluation/metadata-completeness/stopping-audit.json)
- MCP and AI access:
  [MCP selection contract](docs/mcp-selection-contract.md),
  [MCP client rollout](docs/mcp-client-rollout.md), and
  [agent-access and evaluation proposal](docs/agent-access-and-evaluation-proposal.md)
- Evaluation:
  [evaluation method](docs/evaluation.md),
  [cross-client trial analysis](docs/ai-client-trial-analysis.md), and the
  machine-readable
  [study](evaluation/ai-client/study.json),
  [client registry](evaluation/ai-client/client-profiles.json),
  [tasks](evaluation/ai-client/tasks.json),
  [expected results](evaluation/ai-client/expected.json),
  [personas and journeys](evaluation/ai-client/personas-and-journeys.json),
  [issue register](evaluation/ai-client/issue-register.json), and
  [gold queries](evaluation/gold-queries.json)
- Research and communications:
  [research register](research/README.md),
  [research evidence manifest](research/manifest.json),
  [architecture manifest](research/architecture-manifest.json),
  [governed-AI research prompt](research/okf-governed-ai-deep-research-prompt.md),
  [governed-AI architecture report](research/OKF_Governed_AI_Architecture_Deep_Research_Report_2026-07-20.md), and
  [publication draft](docs/LINKEDIN-POST.md)
- Dated AI-client research records:
  [Claude Desktop access trace](research/2026-07-18-claude-desktop-cowork-fable-5-okf-ons-access-trace.md),
  [Antigravity briefing](research/2026-07-18-antigravity-cli-gemini-3-1-pro-okf-ons-briefing.md), and
  [Antigravity postmortem](research/2026-07-18-antigravity-cli-gemini-3-1-pro-okf-ons-postmortem.md)
- Portable research outputs:
  [Claude trace DOCX](research/2026-07-18-claude-desktop-cowork-fable-5-okf-ons-access-trace-public-sanitized.docx),
  [M365 access briefing DOCX](research/2026-07-18-m365-copilot-researcher-okf-ons-access-briefing-public-sanitized.docx),
  [M365 hosting research DOCX](research/2026-07-18-m365-copilot-researcher-okf-hosting-research-public-sanitized.docx),
  [governed-AI presentation](research/Governed_AI_Architecture_%282%29.pptx),
  [enterprise-AI presentation](research/Architecting_Governed_Enterprise_AI%20%281%29.pptx), and the
  [discovery-bridge visual](research/Reliable_Public_Statistics_Discovery_Bridge.png)

OKF Explorer can load the bundle today through the direct link above. A
separate Explorer registry and presentation update is recommended so the bundle
is suggested without pasting its URL and the new authority, rights and
governance fields are shown as first-class UI rather than only in raw JSON.

## SDMX support

The bundle registers SDMX 3.1 (ISO 17369), maps seven canonical OKF fields to
SDMX concepts, and preserves the Nomis lane's SDMX agency, identifier, version,
dimension order, component roles and code-list references. Nomis selections
also retain bounded FREQ code-label options and strict available TIME extents
where that evidence is usable. FREQ is statistical/reference frequency, not
publication cadence, and TIME-period revision annotations are not dataset
revision status. All other required dimensions still need live validation and
selection; completed live execution uses MCP-Geo's `nomis_query`.

The bundle is not itself an SDMX message. It is serialized as JSON-LD using
DCAT 3, SKOS, PROV-O and RDF Data Cube terms, with no SDMX namespace in its
context. The generated `data/standards/sdmx.json` reports the exact mapping and
Nomis evidence counts without asserting upstream conformance or certification.

## Monday demonstrator

The pre-hackathon demonstrator is frozen so the Monday presentation can use a
reproducible, reviewable snapshot rather than changing live acquisitions. It
publishes:

- a source and coverage ledger that makes incompleteness explicit;
- a frozen 5,097-record metadata snapshot from ONS Data API (337), Nomis
  (1,617), ONS Open Geography (3,035), and ONS Explore Local Statistics (108);
- qualified source-producer, service-operator, bundle-publisher and semantic
  authority roles, with explicit non-endorsement;
- deterministic search and first-class filter postings;
- evidence-backed alternative/contrast relationships;
- exact Census table-code reconciliation across ONS Data API and Nomis;
- statistical-quality and standards evidence without false assurance claims;
- an MCP selection-plan contract; and
- a reproducible retrieval and metadata-quality evaluation report.

The immutable snapshot ID `monday-2026-07-17-r2` extends the Friday 17 July
freeze with the pinned ELS metadata projection. The `r2` suffix prevents the
expanded corpus from reusing the original v0.1 snapshot identity; “monday” is
the demonstrator name, not a claim that 17 July was a Monday.

The Explore Local Statistics lane is a deterministic, allowlisted projection
of the pinned application submodule. It carries 108 ONS-curated indicators from
24 attributed producers, explains 12 unpublished manifest entries, preserves
46 valid historical aliases, and removes observation values, status arrays,
value domains, binaries and geometry. It is a development fixture rather than
a claim that the internal ELS API is a stable public execution contract. Its
verified Git `commitAsOf` is kept separate from acquisition time; the frozen
fixture does not invent a retrieval timestamp that was not recorded.

This experimental bundle is independently published by the OKF ONS project.
Source attribution does not imply endorsement by ONS or another producer.

## Build

Python 3.11 or later is required. A recursive clone is required because normal
GitHub source archives do not contain the pinned ELS submodule. The release
bundle ZIP linked above is the self-contained publication artifact.

To reproduce `v0.2.0` from its checked-in frozen snapshot:

```bash
git clone --recurse-submodules --branch v0.2.0 \
  https://github.com/chris-page-gov/okf-ons.git
cd okf-ons
python scripts/project_els_snapshot.py \
  --submodule-dir vendor/explore-local-statistics-app \
  --output output/ons-explore-local-statistics.json
cmp output/ons-explore-local-statistics.json \
  source/demo-snapshot/ons-explore-local-statistics.json
python scripts/build_bundle.py \
  --snapshot-dir source/demo-snapshot \
  --output bundle
python scripts/build_bundle.py \
  --snapshot-dir source/demo-snapshot \
  --output bundle \
  --check
```

The metadata-enrichment campaign also includes immutable successor snapshot
`metadata-enrichment-2026-07-21-r6`. Relative to the v0.2.0 snapshot, r3
refreshes the bounded ONS Data API catalogue, r4 adds bounded metadata-only
Nomis compact overviews, and r5 adds only the reviewed dimension projection
from each frozen ONS latest-version URL. r6 follows the exact FREQ and TIME
codelist references in the frozen r5 Nomis cohort and retains only code-label
metadata and explicit period revision-status annotations. The ONS Data API,
Explore Local Statistics and Open Geography source envelopes in r6 are
byte-identical to r5. Rebuild and profile r6 without network access:

```bash
python scripts/build_bundle.py \
  --snapshot-dir source/metadata-enrichment-2026-07-21-r6 \
  --output bundle
python scripts/build_bundle.py \
  --snapshot-dir source/metadata-enrichment-2026-07-21-r6 \
  --output bundle \
  --check
python scripts/profile_metadata_gaps.py \
  --bundle bundle \
  --output evaluation/metadata-completeness/current.json
```

The live Pages and Explorer URLs above still serve governed release v0.2.0.
The r6 campaign snapshot is checked in as governed campaign evidence but
remains an undeployed release candidate until the release metadata and
Pages-selected snapshot are deliberately switched.

The measured batch history, metric definitions, timings and machine-readable
profiles are linked from the
[metadata-enrichment campaign](docs/metadata-enrichment-campaign.md), including
the [stopping audit](evaluation/metadata-completeness/stopping-audit.json).

For an existing clone, run `git submodule update --init --recursive` before the
projector. To acquire a future snapshot, keep the raw cache outside the
repository, use `--mode refresh`, and choose a new immutable identity—never
overwrite an existing snapshot. To refresh only the ONS catalogue while
carrying the other validated source envelopes forward:

```bash
python scripts/acquire_snapshot.py \
  --cache-dir /path/to/raw-cache \
  --output-dir source \
  --snapshot-id NEW_UNIQUE_SNAPSHOT_ID \
  --base-snapshot source/metadata-enrichment-2026-07-21-r4 \
  --source ons-data-api \
  --mode refresh \
  --page-size 1000 \
  --maximum-pages 1 \
  --require-complete
```

To reproduce or refresh the bounded Nomis compact overviews, use the validated
pre-enrichment r3 snapshot as the base: replacement envelopes are digest-bound
to that exact cohort and enrichment snapshots are not chained as acquisition
bases. First acquire into an external replacement envelope, then compose that
envelope over r3. The acquisition script independently derives its cohort from
the frozen Nomis source and publishes neither raw responses nor cache paths:

```bash
python scripts/acquire_nomis_overviews.py \
  --snapshot-dir source/metadata-enrichment-2026-07-21-r3 \
  --cache-dir /path/to/raw-cache \
  --output /path/to/nomis-overviews.json \
  --limit 1617 \
  --mode refresh \
  --request-interval 0.2
python scripts/acquire_snapshot.py \
  --cache-dir /path/to/raw-cache \
  --output-dir source \
  --snapshot-id NEW_UNIQUE_SNAPSHOT_ID \
  --base-snapshot source/metadata-enrichment-2026-07-21-r3 \
  --replacement-acquisition /path/to/nomis-overviews.json \
  --require-complete
```

To reproduce or refresh the bounded ONS latest-version dimension projection,
use r4 as the validated pre-enrichment base. The acquisition follows only the
337 exact `links.latest_version.href` values frozen in r4, stores only the
allowlisted projection in an external cache, and does not fetch observations,
dimension options, codelists or downloads:

```bash
python scripts/acquire_ons_version_metadata.py \
  --snapshot-dir source/metadata-enrichment-2026-07-21-r4 \
  --cache-dir /path/to/external-cache \
  --output /path/to/ons-version-metadata.json \
  --limit 337 \
  --mode refresh \
  --request-interval 0.5
python scripts/acquire_snapshot.py \
  --cache-dir /path/to/external-cache \
  --output-dir source \
  --snapshot-id NEW_UNIQUE_SNAPSHOT_ID \
  --base-snapshot source/metadata-enrichment-2026-07-21-r4 \
  --replacement-acquisition /path/to/ons-version-metadata.json \
  --require-complete
```

To reproduce or refresh the bounded Nomis FREQ/TIME codelist projection, use
r5 as the exact base. The acquisition follows 3,234 frozen metadata-only
codelist references sequentially, retains explicit failed outcomes in the
denominator, and stores only its allowlisted projection in a versioned external
cache:

```bash
python scripts/acquire_nomis_codelists.py \
  --snapshot-dir source/metadata-enrichment-2026-07-21-r5 \
  --cache-dir /path/to/external-cache \
  --output /path/to/nomis-codelists.json \
  --limit 1617 \
  --mode refresh \
  --request-interval 0.2
python scripts/acquire_snapshot.py \
  --cache-dir /path/to/external-cache \
  --output-dir source \
  --snapshot-id NEW_UNIQUE_SNAPSHOT_ID \
  --base-snapshot source/metadata-enrichment-2026-07-21-r5 \
  --replacement-acquisition /path/to/nomis-codelists.json \
  --require-complete
```

For a full registered-source refresh, first produce the pinned local ELS
projection, then acquire all HTTP lanes and include it:

```bash
python scripts/project_els_snapshot.py \
  --submodule-dir vendor/explore-local-statistics-app \
  --output /path/to/els-projection.json
python scripts/acquire_snapshot.py \
  --cache-dir /path/to/raw-cache \
  --output-dir /path/to/public-snapshots \
  --snapshot-id NEW_UNIQUE_SNAPSHOT_ID \
  --mode refresh \
  --projected-acquisition /path/to/els-projection.json \
  --require-complete
```

Acquisition is resumable and external. `bundle/` is deterministic from a
validated frozen snapshot.

The sendable [ONS hackathon brief](docs/ONS-HACKATHON-BRIEF.md) explains the
work package, demo route and questions for ONS. See also the
[standards register](docs/standards-register.md),
[evaluation method](docs/evaluation.md), and
[scope and denominator](docs/scope-and-denominator.md).

## AI access research and evaluation

The repository preserves and SHA-256-pins 18 July 2026 trials from Claude
Desktop Cowork, Google Antigravity CLI and Microsoft 365 Copilot Researcher in
[`research/`](research/README.md). Only technically reviewed, sanitized public
DOCX derivatives are published. The original Office packages are withheld
outside Git and identified only by their pinned source hashes. Normalized
observations keep public derivatives, session-reported identity, later
verification and our interpretations distinct.

The case study now seeds a provider-neutral, fixture-safe harness:

```bash
python3 scripts/ai_client_harness.py validate
python3 scripts/ai_client_harness.py validate-research
python3 scripts/ai_client_harness.py clients --initial-only
python3 scripts/ai_client_harness.py probe-clients
python3 scripts/ai_client_harness.py tasks
```

The harness defines OKF, open-web and raw-API arms; eight development smoke
tasks; six ONS-specific personas and eight journeys; a ten-item observed-issue
register; a common structured answer; answer-bound independent assessment;
deterministic component scoring; enforced-versus-self-reported separation; and
separate readiness outcomes so a blocked client is not scored as a wrong
answer. CI performs no live, authenticated or paid model calls.

A dependency-free, metadata-only MCP broker now exposes deterministic
descriptor, search, exact-record, comparison, read-only MCP-plan and
answer-submission tools. Antigravity CLI (`agy`) can load it from the
repository-scoped [`.agents/mcp_config.json`](.agents/mcp_config.json). That
configuration was added after the preserved Antigravity trial; no new paid or
live model run is claimed. The broker uses the frozen corpus, makes no network
call, stores no credentials and returns no observation values.

## AI-system connection map

The [MCP rollout guide](docs/mcp-client-rollout.md) is the canonical setup and
status guide for every AI surface in the evaluation registry. It distinguishes
four access and deployment layers:

- **Static bundle access:** any permitted HTTP client can read the Pages
  descriptor and JSON, but native fetch limits differ by host.
- **Local metadata MCP:** command-line and desktop clients that support local
  stdio MCP can start `scripts/okf_ons_mcp.py`. The committed AGY workspace
  configuration is the only repository-scoped client configuration; the guide
  gives the separate Codex, Claude, Gemini, VS Code/Copilot and Inspector
  routes without treating installation as a successful trial.
- **Planned remote metadata MCP:** ChatGPT custom apps need a supported remote
  endpoint or tunnel route; Claude Research, remote-session Cowork and
  Microsoft 365 Copilot Researcher need an authenticated remote endpoint.
  Desktop-local Cowork may use local MCP, subject to device policy. This
  repository deploys neither a remote endpoint nor a tunnel. The M365
  federated-connector route is documented, but it has not been created or
  enabled for a tenant.
- **Downstream live MCP:** once selection is complete, a separate ONS or Nomis
  integration may execute the plan. The repository broker deliberately never
  does so.

The machine-readable
[`client-profiles.json`](evaluation/ai-client/client-profiles.json) is the
complete 16-profile client registry; [`study.json`](evaluation/ai-client/study.json)
pins the evaluation design. The public
[`tasks.json`](evaluation/ai-client/tasks.json),
[`personas-and-journeys.json`](evaluation/ai-client/personas-and-journeys.json)
and [`issue-register.json`](evaluation/ai-client/issue-register.json) keep the
tasks, users, journeys, observed failures and remediations in lockstep with
that design.

See the
[cross-client trial analysis](docs/ai-client-trial-analysis.md) for the
evidence, issue/remediation matrix, personas, efficiency protocol and
prioritized work packages.

## What “all” means

The repository may describe itself as covering **all public ONS metadata** only
when every in-scope source in `source/source-register.json` has a measured
denominator and the generated coverage ledger reports
`unexplained_omissions = 0`.

Observation cells, secure microdata, and duplicate binary payloads are
intentionally out of scope. See
[scope and denominator](docs/scope-and-denominator.md).

## Licensing

Code is MIT licensed. Source metadata remains subject to its stated upstream
licence, often the Open Government Licence v3.0. The bundle makes no blanket
licence claim: ELS record rights remain `not-evaluated` pending source-by-source
review, and generated records preserve the available source and rights evidence.
