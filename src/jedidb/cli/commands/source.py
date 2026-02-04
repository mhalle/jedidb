"""Source command for JediDB CLI."""

import json
from pathlib import Path
from typing import Optional

import typer

from jedidb import JediDB
from jedidb.cli.formatters import (
    get_source_path,
    get_index_path,
    format_json,
    format_source_block,
    get_default_format,
    OutputFormat,
    print_error,
    print_info,
)


def source_cmd(
    ctx: typer.Context,
    name: Optional[str] = typer.Argument(
        None,
        help="Name or full name of the definition",
    ),
    id: Optional[int] = typer.Option(
        None,
        "--id",
        "-i",
        help="Look up definition by database ID",
    ),
    all_matches: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="List all definitions matching name (including imports)",
    ),
    context: int = typer.Option(
        2,
        "--context",
        "-c",
        help="Lines of context around code",
    ),
    calls: bool = typer.Option(
        False,
        "--calls",
        help="Show call sites with source context",
    ),
    refs: bool = typer.Option(
        False,
        "--refs",
        "-r",
        help="Show references with source context",
    ),
    output_format: Optional[OutputFormat] = typer.Option(
        None,
        "--format",
        "-f",
        help="Output format (default: table for terminal, jsonl for pipes)",
    ),
):
    """Display source code for definitions, call sites, or references.

    Shows the actual source code from files using stored line/column information.
    Output includes line numbers for easy navigation.

    Examples:

        jedidb source search_cmd              # full function body with line numbers

        jedidb source MyClass                 # full class body

        jedidb source --id 42                 # look up by database ID

        jedidb source SearchEngine --all      # list all matches (imports + definition)

        jedidb source parse --context 0       # just the definition, no context

        jedidb source parse --context 10      # 10 lines of context around code

        jedidb source Model.save --calls      # show all call sites with source

        jedidb source MyClass --refs          # show all references with source

        jedidb source parse --format json     # JSON output for tooling
    """
    if not name and id is None:
        print_error("Must provide either NAME argument or --id option")
        raise typer.Exit(1)

    if output_format is None:
        output_format = get_default_format()

    source_root = get_source_path(ctx)
    index = get_index_path(ctx)

    try:
        jedidb = JediDB(source=source_root, index=index)
    except Exception as e:
        print_error(f"Failed to open database: {e}")
        raise typer.Exit(1)

    # Handle --all: list all matching definitions
    if all_matches:
        if not name:
            jedidb.close()
            print_error("--all requires a NAME argument")
            raise typer.Exit(1)
        _list_all_definitions(jedidb, name, output_format)
        jedidb.close()
        raise typer.Exit(0)

    # Find the definition by ID or name
    if id is not None:
        definition = jedidb.search_engine.get_definition_by_id(id)
        if not definition:
            jedidb.close()
            print_error(f"Definition not found with ID: {id}")
            raise typer.Exit(1)
    else:
        definition = jedidb.search_engine.get_definition(name)
        if not definition:
            jedidb.close()
            print_error(f"Definition not found: {name}")
            raise typer.Exit(1)

    # Resolve file path
    file_path = _resolve_file_path(definition.file_path, source_root)

    if calls:
        _show_calls(jedidb, definition, source_root, context, output_format)
    elif refs:
        _show_refs(jedidb, definition, source_root, context, output_format)
    else:
        _show_definition(definition, file_path, context, output_format)

    jedidb.close()


def _resolve_file_path(file_path: str | None, source_root: Path) -> Path | None:
    """Resolve file path, joining with source root if relative."""
    if not file_path:
        return None
    path = Path(file_path)
    if path.is_absolute():
        return path
    return source_root / path


def _list_all_definitions(jedidb, name: str, output_format: OutputFormat):
    """List all definitions matching a name (including imports)."""
    query = """
        SELECT
            d.id, d.name, d.full_name, d.type,
            f.path, d.line, d.end_line,
            COALESCE(d.end_line, d.line) - d.line as size
        FROM definitions d
        JOIN files f ON d.file_id = f.id
        WHERE d.full_name = ? OR d.name = ?
        ORDER BY size DESC, f.path
    """
    results = jedidb.db.execute(query, (name, name)).fetchall()

    if not results:
        print_info(f"No definitions found matching: {name}")
        return

    if output_format == OutputFormat.json:
        data = [
            {
                "id": r[0],
                "name": r[1],
                "full_name": r[2],
                "type": r[3],
                "file": r[4],
                "line": r[5],
                "end_line": r[6],
                "size": r[7],
            }
            for r in results
        ]
        print(format_json(data))
    elif output_format == OutputFormat.jsonl:
        for r in results:
            data = {
                "id": r[0],
                "name": r[1],
                "full_name": r[2],
                "type": r[3],
                "file": r[4],
                "line": r[5],
                "end_line": r[6],
            }
            print(json.dumps(data, separators=(",", ":")))
    else:
        # Table format
        print(f"Definitions matching '{name}':")
        print()
        print(f"{'ID':>6}  {'Type':<10} {'Lines':>10}  {'File':<50}")
        print("-" * 80)
        for r in results:
            line_range = f"{r[5]}"
            if r[6] and r[6] != r[5]:
                line_range += f"-{r[6]}"
            size_note = "" if r[7] > 0 else " (import)"
            print(f"{r[0]:>6}  {r[3]:<10} {line_range:>10}  {r[4]:<50}{size_note}")
        print()
        print(f"{len(results)} definition(s). Use --id to view source.")


def _read_source_lines(
    file_path: Path,
    start_line: int,
    end_line: int | None,
    context: int,
) -> tuple[list[str], int, int]:
    """Read source lines from a file with context.

    Returns:
        Tuple of (lines, actual_start_line, actual_end_line)
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
    except Exception:
        return [], start_line, start_line

    # Calculate actual line range
    actual_start = max(1, start_line - context)
    if end_line is not None:
        actual_end = min(len(all_lines), end_line + context)
    else:
        actual_end = min(len(all_lines), start_line + context)

    # Extract lines (convert to 0-indexed)
    lines = all_lines[actual_start - 1 : actual_end]

    return lines, actual_start, actual_end


def _show_definition(
    definition,
    file_path: Path | None,
    context: int,
    output_format: OutputFormat,
):
    """Show source code for a definition."""
    if not file_path or not file_path.exists():
        print_error(f"Source file not found: {definition.file_path}")
        raise typer.Exit(1)

    lines, start, end = _read_source_lines(
        file_path,
        definition.line,
        definition.end_line,
        context,
    )

    if not lines:
        print_error(f"Could not read source from {file_path}")
        raise typer.Exit(1)

    if output_format == OutputFormat.json:
        data = {
            "definition": {
                "name": definition.name,
                "full_name": definition.full_name,
                "type": definition.type,
                "file": definition.file_path,
                "line": definition.line,
                "end_line": definition.end_line,
            },
            "source": {
                "start_line": start,
                "end_line": end,
                "lines": [line.rstrip("\n") for line in lines],
            },
        }
        print(format_json(data))
    elif output_format == OutputFormat.jsonl:
        data = {
            "full_name": definition.full_name,
            "file": definition.file_path,
            "line": definition.line,
            "end_line": definition.end_line,
            "source": "".join(lines),
        }
        print(json.dumps(data, separators=(",", ":")))
    else:
        # Table format
        print(f"{definition.full_name or definition.name}")
        line_range = f"{definition.line}"
        if definition.end_line and definition.end_line != definition.line:
            line_range += f"-{definition.end_line}"
        print(f"{definition.file_path}:{line_range}")
        print()
        print(format_source_block(lines, start))


def _show_calls(
    jedidb,
    definition,
    source_root: Path,
    context: int,
    output_format: OutputFormat,
):
    """Show call sites from a function with source context."""
    if definition.type not in ("function", "class"):
        print_error(f"'{definition.name}' is a {definition.type}, not a function or class")
        raise typer.Exit(1)

    # Query calls
    query = """
        SELECT DISTINCT
            c.callee_full_name,
            c.callee_name,
            f.path,
            c.line,
            c.col,
            c.context,
            c.call_order
        FROM calls c
        JOIN files f ON c.file_id = f.id
        WHERE c.caller_full_name = ?
        ORDER BY c.call_order
    """
    results = jedidb.db.execute(query, (definition.full_name,)).fetchall()

    if not results:
        print_info(f"No calls found in {definition.full_name}")
        raise typer.Exit(0)

    if output_format == OutputFormat.json:
        _output_calls_json(results, source_root, context)
    elif output_format == OutputFormat.jsonl:
        _output_calls_jsonl(results, source_root, context)
    else:
        _output_calls_table(results, source_root, context, definition)


def _output_calls_json(results, source_root: Path, context: int):
    """Output calls in JSON format."""
    calls = []
    for r in results:
        file_path = _resolve_file_path(r[2], source_root)
        lines, start, end = _read_source_lines(file_path, r[3], None, context) if file_path else ([], 0, 0)
        calls.append({
            "callee_full_name": r[0],
            "callee_name": r[1],
            "file": r[2],
            "line": r[3],
            "column": r[4],
            "call_order": r[6],
            "source": {
                "start_line": start,
                "end_line": end,
                "lines": [line.rstrip("\n") for line in lines],
            },
        })
    print(format_json(calls))


def _output_calls_jsonl(results, source_root: Path, context: int):
    """Output calls in JSONL format."""
    for r in results:
        file_path = _resolve_file_path(r[2], source_root)
        lines, _, _ = _read_source_lines(file_path, r[3], None, context) if file_path else ([], 0, 0)
        data = {
            "callee_full_name": r[0],
            "callee_name": r[1],
            "file": r[2],
            "line": r[3],
            "source": "".join(lines),
        }
        print(json.dumps(data, separators=(",", ":")))


def _output_calls_table(results, source_root: Path, context: int, definition):
    """Output calls in table format."""
    print(f"Calls from {definition.full_name}:")
    print()

    for r in results:
        file_path = _resolve_file_path(r[2], source_root)
        if not file_path or not file_path.exists():
            continue

        lines, start, _ = _read_source_lines(file_path, r[3], None, context)
        if lines:
            print(f"{r[2]}:{r[3]}")
            print(format_source_block(lines, start))
            print()

    print(f"{len(results)} call(s)")


def _show_refs(
    jedidb,
    definition,
    source_root: Path,
    context: int,
    output_format: OutputFormat,
):
    """Show references to a definition with source context."""
    references = jedidb.search_engine.find_references(definition.name)

    if not references:
        print_info(f"No references found for {definition.name}")
        raise typer.Exit(0)

    if output_format == OutputFormat.json:
        _output_refs_json(references, source_root, context)
    elif output_format == OutputFormat.jsonl:
        _output_refs_jsonl(references, source_root, context)
    else:
        _output_refs_table(references, source_root, context, definition)


def _output_refs_json(references, source_root: Path, context: int):
    """Output references in JSON format."""
    refs = []
    for r in references:
        file_path = _resolve_file_path(r.file_path, source_root)
        lines, start, end = _read_source_lines(file_path, r.line, None, context) if file_path else ([], 0, 0)
        refs.append({
            "file": r.file_path,
            "line": r.line,
            "column": r.column,
            "context": r.context,
            "source": {
                "start_line": start,
                "end_line": end,
                "lines": [line.rstrip("\n") for line in lines],
            },
        })
    print(format_json(refs))


def _output_refs_jsonl(references, source_root: Path, context: int):
    """Output references in JSONL format."""
    for r in references:
        file_path = _resolve_file_path(r.file_path, source_root)
        lines, _, _ = _read_source_lines(file_path, r.line, None, context) if file_path else ([], 0, 0)
        data = {
            "file": r.file_path,
            "line": r.line,
            "source": "".join(lines),
        }
        print(json.dumps(data, separators=(",", ":")))


def _output_refs_table(references, source_root: Path, context: int, definition):
    """Output references in table format."""
    print(f"References to {definition.full_name or definition.name}:")
    print()

    for r in references:
        file_path = _resolve_file_path(r.file_path, source_root)
        if not file_path or not file_path.exists():
            continue

        lines, start, _ = _read_source_lines(file_path, r.line, None, context)
        if lines:
            print(f"{r.file_path}:{r.line}")
            print(format_source_block(lines, start))
            print()

    print(f"{len(references)} reference(s)")
