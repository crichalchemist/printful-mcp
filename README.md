<div align="center">

# Printful MCP Server

### Automate your print-on-demand business with AI

Connect Printful's API to Claude, Cursor, Codex and other MCP clients — and to your terminal.

[**Install**](#install) • [**Configure**](#configuration) • [**Tools**](#the-32-mcp-tools) • [**CLI**](#the-cli) • [**Quick start**](QUICKSTART.md)

---

[![Made by Purple Horizons](https://img.shields.io/badge/Made_by-Purple_Horizons-7C3AED?style=for-the-badge&logo=data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjQiIGhlaWdodD0iMjQiIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cGF0aCBkPSJNMTIgMkw2IDhMMTIgMTRMMTggOEwxMiAyWiIgZmlsbD0id2hpdGUiLz48cGF0aCBkPSJNMTIgMTBMMTggMTZMMTIgMjJMNiAxNkwxMiAxMFoiIGZpbGw9IndoaXRlIi8+PC9zdmc+)](https://purplehorizons.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Printful API v2](https://img.shields.io/badge/Printful-API_v2-00A3FF?style=for-the-badge)](https://developers.printful.com/docs/v2-beta/)

---

### New to Printful?

<a href="https://www.printful.com/a/purplehorizons">
  <img src="https://img.shields.io/badge/Sign_Up-Get_Started_Free-FA4616?style=for-the-badge&logo=printful&logoColor=white" alt="Sign up for Printful">
</a>

<sub>No upfront costs • Global fulfillment • Uses Purple Horizons' referral link</sub>

---

</div>

## About this fork

This is a fork of [**Purple-Horizons/printful-mcp**](https://github.com/Purple-Horizons/printful-mcp)
by [Purple Horizons](https://purplehorizons.io) / [Gianni D'Alerta](https://giannidalerta.com),
kept under the same [MIT License](LICENSE). The original is the reason this exists and the
attribution above is deliberate.

What this fork changes:

- **One shared core.** The MCP server and the CLI were two codebases with two HTTP clients, two
  error parsers and two paginators. They now sit on `src/printful_core/`, so a fix lands once.
- **A CLI.** `printful` is a second surface over the same core — see [The CLI](#the-cli).
- **More tools, and a test that counts them.** See [below](#the-32-mcp-tools).
- **Documentation checked against the code.** Every command here was checked against the source
  and its `--help` output, and most were run before being written down. The ones that call the
  live Printful API, charge the account, or need an interactive host are **marked in place**
  rather than run — look for *not run here* beside them.

Install instructions below point at this fork, because that is where this code lives. Changes
worth having are offered upstream.

---

## Install

### Prerequisites

- **Python 3.10+** ([download](https://www.python.org/downloads/))
- **A Printful API token** ([get one](https://www.printful.com/dashboard/api)) — see
  [API_TOKEN_SETUP.md](API_TOKEN_SETUP.md) for scopes

### Option 1 — Claude Code plugin

This repository is both a plugin and the marketplace that serves it
(`.claude-plugin/marketplace.json`, `.claude-plugin/plugin.json`). Inside Claude Code:

```text
/plugin marketplace add crichalchemist/printful-mcp
/plugin install printful-mcp@printful-mcp
```

The plugin brings the MCP server (via `.mcp.json`) and two skills — one for the MCP tools, one
for the CLI.

*Not run here — these are Claude Code slash commands, not shell commands. The manifests they
read were verified by reading them.*

### Option 2 — `.mcp.json`, no clone

`.mcp.json` in this repository runs the server straight from git with `uvx`; copy it into your
own project, or use it as the shape of an entry in your client's config:

```json
{
  "mcpServers": {
    "printful": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/crichalchemist/printful-mcp@dev",
        "printful-mcp"
      ],
      "env": {
        "PRINTFUL_API_KEY": "${PRINTFUL_API_KEY}"
      }
    }
  }
}
```

**Two things to know about that ref, both true today:**

- It pins `@dev`, a **moving branch**, not a release tag — you get whatever is on `origin/dev`
  at the moment `uvx` resolves it, which is not necessarily what you see in this working tree.
  It becomes `@main` once the open pull request merges.
- `${PRINTFUL_API_KEY}` is **Claude Code's** expansion syntax. Codex does not expand it — use
  the Codex section below instead.

### Option 3 — clone and install

The path with no resolver between you and the code:

```bash
git clone https://github.com/crichalchemist/printful-mcp.git
cd printful-mcp
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

That installs two console scripts into `.venv/bin/`: `printful-mcp` and `printful`.

**Every runnable command in this README spells out `.venv/bin/`**, because that is what works
immediately after the block above — the install does not put anything on your `PATH`. If you
prefer, `source .venv/bin/activate` once and drop the prefix everywhere; the two forms are
equivalent, and this document picks the explicit one so nothing depends on shell state. (Where a
subcommand is named in passing, such as `printful test`, it is a name rather than something to
paste.)

Point your client at that interpreter too — a bare `python` resolves against `PATH` and is the
single most common reason a working install does not start under an MCP client:

```json
{
  "mcpServers": {
    "printful": {
      "command": "/absolute/path/to/printful-mcp/.venv/bin/printful-mcp",
      "env": {
        "PRINTFUL_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

For Cursor that file is `~/.cursor/mcp.json`; for Claude Desktop it is
`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS.
`cursor-mcp-config.json` in this repository is an older sample of the same entry. It uses a bare
`"command": "python"` with a `cwd` — the exact `PATH` trap described above — so change the
command to an absolute path before using it.

### Option 4 — Codex

Codex has no `${VAR}` expansion, so name the variables instead of interpolating them. In
`~/.codex/config.toml`:

```toml
[mcp_servers.printful]
command = "uvx"
args = ["--from", "git+https://github.com/crichalchemist/printful-mcp@dev", "printful-mcp"]
env_vars = ["PRINTFUL_API_KEY", "PRINTFUL_STORE_ID"]
```

`env_vars` forwards variables already exported in your shell. The full Codex story, including
the `.codex-plugin/` manifest and why the compatibility layout was chosen, is in
[.codex-plugin/INSTALL.md](.codex-plugin/INSTALL.md).

---

## Configuration

| Variable | Required | Purpose |
|---|---|---|
| `PRINTFUL_API_KEY` | yes | Your Printful API token |
| `PRINTFUL_STORE_ID` | only for account-level tokens | Sent as `X-PF-Store-Id` on every request |

Without `PRINTFUL_API_KEY` the server refuses to start rather than failing later:

```console
$ .venv/bin/python -m printful_mcp
Error: PRINTFUL_API_KEY environment variable is required
Get your API key from: https://www.printful.com/dashboard/api
$ echo $?
1
```

For local development, copy the example file and fill it in:

```bash
cp .env.example .env
```

A token can live in two independent places, and **they do not see each other**:

- **`.env` or the environment** — what the MCP server reads.
- **`~/.config/printful/config.json`** — written by `.venv/bin/printful config set api_key
  <token>`, read by the CLI. `.venv/bin/printful config path` prints its location.

Resolution order is explicit argument, then `PRINTFUL_API_KEY`, then that config file. So
`.venv/bin/printful config get` reports `No config set.` when your token is in `.env` — that is
the config file being empty, not a missing key.

To confirm either one without printing the value:

```bash
grep -c '^PRINTFUL_API_KEY=.' .env        # 1 when .env carries it
.venv/bin/printful config get             # reads the config file; masks all but the last 4 chars
```

**Never echo, paste or commit the token.** `.env` is git-ignored; keep it that way.

---

## Transports

stdio is the default and is what Cursor, Claude Desktop and Claude Code use.

| Transport | Use case | Command |
|---|---|---|
| `stdio` (default) | Cursor, Claude Desktop, Claude Code | `.venv/bin/python -m printful_mcp` |
| `http` | HTTP clients, mcporter | `.venv/bin/python -m printful_mcp --transport http` |
| `sse` | Legacy SSE clients | `.venv/bin/python -m printful_mcp --transport sse` |

```bash
.venv/bin/python -m printful_mcp --transport http --port 8000   # streamable-http on /mcp
.venv/bin/python -m printful_mcp --transport http --host 0.0.0.0 --port 8080
```

Run `.venv/bin/python -m printful_mcp --help` for the authoritative list of flags and defaults.

**With mcporter,** pass arguments as JSON — this is why the tools take flattened string
parameters (`items_json`, `variant_ids`) rather than nested objects; typed and nested
parameters do not survive HTTP-to-stdio bridges:

```bash
mcporter call printful_mcp.printful_list_catalog_products --args '{"limit":20}'
```

*Not run here — mcporter is a separate tool and this call hits the live API. The reason behind
it is verified: the flattened parameters are what `src/printful_mcp/models/inputs.py` declares.*

---

## The 32 MCP tools

**32 tools are registered, one per request builder the core defines.** That number is not
maintained by hand. `src/printful_mcp/tests/test_server.py` asserts the builder-to-tool mapping
in **both directions**, by set difference:

- `test_every_core_endpoint_is_bound_by_a_tool` — a builder with no tool fails by name
- `test_no_tool_calls_an_endpoint_that_does_not_exist` — a tool calling a missing builder fails
- `test_one_registered_tool_per_bound_endpoint` — exactly one registration each

The test's `UNBOUND_ON_PURPOSE` exemption list is currently empty, so "one tool per builder" is
literally true. If you add a builder without a tool, the suite tells you which one. **The count
is a consequence of that mapping, not a target** — if it changes, read the failure rather than
editing a number.

To print the registered names yourself:

```bash
.venv/bin/python -c "import asyncio;from printful_mcp.server import mcp;print(len(asyncio.run(mcp.list_tools())))"
```

<details>
<summary><b>Catalog</b> — browse products, variants, pricing and stock</summary>

`printful_list_catalog_products` · `printful_get_product` · `printful_get_product_variants` ·
`printful_get_variant_prices` · `printful_get_product_availability` · `printful_list_categories` ·
`printful_get_category` · `printful_get_size_guide`

</details>

<details>
<summary><b>Orders</b> — draft, update, estimate, confirm, cancel</summary>

`printful_create_order` · `printful_get_order` · `printful_update_order` ·
`printful_confirm_order` · `printful_cancel_order` · `printful_list_orders` ·
`printful_list_order_items` · `printful_list_order_shipments` ·
`printful_create_estimation_task` · `printful_get_estimation_task`

`printful_confirm_order` submits an order for fulfillment and **charges the account**.
`printful_cancel_order` is likewise irreversible. Both are registered with
`destructiveHint: true` so a client can prompt you first.

</details>

<details>
<summary><b>Shipping and tax</b></summary>

`printful_calculate_shipping` · `printful_list_countries` · `printful_calculate_tax`

</details>

<details>
<summary><b>Mockups</b></summary>

`printful_create_mockup_task` · `printful_get_mockup_task` · `printful_list_mockup_styles` ·
`printful_list_mockup_templates`

</details>

<details>
<summary><b>Files</b></summary>

`printful_add_file` · `printful_get_file`

</details>

<details>
<summary><b>Stores</b></summary>

`printful_list_stores` · `printful_get_store_stats` · `printful_list_store_templates`

</details>

<details>
<summary><b>Sync products</b> — v1, no v2 equivalent</summary>

`printful_list_sync_products` · `printful_get_sync_product`

</details>

Every tool returns a string, and 30 of the 32 take a `format` parameter — `"markdown"` for a
rendered table, `"json"` for the raw payload. Errors come back as readable text, never a
traceback.

The two exceptions are deliberate, and `CLAUDE.md` records both under "Known inconsistencies":

- **`printful_list_countries` takes no parameters at all** — not even `format`.
- **`printful_create_mockup_task`'s `format` is the *image* format**, `"jpg"` or `"png"`. Passing
  `"markdown"` there is a validation error, not a harmless no-op. Do not "fix" this by renaming
  it.

---

## The CLI

`printful` is the same core with a terminal in front of it. Called with no subcommand it opens
an interactive REPL.

```text
$ .venv/bin/printful --help
Commands:
  catalog  Browse the Printful product catalog (v2).
  config   Manage stored credentials and defaults.
  draft    Build an order across multiple commands before submitting it.
  files    File library.
  mockup   Generate and inspect product mockups.
  orders   Manage orders.
  session  Inspect and manage persistent session state.
  ship     Shipping rates, countries, and tax.
  store    Store information and reporting.
  sync     Sync products (v1 — not yet in v2).
  test     Verify credentials against the live API.
```

```bash
.venv/bin/printful catalog products --help   # every group takes --help
.venv/bin/printful ship countries
.venv/bin/printful catalog variants 71
.venv/bin/printful --json orders list        # machine-readable output
```

*Only the `--help` line was run here. **Everything else in that block calls the live Printful
API**, so the invocations were checked against each subcommand's `--help` instead — `ship
countries` takes no arguments, `catalog variants` takes a positional `PRODUCT_ID`, and `--json`
is a top-level flag.*

`orders confirm` and `orders cancel` require an explicit `--yes`, and **`confirm` charges the
account** — neither was run here, nor was `printful test`, which exists to make a live call.

---

## Usage examples

Ask your assistant in plain language; the tool calls below are what it reaches for.

**"Show me all t-shirts available for DTG printing"**

```python
printful_list_catalog_products(types="T-SHIRT", techniques="dtg", limit=20, format="markdown")
```

**"What's the price for variant 4011 in USD?"**

```python
printful_get_variant_prices(variant_id=4011, currency="USD", format="markdown")
```

**"Generate a mockup for product 71 with my design"**

```python
printful_create_mockup_task(
    product_id=71,
    variant_ids="4011,4012",
    design_url="https://example.com/design.png",
    placement="front",
)
```

**"Create a draft order for John Doe"**

`items_json` is required, and every item needs `placements` carrying the artwork — Printful
rejects an order item with no design attached. The parameter takes a JSON array **as text**:

```json
[
  {
    "source": "catalog",
    "catalog_variant_id": 4012,
    "quantity": 1,
    "placements": [
      {
        "placement": "front",
        "technique": "dtg",
        "layers": [{ "type": "file", "url": "https://example.com/art.png" }]
      }
    ]
  }
]
```

```python
printful_create_order(
    recipient_name="John Doe",
    recipient_address1="123 Main St",
    recipient_city="Los Angeles",
    recipient_state_code="CA",
    recipient_country_code="US",
    recipient_zip="90001",
    items_json=items_json,
)
```

This creates a **draft**. Nothing is charged until `printful_confirm_order`.

---

## API version strategy

`Request.version` selects the base URL and the transport unwraps the response.

**v2** (`https://api.printful.com/v2`) is the default and covers catalog, orders, shipping,
mockups, files and store statistics. **v1** is used only where v2 has no equivalent: sync
products, product templates and tax rates. v1 responses are unwrapped from
`{"code": ..., "result": ...}` down to `result`.

There is no automatic version negotiation — each endpoint builder declares the version it
needs.

---

## Rate limits

Printful's general limit is 120 requests per 60 seconds. Mockup creation is limited far more
tightly: **2 requests per 60 seconds for new stores**, with a 60-second lockout.

**The client does not retry.** On `429` (and `419`) it raises immediately, carrying the wait
time into the error message, and gives up. There is no backoff, no sleep and no retry loop
anywhere in `src/printful_core/transport.py`.

This is deliberate, and it is the behavior you want: a silent retry against the mockup endpoint
is exactly what walks you into the 60-second lockout. Your client sees the limit and can decide
what to do, which is a decision a library should not make for you.

The wait time comes from Printful's `Retry-After` header when it sends one, and falls back to
60 seconds when it does not — so treat the number as a floor, not a promise. Requests time out
after 30 seconds.

---

## Troubleshooting

<details>
<summary><b>"PRINTFUL_API_KEY environment variable is required"</b></summary>

The key is not reaching the process. Check the source you actually used, without printing the
value:

```bash
grep -c '^PRINTFUL_API_KEY=.' .env        # 1 when .env carries it
.venv/bin/printful config get             # reads the CLI config file, which is not .env
```

Under an MCP client neither file may be involved: the client does not inherit your shell, so
the key must be in the `env` block of the server entry. In JSON the value is a bare string with
no extra quotes inside it.

</details>

<details>
<summary><b>"Rate limit exceeded"</b></summary>

Stop and wait; do not retry in a loop. The error carries the wait time. If you hit this on
mockups, note the new-store limit of 2 requests per 60 seconds and pause between bulk
operations.

</details>

<details>
<summary><b>"This endpoint requires 'store_id'!"</b></summary>

Your token is account-level. Export `PRINTFUL_STORE_ID` (or pass `--store-id`) so the
`X-PF-Store-Id` header is sent. See [API_SCOPES_REFERENCE.md](API_SCOPES_REFERENCE.md).

</details>

<details>
<summary><b>"Resource not found"</b></summary>

Check the ID. Orders accept external IDs prefixed with `@` (`@my-order-123`). Verify the
resource belongs to the store the token is scoped to.

</details>

<details>
<summary><b>The server starts in a terminal but not in the client</b></summary>

Almost always a `PATH` problem: `"command": "python"` resolves to whichever interpreter the
client happens to find, which is usually not the one you installed into. Use an absolute path
to `.venv/bin/printful-mcp`.

</details>

<details>
<summary><b>Mockup generation stuck on "pending"</b></summary>

Generation is asynchronous; poll `printful_get_mockup_task`. Verify the design URL is publicly
reachable. A task still pending after a couple of minutes has most likely failed.

</details>

---

## Testing

```bash
.venv/bin/python -m pytest              # offline suite — no network, no credentials
.venv/bin/python -m pytest -m live      # live API suite — not run here, spends real requests
.venv/bin/python -m pytest -m ""        # everything — not run here, includes the live suite
```

Only the first line is run in preparing this document. The offline suite is the one that
matters for "is my install sound"; the other two cost real API requests.

Two traps, both of which have cost real time:

**Use `.venv/bin/python -m pytest`, not a bare `pytest`.** A bare invocation runs whichever
interpreter comes first on `PATH`, which is usually not the one holding this project's
dependencies. What breaks is machine-specific — a plugin registered in some other
interpreter's global site-packages can abort collection before a single test runs, and the
traceback that follows is about that interpreter, not about this repository.

**`env -u PRINTFUL_API_KEY pytest` does not prove the offline suite is credential-free.**
`server.py` calls `load_dotenv()` at import, so a `.env` in the repository root puts the
variable straight back the moment any test imports the server, and the run passes for the wrong
reason. Take `.env` out of the picture instead:

```bash
mv .env .env.aside && .venv/bin/python -m pytest -q; mv .env.aside .env
```

Note the `;` before the restore, so `.env` comes back even when the suite fails.

**Do not pass a directory path to run "the suite."** A path argument overrides `testpaths`, so
`pytest tests/` collects a handful of cases, reports them as passing, and runs none of the MCP
adapter tests. A path to a single file is fine when you mean it.

Live tests are excluded from the default selection by `addopts = "-m 'not live'"` so a fresh
clone gets a clean result. They are not softened: selected without credentials they fail loudly
rather than skip. The live suite needs `PRINTFUL_STORE_ID` exported as well as
`PRINTFUL_API_KEY`. `printful_confirm_order` is never exercised against the live API — it
charges a real account, and is asserted only against fake transports.

For an interactive tool browser:

```bash
export PRINTFUL_API_KEY=your-key
./test-with-inspector.sh          # npx @modelcontextprotocol/inspector, UI on :5173
```

*Not run here — it launches an interactive browser UI.* Note that the script spawns a bare
`python -m printful_mcp`, so it hits the same `PATH` trap as `cursor-mcp-config.json` above:
either activate the venv first, or edit the script to use `.venv/bin/python`.

[CLAUDE.md](CLAUDE.md) carries the full working notes for this repository.

---

## Project structure

```text
printful-mcp/
├── src/
│   ├── printful_core/        what a Printful call IS (no I/O except transport.py)
│   │   ├── request.py        Request: a frozen description of an un-sent call
│   │   ├── endpoints/        pure functions returning a Request — no I/O
│   │   ├── transport.py      SyncTransport / AsyncTransport — the only network module
│   │   ├── errors.py         PrintfulError and envelope normalization for both versions
│   │   ├── auth.py           Credentials.resolve()
│   │   ├── pagination.py     page arithmetic as pure functions
│   │   ├── polling.py        poll an async task until it leaves "pending"
│   │   └── format/           markdown.py for the MCP tools, summary.py for the CLI
│   ├── printful_mcp/         MCP server — async, returns str
│   │   ├── server.py         the MCP surface: 32 @mcp.tool delegates, no business logic
│   │   ├── tools/            one module per domain
│   │   ├── models/inputs.py  one Pydantic model per tool
│   │   └── transport.py      lazily-initialized transport, closed via atexit
│   └── printful_cli/         Click CLI — sync, prints tables
├── skills/                   printful-mcp and printful-cli skills (symlinked SKILL.md)
├── .claude-plugin/           plugin.json and marketplace.json
├── .codex-plugin/            plugin.json and INSTALL.md
├── .mcp.json                 uvx-based zero-install server entry
├── scripts/bump-version.sh   version bump across the manifests
├── pyproject.toml
└── LICENSE
```

Tests live beside the code they test, in `src/*/tests/`.

---

## Contributing

Issues and pull requests are welcome on
[this fork](https://github.com/crichalchemist/printful-mcp/issues). Changes that belong
upstream are offered to [Purple-Horizons/printful-mcp](https://github.com/Purple-Horizons/printful-mcp).

Before opening a pull request:

```bash
.venv/bin/python -m pytest
.venv/bin/python -m ruff check src/
.venv/bin/python -m ruff format --check src/
```

Those are scoped to `src/`, which is clean, because the repository-wide form is not clean yet:
`ruff check .` reports two findings in `tests/test_create_order.py`, and `ruff format --check .`
would reformat that file plus three planning documents under `docs/superpowers/plans/`. Those
are known and are being cleaned up separately — do not treat them as something your change
broke, and do not fix them in an unrelated pull request.

Adding an MCP tool means touching three files, in this order: `models/inputs.py`,
`tools/<domain>.py`, then a delegate in `server.py`. The parity test will tell you if you
missed one.

---

## Resources

| Resource | Link |
|---|---|
| Printful API v2 docs | [developers.printful.com/docs/v2-beta](https://developers.printful.com/docs/v2-beta/) |
| Printful API v1 docs | [developers.printful.com/docs](https://developers.printful.com/docs/) |
| MCP specification | [modelcontextprotocol.io](https://modelcontextprotocol.io/) |
| MCP Python SDK | [github.com/modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk) |
| Upstream project | [Purple-Horizons/printful-mcp](https://github.com/Purple-Horizons/printful-mcp) |
| Purple Horizons | [purplehorizons.io](https://purplehorizons.io) |
| Gianni D'Alerta | [giannidalerta.com](https://giannidalerta.com) |

Also in this repository: [QUICKSTART.md](QUICKSTART.md),
[API_TOKEN_SETUP.md](API_TOKEN_SETUP.md), [API_SCOPES_REFERENCE.md](API_SCOPES_REFERENCE.md),
[CLAUDE.md](CLAUDE.md).

---

## License

**MIT** — see [LICENSE](LICENSE). Original work © Purple Horizons LLC.

---

<div align="center">

### Support this project

Star the repo · share it · contribute · or sign up for Printful through the referral link
below, which supports the upstream author.

<a href="https://www.printful.com/a/purplehorizons">
  <img src="https://img.shields.io/badge/Try_Printful-Start_Free-FA4616?style=for-the-badge&logo=printful&logoColor=white" alt="Try Printful">
</a>

<br><br>

**Originally made by [Purple Horizons](https://purplehorizons.io)**

</div>
