"""Output formatters for CLI."""

import json
import sys
from enum import Enum
from pathlib import Path
from typing import Any

import typer

from jedidb.core.models import Definition, Reference, SearchResult


class OutputFormat(str, Enum):
    """Output format options."""
    table = "table"
    json = "json"
    jsonl = "jsonl"
    csv = "csv"


def get_default_format() -> OutputFormat:
    """Return 'table' for interactive terminals, 'jsonl' for pipes/redirects."""
    return OutputFormat.table if sys.stdout.isatty() else OutputFormat.jsonl


def get_project_path(ctx: typer.Context) -> Path | None:
    """Get project path from CLI context (set by -C/--project flag)."""
    if ctx.obj and "project" in ctx.obj:
        return ctx.obj["project"]
    return None


def format_definition_table(definitions: list[Definition], show_file: bool = True) -> str:
    """Format definitions as a plain text table."""
    if not definitions:
        return "No definitions found."

    lines = []
    if show_file:
        lines.append(f"{'Name':<40} {'Type':<12} {'File':<40} {'Line':>6}")
        lines.append("-" * 100)
        for d in definitions:
            lines.append(f"{d.name:<40} {d.type:<12} {(d.file_path or ''):<40} {d.line:>6}")
    else:
        lines.append(f"{'Name':<40} {'Type':<12} {'Line':>6}")
        lines.append("-" * 60)
        for d in definitions:
            lines.append(f"{d.name:<40} {d.type:<12} {d.line:>6}")

    return "\n".join(lines)


def format_search_results_table(results: list[SearchResult]) -> str:
    """Format search results as a plain text table."""
    if not results:
        return "No results found."

    lines = []
    lines.append(f"{'Name':<40} {'Type':<12} {'File':<40} {'Line':>6} {'Score':>8}")
    lines.append("-" * 110)
    for r in results:
        lines.append(
            f"{r.definition.name:<40} {r.definition.type:<12} "
            f"{(r.definition.file_path or ''):<40} {r.definition.line:>6} {r.score:>8.2f}"
        )

    return "\n".join(lines)


def format_references_table(references: list[Reference]) -> str:
    """Format references as a plain text table."""
    if not references:
        return "No references found."

    lines = []
    lines.append(f"{'File':<50} {'Line':>6}  {'Context'}")
    lines.append("-" * 100)
    for r in references:
        lines.append(f"{(r.file_path or ''):<50} {r.line:>6}  {r.context or ''}")

    return "\n".join(lines)


def format_definition_detail(definition: Definition) -> str:
    """Format a single definition with full details."""
    lines = []

    # Name and type
    lines.append(f"{definition.full_name or definition.name} ({definition.type})")
    lines.append("")

    # Location
    lines.append(f"Location: {definition.file_path}:{definition.line}")

    # Signature
    if definition.signature:
        lines.append(f"Signature: {definition.signature}")

    # Docstring
    if definition.docstring:
        lines.append("")
        lines.append("Docstring:")
        lines.append(definition.docstring)

    return "\n".join(lines)


def format_stats(stats: dict[str, Any]) -> str:
    """Format database statistics."""
    lines = []

    lines.append(f"Files: {stats.get('total_files', 0)}")
    lines.append(f"Definitions: {stats.get('total_definitions', 0)}")
    lines.append(f"References: {stats.get('total_references', 0)}")
    lines.append(f"Imports: {stats.get('total_imports', 0)}")

    if stats.get("definitions_by_type"):
        lines.append("")
        lines.append("Definitions by type:")
        for type_name, count in stats["definitions_by_type"].items():
            lines.append(f"  {type_name}: {count}")

    if stats.get("last_indexed"):
        lines.append("")
        lines.append(f"Last indexed: {stats['last_indexed']}")

    return "\n".join(lines)


def format_json(data: Any) -> str:
    """Format data as JSON."""
    return json.dumps(data, indent=2, default=str)


def format_csv_row(row: dict[str, Any], columns: list[str]) -> str:
    """Format a dictionary as a CSV row."""
    values = []
    for col in columns:
        val = row.get(col, "")
        # Escape quotes and wrap in quotes if contains comma
        if isinstance(val, str):
            if '"' in val or "," in val or "\n" in val:
                val = '"' + val.replace('"', '""') + '"'
        else:
            val = str(val) if val is not None else ""
        values.append(val)
    return ",".join(values)


def print_success(message: str):
    """Print a success message."""
    print(f"OK: {message}")


def print_error(message: str):
    """Print an error message."""
    print(f"Error: {message}", file=sys.stderr)


def print_warning(message: str):
    """Print a warning message."""
    print(f"Warning: {message}", file=sys.stderr)


def print_info(message: str):
    """Print an info message."""
    print(message)
