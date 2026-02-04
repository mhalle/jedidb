"""Search command for JediDB CLI."""

from enum import Enum
from typing import Optional

import typer

from jedidb import JediDB
from jedidb.cli.formatters import (
    get_source_path,
    get_index_path,
    format_search_results_table,
    format_json,
    get_default_format,
    OutputFormat,
    print_error,
    print_info,
)


class DefinitionType(str, Enum):
    function = "function"
    class_ = "class"
    variable = "variable"
    module = "module"
    param = "param"


def search_cmd(
    ctx: typer.Context,
    query: str = typer.Argument(
        ...,
        help="Search query (use * suffix for prefix search, e.g., 'get*')",
    ),
    type: Optional[DefinitionType] = typer.Option(
        None,
        "--type",
        "-t",
        help="Filter by definition type",
    ),
    limit: int = typer.Option(
        20,
        "--limit",
        "-n",
        help="Maximum number of results",
    ),
    include_private: bool = typer.Option(
        False,
        "--private",
        "-p",
        help="Include private definitions (starting with _)",
    ),
    output_format: Optional[OutputFormat] = typer.Option(
        None,
        "--format",
        "-f",
        help="Output format (default: table for terminal, jsonl for pipes)",
    ),
):
    """Full-text search for definitions.

    Search across function names, class names, and docstrings.
    """
    # Resolve output format (table for TTY, jsonl for pipes)
    if output_format is None:
        output_format = get_default_format()

    source = get_source_path(ctx)
    index = get_index_path(ctx)

    try:
        jedidb = JediDB(source=source, index=index)
    except Exception as e:
        print_error(f"Failed to open database: {e}")
        raise typer.Exit(1)

    results = jedidb.search_engine.search(
        query,
        type=type.value if type else None,
        limit=limit,
        include_private=include_private,
    )

    jedidb.close()

    if not results:
        print_info("No results found")
        raise typer.Exit(0)

    if output_format == OutputFormat.json:
        data = [
            {
                "name": r.definition.name,
                "full_name": r.definition.full_name,
                "type": r.definition.type,
                "file": r.definition.file_path,
                "line": r.definition.line,
                "score": r.score,
                "signature": r.definition.signature,
                "docstring": r.definition.docstring,
            }
            for r in results
        ]
        print(format_json(data))
    elif output_format == OutputFormat.jsonl:
        import json
        for r in results:
            print(json.dumps({
                "name": r.definition.name,
                "full_name": r.definition.full_name,
                "type": r.definition.type,
                "file": r.definition.file_path,
                "line": r.definition.line,
                "score": r.score,
                "signature": r.definition.signature,
                "docstring": r.definition.docstring,
            }, separators=(",", ":")))
    else:
        print(format_search_results_table(results))
        print(f"\n{len(results)} result(s)")
