# Agent access and multi-client evaluation proposal

> **Historical design note.** This document records the proposal that preceded
> the current local broker and expanded evidence model; future-tense sections
> below are retained to show that design history and are not a current setup
> guide. Use [`mcp-client-rollout.md`](mcp-client-rollout.md) for the canonical
> client-by-client connection status,
> [`ai-client-trial-analysis.md`](ai-client-trial-analysis.md) for the current
> synthesis, and
> [`client-profiles.json`](../evaluation/ai-client/client-profiles.json) for
> the complete machine-readable registry.

## Decision

At the time of this proposal, the Claude Cowork session was strong enough to
justify a focused next work package, but not to claim that OKF improved AI
performance.

The recommended package was:

1. make exact record hydration a first-class, byte-bounded OKF contract;
2. expose the same contract through a small metadata-only MCP broker;
3. run the eight-case development smoke suite across every ready client and
   surface;
4. use those results to preregister a three-arm, at-least-50-question trial.

This sequence tests the central proposition: OKF should help a person or agent
find the exact source-qualified dataset, see plausible alternatives and
quality limitations, and hand an unambiguous plan to MCP without silently
inventing statistical choices.

The preserved Claude research input is
[`2026-07-18-claude-desktop-cowork-fable-5-okf-ons-access-trace.md`](../research/2026-07-18-claude-desktop-cowork-fable-5-okf-ons-access-trace.md).
Its Word derivative, hashes, evidence boundary and later qualifications are
registered in [`research/manifest.json`](../research/manifest.json).

## What the case study establishes

The session provides useful design evidence:

- named overview, analysis and standards entrypoints made orientation cheap;
- the model repeated important metadata-only, accuracy and certification
  caveats;
- a hydrated record carried enough identifiers, dimensions, provenance and
  mapping evidence for a useful standards demonstration;
- alternatives and cross-source reconciliation were available for
  discrimination;
- multi-megabyte JSON resources defeated the client's response cap;
- there was no declared per-record hydration route;
- the browser fallback was unavailable, but partial-file spooling allowed a
  disclosed degraded answer; and
- the successful path needed only public read-only HTTPS and temporary local
  storage.

It does not establish causation, comparative benefit, current model-wide
behaviour, statistical accuracy or independent standards compliance. The
three substantive tasks shared one conversation; there were no control arms;
token counts were estimated; and no native provider export is preserved.

## Corrections discovered during verification

The authoritative Markdown is preserved verbatim as the record of what the
client observed and inferred. A clean rebuild from commit
`502c60e94e53a2acd7d26ebdb5b1b2ae376286f7` identified several later
qualifications:

- dataset chunks are approximately 5.2 to 6.8 MB, not the estimated 0.5 MB;
- the complete doc-map is 333,961 bytes, not the 65,038-character partial
  returned to the client;
- the complete MCP bindings file is 3,037,383 bytes and does include CPIH;
  the reported miss was another consequence of truncation;
- search shards are selected from the first two normalised token characters,
  not a hash; and
- a single flat replacement index would itself exceed common response caps.

Every one of the 4,989 current canonical records can, however, be serialized
individually below 64 KiB:

| Measure | Canonical JSON bytes |
|---|---:|
| Minimum | 5,564 |
| Median | 12,070 |
| 95th percentile | 13,488 |
| 99th percentile | 14,866 |
| Maximum | 30,708 |
| CPIH | 7,131 |
| Records over 65,536 bytes | 0 |

This makes one canonical JSON file per record the simplest P0 correction.

## Traceability from F1–F9

| Finding | Qualified implication | Proposal | Acceptance evidence |
|---|---|---|---|
| F1 overview-first | Supported for orientation, not exact hydration | Add one ordered agent-access entrypoint covering orient, search, exact lookup, hydrate and validate | A no-JavaScript client orients in at most three GETs and never guesses a path |
| F2 honesty transfer | Encouraging n=1 association, not a causal result | Give material caveats stable IDs and inheritance rules | Cross-client caveat-fidelity score plus a stripped-caveat control |
| F3 standards evidence | Supports mapping/alignment demonstration, not certification | Add record JSON-LD, explicit assertion source and evidence pointers; independently test RDF expansion and selected SHACL profiles | Alignment and independent validation remain separate; upstream product certification stays false |
| F4 confusables | Information was available; benefit is unmeasured | Curate expert gold alternatives and keep them visible in reduced candidate sets | Target, alternative-exposure, contrast and non-equivalence scores on at least 50 questions |
| F5 hydration failure | Confirmed and more severe than estimated | Publish one canonical record file and a byte-bounded ID/native-ID/route hydration index | All records resolve; CPIH hydrates under a 64-KiB response cap |
| F6 browser-oriented search | Prefix search exists but is undocumented and multi-step | Add a compact agent-search manifest and prefix result shards containing identity, title, route and record URL | Pure HTTP client finds all smoke targets without JavaScript, range requests or grep |
| F7 fallback chain | Browser failure was client readiness; guessed path was a bundle-contract failure | Declare failure states and an explicit substitution marker | Browser-off, scratch-off and fetch-cap fault tests never allow undisclosed substitution |
| F8 token economics | Plausible, but current figures are estimates over partial payloads | Capture exact bytes, calls, latency and truncation; keep provider tokens and estimates separate | No estimated usage can be labelled exact; replay report is byte-identical |
| F9 minimal access | Sufficient for one host, not universally established | Publish required host, method, authentication and capability profile | GET-only test needs no credential, cookie, POST, browser or remote code |

## P0 OKF agent-access contract

Keep the current 500-row chunks for OKF Explorer compatibility. Add an
orthogonal agent path:

```text
okf-explorer.json
  entrypoints.agent_access
    data/agent/profile.json
    data/agent/search/<prefix>.json
    data/agent/hydration/<prefix>.json
    data/records/<stable-record-name>.json
```

`data/agent/profile.json` should declare:

- profile schema and version;
- ordered orientation entrypoints;
- tokenisation and prefix-shard algorithm;
- exact lookup keys: stable ID, native ID and viewer route;
- canonical record media type, byte limit and digest algorithm;
- security requirements: public GET, no authentication, no cookies, no
  observation values and no secrets;
- optional capabilities: browser, JavaScript, range requests and local
  scratch;
- stable outcome codes such as `not-found`, `ambiguous`,
  `metadata-incomplete` and `hydration-unavailable`;
- stable material-caveat IDs; and
- the fallback order and substitution-disclosure rule.

Each hydration-index row should contain:

```json
{
  "record_id": "ons-data-api:dataset:cpih01",
  "native_id": "cpih01",
  "route": "dataset/ons-data-api-dataset-cpih01",
  "url": "data/records/ons-data-api-dataset-cpih01.json",
  "bytes": 7131,
  "sha256": "..."
}
```

Build gates should establish that:

- every dataset record has exactly one canonical URL;
- every stable ID, native ID and route resolves through the declared index;
- each record is valid complete JSON no larger than 65,536 bytes;
- the recorded byte count and digest match the file;
- no record contains observations, secrets or machine paths;
- CPIH and all smoke-suite records can be found and hydrated by a no-browser
  reference client; and
- legacy Explorer chunks and routes remain unchanged.

NDJSON can be added for streaming bulk use, but it is not a substitute for an
exact record route. A very large flat lexicon or doc-map should not become the
new bottleneck.

## Controlled metadata broker (subsequently implemented locally)

The same access contract was to be exposed by a small read-only MCP/HTTP
broker. Its local stdio form is now implemented with the tool set below. A
remote HTTP deployment is not implemented. Its portable core requires only
`tools/list`, `tools/call` and ordinary JSON results. Resources, Apps,
elicitation, sampling and browser support are useful capability strata, not
prerequisites.

Implemented local tools:

- `okf.descriptor` — return the pinned descriptor and agent profile;
- `okf.search` — return ranked compact candidates and reduced-set
  alternatives;
- `okf.get_record` — hydrate one exact record;
- `okf.compare` — return evidence-backed contrasts;
- `okf.prepare_mcp_plan` — validate an incomplete or complete read-only
  selection hand-off; and
- `okf_eval.submit_answer` — capture the source-qualified selection,
  alternatives, contrasts, evidence pointers, caveats, confidence and visible
  answer in one common schema.

The submission tool avoids making transcript extraction the only evidence
channel. The model submission is evidence, not its own safety assessment. An
independent assessor or validated fixture binds annotations to the visible
answer's SHA-256 and confirms supported caveats, evidence and unsupported
claims. The broker must not collect hidden reasoning. No ONS or OS API key is
needed for this metadata-only broker.

## Current harness

The committed harness is deliberately provider-neutral and safe in CI:

- [`study.json`](../evaluation/ai-client/study.json) pins the bundle, three
  arms, delivery modes and study boundaries;
- [`tasks.json`](../evaluation/ai-client/tasks.json) defines eight public smoke
  tasks;
- [`expected.json`](../evaluation/ai-client/expected.json) contains public
  development gold and caveat IDs;
- [`client-profiles.json`](../evaluation/ai-client/client-profiles.json)
  distinguishes readiness, automation and capability evidence;
- [`personas-and-journeys.json`](../evaluation/ai-client/personas-and-journeys.json)
  connects six ONS-specific personas and eight journeys to every smoke task and
  confusable gold query;
- [`issue-register.json`](../evaluation/ai-client/issue-register.json) maps the
  observed Claude, Gemini and M365 failure modes to remediations and tests;
- [`claude-desktop-cowork-fable-5-20260718.json`](../evaluation/ai-client/evidence/claude-desktop-cowork-fable-5-20260718.json)
  plus the Gemini and M365 observation records map the preserved trials into
  the harness without treating them as controlled scores; and
- [`ai_evaluation.py`](../src/okf_ons/ai_evaluation.py) validates inputs and
  public runs, creates run templates, scores components and builds
  deterministic reports.

Run it with:

```bash
python3 scripts/ai_client_harness.py validate
python3 scripts/ai_client_harness.py validate-research
python3 scripts/ai_client_harness.py clients --initial-only
python3 scripts/ai_client_harness.py probe-clients
python3 scripts/ai_client_harness.py tasks
```

`probe-clients` performs only local installation and version checks. It does
not authenticate, call a model or claim that a client is ready.

Create an unstarted capture record:

```bash
python3 scripts/ai_client_harness.py init-run \
  --run-id codex-cli-okf-ai003-r1 \
  --client codex-cli \
  --arm okf-bundle \
  --delivery-mode controlled-broker \
  --task AI-SMOKE-003 \
  --replicate 1 \
  --output evaluation/ai-client/local/codex-cli-okf-ai003-r1.json
```

After capture or manual import:

```bash
python3 scripts/ai_client_harness.py score \
  --run evaluation/ai-client/local/codex-cli-okf-ai003-r1.json

python3 scripts/ai_client_harness.py report \
  --runs evaluation/ai-client/local/*.json \
  --output evaluation/ai-client/local/report.json
```

Local runs and native provider exports must remain ignored. Public normalized
runs may be promoted only after redaction and review.

The scorer records:

- exact stable record, native ID, source, edition and version;
- exact-record hydration;
- alternative exposure and required contrasts;
- caveat and evidence coverage;
- MCP plan completeness;
- disclosed substitution;
- critical and total unsupported claims; and
- the strict `safe-exact-selection` outcome.

Readiness `blocked` and `not-run` outcomes are kept in reports but excluded
from quality denominators. A task that begins and then fails is a task failure,
not a readiness exclusion. Arm violations invalidate the comparison while
remaining visible. Client-declared caveat IDs and safety labels do not earn
credit by themselves; the separate assessment record must support them from
the visible answer.

Only network/tool-enforced arm runs enter comparative denominators. Observed
and self-reported access remains visible in a descriptive aggregate. Fixture
replays enter a separate validation aggregate and can never enter a comparative
denominator. A task fault profile, such as the 64-KiB/no-browser case, is bound
into the run record and must include enforcement evidence; arm enforcement
likewise carries the exact pinned policy and evidence. Otherwise the run is
excluded rather than allowed to pass under unconstrained access. MCP plans are
checked against the expected source-qualified record, tools, identity
arguments, unresolved dimensions, credential prohibition and non-execution
rule. Enforcement evidence is a hash-verified repository-relative trace with
enforcer identity and version, subject-policy digest, redirect checks and
per-rule results. Each trace is also bound to the exact run ID, client profile,
access arm and digest of the captured response; a reusable fixture or non-empty
placeholder cannot make a run comparative.

Assessment methods are restricted to validated fixtures, independent blind
human review and adjudication. The assessment carries an independent
provenance digest, and every credited caveat/evidence item or unsupported
claim has a quoted span in the digest-bound visible answer. MCP non-execution
is derived from the normalized event trace, not accepted solely from the
model's `executed` field.

Usage values carry a value or range, unit, exactness, source and scope.
Unknown is not zero. Estimated values cannot be relabelled exact. Reports
contain no generated timestamp and are byte-identical for the same normalized
inputs.

## Client and host matrix

Client, host surface and model must be recorded separately. A result is named
for the exact host/model combination; it is not a “client effect” when host
and model change together.

This section records the evaluation design, not current connection
instructions. The rollout guide is the current source for connection routes
and explicitly covers all profile IDs, including the installed-but-unverified
ChatGPT, Microsoft Copilot and GitHub Copilot candidates.

### Initial smoke-suite tracks

| Profile | Surface | Capture route | Current status |
|---|---|---|---|
| Codex CLI | Command line | Unattended JSONL, structured answer and MCP trace | Previously ready; fresh probe required |
| Claude Code | Command line | Unattended stream JSON, structured answer, usage and MCP trace | Previously ready; fresh probe required |
| Antigravity CLI (`agy`) | Command line | Repository-scoped MCP, structured answer, trace and usage when exposed | AGY 1.1.4 installed; fresh MCP/model probe required |
| Gemini CLI | Command line | Separate legacy-client track | Installed but not configured for the initial suite |
| VS Code Agent | Desktop IDE | Experimental isolated-window runner, submit tool and MCP trace | Fresh memory/cleanup probe required |
| Claude Cowork | Research-preview desktop | Manual native export or contemporaneous log | Historical trace only |
| Claude Desktop | Desktop | Manual transcript plus submit tool and MCP trace | Local broker implemented; app connection probe required |
| Codex Desktop | Desktop | Manual transcript plus submit tool and MCP trace | Manual path available |
| M365 Copilot Researcher | Edge research agent | Manual export plus remote MCP trace when enabled | Admin-deployed federated connector required |
| MCP Inspector | Protocol baseline | Deterministic MCP trace and submit tool | Probe required; not an AI-quality comparator |

The unattended implementation should reuse the readiness, trace, blocker and
cleanup patterns already proven in
[`mcp-geo`](https://github.com/chris-page-gov/mcp-geo), while keeping the
OKF study and scoring provider-neutral.

### Readiness candidates

ChatGPT Classic, ChatGPT Atlas, Microsoft Copilot, Microsoft 365 Copilot,
GitHub Copilot and GitHub Copilot for Xcode are installed candidates. They
remain readiness-only until authentication, model identity, arm enforcement
and a repeatable evidence export are demonstrated. Installation is not a
successful test. Their inclusion in the registry does not prove that the local
stdio broker has been connected to them, even where a compatible setup route is
documented.

## Three access arms

Each arm is a set of explicit origin plus path-prefix pairs, not prompt
wording:

1. **OKF bundle** — only the pinned OKF-ONS Pages path.
2. **Open web** — ordinary search and public pages, denying both OKF-ONS and
   raw catalogue APIs.
3. **Raw API** — the registered ONS Data API, Nomis and Open Geography API
   roots, denying OKF and generic search.

Prompt-only restrictions are `self-reported`, never `enforced`, and do not
enter comparative denominators. Redirects and tool-mediated access must be
checked against the same origin/path pairs. Each task starts with a fresh
context.

Two delivery modes answer different questions:

- **native access** measures the ecological effect of each host's real fetch,
  browser, JavaScript and spooling behaviour; and
- **controlled broker** holds the metadata access interface constant across
  MCP-capable hosts.

## From smoke suite to confirmatory trial

The eight public tasks reproduce the main case-study paths: orientation,
standards claim safety, exact CPIH hydration, cross-source confusables, UV042
provenance, MCP hand-off, a 64-KiB/no-browser fault case and substitution
integrity. They are regression tests, not unseen research questions.

Before a confirmatory claim:

1. curate at least 50 real questions with ONS/GSS subject experts;
2. include easy, confusable, revision-sensitive, cross-source, geographic and
   valid-abstention cases;
3. keep intended answers and the rubric private;
4. commit their digests in a preregistration before collection;
5. run every client/arm/task cell at least three times with randomized order;
6. freeze runs before revealing gold;
7. use two independently blinded assessors and adjudicate disagreements;
8. report uncertainty and missing-telemetry denominators; and
9. compare arms within host/model strata rather than publishing an
   unqualified provider leaderboard.

Primary outcome:

> Correct source-qualified target, required edition/version where applicable,
> material caveats retained, and no critical unsupported claim.

Report its components separately: retrieval, exact identity, hydration,
alternative exposure, contrast, caveat fidelity, provenance and citation
validity, standards-claim calibration, hallucinations, MCP-plan validity,
calls, bytes, latency and exact tokens where available.

## Original follow-up work packages and current position

| Package | Current position | Remaining exit gate |
|---|---|---|
| WP1 agent access | Static per-record files and byte-bounded hydration/search indexes are not implemented | CPIH and all smoke records hydrate natively without browser or scratch under 64 KiB |
| WP2 neutral broker | Local metadata-only stdio tools for descriptor, search, get, compare, plan and submit are implemented and protocol-tested | Add a controlled client run; remote HTTP parity remains a separate deployment |
| WP3 all-client smoke | Complete 16-profile registry, readiness model, public tasks and manual/automated capture contracts are implemented | Run or explicitly block every preregistered profile with no silent exclusions |
| WP4 confirmatory design | Six personas, eight journeys and 12 development gold queries are public regression inputs | Add subject-reviewed ≥50-question private gold, preregistration and blind-review pack |
| WP5 comparative trial | Not run | Complete three enforced arms, at least three replicates per cell and an adjudicated report |

WP1 should be implemented before interpreting current cross-client hydration
differences in the native static-bundle arm. The local broker provides a
controlled bounded-access arm, but neither route by itself is evidence that
OKF improves AI performance.
