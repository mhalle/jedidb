# JediDB

Python code index with Jedi analysis and full-text search.

## Why JediDB?

Built for **LLM-assisted code exploration**. Unlike embedding-based tools, JediDB uses [Jedi](https://github.com/davidhalter/jedi) for real Python semantic analysis - the same engine that powers IDE autocompletion.

| Feature | JediDB | Embedding tools | Call graph tools |
|---------|--------|-----------------|------------------|
| Semantic Python analysis | Yes (Jedi) | Approximations | AST only |
| Full-text + wildcard search | Yes | Vector similarity | No |
| Source display with context | Yes | No | No |
| Call graphs in execution order | Yes | No | Unordered |
| SQL queries on index | Yes | No | No |
| Structured JSON output | Auto-detected | Varies | No |
| No external services | Yes | Often needs Ollama/API | Yes |

**One tool** for search, source viewing, call navigation, and custom SQL queries - all with CLI-friendly JSON output.

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

- **Jedi-Powered Analysis**: Real Python semantic analysis - definitions, references, imports, decorators
- **Call Graphs**: Caller/callee relationships with execution order tracking
- **Source Display**: View actual source code with line numbers and configurable context
- **Full-Text Search**: BM25 ranking with CamelCase/snake_case tokenization
- **Wildcard Search**: Prefix (`get*`), suffix (`*Engine`), and pattern (`get*path`) matching
- **Watch Mode**: Automatically reindex files when they change
- **SQL Interface**: Query the index directly with DuckDB SQL
- **LLM-Friendly Output**: Auto-detects terminal vs pipe, outputs JSON/JSONL for tooling
- **Lightweight Storage**: Parquet files with zstd compression (~1.5MB for 24K definitions)
- **Incremental Updates**: Only re-indexes changed files
- **Zero Dependencies**: No cloud services, no Ollama, no API keys

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

# Watch for changes and reindex automatically
jedidb index --watch

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
  -i, --include PATTERN              Patterns to include (combined with config)
  -e, --exclude PATTERN              Patterns to exclude (combined with config)
  -f, --force                        Force re-index all files
  -q, --quiet                        Suppress progress output
  -w, --watch                        Watch for changes and reindex automatically
  -r, --resolve-refs (default)       Resolve reference targets (enables call graph)
  -R, --no-resolve-refs              Skip reference resolution (faster indexing)
  -C, --project                      Project directory
```

Patterns use simplified syntax: `Testing` matches directories, `test_` matches file prefixes, `_test` matches suffixes. Full globs like `**/test_*.py` also work. See [Include/Exclude Patterns](#includeexclude-patterns) for details.

Reference resolution is enabled by default, building the call graph. Use `--no-resolve-refs` / `-R` for faster indexing if you don't need caller/callee queries (~30% faster).

### Watch Mode

Watch mode monitors your source directory for file changes and automatically reindexes:

```bash
jedidb index --watch              # Index, then watch for changes
jedidb index --watch --quiet      # Watch with minimal output
```

When a Python file is modified, added, or deleted:
- **Modified/Added**: The file is reindexed incrementally
- **Deleted**: The file is removed from the index

The watcher respects your exclude patterns from both command-line (`--exclude`) and config file. Press `Ctrl+C` to stop watching.

Example output:
```
Watching /path/to/project for changes... (Ctrl+C to stop)
[14:32:15] Changed: mymodule.py
OK: Indexed 1 file(s)
[14:33:02] Deleted: old_file.py
OK: Removed 1 file(s)
```

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

`.jedidb/config.toml` in project root:

```toml
include = ["src/"]
exclude = ["Testing", "test_", "_test"]
```

### Include/Exclude Patterns

Patterns support a **simplified syntax** that expands to full globs:

| Pattern | Expands To | Matches |
|---------|-----------|---------|
| `Testing` | `**/Testing/**` | Any file under a `Testing/` directory |
| `test_` | `**/test_*.py` | Files starting with `test_` (trailing `_`) |
| `_test` | `**/*_test.py` | Files ending with `_test` (leading `_`) |
| `test_*` | `**/test_*.py` | Wildcard filename pattern |
| `src/` | `src/**` | Everything under `src/` directory |
| `src/utils/` | `src/utils/**` | Everything under `src/utils/` |
| `**/test_*.py` | `**/test_*.py` | Full glob (used as-is) |

**Examples:**
```toml
# Exclude test directories and test files
exclude = ["Testing", "test_", "_test"]

# Only index specific directories
include = ["src/", "lib/"]

# Full glob patterns also work
exclude = ["**/test_*.py", "**/conftest.py"]
```

### CLI and Config Pattern Merging

CLI `--include` and `--exclude` options are **combined** with config patterns (additive, not override):

```bash
# Config has: exclude = ["Testing"]
# This ADDS to config, excluding both Testing/ AND benchmark files
jedidb index --exclude "bench_"
```

**Resolution order:**
1. **Excludes are checked first** - if ANY exclude pattern matches, file is skipped
2. **Includes are OR** - file included if it matches ANY include pattern
3. If no includes specified, all non-excluded `.py` files are indexed

Default excludes (always applied): `__pycache__`, `.git`, `.venv`, `.tox`, `node_modules`, `build`, `dist`, etc.

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

**Full-text search** with BM25 ranking (searches names and docstrings):
```bash
jedidb search "parse json"      # finds parseJson, parse_json, JSONParser
```

**Wildcard search** with `*` (matches name only, not docstrings):
```bash
jedidb search "get*"            # prefix: getValue, get_config
jedidb search "*Engine"         # suffix: SearchEngine
jedidb search "get*path"        # pattern: get_source_path, get_index_path
jedidb search "*_cmd"           # underscore is literal, not wildcard
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
- watchfiles >= 0.20.0

## Credits

Built on [Jedi](https://github.com/davidhalter/jedi), the excellent Python static analysis library.

## License

Apache-2.0
