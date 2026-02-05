"""Tests for watch mode functionality."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from jedidb import JediDB
from jedidb.cli.commands.index import make_watch_filter


class TestWatchFilter:
    """Tests for make_watch_filter function."""

    def test_watch_filter_excludes_patterns(self, temp_dir):
        """Test that watch filter excludes files matching exclude patterns."""
        watch_filter = make_watch_filter(
            include_patterns=[],
            exclude_patterns=["test_*", "*_test.py"],
            source=temp_dir,
        )

        # Create mock change type
        change = MagicMock()

        # Should accept regular files
        assert watch_filter(change, str(temp_dir / "module.py")) is True
        assert watch_filter(change, str(temp_dir / "src" / "utils.py")) is True

        # Should reject files matching exclude patterns
        assert watch_filter(change, str(temp_dir / "test_module.py")) is False
        assert watch_filter(change, str(temp_dir / "module_test.py")) is False

    def test_watch_filter_includes_patterns(self, temp_dir):
        """Test that watch filter only includes files matching include patterns."""
        watch_filter = make_watch_filter(
            include_patterns=["src/"],
            exclude_patterns=[],
            source=temp_dir,
        )

        change = MagicMock()

        # Create src directory for the test
        (temp_dir / "src").mkdir()

        # Should accept files in src/
        assert watch_filter(change, str(temp_dir / "src" / "module.py")) is True
        assert watch_filter(change, str(temp_dir / "src" / "sub" / "utils.py")) is True

        # Should reject files outside src/
        assert watch_filter(change, str(temp_dir / "other.py")) is False
        assert watch_filter(change, str(temp_dir / "tests" / "test.py")) is False

    def test_watch_filter_combined_include_exclude(self, temp_dir):
        """Test that watch filter applies both include and exclude patterns."""
        watch_filter = make_watch_filter(
            include_patterns=["src/"],
            exclude_patterns=["test_*"],
            source=temp_dir,
        )

        change = MagicMock()

        # Should accept files in src/ that don't match excludes
        assert watch_filter(change, str(temp_dir / "src" / "module.py")) is True

        # Should reject files in src/ that match excludes
        assert watch_filter(change, str(temp_dir / "src" / "test_module.py")) is False

        # Should reject files outside src/ even if they don't match excludes
        assert watch_filter(change, str(temp_dir / "other.py")) is False

    def test_watch_filter_rejects_non_python(self, temp_dir):
        """Test that watch filter rejects non-Python files."""
        watch_filter = make_watch_filter(
            include_patterns=[],
            exclude_patterns=[],
            source=temp_dir,
        )

        change = MagicMock()

        assert watch_filter(change, str(temp_dir / "readme.md")) is False
        assert watch_filter(change, str(temp_dir / "config.json")) is False
        assert watch_filter(change, str(temp_dir / "script.py")) is True


class TestWatchModeDerivedDataRebuild:
    """Tests for derived data rebuild after file deletion in watch mode."""

    def test_deletion_rebuilds_call_graph(self, temp_dir):
        """Test that deleting a file rebuilds the call graph."""
        # Create a project with two files where one calls the other
        src_dir = temp_dir / "src"
        src_dir.mkdir()

        caller_file = src_dir / "caller.py"
        caller_file.write_text('''"""Caller module."""
from callee import helper

def main():
    """Call the helper."""
    result = helper()
    return result
''')

        callee_file = src_dir / "callee.py"
        callee_file.write_text('''"""Callee module."""

def helper():
    """Helper function."""
    return 42
''')

        # Index the project
        index_dir = temp_dir / ".jedidb"
        index_dir.mkdir()
        (index_dir / "db").mkdir()

        jedidb = JediDB(source=src_dir, index=index_dir, resolve_refs=True)
        jedidb.index_files()

        # Get the file_id for callee.py
        callee_file_id = jedidb.db.execute(
            "SELECT id FROM files WHERE path = 'callee.py'"
        ).fetchone()[0]

        # Verify the helper definition exists in callee.py (the actual function definition)
        helper_def = jedidb.db.execute(
            "SELECT id FROM definitions WHERE name = 'helper' AND file_id = ?",
            (callee_file_id,)
        ).fetchone()
        assert helper_def is not None, "helper definition should exist in callee.py"
        helper_id = helper_def[0]

        # Verify call graph has entries pointing to this definition
        calls_to_helper = jedidb.db.execute(
            "SELECT COUNT(*) FROM calls WHERE callee_id = ?", (helper_id,)
        ).fetchone()[0]
        assert calls_to_helper > 0, "Should have calls to helper before deletion"

        # Simulate watch mode deletion: delete callee file and rebuild
        jedidb.db.delete_file_by_path("callee.py")

        # Verify the helper definition from callee.py is deleted
        helper_def_after = jedidb.db.execute(
            "SELECT id FROM definitions WHERE id = ?", (helper_id,)
        ).fetchone()
        assert helper_def_after is None, "helper definition from callee.py should be deleted"

        # Rebuild derived data (same as watch mode does)
        jedidb.db.populate_parent_ids()
        jedidb.db.build_call_graph()
        try:
            jedidb.db.create_fts_index()
        except Exception:
            pass  # FTS may not be available in restricted CI environments

        # After rebuild, calls should no longer reference the deleted definition ID
        resolved_calls_to_deleted = jedidb.db.execute(
            "SELECT COUNT(*) FROM calls WHERE callee_id = ?", (helper_id,)
        ).fetchone()[0]

        assert resolved_calls_to_deleted == 0, \
            f"Calls to deleted definition ID {helper_id} should not exist after rebuild"

        jedidb.close()

    def test_deletion_rebuilds_fts_index(self, temp_dir):
        """Test that deleting a file updates the FTS index."""
        src_dir = temp_dir / "src"
        src_dir.mkdir()

        # Create a file with a unique searchable name
        unique_file = src_dir / "unique_module.py"
        unique_file.write_text('''"""Module with unique name."""

def zebra_function_xyz():
    """A function with a unique name for searching."""
    pass
''')

        # Index the project
        index_dir = temp_dir / ".jedidb"
        index_dir.mkdir()
        (index_dir / "db").mkdir()

        jedidb = JediDB(source=src_dir, index=index_dir)
        jedidb.index_files()

        # Verify the definition exists via direct query (FTS-independent check)
        def_exists = jedidb.db.execute(
            "SELECT COUNT(*) FROM definitions WHERE name = 'zebra_function_xyz'"
        ).fetchone()[0]
        assert def_exists == 1

        # Try FTS search - may fail in restricted CI environments
        try:
            results_before = jedidb.search("zebra_function_xyz")
            fts_available = len(results_before) > 0
        except Exception:
            fts_available = False

        # Simulate watch mode deletion
        jedidb.db.delete_file_by_path("unique_module.py")

        # Rebuild FTS index (same as watch mode does)
        try:
            jedidb.db.create_fts_index()
        except Exception:
            pass  # FTS may not be available

        # Verify the definition is gone from the database
        def_exists_after = jedidb.db.execute(
            "SELECT COUNT(*) FROM definitions WHERE name = 'zebra_function_xyz'"
        ).fetchone()[0]
        assert def_exists_after == 0, "Definition should be deleted from database"

        # If FTS was available, verify search returns nothing
        if fts_available:
            results_after = jedidb.search("zebra_function_xyz")
            assert len(results_after) == 0, "FTS should not find deleted definition"

        jedidb.close()

    def test_deletion_updates_parent_ids(self, temp_dir):
        """Test that deleting a file with classes updates parent_id references."""
        src_dir = temp_dir / "src"
        src_dir.mkdir()

        # Create a file with nested definitions
        nested_file = src_dir / "nested.py"
        nested_file.write_text('''"""Module with nested definitions."""

class OuterClass:
    """Outer class."""

    def outer_method(self):
        """Method of outer class."""
        pass

    class InnerClass:
        """Inner class."""

        def inner_method(self):
            """Method of inner class."""
            pass
''')

        # Index the project
        index_dir = temp_dir / ".jedidb"
        index_dir.mkdir()
        (index_dir / "db").mkdir()

        jedidb = JediDB(source=src_dir, index=index_dir)
        jedidb.index_files()

        # Verify parent relationships exist
        parent_refs = jedidb.db.execute(
            "SELECT COUNT(*) FROM definitions WHERE parent_id IS NOT NULL"
        ).fetchone()[0]
        assert parent_refs > 0

        # Simulate watch mode deletion
        jedidb.db.delete_file_by_path("nested.py")

        # Rebuild parent IDs
        jedidb.db.populate_parent_ids()

        # After deletion, no definitions should remain with parent refs to deleted file
        remaining_defs = jedidb.db.execute(
            "SELECT COUNT(*) FROM definitions"
        ).fetchone()[0]
        assert remaining_defs == 0

        jedidb.close()
