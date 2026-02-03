"""Export command for JediDB CLI."""

from pathlib import Path
from typing import Optional

import typer

from jedidb import JediDB
from jedidb.config import Config
from jedidb.cli.formatters import console, format_json, print_error, print_success


def export_cmd(
    ctx: typer.Context,
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path (default: stdout)",
    ),
    output_format: str = typer.Option(
        "json",
        "--format",
        "-f",
        help="Output format: json, csv",
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
    db_path: Optional[Path] = typer.Option(
        None,
        "--db-path",
        "-d",
        help="Database path (overrides config)",
    ),
):
    """Export data to JSON or CSV.

    Export indexed data for external analysis or backup.
    """
    from jedidb.cli.formatters import get_project_path

    # Find project root (CLI -C flag takes precedence)
    project_root = get_project_path(ctx)
    if project_root is None:
        project_root = Config.find_project_root()
    if project_root is None:
        project_root = Path.cwd()

    try:
        jedidb = JediDB(path=str(project_root), db_path=str(db_path) if db_path else None)
    except Exception as e:
        print_error(f"Failed to open database: {e}")
        raise typer.Exit(1)

    # Build query based on table
    if table == "definitions":
        sql = """
            SELECT d.id, d.name, d.full_name, d.type, d.line, d.col as column,
                   d.signature, d.docstring, d.is_public, f.path as file
            FROM definitions d
            JOIN files f ON d.file_id = f.id
        """
        if type_filter:
            sql += f" WHERE d.type = '{type_filter}'"
        sql += " ORDER BY f.path, d.line"

    elif table == "files":
        sql = "SELECT id, path, hash, size, modified_at, indexed_at FROM files ORDER BY path"

    elif table == "refs":
        sql = """
            SELECT r.id, r.name, r.line, r.col as column, r.context, f.path as file
            FROM refs r
            JOIN files f ON r.file_id = f.id
            ORDER BY f.path, r.line
        """

    elif table == "imports":
        sql = """
            SELECT i.id, i.module, i.name, i.alias, i.line, f.path as file
            FROM imports i
            JOIN files f ON i.file_id = f.id
            ORDER BY f.path, i.line
        """

    else:
        jedidb.close()
        print_error(f"Unknown table: {table}")
        raise typer.Exit(1)

    try:
        result = jedidb.db.execute(sql)
        rows = result.fetchall()
        columns = [desc[0] for desc in result.description]
    except Exception as e:
        jedidb.close()
        print_error(f"Query error: {e}")
        raise typer.Exit(1)

    jedidb.close()

    # Format output
    if output_format == "json":
        data = [dict(zip(columns, row)) for row in rows]
        content = format_json(data)
    else:
        # CSV
        lines = [",".join(columns)]
        for row in rows:
            values = []
            for val in row:
                if val is None:
                    values.append("")
                elif isinstance(val, str):
                    if '"' in val or "," in val or "\n" in val:
                        val = '"' + val.replace('"', '""') + '"'
                    values.append(val)
                else:
                    values.append(str(val))
            lines.append(",".join(values))
        content = "\n".join(lines)

    # Write output
    if output:
        output.write_text(content)
        print_success(f"Exported {len(rows)} rows to {output}")
    else:
        console.print(content)
