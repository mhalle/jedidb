"""Tests for database views created by init.sql."""

import tempfile
from pathlib import Path

import pytest

from jedidb import JediDB


@pytest.fixture
def indexed_project():
    """Create and index a project with classes, decorators, and inheritance."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)

        # Create a file with various constructs to test views
        code_file = project_dir / "models.py"
        code_file.write_text('''"""Models module."""

class BaseModel:
    """Base model class."""

    def save(self):
        """Save the model."""
        pass


class User(BaseModel):
    """User model."""

    def __init__(self, name: str):
        self.name = name

    @property
    def display_name(self):
        """Get display name."""
        return self.name.title()

    @staticmethod
    def create(name: str):
        """Factory method."""
        return User(name)


def helper_function():
    """A standalone function."""
    user = User("test")
    user.save()
    return user
''')

        # Index the project
        index_dir = project_dir / ".jedidb"
        db = JediDB(source=project_dir, index=index_dir)
        db.index_files()
        db.close()

        # Re-open to load from parquet (which runs init.sql with views)
        db = JediDB(source=project_dir, index=index_dir)
        yield db
        db.close()


class TestViews:
    """Tests for convenience views."""

    def test_functions_view(self, indexed_project):
        """Test the functions view."""
        results = indexed_project.query(
            "SELECT name, file_path FROM functions ORDER BY name"
        )
        names = [r[0] for r in results]

        assert "helper_function" in names
        assert "save" in names
        assert "__init__" in names
        # Verify file_path is included
        assert all(r[1].endswith("models.py") for r in results)

    def test_classes_view(self, indexed_project):
        """Test the classes view."""
        results = indexed_project.query(
            "SELECT name, file_path FROM classes ORDER BY name"
        )
        names = [r[0] for r in results]

        assert "BaseModel" in names
        assert "User" in names
        assert len(names) == 2

    def test_definitions_with_path_view(self, indexed_project):
        """Test the definitions_with_path view."""
        results = indexed_project.query(
            "SELECT name, type, file_path FROM definitions_with_path WHERE type = 'class'"
        )

        assert len(results) == 2
        assert all(r[2].endswith("models.py") for r in results)

    def test_class_hierarchy_view(self, indexed_project):
        """Test the class_hierarchy view."""
        results = indexed_project.query(
            "SELECT class_name, base_name FROM class_hierarchy WHERE base_name IS NOT NULL"
        )

        # User inherits from BaseModel
        assert any(r[0] == "User" and r[1] == "BaseModel" for r in results)

    def test_decorated_definitions_view(self, indexed_project):
        """Test the decorated_definitions view."""
        results = indexed_project.query(
            "SELECT name, decorator_name FROM decorated_definitions ORDER BY name"
        )

        decorators = {r[0]: r[1] for r in results}
        assert decorators.get("display_name") == "property"
        assert decorators.get("create") == "staticmethod"

    def test_calls_with_context_view(self, indexed_project):
        """Test the calls_with_context view."""
        results = indexed_project.query(
            "SELECT caller_full_name, callee_name, file_path FROM calls_with_context"
        )

        # helper_function calls User() and user.save()
        callee_names = [r[1] for r in results]
        assert "User" in callee_names or "save" in callee_names

    def test_refs_with_path_view(self, indexed_project):
        """Test the refs_with_path view."""
        results = indexed_project.query(
            "SELECT name, file_path FROM refs_with_path WHERE name = 'User'"
        )

        assert len(results) > 0
        assert all(r[1].endswith("models.py") for r in results)

    def test_imports_with_path_view(self, indexed_project):
        """Test the imports_with_path view exists and works."""
        # Just verify the view exists and can be queried
        results = indexed_project.query(
            "SELECT COUNT(*) FROM imports_with_path"
        )
        assert results[0][0] >= 0  # May be 0 if no imports
