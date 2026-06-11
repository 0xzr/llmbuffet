# Smithery Submission Copy

Use this after preparing a local MCPB bundle for the stdio server. Smithery's URL
path is for Streamable HTTP servers; freellmpool currently ships a local stdio
server through PyPI.

## Name

freellmpool

## Package / command

```json
{
  "command": "uvx",
  "args": ["freellmpool", "mcp"]
}
```

## Short description

Run free LLM subtasks through MCP: ask, panel, tokenmax, routing preview,
available models, daily quota, and lifetime stats.

## Long description

freellmpool is a local stdio MCP server for using free LLM provider tiers from
Claude Desktop, Claude Code, Cursor, and other MCP clients. It works with no API
keys through keyless providers, and users can add their own free provider keys to
unlock more models and higher limits. The server exposes direct MCP tools for
single-model asks, multi-model panels, maximum fan-out `tokenmax`, routing
explanations, model discovery, quota status, and lifetime stats.

## Links

- Repository: https://github.com/0xzr/freellmpool
- Docs: https://0xzr.github.io/freellmpool/
- MCP docs: https://github.com/0xzr/freellmpool/blob/main/docs/MCP.md
- Package: https://pypi.org/project/freellmpool/
- Manifest: https://github.com/0xzr/freellmpool/blob/main/server.json

## Notes

- Transport: stdio.
- No required secrets for first use.
- Optional provider keys are read from the local environment only.
- Prompts are routed to whichever free provider/model serves the selected tool
  call; see FAQ for provider/privacy notes.
