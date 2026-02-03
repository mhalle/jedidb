"""Jedi-based code analyzer for JediDB."""

from pathlib import Path
from typing import Generator

import jedi
from jedi.api.classes import Name

from jedidb.core.models import Definition, Import, Reference
from jedidb.utils import get_context_lines


class Analyzer:
    """Wraps Jedi to extract code analysis information."""

    def __init__(self, project_path: Path | str | None = None):
        """Initialize the analyzer.

        Args:
            project_path: Optional project root for Jedi's project detection
        """
        self.project_path = Path(project_path) if project_path else None
        self._project = None

        if self.project_path:
            try:
                self._project = jedi.Project(path=str(self.project_path))
            except Exception:
                pass

    def analyze_file(self, file_path: Path) -> tuple[list[Definition], list[Reference], list[Import]]:
        """Analyze a Python file and extract definitions, references, and imports.

        Args:
            file_path: Path to the Python file

        Returns:
            Tuple of (definitions, references, imports)
        """
        try:
            source = file_path.read_text(encoding="utf-8")
        except Exception as e:
            raise ValueError(f"Could not read file {file_path}: {e}")

        try:
            script = jedi.Script(source, path=str(file_path), project=self._project)
        except Exception as e:
            raise ValueError(f"Could not parse file {file_path}: {e}")

        definitions = list(self._extract_definitions(script, file_path))
        references = list(self._extract_references(script, file_path, source))
        imports = list(self._extract_imports(script, file_path))

        return definitions, references, imports

    def _extract_definitions(
        self, script: jedi.Script, file_path: Path
    ) -> Generator[Definition, None, None]:
        """Extract all definitions from a script."""
        try:
            names = script.get_names(all_scopes=True, definitions=True, references=False)
        except Exception:
            return

        for name in names:
            definition = self._name_to_definition(name, file_path)
            if definition:
                yield definition

    def _name_to_definition(self, name: Name, file_path: Path) -> Definition | None:
        """Convert a Jedi Name to a Definition."""
        try:
            # Get position
            line = name.line
            column = name.column

            if line is None:
                return None

            # Get type
            def_type = self._map_jedi_type(name.type)
            if not def_type:
                return None

            # Get signature for callables
            signature = None
            if def_type in ("function", "class"):
                try:
                    sigs = name.get_signatures()
                    if sigs:
                        signature = sigs[0].to_string()
                except Exception:
                    pass

            # Get docstring
            docstring = None
            try:
                docstring = name.docstring(raw=True)
                if docstring:
                    docstring = docstring.strip()
                    if not docstring:
                        docstring = None
            except Exception:
                pass

            # Determine full name
            full_name = name.full_name
            if not full_name:
                full_name = name.name

            return Definition(
                name=name.name,
                full_name=full_name,
                type=def_type,
                line=line,
                column=column,
                signature=signature,
                docstring=docstring,
                is_public=not name.name.startswith("_"),
            )
        except Exception:
            return None

    def _extract_references(
        self, script: jedi.Script, file_path: Path, source: str
    ) -> Generator[Reference, None, None]:
        """Extract all references from a script."""
        try:
            names = script.get_names(all_scopes=True, definitions=False, references=True)
        except Exception:
            return

        source_lines = source.splitlines()

        for name in names:
            try:
                line = name.line
                column = name.column

                if line is None:
                    continue

                # Get context (the line containing the reference)
                context = None
                if 0 < line <= len(source_lines):
                    context = source_lines[line - 1].strip()
                    # Truncate long context
                    if len(context) > 200:
                        context = context[:200] + "..."

                yield Reference(
                    name=name.name,
                    line=line,
                    column=column,
                    context=context,
                )
            except Exception:
                continue

    def _extract_imports(
        self, script: jedi.Script, file_path: Path
    ) -> Generator[Import, None, None]:
        """Extract all imports from a script."""
        try:
            names = script.get_names(all_scopes=False, definitions=True, references=False)
        except Exception:
            return

        for name in names:
            try:
                if name.type != "module":
                    continue

                # Check if this is an import
                line = name.line
                if line is None:
                    continue

                # Get the module being imported
                module = name.full_name or name.name

                # Check for alias
                alias = None
                if name.name != module.split(".")[-1]:
                    alias = name.name

                yield Import(
                    module=module,
                    name=name.name if alias else None,
                    alias=alias,
                    line=line,
                )
            except Exception:
                continue

    def _map_jedi_type(self, jedi_type: str) -> str | None:
        """Map Jedi type string to our definition types."""
        type_map = {
            "module": "module",
            "class": "class",
            "function": "function",
            "param": "param",
            "statement": "variable",
            "instance": "variable",
            "property": "property",
        }
        return type_map.get(jedi_type)

    def get_completions(self, file_path: Path, line: int, column: int) -> list[dict]:
        """Get code completions at a specific position.

        Args:
            file_path: Path to the Python file
            line: Line number (1-indexed)
            column: Column number (0-indexed)

        Returns:
            List of completion dictionaries
        """
        try:
            source = file_path.read_text(encoding="utf-8")
            script = jedi.Script(source, path=str(file_path), project=self._project)
            completions = script.complete(line, column)

            return [
                {
                    "name": c.name,
                    "type": c.type,
                    "description": c.description,
                    "docstring": c.docstring(raw=True),
                }
                for c in completions
            ]
        except Exception:
            return []

    def get_signatures(self, file_path: Path, line: int, column: int) -> list[dict]:
        """Get function signatures at a specific position.

        Args:
            file_path: Path to the Python file
            line: Line number (1-indexed)
            column: Column number (0-indexed)

        Returns:
            List of signature dictionaries
        """
        try:
            source = file_path.read_text(encoding="utf-8")
            script = jedi.Script(source, path=str(file_path), project=self._project)
            signatures = script.get_signatures(line, column)

            return [
                {
                    "name": s.name,
                    "params": [p.description for p in s.params],
                    "index": s.index,
                    "docstring": s.docstring(raw=True),
                }
                for s in signatures
            ]
        except Exception:
            return []

    def goto_definition(self, file_path: Path, line: int, column: int) -> list[dict]:
        """Go to definition at a specific position.

        Args:
            file_path: Path to the Python file
            line: Line number (1-indexed)
            column: Column number (0-indexed)

        Returns:
            List of definition location dictionaries
        """
        try:
            source = file_path.read_text(encoding="utf-8")
            script = jedi.Script(source, path=str(file_path), project=self._project)
            definitions = script.goto(line, column)

            return [
                {
                    "name": d.name,
                    "full_name": d.full_name,
                    "type": d.type,
                    "path": str(d.module_path) if d.module_path else None,
                    "line": d.line,
                    "column": d.column,
                }
                for d in definitions
            ]
        except Exception:
            return []
