"""Init command for JediDB CLI."""

from pathlib import Path
from typing import Optional

import typer

from jedidb.config import Config, create_config_file, DEFAULT_DB_DIR
from jedidb.core.database import Database
from jedidb.cli.formatters import console, print_success, print_info, print_warning


def init_cmd(
    path: Optional[Path] = typer.Argument(
        None,
        help="Project path to initialize (default: current directory)",
    ),
    db_path: Optional[Path] = typer.Option(
        None,
        "--db-path",
        "-d",
        help="Custom database path",
    ),
    include: Optional[list[str]] = typer.Option(
        None,
        "--include",
        "-i",
        help="Glob pattern for files to include (can be used multiple times)",
    ),
    exclude: Optional[list[str]] = typer.Option(
        None,
        "--exclude",
        "-e",
        help="Glob pattern for files to exclude (can be used multiple times)",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing configuration",
    ),
):
    """Initialize jedidb in a project.

    Creates a .jedidb directory and configuration file.
    """
    project_path = (path or Path.cwd()).resolve()

    if not project_path.exists():
        console.print(f"[red]Error:[/red] Path does not exist: {project_path}")
        raise typer.Exit(1)

    # Check for existing configuration
    config_file = project_path / ".jedidb.toml"
    db_dir = project_path / DEFAULT_DB_DIR

    if config_file.exists() and not force:
        print_warning(f"Configuration already exists: {config_file}")
        print_info("Use --force to overwrite")
        raise typer.Exit(1)

    # Create .jedidb directory
    db_dir.mkdir(exist_ok=True)
    print_success(f"Created directory: {db_dir}")

    # Create configuration file
    config_path = create_config_file(project_path, db_path, include, exclude)
    print_success(f"Created configuration: {config_path}")

    # Initialize database
    config = Config(project_path=project_path, db_path=db_path)
    db = Database(config.db_path)
    db.close()
    print_success(f"Initialized database: {config.db_path}")

    # Add .jedidb to .gitignore if it exists
    gitignore_path = project_path / ".gitignore"
    if gitignore_path.exists():
        gitignore_content = gitignore_path.read_text()
        if ".jedidb/" not in gitignore_content:
            with open(gitignore_path, "a") as f:
                f.write("\n# JediDB\n.jedidb/\n")
            print_success("Added .jedidb/ to .gitignore")

    console.print()
    print_info("Next steps:")
    if not include and not exclude:
        console.print("  1. Edit .jedidb.toml to configure include/exclude patterns (optional)")
        console.print("  2. Run [cyan]jedidb index[/cyan] to index your Python files")
    else:
        console.print("  1. Run [cyan]jedidb index[/cyan] to index your Python files")
    console.print(f"  {'3' if not include and not exclude else '2'}. Run [cyan]jedidb search <query>[/cyan] to search definitions")
