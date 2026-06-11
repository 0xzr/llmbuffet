# Glama Submission Copy

## GitHub repository

https://github.com/0xzr/freellmpool

## Name

freellmpool

## Category suggestions

- AI & Machine Learning
- Coding Agents
- Developer Tools

## Install command

```json
{
  "command": "uvx",
  "args": ["freellmpool", "mcp"]
}
```

## Description

freellmpool is a local stdio MCP server that lets Claude Desktop, Claude Code,
Cursor, and other MCP clients offload subtasks to pooled free LLM tiers. It
works with no API keys through keyless providers, supports optional user-owned
free-tier keys, and exposes tools for single asks, model panels, tokenmax
fan-out, routing previews, model listing, quota status, and lifetime stats.

## Tool names

- `free_llm_ask`
- `free_llm_panel`
- `tokenmax`
- `free_llm_route`
- `free_llm_models`
- `free_llm_quota`
- `free_llm_stats`

## Maintainer notes

The server runs locally and speaks MCP over stdio. It does not store provider
secrets. Optional provider keys are read from environment variables or local
config. See `FAQ.md` for provider prompt-destination and ToS notes.
