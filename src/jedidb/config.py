"""Configuration management for JediDB."""

from dataclasses import dataclass, field
from pathlib import Path
import tomllib


@dataclass
class Config:
    """Configuration for JediDB."""

    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, index_path: Path) -> "Config":
        """Load configuration from index directory.

        Args:
            index_path: Path to the index directory (e.g., .jedidb/)

        Returns:
            Config instance with loaded patterns
        """
        config_file = index_path / "config.toml"
        if config_file.exists():
            with open(config_file, "rb") as f:
                data = tomllib.load(f)
            return cls(
                include_patterns=data.get("include", []),
                exclude_patterns=data.get("exclude", []),
            )
        return cls()
