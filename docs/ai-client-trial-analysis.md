# AI-client trials: findings, design implications and remediation plan

## Decision summary

The three 18 July 2026 trials support the same practical conclusion from
different directions: the OKF-ONS content is useful when an agent reaches the
right evidence, but the current static delivery contract asks the client to do
too much discovery plumbing.

The most valuable next unit of work is therefore a provider-neutral,
metadata-only MCP broker over the frozen OKF corpus, coupled to a controlled
evaluation. It should make orientation, bounded search, exact-record hydration,
comparison and read-only query planning explicit. This repository now contains
that local broker and its Antigravity workspace configuration. A later remote
deployment should expose the same tool contract to Claude research modes and
Microsoft 365 Copilot Researcher.

This is not yet evidence that OKF is more efficient than the open web or raw ONS
APIs. The preserved trials did not hold prompts, host capabilities, model,
access arm or capture fidelity constant, and none contains exact provider token
telemetry. They are strong design evidence and regression seeds, not a
comparative benchmark.

## Evidence reviewed

| Trial | Host and model identity | Exact bundle access | Useful result | Main limitation |
| --- | --- | --- | --- | --- |
| Claude | Claude Desktop, Cowork/research mode; “Claude Fable 5” is session-reported | Partial | Good orientation and caveat relay; disclosed substitute example | Multi-megabyte fetch truncation, guessed hydration path and disconnected browser extension |
| Gemini | Antigravity CLI (`agy` 1.1.4 later verified); “Gemini 3.1 Pro (High)” is session-reported | Yes | Traversed descriptor and standards entrypoints; generated a concrete worked example | Downloaded a 5.9 MB shard, chose a convenient early record, and overstated compliance and efficiency |
| M365 | M365 Copilot Researcher in Edge; resolved model not exposed | No | Honest access caveat; useful M365 hosting and connector architecture research | Substituted web and enterprise context; no exact telemetry or native transcript; citations are not portable |

The raw artefacts are hash-pinned in
[`research/manifest.json`](../research/manifest.json). Normalized observations
under [`evaluation/ai-client/evidence/`](../evaluation/ai-client/evidence/)
separate direct observation, session report, later verification and inference.
None is eligible for the controlled comparison.

## What the trials establish

They establish, for these sessions, that:

1. A small descriptor with named entrypoints supports autonomous orientation
   once the client understands that it is the bundle root.
2. The standards register and record-level provenance can support
   evidence-grounded explanations.
3. Large browser-oriented shards create avoidable access, context and selection
   friction for agents.
4. Agents need a first-class exact-record contract and must show alternatives
   before selection when products are easy to confuse.
5. Host capabilities materially affect success. “The agent could not retrieve
   it” is not the same claim as “the bundle was unavailable”.
6. Caveats can survive into a long answer while a headline still overclaims.
   Visible-answer assurance therefore needs independent assessment.
7. Local MCP configuration is not portable across every research surface.

They do not establish:

- that OKF improves task accuracy or efficiency against a control;
- that any model, host or client is generally better than another;
- that OKF, the bundle, or an ONS product is compliant or certified;
- that the 4,989 represented records are all ONS data;
- the accuracy, quality or fitness of ONS observations and estimates; or
- current platform support beyond the sources and local probes recorded here.

## Detailed issue analysis

The machine-readable
[`issue-register.json`](../evaluation/ai-client/issue-register.json) is the
normative cross-reference. The most important design implications are below.

### 1. Orientation must be explicit

Gemini first interpreted “OKF package” as a possible installed package or MCP
server and searched its workspace and the web. That is understandable for a new
format. The descriptor was navigable, but the invitation to use it was not
self-explanatory.

Remediation:

- expose a compact `okf.descriptor` MCP tool and resource;
- state “metadata bundle, not package-manager dependency” in the agent
  quickstart;
- identify exact search, record, comparison, standards and selection-plan
  operations from the first response; and
- test first-use orientation in a fresh context.

### 2. Static UI shards are not an agent hydration API

Claude encountered truncation and Gemini downloaded approximately 5.95 MB,
dominated by `datasets-0.json`. Gemini then inspected only an early slice. A
later deterministic rebuild showed that every individual canonical record is
below 65,536 bytes, with a maximum of 30,708 bytes. The problem is delivery
granularity, not record size.

Remediation:

- keep static shards for OKF Explorer;
- give agents bounded `search` and exact `get_record` tools;
- return a stable record ID and evidence pointer from search;
- add canonical per-record static routes for non-MCP clients; and
- measure complete bytes, partial bytes, retries and hydration success
  separately.

### 3. Exact selection and alternatives are the central product outcome

The Gemini worked example was a convenient record in the first inspected slice,
not the outcome of an explicit user intent. Claude and M365 both used
substitutes after an access failure, although both disclosed the substitution.
This matters because ONS products often share familiar labels while differing
in population, denominator, method, frequency, geography, maturity or source.

The primary success criterion should therefore remain safe exact selection:

- identify the intended source-qualified record;
- expose plausible alternatives in the reduced set;
- show the decisive contrasts;
- hydrate the selected record completely;
- retain material caveats; and
- do not make a critical unsupported claim.

The `okf.compare` tool and the 12 confusable ONS gold queries directly exercise
this behaviour. A shared table code or title similarity is reconciliation
evidence, not proof of statistical equivalence.

### 4. Standards need typed assurance language

The Gemini briefing retained “alignment, not certification” in its detail but
described the exercise as successful autonomous compliance checking in the
executive summary. This is a useful demonstration of why caveat presence alone
is not an outcome.

Use distinct statuses:

- `declared`: stated by the source or bundle;
- `mapped`: a field is cross-walked to a vocabulary or requirement;
- `evaluated`: a named method checked evidence against declared criteria;
- `independently-certified`: a competent external authority certified it; and
- `not-evaluated`.

The public scorer already requires an independent assessment bound to exact
visible-answer spans. Critical phrases such as “aligned means certified” remain
an explicit fail condition.

### 5. Efficiency must be measured comparatively

The Gemini postmortem called the interaction highly token-efficient without
provider token telemetry or a control arm. Claude clearly labelled its token
range as estimated. M365 exposed neither tokens nor tool-call counts.

For each completed run capture, where the host exposes it:

| Measure | Required scope |
| --- | --- |
| elapsed time | task start to submitted structured answer |
| tool calls | by tool, including failed calls and retries |
| transferred bytes | complete and partial responses distinguished |
| provider tokens | input, cached input and output; null when not exposed |
| monetary cost | provider-reported or tariff-derived with method and date |
| selection work | candidates considered, comparisons and hydration attempts |
| result quality | safe exact selection and component scores |

Report time, calls, bytes, tokens and cost separately. Do not collapse them into
one “efficiency score” without a preregistered weighting. A comparative claim
requires the same task, host/model cell and access enforcement across the OKF,
open-web and raw-API arms.

### 6. Failure attribution belongs in the harness

The trials contain four distinct failure classes:

1. client readiness, such as a disconnected extension;
2. access-path or policy failure, such as M365 Researcher not reaching the
   supplied descriptor;
3. bundle contract failure, such as no declared single-record route; and
4. answer failure, such as selecting a substitute without the required
   distinction.

Blocked readiness remains outside answer-quality denominators. Observed and
self-reported enforcement remains descriptive; only run-bound enforced access
can enter comparative aggregates.

### 7. Trial identity must include host, mode and model

“Claude”, “Gemini” or “Copilot” is too coarse. The unit reported must be the
observed combination:

`host product + host version + mode/surface + requested model + resolved model + effort`

Unknown values stay null. In particular:

- Claude ran in the Claude Desktop application’s Cowork/research mode, not
  Claude Code;
- Gemini ran through Antigravity CLI (`agy`), not the older `gemini` CLI; and
- M365 Researcher did not disclose its resolved model.

Without holding the model and other causal factors constant, differences must
not be described as client effects.

### 8. Produced documents are not automatically portable evidence

The M365 source packages contained hidden SharePoint/Outlook relationship
locators, account-specific identifiers and visible enterprise citation labels;
the Claude source package contained MSIP/Purview custom-property metadata.
Those raw packages are retained privately by hash and are not published in Git.
The repository contains only deterministic `-public-sanitized.docx`
derivatives with external link targets and labels redacted, custom properties
removed, author/application properties normalized and embedded media checked.

A LibreOffice review of every sanitized page still found source-layout
limitations: repeated header/body collisions in the access briefing, a
cramped page-spanning options table in the hosting report, and clipping in the
Claude derivative. The manifest records these limitations and binds the
technical public-release review to the derivative hashes. That review is not
formal information-governance clearance. Future evidence ingestion should
apply the same package inspection, rendered-page review and durable-citation
requirements before publication.

## Personas and user journeys

The repository previously had the right ingredients but no canonical
ONS-specific persona contract:

- `evaluation/gold-queries.json` supplied 12 carefully differentiated ONS
  intents;
- the AI harness supplied eight public smoke tasks; and
- sibling OKF Explorer and MCP-Geo repositories supplied generic personas and
  browser journeys.

[`personas-and-journeys.json`](../evaluation/ai-client/personas-and-journeys.json)
now makes six ONS-specific roles explicit:

1. policy and research analyst;
2. government statistician or methodologist;
3. data engineer and MCP integrator;
4. data governance and standards assessor;
5. geography and area analyst; and
6. AI evaluation operator.

They cover eight end-to-end journeys: orientation, candidate reduction,
confusable comparison, exact hydration, standards/quality assessment, MCP plan
preparation, honest recovery and reproducible sharing. Every smoke task and
every gold query is assigned and validated. ONS subject-matter review is still
needed before these are treated as representative of all ONS users.

## MCP delivery by client

The same tool semantics should be used everywhere, but transport and
administration differ.

| Client surface | Viable configuration now | Limitation / next step |
| --- | --- | --- |
| Antigravity CLI (`agy`) | Repository-scoped `.agents/mcp_config.json` starts the local stdio broker | Start AGY from this repository and verify server/tool readiness before a paid/model run |
| Older Gemini CLI | Separate `.gemini/settings.json`; intentionally not modified | Treat as a separate client profile if retained |
| Claude Desktop normal chat | Local stdio server or packaged desktop extension | A local entry can support manual chat trials; package an `.mcpb` for repeatable distribution |
| Claude Desktop Cowork/research | Remote connector | Deploy Streamable HTTP and add it through the connector UI; do not assume the local Desktop config is visible |
| M365 Copilot Researcher in Edge | Admin-deployed federated connector to remote MCP | Requires public HTTPS, read-only tools, Entra SSO or OAuth, admin creation and staged rollout |

Current official documentation supports these distinctions:

- [Antigravity CLI MCP configuration](https://antigravity.google/docs/mcp)
  documents workspace `.agents/mcp_config.json`, stdio `command`/`args`/`cwd`
  and remote `serverUrl`.
- [Claude Desktop local MCP guidance](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop)
  describes local desktop extensions.
- [Claude remote connector guidance](https://support.claude.com/en/articles/11175166-about-custom-integrations-using-remote-mcp)
  distinguishes internet-hosted connectors.
- [Microsoft’s federated connector overview](https://learn.microsoft.com/en-us/microsoft-365/copilot/connectors/federated-connectors-overview)
  states that M365 Copilot fetches through MCP in real time, does not index that
  content, governs connectors through admins, and supports Researcher.
- [Microsoft’s custom federated connector setup](https://learn.microsoft.com/en-us/microsoft-365/copilot/connectors/set-up-custom-federated-connectors)
  requires a read-only remote MCP URL, admin permissions, authentication and a
  staged rollout.

The M365 hosting report’s broader architecture proposal is sound as a work
package hypothesis: keep source control in GitHub, use SharePoint when an
organisation needs governed human publication, use a synced Graph connector
when tenant indexing is the objective, and use federated MCP for live,
non-indexed retrieval. It must not be simplified to “MCP provides full M365
indexing”; Microsoft explicitly separates those modes.

## Evaluation design for OKF efficiency

### Development phase

Run the eight public smoke tasks against the controlled broker first:

1. protocol-baseline replay;
2. AGY;
3. Codex CLI;
4. Claude Code;
5. Claude Desktop manual run; and
6. M365/Claude research modes only after the remote connector is deployed.

Use fresh context for every task. Record readiness before task assignment.
Store no hidden reasoning, credentials or provider-private trace. Bind the
visible answer to an independent assessment.

### Comparative phase

After the broker and capture adapters are stable:

- have ONS subject-matter experts review the personas and author at least 50
  unseen, source-balanced questions;
- preregister arms, host/model cells, repetitions, stopping rule and primary
  outcome;
- run at least three replicates per cell with randomized order;
- enforce access arms rather than relying on prompts;
- blind two assessors to client and arm, with adjudication;
- report blocked readiness separately; and
- publish component metrics, uncertainty and raw normalized records.

The primary outcome remains safe exact selection. Efficiency measures are
secondary outcomes and should be interpreted only among runs that meet the
quality threshold; a fast wrong selection is not an efficiency success.

## Prioritized work packages

### WP0 — completed in this branch: local controlled broker and evidence model

- preserve and normalize the three trials;
- make personas, journeys and issue coverage machine-validatable;
- provide deterministic metadata-only descriptor, search, get, compare, MCP
  plan and answer-submission tools;
- configure AGY at repository scope; and
- test the protocol without live network or paid model calls.

### WP1 — remote parity

- expose the same tool schemas over HTTPS Streamable HTTP;
- add OAuth/Entra authentication without changing read-only semantics;
- log redacted, run-bound tool events and exact response bytes;
- deploy to a non-production test domain; and
- connect Claude research and an M365 staged test user.

### WP2 — controlled runner adapters

- implement native capture adapters for AGY, Codex CLI and Claude Code;
- create a manual import path for GUI clients;
- verify resolved-model and usage telemetry per run;
- enforce network arms and fault profiles; and
- generate one provider-neutral report.

### WP3 — ONS-reviewed confirmatory study

- review the six personas and eight journeys with ONS;
- create hidden, balanced tasks across sources and confusability strata;
- run the preregistered repeated comparison; and
- publish evidence, limitations and remediation backlog without claiming
  statistical accuracy.

## Recommendation

Demonstrate two things together:

1. OKF Explorer gives people a transparent, filterable way to see the corpus,
   alternatives, evidence and geography; and
2. the OKF MCP broker gives agents the same bounded discovery and exact
   selection contract without forcing them to ingest browser shards.

That is a stronger proposition than “another mapping interface”. It makes ONS’s
metadata, distinctions, provenance and standards evidence operational for both
people and agents, while preserving the boundary that the data and statistical
authority remain with ONS.
