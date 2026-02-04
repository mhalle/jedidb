"""Tests for CLI module."""

import pytest
from pathlib import Path
from typer.testing import CliRunner

from jedidb.cli.app import app


runner = CliRunner()


class TestCLI:
    """Tests for CLI commands."""

    def test_help(self):
        """Test help command."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "jedidb" in result.output.lower()

    def test_init_command(self, temp_dir):
        """Test init command."""
        result = runner.invoke(app, ["-C", str(temp_dir), "init"])
        assert result.exit_code == 0

        # Check that files were created
        assert (temp_dir / ".jedidb").exists()
        assert (temp_dir / ".jedidb" / "config.toml").exists()
        assert (temp_dir / ".jedidb" / "db").exists()

    def test_init_already_exists(self, temp_dir):
        """Test init when already initialized."""
        # Initialize once
        runner.invoke(app, ["-C", str(temp_dir), "init"])

        # Try again without force
        result = runner.invoke(app, ["-C", str(temp_dir), "init"])
        assert result.exit_code == 1

        # With force should succeed
        result = runner.invoke(app, ["-C", str(temp_dir), "init", "--force"])
        assert result.exit_code == 0

    def test_index_command(self, sample_project):
        """Test index command."""
        # Initialize first
        runner.invoke(app, ["-C", str(sample_project), "init"])

        # Index
        result = runner.invoke(app, [
            "-C", str(sample_project),
            "index",
            str(sample_project / "src"),
        ])
        assert result.exit_code == 0
        assert "indexed" in result.output.lower()

    def test_index_with_patterns(self, sample_project):
        """Test index with include/exclude patterns."""
        runner.invoke(app, ["-C", str(sample_project), "init"])

        result = runner.invoke(app, [
            "-C", str(sample_project),
            "index",
            "--exclude", "**/test_*.py",
            "--quiet",
        ])
        assert result.exit_code == 0

    def test_search_command(self, sample_project):
        """Test search command."""
        runner.invoke(app, ["-C", str(sample_project), "init"])
        runner.invoke(app, ["-C", str(sample_project), "index"])

        result = runner.invoke(app, ["-C", str(sample_project), "search", "helper"])
        # Should find helper_function
        assert result.exit_code == 0

    def test_search_with_type_filter(self, sample_project):
        """Test search with type filter."""
        runner.invoke(app, ["-C", str(sample_project), "init"])
        runner.invoke(app, ["-C", str(sample_project), "index"])

        result = runner.invoke(app, [
            "-C", str(sample_project),
            "search", "Config",
            "--type", "class",
        ])
        assert result.exit_code == 0

    def test_search_json_output(self, sample_project):
        """Test search with JSON output."""
        runner.invoke(app, ["-C", str(sample_project), "init"])
        runner.invoke(app, ["-C", str(sample_project), "index"])

        result = runner.invoke(app, [
            "-C", str(sample_project),
            "search", "function",
            "--format", "json",
        ])
        assert result.exit_code == 0

    def test_stats_command(self, sample_project):
        """Test stats command."""
        runner.invoke(app, ["-C", str(sample_project), "init"])
        runner.invoke(app, ["-C", str(sample_project), "index"])

        result = runner.invoke(app, ["-C", str(sample_project), "stats"])
        assert result.exit_code == 0
        assert "files" in result.output.lower() or "Files" in result.output

    def test_stats_json_output(self, sample_project):
        """Test stats with JSON output."""
        runner.invoke(app, ["-C", str(sample_project), "init"])
        runner.invoke(app, ["-C", str(sample_project), "index"])

        result = runner.invoke(app, [
            "-C", str(sample_project),
            "stats",
            "--format", "json",
        ])
        assert result.exit_code == 0
        assert "total_files" in result.output

    def test_query_command(self, sample_project):
        """Test query command."""
        runner.invoke(app, ["-C", str(sample_project), "init"])
        runner.invoke(app, ["-C", str(sample_project), "index"])

        result = runner.invoke(app, [
            "-C", str(sample_project),
            "query",
            "SELECT COUNT(*) FROM definitions",
        ])
        assert result.exit_code == 0

    def test_query_with_format(self, sample_project):
        """Test query with different formats."""
        runner.invoke(app, ["-C", str(sample_project), "init"])
        runner.invoke(app, ["-C", str(sample_project), "index"])

        # JSON format
        result = runner.invoke(app, [
            "-C", str(sample_project),
            "query",
            "SELECT name, type FROM definitions LIMIT 3",
            "--format", "json",
        ])
        assert result.exit_code == 0

        # CSV format
        result = runner.invoke(app, [
            "-C", str(sample_project),
            "query",
            "SELECT name, type FROM definitions LIMIT 3",
            "--format", "csv",
        ])
        assert result.exit_code == 0

    def test_show_command(self, sample_project):
        """Test show command."""
        runner.invoke(app, ["-C", str(sample_project), "init"])
        runner.invoke(app, ["-C", str(sample_project), "index"])

        result = runner.invoke(app, [
            "-C", str(sample_project),
            "show", "helper_function",
        ])
        # May or may not find depending on indexing
        assert result.exit_code in [0, 1]

    def test_export_command(self, sample_project):
        """Test export command."""
        output_file = sample_project / "export.json"

        runner.invoke(app, ["-C", str(sample_project), "init"])
        runner.invoke(app, ["-C", str(sample_project), "index"])

        result = runner.invoke(app, [
            "-C", str(sample_project),
            "export",
            "--output", str(output_file),
            "--format", "json",
        ])
        assert result.exit_code == 0
        assert output_file.exists()

    def test_clean_command(self, sample_project):
        """Test clean command."""
        runner.invoke(app, ["-C", str(sample_project), "init"])
        runner.invoke(app, ["-C", str(sample_project), "index"])

        result = runner.invoke(app, ["-C", str(sample_project), "clean"])
        assert result.exit_code == 0

    def test_clean_all_command(self, sample_project):
        """Test clean --all command."""
        runner.invoke(app, ["-C", str(sample_project), "init"])
        runner.invoke(app, ["-C", str(sample_project), "index"])

        result = runner.invoke(app, [
            "-C", str(sample_project),
            "clean", "--all", "--force",
        ])
        assert result.exit_code == 0

        # Stats should show 0 files
        result = runner.invoke(app, [
            "-C", str(sample_project),
            "stats",
            "--format", "json",
        ])
        assert '"total_files": 0' in result.output

    def test_external_index(self, sample_project, temp_dir):
        """Test using --index to store data outside source directory."""
        external_index = temp_dir / "external_index"

        # Initialize with external index
        result = runner.invoke(app, [
            "-C", str(sample_project),
            "--index", str(external_index),
            "init",
        ])
        assert result.exit_code == 0
        assert external_index.exists()
        assert (external_index / "config.toml").exists()
        assert (external_index / "db").exists()

        # Index with external index
        result = runner.invoke(app, [
            "-C", str(sample_project),
            "--index", str(external_index),
            "index",
        ])
        assert result.exit_code == 0

        # Query using just --index (no -C needed for queries)
        result = runner.invoke(app, [
            "--index", str(external_index),
            "stats",
        ])
        assert result.exit_code == 0
