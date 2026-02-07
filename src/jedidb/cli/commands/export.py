"""Export command for JediDB CLI."""

from pathlib import Path
from typing import Optional

import typer

from jedidb import JediDB
from jedidb.cli.formatters import (
    get_source_path,
    get_index_path,
    format_data_json,
    format_data_csv,
    get_format_from_extension,
    write_output,
    print_error,
)


def export_cmd(
    ctx: typer.Context,
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path (format auto-detected from extension: .json, .csv)",
    ),
    output_format: Optional[str] = typer.Option(
        None,
        "--format",
        "-f",
        help="Output format: json, csv (default: json, or auto-detected from -o)",
    ),
    table: str = typer.Option(
        "definitions",
        "--table",
        "-t",
        help="Table to export: definitions, files, refs, imports",
    ),
    type_filter: Optional[str] = typer.Option(
        None,
        "--type",
        help="Filter definitions by type",
    ),
):
    """Export data to JSON or CSV.

    Export indexed data for external analysis or backup.
    """
    # Resolve output format: explicit > file extension > default (json)
    if output_format is None:
        if output:
            detected = get_format_from_extension(output)
            output_format = detected.value if detected else "json"
        else:
            output_format = "json"

    source = get_source_path(ctx)
    index = get_index_path(ctx)

    try:
        jedidb = JediDB(source=source, index=index)
    except Exception as e:
        print_error(f"Failed to open database: {e}")
        raise typer.Exit(1)

    try:
        # Build query based on table
        params = None
        if table == "definitions":
            sql = """
                SELECT d.id, d.name, d.full_name, d.type, d.line, d.col as column,
                       d.signature, d.docstring, d.is_public, f.path as file
                FROM definitions d
                JOIN files f ON d.file_id = f.id
            """
            if type_filter:
                sql += " WHERE d.type = ?"
                params = (type_filter,)
            sql += " ORDER BY f.path, d.line"
            columns = ["id", "name", "full_name", "type", "line", "column", "signature", "docstring", "is_public", "file"]

        elif table == "files":
            sql = "SELECT id, path, hash, size, modified_at, indexed_at FROM files ORDER BY path"
            columns = ["id", "path", "hash", "size", "modified_at", "indexed_at"]

        elif table == "refs":
            sql = """
                SELECT r.id, r.name, r.line, r.col as column, r.context, f.path as file
                FROM refs r
                JOIN files f ON r.file_id = f.id
                ORDER BY f.path, r.line
            """
            columns = ["id", "name", "line", "column", "context", "file"]

        elif table == "imports":
            sql = """
                SELECT i.id, i.module, i.name, i.alias, i.line, f.path as file
                FROM imports i
                JOIN files f ON i.file_id = f.id
                ORDER BY f.path, i.line
            """
            columns = ["id", "module", "name", "alias", "line", "file"]

        else:
            print_error(f"Unknown table: {table}")
            raise typer.Exit(1)

        result = jedidb.db.execute(sql, params)
        rows = result.fetchall()
    except typer.Exit:
        raise
    except Exception as e:
        print_error(f"Query error: {e}")
        raise typer.Exit(1)
    finally:
        jedidb.close()

    # Convert to list of dicts
    data = [dict(zip(columns, row)) for row in rows]

    # Format output
    if output_format == "json":
        content = format_data_json(data)
    else:
        content = format_data_csv(data, columns)

    write_output(content, output, len(rows))
