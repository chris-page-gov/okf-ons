# ONS OKF Monday demonstrator

## Shareable surfaces

- Pages UI: <https://chris-page-gov.github.io/okf-ons/>
- OKF descriptor: <https://chris-page-gov.github.io/okf-ons/okf-explorer.json>
- Open in OKF Explorer:
  <https://chris-page-gov.github.io/okf-explorer/?bundle=https%3A%2F%2Fchris-page-gov.github.io%2Fokf-ons%2Fokf-explorer.json>
- Repository: <https://github.com/chris-page-gov/okf-ons>

The public site is static, metadata-only and key-free. It does not call an
upstream API or execute an MCP request.

## Seven-minute route

The one-sentence framing is:

> OKF makes ONS data findable and distinguishable; a downstream live-data MCP
> retrieves it only after the dataset-specific choices are explicit.

1. Start with the coverage strip. Explain that “all” is measured with expected,
   represented, excluded, errored and unexplained counts per official source.
2. Search for `consumer prices inflation`, `population estimates local
   authority` or `unemployment claimant count`.
3. Add one facet and describe the result as a **reduced candidate set**, not an
   automatically chosen answer.
4. Open a plausible record and read its decision signature: population,
   measure, unit, geography, reference period, frequency and version.
5. Choose **Compare**. Show that easily confused records remain visible and
   that differences are evidence-backed. Similar titles are never treated as
   equivalence.
6. Open **Quality & methodology**, **How produced** and **Standards**. Point to
   QMI, methodology, provenance, revisions and the explicit
   `not-evaluated` state.
7. Open **Dimensions**, then **Access via MCP**. Missing version-specific
   choices remain explicit; the generated read-only plan is not executable
   until structurally valid.
8. Finish with **Open in OKF Explorer** to demonstrate that the UI is reading an
   interoperable bundle rather than a private application database.

## Safe claims

| Say | Do not say |
| --- | --- |
| The frozen build is metadata-only and reproducible. | The bundle proves every observation is accurate. |
| Similar records expose material discriminators before selection. | Similar titles identify the same statistical product. |
| Standards alignment is reported with source evidence. | Every source dataset is certified compliant. |
| A zero-omission ledger supports its stated source scope. | “All ONS” without a measured denominator. |
| The local OKF broker prepares a non-executing selection plan. | The repository broker retrieves live observations. |
| A downstream MCP integration may retrieve live data after validation. | GitHub Pages executes authenticated API calls. |

Metadata completeness is evidence availability. It is not proof of statistical
accuracy, methodological fitness or comparability for a specific analysis.

## Agent entrypoints

| Purpose | Path |
| --- | --- |
| Bundle descriptor | `okf-explorer.json` |
| Bounded comparison records | `data/demo/contrast-records.json` |
| Coverage ledger | `data/coverage/ledger.json` |
| Standards evaluation | `data/standards/evaluation.json` |
| Discovery evaluation | `data/evaluation/report.json` |
| MCP bindings | `data/ons/mcp-bindings.json` |
| Spatial metadata index | `data/ons/spatial-index.json` |

These files are ordinary static JSON. Agents do not need to screen-scrape the
human interface.

## Optional AI-client route

For a technical audience, show the local metadata-only broker after the static
demo:

1. Explain that `scripts/okf_ons_mcp.py` exposes bounded descriptor, search,
   exact-record, comparison, non-executing selection-plan and evaluation
   submission tools over local stdio.
2. Point to the repository-scoped `.agents/mcp_config.json` as the AGY example.
   It was added after the preserved Antigravity trial and is configuration
   evidence, not a fresh model result.
3. Use the [MCP rollout guide](mcp-client-rollout.md) to show the separate
   Codex, Claude, Gemini, VS Code/Copilot, ChatGPT, Microsoft 365 and Inspector
   routes and their current readiness.
4. State the boundary: the repository has no deployed remote broker or secure
   tunnel, makes no live or paid model call in CI, and never retrieves
   observations. ChatGPT custom apps, Claude Research and remote-session
   Cowork, and M365 Researcher therefore remain planned integrations; the M365
   admin connector has not been deployed.

Do not spend the Monday demo authenticating a client. The reproducible proof is
the frozen static site, deterministic local protocol tests and explicit
connection/readiness register.

## If the network is unreliable

The discovery records, contrast evidence and evaluation reports are already
part of the static site. Keep the Pages tab loaded, use the direct JSON links,
or open the descriptor in OKF Explorer. Live ONS execution is the final MCP
hand-off and is not needed to demonstrate discovery.

## Suggested follow-up questions for ONS

- Which source register should be treated as the official denominator for each
  statistical product family?
- Which distinctions most often lead users to the wrong dataset?
- Which version, revision, accreditation and methodology fields should be
  mandatory in a decision signature?
- Can ONS provide stable cross-references among catalogue, release, QMI, API,
  SDMX and Open Geography records?
- Which gold discovery queries and alternatives should an ONS subject expert
  curate first?
