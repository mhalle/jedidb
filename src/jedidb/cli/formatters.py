"""Output formatters for CLI."""

import csv
import io
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


def get_format_from_extension(path: Path) -> OutputFormat | None:
    """Detect output format from file extension.

    Returns None if extension is not recognized.
    """
    ext = path.suffix.lower()
    return {
        ".json": OutputFormat.json,
        ".jsonl": OutputFormat.jsonl,
        ".csv": OutputFormat.csv,
    }.get(ext)


def resolve_output_format(
    output_format: OutputFormat | None,
    output_path: Path | None,
) -> OutputFormat:
    """Resolve output format: explicit > file extension > auto-detect."""
    if output_format is not None:
        return output_format
    if output_path:
        return get_format_from_extension(output_path) or OutputFormat.jsonl
    return get_default_format()


def format_data_json(data: list[dict]) -> str:
    """Format list of dicts as pretty JSON."""
    return json.dumps(data, indent=2, default=str)


def format_data_jsonl(data: list[dict]) -> str:
    """Format list of dicts as newline-delimited JSON."""
    return "\n".join(json.dumps(row, separators=(",", ":"), default=str) for row in data)


def format_data_csv(data: list[dict], columns: list[str] | None = None) -> str:
    """Format list of dicts as CSV using csv module.

    Args:
        data: List of dictionaries to format
        columns: Column order (uses first row's keys if not specified)
    """
    if not data:
        return ""

    if columns is None:
        columns = list(data[0].keys())

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(data)
    return output.getvalue().rstrip("\n")


def write_output(
    content: str,
    output_path: Path | None,
    row_count: int | None = None,
) -> None:
    """Write content to file or stdout.

    Args:
        content: The formatted content to write
        output_path: File path to write to, or None for stdout
        row_count: Optional count for success message
    """
    if output_path:
        output_path.write_text(content)
        if row_count is not None:
            print_success(f"Wrote {row_count} row(s) to {output_path}")
        else:
            print_success(f"Wrote to {output_path}")
    else:
        print(content)


def get_source_path(ctx: typer.Context) -> Path:
    """Get source path from CLI context (set by -C/--source flag)."""
    return ctx.obj["source"]


def get_index_path(ctx: typer.Context) -> Path:
    """Get index path from CLI context (set by --index flag)."""
    return ctx.obj["index"]


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


def format_source_block(lines: list[str], start_line: int) -> str:
    """Format source code with line numbers.

    Args:
        lines: List of source lines (with or without trailing newlines)
        start_line: Line number of the first line (1-indexed)

    Returns:
        Formatted string with line numbers
    """
    if not lines:
        return ""

    # Calculate width needed for line numbers
    max_line = start_line + len(lines) - 1
    width = len(str(max_line))

    formatted = []
    for i, line in enumerate(lines):
        line_num = start_line + i
        # Strip trailing newline if present
        line_content = line.rstrip("\n\r")
        formatted.append(f"{line_num:>{width}} | {line_content}")

    return "\n".join(formatted)
