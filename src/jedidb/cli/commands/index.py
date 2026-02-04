"""Index command for JediDB CLI."""

from pathlib import Path
from typing import Optional

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from jedidb import JediDB
from jedidb.config import Config
from jedidb.cli.formatters import console, print_success, print_error, print_info


def index_cmd(
    ctx: typer.Context,
    paths: Optional[list[str]] = typer.Argument(
        None,
        help="Paths to index (default: project root)",
    ),
    include: Optional[list[str]] = typer.Option(
        None,
        "--include",
        "-i",
        help="Glob patterns to include (e.g., 'src/**/*.py')",
    ),
    exclude: Optional[list[str]] = typer.Option(
        None,
        "--exclude",
        "-e",
        help="Glob patterns to exclude (e.g., '**/test_*.py')",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force re-indexing of all files",
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
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress progress output",
    ),
):
    """Index Python files in the project.

    Only changed files are re-indexed unless --force is used.
    Data is stored as compressed parquet files (~30-40x smaller than DuckDB).
    """
    from jedidb.cli.formatters import get_project_path

    # Find project root (command -C takes precedence over global -C)
    project_root = project or get_project_path(ctx)
    if project_root is None:
        project_root = Config.find_project_root()
    if project_root is None:
        project_root = Path.cwd()

    try:
        jedidb = JediDB(path=str(project_root), db_path=str(db_path) if db_path else None)
    except Exception as e:
        print_error(f"Failed to initialize database: {e}")
        raise typer.Exit(1)

    # Merge include/exclude with config
    all_include = list(include or []) + jedidb.config.include_patterns
    all_exclude = list(exclude or []) + jedidb.config.exclude_patterns

    if not quiet:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Indexing files...", total=None)

            def on_progress(file_path: str, current: int, total: int):
                progress.update(task, total=total, completed=current, description=f"Indexing: {Path(file_path).name}")

            jedidb.indexer.progress_callback = on_progress

            stats = jedidb.index(
                paths=paths,
                include=all_include if all_include else None,
                exclude=all_exclude if all_exclude else None,
                force=force,
            )
    else:
        stats = jedidb.index(
            paths=paths,
            include=all_include if all_include else None,
            exclude=all_exclude if all_exclude else None,
            force=force,
        )

    jedidb.close()

    # Print results
    console.print()
    print_success(f"Indexed {stats['files_indexed']} files")

    if stats["files_skipped"] > 0:
        print_info(f"Skipped {stats['files_skipped']} unchanged files")

    if stats["files_removed"] > 0:
        print_info(f"Removed {stats['files_removed']} deleted files")

    console.print()
    console.print(f"  Definitions: {stats['definitions_added']}")
    console.print(f"  References:  {stats['references_added']}")
    console.print(f"  Imports:     {stats['imports_added']}")

    if stats.get("packed"):
        console.print(f"  Packed:      {stats['parquet_size']:,} bytes")

    if stats["errors"]:
        console.print()
        print_error(f"Errors in {len(stats['errors'])} files:")
        for err in stats["errors"][:5]:
            console.print(f"  [red]{err['file']}[/red]: {err['error']}")
        if len(stats["errors"]) > 5:
            console.print(f"  ... and {len(stats['errors']) - 5} more")
