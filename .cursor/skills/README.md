# Printful MCP Cursor Skill

This directory contains a Cursor AI skill that teaches AI assistants how to effectively use the Printful MCP server.

## What is this?

A single skill file (`printful-mcp/SKILL.md`) that provides:
- Instructions for all 32 Printful MCP tools
- Common workflows (product discovery, orders, mockups, store analysis)
- Best practices and troubleshooting
- Output formatting guidelines

The tool reference is kept one-to-one with what the server registers, and
`src/printful_mcp/tests/test_server.py` asserts that mapping in both directions — so the
count follows the code rather than the other way round. If you ever doubt it, your own
client's tool list is the authority.

## How it works

When you open this project in Cursor and ask Printful-related questions, the AI automatically:
1. Detects Printful/print-on-demand keywords
2. Applies the skill's guidance
3. Uses the appropriate MCP tools
4. Follows best practices
5. Formats results clearly

## Installation

**For this project:** Already included! Just open in Cursor and start asking questions.

**For personal use across all projects:**
```bash
cp -r .cursor/skills/printful-mcp ~/.cursor/skills/
```

## Usage Examples

Just ask naturally:
- "Show me t-shirts I can print with DTG"
- "Create an order for John Doe in Los Angeles"
- "Generate a mockup with my design"
- "Calculate shipping to UK"
- "What are my store statistics?"

Note that the catalog filters on `category_ids`, `colors`, `techniques` and `types` — and
nothing else. The product list carries no prices, so "everything under $15" is not a
question the catalog can answer; pricing is fetched one variant at a time with
`printful_get_variant_prices`.

The skill ensures the AI knows how to use each tool correctly and follows proper workflows.

## File Structure

```
.cursor/skills/
├── README.md
└── printful-mcp/
    └── SKILL.md          (the skill itself)

skills/                   (repository root — where the Claude Code plugin loads skills from)
├── printful-mcp/
│   ├── SKILL.md   ->  ../../.cursor/skills/printful-mcp/SKILL.md
│   └── skill.json
└── printful-cli/
    ├── SKILL.md   ->  ../../src/printful_cli/skills/SKILL.md
    └── skill.json
```

Both `SKILL.md` files under `skills/` are **symlinks**, not copies: the originals live here
and in `src/printful_cli/skills/`, and git records them as symlinks. Two files with the
same content and no check between them is how documentation drifts.

That's it — one skill file, surfaced to Cursor from `.cursor/skills/` and to Claude Code
plugins from `skills/`, with no second copy to keep in sync.
