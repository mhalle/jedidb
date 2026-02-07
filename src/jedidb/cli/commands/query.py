"""Query command for JediDB CLI."""

from pathlib import Path
from typing import Optional

import typer

from jedidb import JediDB
from jedidb.cli.formatters import (
    get_source_path,
    get_index_path,
    format_data_json,
    format_data_jsonl,
    format_data_csv,
    resolve_output_format,
    write_output,
    OutputFormat,
    print_error,
)


def query_cmd(
    ctx: typer.Context,
    sql: str = typer.Argument(
        ...,
        help="SQL query to execute",
    ),
    output_format: Optional[OutputFormat] = typer.Option(
        None,
        "--format",
        "-f",
        help="Output format (default: table for terminal, jsonl for pipes)",
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-n",
        help="Limit number of results (adds LIMIT clause if not present)",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file (format auto-detected from extension: .json, .jsonl, .csv)",
    ),
):
    """Execute a raw SQL query against the database.

    Tables: definitions, files, refs, imports, decorators, calls

    Examples:

        jedidb query "SELECT * FROM definitions WHERE type = 'class'"

        jedidb query "SELECT name FROM definitions WHERE type = 'function'" -n 10

        jedidb query "SELECT caller_full_name FROM calls WHERE callee_full_name = 'mymodule.parse'"

        jedidb query "SELECT full_name, (end_line - line) as size FROM definitions ORDER BY size DESC" -n 20

        jedidb query "DESCRIBE definitions"   # show table schema

        jedidb query "SELECT * FROM definitions" -o defs.csv  # output to CSV
    """
    output_format = resolve_output_format(output_format, output)

    source = get_source_path(ctx)
    index = get_index_path(ctx)

    try:
        jedidb = JediDB(source=source, index=index)
    except Exception as e:
        print_error(f"Failed to open database: {e}")
        raise typer.Exit(1)

    # Add LIMIT if requested and not already present
    query_sql = sql
    if limit and "limit" not in sql.lower():
        query_sql = f"{sql} LIMIT {limit}"

    try:
        result = jedidb.db.execute(query_sql)
        rows = result.fetchall()
        columns = [desc[0] for desc in result.description] if result.description else []
    except Exception as e:
        print_error(f"Query error: {e}")
        raise typer.Exit(1)
    finally:
        jedidb.close()

    if not rows:
        print("No results")
        raise typer.Exit(0)

    # Convert to list of dicts
    data = [dict(zip(columns, row)) for row in rows]

    # Format output
    if output_format == OutputFormat.json:
        content = format_data_json(data)
    elif output_format == OutputFormat.jsonl:
        content = format_data_jsonl(data)
    elif output_format == OutputFormat.csv:
        content = format_data_csv(data, columns)
    else:
        # Table format - plain text
        col_widths = [len(c) for c in columns]
        for row in rows:
            for i, val in enumerate(row):
                col_widths[i] = max(col_widths[i], len(str(val) if val is not None else ""))

        lines = []
        # Header
        header = "  ".join(f"{col:<{col_widths[i]}}" for i, col in enumerate(columns))
        lines.append(header)
        lines.append("-" * len(header))

        # Rows
        for row in rows:
            lines.append("  ".join(f"{(str(v) if v is not None else ''):<{col_widths[i]}}" for i, v in enumerate(row)))

        lines.append(f"\n{len(rows)} row(s)")
        content = "\n".join(lines)

    write_output(content, output, len(rows))
