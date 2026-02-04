"""Data models for JediDB analysis results."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class FileRecord:
    """Represents an indexed file."""

    id: int | None = None
    path: str = ""
    hash: str = ""
    size: int = 0
    modified_at: datetime | None = None
    indexed_at: datetime | None = None

    @property
    def path_obj(self) -> Path:
        return Path(self.path)


@dataclass
class Definition:
    """Represents a code definition (function, class, variable, etc.)."""

    id: int | None = None
    file_id: int | None = None
    name: str = ""
    full_name: str | None = None
    type: str = ""  # 'function', 'class', 'variable', 'param', 'module', 'statement'
    line: int = 0
    column: int = 0
    end_line: int | None = None
    end_column: int | None = None
    signature: str | None = None
    docstring: str | None = None
    parent_id: int | None = None
    parent_full_name: str | None = None
    is_public: bool = True
    search_text: str | None = None  # Pre-computed searchable text

    # Optional joined data
    file_path: str | None = None

    def __post_init__(self):
        if self.full_name is None:
            self.full_name = self.name
        if self.name:
            self.is_public = not self.name.startswith("_")


@dataclass
class Reference:
    """Represents a reference to a definition."""

    id: int | None = None
    file_id: int | None = None
    definition_id: int | None = None
    name: str = ""
    line: int = 0
    column: int = 0
    context: str | None = None
    target_full_name: str | None = None
    target_module_path: str | None = None
    is_call: bool = False

    # Optional joined data
    file_path: str | None = None


@dataclass
class Import:
    """Represents an import statement."""

    id: int | None = None
    file_id: int | None = None
    module: str = ""
    name: str | None = None
    alias: str | None = None
    line: int = 0

    # Optional joined data
    file_path: str | None = None


@dataclass
class SearchResult:
    """Represents a search result with relevance score."""

    definition: Definition
    score: float = 0.0
    matched_field: str | None = None

    @property
    def name(self) -> str:
        return self.definition.name

    @property
    def full_name(self) -> str | None:
        return self.definition.full_name

    @property
    def type(self) -> str:
        return self.definition.type

    @property
    def file_path(self) -> str | None:
        return self.definition.file_path

    @property
    def line(self) -> int:
        return self.definition.line


@dataclass
class Decorator:
    """Represents a decorator on a function or class."""

    id: int | None = None
    definition_id: int | None = None
    name: str = ""
    full_name: str | None = None
    arguments: str | None = None
    line: int = 0


@dataclass
class IndexStats:
    """Statistics about the indexed codebase."""

    total_files: int = 0
    total_definitions: int = 0
    total_references: int = 0
    total_imports: int = 0
    definitions_by_type: dict[str, int] = field(default_factory=dict)
    last_indexed: datetime | None = None
