"""Terminal output for the CLI.

Replaces the vendored cli-anything REPL skin. Colour is disabled when stdout is
not a terminal, so piped output stays parseable.
"""

from __future__ import annotations

import sys
from typing import Any, Sequence

import click

_ACCENT = "cyan"
_DIM = "bright_black"


class UI:
    """Human-facing output. Never used when --json is set."""

    def __init__(self, stream=None):
        self.stream = stream or sys.stdout

    @property
    def colour(self) -> bool:
        return self.stream.isatty()

    def _echo(self, text: str, **style) -> None:
        click.echo(click.style(text, **style) if self.colour else text, file=self.stream)

    def section(self, title: str) -> None:
        self._echo(f"\n{title}", fg=_ACCENT, bold=True)
        self._echo("─" * len(title), fg=_DIM)

    def success(self, message: str) -> None:
        self._echo(f"✓ {message}", fg="green")

    def error(self, message: str) -> None:
        click.echo(
            click.style(f"✗ {message}", fg="red") if self.colour else f"✗ {message}", err=True
        )

    def warning(self, message: str) -> None:
        self._echo(f"⚠ {message}", fg="yellow")

    def info(self, message: str) -> None:
        self._echo(f"● {message}", fg="blue")

    def status(self, label: str, value: Any) -> None:
        self._echo(f"  {label}: {value}")

    def table(
        self, headers: Sequence[str], rows: Sequence[Sequence[Any]], max_width: int = 40
    ) -> None:
        """Print a simple aligned table."""
        if not headers:
            return

        widths = [len(str(h)) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(widths):
                    widths[i] = min(max(widths[i], len(str(cell))), max_width)

        def render(cells: Sequence[Any]) -> str:
            parts = []
            for i, cell in enumerate(cells):
                text = str(cell)
                if len(text) > widths[i]:
                    text = text[: widths[i] - 1] + "…"
                parts.append(text.ljust(widths[i]))
            return "  ".join(parts).rstrip()

        self._echo(render(headers), bold=True)
        self._echo("  ".join("─" * w for w in widths), fg=_DIM)
        for row in rows:
            self._echo(render(row))

    def prompt(self, text: str, count: int) -> int:
        """Ask for a 1-based selection. Callers must confirm a TTY first."""
        return click.prompt(f"{text} [1-{count}]", type=click.IntRange(1, count))
