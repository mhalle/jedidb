"""Stats command for JediDB CLI."""

from pathlib import Path
from typing import Optional

import typer

from jedidb import JediDB
from jedidb.config import Config
from jedidb.cli.formatters import console, format_stats, format_json, print_error


def stats_cmd(
    output_format: str = typer.Option(
        "pretty",
        "--format",
        "-f",
        help="Output format: pretty, json",
    ),
    db_path: Optional[Path] = typer.Option(
        None,
        "--db-path",
        "-d",
        help="Database path (overrides config)",
    ),
):
    """Show database statistics.

    Display counts and summaries of indexed data.
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

    stats = jedidb.stats()
    jedidb.close()

    if output_format == "json":
        # Convert datetime to string for JSON
        if stats.get("last_indexed"):
            stats["last_indexed"] = str(stats["last_indexed"])
        console.print(format_json(stats))
    else:
        console.print(format_stats(stats))
