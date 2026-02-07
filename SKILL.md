---
name: jedidb-exploring
description: Explores Python codebases using JediDB semantic analysis. Indexes definitions, references, calls, inheritance, and decorators into a queryable DuckDB database. Use when analyzing Python projects, understanding code structure, finding callers/callees, tracing inheritance, or searching for definitions.
license: Apache-2.0
metadata:
  author: mhalle
  version: "0.4.2"
compatibility: Requires Python 3.12+, jedidb package. Works with Claude Code and similar agents.
---

# JediDB Exploring

JediDB is a Python CLI that indexes Python codebases using Jedi semantic analysis and stores results in queryable DuckDB/Parquet files.

## Installation

[Installation instructions to be added]

## Quick Start

```bash
# Initialize and index the current directory
jedidb init
jedidb index

# Search for code
jedidb search parse                    # full-text search
jedidb search "get*"                   # prefix wildcard
jedidb search volume --type function   # filter by type

# View source code
jedidb source MyClass                  # view class source
jedidb source parse_json --context 5   # with context lines

# Explore call graphs
jedidb calls MyClass.__init__          # what does this call?
jedidb calls parse --tree              # as indented tree

# Run SQL queries directly
jedidb query "SELECT name, type FROM definitions WHERE type = 'class'"
```

## When to Use This Skill

Use JediDB when you need to:

- **Search code**: Find functions, classes, or variables by name (supports wildcards and full-text search)
- **View source**: Display actual source code with line numbers
- **Navigate call graphs**: See what functions call what, in execution order
- **Find references**: Locate all usages of a function or class
- **Understand inheritance**: Trace class hierarchies up and down
- **Find decorated functions**: Query by decorator (`@property`, `@cached_property`, etc.)
- **Run custom SQL**: Query the indexed codebase with any SQL pattern

## Core Workflows

### 1. Searching for Code

```bash
# Full-text search (names and docstrings)
jedidb search "parse json"         # finds parseJson, parse_json, JSONParser

# Wildcard search (names only)
jedidb search "get*"               # prefix: getValue, get_config
jedidb search "*Engine"            # suffix: SearchEngine

# Filter by type
jedidb search model --type class
jedidb search test --type function

# Include private definitions
jedidb search _helper --private
```

### 2. Viewing Source Code

```bash
# View definition source
jedidb source MyClass              # full class body
jedidb source parse_config         # full function body

# Lookup by database ID (from query results)
jedidb source --id 42

# List all matches (imports + actual definition)
jedidb source SearchEngine --all

# Show call sites with source context
jedidb source Model.save --calls

# Show references with source context
jedidb source MyClass --refs
```

### 3. Exploring Call Graphs

```bash
# What does a function call?
jedidb calls Model.save              # direct calls
jedidb calls Model.save --depth 2    # include calls made by callees
jedidb calls Model.save --top-level  # hide nested calls (args in foo(bar()))
jedidb calls Model.save --tree       # show as indented tree

# Who calls a function? (use SQL)
jedidb query "SELECT caller_full_name, file_path FROM calls_with_context
              WHERE callee_full_name = 'mymodule.my_function'"
```

### 4. Understanding Inheritance

```bash
# What does a class inherit from?
jedidb inheritance MyClass

# What classes inherit from this one?
jedidb inheritance MyClass --children

# Full inheritance tree (ancestors and descendants)
jedidb inheritance MyClass --tree
```

### 5. Running SQL Queries

JediDB uses DuckDB (SQLite-compatible SQL). Run arbitrary queries:

```bash
# Find all async functions
jedidb query "SELECT name, file_path FROM functions WHERE name LIKE 'async_%'"

# Find decorated functions
jedidb query "SELECT full_name FROM decorated_definitions WHERE decorator_name = 'property'"

# Find largest functions
jedidb query "SELECT full_name, (end_line - line) as lines FROM definitions
              WHERE type = 'function' ORDER BY lines DESC LIMIT 10"

# Find unused definitions (dead code candidates)
jedidb query "SELECT d.full_name, d.type, f.path FROM definitions d
              JOIN files f ON d.file_id = f.id
              LEFT JOIN refs r ON r.target_full_name = d.full_name
              WHERE r.id IS NULL AND d.type IN ('function', 'class')"
```

See [references/QUERIES.md](references/QUERIES.md) for more query patterns.

## CLI Commands

| Command | Description |
|---------|-------------|
| `init` | Initialize jedidb in a project |
| `index` | Index Python files |
| `search` | Full-text search definitions |
| `show` | Show details for a definition |
| `source` | Display source code |
| `calls` | Show calls from a function |
| `inheritance` | Show class inheritance |
| `query` | Run raw SQL queries |
| `export` | Export to JSON/CSV |
| `stats` | Show database statistics |
| `clean` | Remove stale entries or reset |

See [references/CLI.md](references/CLI.md) for full command reference.

## Output Formats

Commands auto-detect the best format:
- **Interactive terminal**: `table` (human-readable)
- **Piped/redirected**: `jsonl` (full values, easy to parse)

Override with `--format table`, `--format json`, or `--format jsonl`.

## Filtering at Index-Time vs Query-Time

You can either:

1. **Index-time filtering**: Use `--exclude` patterns when indexing
   ```bash
   jedidb init --exclude test_ --exclude _test
   jedidb index
   ```

2. **Query-time filtering**: Index everything, filter with SQL
   ```sql
   SELECT * FROM definitions_with_path
   WHERE file_path NOT LIKE '%tests%'
   ```

Query-time filtering is often better because:
- DuckDB handles large indexes with no query slowdown (~30ms regardless of size)
- You retain flexibility to include tests when useful (e.g., finding API usage examples)

## Tips for Large Codebases

1. **Start with stats**: `jedidb stats` shows what's indexed
2. **Use wildcards**: `jedidb search "parse*"` is faster than full-text for known prefixes
3. **Leverage views**: Use convenience views like `functions`, `classes`, `calls_with_context`
4. **Filter by file path**: Add `WHERE file_path LIKE '%mymodule%'` to narrow results
5. **Use LIMIT**: Always add `LIMIT` for exploratory queries

## Database Schema

See [references/SCHEMA.md](references/SCHEMA.md) for:
- All 7 tables with column definitions
- All 8 convenience views
- Key joins explained

## References

- [SCHEMA.md](references/SCHEMA.md) - Database tables and views
- [QUERIES.md](references/QUERIES.md) - Example SQL patterns
- [CLI.md](references/CLI.md) - Full CLI command reference
