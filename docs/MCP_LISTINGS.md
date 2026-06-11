# MCP Registry Listing Handoff

Prepared on 2026-06-11. Do not submit, publish, push registry branches, or open
external PRs from the polish automation branch. The operator submits after the
polish PR is merged and `freellmpool 0.11.3` is published to PyPI.

## Local Manifest Status

`server.json` is ready for package-based stdio registry entries:

- Schema: `https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json`
- Name: `io.github.0xzr/freellmpool`
- Version: `0.11.3`
- Repository: `https://github.com/0xzr/freellmpool`
- Package: PyPI `freellmpool`, runtime hint `uvx`
- Transport: stdio
- Package argument: `mcp`

Install blocks for directories that accept raw client config:

```json
{
  "mcpServers": {
    "freellmpool": {
      "command": "uvx",
      "args": ["freellmpool", "mcp"]
    }
  }
}
```

After an explicit `pipx install freellmpool` or `pip install freellmpool`, users
can also configure:

```json
{
  "mcpServers": {
    "freellmpool": {
      "command": "freellmpool",
      "args": ["mcp"]
    }
  }
}
```

Tool surface to mention in every listing:

- `free_llm_ask`
- `free_llm_panel`
- `tokenmax`
- `free_llm_route`
- `free_llm_models`
- `free_llm_quota`
- `free_llm_stats`

## Registry Status

| Registry | Status | Requirement checked | Operator action |
|---|---|---|---|
| Smithery | Ready for operator packaging; not directly URL-ready | Smithery URL publishing requires Streamable HTTP; local stdio publishing uses an MCPB bundle. Source: <https://smithery.ai/docs/build/publish>. | Build a local MCPB bundle for `freellmpool mcp`, then go to <https://smithery.ai/new>, choose **Local (MCPB Bundle)**, upload the bundle, and paste the copy from `docs/mcp-listings/smithery.md`. |
| Glama | Ready after merge | Glama lists open-source MCP servers from GitHub repo submission, verifies maintainer GitHub OAuth access, clones/builds/introspects the repo, and scores tools. Sources: <https://glama.ai/> and <https://glama.ai/mcp/methodology>. | Sign in, open <https://glama.ai/mcp/servers>, click **Submit** / **List your server for free**, enter `https://github.com/0xzr/freellmpool`, authorize with a GitHub account that has write/admin access, and paste the copy from `docs/mcp-listings/glama-submission.md` if the form asks for details. |
| MCP.so | Ready after merge | MCP.so says submissions are created via a GitHub issue and should include name, description, features, and connection information. Source: <https://mcp.so/>. | Open <https://mcp.so/>, click **Submit**, create the GitHub issue, and use `docs/mcp-listings/mcp-so-issue.md` as the issue body. |
| PulseMCP | Ready after merge; strongest after official registry publish | PulseMCP says its directory uses manual submissions, automated crawling, the official MCP Registry, and server.json metadata enrichment. Sources: <https://www.pulsemcp.com/api> and example listing <https://www.pulsemcp.com/servers/wei-mcp-registry>. | Open <https://www.pulsemcp.com/>, click **Submit server/client**, submit `https://github.com/0xzr/freellmpool`, and use `docs/mcp-listings/pulsemcp-submission.md`. After `server.json` is published to the official MCP Registry, ask PulseMCP to refresh if the listing does not appear automatically. |

## Submission Files

- `docs/mcp-listings/smithery.md`
- `docs/mcp-listings/glama-submission.md`
- `docs/mcp-listings/mcp-so-issue.md`
- `docs/mcp-listings/pulsemcp-submission.md`

No external submissions were performed while preparing this handoff.
