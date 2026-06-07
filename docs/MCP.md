# MCP server — give Claude (and other MCP clients) free models

`freellmpool mcp` runs a [Model Context Protocol](https://modelcontextprotocol.io)
server over stdio, so an MCP client — **Claude Desktop, Claude Code, Cursor**, … —
can hand off self-contained subtasks (drafting, summarizing, classifying, quick
lookups) to **free** LLMs instead of spending its own context/quota.

It needs **no extra dependencies and no API keys** — `pip install freellmpool`
and it works (keyless providers). Add keys to unlock more.

## Tools it exposes

| Tool | What it does |
|---|---|
| `free_llm_ask` | Ask a free model (`prompt`, optional `system` / `model` / `provider`). |
| `free_llm_models` | List available `provider/model` ids. |
| `free_llm_quota` | Today's per-provider usage + daily-limit headroom, plus session totals and estimated cost avoided. |

## Claude Desktop

Edit `claude_desktop_config.json` (Settings → Developer → Edit Config):

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

Restart Claude Desktop. Ask it to *"use free_llm_ask to summarize this"* and it
will route to a free model.

## Claude Code

```bash
claude mcp add freellmpool -- freellmpool mcp
```

## Cursor

`~/.cursor/mcp.json` (or Settings → MCP):

```json
{
  "mcpServers": {
    "freellmpool": { "command": "freellmpool", "args": ["mcp"] }
  }
}
```

## Adding provider keys

Pass them through the MCP server's environment, e.g. in the config:

```json
{
  "mcpServers": {
    "freellmpool": {
      "command": "freellmpool",
      "args": ["mcp"],
      "env": { "GROQ_API_KEY": "gsk_...", "CEREBRAS_API_KEY": "csk-..." }
    }
  }
}
```

## Notes

- The server speaks newline-delimited JSON-RPC 2.0 over stdio (the standard MCP
  stdio transport) and is implemented on the Python standard library only.
- `stdout` carries the protocol; freellmpool prints its banner to `stderr`.
