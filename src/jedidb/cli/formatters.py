"""Output formatters for CLI."""

import json
from typing import Any

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from jedidb.core.models import Definition, Reference, SearchResult


console = Console()


def format_definition_table(definitions: list[Definition], show_file: bool = True) -> Table:
    """Format definitions as a Rich table."""
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Name", style="green")
    table.add_column("Type", style="yellow")
    if show_file:
        table.add_column("File", style="blue")
    table.add_column("Line", justify="right")

    for d in definitions:
        row = [d.name, d.type]
        if show_file:
            row.append(d.file_path or "")
        row.append(str(d.line))
        table.add_row(*row)

    return table


def format_search_results_table(results: list[SearchResult]) -> Table:
    """Format search results as a Rich table."""
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Name", style="green")
    table.add_column("Type", style="yellow")
    table.add_column("File", style="blue")
    table.add_column("Line", justify="right")
    table.add_column("Score", justify="right", style="magenta")

    for r in results:
        table.add_row(
            r.definition.name,
            r.definition.type,
            r.definition.file_path or "",
            str(r.definition.line),
            f"{r.score:.2f}",
        )

    return table


def format_references_table(references: list[Reference]) -> Table:
    """Format references as a Rich table."""
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("File", style="blue")
    table.add_column("Line", justify="right")
    table.add_column("Context", style="dim")

    for r in references:
        table.add_row(
            r.file_path or "",
            str(r.line),
            r.context or "",
        )

    return table


def format_definition_detail(definition: Definition) -> Panel:
    """Format a single definition with full details."""
    content = Text()

    # Name and type
    content.append(definition.full_name or definition.name, style="bold green")
    content.append(f" ({definition.type})", style="yellow")
    content.append("\n\n")

    # Location
    content.append("Location: ", style="bold")
    content.append(f"{definition.file_path}:{definition.line}", style="blue")
    content.append("\n")

    # Signature
    if definition.signature:
        content.append("\nSignature: ", style="bold")
        content.append(definition.signature, style="cyan")
        content.append("\n")

    # Docstring
    if definition.docstring:
        content.append("\nDocstring:\n", style="bold")
        content.append(definition.docstring, style="dim")

    return Panel(content, title="Definition", border_style="cyan")


def format_stats(stats: dict[str, Any]) -> Panel:
    """Format database statistics."""
    content = Text()

    content.append("Files: ", style="bold")
    content.append(f"{stats.get('total_files', 0)}\n")

    content.append("Definitions: ", style="bold")
    content.append(f"{stats.get('total_definitions', 0)}\n")

    content.append("References: ", style="bold")
    content.append(f"{stats.get('total_references', 0)}\n")

    content.append("Imports: ", style="bold")
    content.append(f"{stats.get('total_imports', 0)}\n")

    if stats.get("definitions_by_type"):
        content.append("\nDefinitions by type:\n", style="bold")
        for type_name, count in stats["definitions_by_type"].items():
            content.append(f"  {type_name}: ", style="yellow")
            content.append(f"{count}\n")

    if stats.get("last_indexed"):
        content.append("\nLast indexed: ", style="bold")
        content.append(str(stats["last_indexed"]))

    return Panel(content, title="Database Statistics", border_style="green")


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
    console.print(f"[green]✓[/green] {message}")


def print_error(message: str):
    """Print an error message."""
    console.print(f"[red]✗[/red] {message}")


def print_warning(message: str):
    """Print a warning message."""
    console.print(f"[yellow]![/yellow] {message}")


def print_info(message: str):
    """Print an info message."""
    console.print(f"[blue]i[/blue] {message}")
