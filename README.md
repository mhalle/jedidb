# JediDB

Python code index with Jedi analysis and full-text search. Stores data as compressed parquet files (~30-40x smaller than SQLite/DuckDB).

## Features

- **Code Analysis**: Extracts definitions, references, and imports using Jedi
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

# Search
jedidb search parse                    # full-text search
jedidb search "get*"                   # prefix search
jedidb search volume --type function   # filter by type
jedidb search test --format jsonl      # newline-delimited JSON output

# Explore
jedidb stats
jedidb show MyClass
jedidb query "SELECT name, type FROM definitions WHERE type = 'class'"
```

## CLI Reference

```
jedidb [--project DIR] COMMAND

Commands:
  init     Initialize jedidb in a project
  index    Index Python files (incremental by default)
  search   Full-text search definitions
  query    Run raw SQL queries
  show     Show details for a definition
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
  -f, --format  [table|json|jsonl]                       Output format
  -C, --project DIRECTORY                                Project directory
```

### index

```
jedidb index [OPTIONS] [PATHS]...

Options:
  -i, --include  PATTERN  Glob patterns to include (e.g., 'src/**/*.py')
  -e, --exclude  PATTERN  Glob patterns to exclude
  -f, --force             Force re-index all files
  -C, --project           Project directory
```

## Library Usage

```python
from jedidb import JediDB

db = JediDB(path="./myproject")

# Index
db.index(include=["src/**/*.py"], exclude=["**/test_*.py"])

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

# Raw SQL
rows = db.query("SELECT * FROM definitions WHERE type = 'class'")

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
  definitions.parquet   # functions, classes, variables
  files.parquet         # indexed files with hashes
  refs.parquet          # references/usages
  imports.parquet       # import statements
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
SELECT name, full_name, type, line, signature, docstring
FROM definitions WHERE type = 'function';

-- files: indexed files with modification tracking
SELECT path, hash, size, indexed_at FROM files;

-- refs: references to names
SELECT name, line, context FROM refs WHERE name = 'MyClass';

-- imports: import statements
SELECT module, name, alias FROM imports;
```

## Requirements

- Python 3.12+
- jedi >= 0.19.0
- duckdb >= 1.0.0
- typer >= 0.12.0
- rich >= 13.0.0

## License

MIT
