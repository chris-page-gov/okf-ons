# Research evidence

This directory preserves three AI-access trials against, or prompted about, the
public OKF-ONS demonstrator on 18 July 2026:

- Claude Desktop in Cowork/research mode (local-versus-remote execution mode
  was not captured), with the session-reported model “Claude Fable 5”;
- Google Antigravity CLI (`agy`), with the session-reported model
  “Gemini 3.1 Pro (High)”; and
- Microsoft 365 Copilot Researcher in Microsoft Edge, whose resolved model was
  not exposed.

These dated artefacts record observed trial behaviour, not current installation
guidance. Supported but unverified client routes are maintained in the
[connection guide](../docs/mcp-client-rollout.md).

The date/client/task filenames make the host surface explicit without turning a
session-reported model label into provider-verified telemetry.

## Authority and derivation

- `2026-07-18-claude-desktop-cowork-fable-5-okf-ons-access-trace.md` is the
  authoritative Claude research record. The matching
  `-public-sanitized.docx` is a formatting derivative.
- `2026-07-18-antigravity-cli-gemini-3-1-pro-okf-ons-postmortem.md` is the
  Gemini session-authored postmortem. The matching briefing is a produced
  output, not a native transcript.
- The two Microsoft 365 Copilot `-public-sanitized.docx` files are public
  derivatives of produced research outputs. They are not native provider
  exports and neither identifies the resolved model.
- `manifest.json` pins every public artefact by SHA-256, records each private
  source package hash in `sanitized_from_sha256`, and separates observed,
  session-reported, later-verified, and inferred statements.

The raw Office packages are not stored in Git. Private owner-held backups retain
the source hashes recorded in the manifest. Sanitization changes package
metadata and replaces external link labels and targets with explicit public
redaction markers; it does not editorially correct the research claims.
Qualifications and corrections belong in the manifest, normalized observation
records, and
[`docs/ai-client-trial-analysis.md`](../docs/ai-client-trial-analysis.md).

## Evidence boundary

These artefacts are exploratory case studies, not controlled benchmark runs:

- prompts, host capabilities, models, context and capture fidelity differed;
- no trial contains a complete native provider export;
- the M365 trial could not retrieve the supplied descriptor and used other
  sources, including enterprise context;
- exact provider token telemetry is absent;
- the Gemini “highly token-efficient” conclusion is not supported by a control
  arm and followed a 5.9 MB shard download;
- standards mapping or vocabulary alignment is not independent conformance,
  statistical-product, legal, or policy certification; and
- the harness evaluates metadata discovery, not ONS observation accuracy.

Repository code is MIT licensed; upstream ONS metadata is normally published
under the Open Government Licence. This repository does not assert that every
research artefact is OGL-licensed.

## Public-release and document portability

The raw M365 packages contained hidden SharePoint/Outlook relationship
locators, account-specific identifiers and visible enterprise citation labels.
The raw Claude package contained MSIP/Purview custom-property metadata. Only the
sanitized derivatives are published: custom properties are removed, external
relationship targets and their visible labels are redacted, author/application
properties are normalized, and embedded media is checked for metadata.

Every derivative received a hash-bound technical public-release review and was
rendered to PDF and PNG for all-page inspection. This is not formal
information-governance clearance. Known source-layout limitations remain: the
M365 access briefing has header/body collisions, the hosting report has a
cramped page-spanning table, and the Claude derivative has clipping in
LibreOffice. These are recorded in `manifest.json`; the Claude Markdown remains
the content authority.

## Governed-AI architecture research

The following 20 July architecture-research artefacts are separate from the
18 July AI-client trials and are registered in
[`architecture-manifest.json`](architecture-manifest.json):

- [`okf-governed-ai-deep-research-prompt.md`](okf-governed-ai-deep-research-prompt.md)
  is a research design and question set, not a completed report.
- [`OKF_Governed_AI_Architecture_Deep_Research_Report_2026-07-20.md`](OKF_Governed_AI_Architecture_Deep_Research_Report_2026-07-20.md)
  is the generated research assessment at its dated repository snapshot. It is
  not factually validated, its footnote definitions are absent, and its
  repository assessment predates the current ELS integration and submodule.
- [`Governed_AI_Architecture_(2).pptx`](Governed_AI_Architecture_(2).pptx) and
  [`Architecting_Governed_Enterprise_AI (1).pptx`](Architecting_Governed_Enterprise_AI%20(1).pptx)
  are 15-slide, image-based architecture-research presentations.
- [`Reliable_Public_Statistics_Discovery_Bridge.png`](Reliable_Public_Statistics_Discovery_Bridge.png)
  is a generated explanatory visual.

The PowerPoint packages were rendered successfully and checked for macros,
external relationships, notes, comments, embedded files, custom XML, author
identity, machine paths and credential patterns. None were found. This is a
technical public-release review, not formal information-governance clearance
or factual validation.

The standalone generated visual is non-authoritative: it contains visible
typographical errors and model-effect wording that is stronger than the
controlled evidence supports. The presentations and visual preserve research
ideas and design exploration; their architectural and empirical claims must be
checked against primary sources and the repository's evidence register before
reuse.
