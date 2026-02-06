"""JediDB - Jedi code analyzer with DuckDB storage and full-text search."""

__version__ = "0.3.10"

import logging
from pathlib import Path

# Configure library logger - users can adjust level via logging.getLogger("jedidb")
logger = logging.getLogger("jedidb")
logger.addHandler(logging.NullHandler())

from jedidb.core.database import Database
from jedidb.core.indexer import Indexer
from jedidb.core.search import SearchEngine
from jedidb.core.analyzer import Analyzer
from jedidb.core.models import (
    FileRecord,
    Definition,
    Reference,
    Import,
    Decorator,
    ClassBase,
    SearchResult,
)
from jedidb.config import Config


class JediDB:
    """Main interface for the JediDB code analyzer."""

    def __init__(self, source: Path | str, index: Path | str, resolve_refs: bool = True, base_classes: bool = True):
        """Initialize JediDB for a project.

        Args:
            source: Source code directory
            index: Index directory (where jedidb data lives)
            resolve_refs: Whether to resolve reference targets (enables call graph)
            base_classes: Whether to track class inheritance (base classes)
        """
        self.source = Path(source).resolve()
        self.index = Path(index).resolve()
        self.db_dir = self.index / "db"
        self._resolve_refs = resolve_refs
        self._base_classes = base_classes

        self.config = Config.load(self.index)

        # Prefer parquet if available, otherwise create in-memory DuckDB
        if (self.db_dir / "definitions.parquet").exists():
            self.db = Database.open_parquet(self.db_dir)
        else:
            self.db_dir.mkdir(parents=True, exist_ok=True)
            self.db = Database(":memory:")

        self.analyzer = Analyzer(self.source, base_classes=base_classes)
        self.indexer = Indexer(self.db, self.analyzer, resolve_refs=resolve_refs)
        self.search_engine = SearchEngine(self.db)

    def index_files(
        self,
        paths: list[str] | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        force: bool = False,
    ) -> dict:
        """Index Python files in the project.

        Args:
            paths: Specific paths to index. If None, indexes source root.
            include: Glob patterns to include (e.g., ["src/**/*.py"])
            exclude: Glob patterns to exclude (e.g., ["**/test_*.py"])
            force: Force re-indexing even if files haven't changed

        Returns:
            Dictionary with indexing statistics
        """
        stats = self.indexer.index(
            paths=paths,
            include=include,
            exclude=exclude,
            force=force,
        )

        # Always export to parquet (this is now the primary storage format)
        if stats["files_indexed"] > 0 or stats["files_removed"] > 0:
            self.db.export_to_parquet(self.db_dir)
            stats["packed"] = True
            stats["parquet_size"] = sum(
                f.stat().st_size
                for f in self.db_dir.iterdir()
                if f.suffix == ".parquet"
            )

        return stats

    def search(
        self,
        query: str,
        type: str | None = None,
        limit: int = 20,
    ) -> list[SearchResult]:
        """Full-text search definitions.

        Args:
            query: Search query string
            type: Filter by definition type (function, class, variable, etc.)
            limit: Maximum number of results

        Returns:
            List of SearchResult objects
        """
        return self.search_engine.search(query, type=type, limit=limit)

    def get_definition(self, name: str) -> Definition | None:
        """Get a definition by its full name.

        Args:
            name: Fully qualified name (e.g., "mymodule.MyClass.method")

        Returns:
            Definition object or None if not found
        """
        return self.search_engine.get_definition(name)

    def references(self, name: str) -> list[Reference]:
        """Find all references to a definition.

        Args:
            name: Name to find references for

        Returns:
            List of Reference objects
        """
        return self.search_engine.find_references(name)

    def query(self, sql: str) -> list[dict]:
        """Execute a raw SQL query.

        Args:
            sql: SQL query string

        Returns:
            List of result dictionaries
        """
        return self.db.execute(sql).fetchall()

    def stats(self) -> dict:
        """Get database statistics.

        Returns:
            Dictionary with counts and other statistics
        """
        return self.db.get_stats()

    def close(self):
        """Close the database connection."""
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


__all__ = [
    "__version__",
    "JediDB",
    "Database",
    "Indexer",
    "SearchEngine",
    "Analyzer",
    "Config",
    "FileRecord",
    "Definition",
    "Reference",
    "Import",
    "Decorator",
    "ClassBase",
    "SearchResult",
]
