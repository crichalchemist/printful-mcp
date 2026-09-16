---
name: "printful"
description: "Command-line interface for the Printful print-on-demand API — browse the catalog, build and place orders, calculate shipping and tax, and generate mockups. Includes guards on billable operations."
---

# printful

A command-line harness for the [Printful](https://www.printful.com) print-on-demand
API. Browse the catalog, build and place orders, calculate shipping, and generate
mockups from the shell or from an agent — with a REPL for multi-step work.

The backend is the hosted Printful REST API (v2, with v1 fallback for tax, product
templates, and sync products). Most commands make a live API call. The purely local
exceptions are the `session` and `config` groups, `files list`, and the `draft`
group **except `draft submit`** — building a draft is local, but submitting it
posts the order to Printful (it creates a DRAFT, so nothing is charged).

`--dry-run` suppresses the call for the commands that *write*: `orders create`,
`update`, `cancel`, `confirm` and `estimate`, plus `mockup create` and `files add`
— and `draft submit`, which routes through `orders create`'s gate.
It does not make read commands offline — `catalog products --dry-run` still queries
the API. It also skips the session auto-save, so a dry run leaves no trace in the
session file.

## ⚠️ Read this before running any command

**`orders confirm` submits an order to production and CHARGES the account with real
money.** `orders cancel` is destructive. Both refuse to run without an explicit
`--yes` on that invocation, and there is no persistent override.

An agent must not pass `--yes` on its own initiative. Treat it as requiring the
human's express instruction for that specific order. When unsure, use `--dry-run`,
which prints the request that would be sent and makes no network call.

`orders create` and `draft submit` produce a **draft**, which is not charged — those
are safe to run.

## Installation

```bash
pip install printful-mcp
```

**Prerequisites:**
- Python 3.10+
- A Printful API token from <https://www.printful.com/dashboard/api>

There is nothing to install locally beyond the package — Printful is a hosted
service, not a local application. Note that Printful private tokens **expire and
cannot be refreshed**; a lapsed token must be regenerated.

## Configuration

Credentials resolve as: `--api-key` flag → `PRINTFUL_API_KEY` env → config file.

```bash
export PRINTFUL_API_KEY=your-token
# or
printful config set api_key your-token

# Verify
printful --json test
```

Store-level tokens carry their own store context. **Account-level tokens must
select a store** or every store-scoped endpoint (orders, shipping rates,
estimates) fails with Printful's own store-scope error, whose text mentions
`store_id`:

```bash
# Non-interactive: returns the store list rather than prompting
printful --json store use
# Then set it
printful --json store use 23456789 --save
```

`store use` with no ID prompts interactively **only** when stdin is a terminal.
Under `--json` or in a pipeline it refuses and returns the list, so an agent
never blocks on a prompt.

## Usage

```bash
# Show help
printful --help

# Interactive REPL (default when no subcommand is given)
printful

# JSON output for programmatic use
printful --json catalog products --limit 5

# Preview a mutation without performing it
printful --dry-run orders confirm 12345 --yes
```

## Command Groups

### Catalog

Browse the Printful product catalog (v2).

| Command | Description |
|---------|-------------|
| `products` | List catalog products. |
| `product` | Get details for one catalog product. |
| `variants` | List variants (size/color combinations) for a product. |
| `variant-price` | Get pricing for a catalog variant. |
| `availability` | Get stock availability for a product. |
| `categories` | List catalog categories. |
| `category` | Get one catalog category. |
| `size-guide` | Get the size guide for a product. |

### Orders

Manage orders. `confirm` and `cancel` require --yes.

| Command | Description |
|---------|-------------|
| `list` | List orders. |
| `get` | Get one order. Prefix an external ID with @. |
| `create` | Create a DRAFT order. Drafts are not charged until confirmed. |
| `update` | Update a draft order (PATCH). |
| `cancel` | Cancel an order. DESTRUCTIVE — requires --yes. |
| `confirm` | Confirm an order for fulfillment. CHARGES YOUR ACCOUNT — requires --yes. |
| `estimate` | Estimate order costs without placing an order. Free. |
| `items` | List the items on an order. |
| `shipments` | List shipments for an order. |

### Ship

Shipping rates, countries, and tax.

| Command | Description |
|---------|-------------|
| `rates` | Calculate live shipping rates. |
| `countries` | List countries Printful ships to. |
| `tax` | Calculate a tax rate (v1 — no v2 equivalent exists). |

### Mockup

Generate and inspect product mockups. Tightly rate limited.

| Command | Description |
|---------|-------------|
| `create` | Create a mockup generation task. |
| `status` | Check a mockup generation task. |
| `styles` | List mockup styles available for a product. |
| `templates` | List mockup templates (positional data) for a product. |

### Files

File library. Note: Printful has no list-files endpoint.

| Command | Description |
|---------|-------------|
| `add` | Add a file to the library by URL. |
| `get` | Get file details by ID. |
| `list` | List files added through this CLI (session-local, not a server query). |

### Store

Store information and reporting.

| Command | Description |
|---------|-------------|
| `list` | List stores available to the token. |
| `stats` | Get store statistics. Range cannot exceed 6 months. |
| `templates` | List product templates (v1 — no v2 equivalent). |
| `use` | Set the active store for account-level tokens. |

### Sync

Sync products (v1 — not yet in v2).

| Command | Description |
|---------|-------------|
| `products` | List sync products. |
| `get` | Get one sync product. |

### Draft

Build an order across multiple commands before submitting it.

| Command | Description |
|---------|-------------|
| `show` | Show the draft order under construction. |
| `recipient` | Set recipient fields on the draft. |
| `add-item` | Add a line item to the draft. |
| `remove-item` | Remove a line item from the draft by index. |
| `clear` | Clear the draft order. |
| `submit` | Submit the draft as a DRAFT order (not charged). |

### Session

Inspect and manage persistent session state.

| Command | Description |
|---------|-------------|
| `status` | Show session state. |
| `draft` | Show the draft order (alias of `draft show`). |
| `history` | Show recent commands recorded in the session. |
| `clear` | Clear draft, file records, and history. |

### Config

Manage stored credentials and defaults.

| Command | Description |
|---------|-------------|
| `set` | Set a config value (api_key, store_id). |
| `get` | Show config values. The API token is masked. |
| `delete` | Delete a config value. |
| `path` | Show the config file path. |


## Examples

### Price an order before committing to it

The core read-only workflow. Nothing here creates or charges anything.

```bash
# Find a product and a variant
printful --json catalog products --limit 5
printful --json catalog variants 71 --limit 5
printful --json catalog variant-price 4012

# Assemble a draft in the session
printful --json draft recipient --name "Jane Doe" \
    --address1 "1 Main St" --city Austin --state-code TX \
    --country-code US --zip 78701
printful --json draft add-item --variant-id 4012 --quantity 2

# Rates can be quoted with no artwork yet
printful --json ship rates

# Placing the order cannot — add a design first
printful --json draft add-item --variant-id 4012 --quantity 2 \
    --image-url https://example.com/art.png
printful --json orders estimate
```

### Place an order

```bash
# Creates a DRAFT — not charged
printful --json draft submit

# Inspect it
printful --json orders get 12345678

# Charge the account — only with the human's explicit go-ahead
printful --json orders confirm 12345678 --yes
```

### Generate a mockup

```bash
printful --json mockup styles 71
printful --json mockup create --product-id 71 \
    --variant-ids 4012,4013 --image-url https://example.com/art.png --wait
```

### Interactive REPL session

```bash
printful
# `help` lists command groups; `exit` leaves.
# The prompt shows the draft item count.
# Billable commands still require --yes inside the REPL.
```

## For AI Agents

1. **Always pass `--json`.** Every command supports it and emits a single parseable
   object on stdout. Human mode prints tables that are not stable to parse.
2. **Never pass `--yes` without explicit human instruction for that order.** It is
   the only thing standing between a command and a real charge. Use `--dry-run` to
   inspect a mutation safely.
3. **Check exit codes.** 0 for success, non-zero for failure. Errors are emitted as
   JSON on stderr with `error`, `status_code`, and `detail` keys.
4. **Build orders incrementally.** The `draft` group persists across separate process
   invocations via the session file, so a multi-step order does not need one giant
   command. Read state back with `session status` or `draft show`.
5. **Respect the rate limits, and do not retry a 429 blindly.** The general limit is
   120 req/60s. Mockup creation is 10/60s for established stores and **2/60s for new
   stores**, with a 60-second lockout on exceeding it plus a 20,000 files/24h account
   cap. The CLI surfaces `retry_after` in the error; honor it.
6. **`files list` is session-local, not a server query.** Printful has no list-files
   endpoint in either API version, so only files added through this CLI appear. The
   response is labelled `"source": "session-local"`.
7. **Async operations need polling.** `orders estimate` polls for you; `mockup create`
   polls only with `--wait`. Otherwise use `mockup status <task_id>`.
8. **Prefix external IDs with `@`** when passing them where an order ID is expected,
   e.g. `orders get @my-order-1`.
9. **Every catalog order item needs artwork.** Printful rejects an order item with no
   `placements` — there is nothing to print. `draft show` separates the two states:
   `priceable` (enough to quote shipping) and `complete` (enough to place the order),
   with `items_without_design` counting what still needs a design. Check `missing`
   before calling `draft submit`; it names the exact command to fix each gap.
10. **Select a store first on an account-level token.** Whenever Printful's error
    message mentions `store_id`, the CLI adds a `hint` field carrying the command
    to fix it — the match is on that substring, so the wording of Printful's own
    message does not matter. Run `--json store use` to list stores, then
    `store use <ID> --save`.
11. **Trust the error text.** API errors surface Printful's own message (the v2 API
    does not use the RFC 9457 shape its docs describe; this CLI reads both). A
    message of "Unknown error" would indicate a genuinely unrecognized body, not a
    parsing gap.

## Version

Run `printful --version`.
