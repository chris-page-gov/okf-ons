# Connecting OKF-ONS to AI clients

Last verified against the linked product documentation: **19 July 2026**.

This is the canonical human setup guide for the client profiles in
[`client-profiles.json`](../evaluation/ai-client/client-profiles.json). The
profile register pins this file by SHA-256, and repository validation requires
every profile ID to appear here. Product support and local installation are not
trial evidence: every evaluation run still needs a fresh connection, model and
capture probe.

## What is ready for Monday

The checked-in server is a dependency-free, read-only, metadata-only MCP broker
over JSON-lines stdio. It requires Python 3.11 or later, reads the frozen
repository snapshot, makes no network call, stores no credentials and cannot
return observation values.

Connection states mean:

| State | Meaning |
| --- | --- |
| `repository-configured` | A portable project configuration is committed; a fresh host connection probe is still required. |
| `setup-required` | The product documents a compatible route, but OKF-ONS is not configured for that profile in the repository or user account. |
| `execution-mode-dependent` | The route changes with the host execution mode; that mode must be recorded before the run. |
| `remote-endpoint-required` | The product cannot use this local stdio process for the intended mode; the planned authenticated remote broker is not yet deployed. |
| `not-established` | Installation may have been observed, but no repeatable OKF-ONS connection and capture route has been demonstrated. |
| `protocol-baseline` | A non-AI client can validate the protocol and broker but is not an answer-quality comparator. |

The publication matrix covers every machine profile:

| Profile ID | Product / surface | Connection state | Route and Monday evidence boundary |
| --- | --- | --- | --- |
| `codex-cli` | OpenAI Codex CLI | `setup-required` | Local stdio through shared Codex MCP configuration; supported setup below, fresh `/mcp` probe required. |
| `codex-desktop` | OpenAI Codex desktop | `setup-required` | Uses the same Codex MCP configuration as the CLI and IDE; manual capture path, no unattended trial evidenced. |
| `claude-code` | Anthropic Claude Code | `setup-required` | Project `.mcp.json` or `claude mcp add`; fresh connection/model probe required. |
| `gemini-cli` | Google Gemini CLI | `setup-required` | Separate project `.gemini/settings.json`; current product, but not configured or included in the initial suite. |
| `google-antigravity-cli` | Google Antigravity CLI (`agy`) | `repository-configured` | Committed `.agents/mcp_config.json`; added after the preserved web-fetch trial, so no controlled MCP model run is claimed. |
| `vscode-agent` | VS Code Agent / Copilot Chat | `setup-required` | Workspace `.vscode/mcp.json`; supported setup below, fresh isolated-window probe required. |
| `github-copilot` | GitHub Copilot app / CLI-backed surface | `setup-required` | Workspace `.github/mcp.json` or app settings; supported by the product, not yet an OKF-ONS trial. |
| `github-copilot-xcode` | GitHub Copilot for Xcode | `setup-required` | Xcode extension MCP settings; product support is documented, but connection/model/capture remain unverified. |
| `claude-desktop` | Claude Desktop normal chat | `setup-required` | Local stdio developer entry or packaged desktop extension; fully restart and probe. |
| `claude-cowork` | Claude Cowork | `execution-mode-dependent` | Existing local desktop sessions can use local plugin MCP; remote sessions are now the default and require a remote connector. The preserved trial used the public web bundle, not this broker. |
| `m365-copilot-researcher-edge` | Microsoft 365 Copilot Researcher in Edge | `remote-endpoint-required` | Tenant-created federated connector to a Microsoft-reachable HTTPS MCP endpoint; no OKF-ONS connector has been deployed or tested. |
| `chatgpt-classic` | Installed ChatGPT Classic desktop inventory | `not-established` | No repeatable route is established for this desktop profile. ChatGPT web custom apps are a separate remote-only route described below. |
| `chatgpt-atlas` | Installed ChatGPT Atlas inventory | `not-established` | Browser capability was observed, but no authenticated OKF-ONS MCP route or evaluation capture has been established. |
| `microsoft-copilot` | Installed Microsoft Copilot desktop inventory | `not-established` | Do not infer support or readiness from installation. |
| `microsoft-365-copilot` | Installed Microsoft 365 Copilot desktop inventory | `not-established` | The documented federated-connector experiences do not prove this installed desktop profile is connected. |
| `mcp-inspector` | Model Context Protocol Inspector | `protocol-baseline` | Local stdio protocol baseline only; not an AI-quality result. |

## Architecture and evidence boundary

The four layers are intentionally separate:

| Layer | Publication state | Role |
| --- | --- | --- |
| Static OKF bundle and Pages site | Built and publishable | Human/agent discovery, comparison, provenance and selection metadata over public HTTPS. |
| Local OKF-ONS stdio broker | Implemented and tested | Gives local MCP clients bounded metadata tools over the same frozen snapshot. |
| Remote OKF-ONS broker | **Not implemented or deployed** | Future authenticated HTTPS parity for remote-only clients and enterprise connectors. |
| Downstream live retrieval MCP | Separate system | Executes a supported live statistical query only after a complete, revalidated and authorised selection plan; this repository only prepares a non-executing plan. |

Connecting a client to this repository never turns the local broker into a live
ONS query service. `okf.prepare_mcp_plan` is a non-executing hand-off to a
separately trusted downstream MCP such as MCP-Geo.

## Broker contract and local smoke test

The server identifies itself as `okf-ons-metadata-broker` version `0.2.0` and
negotiates the current MCP protocol `2025-11-25` while retaining
`2025-06-18` compatibility for existing clients. If a client requests an
unsupported version, it returns `2025-11-25` during initialization.

The six tools are:

- `okf.descriptor`: compact orientation, scope and assurance boundary;
- `okf.search`: bounded search with stable, source-qualified record IDs;
- `okf.get_record`: complete exact-record hydration;
- `okf.compare`: side-by-side material contrasts and declared alternatives;
- `okf.prepare_mcp_plan`: non-executing, read-only selection hand-off with
  unresolved dimensions kept explicit; and
- `okf_eval.submit_answer`: validates and hashes the visible structured answer
  without persisting hidden reasoning.

Small descriptor, agent-profile and selection-contract resources are advertised.
An exact record can also be read by its discovered `okf://ons/record/...` URI;
the server does not currently advertise a record URI template.

From the repository root:

```bash
python3 --version
python3 -m pytest -q tests/test_mcp_broker.py
python3 scripts/ai_client_harness.py validate
```

The broker test exercises initialization, version negotiation, tool listing,
tool calls and the no-network metadata boundary. Do not launch
`scripts/okf_ons_mcp.py` alone and wait for a prompt: it is a stdio server and
waits for MCP JSON-RPC input.

## OpenAI Codex CLI, desktop and IDE

Codex CLI, the Codex IDE extension and the Codex surface in the ChatGPT desktop
app share MCP configuration. A trusted repository may use
`.codex/config.toml`; a user can instead register the server with the CLI.
Because a reusable repository cannot know its checkout location, use an
absolute script path:

```bash
codex mcp add okf-ons -- python3 /absolute/path/to/okf-ons/scripts/okf_ons_mcp.py
codex mcp list
```

Equivalent TOML is:

```toml
[mcp_servers.okf-ons]
command = "python3"
args = ["/absolute/path/to/okf-ons/scripts/okf_ons_mcp.py"]
required = true
```

Use `/mcp` in the CLI, or the IDE MCP server list, to confirm all six tools.
Record the actual host as `codex-cli` or `codex-desktop`; shared configuration
does not make those evaluation surfaces interchangeable.

## OpenAI ChatGPT web custom app

ChatGPT web does not directly connect to a local MCP server or read local Codex
configuration. OpenAI documents a remote custom-app route in developer mode and
a Secure MCP Tunnel for supported private/developer-machine servers. Neither a
remote OKF-ONS endpoint nor a tunnel is configured in this repository.

This route is therefore a future work package, not evidence for
`chatgpt-classic` or `chatgpt-atlas`. When a remote endpoint exists, an
authorized user provides the endpoint and authentication, scans the tools and
tests a draft app; workspace admins/owners control publication. Current custom
apps are web-only. Agent mode does not use them, while deep research can use
read/fetch actions only.

## Anthropic Claude Code

Create a project-scoped entry from the repository root:

```bash
claude mcp add --transport stdio --scope project okf-ons -- \
  python3 scripts/okf_ons_mcp.py
claude mcp list
```

The equivalent `.mcp.json` shape is:

```json
{
  "mcpServers": {
    "okf-ons": {
      "type": "stdio",
      "command": "python3",
      "args": [
        "${CLAUDE_PROJECT_DIR:-.}/scripts/okf_ons_mcp.py"
      ]
    }
  }
}
```

Confirm the server with `/mcp`. A project entry is a product-specific config
surface; it does not configure Gemini, Antigravity, VS Code or Copilot.

## Anthropic Claude Desktop and Cowork

Claude Desktop normal chat supports local stdio in
`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS and
`%APPDATA%\Claude\claude_desktop_config.json` on Windows. Packaged desktop
extensions are a second, easier-to-distribute local mechanism. A manual
developer entry must use an absolute path:

```json
{
  "mcpServers": {
    "okf-ons": {
      "command": "python3",
      "args": [
        "/absolute/path/to/okf-ons/scripts/okf_ons_mcp.py"
      ]
    }
  }
}
```

Back up the existing file, merge only the `okf-ons` key, add no secret, validate
the JSON, fully restart Claude Desktop, then inspect Connectors or Developer
settings/logs. Do not replace unrelated user servers.

Cowork now has two materially different execution modes. Remote sessions run
on Anthropic infrastructure by default and cannot run local MCP servers.
Existing local desktop Cowork deployments can run local plugin or locally
configured MCP servers, subject to organization and MDM controls. Record the
execution mode before the run. A remote custom connector remains the portable
route for remote Cowork and Claude Research, but it needs an internet-reachable
remote MCP server; that server has not been built here.

## Google Antigravity CLI

The committed [`.agents/mcp_config.json`](../.agents/mcp_config.json) is:

```json
{
  "mcpServers": {
    "okf-ons": {
      "command": "python3",
      "args": [
        "scripts/okf_ons_mcp.py"
      ],
      "cwd": "."
    }
  }
}
```

Start `agy` from the repository root and use `/mcp` to confirm the server and
tools. This configuration was added after the 18 July Antigravity trial, which
used the public bundle over the web. Repository configuration is not evidence
that a fresh model call succeeded.

## Google Gemini CLI

Gemini CLI is a separate current product with a different project config,
`.gemini/settings.json`:

```json
{
  "mcpServers": {
    "okf-ons": {
      "command": "python3",
      "args": [
        "scripts/okf_ons_mcp.py"
      ],
      "cwd": "."
    }
  }
}
```

Run Gemini from the repository root and verify with `/mcp`. Do not copy an
entry between `.gemini/settings.json` and `.agents/mcp_config.json` and assume
the other host reads it.

## VS Code Agent and GitHub Copilot Chat

VS Code uses `.vscode/mcp.json` with a top-level `servers` object:

```json
{
  "servers": {
    "okf-ons": {
      "type": "stdio",
      "command": "python3",
      "args": [
        "${workspaceFolder}/scripts/okf_ons_mcp.py"
      ],
      "cwd": "${workspaceFolder}"
    }
  }
}
```

Start the server, open Copilot Chat in Agent mode and inspect the available
tools. Business/Enterprise administrators must allow MCP in policy. Use an
isolated window and record the resolved model and tool names; product support
alone is not an evaluated `vscode-agent` run.

## GitHub Copilot app, CLI and Xcode

The Copilot app is built on Copilot CLI and can use workspace MCP
configuration. Prefer `.github/mcp.json` here so it does not collide with
Claude Code’s `.mcp.json`:

```json
{
  "mcpServers": {
    "okf-ons": {
      "type": "stdio",
      "command": "python3",
      "args": [
        "scripts/okf_ons_mcp.py"
      ],
      "cwd": ".",
      "tools": [
        "okf.descriptor",
        "okf.search",
        "okf.get_record",
        "okf.compare",
        "okf.prepare_mcp_plan",
        "okf_eval.submit_answer"
      ]
    }
  }
}
```

Copilot CLI requires an explicit tool allow-list. Verify with
`copilot mcp list` or `/mcp list`, and record any host-normalized tool names.
The desktop app can also add a server under **Settings > MCP Servers**.
Business/Enterprise use requires the relevant Copilot CLI policy.

GitHub Copilot for Xcode documents local and remote MCP through
**Settings > MCP > Edit Config**, using a top-level `servers` object. Use an
absolute script path for a local entry. Its `github-copilot-xcode` profile
remains unverified until connection, authentication, model identity and capture
all pass.

GitHub.com’s cloud coding agent is a separate host: its MCP process runs in a
cloud runner, not on this laptop, and its supported tool/authentication boundary
differs. It is not one of the current local profiles.

## Microsoft 365 Copilot Researcher

Microsoft documents tenant-created custom federated connectors, but no
OKF-ONS connector has been deployed or tested. The local stdio broker cannot be
entered directly: Microsoft 365 needs a Microsoft-reachable HTTPS MCP base URL
with read-only tools, plus Microsoft Entra SSO or OAuth 2.0 registered through
Teams Developer Portal.

For a tenant trial:

1. build and compatibility-test the remote endpoint;
2. use an AI Administrator where possible (Microsoft’s dedicated setup page
   also lists Global Administrator) and any required Entra administrator;
3. ensure each test user has a Microsoft 365 Copilot add-on licence or
   Microsoft 365 E7;
4. in Microsoft 365 admin center, use **Copilot > Connectors > Gallery >
   Created by your org > Create a new connector**;
5. enter the MCP base URL and authentication registration ID;
6. stage the connector to the evaluation user or group and allow up to
   15 minutes for changes;
7. in Researcher, select the source under **Sources**, choose **Connect** and
   authenticate; and
8. run deterministic readiness probes and retain broker-side redacted events.

Federated connectors fetch at run time under the signed-in user’s source
permissions; they do not index OKF content into Microsoft 365. Organization-wide
indexed discovery is a separate synced Copilot connector, which indexes content
into Microsoft Graph. Microsoft currently lists federated-connector support in
Microsoft 365 Copilot Chat, Copilot in Excel and Researcher; do not generalize
that to every Microsoft product or to the installed `microsoft-copilot` and
`microsoft-365-copilot` profiles.

Microsoft’s dedicated setup pages document an HTTPS MCP URL but do not currently
name Streamable HTTP as a platform requirement. Treat transport compatibility
as an acceptance test. Microsoft’s general overview and newer dedicated custom
setup pages currently differ on custom-connector availability, so confirm that
**Created by your org > Create a new connector** exists in the target tenant
before declaring readiness. Public gallery submission is a separate partner
and review process, not required for a tenant hackathon trial.

## MCP Inspector

Use the Inspector only as a protocol baseline:

```bash
npx -y @modelcontextprotocol/inspector \
  python3 scripts/okf_ons_mcp.py
```

Confirm initialization, the six tools and representative fixture responses.
Record Inspector results as `mcp-inspector`, never as evidence of AI selection
quality.

## Remote parity acceptance criteria

There is no remote OKF-ONS endpoint today. Before adding any remote-only profile
to answer-quality denominators:

- the deployed snapshot identity matches the local frozen snapshot;
- search, exact-record, compare and plan fixture responses have equivalent
  semantics;
- every exposed operation is read-only;
- the client-specific connector profile is recorded—Microsoft gallery routes
  may expose only retrieval tools, so identical six-tool exposure is not
  assumed;
- authentication, user scope and source activation are evidenced;
- redacted broker-side events and response-byte measures are captured;
- no credential, private path, Office metadata or observation value enters a
  public run; and
- blocked readiness stays outside answer-quality denominators.

## Troubleshooting and cleanup

- Run from the repository root unless the configuration uses absolute paths.
- If the host shows no tools, run the broker test first, check Python 3.11+,
  inspect the configured path/cwd, then fully restart the host.
- The similar-looking config files are not interchangeable:
  `.agents/mcp_config.json`, `.gemini/settings.json`, `.vscode/mcp.json`,
  `.github/mcp.json`, Claude Code `.mcp.json`, Claude Desktop user JSON, Codex
  TOML and Xcode MCP JSON belong to different products.
- A successful installation/version probe does not prove authentication,
  server initialization, model identity or capture readiness.
- A remote client cannot call `localhost` or spawn this laptop process unless
  that product explicitly provides and you validate a secure bridge.
- Remove only the `okf-ons` entry you added during cleanup; do not overwrite
  unrelated user or organization configuration.

## Official product sources

- [OpenAI Codex MCP configuration](https://learn.chatgpt.com/docs/customization-mcp)
- [OpenAI ChatGPT developer mode and MCP apps](https://help.openai.com/en/articles/12584461-developer-mode-and-full-mcp-connectors-in-chatgpt-beta)
- [Claude Code MCP configuration](https://code.claude.com/docs/en/mcp)
- [Claude Desktop local MCP servers](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop)
- [Claude Cowork architecture](https://support.claude.com/en/articles/14479288-claude-cowork-architecture-overview)
- [Claude remote custom connectors](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp)
- [Google Antigravity MCP configuration](https://antigravity.google/docs/mcp)
- [Google Gemini CLI MCP servers](https://google-gemini.github.io/gemini-cli/docs/tools/mcp-server.html)
- [VS Code MCP configuration](https://code.visualstudio.com/docs/agents/reference/mcp-configuration)
- [GitHub Copilot MCP in IDEs](https://docs.github.com/en/copilot/how-tos/provide-context/use-mcp-in-your-ide/extend-copilot-chat-with-mcp)
- [GitHub Copilot CLI reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference)
- [GitHub Copilot app MCP customization](https://docs.github.com/en/enterprise-cloud@latest/copilot/how-tos/github-copilot-app/customize-github-copilot-app)
- [Microsoft custom federated connector setup](https://learn.microsoft.com/en-us/microsoft-365/copilot/connectors/set-up-custom-federated-connectors)
- [Microsoft federated connector prerequisites](https://learn.microsoft.com/en-us/microsoft-365/copilot/connectors/prerequisites)
- [Microsoft federated connectors overview](https://learn.microsoft.com/en-us/microsoft-365/copilot/connectors/federated-connectors-overview)
- [Microsoft Copilot connectors overview](https://learn.microsoft.com/en-us/microsoft-365/copilot/connectors/overview)
- [MCP Inspector](https://github.com/modelcontextprotocol/inspector)
