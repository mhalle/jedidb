# JediDB

Jedi code analyzer with DuckDB storage and full-text search.

## Features

- **Code Analysis**: Uses Jedi to analyze Python code, extracting definitions, references, and imports
- **DuckDB Storage**: Stores analysis results in DuckDB for fast querying
- **Full-Text Search**: Search across function names, class names, and docstrings
- **Incremental Updates**: Only re-indexes changed files
- **CLI & Library**: Use from command line or as a Python library

## Installation

```bash
pip install jedidb
```

Or with uv:

```bash
uv add jedidb
```

## Quick Start

### CLI Usage

```bash
# Initialize jedidb in your project
jedidb init

# Index Python files
jedidb index

# Search for definitions
jedidb search "parse"

# Show details for a specific definition
jedidb show MyClass

# View statistics
jedidb stats

# Run SQL queries
jedidb query "SELECT name, type FROM definitions WHERE type = 'class'"
```

### Library Usage

```python
from jedidb import JediDB

# Initialize
db = JediDB(path="./myproject")

# Index files
db.index(include=["src/**/*.py"], exclude=["**/test_*.py"])

# Search
results = db.search("parse", type="function", limit=10)
for result in results:
    print(f"{result.name} in {result.file_path}:{result.line}")

# Get definition details
defn = db.get_definition("mymodule.MyClass.method")
print(defn.docstring)

# Find references
refs = db.references("MyClass")

# Raw SQL queries
rows = db.query("SELECT name, type FROM definitions WHERE type = 'class'")
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `init` | Initialize jedidb in a project |
| `index` | Index Python files |
| `search` | Full-text search definitions |
| `query` | Run raw SQL queries |
| `show` | Show details for a definition |
| `export` | Export to JSON/CSV |
| `stats` | Show database statistics |
| `clean` | Remove stale entries or reset |

## Configuration

Create a `.jedidb.toml` file in your project root:

```toml
[jedidb]
# Database path (relative to project root or absolute)
db_path = ".jedidb/jedidb.duckdb"

# Glob patterns for files to include
include = ["src/**/*.py", "lib/**/*.py"]

# Glob patterns for files to exclude
exclude = ["**/test_*.py", "**/*_test.py"]
```

## Database Schema

JediDB stores data in four tables:

- **files**: Indexed files with modification tracking
- **definitions**: Functions, classes, variables, parameters
- **refs**: References to definitions
- **imports**: Import statements

## Requirements

- Python 3.12+
- jedi >= 0.19.0
- duckdb >= 1.0.0
- typer >= 0.12.0
- rich >= 13.0.0

## Development

```bash
# Clone repository
git clone https://github.com/yourusername/jedidb
cd jedidb

# Install with dev dependencies
uv sync --all-extras

# Run tests
uv run pytest

# Run linter
uv run ruff check src tests
```

## License

MIT
