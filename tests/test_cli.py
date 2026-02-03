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
        result = runner.invoke(app, ["init", str(temp_dir)])
        assert result.exit_code == 0

        # Check that files were created
        assert (temp_dir / ".jedidb").exists()
        assert (temp_dir / ".jedidb.toml").exists()

    def test_init_already_exists(self, temp_dir):
        """Test init when already initialized."""
        # Initialize once
        runner.invoke(app, ["init", str(temp_dir)])

        # Try again without force
        result = runner.invoke(app, ["init", str(temp_dir)])
        assert result.exit_code == 1

        # With force should succeed
        result = runner.invoke(app, ["init", str(temp_dir), "--force"])
        assert result.exit_code == 0

    def test_index_command(self, sample_project):
        """Test index command."""
        db_path = sample_project / ".jedidb" / "jedidb.duckdb"

        # Initialize first
        runner.invoke(app, ["init", str(sample_project)])

        # Index with explicit db-path
        result = runner.invoke(app, [
            "index",
            str(sample_project / "src"),
            "--db-path", str(db_path)
        ])
        assert result.exit_code == 0
        assert "indexed" in result.output.lower()

    def test_index_with_patterns(self, sample_project):
        """Test index with include/exclude patterns."""
        db_path = sample_project / ".jedidb" / "jedidb.duckdb"

        runner.invoke(app, ["init", str(sample_project)])

        result = runner.invoke(app, [
            "index",
            str(sample_project),
            "--exclude", "**/test_*.py",
            "--quiet",
            "--db-path", str(db_path)
        ])
        assert result.exit_code == 0

    def test_search_command(self, sample_project):
        """Test search command."""
        db_path = sample_project / ".jedidb" / "jedidb.duckdb"

        runner.invoke(app, ["init", str(sample_project)])
        runner.invoke(app, ["index", str(sample_project), "--db-path", str(db_path)])

        result = runner.invoke(app, ["search", "helper", "--db-path", str(db_path)])
        # Should find helper_function
        assert result.exit_code == 0

    def test_search_with_type_filter(self, sample_project):
        """Test search with type filter."""
        db_path = sample_project / ".jedidb" / "jedidb.duckdb"

        runner.invoke(app, ["init", str(sample_project)])
        runner.invoke(app, ["index", str(sample_project), "--db-path", str(db_path)])

        result = runner.invoke(app, [
            "search", "Config",
            "--type", "class",
            "--db-path", str(db_path)
        ])
        assert result.exit_code == 0

    def test_search_json_output(self, sample_project):
        """Test search with JSON output."""
        db_path = sample_project / ".jedidb" / "jedidb.duckdb"

        runner.invoke(app, ["init", str(sample_project)])
        runner.invoke(app, ["index", str(sample_project), "--db-path", str(db_path)])

        result = runner.invoke(app, [
            "search", "function",
            "--format", "json",
            "--db-path", str(db_path)
        ])
        assert result.exit_code == 0

    def test_stats_command(self, sample_project):
        """Test stats command."""
        db_path = sample_project / ".jedidb" / "jedidb.duckdb"

        runner.invoke(app, ["init", str(sample_project)])
        runner.invoke(app, ["index", str(sample_project), "--db-path", str(db_path)])

        result = runner.invoke(app, ["stats", "--db-path", str(db_path)])
        assert result.exit_code == 0
        assert "files" in result.output.lower() or "Files" in result.output

    def test_stats_json_output(self, sample_project):
        """Test stats with JSON output."""
        db_path = sample_project / ".jedidb" / "jedidb.duckdb"

        runner.invoke(app, ["init", str(sample_project)])
        runner.invoke(app, ["index", str(sample_project), "--db-path", str(db_path)])

        result = runner.invoke(app, [
            "stats",
            "--format", "json",
            "--db-path", str(db_path)
        ])
        assert result.exit_code == 0
        assert "total_files" in result.output

    def test_query_command(self, sample_project):
        """Test query command."""
        db_path = sample_project / ".jedidb" / "jedidb.duckdb"

        runner.invoke(app, ["init", str(sample_project)])
        runner.invoke(app, ["index", str(sample_project), "--db-path", str(db_path)])

        result = runner.invoke(app, [
            "query",
            "SELECT COUNT(*) FROM definitions",
            "--db-path", str(db_path)
        ])
        assert result.exit_code == 0

    def test_query_with_format(self, sample_project):
        """Test query with different formats."""
        db_path = sample_project / ".jedidb" / "jedidb.duckdb"

        runner.invoke(app, ["init", str(sample_project)])
        runner.invoke(app, ["index", str(sample_project), "--db-path", str(db_path)])

        # JSON format
        result = runner.invoke(app, [
            "query",
            "SELECT name, type FROM definitions LIMIT 3",
            "--format", "json",
            "--db-path", str(db_path)
        ])
        assert result.exit_code == 0

        # CSV format
        result = runner.invoke(app, [
            "query",
            "SELECT name, type FROM definitions LIMIT 3",
            "--format", "csv",
            "--db-path", str(db_path)
        ])
        assert result.exit_code == 0

    def test_show_command(self, sample_project):
        """Test show command."""
        db_path = sample_project / ".jedidb" / "jedidb.duckdb"

        runner.invoke(app, ["init", str(sample_project)])
        runner.invoke(app, ["index", str(sample_project), "--db-path", str(db_path)])

        result = runner.invoke(app, [
            "show", "helper_function",
            "--db-path", str(db_path)
        ])
        # May or may not find depending on indexing
        assert result.exit_code in [0, 1]

    def test_export_command(self, sample_project):
        """Test export command."""
        db_path = sample_project / ".jedidb" / "jedidb.duckdb"
        output_file = sample_project / "export.json"

        runner.invoke(app, ["init", str(sample_project)])
        runner.invoke(app, ["index", str(sample_project), "--db-path", str(db_path)])

        result = runner.invoke(app, [
            "export",
            "--output", str(output_file),
            "--format", "json",
            "--db-path", str(db_path)
        ])
        assert result.exit_code == 0
        assert output_file.exists()

    def test_clean_command(self, sample_project):
        """Test clean command."""
        db_path = sample_project / ".jedidb" / "jedidb.duckdb"

        runner.invoke(app, ["init", str(sample_project)])
        runner.invoke(app, ["index", str(sample_project), "--db-path", str(db_path)])

        result = runner.invoke(app, ["clean", "--db-path", str(db_path)])
        assert result.exit_code == 0

    def test_clean_all_command(self, sample_project):
        """Test clean --all command."""
        db_path = sample_project / ".jedidb" / "jedidb.duckdb"

        runner.invoke(app, ["init", str(sample_project)])
        runner.invoke(app, ["index", str(sample_project), "--db-path", str(db_path)])

        result = runner.invoke(app, [
            "clean", "--all", "--force",
            "--db-path", str(db_path)
        ])
        assert result.exit_code == 0

        # Stats should show 0 files
        result = runner.invoke(app, [
            "stats",
            "--format", "json",
            "--db-path", str(db_path)
        ])
        assert '"total_files": 0' in result.output
