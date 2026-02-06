"""Index command for JediDB CLI."""

import shutil
import sys
from pathlib import Path
from typing import Optional

import typer

from jedidb import JediDB
from jedidb.cli.formatters import get_source_path, get_index_path, print_success, print_error, print_info, print_warning


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
        help="Patterns to include (e.g., 'src/', 'mymodule'); combined with config",
    ),
    exclude: Optional[list[str]] = typer.Option(
        None,
        "--exclude",
        "-e",
        help="Patterns to exclude (e.g., 'Testing', 'test_', '_test'); combined with config",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force re-indexing even if no files have changed",
    ),
    check: bool = typer.Option(
        False,
        "--check",
        "-c",
        help="Check if index is stale without indexing",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show list of changed/added/removed files (with --check)",
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

    If any files have changed since last indexing, all files are re-indexed
    to ensure cross-file references are consistent. If nothing has changed,
    indexing is skipped. Use --force to re-index regardless.

    Use --check to report staleness without indexing (exit 0 = up-to-date, 1 = stale).

    Data is stored as compressed parquet files (~30-40x smaller than DuckDB).

    Patterns use simplified syntax: 'Testing' matches directories, 'test_' matches
    file prefixes, '_test' matches suffixes. Full globs like '**/test_*.py' also work.
    """
    source = get_source_path(ctx)
    index = get_index_path(ctx)
    db_dir = index / "db"

    # Check mode: just report staleness
    if check:
        if not db_dir.exists():
            print_warning("No index found. Run 'jedidb index' to create one.")
            raise typer.Exit(1)

        try:
            jedidb = JediDB(source=source, index=index)
        except Exception as e:
            print_error(f"Failed to open database: {e}")
            raise typer.Exit(1)

        all_include = list(include or []) + jedidb.config.include_patterns
        all_exclude = list(exclude or []) + jedidb.config.exclude_patterns

        staleness = jedidb.indexer.check_staleness(
            include=all_include if all_include else None,
            exclude=all_exclude if all_exclude else None,
        )
        jedidb.close()

        if not staleness["is_stale"]:
            print_success("Index is up-to-date")
            raise typer.Exit(0)

        print_warning("Index is stale")
        print()

        changed = staleness["changed"]
        added = staleness["added"]
        removed = staleness["removed"]

        if changed:
            print(f"  Changed: {len(changed)} file(s)")
            if verbose:
                for f in changed[:10]:
                    print(f"    {f}")
                if len(changed) > 10:
                    print(f"    ... and {len(changed) - 10} more")

        if added:
            print(f"  Added:   {len(added)} file(s)")
            if verbose:
                for f in added[:10]:
                    print(f"    {f}")
                if len(added) > 10:
                    print(f"    ... and {len(added) - 10} more")

        if removed:
            print(f"  Removed: {len(removed)} file(s)")
            if verbose:
                for f in removed[:10]:
                    print(f"    {f}")
                if len(removed) > 10:
                    print(f"    ... and {len(removed) - 10} more")

        print()
        print_info("Run 'jedidb index' to update")
        raise typer.Exit(1)

    try:
        jedidb = JediDB(source=source, index=index, resolve_refs=resolve_refs, base_classes=base_classes)
    except Exception as e:
        # If database schema is incompatible and we have --force, reset and retry
        if force and db_dir.exists():
            print_warning(f"Database schema error, resetting: {e}")
            shutil.rmtree(db_dir)
            db_dir.mkdir(parents=True, exist_ok=True)
            try:
                jedidb = JediDB(source=source, index=index, resolve_refs=resolve_refs, base_classes=base_classes)
            except Exception as e2:
                print_error(f"Failed to initialize database after reset: {e2}")
                raise typer.Exit(1)
        else:
            print_error(f"Failed to initialize database: {e}")
            if db_dir.exists():
                print_error("Try 'jedidb index --force' to reset and reindex")
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

    # Print results
    print()

    if stats.get("index_skipped"):
        print_success(f"Index is up-to-date ({stats['files_skipped']} files)")
        jedidb.close()
        return

    print_success(f"Indexed {stats['files_indexed']} files")

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

    jedidb.close()
