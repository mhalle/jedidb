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
    include: list[str] = typer.Option(
        None,
        "--include",
        "-i",
        help="Patterns to include (e.g., 'src/' or 'mymodule')",
    ),
    exclude: list[str] = typer.Option(
        None,
        "--exclude",
        "-e",
        help="Patterns to exclude (e.g., 'Testing' or 'test_')",
    ),
):
    """Initialize jedidb in a project.

    Creates a .jedidb directory with config.toml and db/ subdirectory.

    Pattern syntax (patterns are expanded automatically):

        Testing     → **/Testing/**     Directory named 'Testing' anywhere

        test_       → **/test_*.py      Files starting with 'test_'

        _test       → **/*_test.py      Files ending with '_test'

        **/test*    → **/test*          Explicit glob (unchanged)

        src/        → src/**            Everything under src/

    Examples:

        jedidb init                              # Basic init

        jedidb init -e Testing -e test_          # Exclude Testing/ dirs and test_* files

        jedidb init -i src/ -e test_             # Only src/, excluding test_* files
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

    # Create config file
    if not config_file.exists() or force:
        config_lines = ["# JediDB Configuration", ""]

        if include:
            include_str = ", ".join(f'"{p}"' for p in include)
            config_lines.append(f"include = [{include_str}]")
        else:
            config_lines.append("# include = []  # Empty means all .py files (default)")

        if exclude:
            exclude_str = ", ".join(f'"{p}"' for p in exclude)
            config_lines.append(f"exclude = [{exclude_str}]")
        else:
            config_lines.append('# exclude = ["test_", "_test"]  # or use globs: "**/test_*.py"')

        config_lines.append("")
        config_file.write_text("\n".join(config_lines))
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
    if not include and not exclude:
        print("  1. Edit config.toml to configure include/exclude patterns (optional)")
        print("  2. Run 'jedidb index' to index your Python files")
        print("  3. Run 'jedidb search <query>' to search definitions")
    else:
        print("  1. Run 'jedidb index' to index your Python files")
        print("  2. Run 'jedidb search <query>' to search definitions")
