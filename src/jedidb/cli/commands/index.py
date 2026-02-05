"""Index command for JediDB CLI."""

import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer

from jedidb import JediDB
from jedidb.cli.formatters import get_source_path, get_index_path, print_success, print_error, print_info, print_warning
from jedidb.utils import expand_pattern, glob_match


def make_watch_filter(exclude_patterns: list[str], source: Path):
    """Create a watchfiles filter from exclude patterns.

    Args:
        exclude_patterns: List of exclude patterns (simplified or full glob)
        source: Source directory for relative path matching

    Returns:
        Filter class for watchfiles
    """
    from watchfiles import DefaultFilter

    # Expand patterns once
    expanded_patterns = [expand_pattern(p) for p in exclude_patterns]

    class JediDBFilter(DefaultFilter):
        def __call__(self, change, path: str) -> bool:
            # Only watch .py files
            if not path.endswith('.py'):
                return False
            # Apply default filters (ignores .git, __pycache__, etc.)
            if not super().__call__(change, path):
                return False
            # Apply user exclude patterns
            try:
                rel_path = str(Path(path).relative_to(source))
            except ValueError:
                rel_path = path
            for pattern in expanded_patterns:
                if glob_match(rel_path, pattern):
                    return False
            return True

    return JediDBFilter()


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
        help="Force re-indexing of all files",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress progress output",
    ),
    watch: bool = typer.Option(
        False,
        "--watch",
        "-w",
        help="Watch for file changes and reindex incrementally",
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

    Patterns use simplified syntax: 'Testing' matches directories, 'test_' matches
    file prefixes, '_test' matches suffixes. Full globs like '**/test_*.py' also work.
    """
    source = get_source_path(ctx)
    index = get_index_path(ctx)
    db_dir = index / "db"

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

    # Close database after initial index
    jedidb.close()

    # Watch mode
    if watch:
        from watchfiles import watch as fs_watch, Change

        print()
        print_info(f"Watching {source} for changes... (Ctrl+C to stop)")

        # Build filter from config exclude patterns
        watch_filter = make_watch_filter(all_exclude, source)

        try:
            for changes in fs_watch(source, watch_filter=watch_filter):
                # Classify changes
                changed_files = []
                deleted_files = []
                for change_type, path in changes:
                    if not path.endswith('.py'):
                        continue
                    if change_type == Change.deleted:
                        deleted_files.append(path)
                    else:
                        changed_files.append(path)

                if not changed_files and not deleted_files:
                    continue

                # Show what changed
                timestamp = datetime.now().strftime("%H:%M:%S")
                if not quiet:
                    for path in changed_files:
                        print(f"[{timestamp}] Changed: {Path(path).name}")
                    for path in deleted_files:
                        print(f"[{timestamp}] Deleted: {Path(path).name}")

                # Open fresh database connection for this batch of changes
                try:
                    jedidb = JediDB(source=source, index=index, resolve_refs=resolve_refs, base_classes=base_classes)
                except Exception as e:
                    print_error(f"Failed to open database: {e}")
                    continue

                try:
                    # Reindex changed files
                    if changed_files:
                        file_stats = jedidb.index_files(paths=changed_files)
                        if not quiet:
                            print_success(f"Indexed {file_stats['files_indexed']} file(s)")
                        if file_stats["errors"]:
                            for err in file_stats["errors"]:
                                print_error(f"  {err['file']}: {err['error']}")

                    # Handle deletions
                    if deleted_files:
                        for path in deleted_files:
                            rel_path = str(Path(path).relative_to(source))
                            jedidb.db.delete_file_by_path(rel_path)
                        jedidb.db.export_to_parquet(jedidb.db_dir)
                        if not quiet:
                            print_success(f"Removed {len(deleted_files)} file(s)")
                except Exception as e:
                    print_error(f"Index error: {e}")
                finally:
                    jedidb.close()

        except KeyboardInterrupt:
            print("\nWatch mode stopped.")
