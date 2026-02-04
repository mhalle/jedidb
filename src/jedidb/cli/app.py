"""Main Typer application for JediDB CLI."""

from pathlib import Path
from typing import Optional

import typer

from jedidb.cli.commands import init, index, search, query, show, export, stats, clean, calls, source


app = typer.Typer(
    name="jedidb",
    help="Jedi code analyzer with DuckDB storage and full-text search.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode=None,
    pretty_exceptions_enable=False,
)


@app.callback()
def main_callback(
    ctx: typer.Context,
    source: Optional[Path] = typer.Option(
        None,
        "-C",
        "--source",
        help="Source directory (default: current directory)",
    ),
    index_dir: Optional[Path] = typer.Option(
        None,
        "--index",
        help="Index directory (default: <source>/.jedidb)",
    ),
):
    """Jedi code analyzer with DuckDB storage and full-text search."""
    ctx.ensure_object(dict)

    source_path = (source or Path.cwd()).resolve()
    index_path = (index_dir or source_path / ".jedidb").resolve()

    ctx.obj["source"] = source_path
    ctx.obj["index"] = index_path


app.command(name="init", help="Initialize jedidb in a project")(init.init_cmd)
app.command(name="index", help="Index Python files")(index.index_cmd)
app.command(name="search", help="Full-text search definitions")(search.search_cmd)
app.command(name="query", help="Run raw SQL queries")(query.query_cmd)
app.command(name="show", help="Show details for a definition")(show.show_cmd)
app.command(name="export", help="Export data to JSON or CSV")(export.export_cmd)
app.command(name="stats", help="Show database statistics")(stats.stats_cmd)
app.command(name="clean", help="Remove stale entries or reset database")(clean.clean_cmd)
app.command(name="calls", help="Show calls from a function in execution order")(calls.calls_cmd)
app.command(name="source", help="Display source code for definitions")(source.source_cmd)


def main():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
