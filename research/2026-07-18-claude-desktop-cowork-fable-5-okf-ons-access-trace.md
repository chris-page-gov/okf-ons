# Briefing-note input: AI access to an Open Knowledge Format bundle (okf-ons)

| Field | Detail |
|---|---|
| **Subject** | Case-study evidence: a frontier AI model (Claude Fable 5) discovering and using ONS metadata through an Open Knowledge Format (OKF) bundle |
| **Prepared** | 18 July 2026, 05:55 UTC (contemporaneous with the recorded session) |
| **Prepared by** | Claude Fable 5 (model string `claude-fable-5`), operating in Anthropic Cowork (research preview), at the direction of Chris Page |
| **Status** | Input material for a briefing note; not itself a cleared briefing |
| **Suggested handling** | OFFICIAL. All source material is public and OGL v3 licensed |
| **Evidence base** | One live session, 18 July 2026; full interaction log at Appendix A |

---

## 1. Purpose

This paper provides the factual input a civil servant needs to (a) assess the utility of Open Knowledge Format (OKF) bundles as an interface between AI assistants and official statistics metadata, and (b) design further research to establish that utility rigorously. It records, contemporaneously and verbatim where possible, a single end-to-end session in which an AI model was pointed at the `okf-ons` bundle and asked to brief on it, assess its standards compliance, and demonstrate DCAT 3 and PROV-O conformance on a real record. Everything the assessment needs — every call made, every payload size, every failure, and the access the AI required — is logged in the appendices.

## 2. Summary of findings

The bundle worked as designed for orientation and grounding: three small fetches gave the AI an accurate, caveated picture of a 4,989-record corpus, and the AI relayed the bundle's own honesty markers ("metadata-only", "alignment not certification", "accuracy not evaluated") unprompted in every answer. Record-level evidence was rich enough to demonstrate DCAT 3 and PROV-O mappings field-by-field from a fully hydrated record, using the bundle's own machine-readable ontology crosswalk as the normative reference.

The friction was infrastructural, not conceptual. The bundle's data chunks (~0.5 MB each, estimated) exceeded the AI harness's ~92–95 KB per-fetch limit; there was no per-record URL (a probe returned empty); the search lexicon is sharded for a browser worker and is impractical for a non-JS agent; and a fallback to browser rendering failed because the Chrome extension was disconnected. The AI completed all tasks anyway, by grepping partially fetched chunks — but it reached the *flagship* record it wanted (CPIH) only as an identifier, and substituted a Census record it could fully hydrate. Roughly 504 KB of oversized payloads were handled at an estimated context cost of under ~6,000 tokens because the harness diverted them to local files for selective search — a pattern worth designing for.

Net assessment offered for consideration: OKF bundles show real promise for safe, cheap, well-grounded AI access to official metadata; the single-session evidence also yields a concrete agent-accessibility design checklist and a testable research design (Section 8).

## 3. Background

**Open Knowledge Format.** OKF is an emerging packaging convention: a single self-describing JSON bundle (`okf-explorer.json`) that declares its scope, counts, licence, provenance, entrypoints, extensions and vocabulary, and links to sharded data files that viewers and agents hydrate lazily. The instance studied is `okf-ons` ("ONS data discovery OKF", v0.1.0, snapshot `monday-2026-07-17`), published by github.com/chris-page-gov and rendered by a static explorer application. It describes itself as a "metadata-only ONS discovery demonstrator" — a bounded demonstrator, explicitly not the complete ONS corpus.

**Contents.** 4,989 ONS metadata records from three official catalogues — ONS Open Geography (3,035), Nomis (1,617), ONS Data API (337) — with 19,570 typed relationships, confusable-alternative warnings on 4,931 records, a 34-standard evidence register (42 requirements), a cross-source reconciliation report (283 matched census table codes, 3 title conflicts, 1 unmatched anchor), read-only MCP selection bindings, and a static sharded search index. Licence: Open Government Licence v3. Source snapshot SHA-256 is pinned in the bundle root.

**Why this matters to departments.** Departments are deploying AI assistants that will be asked "which official dataset answers X?". Today those assistants improvise over web search. An OKF bundle offers a governed alternative: a versioned, licensed, provenance-pinned, self-caveating catalogue an AI can ground itself in — without credentials, without touching data values, and without the publisher operating live infrastructure (the whole bundle is static files).

## 4. The case study: what happened

One session, three user tasks, in sequence. The AI had no prior knowledge of this bundle (its training cutoff is May 2025; the bundle is dated 17 July 2026), so everything below was learned live from fetches recorded in Appendix A.

**Task 1 — orient.** Asked to load the bundle and stand ready. Three fetches (bundle root, overview index, analysis overview — all under ~15 KB) yielded the corpus shape, counts, source split, self-declared caveats, and the bundle's own evaluation metrics (MRR 0.35; recall@10 0.417; nDCG@10 0.366; standards coverage 0.315; metadata evidence completeness 0.193).

**Task 2 — standards briefing.** Asked whether the artefact is compliant with UK government standards. One fetch (the standards evaluation entrypoint, ~13 KB) returned the full 34-standard register spanning binding legislation (Statistics and Registration Service Act 2007, Data Protection Act 2018, Accessibility Regulations 2018, INSPIRE 2009), the statutory Code of Practice for Statistics 3.0, cross-government standards and guidance (GovS 010, Aqua Book, RAP Strategy, Data Quality Framework, GDS API standards, UK DCAT-3 profile, GEMINI 2.3), and W3C/international standards (DCAT 3, SKOS, PROV-O, DQV, RDF Data Cube, CSVW, SDMX 3.1, GSBPM 5.2, GSIM 2.0, DDI, ISO 19115-1, ISO 19157-1). The AI reported the bundle's own verdict accurately: profile alignment "partial"; "evidence mapping and profile alignment; not certification"; statistical accuracy not evaluated.

**Task 3 — demonstrate DCAT 3 and PROV-O on a key statistic.** This surfaced both the strengths and the frictions:

1. The AI fetched the data manifest and the ontology crosswalk (the bundle's normative field-by-field mapping to DCAT, PROV-O, SKOS, SDMX, Data Cube, DQV, CSVW and others) — both inline, no difficulty.
2. It located CPIH (the flagship inflation measure) by grepping the searchable doc-map: `"1639": "dataset/ons-data-api-dataset-cpih01"`.
3. It then failed to hydrate the CPIH record: the containing chunk (`datasets-3.json`) truncated at 94,577 characters mid-JSON under the harness's fetch cap; a guessed per-record URL returned an empty body; and four browser-tool calls failed because the Chrome extension was not connected.
4. It recovered by working with what the truncated chunk did contain: a complete record for Census table UV042 ("Accommodation type (people)", Nomis `NM_1662_1`), including its provenance block, SDMX dimension list, licence, per-record quality-evidence scorecard (6 of 14 evidence items present, band "low"), and a per-record standards-evidence block self-declaring `dcat-3: aligned` (mapped type `dcat:Dataset`) and `prov-o: aligned`.
5. It presented field-to-term mapping tables and a Turtle rendering, using the crosswalk as authority, and disclosed the CPIH substitution and the record's declared weaknesses.

Appendix C reproduces the record extract and mappings; Appendix A logs every call.

## 5. Findings

**F1 — Overview-first design works for agents.** Orientation cost three calls and roughly 3,000 estimated tokens of payload. The bundle's `entrypoints` map meant no crawling and no guesswork; each subsequent question mapped to one named entrypoint.

**F2 — The honesty architecture transferred.** The bundle embeds caveats at every level (bundle root scope flags, per-file warnings, per-record `warning` strings). In all three answers the AI repeated the material caveats without being asked. This is the behaviour a department wants from an assistant citing official statistics, and here it was induced by the data format rather than by prompt engineering.

**F3 — Record-level evidence is deep enough for standards demonstration.** A single hydrated record carried everything needed to demonstrate DCAT 3 and PROV-O conformance concretely: native identifiers, licence URIs, publisher, endpoint URL and protocols, five SDMX dimensions with codelists, a digest-pinned provenance block (source URL, SHA-256, retrieval timestamp, snapshot ID), and a self-assessment distinguishing "aligned" from "partial" per standard.

**F4 — Confusables and reconciliation add discriminating power.** The hydrated record exposed four confusable alternatives with explicit field-level differences; the reconciliation report showed 283 cross-source code matches with 3 title conflicts named. This is exactly the information an assistant needs to avoid the classic failure of confidently citing the wrong near-duplicate dataset.

**F5 — Chunk granularity defeated record hydration (the main friction).** Data chunks of roughly 0.5 MB (estimated from 4,989 records across 10 files) sat far above the harness's ~92–95 KB fetch ceiling. Three chunk fetches truncated mid-JSON (confirmed by inspecting file tails). There is no per-record endpoint and no record→chunk index, so a targeted record fetch is impossible without either full-chunk access or executing the explorer's JavaScript.

**F6 — The search index assumes a browser.** The lexicon is sharded by hashed token prefix for a web worker. A plain-string grep over it found nothing; the flat doc-map, by contrast, was immediately greppable and productive. For agents, one flat title/route index outperforms a clever sharded index.

**F7 — Fallback chains matter and were exercised.** web_fetch cap → local-file grep worked; browser rendering → failed (extension disconnected); guessed per-record URL → failed (empty response). The task still completed, degraded gracefully (CPIH identified but not hydrated; UV042 substituted with disclosure).

**F8 — The token economics are favourable.** Approximately 504 KB of oversized payloads were diverted to local files and interrogated with targeted searches; the estimated total context consumed by all bundle material across the session is ~19,000–24,000 tokens (method and per-call figures in Appendix B). The design lesson: agent-side spooling plus selective read makes even oversized bundles cheap, but only because the payloads were plain, greppable JSON.

**F9 — Minimal access was sufficient.** The entire evidence-gathering exercise required only unauthenticated, read-only HTTPS GET to one public static host, plus a local scratch filesystem. No credentials, no cookies, no personal data, no write access to anything external, no execution of remote code. Appendix E gives the full access profile including the failed/unneeded browser permission.

## 6. Assessment against UK standards and best practice

For the assessing civil servant, three distinct compliance questions should be kept separate — the bundle itself keeps them separate, which is to its credit:

**(a) Does the bundle correctly *register* the applicable landscape?** Yes, and unusually thoroughly: 34 standards across binding legislation, statutory code, official guidance and technical recommendations (full register at Appendix D), each with canonical URI, normative status and requirement count. Notably current: it cites Code of Practice 3.0 (October 2025) and its May 2026 public-use standards, GovS 010 (August 2025 update), and DCAT 3.

**(b) Does the bundle *conform*?** Self-assessed as "partial" overall, "aligned" for specific vocabularies per record (DCAT 3 and PROV-O both "aligned" on the examined record, with every crosswalk mapping evidenced by an actual populated field). Weaknesses are declared in numbers: methodology links on only 9 of 4,989 records; quality documentation links on 49; metadata evidence completeness 19.3%; standards coverage 31.5%. The examined record scored 6/14 on evidence availability, band "low". No claim of certification is made anywhere; the bundle states "not certification of ONS products or legal compliance".

**(c) Is the *practice* of publishing it aligned with government best practice?** The design choices — OGL v3 licensing, pinned SHA-256 provenance, explicit scope limits, machine-readable caveats, separation of evidence from accuracy claims ("evidence availability does not establish the accuracy of observations") — are consistent with intelligent-transparency expectations under the Code of Practice and with the spirit of the AQuA Book's emphasis on uncertainty communication. This paper makes no legal-compliance determination (e.g. accessibility regulations apply to the explorer web application and would need a WCAG audit outside this session's scope).

## 7. Limitations of this evidence

This is a single session, by a single model, over a single bundle, initiated by the bundle's own author — a best-case, cooperative scenario, not an adversarial or comparative trial. Specific limitations: (i) n=1 throughout, no baseline arm; (ii) token figures are estimates reconstructed from reported character counts, not billing-grade telemetry (method stated in Appendix B; exact counts exist in platform usage logs and should be used in any formal study); (iii) the AI verified conformance *as declared by the bundle's own crosswalk and evidence blocks* — it did not independently validate the RDF against W3C shapes; (iv) the flagship record (CPIH) was never fully hydrated, so the worked example is a Census table of lower salience; (v) alignment statuses are self-assessments by the bundle publisher; (vi) the assessor should note the AI's knowledge cutoff (May 2025) means all post-cutoff standards facts in Section 6 rest on the bundle's register, not on independent verification of, e.g., Code of Practice 3.0's content.

## 8. Design for further research

The natural next step is a controlled utility trial. The following design is offered as input:

**Research questions.** RQ1: Does OKF-mediated access improve an AI assistant's dataset-selection accuracy over status-quo access (ONS website search, raw source APIs, generic web search)? RQ2: Does it increase caveat fidelity (rate at which material caveats are relayed to the user)? RQ3: What does it cost (tokens, calls, latency) per correctly answered discovery question? RQ4: How robust is access across agent harnesses with different fetch caps, JS capability and file-spooling behaviour?

**Method.** Pre-registered task battery of ≥50 real discovery questions drawn from GSS user-need evidence, spanning easy, confusable-pair, and cross-source cases (the bundle's reconciliation report is a ready-made source of confusable pairs, e.g. the RM166/RM181 title conflicts). Three arms per task: (A) bundle-grounded agent, (B) open-web agent, (C) raw-API agent. Blind human scoring against a rubric: correct dataset identified; correct version/source; caveats relayed; hallucinated claims. Instrument exact token/call counts from platform logs. Report against the bundle's own baseline metrics (MRR 0.35, recall@10 0.417) to test whether an agentic consumer beats the static retrieval evaluation.

**Bundle design changes to test (from this session's evidence).** Per-record JSON endpoints or chunks ≤64 KB; a flat record→chunk (or route→URL) index; a plain-token flat lexicon alongside the sharded one; NDJSON chunk variants to make partial fetches valid; an explicit "agent profile" section in the bundle root declaring these affordances. Each is directly traceable to a logged failure in Appendix A.

**Governance of the study.** AQuA Book-compliant analysis plan; RAP for the evaluation pipeline; publication under OGL; engagement with ONS/UKSA (as the metadata's owner), CDDO (metadata exchange model alignment) and AISI/DSIT (agent-safety framing). Data protection screening is expected to be trivial (public metadata only) but should be recorded.

**Decision the briefing note should seek.** Approval for a small, time-boxed comparative trial as above, with a stop/go review against RQ1–RQ3 results.

---

# Appendices — contemporaneous evidence

*Compiled 18 July 2026 05:55 UTC from the session transcript. Timings for the six oversized fetches are exact, recovered from epoch-millisecond identifiers assigned by the harness when spooling payloads to disk; other calls are logged in order but were not individually timestamped by the tooling.*

## Appendix A — Full interaction log

Session: Anthropic Cowork (research preview), model `claude-fable-5`, sandboxed Linux workspace, working folder `Claude-Cowork/Research`. All URLs below are under `https://chris-page-gov.github.io/okf-ons/` unless stated. "→ file" means the harness auto-spooled an oversized result to a local file for selective reading; payload character/line counts for those are exact as reported by the tool.

### A.1 User task 1 — "link to the explorer and make use of the package"

| # | Tool | Target / action | Result |
|---|---|---|---|
| 1 | web_fetch | `okf-explorer.json` (bundle root) | Success, inline (~3.3 KB est.). Counts, entrypoints, extensions, scope, licence, snapshot SHA-256 |
| 2 | web_fetch | `data/overview.json` | Success, inline (~0.9 KB est.). Record-type and source counts |
| 3 | web_fetch | `data/analysis/overview.json` (parallel with #2) | Success, inline (~1.7 KB est.). Evaluation metrics, evidence denominators, reconciliation summary |

### A.2 User task 2 — standards briefing

| # | Tool | Target / action | Result |
|---|---|---|---|
| 4 | web_fetch | `data/standards/evaluation.json` | Success, inline (~13 KB est.). 34-standard register, 42 requirements, alignment claim, evidence availability |

### A.3 User task 3 — key statistic + DCAT 3 / PROV-O demonstration

| # | Tool | Target / action | Result |
|---|---|---|---|
| 5 | web_fetch | `data/manifest.json` | Success, inline (~3.7 KB est.). 10 dataset chunks, 40 relationship chunks, 10 resource chunks |
| 6 | web_fetch | `data/standards/ontology-crosswalk.json` (parallel with #5) | Success, inline (~20 KB est.). Normative field→term mappings incl. DCAT 3, PROV-O; relationship policy; namespaces |
| 7 | web_fetch | `data/search/manifest.json` | Oversize → file. **75,391 chars / 1,830 lines**, spooled **05:32:30 UTC** |
| 8 | Grep | spooled search manifest for `cpih\|unemployment` | 0 matches (lexicon sharded by hashed prefix — F6) |
| 9 | Read | spooled search manifest, first 80 lines | Structure: doc-map, filter postings, hex-sharded lexicon |
| 10 | web_fetch | `data/search/doc-map.json` | Oversize → file. **65,038 chars / 1,267 lines**, spooled **05:32:48 UTC** |
| 11 | Grep | doc-map for `cpih` | **1 match, line 718**: `"1639": "dataset/ons-data-api-dataset-cpih01"` — CPIH located |
| 12 | web_fetch | `data/datasets-3.json` | Oversize → file. **94,577 chars / 3,325 lines**, spooled **05:33:04 UTC**. Later confirmed truncated mid-JSON |
| 13 | Grep | chunk 3 for `cpih01` | 0 matches (record lies beyond truncation point) |
| 14 | Grep | chunk 3 for `"id": "dataset/` | 0 matches (ID scheme differs: `nomis:dataset:NM_…`) |
| 15 | Read | chunk 3, first 60 lines | Nomis census records with alternatives arrays |
| 16 | Grep (count) | chunk 3 for `"source_surface": "ons-data-api"` | 3 occurrences (as alternatives only) |
| 17 | web_fetch | `data/datasets-4.json` | Oversize → file. **92,319 chars / 2,679 lines**, spooled **05:33:43 UTC**. Truncated |
| 18 | Grep | chunk 4 for `cpih01` | 0 matches |
| 19 | bash | locate spooled files in sandbox | 4 files found under session mount |
| 20 | bash | `tail` of chunk 4 file | **Truncation confirmed**: payload ends mid-string (`"source_surface": "o`) |
| 21 | web_fetch | `data/records/ons-data-api-dataset-cpih01.json` (probe for per-record endpoint) | **Empty body** (no such resource) — F5 |
| 22 | ToolSearch | load 5 Chrome browser tools | Loaded |
| 23 | navigate (Chrome) | explorer record page for cpih01 | **Failed**: extension lookup timeout (8 s) |
| 24–25 | tabs_context (Chrome) ×2 | create tab group | **Failed ×2**: "Claude in Chrome is not connected" |
| 26 | web_fetch | `data/ons/mcp-bindings.json` | Oversize → file. **84,170 chars / 2,643 lines**, spooled **05:35:12 UTC** |
| 27 | web_fetch | `data/reconciliation/report.json` (parallel with #26) | Success, inline (~8 KB est.). 283 matched codes, 13 disambiguations, 3 title conflicts, 1 unmatched anchor |
| 28 | Grep | mcp-bindings for `cpih` | 0 matches (central bindings file does not cover cpih01; per-record `selection` blocks exist instead) |
| 29 | tabs_context (Chrome) | third retry | **Failed**: still not connected. Browser route abandoned |
| 30 | Grep | chunk 3 for census-table titles | QS401EW/UK, RM207, QS112, QS611/613, TS041 present as alternative entries |
| 31 | Grep | chunk 3 for top-level `route/title/id` fields | Complete records identified: NM_1662_1 (UV042), NM_1663_1 (UV043 Tenure), NM_1664–1670… |
| 32 | Read | chunk 3, lines 234–413 | **Full UV042 record captured** (reproduced at Appendix C) |
| 33 | Grep | chunk 4 top-level titles | ONS Open Geography records (Cancer Alliances boundaries) — chunk ordering established |
| 34 | web_fetch | `data/datasets-0.json` | Oversize → file. **92,315 chars / 3,241 lines**, spooled **05:36:51 UTC**. Truncated |
| 35 | Grep | chunk 0 top-level titles/ids | 1981/1991 census records; per-source title-sort ordering confirmed; CPIH confirmed unreachable within caps |

### A.4 User task 4 — this document

AskUserQuestion (format: user chose "Both"); ToolSearch (task tools); TaskCreate ×4; bash (UTC clock read and epoch conversions verifying the six timestamps above); document writes; docx build per the docx skill. These calls produced no new bundle evidence and are logged here only for completeness.

### A.5 Failure summary

| Failure | Count | Consequence | Design lesson |
|---|---|---|---|
| Fetch truncation at ~92–95 KB on dataset chunks | 3 (chunks 0, 3, 4) | CPIH record unreachable; substituted UV042 | Chunks ≤64 KB or per-record endpoints |
| Per-record URL probe empty | 1 | No targeted hydration path | Publish per-record JSON or a route→URL index |
| Search lexicon not plain-greppable | 1 | Search index unusable without JS | Ship a flat lexicon/title index |
| Chrome extension disconnected | 4 calls | Browser-rendering fallback unavailable | Agents cannot assume a browser; static JSON must suffice |

## Appendix B — Resource-cost estimates

**Method.** The model cannot observe exact token counts; platform usage logs hold ground truth and should be used in any formal study. Estimates below use exact character counts where the tooling reported them (the six spooled payloads) and visual size estimates (±20%) for inline payloads, converted at ~4 characters/token (typical for JSON in Claude tokenisers).

### B.1 Bundle payloads brought into context (inline fetches)

| Payload | Size (est.) | Est. tokens |
|---|---|---|
| Bundle root | ~3.3 KB | ~830 |
| Overview index | ~0.9 KB | ~230 |
| Analysis overview | ~1.7 KB | ~430 |
| Standards evaluation | ~13 KB | ~3,300 |
| Data manifest | ~3.7 KB | ~930 |
| Ontology crosswalk | ~20 KB | ~5,000 |
| Reconciliation report | ~8 KB | ~2,000 |
| **Subtotal inline** | **~51 KB** | **~12,700** |

### B.2 Oversized payloads spooled to disk (exact sizes; only fragments entered context)

| Payload | Exact chars | Entered context |
|---|---|---|
| Search manifest | 75,391 | ~80 lines read + grep outputs |
| Doc-map | 65,038 | 1 grep line (the CPIH hit) |
| datasets-3.json (truncated) | 94,577 | ~240 lines read + grep outputs |
| datasets-4.json (truncated) | 92,319 | grep outputs + 300-char tail |
| mcp-bindings.json | 84,170 | 0 lines (grep miss only) |
| datasets-0.json (truncated) | 92,315 | grep outputs (~10 lines) |
| **Total spooled** | **503,810 chars (~504 KB)** | **est. ~4,000–6,000 tokens** (selective reads + ~6 spool notices) |

### B.3 Call totals (bundle-evidence phase, tasks 1–3)

| Tool | Calls | Notes |
|---|---|---|
| web_fetch | 14 | 7 inline successes, 6 oversize→file (3 of them truncated), 1 empty probe |
| Grep | 11 | 10 informative (incl. 1 decisive: the CPIH locate) |
| Read | 3 | 320 lines total from spooled files |
| bash | 2 | file location; truncation confirmation |
| ToolSearch | 1 | browser toolset load |
| Browser (Chrome) | 4 | all failed — extension disconnected |
| **Total** | **35** | across 3 user tasks; zero retries wasted on refetching same URL at same cap |

**Headline economics (estimate).** All bundle material consumed across three substantive user tasks ≈ 19,000–24,000 tokens of context (sum of B.1 ≈ 12,700, B.2 ≈ 4,000–6,000, ~2,100 of spool notices, plus tool-call overhead), ≈ 555 KB fetched, 35 tool calls, ~4.5 minutes of tool-active time for the heaviest task (05:32:30–05:36:51 UTC). No authentication, no paid API, no server-side compute for the publisher beyond static hosting.

## Appendix C — Worked example: UV042 record, DCAT 3 and PROV-O mappings

Record `dataset/nomis-dataset-nm-1662-1` (Nomis `NM_1662_1`, Census 2001 univariate table UV042 "Accommodation type (people)"), hydrated in full from `datasets-3.json` lines 234–409 of the spooled copy. Key verbatim fields:

```json
"id": "nomis:dataset:NM_1662_1",
"license_title": "Open Government Licence v3.0",
"metadata_evidence_band": "low",
"native_id": "NM_1662_1",
"provenance": {
  "native_id": "NM_1662_1",
  "retrieved_at": "2026-07-17T19:22:49.006464Z",
  "schema": "okf-provenance.v1",
  "snapshot_id": "monday-2026-07-17",
  "source_adapter": "nomis",
  "source_id": "nomis-dataset-definitions",
  "source_sha256": "90923b56f25118e4430b1107be07c73d1fe1d9df63965723fba92410c90db4c0",
  "source_url": "https://www.nomisweb.co.uk/api/v01/dataset/def.sdmx.json"
},
"publisher_title": "Office for National Statistics",
"quality_evidence": { "possible": 14, "present": 6, "score": 0.429,
  "warning": "This score measures discoverable metadata evidence. It does not certify statistical accuracy, methodological quality, or fitness for use." },
"standards_evidence": {
  "claims_are_alignment_not_certification": true,
  "code-of-practice-3.0": { "evidence": { "quality": false, "trustworthiness": true, "value": true }, "status": "partial" },
  "data-cube": { "status": "partial" },
  "dcat-3": { "evidence": true, "mapped_type": "dcat:Dataset", "status": "aligned" },
  "dqv": { "status": "partial" },
  "prov-o": { "evidence": true, "status": "aligned" },
  "sdmx": { "status": "aligned" }
},
"title": "UV042 - Accommodation type (people)",
"unit_of_measure": "Persons",
"url": "https://www.nomisweb.co.uk/api/v01/dataset/NM_1662_1.overview.json"
```

**DCAT 3 mapping** (authority: the bundle's ontology crosswalk, `okf-ons.ontology-crosswalk.v1`):

| Record field (value) | DCAT 3 / DCTERMS term | Crosswalk kind |
|---|---|---|
| record_type "Nomis Dataset" | `dcat:Dataset` | conditional (class per record layer) |
| native_id "NM_1662_1" | `dct:identifier` | direct |
| title | `dct:title` | direct |
| notes "All Households" | `dct:description` | direct |
| publisher "Office for National Statistics" | `dct:publisher` | direct |
| license OGL v3.0 | `dct:license` | direct |
| url + protocol ["SDMX","REST/HTTP"] | `dcat:DataService` / `dcat:endpointURL` | direct |
| metadata_modified 2003-08-30 | `dct:modified` | direct |
| 4 alternatives with field-level differences | `dct:relation` / `dcat:qualifiedRelation` | structural |

**PROV-O mapping** (provenance block present on all 4,989 records):

| Provenance field (value) | PROV-O term |
|---|---|
| the record | `prov:Entity` |
| source_url (Nomis SDMX definitions endpoint) | `prov:hadPrimarySource` |
| source_sha256 `90923b56…` | `prov:wasDerivedFrom` (digest-pinned entity) |
| snapshot harvest `monday-2026-07-17` | `prov:Activity` |
| retrieved_at 2026-07-17T19:22:49Z | `prov:generatedAtTime` |
| ONS (publisher) / nomis adapter | `prov:Agent` / `prov:wasAssociatedWith` |

**Turtle rendering** (as presented in-session):

```turtle
<dataset/nomis-dataset-nm-1662-1> a dcat:Dataset, prov:Entity ;
    dct:identifier "NM_1662_1" ;
    dct:title "UV042 - Accommodation type (people)" ;
    dct:publisher <office-for-national-statistics> ;
    dct:license <https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/> ;
    prov:hadPrimarySource <https://www.nomisweb.co.uk/api/v01/dataset/def.sdmx.json> ;
    prov:generatedAtTime "2026-07-17T19:22:49Z"^^xsd:dateTime .
```

**Disclosed caveats.** Metadata evidence 6/14 ("low" band); Code of Practice quality pillar unevidenced; the record's own warning that evidence availability does not certify accuracy; alignment statuses are publisher self-assessments; the flagship CPIH record (`dataset/ons-data-api-dataset-cpih01`, doc 1639) was located but not hydrated (Appendix A #12–21).

## Appendix D — The bundle's standards register (34 standards, 42 requirements)

As fetched from `data/standards/evaluation.json`, current as of 2026-07-17. Grouped by the bundle's own categories.

**Binding legislation (4):** Statistics and Registration Service Act 2007; Public Sector Bodies Accessibility Regulations 2018; Data Protection Act 2018; INSPIRE Regulations 2009.

**Statutory code (2):** Code of Practice for Statistics 3.0 — Standards for Official Statistics (October 2025); Code of Practice 3.0 — Standards for Public Use (replacing 2022 intelligent-transparency guidance, May 2026).

**Official standards (4):** GovS 010 Analysis (updated August 2025); UK DCAT-3 catalogue metadata profile (recommended open standard); UK Cross-Government Metadata Exchange Model; UK GEMINI 2.3.

**Official guidance (9):** ONS QMI; ONS Guide to Statistical Revisions; OSR Administrative Data QA Toolkit (QAAD); Aqua Book; RAP Strategy; Government Data Quality Framework; ONS Classifications and Standards; GSS Harmonised Standards; GDS API technical and data standards.

**Technical recommendations (7):** W3C DCAT 3; SKOS; PROV-O; DQV (Working Group Note); RDF Data Cube; CSVW; DCAT-AP 3.0.1.

**International standards (8):** SDMX 3.1 (ISO 17369); GSBPM 5.2; GSIM 2.0; DDI Common Core 1 (ISO/PAS 25955:2026); UN Fundamental Principles of Official Statistics; UN NQAF; ISO 19115-1; ISO 19157-1:2023.

Bundle-declared position: profile alignment **"partial"**; "The bundle maps evidence to the registered standards and ontologies. This is not certification of ONS products or legal compliance." Evidence availability across 4,989 records: provenance 4,989; dimension metadata 1,617; quality documentation links 49; methodology links 9.

## Appendix E — Access and environment profile

| Dimension | Detail |
|---|---|
| Model | Claude Fable 5 (`claude-fable-5`), knowledge cutoff May 2025 — all bundle facts fetched live |
| Harness | Anthropic Cowork (research preview) on macOS; sandboxed Ubuntu 22 workspace for shell; file tools scoped to the user-selected Research folder plus a session scratchpad |
| Network access used | Unauthenticated HTTPS GET only, to `chris-page-gov.github.io` (GitHub Pages, static). No cookies, tokens, credentials, or POST requests. No access to non-public systems |
| Data sensitivity | Public official metadata under OGL v3. No personal data processed. Bundle declares `secret_values_stored: false`, MCP bindings `read_only: true` |
| Local capabilities used | Read/Grep over harness-spooled tool results; bash for file inspection and timestamp arithmetic; Write for this document |
| Capabilities attempted but unavailable | Claude in Chrome browser rendering (extension disconnected; 4 failed calls). Task completed without it |
| Capabilities not required | Credentials of any kind; write access to any external system; code execution against remote hosts; the bundle's MCP query tools (e.g. `nomis.query`) were described in-record but not invoked |
| Known harness constraints encountered | Per-fetch response cap ~92–95 KB (exact bound not published; observed truncations at 92,315–94,577 chars); oversized results auto-spooled to local files; sandbox prohibits fetching URLs by shell (curl/wget), so all web access went through the governed fetch tool |
| Verification performed | Truncation confirmed by file-tail inspection; spool timestamps recovered from epoch-ms filenames and independently converted with `date -u`; all quoted counts traced to specific fetched files |

## Appendix F — Glossary

**OKF** — Open Knowledge Format, a self-describing static JSON bundle convention for publishing knowledge corpora to humans and machines. **Bundle root** — the single entry JSON declaring scope, counts, entrypoints, licence and provenance. **Entrypoint** — a named path from the root to a functional index (overview, standards, search, etc.). **Hydration** — fetching full record detail lazily from sharded chunk files. **Confusable alternative** — a near-duplicate dataset explicitly linked with field-level differences. **DCAT 3** — W3C Data Catalog Vocabulary v3. **PROV-O** — W3C Provenance Ontology. **SDMX** — Statistical Data and Metadata eXchange (ISO 17369). **MCP** — Model Context Protocol, the tool-calling interface for AI agents. **Spooling** — the harness diverting an oversized tool result to a local file for selective reading. **MRR / recall@k / nDCG** — standard retrieval-quality metrics reported by the bundle's own evaluation.

---

*End of input. Prepared as evidence for a briefing note on the utility of Open Knowledge Format bundles for AI-mediated access to official statistics. All uncited claims trace to the session log at Appendix A; all URLs were live at 05:32–05:37 UTC, 18 July 2026.*
