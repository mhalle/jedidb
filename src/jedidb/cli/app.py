"""Main Typer application for JediDB CLI."""

from pathlib import Path
from typing import Optional

import typer

from jedidb.cli.commands import init, index, search, query, show, export, stats, clean


app = typer.Typer(
    name="jedidb",
    help="Jedi code analyzer with DuckDB storage and full-text search.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def main_callback(
    ctx: typer.Context,
    project: Optional[Path] = typer.Option(
        None,
        "--project",
        "-C",
        help="Project directory (like git -C)",
        exists=True,
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
):
    """Jedi code analyzer with DuckDB storage and full-text search."""
    ctx.ensure_object(dict)
    ctx.obj["project"] = project


app.command(name="init", help="Initialize jedidb in a project")(init.init_cmd)
app.command(name="index", help="Index Python files")(index.index_cmd)
app.command(name="search", help="Full-text search definitions")(search.search_cmd)
app.command(name="query", help="Run raw SQL queries")(query.query_cmd)
app.command(name="show", help="Show details for a definition")(show.show_cmd)
app.command(name="export", help="Export data to JSON or CSV")(export.export_cmd)
app.command(name="stats", help="Show database statistics")(stats.stats_cmd)
app.command(name="clean", help="Remove stale entries or reset database")(clean.clean_cmd)


def main():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
