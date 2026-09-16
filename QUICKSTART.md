# Quick Start

One path, start to finish. For the other install options — Claude Code plugin, `uvx` with no
clone, Codex — see [README.md](README.md#install).

## 1. Get an API token

1. Go to <https://www.printful.com/dashboard/api> and create a token.
2. Give it these scopes:
   - **View and manage all orders** (required)
   - **View all store information** (required)
   - **View and manage all store files** (required)
   - **View all store products** (recommended)
3. Choose access level **Account (all stores)** for the most flexibility. An account-level token
   needs `PRINTFUL_STORE_ID` set as well — store-scoped calls are rejected without it.

Full detail, including security notes: [API_TOKEN_SETUP.md](API_TOKEN_SETUP.md).

## 2. Install

```bash
git clone https://github.com/crichalchemist/printful-mcp.git
cd printful-mcp
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

This installs two console scripts into `.venv/bin/`: `printful-mcp` (the MCP server) and
`printful` (the CLI).

## 3. Verify, before wiring anything up

```bash
.venv/bin/printful --version
.venv/bin/python -m printful_mcp --help
.venv/bin/python -m pytest
```

The last command runs the offline suite. It needs no network and no credentials; if it passes,
the install is sound. Use `.venv/bin/python -m pytest`, not a bare `pytest` — a bare invocation
runs whichever interpreter is first on `PATH`, which is usually not this one.

## 4. Give it your token

```bash
cp .env.example .env
```

Put your token in `.env` as `PRINTFUL_API_KEY=...`, plus `PRINTFUL_STORE_ID=...` if your token
is account-level. `.env` is git-ignored. **Never paste or commit the token.**

`printful config get` confirms a token is in place without printing it — it shows only the last
four characters.

## 5. Point your client at it

Use an **absolute path** to the interpreter you just installed into. A bare `python` resolves
against `PATH` and is the most common reason a working install does not start under an MCP
client.

**Cursor** — `~/.cursor/mcp.json`, or a workspace `.cursor/mcp.json`.
**Claude Desktop** — `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS.

```json
{
  "mcpServers": {
    "printful": {
      "command": "/absolute/path/to/printful-mcp/.venv/bin/printful-mcp",
      "env": {
        "PRINTFUL_API_KEY": "paste-your-api-key-here"
      }
    }
  }
}
```

Restart the client.

## 6. Try it

In the client:

- "Show me available t-shirts in the catalog" → `printful_list_catalog_products`
- "Get details for product 71" → `printful_get_product`
- "What's the price for variant 4011?" → `printful_get_variant_prices`
- "What countries does Printful ship to?" → `printful_list_countries`

Or in the terminal, against the same core:

```bash
printful ship countries
printful catalog products --help
```

## What runs on which API version

**v2** — catalog, orders, shipping, mockups, files, store statistics.
**v1** — sync products, store/product templates, tax rates. These are the endpoints v2 has no
equivalent for; each builder declares its own version, and nothing switches at runtime.

There are no webhook tools.

## If something is wrong

**The server does not appear in the client.** Restart it completely. Check that `command` is an
absolute path — verify with `ls -l /absolute/path/to/printful-mcp/.venv/bin/printful-mcp`.

**"PRINTFUL_API_KEY environment variable is required".** The client does not inherit your
shell; the key must be in the `env` block of the server entry. In JSON the value is a bare
string — no extra quotes inside it.

**"This endpoint requires 'store_id'!".** Your token is account-level. Set
`PRINTFUL_STORE_ID` too.

**"Rate limit exceeded".** Wait — do not retry in a loop. The server raises on the first 429
and deliberately does not retry, because a silent retry against the mockup endpoint is what
causes Printful's 60-second lockout. New stores are limited to 2 mockup requests per 60
seconds.

More, including the tool list and the testing traps: [README.md](README.md).
