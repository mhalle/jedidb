"""Clean command for JediDB CLI."""

from pathlib import Path
from typing import Optional

import typer

from jedidb import JediDB
from jedidb.config import Config
from jedidb.cli.formatters import console, print_success, print_error, print_warning


def clean_cmd(
    ctx: typer.Context,
    all: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Remove all data and reset database",
    ),
    stale: bool = typer.Option(
        True,
        "--stale/--no-stale",
        help="Remove entries for deleted files",
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
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Skip confirmation prompt",
    ),
):
    """Remove stale entries or reset the database.

    By default, removes entries for files that no longer exist.
    Use --all to completely reset the database.
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
        print_error(f"Failed to open database: {e}")
        raise typer.Exit(1)

    if all:
        if not force:
            confirm = typer.confirm("This will delete all indexed data. Continue?")
            if not confirm:
                jedidb.close()
                print_warning("Aborted")
                raise typer.Exit(0)

        # Drop all data
        jedidb.db.execute("DELETE FROM refs")
        jedidb.db.execute("DELETE FROM imports")
        jedidb.db.execute("DELETE FROM definitions")
        jedidb.db.execute("DELETE FROM files")
        jedidb.close()
        print_success("Database reset successfully")
        return

    if stale:
        # Find files that no longer exist
        result = jedidb.db.execute("SELECT id, path FROM files").fetchall()
        removed = 0

        for file_id, file_path in result:
            full_path = project_root / file_path
            if not full_path.exists():
                jedidb.db.delete_file(file_id)
                removed += 1
                console.print(f"[dim]Removed:[/dim] {file_path}")

        jedidb.close()

        if removed > 0:
            print_success(f"Removed {removed} stale file entries")
        else:
            console.print("[dim]No stale entries found[/dim]")
