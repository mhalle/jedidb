"""File indexing logic for JediDB."""

from pathlib import Path
from typing import Callable

from jedidb.core.analyzer import Analyzer
from jedidb.core.database import Database
from jedidb.core.models import ClassBase, Definition, FileRecord, Import, Reference
from jedidb.utils import (
    compute_file_hash,
    discover_python_files,
    get_file_modified_time,
    get_file_size,
    normalize_path,
)


class Indexer:
    """Handles indexing of Python files."""

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

    def check_staleness(
        self,
        paths: list[str] | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        base_path: Path | None = None,
    ) -> dict:
        """Check if the index is stale (any files changed, added, or removed).

        Args:
            paths: Specific paths to check. If None, uses base_path or current directory.
            include: Glob patterns to include
            exclude: Glob patterns to exclude
            base_path: Base path for relative path storage

        Returns:
            Dictionary with staleness information:
            - is_stale: True if any changes detected
            - changed: List of files with different content
            - added: List of new files not in index
            - removed: List of indexed files no longer on disk
        """
        if base_path is None:
            base_path = self.analyzer.project_path or Path.cwd()

        # Discover current files on disk
        disk_files = self._discover_files(paths, include, exclude, base_path)
        disk_paths = {normalize_path(f, base_path): f for f in disk_files}

        # Get indexed files from database
        result = self.db.execute("SELECT path, hash FROM files").fetchall()
        db_files = {row[0]: row[1] for row in result}

        changed = []
        added = []
        removed = []

        # Check for changed and new files
        for rel_path, abs_path in disk_paths.items():
            if rel_path in db_files:
                current_hash = compute_file_hash(abs_path)
                if current_hash != db_files[rel_path]:
                    changed.append(rel_path)
            else:
                added.append(rel_path)

        # Check for removed files
        for db_path in db_files:
            if db_path not in disk_paths:
                removed.append(db_path)

        return {
            "is_stale": bool(changed or added or removed),
            "changed": changed,
            "added": added,
            "removed": removed,
        }

    def index(
        self,
        paths: list[str] | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        force: bool = False,
        base_path: Path | None = None,
    ) -> dict:
        """Index Python files.

        Uses all-or-nothing indexing: if any files have changed, all files are
        re-indexed to ensure cross-file references are consistent. If nothing
        has changed, indexing is skipped entirely.

        Args:
            paths: Specific paths to index. If None, uses base_path or current directory.
            include: Glob patterns to include
            exclude: Glob patterns to exclude
            force: Force re-indexing even if no files have changed
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
            "class_bases_added": 0,
            "errors": [],
            "index_skipped": False,
        }

        total_files = len(files_to_index)

        # Check staleness first (unless force)
        if not force:
            staleness = self.check_staleness(paths, include, exclude, base_path)
            if not staleness["is_stale"]:
                # Nothing changed, skip indexing entirely
                stats["files_skipped"] = total_files
                stats["index_skipped"] = True
                return stats

        # Something changed (or force) - do full re-index
        indexed_paths = set()

        for i, file_path in enumerate(files_to_index):
            if self.progress_callback:
                self.progress_callback(str(file_path), i + 1, total_files)

            rel_path = normalize_path(file_path, base_path)
            indexed_paths.add(rel_path)

            try:
                # Always force=True for individual files since we're doing full re-index
                file_stats = self._index_file(file_path, rel_path, force=True)
                if file_stats["indexed"]:
                    stats["files_indexed"] += 1
                    stats["definitions_added"] += file_stats["definitions"]
                    stats["references_added"] += file_stats["references"]
                    stats["imports_added"] += file_stats["imports"]
                    stats["decorators_added"] += file_stats["decorators"]
                    stats["class_bases_added"] += file_stats["class_bases"]
                else:
                    stats["files_skipped"] += 1
            except Exception as e:
                stats["errors"].append({"file": str(file_path), "error": str(e)})

        # Remove files no longer in scope
        stats["files_removed"] = self._cleanup_deleted_files(indexed_paths, base_path, force=True)

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
            "class_bases": 0,
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
        definitions, references, imports, decorators, class_bases = self.analyzer.analyze_file(
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

        # Link decorators and class_bases to definitions by matching full_name
        # Build a mapping of full_name -> id for all definitions in this file
        if decorators or class_bases:
            result = self.db.execute(
                "SELECT id, full_name FROM definitions WHERE file_id = ?",
                (file_id,)
            ).fetchall()
            full_name_to_id = {row[1]: row[0] for row in result}

            # Set definition_id on decorators and clear the temporary full_name
            if decorators:
                for dec in decorators:
                    parent_full_name = dec.full_name
                    dec.definition_id = full_name_to_id.get(parent_full_name)
                    dec.full_name = None  # Clear - this was just for linking

                # Only insert decorators that have a valid definition_id
                valid_decorators = [d for d in decorators if d.definition_id is not None]
                self.db.insert_decorators_batch(valid_decorators)

            # Link class_bases to class definitions
            if class_bases:
                for cb in class_bases:
                    cb.class_id = full_name_to_id.get(cb.class_full_name)
                    # Optionally resolve base_id if base is in our index
                    if cb.base_full_name:
                        cb.base_id = full_name_to_id.get(cb.base_full_name)
                    cb.class_full_name = None  # Clear temp field

                # Only insert class_bases that have a valid class_id
                valid_class_bases = [cb for cb in class_bases if cb.class_id is not None]
                self.db.insert_class_bases_batch(valid_class_bases)

        self.db.insert_references_batch(references)
        self.db.insert_imports_batch(imports)

        stats["indexed"] = True
        stats["definitions"] = len(definitions)
        stats["references"] = len(references)
        stats["imports"] = len(imports)
        stats["decorators"] = len(decorators)
        stats["class_bases"] = len(class_bases)

        return stats

    def _cleanup_deleted_files(
        self, indexed_paths: set[str], base_path: Path, force: bool = False
    ) -> int:
        """Remove files from database that no longer exist or were excluded.

        Args:
            indexed_paths: Set of paths that were indexed in this run
            base_path: Base path for resolving relative paths
            force: If True, remove all files not in indexed_paths (even if they exist)

        Returns:
            Number of files removed
        """
        # Get all files in database
        result = self.db.execute("SELECT path FROM files").fetchall()
        db_paths = {r[0] for r in result}

        # Find files that are in DB but not in indexed paths
        removed = 0
        for db_path in db_paths:
            if db_path not in indexed_paths:
                full_path = base_path / db_path
                # Remove if file deleted OR if force mode (excluded files)
                if not full_path.exists() or force:
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
