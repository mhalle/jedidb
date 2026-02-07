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

    @classmethod
    def from_row(cls, row: tuple) -> "Definition":
        """Create a Definition from a standard database query row.

        Expected columns: id, file_id, name, full_name, type, line, col,
        end_line, end_col, signature, docstring, parent_id, is_public[, file_path]
        """
        return cls(
            id=row[0],
            file_id=row[1],
            name=row[2],
            full_name=row[3],
            type=row[4],
            line=row[5],
            column=row[6],
            end_line=row[7],
            end_column=row[8],
            signature=row[9],
            docstring=row[10],
            parent_id=row[11],
            is_public=row[12],
            file_path=row[13] if len(row) > 13 else None,
        )


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
    call_order: int = 0  # Execution sequence within function (1, 2, 3...)
    call_depth: int = 0  # Nesting level (1=top-level, 2=argument to another call)

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
class ClassBase:
    """Represents a base class relationship."""

    id: int | None = None
    class_id: int | None = None
    base_name: str = ""
    base_full_name: str | None = None
    base_id: int | None = None
    position: int = 0
    # Temporary field for linking (class_full_name of the child class)
    class_full_name: str | None = None


@dataclass
class IndexStats:
    """Statistics about the indexed codebase."""

    total_files: int = 0
    total_definitions: int = 0
    total_references: int = 0
    total_imports: int = 0
    definitions_by_type: dict[str, int] = field(default_factory=dict)
    last_indexed: datetime | None = None
