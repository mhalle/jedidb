# JediDB CLI Reference

Complete reference for all JediDB CLI commands.

## Global Options

```
jedidb [-C DIR] [--index DIR] COMMAND
```

| Option | Description |
|--------|-------------|
| `-C, --source DIR` | Source directory (default: current directory) |
| `--index DIR` | Index directory (default: `<source>/.jedidb`) |
| `--readme` | Print the README and exit |
| `--help` | Show help message |

## init

Initialize jedidb in a project.

```
jedidb init [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-i, --include PATTERN` | Patterns to include |
| `-e, --exclude PATTERN` | Patterns to exclude |

Creates `.jedidb/config.toml` with include/exclude patterns.

**Pattern Syntax:**

| Pattern | Expands To | Matches |
|---------|-----------|---------|
| `Testing` | `**/Testing/**` | Any file under `Testing/` directory |
| `test_` | `**/test_*.py` | Files starting with `test_` |
| `_test` | `**/*_test.py` | Files ending with `_test` |
| `src/` | `src/**` | Everything under `src/` |
| `**/test_*.py` | (used as-is) | Full glob pattern |

**Examples:**

```bash
jedidb init
jedidb init --exclude test_ --exclude _test
jedidb init --include src/ --exclude Testing
```

## index

Index Python files.

```
jedidb index [OPTIONS] [PATHS]...
```

| Option | Description |
|--------|-------------|
| `-i, --include PATTERN` | Additional include patterns |
| `-e, --exclude PATTERN` | Additional exclude patterns |
| `-f, --force` | Force re-index even if nothing changed |
| `-c, --check` | Check if stale without indexing (exit 0=ok, 1=stale) |
| `-v, --verbose` | Show changed files (with --check) |
| `-q, --quiet` | Suppress progress output |
| `-r, --resolve-refs` | Resolve reference targets (default, enables call graph) |
| `-R, --no-resolve-refs` | Skip reference resolution (~30% faster) |

Indexing uses all-or-nothing semantics: if any files changed, all files are re-indexed.

**Examples:**

```bash
jedidb index
jedidb index --force
jedidb index --check --verbose
jedidb index --exclude bench_ --exclude examples/
jedidb index --no-resolve-refs  # faster, but no call graph
```

## search

Full-text search definitions.

```
jedidb search [OPTIONS] QUERY
```

| Option | Description |
|--------|-------------|
| `-t, --type TYPE` | Filter by type: `function`, `class`, `variable`, `module`, `param` |
| `-n, --limit N` | Max results (default: 20) |
| `-p, --private` | Include private (`_`) definitions |
| `-f, --format FMT` | Output format: `table`, `json`, `jsonl`, `csv` |

**Search Types:**

- **Full-text**: `jedidb search "parse json"` - searches names and docstrings
- **Prefix**: `jedidb search "get*"` - matches names starting with "get"
- **Suffix**: `jedidb search "*Engine"` - matches names ending with "Engine"
- **Pattern**: `jedidb search "get*path"` - matches "get_source_path", etc.

**Examples:**

```bash
jedidb search parse
jedidb search "get*" --type function
jedidb search model --type class --limit 50
jedidb search _helper --private
jedidb search config --format jsonl
```

## show

Show details for a definition.

```
jedidb show [OPTIONS] NAME
```

| Option | Description |
|--------|-------------|
| `-f, --format FMT` | Output format: `table`, `json` |

Shows full_name, type, signature, docstring, file, and line number.

**Examples:**

```bash
jedidb show MyClass
jedidb show mymodule.parse_config
jedidb show Model --format json
```

## source

Display source code for definitions.

```
jedidb source [OPTIONS] [NAME]
```

| Option | Description |
|--------|-------------|
| `-i, --id N` | Look up definition by database ID |
| `-a, --all` | List all matches (including imports) |
| `-c, --context N` | Lines of context around code (default: 2) |
| `--calls` | Show call sites with source context |
| `-r, --refs` | Show references with source context |
| `-f, --format FMT` | Output format: `table`, `json`, `jsonl` |
| `-o, --output FILE` | Write output to file |

**Examples:**

```bash
jedidb source search_cmd
jedidb source MyClass --context 5
jedidb source --id 42
jedidb source SearchEngine --all
jedidb source Model.save --calls
jedidb source MyClass --refs
jedidb source parse --format json -o source.json
```

## calls

Show calls from a function in execution order.

```
jedidb calls [OPTIONS] NAME
```

| Option | Description |
|--------|-------------|
| `-d, --depth N` | Recurse into callees (1 = direct calls only, default: 1) |
| `-t, --top-level` | Hide nested calls (arguments in `foo(bar())`) |
| `--tree` | Show calls as indented tree |
| `-f, --format FMT` | Output format: `table`, `json`, `jsonl` |
| `-o, --output FILE` | Write output to file |

**Examples:**

```bash
jedidb calls Model.save
jedidb calls Model.save --depth 2
jedidb calls Model.save --top-level
jedidb calls __init__ --tree
jedidb calls parse --format json
```

## inheritance

Show class inheritance relationships.

```
jedidb inheritance [OPTIONS] NAME
```

| Option | Description |
|--------|-------------|
| `-c, --children` | Show classes that inherit from this class |
| `-t, --tree` | Show full inheritance tree |
| `-f, --format FMT` | Output format: `table`, `json`, `jsonl` |

**Examples:**

```bash
jedidb inheritance MyClass
jedidb inheritance MyClass --children
jedidb inheritance BaseModel --tree
jedidb inheritance Model --format json
```

## query

Run raw SQL queries on the index.

```
jedidb query [OPTIONS] SQL
```

| Option | Description |
|--------|-------------|
| `-f, --format FMT` | Output format: `table`, `json`, `jsonl`, `csv` |
| `-o, --output FILE` | Write output to file |

Uses DuckDB SQL dialect. See [SCHEMA.md](SCHEMA.md) for tables and [QUERIES.md](QUERIES.md) for examples.

**Examples:**

```bash
jedidb query "SELECT name, type FROM definitions WHERE type = 'class'"
jedidb query "SELECT * FROM calls WHERE callee_name = 'parse'"
jedidb query "SELECT COUNT(*) FROM definitions" --format json
jedidb query "SELECT * FROM functions LIMIT 100" -o functions.csv
```

## export

Export data to JSON or CSV.

```
jedidb export [OPTIONS] TABLE
```

| Option | Description |
|--------|-------------|
| `-f, --format FMT` | Output format: `json`, `jsonl`, `csv` |
| `-o, --output FILE` | Output file (required) |

Tables: `files`, `definitions`, `refs`, `imports`, `decorators`, `class_bases`, `calls`

**Examples:**

```bash
jedidb export definitions -o definitions.json
jedidb export calls -f csv -o calls.csv
```

## stats

Show database statistics.

```
jedidb stats [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `-f, --format FMT` | Output format: `table`, `json` |

Shows counts of files, definitions (by type), references, and imports.

**Examples:**

```bash
jedidb stats
jedidb stats --format json
```

## clean

Remove stale entries or reset database.

```
jedidb clean [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--reset` | Delete entire index and start fresh |
| `-f, --force` | Skip confirmation prompt |

**Examples:**

```bash
jedidb clean --reset
jedidb clean --reset --force
```

## Output Format Auto-Detection

Commands with `--format` option auto-detect the best format:

| Context | Default Format |
|---------|----------------|
| Interactive terminal | `table` (human-readable) |
| Piped/redirected | `jsonl` (full values, parseable) |

Override with `--format table`, `--format json`, or `--format jsonl`.
