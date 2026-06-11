# freellmpool MCP server

## Name

freellmpool

## Repository

https://github.com/0xzr/freellmpool

## Website / docs

- https://0xzr.github.io/freellmpool/
- https://github.com/0xzr/freellmpool/blob/main/docs/MCP.md
- https://github.com/0xzr/freellmpool/blob/main/server.json

## Description

freellmpool is a local stdio MCP server that lets MCP clients use pooled free LLM
provider tiers. It works with no API keys through keyless providers, and users
can add their own free-tier provider keys to unlock more models and higher
limits.

## Features

- Ask one free model with `free_llm_ask`.
- Compare multiple model answers with `free_llm_panel`.
- Fan out to every available model with `tokenmax`.
- Preview routing decisions without spending a token with `free_llm_route`.
- List available provider/model ids with `free_llm_models`.
- Inspect daily quota usage with `free_llm_quota`.
- Show lifetime free-token stats with `free_llm_stats`.

## Connection information

Recommended package-based config:

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

If already installed:

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

## Security / privacy notes

The MCP server runs locally over stdio. Prompts are sent to the selected free
provider/model for each tool call. Provider keys are optional and remain in the
user's local environment/config.
