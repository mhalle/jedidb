"""Clean command for JediDB CLI."""

import typer

from jedidb import JediDB
from jedidb.cli.formatters import get_source_path, get_index_path, print_success, print_error, print_warning


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
    source = get_source_path(ctx)
    index = get_index_path(ctx)

    try:
        jedidb = JediDB(source=source, index=index)
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

        # Re-export to parquet (so next open gets empty database)
        jedidb.db.export_to_parquet(jedidb.db_dir)

        jedidb.close()
        print_success("Database reset successfully")
        return

    if stale:
        # Find files that no longer exist
        result = jedidb.db.execute("SELECT id, path FROM files").fetchall()
        removed = 0

        for file_id, file_path in result:
            full_path = source / file_path
            if not full_path.exists():
                jedidb.db.delete_file(file_id)
                removed += 1
                print(f"Removed: {file_path}")

        # Re-export to parquet if we removed anything
        if removed > 0:
            jedidb.db.export_to_parquet(jedidb.db_dir)

        jedidb.close()

        if removed > 0:
            print_success(f"Removed {removed} stale file entries")
        else:
            print("No stale entries found")
