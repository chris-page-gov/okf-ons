# Research evidence

This directory preserves the evidence from one live AI-access session against
the public OKF-ONS demonstrator on 18 July 2026.

## Authority and derivation

- `OKF-ONS_AI_Access_Briefing_Input.md` is the authoritative research record.
- `2026-07-18-claude-desktop-cowork-fable-5-okf-ons-access-trace-public-sanitized.docx`
  is a public formatting derivative of that Markdown record. Page numbering
  and provenance formatting in the DOCX do not override the Markdown.
- `manifest.json` pins both public files by SHA-256, records the private source
  package hash in `sanitized_from_sha256`, and separates session-reported
  observations from later repository verification.

The raw Office package is retained privately by source hash and is not stored
in Git because it contained MSIP/Purview custom-property metadata. The public
derivative removes those properties without editorially correcting the
research claims. Later checks found that several interpretations in the
session were caused by partial fetches. Those qualifications are recorded in
the manifest and in
[`docs/agent-access-and-evaluation-proposal.md`](../docs/agent-access-and-evaluation-proposal.md).

## Evidence boundary

This is a contemporaneous case-study trace, not a controlled benchmark:

- one model and host surface were observed;
- the three substantive tasks shared one conversation;
- there was no open-web or raw-API control arm;
- token counts and some payload sizes are estimates;
- model identity, tool chronology and transcript completeness are
  session-reported because a native provider export is not included; and
- standards alignment was assessed from bundle-declared evidence rather than
  independently certified.

The artefacts are research input under the handling statement in the source
document. Repository code is MIT licensed; upstream ONS metadata is normally
published under the Open Government Licence. This repository does not assert
that every statement or research artefact is itself OGL-licensed.

## Document portability

The sanitized DOCX is structurally valid and contains page-number fields and
provenance headers. Package inspection found no macros and confirmed removal
of the private custom-properties part. A LibreOffice rendering on macOS
produced 13 pages but showed clipped top content on several even pages, while
the odd-page layout rendered as intended. This is a renderer-specific
portability warning, not a claim that the source layout was perfect. Use the
Markdown for content and the DOCX for its intended Word formatting.
