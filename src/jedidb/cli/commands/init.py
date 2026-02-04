"""Init command for JediDB CLI."""

import sys

import typer

from jedidb.cli.formatters import get_source_path, get_index_path, print_success, print_info, print_warning


def init_cmd(
    ctx: typer.Context,
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing configuration",
    ),
):
    """Initialize jedidb in a project.

    Creates a .jedidb directory with config.toml and db/ subdirectory.
    """
    source = get_source_path(ctx)
    index = get_index_path(ctx)

    if not source.exists():
        print(f"Error: Source directory does not exist: {source}", file=sys.stderr)
        raise typer.Exit(1)

    # Check for existing configuration
    config_file = index / "config.toml"

    if config_file.exists() and not force:
        print_warning(f"Configuration already exists: {config_file}")
        print_info("Use --force to overwrite")
        raise typer.Exit(1)

    # Create index directory structure
    index.mkdir(parents=True, exist_ok=True)
    (index / "db").mkdir(exist_ok=True)
    print_success(f"Created index directory: {index}")

    # Create default config file
    if not config_file.exists() or force:
        config_file.write_text('# JediDB Configuration\n\n# include = ["**/*.py"]\n# exclude = ["**/test_*.py"]\n')
        print_success(f"Created configuration: {config_file}")

    # Add .jedidb to .gitignore if it exists and index is inside source
    if index.is_relative_to(source):
        gitignore_path = source / ".gitignore"
        relative_index = index.relative_to(source)
        gitignore_entry = f"{relative_index}/"

        if gitignore_path.exists():
            gitignore_content = gitignore_path.read_text()
            if gitignore_entry not in gitignore_content and ".jedidb/" not in gitignore_content:
                with open(gitignore_path, "a") as f:
                    f.write(f"\n# JediDB\n{gitignore_entry}\n")
                print_success(f"Added {gitignore_entry} to .gitignore")

    print()
    print_info("Next steps:")
    print("  1. Edit config.toml to configure include/exclude patterns (optional)")
    print("  2. Run 'jedidb index' to index your Python files")
    print("  3. Run 'jedidb search <query>' to search definitions")
