"""Query command for JediDB CLI."""

from pathlib import Path
from typing import Optional

import typer

from jedidb import JediDB
from jedidb.config import Config
from jedidb.cli.formatters import (
    console,
    format_json,
    get_default_format,
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
    db_path: Optional[Path] = typer.Option(
        None,
        "--db-path",
        "-d",
        help="Database path (overrides config)",
    ),
    project: Optional[Path] = typer.Option(
        None,
        "--project",
        "-C",
        help="Project directory",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
):
    """Execute a raw SQL query against the database.

    Examples:
        jedidb query "SELECT * FROM definitions WHERE type = 'class'"
        jedidb query "SELECT name, COUNT(*) FROM definitions GROUP BY name"
    """
    from jedidb.cli.formatters import get_project_path

    # Resolve output format (table for TTY, jsonl for pipes)
    if output_format is None:
        output_format = get_default_format()

    # Find project root (command -C takes precedence over global -C)
    project_root = project or get_project_path(ctx)
    if project_root is None:
        project_root = Config.find_project_root()
    if project_root is None:
        project_root = Path.cwd()

    try:
        jedidb = JediDB(path=str(project_root), db_path=str(db_path) if db_path else None)
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
        jedidb.close()
        print_error(f"Query error: {e}")
        raise typer.Exit(1)

    jedidb.close()

    if not rows:
        console.print("[dim]No results[/dim]")
        raise typer.Exit(0)

    if output_format == OutputFormat.json:
        data = [dict(zip(columns, row)) for row in rows]
        console.print(format_json(data))

    elif output_format == OutputFormat.jsonl:
        import json
        for row in rows:
            print(json.dumps(dict(zip(columns, row)), separators=(",", ":"), default=str))

    elif output_format == OutputFormat.csv:
        # Header
        console.print(",".join(columns))
        # Rows
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
            console.print(",".join(values))

    else:
        # Table format
        from rich.table import Table

        table = Table(show_header=True, header_style="bold cyan")
        for col in columns:
            table.add_column(col)

        for row in rows:
            table.add_row(*[str(v) if v is not None else "" for v in row])

        console.print(table)
        console.print(f"\n[dim]{len(rows)} row(s)[/dim]")
