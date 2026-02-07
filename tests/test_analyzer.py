"""Tests for analyzer module."""

import pytest

from jedidb.core.analyzer import Analyzer


class TestAnalyzer:
    """Tests for Analyzer class."""

    def test_analyze_file(self, sample_python_file, analyzer):
        """Test analyzing a Python file."""
        definitions, references, imports, decorators, class_bases = analyzer.analyze_file(sample_python_file)

        assert len(definitions) > 0

        # Check for expected definitions
        def_names = [d.name for d in definitions]
        assert "SampleClass" in def_names
        assert "sample_function" in def_names
        assert "get_value" in def_names

    def test_definition_types(self, sample_python_file, analyzer):
        """Test that definitions have correct types."""
        definitions, _, _, _, _ = analyzer.analyze_file(sample_python_file)

        def_by_name = {d.name: d for d in definitions}

        assert def_by_name["SampleClass"].type == "class"
        assert def_by_name["sample_function"].type == "function"
        assert def_by_name["get_value"].type == "function"

    def test_definition_docstrings(self, sample_python_file, analyzer):
        """Test that docstrings are extracted."""
        definitions, _, _, _, _ = analyzer.analyze_file(sample_python_file)

        def_by_name = {d.name: d for d in definitions}

        assert def_by_name["SampleClass"].docstring is not None
        assert "sample class" in def_by_name["SampleClass"].docstring.lower()

        assert def_by_name["sample_function"].docstring is not None
        assert "add two numbers" in def_by_name["sample_function"].docstring.lower()

    def test_definition_line_numbers(self, sample_python_file, analyzer):
        """Test that line numbers are correct."""
        definitions, _, _, _, _ = analyzer.analyze_file(sample_python_file)

        def_by_name = {d.name: d for d in definitions}

        # SampleClass is at line 5 (after module docstring and imports)
        assert def_by_name["SampleClass"].line > 0
        assert def_by_name["sample_function"].line > def_by_name["SampleClass"].line

    def test_private_definitions(self, sample_python_file, analyzer):
        """Test detection of private definitions."""
        definitions, _, _, _, _ = analyzer.analyze_file(sample_python_file)

        def_by_name = {d.name: d for d in definitions}

        # _private_method should be marked as private
        if "_private_method" in def_by_name:
            assert def_by_name["_private_method"].is_public is False

    def test_references(self, sample_python_file, analyzer):
        """Test reference extraction."""
        _, references, _, _, _ = analyzer.analyze_file(sample_python_file)

        ref_names = [r.name for r in references]

        # Should have at least some references (self, value, etc.)
        assert len(references) > 0

    def test_analyze_invalid_file(self, temp_dir, analyzer):
        """Test analyzing a non-existent file."""
        with pytest.raises(ValueError):
            analyzer.analyze_file(temp_dir / "nonexistent.py")

    def test_analyze_syntax_error(self, temp_dir, analyzer):
        """Test analyzing a file with syntax errors still returns results."""
        bad_file = temp_dir / "bad.py"
        bad_file.write_text("def foo(\n")  # Incomplete syntax

        # Jedi is tolerant of syntax errors - should return results, not raise
        definitions, _, _, _, _ = analyzer.analyze_file(bad_file)
        assert isinstance(definitions, list)

    def test_get_completions(self, sample_python_file, analyzer):
        """Test getting completions."""
        completions = analyzer.get_completions(sample_python_file, 15, 8)
        # Completions at 'self.' inside get_value method
        assert isinstance(completions, list)

    def test_goto_definition(self, sample_python_file, analyzer):
        """Test go-to-definition functionality."""
        results = analyzer.goto_definition(sample_python_file, 14, 15)
        # At 'self.value' in get_value
        assert isinstance(results, list)
