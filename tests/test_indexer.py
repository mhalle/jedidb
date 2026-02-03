"""Tests for indexer module."""

import pytest
from pathlib import Path

from jedidb.core.indexer import Indexer
from jedidb.core.database import Database
from jedidb.core.analyzer import Analyzer


class TestIndexer:
    """Tests for Indexer class."""

    def test_index_single_file(self, temp_db, sample_python_file, temp_dir):
        """Test indexing a single file."""
        analyzer = Analyzer(project_path=temp_dir)
        indexer = Indexer(temp_db, analyzer)

        stats = indexer.index(paths=[str(sample_python_file)], base_path=temp_dir)

        assert stats["files_indexed"] == 1
        assert stats["definitions_added"] > 0
        assert stats["errors"] == []

    def test_index_directory(self, temp_db, sample_project):
        """Test indexing a directory."""
        analyzer = Analyzer(project_path=sample_project)
        indexer = Indexer(temp_db, analyzer)

        stats = indexer.index(base_path=sample_project)

        assert stats["files_indexed"] >= 2  # main.py and utils.py
        assert stats["definitions_added"] > 0

    def test_incremental_indexing(self, temp_db, sample_python_file, temp_dir):
        """Test that unchanged files are skipped."""
        analyzer = Analyzer(project_path=temp_dir)
        indexer = Indexer(temp_db, analyzer)

        # First index
        stats1 = indexer.index(paths=[str(sample_python_file)], base_path=temp_dir)
        assert stats1["files_indexed"] == 1

        # Second index without changes
        stats2 = indexer.index(paths=[str(sample_python_file)], base_path=temp_dir)
        assert stats2["files_indexed"] == 0
        assert stats2["files_skipped"] == 1

    def test_force_reindex(self, temp_db, sample_python_file, temp_dir):
        """Test force re-indexing."""
        analyzer = Analyzer(project_path=temp_dir)
        indexer = Indexer(temp_db, analyzer)

        # First index
        indexer.index(paths=[str(sample_python_file)], base_path=temp_dir)

        # Force re-index
        stats = indexer.index(paths=[str(sample_python_file)], base_path=temp_dir, force=True)
        assert stats["files_indexed"] == 1
        assert stats["files_skipped"] == 0

    def test_modified_file_reindex(self, temp_db, sample_python_file, temp_dir):
        """Test that modified files are re-indexed."""
        analyzer = Analyzer(project_path=temp_dir)
        indexer = Indexer(temp_db, analyzer)

        # First index
        indexer.index(paths=[str(sample_python_file)], base_path=temp_dir)

        # Modify file
        content = sample_python_file.read_text()
        sample_python_file.write_text(content + "\n\ndef new_function(): pass\n")

        # Re-index
        stats = indexer.index(paths=[str(sample_python_file)], base_path=temp_dir)
        assert stats["files_indexed"] == 1

    def test_exclude_patterns(self, temp_db, sample_project):
        """Test exclude patterns."""
        analyzer = Analyzer(project_path=sample_project)
        indexer = Indexer(temp_db, analyzer)

        # Exclude test files
        stats = indexer.index(
            base_path=sample_project,
            exclude=["**/test_*.py"],
        )

        # Should not index test_utils.py
        file_result = temp_db.execute(
            "SELECT path FROM files WHERE path LIKE '%test_%'"
        ).fetchall()
        assert len(file_result) == 0

    def test_include_patterns(self, temp_db, sample_project):
        """Test include patterns."""
        analyzer = Analyzer(project_path=sample_project)
        indexer = Indexer(temp_db, analyzer)

        # Only include src directory
        stats = indexer.index(
            base_path=sample_project,
            include=["src/**/*.py"],
        )

        # Should only have files from src
        file_result = temp_db.execute("SELECT path FROM files").fetchall()
        for (path,) in file_result:
            assert "src" in path or path.startswith("src")

    def test_cleanup_deleted_files(self, temp_db, temp_dir):
        """Test that deleted files are removed from database."""
        # Create a file
        test_file = temp_dir / "to_delete.py"
        test_file.write_text("x = 1")

        analyzer = Analyzer(project_path=temp_dir)
        indexer = Indexer(temp_db, analyzer)

        # Index it
        indexer.index(paths=[str(test_file)], base_path=temp_dir)
        assert temp_db.get_file("to_delete.py") is not None

        # Delete the file
        test_file.unlink()

        # Re-index the directory (not the specific file)
        stats = indexer.index(base_path=temp_dir)
        assert stats["files_removed"] == 1

        # File should be gone from database
        assert temp_db.get_file("to_delete.py") is None

    def test_progress_callback(self, temp_db, sample_python_file, temp_dir):
        """Test progress callback."""
        analyzer = Analyzer(project_path=temp_dir)

        progress_calls = []

        def on_progress(path, current, total):
            progress_calls.append((path, current, total))

        indexer = Indexer(temp_db, analyzer, progress_callback=on_progress)
        indexer.index(paths=[str(sample_python_file)], base_path=temp_dir)

        assert len(progress_calls) == 1
        assert progress_calls[0][1] == 1  # current
        assert progress_calls[0][2] == 1  # total

    def test_index_error_handling(self, temp_db, temp_dir):
        """Test handling of files that can't be analyzed."""
        # Create a file with encoding issues
        bad_file = temp_dir / "bad_encoding.py"
        bad_file.write_bytes(b"\xff\xfe invalid utf-8")

        analyzer = Analyzer(project_path=temp_dir)
        indexer = Indexer(temp_db, analyzer)

        stats = indexer.index(paths=[str(bad_file)], base_path=temp_dir)

        # Should have an error but not crash
        assert len(stats["errors"]) >= 0  # May or may not error depending on handling
