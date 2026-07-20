# ONS Open Knowledge Format

`okf-ons` is a metadata-only discovery layer for public Office for National
Statistics data. It is designed to help a person or an agent find the exact
dataset, see easily confused alternatives, understand the statistical-quality
evidence that is available, and hand a validated selection to a downstream MCP
server for live retrieval.

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

## SDMX support

The bundle registers SDMX 3.1 (ISO 17369), maps seven canonical OKF fields to
SDMX concepts, and preserves the Nomis lane's SDMX agency, identifier, version,
dimension order, component roles and code-list references. Nomis selections
remain incomplete until their dimensions and codelist values have been chosen;
completed live execution uses MCP-Geo's `nomis_query`.

The bundle is not itself an SDMX message. It is serialized as JSON-LD using
DCAT 3, SKOS, PROV-O and RDF Data Cube terms, with no SDMX namespace in its
context. The generated `data/standards/sdmx.json` reports the exact mapping and
Nomis evidence counts without asserting upstream conformance or certification.

## Monday demonstrator

The pre-hackathon demonstrator is frozen so the Monday presentation can use a
reproducible, reviewable snapshot rather than changing live acquisitions. It
publishes:

- a source and coverage ledger that makes incompleteness explicit;
- a frozen 4,989-record metadata snapshot from ONS Data API (337), Nomis
  (1,617), and ONS Open Geography (3,035);
- deterministic search and first-class filter postings;
- evidence-backed alternative/contrast relationships;
- exact Census table-code reconciliation across ONS Data API and Nomis;
- statistical-quality and standards evidence without false assurance claims;
- an MCP selection-plan contract; and
- a reproducible retrieval and metadata-quality evaluation report.

The immutable snapshot ID `monday-2026-07-17` records the Friday 17 July freeze
for the Monday 20 July 2026 hackathon; it is not a claim that 17 July was a
Monday.

The public descriptor is designed to be:

```text
https://chris-page-gov.github.io/okf-ons/okf-explorer.json
```

and to open in OKF Explorer using:

```text
https://chris-page-gov.github.io/okf-explorer/?bundle=https%3A%2F%2Fchris-page-gov.github.io%2Fokf-ons%2Fokf-explorer.json
```

## Build

Python 3.11 or later is required. To refresh a snapshot, keep the raw
acquisition cache outside the repository; the checked-in Monday build is
generated from `source/demo-snapshot`.

```bash
python scripts/acquire_snapshot.py \
  --cache-dir /path/to/raw-cache \
  --output-dir /path/to/public-snapshots \
  --snapshot-id monday-2026-07-17
python scripts/build_bundle.py \
  --snapshot-dir source/demo-snapshot \
  --output bundle
python scripts/build_bundle.py \
  --snapshot-dir source/demo-snapshot \
  --output bundle \
  --check
```

Acquisition is resumable and external. `bundle/` is deterministic from a
frozen snapshot.

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
licence, normally the Open Government Licence v3.0. Generated records preserve
source and licence evidence.
