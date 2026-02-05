"""Tests for database module."""

import pytest

from jedidb.core.database import Database
from jedidb.core.models import Definition, FileRecord, Reference, Import


class TestDatabase:
    """Tests for Database class."""

    def test_create_database(self, temp_dir):
        """Test database creation."""
        db_path = temp_dir / "test.duckdb"
        db = Database(db_path)
        # Trigger lazy connection to create the database
        _ = db.conn

        assert db_path.exists()
        db.close()

    def test_insert_and_get_file(self, temp_db):
        """Test file insertion and retrieval."""
        file_record = FileRecord(
            path="test/file.py",
            hash="abc123",
            size=1024,
        )

        file_id = temp_db.insert_file(file_record)
        assert file_id is not None

        retrieved = temp_db.get_file("test/file.py")
        assert retrieved is not None
        assert retrieved.path == "test/file.py"
        assert retrieved.hash == "abc123"
        assert retrieved.size == 1024

    def test_file_not_found(self, temp_db):
        """Test retrieving non-existent file."""
        result = temp_db.get_file("nonexistent.py")
        assert result is None

    def test_insert_definition(self, temp_db):
        """Test definition insertion."""
        # First create a file
        file_record = FileRecord(path="test.py", hash="abc", size=100)
        file_id = temp_db.insert_file(file_record)

        # Insert definition
        definition = Definition(
            file_id=file_id,
            name="test_func",
            full_name="module.test_func",
            type="function",
            line=10,
            column=0,
            signature="def test_func(x: int) -> int",
            docstring="A test function.",
        )

        def_id = temp_db.insert_definition(definition)
        assert def_id is not None

    def test_insert_definitions_batch(self, temp_db):
        """Test batch definition insertion."""
        file_record = FileRecord(path="test.py", hash="abc", size=100)
        file_id = temp_db.insert_file(file_record)

        definitions = [
            Definition(file_id=file_id, name=f"func_{i}", type="function", line=i * 10, column=0)
            for i in range(5)
        ]

        temp_db.insert_definitions_batch(definitions)

        # Verify insertion
        result = temp_db.execute(
            "SELECT COUNT(*) FROM definitions WHERE file_id = ?", (file_id,)
        ).fetchone()
        assert result[0] == 5

    def test_insert_references_batch(self, temp_db):
        """Test batch reference insertion."""
        file_record = FileRecord(path="test.py", hash="abc", size=100)
        file_id = temp_db.insert_file(file_record)

        references = [
            Reference(file_id=file_id, name=f"ref_{i}", line=i, column=0)
            for i in range(3)
        ]

        temp_db.insert_references_batch(references)

        result = temp_db.execute(
            "SELECT COUNT(*) FROM refs WHERE file_id = ?", (file_id,)
        ).fetchone()
        assert result[0] == 3

    def test_insert_imports_batch(self, temp_db):
        """Test batch import insertion."""
        file_record = FileRecord(path="test.py", hash="abc", size=100)
        file_id = temp_db.insert_file(file_record)

        imports = [
            Import(file_id=file_id, module="os", line=1),
            Import(file_id=file_id, module="sys", line=2),
        ]

        temp_db.insert_imports_batch(imports)

        result = temp_db.execute(
            "SELECT COUNT(*) FROM imports WHERE file_id = ?", (file_id,)
        ).fetchone()
        assert result[0] == 2

    def test_delete_file_cascades(self, temp_db):
        """Test that deleting a file removes related records."""
        file_record = FileRecord(path="test.py", hash="abc", size=100)
        file_id = temp_db.insert_file(file_record)

        # Add some related data
        temp_db.insert_definition(
            Definition(file_id=file_id, name="func", type="function", line=1, column=0)
        )
        temp_db.insert_references_batch([Reference(file_id=file_id, name="ref", line=2, column=0)])
        temp_db.insert_imports_batch([Import(file_id=file_id, module="os", line=1)])

        # Delete file
        temp_db.delete_file(file_id)

        # Verify cascade
        assert temp_db.get_file("test.py") is None
        assert temp_db.execute("SELECT COUNT(*) FROM definitions").fetchone()[0] == 0
        assert temp_db.execute("SELECT COUNT(*) FROM refs").fetchone()[0] == 0
        assert temp_db.execute("SELECT COUNT(*) FROM imports").fetchone()[0] == 0

    def test_get_stats(self, temp_db):
        """Test getting database statistics."""
        # Add some data
        file_record = FileRecord(path="test.py", hash="abc", size=100)
        file_id = temp_db.insert_file(file_record)

        temp_db.insert_definitions_batch([
            Definition(file_id=file_id, name="func", type="function", line=1, column=0),
            Definition(file_id=file_id, name="MyClass", type="class", line=10, column=0),
        ])

        stats = temp_db.get_stats()

        assert stats["total_files"] == 1
        assert stats["total_definitions"] == 2
        assert "function" in stats["definitions_by_type"]
        assert "class" in stats["definitions_by_type"]

    def test_transaction_rollback(self, temp_db):
        """Test transaction rollback on error."""
        file_record = FileRecord(path="test.py", hash="abc", size=100)
        temp_db.insert_file(file_record)

        try:
            with temp_db.transaction():
                temp_db.execute("DELETE FROM files")
                raise ValueError("Test error")
        except ValueError:
            pass

        # File should still exist due to rollback
        assert temp_db.get_file("test.py") is not None

    def test_insert_definition_duplicate_name_line(self, temp_db):
        """Test that insert_definition returns correct ID with duplicate name+line but different columns."""
        file_record = FileRecord(path="test.py", hash="abc", size=100)
        file_id = temp_db.insert_file(file_record)

        # Insert two definitions with same name and line but different columns
        def1 = Definition(
            file_id=file_id,
            name="x",
            full_name="module.x",
            type="variable",
            line=10,
            column=0,
        )
        def2 = Definition(
            file_id=file_id,
            name="x",
            full_name="module.x",
            type="variable",
            line=10,
            column=5,  # Different column
        )

        id1 = temp_db.insert_definition(def1)
        id2 = temp_db.insert_definition(def2)

        # IDs should be different
        assert id1 != id2

        # Verify both records exist with correct columns
        result = temp_db.execute(
            "SELECT id, col FROM definitions WHERE file_id = ? ORDER BY id",
            (file_id,)
        ).fetchall()
        assert len(result) == 2
        assert result[0] == (id1, 0)
        assert result[1] == (id2, 5)

    def test_insert_reference_duplicate_name_line(self, temp_db):
        """Test that insert_reference returns correct ID with duplicate name+line but different columns."""
        file_record = FileRecord(path="test.py", hash="abc", size=100)
        file_id = temp_db.insert_file(file_record)

        # Insert two references with same name and line but different columns
        ref1 = Reference(
            file_id=file_id,
            name="func",
            line=20,
            column=0,
            is_call=True,
        )
        ref2 = Reference(
            file_id=file_id,
            name="func",
            line=20,
            column=10,  # Different column
            is_call=True,
        )

        id1 = temp_db.insert_reference(ref1)
        id2 = temp_db.insert_reference(ref2)

        # IDs should be different
        assert id1 != id2

        # Verify both records exist with correct columns
        result = temp_db.execute(
            "SELECT id, col FROM refs WHERE file_id = ? ORDER BY id",
            (file_id,)
        ).fetchall()
        assert len(result) == 2
        assert result[0] == (id1, 0)
        assert result[1] == (id2, 10)
