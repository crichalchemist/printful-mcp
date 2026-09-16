# printful

A command-line harness for the [Printful](https://www.printful.com) print-on-demand
API. Browse the catalog, build and place orders, calculate shipping, and generate
mockups from the shell or from an agent — with a REPL for multi-step work.

Built with the [cli-anything](https://github.com/cli-anything) methodology. The
"software" this harness wraps is the hosted Printful REST API; every command calls
the live API.

## ⚠️ This CLI can spend real money

`orders confirm` submits an order for fulfillment and **charges your Printful
account**. `orders cancel` is destructive. Both refuse to run without an explicit
`--yes` on that invocation. There is no persistent "always allow" setting.

Creating an order (`orders create`, `draft submit`) only produces a **draft**, which
is not charged.

## Prerequisites

- Python 3.10+
- A Printful API token — create one at
  <https://www.printful.com/dashboard/api>

Printful private tokens **expire and cannot be refreshed**; when one lapses you must
generate a new one.

## Installation

```bash
git clone https://github.com/crichalchemist/printful-mcp.git
cd printful-mcp
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

That installs two console scripts into `.venv/bin/`: `printful-mcp` and `printful`.
This README uses `printful`.

**Every runnable command in this README spells out `.venv/bin/`**, because that is what
works immediately after the block above — the install does not put anything on your
`PATH`. If you prefer, `source .venv/bin/activate` once and drop the prefix everywhere;
the two forms are equivalent, and this document picks the explicit one so nothing depends
on shell state. (Where a subcommand is named in passing, such as `store use`, it is a name
rather than something to paste.)

Verify it:

```bash
.venv/bin/printful --version
```

## Configuration

Credentials resolve in this order: `--api-key` flag → `PRINTFUL_API_KEY` env var →
config file.

```bash
# Option 1: environment
export PRINTFUL_API_KEY=your-token

# Option 2: stored config (written 0600 to ~/.config/printful/config.json)
.venv/bin/printful config set api_key your-token

# Account-level tokens only: set the store context (sends X-PF-Store-Id)
.venv/bin/printful config set store_id 12345
```

Store-level tokens already carry their store context and need no store ID.

**Account-level tokens must choose a store** before orders, shipping rates, or cost
estimates will work — otherwise every one returns `This endpoint requires store_id!`.
Pick one interactively:

```bash
.venv/bin/printful store use
#   #  ID        Name                    Type
#   1  12345678  Example Store           native
#   2  23456789  Example Store 2         storenvy
#   3  34567890  Example Store 3         square
# Select a store [1-3]:

# Or set it directly and make it the default
.venv/bin/printful store use 23456789 --save
```

With `--json`, or when stdin is not a terminal, the picker does not prompt — it
returns the store list and an instruction, so scripts and agents never hang.

Check it works:

```bash
.venv/bin/printful test
```

## Usage

Running with no subcommand opens the REPL:

```bash
.venv/bin/printful
```

One-shot commands:

```bash
# Browse
.venv/bin/printful catalog products --limit 5
.venv/bin/printful catalog product 71
.venv/bin/printful catalog variants 71 --limit 5
.venv/bin/printful catalog variant-price 4012
.venv/bin/printful catalog size-guide 71 --unit inches

# Build an order step by step (artwork is required to place the order)
.venv/bin/printful draft recipient --name "Jane Doe" --address1 "1 Main St" \
    --city Austin --state-code TX --country-code US --zip 78701
.venv/bin/printful draft add-item --variant-id 4012 --quantity 2 \
    --image-url https://example.com/art.png
.venv/bin/printful draft show

# Price it before committing to anything
.venv/bin/printful ship rates
.venv/bin/printful orders estimate

# Create a DRAFT order (not charged)
.venv/bin/printful draft submit

# Confirm it — THIS CHARGES YOUR ACCOUNT
.venv/bin/printful orders confirm 12345678 --yes
```

Every command supports `--json`:

```bash
.venv/bin/printful --json catalog products --limit 3 | jq '.products[].id'
```

`--dry-run` suppresses session writes and, for mutating commands, prints the request
that would have been sent instead of sending it:

```bash
.venv/bin/printful --dry-run orders confirm 12345678 --yes
```

## Command groups

| Group | Commands |
|---|---|
| `catalog` | `products`, `product`, `variants`, `variant-price`, `availability`, `categories`, `category`, `size-guide` |
| `orders` | `list`, `get`, `create`, `update`, `cancel`, `confirm`, `estimate`, `items`, `shipments` |
| `ship` | `rates`, `countries`, `tax` |
| `mockup` | `create`, `status`, `styles`, `templates` |
| `files` | `add`, `get`, `list` |
| `store` | `list`, `stats`, `templates`, `use` (interactive picker) |
| `sync` | `products`, `get` |
| `draft` | `show`, `recipient`, `add-item`, `remove-item`, `clear`, `submit` |
| `session` | `status`, `draft`, `history`, `clear` |
| `config` | `set`, `get`, `delete`, `path` |
| `test` | connectivity check |

## Things the API itself limits

- **Mockup generation is rate limited far harder than anything else** — 10 requests
  per 60s for established stores, **2 per 60s for new stores**, with a 60-second
  lockout when exceeded, plus a 20,000-file/24h account cap. This CLI surfaces `429`
  with the `Retry-After` value rather than retrying, so you see the limit instead of
  being walked into a lockout.
- **General rate limit** is 120 requests per 60 seconds.
- **There is no "list files" endpoint** in either API version — Printful exposes only
  "add file" and "get file by ID". `files list` therefore shows files added *through
  this CLI*, read from the session record, and labels itself as session-local.
- **Cost estimation and mockup generation are asynchronous**; both commands can poll
  for you (`orders estimate`, `mockup create --wait`).
- **Store statistics** cannot span more than 6 months.
- **Every order item needs artwork.** Printful rejects a catalog order item with no
  `placements` — there is nothing to print. Shipping rates are the exception and can
  be quoted before a design exists, so `draft show` reports `priceable` and
  `complete` separately:

  ```bash
  .venv/bin/printful draft add-item --variant-id 4012 --quantity 2
  # priceable: true, complete: false, items_without_design: 1

  .venv/bin/printful draft add-item --variant-id 4012 --quantity 2 \
      --image-url https://example.com/art.png
  # priceable: true, complete: true
  ```
- **`/v2/countries` is paginated** at 20 of 239 rows, and `US` is not on the first
  page. `ship countries` fetches every page, so the list is complete.
- **The v2 error format is not what the docs say.** They describe RFC 9457
  (`detail`/`title`); the live API returns `{"data": "...", "error": {"message": ...}}`.
  This CLI reads both, so API errors surface with their real text rather than
  "Unknown error".

## API versions

v2 is primary. v1 is used only where v2 has no equivalent: tax rates
(`ship tax`), product templates (`store templates`), and sync products (`sync`).
The backend normalizes the two versions' different success and error envelopes.

## Session state

State lives in `~/.config/printful/session.json` (override with `--session`)
and holds the draft order, the active store, file records, and command history.
A session file left at the old `~/.cli-anything-printful/session.json` is no
longer read; move it across by hand if you want to keep it.
One-shot mutations auto-save; `--dry-run` suppresses that. Writes use an exclusive
file lock.

```bash
.venv/bin/printful session status
.venv/bin/printful session history --limit 5
.venv/bin/printful session clear
```

## Running the tests

```bash
.venv/bin/pip install -e ".[dev]"

# Unit tests — no API key, no network
.venv/bin/python -m pytest src/printful_cli/tests/test_core.py -v

# This CLI's tests including live API calls
export PRINTFUL_API_KEY=your-token
export PRINTFUL_STORE_ID=23456789        # required for an account-level token
PRINTFUL_FORCE_INSTALLED=1 .venv/bin/python -m pytest src/printful_cli/tests/ -v -s
```

Use `.venv/bin/python -m pytest`, never a bare `pytest` — a bare invocation resolves to
whichever interpreter is first on `PATH` rather than this project's venv, and the failures
that follow look like broken guards rather than a wrong interpreter. The last line passes a
directory, so it collects this package's tests only; it does not stand in for the whole
repository's suite, which is `.venv/bin/python -m pytest` with no path. See the repository
root `CLAUDE.md` for both rules in full.

The live E2E tests deliberately never confirm or cancel a real order. See
`tests/TEST.md` for the full plan, the reasoning, and the recorded coverage gaps.

## Relationship to the MCP server in this repo

The parent repository is an MCP server exposing the same API to AI assistants. This
CLI is a separate, self-contained package: it shares no code with `src/printful_mcp/`
so that it can be installed and published on its own. It covers the MCP's surface
plus order update/cancel/estimate, categories, size guides, tax, and templates.
