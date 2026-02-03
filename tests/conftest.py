"""Test fixtures for JediDB."""

import tempfile
from pathlib import Path

import pytest

from jedidb import JediDB
from jedidb.core.database import Database
from jedidb.core.analyzer import Analyzer


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_db(temp_dir):
    """Create a temporary database."""
    db_path = temp_dir / "test.duckdb"
    db = Database(db_path)
    # Trigger lazy connection to create the database file
    _ = db.conn
    yield db
    db.close()


@pytest.fixture
def sample_python_file(temp_dir):
    """Create a sample Python file for testing."""
    file_path = temp_dir / "sample.py"
    file_path.write_text('''"""Sample module for testing."""


class SampleClass:
    """A sample class."""

    def __init__(self, value: int):
        """Initialize with a value."""
        self.value = value

    def get_value(self) -> int:
        """Return the value."""
        return self.value

    def _private_method(self):
        """A private method."""
        pass


def sample_function(x: int, y: int) -> int:
    """Add two numbers.

    Args:
        x: First number
        y: Second number

    Returns:
        Sum of x and y
    """
    return x + y


CONSTANT = 42

_private_var = "private"
''')
    return file_path


@pytest.fixture
def sample_project(temp_dir):
    """Create a sample project structure."""
    # Create src directory
    src_dir = temp_dir / "src"
    src_dir.mkdir()

    # Create main module
    main_file = src_dir / "main.py"
    main_file.write_text('''"""Main module."""

from utils import helper_function


def main():
    """Entry point."""
    result = helper_function(10)
    print(result)


if __name__ == "__main__":
    main()
''')

    # Create utils module
    utils_file = src_dir / "utils.py"
    utils_file.write_text('''"""Utility functions."""


def helper_function(x: int) -> int:
    """A helper function.

    Args:
        x: Input value

    Returns:
        Doubled value
    """
    return x * 2


class Config:
    """Configuration class."""

    def __init__(self):
        self.debug = False
        self.verbose = True
''')

    # Create tests directory
    tests_dir = temp_dir / "tests"
    tests_dir.mkdir()

    test_file = tests_dir / "test_utils.py"
    test_file.write_text('''"""Tests for utils."""

from utils import helper_function


def test_helper():
    assert helper_function(5) == 10
''')

    return temp_dir


@pytest.fixture
def jedidb_instance(temp_dir, sample_python_file):
    """Create a JediDB instance with sample data."""
    db = JediDB(path=str(temp_dir))
    yield db
    db.close()


@pytest.fixture
def indexed_jedidb(jedidb_instance, sample_python_file):
    """Create a JediDB instance with indexed sample data."""
    jedidb_instance.index(paths=[str(sample_python_file)])
    return jedidb_instance


@pytest.fixture
def analyzer(temp_dir):
    """Create an analyzer instance."""
    return Analyzer(project_path=temp_dir)
