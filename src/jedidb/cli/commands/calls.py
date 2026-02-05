"""Calls command for JediDB CLI."""

from pathlib import Path
from typing import Optional

import typer

from jedidb import JediDB
from jedidb.cli.formatters import (
    get_source_path,
    get_index_path,
    format_data_json,
    format_data_jsonl,
    resolve_output_format,
    write_output,
    OutputFormat,
    print_error,
    print_info,
)


def format_calls_table(calls: list[dict], show_depth: bool = False) -> str:
    """Format calls as a plain text table."""
    if not calls:
        return "No calls found."

    lines = []
    if show_depth:
        lines.append(f"{'Order':>5} {'Depth':>5}  {'Callee':<40} {'Line':>6}  {'Context'}")
        lines.append("-" * 100)
        for c in calls:
            callee = c.get("callee_full_name") or c.get("callee_name", "")
            lines.append(
                f"{c.get('call_order', 0):>5} {c.get('call_depth', 0):>5}  "
                f"{callee:<40} {c.get('line', 0):>6}  {c.get('context', '')[:50]}"
            )
    else:
        lines.append(f"{'Order':>5}  {'Callee':<40} {'Line':>6}  {'Context'}")
        lines.append("-" * 95)
        for c in calls:
            callee = c.get("callee_full_name") or c.get("callee_name", "")
            lines.append(
                f"{c.get('call_order', 0):>5}  "
                f"{callee:<40} {c.get('line', 0):>6}  {c.get('context', '')[:50]}"
            )

    return "\n".join(lines)


def format_calls_tree(calls: list[dict], depth: int = 0, prefix: str = "") -> str:
    """Format calls as an indented tree."""
    if not calls:
        return "No calls found."

    lines = []
    for i, c in enumerate(calls):
        is_last = i == len(calls) - 1
        callee = c.get("callee_full_name") or c.get("callee_name", "")
        connector = "`-- " if is_last else "|-- "
        lines.append(f"{prefix}{connector}{callee} (line {c.get('line', 0)})")

        # If there are nested calls, show them
        nested = c.get("nested_calls", [])
        if nested:
            extension = "    " if is_last else "|   "
            nested_output = format_calls_tree(nested, depth + 1, prefix + extension)
            lines.append(nested_output)

    return "\n".join(lines)


def calls_cmd(
    ctx: typer.Context,
    name: str = typer.Argument(
        ...,
        help="Name or full name of the function to show calls for",
    ),
    depth: int = typer.Option(
        1,
        "--depth",
        "-d",
        help="Recursion depth for call tree (1 = direct calls only)",
    ),
    top_level: bool = typer.Option(
        False,
        "--top-level",
        "-t",
        help="Only show top-level calls (not nested as arguments)",
    ),
    tree: bool = typer.Option(
        False,
        "--tree",
        help="Show calls as a tree",
    ),
    output_format: Optional[OutputFormat] = typer.Option(
        None,
        "--format",
        "-f",
        help="Output format (default: table for terminal, jsonl for pipes)",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file (format auto-detected from extension: .json, .jsonl)",
    ),
):
    """Show what a function calls in execution order.

    Display all calls made by a function, ordered by execution sequence.
    Nested calls (like arguments to other calls) have higher call_depth values.

    Examples:

        jedidb calls Model.save              # direct calls from Model.save

        jedidb calls Model.save --depth 2    # include calls made by callees

        jedidb calls Model.save --top-level  # only top-level calls (depth=1)

        jedidb calls __init__ --tree         # show as indented tree

        jedidb calls parse --format json     # JSON output for tooling

        jedidb calls parse -o calls.json     # output to file
    """
    output_format = resolve_output_format(output_format, output)

    source = get_source_path(ctx)
    index = get_index_path(ctx)

    try:
        jedidb = JediDB(source=source, index=index)
    except Exception as e:
        print_error(f"Failed to open database: {e}")
        raise typer.Exit(1)

    # Find the function
    definition = jedidb.search_engine.get_definition(name)

    if not definition:
        jedidb.close()
        print_error(f"Definition not found: {name}")
        raise typer.Exit(1)

    if definition.type not in ("function", "class"):
        jedidb.close()
        print_error(f"'{name}' is a {definition.type}, not a function or class")
        raise typer.Exit(1)

    # Build query for calls
    depth_filter = "AND call_depth = 1" if top_level else ""

    def get_calls_for_function(full_name: str, current_depth: int = 1) -> list[dict]:
        """Get calls for a function, optionally recursing into callees."""
        # Use DISTINCT to avoid duplicates from refs matching multiple enclosing definitions
        query = f"""
            SELECT DISTINCT
                callee_full_name,
                callee_name,
                line,
                col,
                context,
                call_order,
                call_depth
            FROM calls
            WHERE caller_full_name = ?
            {depth_filter}
            ORDER BY call_order
        """
        results = jedidb.db.execute(query, (full_name,)).fetchall()

        calls = []
        for r in results:
            call = {
                "callee_full_name": r[0],
                "callee_name": r[1],
                "line": r[2],
                "col": r[3],
                "context": r[4],
                "call_order": r[5],
                "call_depth": r[6],
            }

            # Recurse if requested and callee is resolved
            if current_depth < depth and r[0]:
                call["nested_calls"] = get_calls_for_function(r[0], current_depth + 1)

            calls.append(call)

        return calls

    calls = get_calls_for_function(definition.full_name)
    jedidb.close()

    if not calls:
        print_info(f"No calls found in {definition.full_name}")
        raise typer.Exit(0)

    # Format output
    if output_format == OutputFormat.json:
        content = format_data_json(calls)
    elif output_format == OutputFormat.jsonl and not tree:
        content = format_data_jsonl(calls)
    elif tree:
        content = f"Calls from {definition.full_name}:\n{format_calls_tree(calls)}"
    else:
        content = f"Calls from {definition.full_name}:\n\n{format_calls_table(calls, show_depth=not top_level)}\n\n{len(calls)} call(s)"

    write_output(content, output, len(calls))
