#!/bin/bash
# Test the Printful MCP server with MCP Inspector.
set -euo pipefail

# Resolve the repo root from this script's own location, so the interpreter
# path below is correct regardless of where the script is invoked from.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"

if [ ! -x "$PY" ]; then
  echo "No interpreter at $PY" >&2
  echo "Create one first:  python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'" >&2
  exit 1
fi

echo "Starting MCP Inspector..."
echo "This will open a web UI at http://localhost:5173"
echo ""
echo "Make sure you have set PRINTFUL_API_KEY in your environment:"
echo "  export PRINTFUL_API_KEY=your-api-key-here"
echo ""

# The interpreter is spelled out rather than bare. A bare `python` here runs
# whichever one is first on PATH, which is how this project's tests have
# already produced two different sets of misleading failures.
npx @modelcontextprotocol/inspector "$PY" -m printful_mcp
