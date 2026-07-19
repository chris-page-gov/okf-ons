# MCP client rollout for OKF-ONS evaluation

## Current state

The controlled broker is local, dependency-free, read-only and metadata-only.
It loads the frozen repository snapshot and never calls ONS, Nomis, the open
web or MCP-Geo. It stores no credentials and cannot return observation values.

| Client | Repository or local status | Evaluation status |
| --- | --- | --- |
| Google Antigravity CLI (`agy`) | Enabled by repository-scoped `.agents/mcp_config.json` | Ready for a fresh `/mcp` connection check; no model run was made during installation |
| Gemini CLI (`gemini`) | Not modified; its `.gemini/settings.json` is a different configuration surface | Retained as a separate, non-initial profile |
| Claude Desktop normal chat | Existing user-wide configuration was inspected by server name only and not modified; see the safe merge procedure below | Manual transcript/capture path after explicit local installation |
| Claude Desktop Cowork/research | Local stdio configuration is not assumed to be available | Requires the remote connector work package |
| Claude Code | No global configuration changed | Can be added in an isolated project configuration during runner work |
| Microsoft 365 Copilot Researcher in Edge | No local configuration is possible | Requires a staged, admin-created federated connector to a remote HTTPS broker |

## Tool contract

The local server exposes:

- `okf.descriptor`: compact orientation, scope and assurance boundary;
- `okf.search`: bounded search with stable, source-qualified record IDs;
- `okf.get_record`: complete exact-record hydration;
- `okf.compare`: side-by-side material contrasts and declared alternatives;
- `okf.prepare_mcp_plan`: read-only MCP-Geo selection hand-off with unresolved
  dimensions kept explicit; and
- `okf_eval.submit_answer`: validates and hashes the visible structured answer
  without persisting hidden reasoning.

It also exposes small read-only descriptor, agent-profile, selection-contract
and exact-record resources.

## Antigravity CLI

Current Google documentation places workspace MCP configuration at
`.agents/mcp_config.json`. Start `agy` from the repository root, open `/mcp`,
and confirm that `okf-ons` is connected before starting a fresh-context task.

The committed configuration uses:

```json
{
  "mcpServers": {
    "okf-ons": {
      "command": "python3",
      "args": ["scripts/okf_ons_mcp.py"],
      "cwd": "."
    }
  }
}
```

Do not copy this entry into the older Gemini CLI settings and assume it
configures AGY. The products use different project configuration paths.

## Claude Desktop

Claude Desktop normal chat can run a local stdio server, but current Anthropic
guidance prefers packaged desktop extensions for repeatable distribution. A
local developer entry must use an absolute repository path because the app does
not start inside the repository:

```json
{
  "mcpServers": {
    "okf-ons": {
      "command": "python3",
      "args": ["/absolute/path/to/okf-ons/scripts/okf_ons_mcp.py"]
    }
  }
}
```

Safe rollout rules:

1. back up the existing Claude Desktop configuration;
2. merge only the `okf-ons` key without replacing other servers;
3. place no API key, bearer token or environment secret in the entry;
4. validate the JSON and run the broker protocol smoke test;
5. restart Claude Desktop and inspect connection status in Developer settings;
   and
6. run evaluation tasks in a fresh normal-chat context.

This does not configure Cowork/research mode. Use a remote custom connector for
that surface and record it as a different client profile.

## Microsoft 365 Copilot Researcher

Microsoft 365 Copilot Researcher cannot launch a laptop stdio process.
Microsoft’s current federated-connector flow requires:

1. a public HTTPS MCP endpoint with read-only tools;
2. Streamable HTTP transport;
3. Microsoft Entra SSO or OAuth 2.0;
4. Global Administrator or AI Administrator and suitable Entra permissions;
5. registration through the Teams Developer Portal where required;
6. connector creation in the Microsoft 365 admin center;
7. staged rollout to the evaluation user or group; and
8. an up-to-15-minute propagation allowance before the readiness probe.

The connector fetches at run time and does not make OKF content part of the
Microsoft 365 semantic index. If tenant-wide indexed discovery is also wanted,
that is a separate synced-connector work package.

## Remote parity acceptance criteria

The remote server must have the same tool names, input schemas, output semantics
and snapshot identity as the local broker. Before a comparative run:

- tool-list digests match;
- search and exact-record fixture responses match;
- every tool is read-only;
- authentication and user scope are evidenced;
- access-arm and response-byte events are captured and redacted;
- no secret or observation value appears in a public run; and
- blocked connector readiness remains outside answer-quality denominators.

## Sources

- [Google Antigravity MCP configuration](https://antigravity.google/docs/mcp)
- [Claude Desktop local MCP servers](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop)
- [Claude remote custom connectors](https://support.claude.com/en/articles/11175166-about-custom-integrations-using-remote-mcp)
- [Microsoft federated connectors overview](https://learn.microsoft.com/en-us/microsoft-365/copilot/connectors/federated-connectors-overview)
- [Microsoft custom federated connector setup](https://learn.microsoft.com/en-us/microsoft-365/copilot/connectors/set-up-custom-federated-connectors)
