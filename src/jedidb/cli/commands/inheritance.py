"""Inheritance command for JediDB CLI."""

from typing import Optional

import typer

from jedidb import JediDB
from jedidb.cli.formatters import (
    get_source_path,
    get_index_path,
    format_json,
    get_default_format,
    OutputFormat,
    print_error,
    print_info,
)


def format_inheritance_table(bases: list[dict], show_position: bool = False) -> str:
    """Format base classes as a plain text table."""
    if not bases:
        return "No base classes found."

    lines = []
    if show_position:
        lines.append(f"{'Pos':>3}  {'Base Name':<30} {'Full Name'}")
        lines.append("-" * 80)
        for b in bases:
            lines.append(
                f"{b.get('position', 0):>3}  "
                f"{b.get('base_name', ''):<30} {b.get('base_full_name', '') or '(unresolved)'}"
            )
    else:
        lines.append(f"{'Base Name':<30} {'Full Name'}")
        lines.append("-" * 75)
        for b in bases:
            lines.append(
                f"{b.get('base_name', ''):<30} {b.get('base_full_name', '') or '(unresolved)'}"
            )

    return "\n".join(lines)


def format_children_table(children: list[dict]) -> str:
    """Format child classes as a plain text table."""
    if not children:
        return "No subclasses found."

    lines = []
    lines.append(f"{'Class Name':<40} {'File'}")
    lines.append("-" * 80)
    for c in children:
        lines.append(f"{c.get('full_name', ''):<40} {c.get('file_path', '')}")

    return "\n".join(lines)


def format_tree(
    jedidb: JediDB,
    full_name: str,
    prefix: str = "",
    is_last: bool = True,
    direction: str = "up",
    visited: set | None = None,
    depth: int = 0,
    max_depth: int = 10,
) -> list[str]:
    """Format inheritance as a tree.

    Args:
        direction: "up" for ancestors, "down" for descendants, "both" for full tree
    """
    if visited is None:
        visited = set()

    if full_name in visited or depth > max_depth:
        return []

    visited.add(full_name)

    lines = []
    connector = "`-- " if is_last else "|-- "

    if depth == 0:
        lines.append(full_name)
    else:
        lines.append(f"{prefix}{connector}{full_name}")

    extension = "    " if is_last else "|   "
    new_prefix = prefix + extension if depth > 0 else ""

    if direction in ("up", "both"):
        # Get base classes (ancestors)
        query = """
            SELECT base_full_name FROM class_bases cb
            JOIN definitions d ON cb.class_id = d.id
            WHERE d.full_name = ?
            ORDER BY cb.position
        """
        results = jedidb.db.execute(query, (full_name,)).fetchall()
        bases = [r[0] for r in results if r[0]]

        for i, base in enumerate(bases):
            is_last_base = i == len(bases) - 1 and direction == "up"
            child_lines = format_tree(
                jedidb, base, new_prefix, is_last_base, "up", visited, depth + 1, max_depth
            )
            lines.extend(child_lines)

    if direction in ("down", "both"):
        # Get child classes (descendants)
        query = """
            SELECT d.full_name FROM class_bases cb
            JOIN definitions d ON cb.class_id = d.id
            WHERE cb.base_full_name = ?
            ORDER BY d.full_name
        """
        results = jedidb.db.execute(query, (full_name,)).fetchall()
        children = [r[0] for r in results if r[0]]

        for i, child in enumerate(children):
            is_last_child = i == len(children) - 1
            child_lines = format_tree(
                jedidb, child, new_prefix, is_last_child, "down", visited, depth + 1, max_depth
            )
            lines.extend(child_lines)

    return lines


def inheritance_cmd(
    ctx: typer.Context,
    name: str = typer.Argument(
        ...,
        help="Class name or full name to show inheritance for",
    ),
    children: bool = typer.Option(
        False,
        "--children",
        "-c",
        help="Show classes that inherit from this class",
    ),
    tree: bool = typer.Option(
        False,
        "--tree",
        "-t",
        help="Show full inheritance tree (ancestors and descendants)",
    ),
    output_format: Optional[OutputFormat] = typer.Option(
        None,
        "--format",
        "-f",
        help="Output format (default: table for terminal, jsonl for pipes)",
    ),
):
    """Show class inheritance relationships.

    By default, shows what a class inherits from (its base classes).
    Use --children to show what inherits from the class.
    Use --tree to show the full inheritance hierarchy.

    Examples:

        jedidb inheritance MyClass              # Show base classes

        jedidb inheritance MyClass --children   # Show subclasses

        jedidb inheritance MyClass --tree       # Full inheritance tree

        jedidb inheritance BaseModel --format json
    """
    if output_format is None:
        output_format = get_default_format()

    source = get_source_path(ctx)
    index = get_index_path(ctx)

    try:
        jedidb = JediDB(source=source, index=index)
    except Exception as e:
        print_error(f"Failed to open database: {e}")
        raise typer.Exit(1)

    # Find the class
    definition = jedidb.search_engine.get_definition(name)

    if not definition:
        jedidb.close()
        print_error(f"Definition not found: {name}")
        raise typer.Exit(1)

    if definition.type != "class":
        jedidb.close()
        print_error(f"'{name}' is a {definition.type}, not a class")
        raise typer.Exit(1)

    if tree:
        # Show full inheritance tree
        lines = format_tree(jedidb, definition.full_name, direction="both")
        jedidb.close()

        if output_format == OutputFormat.json:
            # For JSON, we need structured data
            print(format_json({"tree": lines}))
        else:
            print(f"Inheritance tree for {definition.full_name}:")
            print()
            for line in lines:
                print(line)
    elif children:
        # Show what inherits from this class
        query = """
            SELECT d.full_name, d.name, f.path
            FROM class_bases cb
            JOIN definitions d ON cb.class_id = d.id
            JOIN files f ON d.file_id = f.id
            WHERE cb.base_full_name = ?
            ORDER BY d.full_name
        """
        results = jedidb.db.execute(query, (definition.full_name,)).fetchall()
        jedidb.close()

        child_classes = [
            {"full_name": r[0], "name": r[1], "file_path": r[2]}
            for r in results
        ]

        if not child_classes:
            print_info(f"No classes inherit from {definition.full_name}")
            raise typer.Exit(0)

        if output_format == OutputFormat.json:
            print(format_json(child_classes))
        elif output_format == OutputFormat.jsonl:
            import json
            for c in child_classes:
                print(json.dumps(c, separators=(",", ":")))
        else:
            print(f"Classes inheriting from {definition.full_name}:")
            print()
            print(format_children_table(child_classes))
            print(f"\n{len(child_classes)} subclass(es)")
    else:
        # Show what this class inherits from (default)
        query = """
            SELECT cb.base_name, cb.base_full_name, cb.base_id, cb.position
            FROM class_bases cb
            JOIN definitions d ON cb.class_id = d.id
            WHERE d.full_name = ?
            ORDER BY cb.position
        """
        results = jedidb.db.execute(query, (definition.full_name,)).fetchall()
        jedidb.close()

        bases = [
            {
                "base_name": r[0],
                "base_full_name": r[1],
                "base_id": r[2],
                "position": r[3],
            }
            for r in results
        ]

        if not bases:
            print_info(f"No base classes found for {definition.full_name}")
            raise typer.Exit(0)

        if output_format == OutputFormat.json:
            print(format_json(bases))
        elif output_format == OutputFormat.jsonl:
            import json
            for b in bases:
                print(json.dumps(b, separators=(",", ":")))
        else:
            print(f"Base classes of {definition.full_name}:")
            print()
            print(format_inheritance_table(bases, show_position=len(bases) > 1))
            print(f"\n{len(bases)} base class(es)")
