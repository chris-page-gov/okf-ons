# Deep Research Prompt: Positioning Open Knowledge Format in a Governed AI Architecture for UK Government

## Role

Act as a multidisciplinary research team comprising:

- a UK Government enterprise architect;
- an AI assurance and security architect;
- a semantic-web and linked-data specialist;
- a public-sector data-governance specialist;
- an official-statistics domain expert; and
- a critical technology-policy researcher.

Write for senior architects, data leaders, statisticians, assurance professionals and digital-policy decision-makers. Use British English. Distinguish clearly between facts, interpretations, architectural judgements and recommendations.

## Primary research question

**Where should Open Knowledge Format (OKF), including YAML-LD-based OKF bundles and OKF Explorer, sit within a Governed AI Architecture suitable for UK Government, using the Office for National Statistics (ONS) as the principal reference case?**

Determine whether OKF is best understood as:

1. a portable content/interchange format;
2. a semantic catalogue or data-product descriptor;
3. a knowledge-contract layer;
4. an evidence and assurance layer;
5. an agent discovery or control-plane component;
6. a retrieval/RAG packaging mechanism;
7. a cross-cutting architectural plane spanning several layers; or
8. some carefully bounded combination of these.

Do not assume that OKF is a new numbered layer. Test that proposition against alternatives.

## Core artefacts to inspect

Inspect the current contents, documentation, profiles, schemas, constraints, tests, release history and architectural decisions in:

- https://github.com/chris-page-gov/okf-ons
- https://github.com/chris-page-gov/okf-explorer
- https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf
- the attached presentation, **Governed AI Architecture**, which provides the baseline six-layer model;
- the W3C YAML-LD specification and related JSON-LD standards; and
- any attached contextual material, treating it as secondary rather than authoritative evidence.

Record the branch, commit SHA, version and retrieval date used for each repository. Distinguish the normative OKF v0.1 specification from experimental application profiles and local implementation choices in the two `chris-page-gov` repositories.

## Baseline architectural model

Use the six-layer architecture in the attached presentation as the starting point:

1. **Decentralised data stores** — authoritative institutional data remains locally governed and is not automatically pooled.
2. **Local execution and tools** — sandboxed runtimes, APIs, gateways and bounded execution environments.
3. **Zero-trust security and identity** — human delegation, workload identity, policy enforcement and least privilege.
4. **Agent orchestration** — discovery, binding, workflow and agent/tool protocols.
5. **Federation control** — coordination across independently governed organisations, nodes and releases.
6. **Policy and governance** — law, ethics, assurance, risk, human authority and institutional accountability.

Also analyse the architecture using these planes, because a layer-only view may be insufficient:

- source-data plane;
- knowledge/semantic plane;
- control and execution plane;
- security and trust plane;
- management/federation plane; and
- governance, evidence and assurance plane.

## Starting hypothesis to test, not assume

Test the following proposition rigorously:

> OKF is best placed as a cross-cutting **Governed Knowledge Contract and Evidence Plane**. It packages authoritative metadata, context, provenance, quality evidence, constraints and machine-actionable references into portable, versioned, human-auditable bundles. YAML-LD can serve as a canonical semantic authoring form; deterministic builds can publish JSON-LD and consumer-specific projections; OKF Explorer can provide deterministic discovery and comparison; and a bounded MCP component can compile or validate a non-executing selection plan. Identity, authorisation, policy enforcement, live retrieval and consequential action remain responsibilities of separate trusted services and accountable human or institutional authorities.

Evaluate whether “Governed Knowledge Contract and Evidence Plane” is the right label. Compare it with at least these alternatives:

- semantic interoperability plane;
- context plane;
- knowledge exchange plane;
- metadata and provenance layer;
- semantic control plane;
- evidence substrate;
- data-product contract layer; and
- no special architectural plane: merely a file format used by components in existing layers.

Avoid calling OKF a “control plane” unless the evidence shows that it actually exercises control rather than merely informing, constraining or documenting it.

## Required conceptual distinctions

Make the following distinctions explicit and use them throughout the analysis:

1. **Source authority** — the system or institution authoritative for the underlying data or publication.
2. **Semantic authority** — the authority for meaning, identifiers, classifications, relationships, caveats and interpretations represented in the bundle.
3. **Operational authority** — the service permitted to perform a live query or action.
4. **Decision authority** — the human or institution accountable for a consequential decision.
5. **Official statements** — directly supported by an authoritative source.
6. **Normalised statements** — deterministic transformations of official material.
7. **Inferred statements** — rule-derived claims carrying evidence and confidence.
8. **Model-derived statements** — AI-assisted claims carrying passage evidence, method/model version, confidence and evaluation status.

Assess whether the authority classes used by the OKF Explorer profile are sufficient and how they should map to W3C PROV-O or another provenance model.

## ONS reference case

Use `okf-ons` as a worked reference architecture, not merely as a software demonstration. Analyse this intended chain:

1. ONS Data API, Nomis, ONS Open Geography and other authoritative sources remain the source-data systems.
2. Acquisition records source evidence and measured coverage.
3. Deterministic normalisation produces stable identifiers and version-specific metadata.
4. Markdown plus YAML-LD provides a human-reviewable semantic authoring surface.
5. Build and validation produce JSON-LD, Explorer descriptors, manifests, indexes, checksums and other derived artefacts.
6. Independent publication and a registry provide federated discovery without copying all source corpora into one central service.
7. OKF Explorer supports deterministic search, filtering, comparison, relationship inspection and progressive disclosure.
8. A local or remote metadata MCP service exposes bounded read-only discovery and emits a non-executing selection plan.
9. Identity, policy, user intent and required dimensions/options are validated.
10. A separate downstream ONS or Nomis integration performs live retrieval.
11. The response carries source, version, parameters, time, caveats and other provenance into audit, evaluation and any subsequent AI answer.

Test the architectural and governance value of keeping observations, secure microdata, credentials and private data outside the OKF bundle. Examine whether this separation reduces attack surface, privacy risk, stale-data risk and hallucinated execution, while identifying any new risks created by stale or misleading metadata.

Address the semantics of official statistics, including:

- dataset, edition, version, release, revision, dimension, option, geography and observation;
- comparability and “easily confused alternatives”;
- quality, uncertainty, methodological change and caveats;
- the Code of Practice for Statistics concepts of Trustworthiness, Quality and Value;
- measured coverage denominators and explicit incompleteness;
- statistical disclosure control and the Five Safes where relevant;
- provenance of classifications, mappings and cross-source reconciliation; and
- the boundary between discovery metadata and statistical evidence used in a decision.

## Architectural questions to answer

### Placement and boundaries

1. Is OKF a layer, a cross-cutting plane, a contract at architectural boundaries, an artefact chain, or a combination?
2. On the six-layer diagram, where should OKF bundles, YAML-LD, JSON-LD, the Explorer, registries, validators and MCP selection plans each appear?
3. Which responsibilities belong to OKF, and which must remain outside it?
4. What is canonical: the source system, the YAML-LD authoring artefact, the expanded JSON-LD graph, or a generated runtime projection?
5. How should semantic authority be distinguished from source, operational and decision authority?
6. Is the Explorer a knowledge-plane consumer, a presentation layer, a deterministic retrieval component, or part of agent orchestration?
7. Is the selection-plan component best understood as a compiler, boundary adaptor, capability request, workflow fragment or executable command?

### Federation and institutional governance

8. How should independently owned bundles be published, registered, discovered, versioned, deprecated and revoked?
9. What prevents a central registry from becoming a new centralisation trap?
10. What trust framework is needed for cross-departmental or cross-public-sector bundle publication?
11. Who may assert official, normalised, inferred or model-derived claims?
12. How should conflicts between bundles, identifiers or interpretations be represented rather than silently resolved?
13. What are the minimum conformance levels for a producer, publisher, registry, consumer and execution broker?

### Security, integrity and safety

14. How should bundle integrity, publisher identity, signing, checksums, content-addressing, provenance and revocation work?
15. How should remote JSON-LD/YAML-LD contexts be pinned or allowlisted to prevent context substitution and non-deterministic interpretation?
16. How should Markdown, links, embedded resources and model-facing text be treated as potentially hostile input?
17. What controls are needed against prompt injection, malicious resources, poisoned metadata, registry takeover, dependency compromise, identity collision, replay, stale selection plans and confused-deputy execution?
18. How should human delegated authority and workload identity remain separate?
19. Which controls belong in OKF metadata, which belong in OPA or another policy engine, and which require organisational process or human approval?
20. What evidence is needed for incident response, forensic reconstruction and continuous assurance?

### Lifecycle and operations

21. Define the lifecycle from authoritative source through acquisition, authoring, validation, compilation, publication, registry, discovery, binding, authorisation, execution, audit, evaluation, refresh, deprecation and archival.
22. Identify the control owner, evidence produced, failure mode and recovery action at every lifecycle stage.
23. How should freshness, service-level expectations, coverage, semantic versioning and backward compatibility be represented?
24. Which artefacts are immutable snapshots, and which are mutable pointers to a current release?
25. What should be cached, and how must caches remain subordinate to versioned semantic authority?
26. How should large bundles support progressive disclosure without hiding material caveats or provenance?
27. How can deterministic evaluation test retrieval quality, metadata quality, execution safety and user outcomes without relying only on model self-report?

## Standards and framework crosswalk

Compare OKF and the proposed architecture with current authoritative specifications and frameworks. Explain complementarity, overlap, gaps and possible mappings. Do not claim that OKF replaces a mature domain standard without strong evidence.

At minimum examine:

### Knowledge, semantics and provenance

- OKF v0.1;
- YAML-LD, including its current W3C maturity status;
- JSON-LD;
- RDF and RDFS/OWL where relevant;
- SHACL;
- PROV-O;
- DCAT 3;
- SKOS;
- schema.org;
- CSV on the Web; and
- content-addressing or signed-envelope standards where relevant.

### Official statistics and data management

- SDMX;
- DDI;
- GSIM;
- GSBPM;
- RDF Data Cube vocabulary where still relevant;
- ONS metadata and API models;
- the Code of Practice for Statistics 3.0;
- the Five Safes; and
- data-product and data-contract practices.

### APIs, agents and workflow

- OpenAPI;
- AsyncAPI;
- GraphQL schemas where relevant;
- Arazzo;
- Model Context Protocol (MCP);
- agent-to-agent protocols where sufficiently mature; and
- capability-based or contract-based invocation patterns.

### Security, identity, policy and observability

- OAuth 2.0 and OpenID Connect;
- sender-constrained tokens such as DPoP where relevant;
- SPIFFE/SPIRE;
- OPA or equivalent policy-as-code;
- OpenTelemetry;
- software supply-chain practices such as SBOM, SLSA, in-toto or DSSE where appropriate; and
- NCSC secure-AI-system-development guidance.

### UK Government governance and assurance

Use current primary sources and record publication/update dates and applicability. Include at least:

- the UK Government AI Playbook;
- the Data and AI Ethics Framework;
- the Algorithmic Transparency Recording Standard;
- the Technology Code of Practice and Open Standards Principles;
- the Digital Assurance Playbook and current spend/assurance controls;
- NCSC guidance for secure AI system development;
- ICO guidance on AI and data protection;
- the Service Standard where relevant;
- the Code of Practice for Statistics 3.0;
- ONS data strategy, business plans and relevant architecture publications;
- the Statistics and Registration Service Act 2007;
- UK GDPR and the Data Protection Act 2018;
- the Digital Economy Act 2017 where relevant;
- the Equality Act 2010 and public-sector equality duty where consequential uses are in scope;
- Freedom of Information, public-records and records-management duties where applicable; and
- procurement, intellectual-property, licensing and Open Government Licence considerations.

State precisely which requirements are mandatory, advisory, sector-specific or merely useful analogies.

## Competing hypotheses

Evaluate at least the following hypotheses and provide evidence for and against each:

- **H1 — File-format hypothesis:** OKF is only a portable file convention and should not appear as a distinct architectural plane.
- **H2 — Knowledge-contract hypothesis:** OKF is a versioned contract between knowledge producers and human/agent consumers.
- **H3 — Evidence-plane hypothesis:** OKF’s greatest government value is carrying provenance, quality, caveats, authority and assurance evidence.
- **H4 — Semantic-control-plane hypothesis:** OKF can act as a semantic control plane for agents.
- **H5 — Federated-publication hypothesis:** OKF is primarily an institutional federation mechanism for independently governed knowledge products.
- **H6 — RAG-packaging hypothesis:** OKF is chiefly a more inspectable packaging format for retrieval-augmented generation.
- **H7 — Compilation-target hypothesis:** YAML-LD OKF is a human-auditable source form compiled deterministically into graph and runtime projections.
- **H8 — Boundary-contract hypothesis:** OKF is most valuable at the boundary between discovery and authorised execution, where it can produce an inspectable, non-executing selection plan.

Score the hypotheses against public value, semantic precision, provenance, determinism, human auditability, machine actionability, interoperability, federation, privacy, security, operational resilience, adoption cost, standards maturity and vendor neutrality.

## Threat and failure analysis

Produce a threat model and failure-mode analysis covering at least:

- false claims of official authority;
- conflation of official, normalised, inferred and model-derived statements;
- stale or incomplete bundles presented as current or complete;
- forged publisher identity or provenance;
- unsigned or altered generated artefacts;
- remote context substitution;
- identifier collision or semantic drift;
- malicious Markdown, links, resources or prompt injection;
- registry poisoning or takeover;
- compromised build pipeline or dependency;
- licence, attribution or redistribution failures;
- leakage of sensitive data into a public bundle;
- excessive or unauthorised retrieval;
- ambiguous geography, edition, version, dimension or option;
- execution of a plan that was intended only for inspection;
- mismatch between the bundle version used for selection and the live API version used for execution;
- cache poisoning, embedding drift and reuse of semantically inappropriate cached material;
- loss of audit linkage between discovery, authorisation, execution and answer generation; and
- over-reliance on deterministic metadata when the underlying statistical judgement remains contextual.

For each, identify threat actor or cause, affected trust boundary, consequence, preventive control, detective control, recovery action, evidence retained and residual risk.

## Required outputs

Produce the final report in the following order.

### 1. Executive conclusion

In 500–800 words, answer the primary question directly. Include:

- a one-sentence recommended architectural placement;
- the strongest evidence;
- the principal limitation of that placement;
- what OKF must not be mistaken for; and
- the decision UK Government should take now.

### 2. Facts, inferences and recommendations

Provide three clearly separated sections:

- **Established facts** supported by primary sources or repository evidence;
- **Architectural inferences** derived from those facts; and
- **Recommendations** requiring a policy, design or governance choice.

### 3. Placement-options assessment

Compare at least:

- a seventh architectural layer;
- a component within the data layer;
- a component within agent orchestration;
- a cross-cutting Governed Knowledge Contract and Evidence Plane;
- an artefact chain with no separate plane; and
- a hybrid of plane plus concrete components.

Use a weighted decision matrix, explain the weights and show sensitivity to different priorities.

### 4. Architecture diagrams

Provide valid Mermaid diagrams for:

1. the six-layer model with OKF’s proposed placement;
2. the ONS component and data-flow architecture;
3. a trust-boundary sequence from discovery to live retrieval and audit; and
4. the bundle lifecycle from source to deprecation.

Show separately:

- ONS/Nomis/source systems;
- acquisition and normalisation;
- YAML-LD semantic source;
- JSON-LD and generated projections;
- validation, signing and publication;
- bundle registry;
- OKF Explorer;
- metadata MCP and selection plan;
- human identity/delegation;
- workload identity;
- policy decision and enforcement points;
- downstream live-data MCP/API;
- provenance, observability and audit; and
- evaluation and assurance records.

### 5. Responsibility and authority matrix

For every major component or artefact, state:

- architectural layer and plane;
- owner;
- source authority;
- semantic authority;
- operational authority;
- decision authority;
- inputs and outputs;
- security classification;
- applicable policy;
- evidence produced; and
- what it explicitly cannot do.

### 6. Standards crosswalk

Create a table with columns:

- concern;
- OKF/YAML-LD role;
- relevant external standard;
- overlap;
- gap;
- proposed mapping or extension;
- maturity/status;
- implementation implication for UK Government; and
- source.

### 7. ONS worked example

Trace at least three realistic user journeys, for example:

- finding the correct inflation series and avoiding a similarly named alternative;
- selecting a Census table with a specific geography and version; and
- discovering metadata about a geography product before a live query.

For each journey, show what is handled by the bundle, Explorer, metadata MCP, identity/policy layer, downstream execution service and human judgement. Include failure paths.

### 8. Governance and assurance control catalogue

Map proposed controls to current UK Government and official-statistics obligations. Include:

- accountable owner;
- legal/ethical basis;
- transparency;
- meaningful human control;
- data protection;
- equality and accessibility;
- security;
- statistical quality;
- records and audit;
- procurement and supplier portability;
- licensing;
- continuous evaluation; and
- incident management.

State which controls can be evidenced through an OKF bundle and which cannot.

### 9. Gap analysis of the current implementation

Assess the present repositories against the proposed target architecture. Consider at least:

- normative versus experimental profile boundaries;
- signing and publisher trust;
- checksum coverage and content-addressing;
- registry governance and revocation;
- context governance;
- provenance vocabulary;
- authority classes;
- classification and access labels;
- legal basis and policy references;
- licences and attribution;
- freshness and deprecation;
- coverage and completeness claims;
- quality metrics and caveats;
- compatibility and semantic versioning;
- selection-plan semantics;
- policy bindings;
- audit correlation identifiers;
- evaluation evidence;
- accessibility;
- threat modelling; and
- operational ownership.

Prioritise gaps as critical, high, medium or low, and distinguish demonstrator needs from production requirements.

### 10. Architecture Decision Record

Write an ADR containing:

- context;
- decision drivers;
- options considered;
- decision;
- rationale;
- positive and negative consequences;
- risks and mitigations;
- standards implications;
- adoption status; and
- review triggers.

The ADR must state whether UK Government should presently treat OKF as:

- a mandated standard;
- an endorsed interoperability profile;
- an experimental cross-government pattern;
- a reference implementation;
- a discovery/evidence packaging convention; or
- something else.

### 11. Roadmap and maturity model

Map recommendations to the presentation’s maturity levels from undocumented/described through discoverable, governed, observable and evidential. Provide:

- a 90-day ONS-centred pilot;
- a 6-month reference architecture and assurance package;
- a 12–18-month federated adoption path; and
- explicit exit criteria for each stage.

Include organisational capabilities, not only technology tasks.

### 12. Unresolved questions and research confidence

End with:

- questions requiring ONS, GDS, CDDO, DSIT, NCSC, ICO, OSR or legal input;
- assumptions that materially affect the recommendation;
- evidence gaps;
- disagreements between sources;
- confidence for each major conclusion; and
- what evidence could falsify the recommended placement.

## Evidence rules

1. Prefer current primary sources: legislation, official government guidance, standards bodies, ONS/OSR publications, normative specifications and repository artefacts.
2. Cite every material factual claim inline, with title, publisher, version/status, publication or update date and a stable link.
3. Label repository-derived statements separately from claims made by external standards or official policy.
4. Do not treat an implementation README, slide, blog post or model-generated document as normative merely because it is detailed.
5. State that YAML-LD is a W3C Working Draft unless its status has changed at the date of research; verify the current status rather than relying on memory.
6. State that OKF v0.1 is an early specification unless a later normative version exists; verify current status.
7. Do not conflate metadata discovery with access to observation data, secure microdata or authority to act.
8. Do not infer legal compliance from the presence of metadata fields, logs or a policy reference.
9. Do not treat a valid JSON or schema-valid MCP request as authorised execution.
10. Do not claim complete ONS coverage without a stated scope, denominator, exclusions and measured omissions.
11. Use short quotations only where exact wording is analytically necessary.
12. When evidence is weak or conflicting, say so and reduce confidence.
13. For recommendations, explain the value judgement and trade-off rather than presenting it as fact.

## Quality bar

The report must be specific enough that an enterprise architecture board could:

- decide where OKF appears on the target architecture;
- define its interfaces and non-responsibilities;
- commission an ONS-centred pilot;
- assign control owners;
- identify assurance evidence;
- avoid conflating discovery with authority or execution; and
- decide whether OKF should progress from an experimental pattern to a governed interoperability profile.

Avoid generic statements such as “governance is important” or “use zero trust”. Tie every claim to an artefact, trust boundary, control, accountable owner, standard or measurable acceptance criterion.
