# LinkedIn launch post

## Main post

Ahead of Monday’s hackathon, I’ve now published an experiment in making
official statistics easier for both people and AI agents to discover—without
hiding the distinctions, gaps and failures that matter.

The demonstrator packages metadata from three bounded ONS catalogue
routes—the ONS Data API, Nomis and Open Geography—into an Open Knowledge
Format bundle:

- 4,989 metadata records and 19,570 relationships
- search and comparison designed to expose easily confused alternatives
  before a dataset is selected
- visible standards, provenance, evidence and geography
- portable exploration in OKF Explorer
- MCP selection plans covering 1,954 current bindings and 3,035 explicitly
  planned ones

This is deliberately not presented as “all ONS” yet. It is a reproducible
foundation for extending coverage while preserving source distinctions,
unresolved questions and evidence gaps.

The repository also includes a local, provider-neutral, metadata-only MCP broker
and a source-linked connection guide covering 16 profiles across Codex and
ChatGPT, Claude, Gemini and Antigravity, VS Code and GitHub Copilot, Microsoft
365 Copilot, and MCP Inspector.

The useful finding is that “AI access” is not one switch:

- local command-line and desktop clients can use a local stdio broker, with
  product-specific configuration
- ChatGPT custom apps, Claude’s remote research modes and Microsoft 365
  Researcher need a remote or enterprise-managed route
- the Microsoft 365 trial did not retrieve the supplied OKF descriptor, so it
  is recorded as an access failure—not converted into a success story
- documented product support, an installed app and a successful controlled
  trial are three different things

The three AI trials are exploratory case studies, not a model or vendor
benchmark. The broker was validated without live or paid model calls. It
searches frozen metadata and prepares a non-executing plan; a separate trusted
MCP integration would perform live ONS or Nomis retrieval.

The public bundle contains metadata only—no observation data, credentials or
API keys. Public research documents are sanitized derivatives; private source
packages are withheld and represented by hashes.

I’d value feedback from official-statistics, metadata, data-discovery,
AI-evaluation and MCP practitioners: can you find the exact dataset, understand
its alternatives, and tell which AI connection paths are genuinely ready
rather than merely documented?

Live demonstrator: https://chris-page-gov.github.io/okf-ons/

GitHub: https://github.com/chris-page-gov/okf-ons

AI connection guide:
https://github.com/chris-page-gov/okf-ons/blob/main/docs/mcp-client-rollout.md

#OfficialStatistics #OpenData #ResponsibleAI #MCP #Metadata #DataDiscovery #ONS

## Optional first comment

The most useful test is a difficult one: search for something with several
plausible ONS alternatives, compare the reduced set, and tell me what evidence
or distinction is still missing. That feedback will shape the next coverage
and evaluation work package.

For AI-client practitioners, I would also value reproducible connection
evidence—client and host version, execution mode, resolved model, tool list and
failure point. “Installed” is not the same as “ready”.

Open the bundle in OKF Explorer:
https://chris-page-gov.github.io/okf-explorer/?bundle=https%3A%2F%2Fchris-page-gov.github.io%2Fokf-ons%2Fokf-explorer.json
