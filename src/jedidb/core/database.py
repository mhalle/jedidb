"""DuckDB database management for JediDB."""

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb

from jedidb.core.models import ClassBase, Decorator, Definition, FileRecord, Import, Reference


SCHEMA_SQL = """
-- Indexed files with modification tracking
CREATE SEQUENCE IF NOT EXISTS files_id_seq;
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY DEFAULT nextval('files_id_seq'),
    path TEXT UNIQUE NOT NULL,
    hash TEXT NOT NULL,
    size INTEGER,
    modified_at TIMESTAMP,
    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Definitions (functions, classes, variables, parameters)
CREATE SEQUENCE IF NOT EXISTS definitions_id_seq;
CREATE TABLE IF NOT EXISTS definitions (
    id INTEGER PRIMARY KEY DEFAULT nextval('definitions_id_seq'),
    file_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    full_name TEXT,
    type TEXT NOT NULL,
    line INTEGER NOT NULL,
    col INTEGER NOT NULL,
    end_line INTEGER,
    end_col INTEGER,
    signature TEXT,
    docstring TEXT,
    parent_id INTEGER,
    parent_full_name TEXT,
    is_public BOOLEAN DEFAULT TRUE,
    search_text TEXT
);

-- References (usages of definitions)
CREATE SEQUENCE IF NOT EXISTS refs_id_seq;
CREATE TABLE IF NOT EXISTS refs (
    id INTEGER PRIMARY KEY DEFAULT nextval('refs_id_seq'),
    file_id INTEGER NOT NULL,
    definition_id INTEGER,
    name TEXT NOT NULL,
    line INTEGER NOT NULL,
    col INTEGER NOT NULL,
    context TEXT,
    target_full_name TEXT,
    target_module_path TEXT,
    is_call BOOLEAN DEFAULT FALSE,
    call_order INTEGER DEFAULT 0,
    call_depth INTEGER DEFAULT 0
);

-- Imports
CREATE SEQUENCE IF NOT EXISTS imports_id_seq;
CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY DEFAULT nextval('imports_id_seq'),
    file_id INTEGER NOT NULL,
    module TEXT NOT NULL,
    name TEXT,
    alias TEXT,
    line INTEGER NOT NULL
);

-- Decorators on functions/classes
CREATE SEQUENCE IF NOT EXISTS decorators_id_seq;
CREATE TABLE IF NOT EXISTS decorators (
    id INTEGER PRIMARY KEY DEFAULT nextval('decorators_id_seq'),
    definition_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    full_name TEXT,
    arguments TEXT,
    line INTEGER NOT NULL
);

-- Class base classes (inheritance)
CREATE SEQUENCE IF NOT EXISTS class_bases_id_seq;
CREATE TABLE IF NOT EXISTS class_bases (
    id INTEGER PRIMARY KEY DEFAULT nextval('class_bases_id_seq'),
    class_id INTEGER NOT NULL,
    base_name TEXT NOT NULL,
    base_full_name TEXT,
    base_id INTEGER,
    position INTEGER NOT NULL
);

-- Call graph (built from resolved references)
CREATE SEQUENCE IF NOT EXISTS calls_id_seq;
CREATE TABLE IF NOT EXISTS calls (
    id INTEGER PRIMARY KEY DEFAULT nextval('calls_id_seq'),
    caller_full_name TEXT NOT NULL,
    callee_full_name TEXT,
    callee_name TEXT NOT NULL,
    caller_id INTEGER,
    callee_id INTEGER,
    file_id INTEGER NOT NULL,
    line INTEGER NOT NULL,
    col INTEGER NOT NULL,
    context TEXT,
    call_order INTEGER DEFAULT 0,
    call_depth INTEGER DEFAULT 0
);

-- Create indexes for faster lookups
CREATE INDEX IF NOT EXISTS idx_definitions_name ON definitions(name);
CREATE INDEX IF NOT EXISTS idx_definitions_full_name ON definitions(full_name);
CREATE INDEX IF NOT EXISTS idx_definitions_type ON definitions(type);
CREATE INDEX IF NOT EXISTS idx_definitions_file_id ON definitions(file_id);
CREATE INDEX IF NOT EXISTS idx_definitions_parent_full_name ON definitions(parent_full_name);
CREATE INDEX IF NOT EXISTS idx_refs_name ON refs(name);
CREATE INDEX IF NOT EXISTS idx_refs_file_id ON refs(file_id);
CREATE INDEX IF NOT EXISTS idx_refs_target_full_name ON refs(target_full_name);
CREATE INDEX IF NOT EXISTS idx_refs_is_call ON refs(is_call);
CREATE INDEX IF NOT EXISTS idx_imports_module ON imports(module);
CREATE INDEX IF NOT EXISTS idx_imports_file_id ON imports(file_id);
CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);
CREATE INDEX IF NOT EXISTS idx_decorators_definition_id ON decorators(definition_id);
CREATE INDEX IF NOT EXISTS idx_decorators_name ON decorators(name);
CREATE INDEX IF NOT EXISTS idx_class_bases_class ON class_bases(class_id);
CREATE INDEX IF NOT EXISTS idx_class_bases_base ON class_bases(base_full_name);
CREATE INDEX IF NOT EXISTS idx_calls_caller ON calls(caller_full_name);
CREATE INDEX IF NOT EXISTS idx_calls_callee ON calls(callee_full_name);
CREATE INDEX IF NOT EXISTS idx_calls_callee_name ON calls(callee_name);
CREATE INDEX IF NOT EXISTS idx_calls_caller_order ON calls(caller_full_name, call_order);
"""

FTS_SETUP_SQL = """
-- Install and load FTS extension
INSTALL fts;
LOAD fts;
"""


class Database:
    """DuckDB database connection and operations."""

    def __init__(self, db_path: Path | str):
        """Initialize database connection.

        Args:
            db_path: Path to the DuckDB database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._fts_initialized = False

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        """Get or create database connection."""
        if self._conn is None:
            self._conn = duckdb.connect(str(self.db_path))
            self._init_schema()
        return self._conn

    def _init_schema(self):
        """Initialize database schema."""
        self.conn.execute(SCHEMA_SQL)

    def _init_fts(self):
        """Initialize full-text search extension."""
        if self._fts_initialized:
            return

        try:
            self.conn.execute(FTS_SETUP_SQL)
            self._fts_initialized = True
        except Exception:
            # FTS extension might already be loaded
            self._fts_initialized = True

    def create_fts_index(self):
        """Create or recreate the FTS index on definitions.search_text."""
        self._init_fts()

        # Drop existing FTS index if it exists
        try:
            self.conn.execute("PRAGMA drop_fts_index('definitions')")
        except Exception:
            pass  # Index might not exist

        # Create new FTS index on search_text (contains original + split tokens + docstring)
        # No stemming or stopwords to preserve code identifiers exactly
        self.conn.execute(
            "PRAGMA create_fts_index('definitions', 'id', 'search_text', stemmer='none', stopwords='none', overwrite=1)"
        )

    def execute(self, sql: str, params: tuple | list | None = None) -> duckdb.DuckDBPyRelation:
        """Execute a SQL query.

        Args:
            sql: SQL query string
            params: Optional query parameters

        Returns:
            Query result relation
        """
        if params:
            return self.conn.execute(sql, params)
        return self.conn.execute(sql)

    @contextmanager
    def transaction(self):
        """Context manager for database transactions."""
        self.conn.execute("BEGIN TRANSACTION")
        try:
            yield
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise

    # File operations

    def get_file(self, path: str) -> FileRecord | None:
        """Get a file record by path."""
        result = self.execute(
            "SELECT id, path, hash, size, modified_at, indexed_at FROM files WHERE path = ?",
            (path,)
        ).fetchone()

        if result:
            return FileRecord(
                id=result[0],
                path=result[1],
                hash=result[2],
                size=result[3],
                modified_at=result[4],
                indexed_at=result[5],
            )
        return None

    def insert_file(self, file_record: FileRecord) -> int:
        """Insert a file record and return its ID."""
        result = self.execute(
            """
            INSERT INTO files (path, hash, size, modified_at, indexed_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            RETURNING id
            """,
            (file_record.path, file_record.hash, file_record.size, file_record.modified_at)
        ).fetchone()
        return result[0]

    def update_file(self, file_record: FileRecord):
        """Update a file record."""
        self.execute(
            """
            UPDATE files
            SET hash = ?, size = ?, modified_at = ?, indexed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (file_record.hash, file_record.size, file_record.modified_at, file_record.id)
        )

    def delete_file(self, file_id: int):
        """Delete a file and all related records."""
        # Delete related records first (manual cascade)
        self.delete_decorators_by_file(file_id)
        self.delete_class_bases_by_file(file_id)
        self.execute("DELETE FROM calls WHERE file_id = ?", (file_id,))
        self.execute("DELETE FROM refs WHERE file_id = ?", (file_id,))
        self.execute("DELETE FROM imports WHERE file_id = ?", (file_id,))
        self.execute("DELETE FROM definitions WHERE file_id = ?", (file_id,))
        self.execute("DELETE FROM files WHERE id = ?", (file_id,))

    def delete_file_by_path(self, path: str):
        """Delete a file by path."""
        # Get file id first
        result = self.execute("SELECT id FROM files WHERE path = ?", (path,)).fetchone()
        if result:
            self.delete_file(result[0])

    # Definition operations

    def insert_definition(self, definition: Definition) -> int:
        """Insert a definition and return its ID."""
        self.insert_definitions_batch([definition])
        result = self.execute(
            "SELECT id FROM definitions WHERE file_id = ? AND name = ? AND line = ? ORDER BY id DESC LIMIT 1",
            (definition.file_id, definition.name, definition.line)
        ).fetchone()
        return result[0]

    def insert_definitions_batch(self, definitions: list[Definition]):
        """Insert multiple definitions in a batch."""
        if not definitions:
            return

        data = [
            (
                d.file_id, d.name, d.full_name, d.type, d.line, d.column,
                d.end_line, d.end_column, d.signature, d.docstring,
                d.parent_id, d.parent_full_name, d.is_public, d.search_text
            )
            for d in definitions
        ]

        self.conn.executemany(
            """
            INSERT INTO definitions
            (file_id, name, full_name, type, line, col, end_line, end_col,
             signature, docstring, parent_id, parent_full_name, is_public, search_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            data
        )

    def get_definitions_by_file(self, file_id: int) -> list[Definition]:
        """Get all definitions in a file."""
        results = self.execute(
            """
            SELECT id, file_id, name, full_name, type, line, col,
                   end_line, end_col, signature, docstring, parent_id, is_public
            FROM definitions WHERE file_id = ?
            """,
            (file_id,)
        ).fetchall()

        return [
            Definition(
                id=r[0], file_id=r[1], name=r[2], full_name=r[3], type=r[4],
                line=r[5], column=r[6], end_line=r[7], end_column=r[8],
                signature=r[9], docstring=r[10], parent_id=r[11], is_public=r[12]
            )
            for r in results
        ]

    # Reference operations

    def insert_reference(self, reference: Reference) -> int:
        """Insert a reference and return its ID."""
        self.insert_references_batch([reference])
        result = self.execute(
            "SELECT id FROM refs WHERE file_id = ? AND name = ? AND line = ? ORDER BY id DESC LIMIT 1",
            (reference.file_id, reference.name, reference.line)
        ).fetchone()
        return result[0]

    def insert_references_batch(self, references: list[Reference]):
        """Insert multiple references in a batch."""
        if not references:
            return

        data = [
            (r.file_id, r.definition_id, r.name, r.line, r.column, r.context,
             r.target_full_name, r.target_module_path, r.is_call, r.call_order, r.call_depth)
            for r in references
        ]

        self.conn.executemany(
            """
            INSERT INTO refs (file_id, definition_id, name, line, col, context,
                              target_full_name, target_module_path, is_call, call_order, call_depth)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            data
        )

    # Import operations

    def insert_import(self, imp: Import) -> int:
        """Insert an import and return its ID."""
        result = self.execute(
            """
            INSERT INTO imports (file_id, module, name, alias, line)
            VALUES (?, ?, ?, ?, ?)
            RETURNING id
            """,
            (imp.file_id, imp.module, imp.name, imp.alias, imp.line)
        ).fetchone()
        return result[0]

    def insert_imports_batch(self, imports: list[Import]):
        """Insert multiple imports in a batch."""
        if not imports:
            return

        data = [(i.file_id, i.module, i.name, i.alias, i.line) for i in imports]

        self.conn.executemany(
            """
            INSERT INTO imports (file_id, module, name, alias, line)
            VALUES (?, ?, ?, ?, ?)
            """,
            data
        )

    # Stats and queries

    def get_stats(self) -> dict[str, Any]:
        """Get database statistics."""
        stats = {}

        # File count
        result = self.execute("SELECT COUNT(*) FROM files").fetchone()
        stats["total_files"] = result[0]

        # Definition count
        result = self.execute("SELECT COUNT(*) FROM definitions").fetchone()
        stats["total_definitions"] = result[0]

        # Reference count
        result = self.execute("SELECT COUNT(*) FROM refs").fetchone()
        stats["total_references"] = result[0]

        # Import count
        result = self.execute("SELECT COUNT(*) FROM imports").fetchone()
        stats["total_imports"] = result[0]

        # Definitions by type
        results = self.execute(
            "SELECT type, COUNT(*) FROM definitions GROUP BY type ORDER BY COUNT(*) DESC"
        ).fetchall()
        stats["definitions_by_type"] = {r[0]: r[1] for r in results}

        # Last indexed
        result = self.execute(
            "SELECT MAX(indexed_at) FROM files"
        ).fetchone()
        stats["last_indexed"] = result[0]

        return stats

    def close(self):
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # Decorator operations

    def insert_decorators_batch(self, decorators: list[Decorator]):
        """Insert multiple decorators in a batch."""
        if not decorators:
            return

        data = [
            (d.definition_id, d.name, d.full_name, d.arguments, d.line)
            for d in decorators
        ]

        self.conn.executemany(
            """
            INSERT INTO decorators (definition_id, name, full_name, arguments, line)
            VALUES (?, ?, ?, ?, ?)
            """,
            data
        )

    def delete_decorators_by_file(self, file_id: int):
        """Delete decorators for definitions in a file."""
        self.execute(
            """
            DELETE FROM decorators WHERE definition_id IN (
                SELECT id FROM definitions WHERE file_id = ?
            )
            """,
            (file_id,)
        )

    # Class bases (inheritance) operations

    def insert_class_bases_batch(self, class_bases: list[ClassBase]):
        """Insert multiple class bases in a batch."""
        if not class_bases:
            return

        data = [
            (cb.class_id, cb.base_name, cb.base_full_name, cb.base_id, cb.position)
            for cb in class_bases
        ]

        self.conn.executemany(
            """
            INSERT INTO class_bases (class_id, base_name, base_full_name, base_id, position)
            VALUES (?, ?, ?, ?, ?)
            """,
            data
        )

    def delete_class_bases_by_file(self, file_id: int):
        """Delete class bases for classes in a file."""
        self.execute(
            """
            DELETE FROM class_bases WHERE class_id IN (
                SELECT id FROM definitions WHERE file_id = ? AND type = 'class'
            )
            """,
            (file_id,)
        )

    # Post-processing methods

    def populate_parent_ids(self):
        """Populate parent_id from parent_full_name."""
        self.execute("""
            UPDATE definitions d SET parent_id = (
                SELECT p.id FROM definitions p
                WHERE p.full_name = d.parent_full_name AND p.file_id = d.file_id
                LIMIT 1
            ) WHERE d.parent_full_name IS NOT NULL
        """)

    def build_call_graph(self):
        """Build call graph from all call references (resolved and unresolved)."""
        self.execute("DELETE FROM calls")
        # Use window function to pick only the innermost enclosing definition
        # (smallest line range = most specific caller)
        self.execute("""
            INSERT INTO calls (caller_full_name, callee_full_name, callee_name, caller_id, callee_id, file_id, line, col, context, call_order, call_depth)
            SELECT
                caller_full_name, target_full_name, name, caller_id, callee_id,
                file_id, line, col, context, call_order, call_depth
            FROM (
                SELECT
                    d.full_name AS caller_full_name,
                    r.target_full_name,
                    r.name,
                    d.id AS caller_id,
                    callee.id AS callee_id,
                    r.file_id,
                    r.line,
                    r.col,
                    r.context,
                    r.call_order,
                    r.call_depth,
                    ROW_NUMBER() OVER (
                        PARTITION BY r.id
                        ORDER BY COALESCE(d.end_line, 999999) - d.line ASC
                    ) AS rn
                FROM refs r
                JOIN definitions d ON r.file_id = d.file_id
                    AND r.line BETWEEN d.line AND COALESCE(d.end_line, 999999)
                    AND d.type IN ('function', 'class')
                LEFT JOIN definitions callee ON callee.full_name = r.target_full_name
                WHERE r.is_call = TRUE
            ) ranked
            WHERE rn = 1
        """)

    # Parquet storage methods

    def export_to_parquet(self, output_dir: Path, compression_level: int = 19):
        """Export all tables to parquet files with zstd compression.

        Args:
            output_dir: Directory to write parquet files
            compression_level: Zstd compression level (1-22, default 19)
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        tables = ["files", "definitions", "refs", "imports", "decorators", "class_bases", "calls"]
        for table in tables:
            self.execute(f"""
                COPY {table} TO '{output_dir / f"{table}.parquet"}'
                (FORMAT PARQUET, COMPRESSION ZSTD, COMPRESSION_LEVEL {compression_level})
            """)

    @classmethod
    def open_parquet(cls, parquet_dir: Path) -> "Database":
        """Open a parquet-backed database (in-memory with tables from parquet files).

        Args:
            parquet_dir: Directory containing parquet files

        Returns:
            Database instance with tables loaded from parquet files
        """
        import re
        from importlib.resources import files

        parquet_dir = Path(parquet_dir).resolve()

        # Create in-memory database
        db = cls.__new__(cls)
        db.db_path = parquet_dir / "jedidb.duckdb"  # For reference only
        db._conn = duckdb.connect(":memory:")
        db._fts_initialized = False

        # Set the parquet directory variable
        db._conn.execute(f"SET variable parquet_dir = '{parquet_dir}'")

        # Load init.sql from package
        init_sql = files("jedidb").joinpath("init.sql").read_text()

        # DuckDB execute() only runs one statement at a time
        # Remove comments and split on semicolons
        sql_no_comments = re.sub(r"--.*$", "", init_sql, flags=re.MULTILINE)
        statements = [s.strip() for s in sql_no_comments.split(";") if s.strip()]

        for stmt in statements:
            db._conn.execute(stmt)

        # Handle class_bases table (may not exist in older indexes)
        class_bases_parquet = parquet_dir / "class_bases.parquet"
        if class_bases_parquet.exists():
            db._conn.execute(f"CREATE OR REPLACE TABLE class_bases AS SELECT * FROM read_parquet('{class_bases_parquet}')")
        else:
            # Create empty table for older indexes
            db._conn.execute("""
                CREATE TABLE class_bases (
                    id INTEGER PRIMARY KEY,
                    class_id INTEGER NOT NULL,
                    base_name TEXT NOT NULL,
                    base_full_name TEXT,
                    base_id INTEGER,
                    position INTEGER NOT NULL
                )
            """)

        # Create sequences for incremental inserts (must be done after loading data)
        for table in ["files", "definitions", "refs", "imports", "decorators", "class_bases", "calls"]:
            max_id = db._conn.execute(f"SELECT COALESCE(MAX(id), 0) FROM {table}").fetchone()[0]
            db._conn.execute(f"CREATE SEQUENCE {table}_id_seq START WITH {max_id + 1}")
            db._conn.execute(f"ALTER TABLE {table} ALTER COLUMN id SET DEFAULT nextval('{table}_id_seq')")

        # Create index for call ordering queries (after ALTER statements to avoid dependency issues)
        db._conn.execute("CREATE INDEX IF NOT EXISTS idx_calls_caller_order ON calls(caller_full_name, call_order)")

        db._fts_initialized = True
        return db
