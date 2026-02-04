# JediDB

Python code index with Jedi analysis and full-text search.

## What Can JediDB Do?

- **Search code** - Full-text search across function names, class names, and docstrings
- **View source** - Display actual source code for any definition with line numbers
- **Navigate call graphs** - See what functions call what, in execution order
- **Find references** - Locate all usages of a function or class
- **Run SQL queries** - Query the indexed codebase with SQL (DuckDB)
- **Export data** - Export definitions, references, and calls to JSON/CSV

```bash
# Get help on any command
jedidb --help
jedidb search --help
jedidb source --help
```

## Features

- **Code Analysis**: Extracts definitions, references, imports, and decorators using Jedi
- **Call Graph**: Optional reference resolution to build caller/callee relationships
- **Parent Hierarchy**: Track class methods, nested functions, and module-level definitions
- **Definition Ranges**: End line/column for each definition (enables "large function" queries)
- **Compact Storage**: Parquet files with zstd compression (~1.5MB for 24K definitions)
- **Full-Text Search**: BM25 ranking with CamelCase/snake_case tokenization
- **Prefix Search**: Find definitions starting with a pattern (e.g., `get*`)
- **Incremental Updates**: Only re-indexes changed files
- **CLI & Library**: Command line tool and Python API

## Installation

```bash
pip install jedidb
```

Or with uv:

```bash
uv add jedidb
```

## Quick Start

```bash
# Initialize and index
jedidb init
jedidb index

# Index with call graph disabled (faster, but no caller/callee queries)
jedidb index --no-resolve-refs

# Search
jedidb search parse                    # full-text search
jedidb search "get*"                   # prefix search
jedidb search volume --type function   # filter by type
jedidb search test --format jsonl      # newline-delimited JSON output

# Explore
jedidb stats
jedidb show MyClass
jedidb source MyClass                  # view source code
jedidb query "SELECT name, type FROM definitions WHERE type = 'class'"

# Call graph (enabled by default)
jedidb calls MyClass.__init__          # what does this function call?
jedidb calls MyClass.__init__ --tree   # show as tree
jedidb source MyClass.__init__ --calls # call sites with source context
jedidb query "SELECT * FROM calls WHERE callee_full_name LIKE '%parse%'"
```

## CLI Reference

```
jedidb [-C DIR] COMMAND

Commands:
  init     Initialize jedidb in a project
  index    Index Python files (incremental by default)
  search   Full-text search definitions
  query    Run raw SQL queries
  show     Show details for a definition
  calls    Show calls from a function in execution order
  source   Display source code for definitions
  export   Export to JSON/CSV
  stats    Show database statistics
  clean    Remove stale entries or reset database
```

### search

```
jedidb search [OPTIONS] QUERY

Arguments:
  QUERY  Search query (use * suffix for prefix search, e.g., 'get*')

Options:
  -t, --type    [function|class|variable|module|param]  Filter by type
  -n, --limit   INTEGER                                  Max results [default: 20]
  -p, --private                                          Include private (_) defs
  -f, --format  [table|json|jsonl|csv]                   Output format (auto-detected)
  -C, --project DIRECTORY                                Project directory
```

### index

```
jedidb index [OPTIONS] [PATHS]...

Options:
  -i, --include               PATTERN  Glob patterns to include (e.g., 'src/**/*.py')
  -e, --exclude               PATTERN  Glob patterns to exclude
  -f, --force                          Force re-index all files
  -r, --resolve-refs (default)         Resolve reference targets (enables call graph)
  -R, --no-resolve-refs                Skip reference resolution (faster indexing)
  -C, --project                        Project directory
```

Reference resolution is enabled by default, building the call graph. Use `--no-resolve-refs` / `-R` for faster indexing if you don't need caller/callee queries (~30% faster).

### calls

```
jedidb calls [OPTIONS] NAME

Arguments:
  NAME  Name or full name of the function to show calls for

Options:
  -d, --depth INTEGER             Recursion depth for call tree [default: 1]
  -t, --top-level                 Only show top-level calls (not nested as arguments)
  --tree                          Show calls as a tree
  -f, --format [table|json|jsonl] Output format (auto-detected)
```

Show what a function calls in execution order:

```bash
jedidb calls Model.save              # Direct calls from Model.save
jedidb calls Model.save --depth 2    # Include calls made by callees
jedidb calls Model.save --top-level  # Only top-level calls (depth=1)
jedidb calls Model.save --tree       # Show as indented tree
```

### source

```
jedidb source [OPTIONS] [NAME]

Arguments:
  NAME  Name or full name of the definition

Options:
  -i, --id INTEGER                Look up definition by database ID
  -a, --all                       List all matches (including imports)
  -c, --context INTEGER           Lines of context around code [default: 2]
  --calls                         Show call sites with source context
  -r, --refs                      Show references with source context
  -f, --format [table|json|jsonl] Output format (auto-detected)
```

Display actual source code for definitions, call sites, or references:

```bash
jedidb source search_cmd              # Full function body with line numbers
jedidb source MyClass                 # Full class body
jedidb source --id 42                 # Look up by database ID (from query results)
jedidb source SearchEngine --all      # List all matches (imports + actual definition)
jedidb source search_cmd --context 5  # More context lines
jedidb source search_cmd --calls      # Call sites with source context
jedidb source search_cmd --refs       # References with source context
```

### Output Format Auto-Detection

Commands with `--format` option auto-detect the best format:
- **Interactive terminal**: `table` (human-readable)
- **Piped/redirected**: `jsonl` (full values, easy to parse)

Override with `--format table` or `--format jsonl` as needed.

## Library Usage

```python
from jedidb import JediDB

db = JediDB(path="./myproject")

# Index (includes call graph by default)
db.index(include=["src/**/*.py"], exclude=["**/test_*.py"])

# Index without reference resolution (faster, no call graph)
db = JediDB(path="./myproject", resolve_refs=False)
db.index()

# Search
results = db.search("parse", type="function", limit=10)
for r in results:
    print(f"{r.name} ({r.type}) {r.file_path}:{r.line}")

# Prefix search
results = db.search("get*")

# Get definition details
defn = db.get_definition("mymodule.MyClass")
print(defn.signature, defn.docstring)

# Find references
refs = db.references("MyClass")

# Raw SQL queries
rows = db.query("SELECT * FROM definitions WHERE type = 'class'")

# Call graph queries (enabled by default)
rows = db.query("""
    SELECT caller_full_name, callee_full_name
    FROM calls WHERE callee_full_name = 'mymodule.parse'
""")

db.close()
```

## Configuration

`.jedidb.toml` in project root:

```toml
[jedidb]
db_path = ".jedidb"

include = ["src/**/*.py"]
exclude = ["**/test_*.py", "**/*_test.py"]
```

## Storage

Data is stored as compressed parquet files in `.jedidb/`:

```
.jedidb/
  definitions.parquet   # functions, classes, variables (with end positions, parent info)
  files.parquet         # indexed files with hashes
  refs.parquet          # references/usages (with resolved targets by default)
  imports.parquet       # import statements
  decorators.parquet    # decorators on functions/classes
  calls.parquet         # call graph (built from resolved refs)
```

Typical sizes:
- 24K definitions → ~1.5MB total
- 264 files → 30-40x smaller than DuckDB

## Search Features

**Full-text search** with BM25 ranking:
```bash
jedidb search "parse json"      # finds parseJson, parse_json, JSONParser
```

**Prefix search** with `*` suffix:
```bash
jedidb search "get*"            # finds get, getattr, getValue, get_config
jedidb search "MRML*"           # case-insensitive prefix matching
```

**CamelCase/snake_case aware**: Searching `volume` finds `volumeNode`, `crop_volume`, `VolumeRenderer`.

## Database Schema

```sql
-- definitions: functions, classes, variables, params, modules
-- Includes end_line/end_column for definition ranges
-- parent_full_name links nested definitions to their parent
SELECT name, full_name, type, line, end_line, parent_full_name, signature
FROM definitions WHERE type = 'function';

-- files: indexed files with modification tracking
SELECT path, hash, size, indexed_at FROM files;

-- refs: references to names (target resolution enabled by default)
SELECT name, line, context, target_full_name, is_call FROM refs;

-- imports: import statements
SELECT module, name, alias FROM imports;

-- decorators: decorators on functions/classes
SELECT d.full_name, dec.name as decorator
FROM definitions d JOIN decorators dec ON dec.definition_id = d.id;

-- calls: call graph (populated by default)
SELECT caller_full_name, callee_full_name, line FROM calls;
```

## Example Queries

```sql
-- Who calls function X?
SELECT c.caller_full_name, f.path, c.line
FROM calls c JOIN files f ON c.file_id = f.id
WHERE c.callee_full_name = 'mymodule.my_function';

-- What does function X call?
SELECT DISTINCT c.callee_full_name FROM calls c
WHERE c.caller_full_name = 'mymodule.MyClass.__init__';

-- Methods of a class
SELECT name, type FROM definitions
WHERE parent_full_name = 'mymodule.MyClass';

-- Functions with @property decorator
SELECT d.full_name FROM definitions d
JOIN decorators dec ON dec.definition_id = d.id
WHERE dec.name = 'property';

-- Largest functions by line count
SELECT full_name, (end_line - line) as lines FROM definitions
WHERE type = 'function' AND end_line IS NOT NULL
ORDER BY lines DESC LIMIT 20;

-- Unused definitions (no incoming references)
SELECT d.full_name, d.type, f.path
FROM definitions d JOIN files f ON d.file_id = f.id
LEFT JOIN refs r ON r.target_full_name = d.full_name
WHERE r.id IS NULL AND d.type IN ('function', 'class');
```

## Requirements

- Python 3.12+
- jedi >= 0.19.0
- duckdb >= 1.0.0
- typer >= 0.12.0
- rich >= 13.0.0

## Credits

Built on [Jedi](https://github.com/davidhalter/jedi), the excellent Python static analysis library.

## License

Apache-2.0
