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
| `free_llm_ask` | Ask a free model (`prompt`, optional `system` / `model` / `provider` / `routing` / `max_tokens`). The reply names the serving model. |
| `free_llm_panel` | Ask the **same** prompt to N different free models at once and compare — a free second opinion / ensemble. Optional `synthesize` merges them into one best answer. |
| `tokenmax` | 🌈 Gloriously excessive: blast the prompt to **every** free model across **every** provider at once, then the **calling** model synthesizes them all. Emits live `notifications/progress` (`🌈 TOKENMAXXING ▸ 47/168 models…`) so hosts like Claude Code show it ticking up, and a colorful rainbow banner in the result. Tongue-in-cheek, genuinely useful for hard questions. |
| `free_llm_route` | Explain where a prompt **would** route (estimated difficulty + ranked candidate models) **without spending a token**. |
| `free_llm_models` | List available `provider/model` ids. |
| `free_llm_quota` | Today's per-provider usage + daily-limit headroom, plus session totals and estimated cost avoided. |
| `free_llm_stats` | Lifetime tokens served free + estimated cost avoided vs Claude Opus 4.8 (persists across restarts). |

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
- **Invoke the tools directly.** The `initialize` handshake returns an
  `instructions` field telling the calling agent to call these as MCP tools — **not**
  to shell out to the `freellmpool` CLI as a subprocess. Subprocessing captures the
  output inside the agent's process and hides `tokenmax`'s live progress, the rainbow
  banner, and the answers from the user.
- **Want the *visible* rainbow animation?** An MCP tool can't paint a live animation in
  the host chat (stdout is the protocol, stderr is logged, results strip ANSI) — the
  `tokenmax` `notifications/progress` status line is the ceiling here. For a genuine
  in-harness graphic, use the **OpenCode embedded TUI plugin** (`integrations/opencode-tui`),
  whose panel throbs a live rainbow `TOKENMAXXING` animation; or run `freellmpool tokenmax`
  in a real terminal for the standalone flash.
- **Live `tokenmax` progress:** when a client passes a `progressToken` (Claude
  Code does), `tokenmax` streams `notifications/progress` as each model answers, so
  you see the swarm tick up in real time. Raw ANSI can't animate inside an MCP
  host's chat, so progress + a rainbow emoji banner are how the spectacle "comes
  through" there. For the **genuine** flashing rainbow animation, run it in a real
  terminal: `freellmpool tokenmax "your question"` (it also prints every answer and
  a synthesized verdict).
