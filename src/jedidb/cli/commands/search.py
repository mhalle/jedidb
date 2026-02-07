"""Search command for JediDB CLI."""

from enum import Enum
from pathlib import Path
from typing import Optional

import typer

from jedidb import JediDB
from jedidb.cli.formatters import (
    get_source_path,
    get_index_path,
    format_search_results_table,
    format_data_json,
    format_data_jsonl,
    format_data_csv,
    resolve_output_format,
    write_output,
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
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file (format auto-detected from extension: .json, .jsonl, .csv)",
    ),
):
    """Full-text search for definitions.

    Search across function names, class names, and docstrings.
    Supports CamelCase/snake_case aware matching.

    Examples:

        jedidb search parse              # finds parse, parseJSON, parse_config

        jedidb search "get*"             # prefix search: getValue, get_config

        jedidb search Model --type class # only classes

        jedidb search test -p            # include private (_test, __init__)

        jedidb search api --format json  # JSON output for scripting

        jedidb search api -o results.csv # output to CSV file
    """
    output_format = resolve_output_format(output_format, output)

    source = get_source_path(ctx)
    index = get_index_path(ctx)

    try:
        jedidb = JediDB(source=source, index=index)
    except Exception as e:
        print_error(f"Failed to open database: {e}")
        raise typer.Exit(1)

    try:
        results = jedidb.search_engine.search(
            query,
            type=type.value if type else None,
            limit=limit,
            include_private=include_private,
        )
    finally:
        jedidb.close()

    if not results:
        print_info("No results found")
        raise typer.Exit(0)

    # Convert results to list of dicts
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

    # Format output
    if output_format == OutputFormat.json:
        content = format_data_json(data)
    elif output_format == OutputFormat.jsonl:
        content = format_data_jsonl(data)
    elif output_format == OutputFormat.csv:
        content = format_data_csv(data)
    else:
        content = format_search_results_table(results) + f"\n\n{len(results)} result(s)"

    write_output(content, output, len(results))
