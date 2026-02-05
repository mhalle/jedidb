"""Main Typer application for JediDB CLI."""

from importlib.resources import files
from pathlib import Path
from typing import Optional

import typer

from jedidb.cli.commands import init, index, search, query, show, export, stats, clean, calls, source, inheritance


app = typer.Typer(
    name="jedidb",
    help="Jedi code analyzer with DuckDB storage and full-text search.",
    add_completion=False,
    rich_markup_mode=None,
    pretty_exceptions_enable=False,
)


@app.callback(invoke_without_command=True)
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
    readme: bool = typer.Option(
        False,
        "--readme",
        help="Print the README and exit",
    ),
):
    """Jedi code analyzer with DuckDB storage and full-text search."""
    if readme:
        try:
            readme_text = files("jedidb").joinpath("README.md").read_text()
            print(readme_text)
        except FileNotFoundError:
            # Fallback for development: read from project root
            project_readme = Path(__file__).parent.parent.parent.parent / "README.md"
            if project_readme.exists():
                print(project_readme.read_text())
            else:
                print("README.md not found")
                raise typer.Exit(1)
        raise typer.Exit(0)

    # Show help if no command provided
    if ctx.invoked_subcommand is None:
        print(ctx.get_help())
        raise typer.Exit(0)

    ctx.ensure_object(dict)

    source_path = (source or Path.cwd()).resolve()
    index_path = (index_dir or source_path / ".jedidb").resolve()

    ctx.obj["source"] = source_path
    ctx.obj["index"] = index_path


app.command(name="init")(init.init_cmd)
app.command(name="index")(index.index_cmd)
app.command(name="search")(search.search_cmd)
app.command(name="query")(query.query_cmd)
app.command(name="show")(show.show_cmd)
app.command(name="export")(export.export_cmd)
app.command(name="stats")(stats.stats_cmd)
app.command(name="clean")(clean.clean_cmd)
app.command(name="calls")(calls.calls_cmd)
app.command(name="source")(source.source_cmd)
app.command(name="inheritance")(inheritance.inheritance_cmd)


def main():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
