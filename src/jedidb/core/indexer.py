"""File indexing logic for JediDB."""

from pathlib import Path
from typing import Callable

from jedidb.core.analyzer import Analyzer
from jedidb.core.database import Database
from jedidb.core.models import Definition, FileRecord, Import, Reference
from jedidb.utils import (
    compute_file_hash,
    discover_python_files,
    get_file_modified_time,
    get_file_size,
    normalize_path,
)


class Indexer:
    """Handles incremental indexing of Python files."""

    def __init__(
        self,
        db: Database,
        analyzer: Analyzer,
        progress_callback: Callable[[str, int, int], None] | None = None,
        resolve_refs: bool = False,
    ):
        """Initialize the indexer.

        Args:
            db: Database instance
            analyzer: Analyzer instance
            progress_callback: Optional callback for progress updates (file_path, current, total)
            resolve_refs: Whether to resolve reference targets (enables call graph)
        """
        self.db = db
        self.analyzer = analyzer
        self.progress_callback = progress_callback
        self.resolve_refs = resolve_refs

    def index(
        self,
        paths: list[str] | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        force: bool = False,
        base_path: Path | None = None,
    ) -> dict:
        """Index Python files.

        Args:
            paths: Specific paths to index. If None, uses base_path or current directory.
            include: Glob patterns to include
            exclude: Glob patterns to exclude
            force: Force re-indexing even if files haven't changed
            base_path: Base path for relative path storage

        Returns:
            Dictionary with indexing statistics
        """
        if base_path is None:
            base_path = self.analyzer.project_path or Path.cwd()

        # Discover files to index
        files_to_index = self._discover_files(paths, include, exclude, base_path)

        stats = {
            "files_indexed": 0,
            "files_skipped": 0,
            "files_removed": 0,
            "definitions_added": 0,
            "references_added": 0,
            "imports_added": 0,
            "decorators_added": 0,
            "errors": [],
        }

        total_files = len(files_to_index)
        indexed_paths = set()

        for i, file_path in enumerate(files_to_index):
            if self.progress_callback:
                self.progress_callback(str(file_path), i + 1, total_files)

            rel_path = normalize_path(file_path, base_path)
            indexed_paths.add(rel_path)

            try:
                file_stats = self._index_file(file_path, rel_path, force)
                if file_stats["indexed"]:
                    stats["files_indexed"] += 1
                    stats["definitions_added"] += file_stats["definitions"]
                    stats["references_added"] += file_stats["references"]
                    stats["imports_added"] += file_stats["imports"]
                    stats["decorators_added"] += file_stats["decorators"]
                else:
                    stats["files_skipped"] += 1
            except Exception as e:
                stats["errors"].append({"file": str(file_path), "error": str(e)})

        # Remove deleted files
        stats["files_removed"] = self._cleanup_deleted_files(indexed_paths, base_path)

        # Post-processing: populate parent_ids and build call graph
        if stats["files_indexed"] > 0 or stats["files_removed"] > 0:
            try:
                self.db.populate_parent_ids()
            except Exception:
                pass

            if self.resolve_refs:
                try:
                    self.db.build_call_graph()
                except Exception:
                    pass

            # Rebuild FTS index after changes
            try:
                self.db.create_fts_index()
            except Exception:
                pass  # FTS index creation is optional

        return stats

    def _discover_files(
        self,
        paths: list[str] | None,
        include: list[str] | None,
        exclude: list[str] | None,
        base_path: Path,
    ) -> list[Path]:
        """Discover Python files to index."""
        all_files = []

        if paths:
            for path_str in paths:
                path = Path(path_str)
                if not path.is_absolute():
                    path = base_path / path

                if path.is_file() and path.suffix == ".py":
                    all_files.append(path)
                elif path.is_dir():
                    all_files.extend(discover_python_files(path, include, exclude))
        else:
            all_files = discover_python_files(base_path, include, exclude)

        return all_files

    def _index_file(self, file_path: Path, rel_path: str, force: bool) -> dict:
        """Index a single file.

        Returns:
            Dictionary with indexing statistics for this file
        """
        stats = {
            "indexed": False,
            "definitions": 0,
            "references": 0,
            "imports": 0,
            "decorators": 0,
        }

        # Check if file needs reindexing
        current_hash = compute_file_hash(file_path)
        existing_file = self.db.get_file(rel_path)

        if existing_file:
            if not force and existing_file.hash == current_hash:
                # File hasn't changed
                return stats

            # File changed or force re-index, delete old records
            self.db.delete_file(existing_file.id)

        # Create file record
        file_record = FileRecord(
            path=rel_path,
            hash=current_hash,
            size=get_file_size(file_path),
            modified_at=get_file_modified_time(file_path),
        )
        file_id = self.db.insert_file(file_record)

        # Analyze file
        definitions, references, imports, decorators = self.analyzer.analyze_file(
            file_path, resolve_refs=self.resolve_refs
        )

        # Set file_id on all records
        for d in definitions:
            d.file_id = file_id
        for r in references:
            r.file_id = file_id
        for i in imports:
            i.file_id = file_id

        # Insert definitions first to get their IDs for decorators
        self.db.insert_definitions_batch(definitions)

        # Link decorators to definitions by matching full_name
        # Decorators have full_name set to their parent definition's full_name
        if decorators:
            result = self.db.execute(
                "SELECT id, full_name FROM definitions WHERE file_id = ?",
                (file_id,)
            ).fetchall()
            full_name_to_id = {row[1]: row[0] for row in result}

            # Set definition_id on decorators and clear the temporary full_name
            for dec in decorators:
                parent_full_name = dec.full_name
                dec.definition_id = full_name_to_id.get(parent_full_name)
                dec.full_name = None  # Clear - this was just for linking

            # Only insert decorators that have a valid definition_id
            valid_decorators = [d for d in decorators if d.definition_id is not None]
            self.db.insert_decorators_batch(valid_decorators)

        self.db.insert_references_batch(references)
        self.db.insert_imports_batch(imports)

        stats["indexed"] = True
        stats["definitions"] = len(definitions)
        stats["references"] = len(references)
        stats["imports"] = len(imports)
        stats["decorators"] = len(decorators)

        return stats

    def _cleanup_deleted_files(self, indexed_paths: set[str], base_path: Path) -> int:
        """Remove files from database that no longer exist.

        Returns:
            Number of files removed
        """
        # Get all files in database
        result = self.db.execute("SELECT path FROM files").fetchall()
        db_paths = {r[0] for r in result}

        # Find files that are in DB but not in indexed paths
        # Only remove if the file is under base_path and no longer exists
        removed = 0
        for db_path in db_paths:
            if db_path not in indexed_paths:
                # Check if file still exists
                full_path = base_path / db_path
                if not full_path.exists():
                    self.db.delete_file_by_path(db_path)
                    removed += 1

        return removed

    def index_single_file(self, file_path: Path, base_path: Path | None = None) -> dict:
        """Index a single file.

        Args:
            file_path: Path to the file
            base_path: Base path for relative path storage

        Returns:
            Dictionary with indexing statistics
        """
        if base_path is None:
            base_path = self.analyzer.project_path or Path.cwd()

        rel_path = normalize_path(file_path, base_path)

        with self.db.transaction():
            stats = self._index_file(file_path, rel_path, force=True)

        if stats["indexed"]:
            try:
                self.db.create_fts_index()
            except Exception:
                pass

        return stats
