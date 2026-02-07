"""Stats command for JediDB CLI."""

import typer

from jedidb import JediDB
from jedidb.cli.formatters import get_source_path, get_index_path, format_stats, format_json, print_error


def stats_cmd(
    ctx: typer.Context,
    output_format: str = typer.Option(
        "pretty",
        "--format",
        "-f",
        help="Output format: pretty, json",
    ),
):
    """Show database statistics.

    Display counts and summaries of indexed data.
    """
    source = get_source_path(ctx)
    index = get_index_path(ctx)

    try:
        jedidb = JediDB(source=source, index=index)
    except Exception as e:
        print_error(f"Failed to open database: {e}")
        raise typer.Exit(1)

    try:
        stats = jedidb.stats()
    finally:
        jedidb.close()

    if output_format == "json":
        # Convert datetime to string for JSON
        if stats.get("last_indexed"):
            stats["last_indexed"] = str(stats["last_indexed"])
        print(format_json(stats))
    else:
        print(format_stats(stats))
