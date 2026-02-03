"""Utility functions for JediDB."""

import hashlib
import re
from datetime import datetime
from pathlib import Path


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA256 hash of a file's content.

    Args:
        file_path: Path to the file

    Returns:
        Hex-encoded SHA256 hash string
    """
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_file_modified_time(file_path: Path) -> datetime:
    """Get the modification time of a file.

    Args:
        file_path: Path to the file

    Returns:
        Datetime of last modification
    """
    stat = file_path.stat()
    return datetime.fromtimestamp(stat.st_mtime)


def get_file_size(file_path: Path) -> int:
    """Get the size of a file in bytes.

    Args:
        file_path: Path to the file

    Returns:
        File size in bytes
    """
    return file_path.stat().st_size


def normalize_path(path: Path, base_path: Path | None = None) -> str:
    """Normalize a path to a consistent string representation.

    Args:
        path: Path to normalize
        base_path: Optional base path to make relative to

    Returns:
        Normalized path string
    """
    path = path.resolve()
    if base_path:
        try:
            return str(path.relative_to(base_path.resolve()))
        except ValueError:
            pass
    return str(path)


def is_python_file(path: Path) -> bool:
    """Check if a path is a Python file.

    Args:
        path: Path to check

    Returns:
        True if the path is a Python file
    """
    return path.is_file() and path.suffix == ".py"


def glob_match(path_str: str, pattern: str) -> bool:
    """Match a path against a glob pattern with proper ** support.

    Unlike Path.match(), this correctly handles ** to match zero or more
    directory levels.

    Args:
        path_str: Path string to match
        pattern: Glob pattern (supports *, **, and ?)

    Returns:
        True if the path matches the pattern
    """
    # Convert glob pattern to regex
    # ** matches any number of directories (including zero)
    # * matches anything except /
    regex_parts = []
    i = 0
    while i < len(pattern):
        if pattern[i : i + 2] == "**":
            regex_parts.append(".*")  # Match anything including /
            i += 2
            # Skip following / if present (** absorbs it)
            if i < len(pattern) and pattern[i] == "/":
                regex_parts.append("/?")
                i += 1
        elif pattern[i] == "*":
            regex_parts.append("[^/]*")  # Match anything except /
            i += 1
        elif pattern[i] == "?":
            regex_parts.append("[^/]")  # Match single char except /
            i += 1
        elif pattern[i] in r".^$+{}[]|()\\":
            regex_parts.append("\\" + pattern[i])
            i += 1
        else:
            regex_parts.append(pattern[i])
            i += 1

    regex_pattern = "^" + "".join(regex_parts) + "$"
    return bool(re.match(regex_pattern, path_str))


def match_glob_patterns(
    path: Path,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    base_path: Path | None = None,
) -> bool:
    """Check if a path matches include/exclude glob patterns.

    Args:
        path: Path to check
        include: Glob patterns to include (if None, include all)
        exclude: Glob patterns to exclude
        base_path: Base path for relative pattern matching

    Returns:
        True if the path should be included
    """
    if base_path:
        try:
            rel_path = path.relative_to(base_path)
        except ValueError:
            rel_path = path
    else:
        rel_path = path

    rel_str = str(rel_path)

    # Check exclude patterns first
    if exclude:
        for pattern in exclude:
            if glob_match(rel_str, pattern):
                return False

    # Check include patterns
    if include:
        for pattern in include:
            if glob_match(rel_str, pattern):
                return True
        return False

    return True


def discover_python_files(
    root: Path,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> list[Path]:
    """Discover Python files in a directory.

    Args:
        root: Root directory to search
        include: Glob patterns to include
        exclude: Glob patterns to exclude

    Returns:
        List of Python file paths
    """
    root = root.resolve()
    files = []

    # Default exclude patterns
    default_exclude = [
        "__pycache__/*",
        ".*",
        ".git/*",
        ".venv/*",
        "venv/*",
        "*.egg-info/*",
        "build/*",
        "dist/*",
    ]
    all_exclude = (exclude or []) + default_exclude

    for path in root.rglob("*.py"):
        if match_glob_patterns(path, include, all_exclude, root):
            files.append(path)

    return sorted(files)


def get_context_lines(file_path: Path, line: int, context: int = 1) -> str:
    """Get lines of context around a specific line.

    Args:
        file_path: Path to the file
        line: Line number (1-indexed)
        context: Number of context lines before and after

    Returns:
        String with the context lines
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        start = max(0, line - 1 - context)
        end = min(len(lines), line + context)

        return "".join(lines[start:end]).rstrip()
    except Exception:
        return ""
