"""Index command for JediDB CLI."""

import sys
from pathlib import Path
from typing import Optional

import typer

from jedidb import JediDB
from jedidb.cli.formatters import get_source_path, get_index_path, print_success, print_error, print_info


def index_cmd(
    ctx: typer.Context,
    paths: Optional[list[str]] = typer.Argument(
        None,
        help="Paths to index (default: source root)",
    ),
    include: Optional[list[str]] = typer.Option(
        None,
        "--include",
        "-i",
        help="Patterns to include (e.g., 'src/' or 'mymodule')",
    ),
    exclude: Optional[list[str]] = typer.Option(
        None,
        "--exclude",
        "-e",
        help="Patterns to exclude (e.g., 'Testing' or 'test_')",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force re-indexing of all files",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress progress output",
    ),
    resolve_refs: bool = typer.Option(
        True,
        "--resolve-refs/--no-resolve-refs",
        "-r/-R",
        help="Resolve reference targets for call graph (default: enabled)",
    ),
    base_classes: bool = typer.Option(
        True,
        "--base-classes/--no-base-classes",
        help="Track class inheritance (default: enabled)",
    ),
):
    """Index Python files in the project.

    Only changed files are re-indexed unless --force is used.
    Data is stored as compressed parquet files (~30-40x smaller than DuckDB).
    """
    source = get_source_path(ctx)
    index = get_index_path(ctx)

    try:
        jedidb = JediDB(source=source, index=index, resolve_refs=resolve_refs, base_classes=base_classes)
    except Exception as e:
        print_error(f"Failed to initialize database: {e}")
        raise typer.Exit(1)

    # Merge include/exclude with config
    all_include = list(include or []) + jedidb.config.include_patterns
    all_exclude = list(exclude or []) + jedidb.config.exclude_patterns

    # Use Rich progress bar only for TTY, otherwise simple text
    use_progress_bar = not quiet and sys.stderr.isatty()

    if use_progress_bar:
        from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
        from rich.console import Console

        console = Console(stderr=True)
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

            stats = jedidb.index_files(
                paths=paths,
                include=all_include if all_include else None,
                exclude=all_exclude if all_exclude else None,
                force=force,
            )
    elif not quiet:
        def on_progress(file_path: str, current: int, total: int):
            print(f"Indexing [{current}/{total}]: {Path(file_path).name}", file=sys.stderr)

        jedidb.indexer.progress_callback = on_progress

        stats = jedidb.index_files(
            paths=paths,
            include=all_include if all_include else None,
            exclude=all_exclude if all_exclude else None,
            force=force,
        )
    else:
        stats = jedidb.index_files(
            paths=paths,
            include=all_include if all_include else None,
            exclude=all_exclude if all_exclude else None,
            force=force,
        )

    jedidb.close()

    # Print results
    print()
    print_success(f"Indexed {stats['files_indexed']} files")

    if stats["files_skipped"] > 0:
        print_info(f"Skipped {stats['files_skipped']} unchanged files")

    if stats["files_removed"] > 0:
        print_info(f"Removed {stats['files_removed']} deleted files")

    print()
    print(f"  Definitions: {stats['definitions_added']}")
    print(f"  References:  {stats['references_added']}")
    print(f"  Imports:     {stats['imports_added']}")

    if stats.get("packed"):
        print(f"  Packed:      {stats['parquet_size']:,} bytes")

    if stats["errors"]:
        print()
        print_error(f"Errors in {len(stats['errors'])} files:")
        for err in stats["errors"][:5]:
            print(f"  {err['file']}: {err['error']}", file=sys.stderr)
        if len(stats["errors"]) > 5:
            print(f"  ... and {len(stats['errors']) - 5} more", file=sys.stderr)
