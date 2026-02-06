# JediDB

An experimental Python code indexer with Jedi analysis and full-text search.



JediDB is an experiment built to help **LLMs explore
Python code**. One of the best uses for LLMs is to help explain
unfamiliar code bases. However, that can be a challenge for them. By
looking only through files of code, they can forget things. They can
lose track of things. They have trouble handling long files and
abstractions that span multiple files - just like people, in fact.

JediDB is a Python CLI that crawls a local python code base (for
instance, a git checkout --depth 1), builds an analysis database, and
provides command line tools to query and search it. 

## Background

I looked around for tools that could help with the "help LLMs explore
code" problem.  Surprisingly, I couldn't find too many, at least
modern ones. There are many Python code analysis packages out there,
but most involve LSP / language server-like interactive analysis on
dynamically changing code for tasks like autocompletion.

In fact, when I let David Halter, the creator of
[Jedi](https://github.com/davidhalter/jedi) ("an awesome
autocompletion, static analysis and refactoring library for Python"),
know about my project, he said, "I think this is fundamentally the
wrong direction and why I wrote Zuban in the first place." Fair
enough. However, I'm interested in giving LLMs the ability to explore
static code bases. I don't really care about interactivity. There's
plenty of hard to understand code at rest.

And, frankly, I don't care that much about types or typechecking. I
love types, but that's not what I'm most interested in, especially for
stable code that works. I care more about program and code
structure. What calls what, what inherits from what, where's that darn
function, etc.

But even that information can become overwhelming for a person,
especially if they have to write queries to find it. That's where LLMs
come in. I want to let LLMs explore code doing what they do really
well now: running scripts and writing complex queries and extracting
information to build their own mental model of code, then explaining
it to me.

JediDB is a Python CLI for LLMs to explore code without blowing out their
context window with raw Python.

Like I said, I used Jedi because it gave me library-level access to
code parsing. If there are other libraries that can do the same,
please let me know.

## Why JediDB?

Unlike RAG embedding-based or pure text-based tools, JediDB uses
[Jedi](https://github.com/davidhalter/jedi) for Python semantic
analysis - the same engine that powers IDE autocompletion. The results
are stored in highly compressed Parquet files (less then 2MB for
Django) and searched/queried with DuckDB, including full text search.

| Feature | JediDB | Embedding tools | Call graph tools |
|---------|--------|-----------------|------------------|
| Semantic Python analysis | Yes (Jedi) | Approximations | AST only |
| Full-text + wildcard search | Yes | Vector similarity | No |
| Source display with context | Yes | No | No |
| Call graphs in execution order | Yes | No | Unordered |
| SQL queries on index | Yes | No | No |
| Structured JSON output | Auto-detected | Varies | No |
| No external services | Yes | Often needs Ollama/API | Yes |

**One tool** for search, source viewing, call navigation, and custom
  SQL queries - all with CLI-friendly table or JSON output.

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

- **Jedi-Powered Analysis**: Python semantic analysis - definitions, references, imports, decorators, inheritance
- **Call Graphs**: Caller/callee relationships with execution order tracking
- **Source Display**: View actual source code with line numbers and configurable context
- **Full-Text Search**: BM25 ranking with CamelCase/snake_case tokenization
- **Wildcard Search**: Prefix (`get*`), suffix (`*Engine`), and pattern (`get*path`) matching
- **Smart Re-indexing**: Skips if nothing changed, full re-index if anything changed
- **SQL Interface**: Query the index directly with DuckDB SQL
- **LLM-Friendly Output**: Auto-detects terminal vs pipe, outputs JSON/JSONL for tooling
- **Lightweight Storage**: Parquet files with zstd compression (~1.5MB for 24K definitions in the Django code base)
- **Zero Cloud Dependencies**: No cloud services, no Ollama, no API keys

## Installation

Run directly with uvx (no install needed):

```bash
uvx git+https://github.com/mhalle/jedidb jedidb --help
```

Install as a tool with uv:

```bash
uv tool install git+https://github.com/mhalle/jedidb
jedidb --help
```

Or with pip:

```bash
pip install jedidb
```

## Quick Start

```bash
# Initialize and index
jedidb init
jedidb index

# Or initialize with exclude patterns (e.g., skip test files)
jedidb init --exclude test_ --exclude _test

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
  index    Index Python files (full re-index if anything changed)
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
  -f, --force                        Force re-index even if nothing changed
  -c, --check                        Check if stale without indexing (exit 0=ok, 1=stale)
  -v, --verbose                      Show changed files (with --check)
  -q, --quiet                        Suppress progress output
  -r, --resolve-refs (default)       Resolve reference targets (enables call graph)
  -R, --no-resolve-refs              Skip reference resolution (faster indexing)
  -C, --project                      Project directory
```

Indexing uses all-or-nothing semantics: if any files have changed, all files are re-indexed to ensure cross-file references are consistent. If nothing has changed, indexing is skipped entirely. Use `--check` to see what changed without indexing.

Patterns use simplified syntax: `Testing` matches directories, `test_` matches file prefixes, `_test` matches suffixes. Full globs like `**/test_*.py` also work. See [Include/Exclude Patterns](#includeexclude-patterns) for details.

Reference resolution is enabled by default, building the call graph. Use `--no-resolve-refs` / `-R` for faster indexing if you don't need caller/callee queries (~30% faster).

### calls

```
jedidb calls [OPTIONS] NAME

Arguments:
  NAME  Name or full name of the function to show calls for

Options:
  -d, --depth INTEGER             Recurse into callees (1 = direct calls only) [default: 1]
  -t, --top-level                 Hide nested calls like args in foo(bar())
  --tree                          Show calls as a tree
  -f, --format [table|json|jsonl] Output format (auto-detected)
```

Show what a function calls in execution order:

```bash
jedidb calls Model.save              # Direct calls from Model.save
jedidb calls Model.save --depth 2    # Also show what those callees call
jedidb calls Model.save --top-level  # Hide nested calls (e.g., args in foo(bar()))
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

# Initialize with source directory and index location
# source: where your Python code lives
# index: where JediDB stores its data (typically .jedidb in project root)
db = JediDB(source="./myproject", index="./myproject/.jedidb")

# Index (includes call graph by default)
db.index_files(include=["src/**/*.py"], exclude=["**/test_*.py"])

# Index without reference resolution (faster, no call graph)
db = JediDB(source="./myproject", index="./myproject/.jedidb", resolve_refs=False)
db.index_files()

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

Data is stored as compressed parquet files in `.jedidb/db/`:

```
.jedidb/
  config.toml           # include/exclude patterns
  db/
    definitions.parquet   # functions, classes, variables (with end positions, parent info)
    files.parquet         # indexed files with hashes
    refs.parquet          # references/usages (with resolved targets by default)
    imports.parquet       # import statements
    decorators.parquet    # decorators on functions/classes
    class_bases.parquet   # class inheritance (base classes)
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

The index uses DuckDB (SQLite-compatible SQL). Here are the table schemas:

```sql
-- files: indexed source files
files (
    id, path, hash, size, modified_at, indexed_at
)

-- definitions: functions, classes, variables, params, modules
definitions (
    id, file_id, name, full_name,
    type,           -- 'function', 'class', 'variable', 'param', 'module'
    line, col, end_line, end_col,
    signature,      -- function/method signature
    docstring,
    parent_id, parent_full_name,  -- for nested definitions
    is_public       -- FALSE if name starts with _
)

-- refs: references/usages of names
refs (
    id, file_id, definition_id, name,
    line, col, context,           -- source line containing the reference
    target_full_name,             -- resolved target (if --resolve-refs)
    target_module_path,
    is_call,                      -- TRUE if this is a function call
    call_order, call_depth        -- execution order within caller
)

-- imports: import statements
imports (
    id, file_id, module, name, alias, line
)

-- decorators: @decorator on functions/classes
decorators (
    id, definition_id, name, full_name, arguments, line
)

-- class_bases: inheritance relationships
class_bases (
    id, class_id, base_name, base_full_name, base_id, position
)

-- calls: call graph (caller -> callee)
calls (
    id, file_id,
    caller_full_name, caller_id,
    callee_full_name, callee_name, callee_id,
    line, col, context,
    call_order, call_depth        -- execution order within caller
)
```

**Key joins:** `definitions.file_id → files.id`, `calls.caller_id → definitions.id`, `decorators.definition_id → definitions.id`, `class_bases.class_id → definitions.id`

### Convenience Views

JediDB creates these views at runtime (via `init.sql` when DuckDB loads the parquet files) to simplify common queries:

| View | Description |
|------|-------------|
| `functions` | All function/method definitions with `file_path` |
| `classes` | All class definitions with `file_path` |
| `definitions_with_path` | All definitions joined with their file path |
| `refs_with_path` | All references joined with their file path |
| `imports_with_path` | All imports joined with their file path |
| `calls_with_context` | Calls with file paths for caller and callee |
| `class_hierarchy` | Classes with their base classes (one row per base) |
| `decorated_definitions` | Definitions with decorators (one row per decorator) |

**Examples using views:**
```sql
-- Find all async functions
SELECT name, file_path FROM functions WHERE name LIKE 'async_%';

-- Find all classes inheriting from Model
SELECT class_full_name, file_path FROM class_hierarchy
WHERE base_full_name LIKE '%Model';

-- Find all @pytest.fixture functions
SELECT full_name, file_path FROM decorated_definitions
WHERE decorator_name = 'fixture';

-- What calls are made from test files?
SELECT caller_full_name, callee_full_name FROM calls_with_context
WHERE file_path LIKE '%test_%';
```

## What You Can Discover

JediDB's SQL interface lets you answer questions about your codebase that would be tedious to figure out manually. Here are some examples:

**Finding code patterns:**
- All classes that inherit from a specific base class
- Functions decorated with `@property`, `@staticmethod`, `@cached_property`, etc.
- All usages of a deprecated function
- Where a class is instantiated throughout the codebase
- Private methods (`_name`) vs public methods in a class
- Module-level functions (not inside classes)

**Understanding structure:**
- The largest functions by line count
- Classes with the most methods
- Files with the most definitions
- The full class hierarchy for a module
- Nested classes and inner functions

**Dependency analysis:**
- What functions does `MyClass.__init__` call, in execution order?
- Who calls a specific function? (reverse call graph)
- What external modules does a file import?
- Functions that are defined but never called (dead code candidates)
- The most-referenced functions in the codebase

**Code quality insights:**
- Functions without docstrings
- Very long functions (potential refactoring targets)
- Deeply nested call chains
- Classes that might be doing too much

**Navigation:**
- Jump from a function name to its full source code
- See call sites with surrounding context
- Follow call chains: A calls B calls C

**Filtering at query time vs index time:**

The `--include` and `--exclude` options control what gets indexed. But you can also index everything and filter later with SQL. This is useful when you want to:
- Normally ignore test files, but occasionally explore them
- Find pytest tests by looking for classes inheriting from `unittest.TestCase`
- Compare production code vs test code patterns
- Search test files for usage examples of your APIs

```sql
-- Find functions only in test files
SELECT name, full_name FROM definitions d
JOIN files f ON d.file_id = f.id
WHERE f.path LIKE '%test_%' AND d.type = 'function';

-- Find non-test code that calls a specific function
SELECT c.caller_full_name, f.path FROM calls c
JOIN files f ON c.file_id = f.id
WHERE c.callee_full_name = 'mymodule.my_function'
  AND f.path NOT LIKE '%test_%';
```

Most of these are one-liners with `jedidb query`, and the SQL is simple enough that LLMs can easily write these queries for you—just describe what you're looking for. A few more examples:

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

-- Classes that inherit from a specific base
SELECT d.full_name FROM definitions d
JOIN class_bases cb ON cb.class_id = d.id
WHERE cb.base_full_name = 'django.db.models.Model';

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

## Caveats

### Jedi Internal API Usage

Two features use Jedi's internal APIs (`_name.tree_name`) which may change between Jedi versions:

| Feature | Fallback if API changes |
|---------|------------------------|
| Decorator extraction | Returns empty list (decorators won't be indexed) |
| Base class extraction | Returns empty list (inheritance won't be tracked) |

These accesses are guarded with try/except, so JediDB will continue to work if Jedi's internals change - you'll just lose decorator and inheritance data. Core functionality (definitions, references, imports, call graphs, search) uses only Jedi's public API.

If you encounter issues after a Jedi upgrade, please [report them](https://github.com/mhalle/jedidb/issues).

## Credits

Built on [Jedi](https://github.com/davidhalter/jedi), the excellent Python static analysis library.

## License

Apache-2.0
