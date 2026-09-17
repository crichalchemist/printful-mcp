# Installing the Printful MCP server in Codex

Two paths. The `config.toml` entry is the one this repository can point at a
documented, worked example; the plugin manifest beside this file is the newer
surface and is described below with the caveats that apply to it.

## Path 1 — a `config.toml` MCP server entry

Add this to `~/.codex/config.toml`:

```toml
[mcp_servers.printful]
command = "uvx"
args = ["--from", "git+https://github.com/Purple-Horizons/printful-mcp@main", "printful-mcp"]
env_vars = ["PRINTFUL_API_KEY", "PRINTFUL_STORE_ID"]
```

`env_vars` forwards variables already exported in your shell. To set a literal
value in the config instead, use the `env` sub-table:

```toml
[mcp_servers.printful.env]
PRINTFUL_API_KEY = "your-token"
```

**Codex does not expand `${PRINTFUL_API_KEY}` the way the repository's
`.mcp.json` does.** That placeholder syntax is a Claude Code feature; on Codex
you name the variable in `env_vars` or give a literal in `env`.

`PRINTFUL_STORE_ID` is optional and only needed for an account-level
(multi-store) token — see `docs/api-token-setup.md`.

Source: <https://developers.openai.com/codex/mcp>

## Path 2 — the plugin manifest

`.codex-plugin/plugin.json` describes this repository as a Codex plugin in the
**compatibility layout**: the manifest at `.codex-plugin/plugin.json`, with
`.mcp.json` and `skills/` at the repository root.

The manifest's field set follows the published sample spec —
<https://github.com/openai/codex/blob/main/codex-rs/skills/src/assets/samples/plugin-creator/references/plugin-json-spec.md>
— and only uses fields documented there: `name`, `version`, `description`,
`author`, `repository`, `license`, `keywords`, `skills`, `mcpServers` and
`interface`.

The compatibility layout was chosen over the portable Agent Plugins layout
deliberately. OpenAI's packaging guide says of the compatibility scaffold that
"The scaffold remains supported", and warns that moving to the portable layout
is not a rename: "Don't just rename `.mcp.json`: the portable MCP format also
declares a transport `type` for each server." Converting would mean writing a
second, differently-shaped MCP file; the repository ships one `.mcp.json` that
both Claude Code and this manifest reference.

**That shared `.mcp.json` is where Path 1's `${PRINTFUL_API_KEY}` caveat bites,
so it is repeated here.** The manifest's `mcpServers` points at `.mcp.json`,
whose `env` block holds `"${PRINTFUL_API_KEY}"` — a placeholder Codex passes
through literally rather than expanding. Supply the token the way Path 1
describes, with `env_vars` or an `env` literal, rather than relying on the
manifest to resolve it.

Source: <https://developers.openai.com/codex/plugins/build>

## Path 3 — no plugin at all

The server is an ordinary Python console script. `pip install -e .` in a clone,
export `PRINTFUL_API_KEY`, and run `printful-mcp`. See `docs/quickstart.md`.
