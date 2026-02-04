"""Show command for JediDB CLI."""

from typing import Optional

import typer

from jedidb import JediDB
from jedidb.cli.formatters import (
    get_source_path,
    get_index_path,
    format_definition_detail,
    format_references_table,
    format_json,
    print_error,
    print_info,
)


def show_cmd(
    ctx: typer.Context,
    name: str = typer.Argument(
        ...,
        help="Name or full name of the definition",
    ),
    refs: bool = typer.Option(
        False,
        "--refs",
        "-r",
        help="Show references to this definition",
    ),
    output_format: str = typer.Option(
        "pretty",
        "--format",
        "-f",
        help="Output format: pretty, json",
    ),
):
    """Show details for a definition.

    Display full information including signature, docstring, and optionally references.
    """
    source = get_source_path(ctx)
    index = get_index_path(ctx)

    try:
        jedidb = JediDB(source=source, index=index)
    except Exception as e:
        print_error(f"Failed to open database: {e}")
        raise typer.Exit(1)

    definition = jedidb.search_engine.get_definition(name)

    if not definition:
        jedidb.close()
        print_error(f"Definition not found: {name}")
        raise typer.Exit(1)

    references = []
    if refs:
        references = jedidb.search_engine.find_references(definition.name)

    jedidb.close()

    if output_format == "json":
        data = {
            "definition": {
                "id": definition.id,
                "name": definition.name,
                "full_name": definition.full_name,
                "type": definition.type,
                "file": definition.file_path,
                "line": definition.line,
                "column": definition.column,
                "signature": definition.signature,
                "docstring": definition.docstring,
                "is_public": definition.is_public,
            }
        }
        if refs:
            data["references"] = [
                {
                    "file": r.file_path,
                    "line": r.line,
                    "column": r.column,
                    "context": r.context,
                }
                for r in references
            ]
        print(format_json(data))
    else:
        print(format_definition_detail(definition))

        if refs:
            print()
            if references:
                print(f"References ({len(references)}):")
                print(format_references_table(references))
            else:
                print_info("No references found")
