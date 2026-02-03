"""Configuration management for JediDB."""

from dataclasses import dataclass, field
from pathlib import Path
import tomllib


DEFAULT_DB_DIR = ".jedidb"
DEFAULT_DB_NAME = "jedidb.duckdb"
CONFIG_FILE_NAME = ".jedidb.toml"


@dataclass
class Config:
    """Configuration for JediDB."""

    project_path: Path = field(default_factory=Path.cwd)
    db_path: Path | None = None
    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.project_path = Path(self.project_path).resolve()

        # Load config file if exists
        config_file = self.project_path / CONFIG_FILE_NAME
        if config_file.exists():
            self._load_config_file(config_file)

        # Set default db_path if not provided
        if self.db_path is None:
            self.db_path = self.project_path / DEFAULT_DB_DIR / DEFAULT_DB_NAME
        else:
            self.db_path = Path(self.db_path)

    def _load_config_file(self, config_file: Path):
        """Load configuration from a TOML file."""
        with open(config_file, "rb") as f:
            data = tomllib.load(f)

        if "jedidb" in data:
            jedidb_config = data["jedidb"]

            if "db_path" in jedidb_config and self.db_path is None:
                self.db_path = Path(jedidb_config["db_path"])

            if "include" in jedidb_config:
                self.include_patterns = jedidb_config["include"]

            if "exclude" in jedidb_config:
                self.exclude_patterns = jedidb_config["exclude"]

    def ensure_db_dir(self):
        """Ensure the database directory exists."""
        if self.db_path:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def find_project_root(cls, start_path: Path | None = None) -> Path | None:
        """Find the project root by looking for config files.

        Args:
            start_path: Starting path for the search

        Returns:
            Project root path or None if not found
        """
        path = (start_path or Path.cwd()).resolve()

        # Look for indicators of project root
        indicators = [
            CONFIG_FILE_NAME,
            DEFAULT_DB_DIR,
            "pyproject.toml",
            "setup.py",
            ".git",
        ]

        while path != path.parent:
            for indicator in indicators:
                if (path / indicator).exists():
                    return path
            path = path.parent

        return None

    def to_dict(self) -> dict:
        """Convert config to dictionary."""
        return {
            "project_path": str(self.project_path),
            "db_path": str(self.db_path) if self.db_path else None,
            "include_patterns": self.include_patterns,
            "exclude_patterns": self.exclude_patterns,
        }


def create_config_file(project_path: Path, db_path: Path | None = None) -> Path:
    """Create a default configuration file.

    Args:
        project_path: Project root directory
        db_path: Optional custom database path

    Returns:
        Path to the created config file
    """
    config_file = project_path / CONFIG_FILE_NAME

    content = '''# JediDB Configuration

[jedidb]
# Database path (relative to project root or absolute)
# db_path = ".jedidb/jedidb.duckdb"

# Glob patterns for files to include
# include = ["src/**/*.py", "lib/**/*.py"]

# Glob patterns for files to exclude
# exclude = ["**/test_*.py", "**/*_test.py"]
'''

    if db_path:
        content = content.replace(
            '# db_path = ".jedidb/jedidb.duckdb"',
            f'db_path = "{db_path}"'
        )

    with open(config_file, "w") as f:
        f.write(content)

    return config_file
