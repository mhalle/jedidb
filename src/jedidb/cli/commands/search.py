"""Search command for JediDB CLI."""

from pathlib import Path
from typing import Optional

import typer

from jedidb import JediDB
from jedidb.config import Config
from jedidb.cli.formatters import (
    console,
    format_search_results_table,
    format_json,
    print_error,
    print_info,
)


def search_cmd(
    query: str = typer.Argument(
        ...,
        help="Search query",
    ),
    type: Optional[str] = typer.Option(
        None,
        "--type",
        "-t",
        help="Filter by type (function, class, variable, etc.)",
    ),
    limit: int = typer.Option(
        20,
        "--limit",
        "-n",
        help="Maximum number of results",
    ),
    include_private: bool = typer.Option(
        False,
        "--private",
        "-p",
        help="Include private definitions (starting with _)",
    ),
    output_format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format: table, json",
    ),
    db_path: Optional[Path] = typer.Option(
        None,
        "--db-path",
        "-d",
        help="Database path (overrides config)",
    ),
):
    """Full-text search for definitions.

    Search across function names, class names, and docstrings.
    """
    # Find project root
    project_root = Config.find_project_root()
    if project_root is None:
        project_root = Path.cwd()

    try:
        jedidb = JediDB(path=str(project_root), db_path=str(db_path) if db_path else None)
    except Exception as e:
        print_error(f"Failed to open database: {e}")
        raise typer.Exit(1)

    results = jedidb.search_engine.search(
        query,
        type=type,
        limit=limit,
        include_private=include_private,
    )

    jedidb.close()

    if not results:
        print_info("No results found")
        raise typer.Exit(0)

    if output_format == "json":
        data = [
            {
                "name": r.definition.name,
                "full_name": r.definition.full_name,
                "type": r.definition.type,
                "file": r.definition.file_path,
                "line": r.definition.line,
                "score": r.score,
                "signature": r.definition.signature,
                "docstring": r.definition.docstring,
            }
            for r in results
        ]
        console.print(format_json(data))
    else:
        console.print(format_search_results_table(results))
        console.print(f"\n[dim]{len(results)} result(s)[/dim]")
