"""Jedi-based code analyzer for JediDB."""

from pathlib import Path
from typing import Generator

import jedi
from jedi.api.classes import Name

from jedidb.core.models import Decorator, Definition, Import, Reference
from jedidb.utils import get_context_lines, make_search_text


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

    def analyze_file(
        self, file_path: Path, resolve_refs: bool = False
    ) -> tuple[list[Definition], list[Reference], list[Import], list[Decorator]]:
        """Analyze a Python file and extract definitions, references, imports, and decorators.

        Args:
            file_path: Path to the Python file
            resolve_refs: Whether to resolve reference targets (enables call graph)

        Returns:
            Tuple of (definitions, references, imports, decorators)
        """
        try:
            source = file_path.read_text(encoding="utf-8")
        except Exception as e:
            raise ValueError(f"Could not read file {file_path}: {e}")

        try:
            script = jedi.Script(source, path=str(file_path), project=self._project)
        except Exception as e:
            raise ValueError(f"Could not parse file {file_path}: {e}")

        definitions, decorators = self._extract_definitions_and_decorators(script, file_path)
        references = list(self._extract_references(script, file_path, source, resolve_refs))
        imports = list(self._extract_imports(script, file_path))

        return definitions, references, imports, decorators

    def _extract_definitions_and_decorators(
        self, script: jedi.Script, file_path: Path
    ) -> tuple[list[Definition], list[Decorator]]:
        """Extract all definitions and decorators from a script."""
        definitions = []
        decorators = []

        try:
            names = script.get_names(all_scopes=True, definitions=True, references=False)
        except Exception:
            return definitions, decorators

        for name in names:
            result = self._name_to_definition(name, file_path)
            if result:
                definition, decs = result
                definitions.append(definition)
                decorators.extend(decs)

        return definitions, decorators

    def _get_definition_range(self, name: Name) -> tuple[int | None, int | None]:
        """Return (end_line, end_col) using Jedi internals."""
        try:
            tree_name = name._name.tree_name
            if hasattr(tree_name, "get_definition"):
                node = tree_name.get_definition()
                if node and hasattr(node, "end_pos"):
                    return (node.end_pos[0], node.end_pos[1])
        except Exception:
            pass
        return (None, None)

    def _extract_decorators(self, name: Name) -> list[dict]:
        """Extract decorators from a function/class definition."""
        decorators = []
        try:
            tree_name = name._name.tree_name
            if hasattr(tree_name, "get_definition"):
                node = tree_name.get_definition()
                if node and hasattr(node, "get_decorators"):
                    for dec in node.get_decorators():
                        dec_name = None
                        dec_args = None
                        if hasattr(dec, "children") and len(dec.children) > 1:
                            # Dec structure: '@' name ['(' args ')'] newline
                            name_node = dec.children[1]
                            if hasattr(name_node, "value"):
                                dec_name = name_node.value
                            elif hasattr(name_node, "get_code"):
                                # Complex decorator like @module.decorator
                                dec_name = name_node.get_code().strip()
                            # Check for arguments
                            if len(dec.children) > 2:
                                for child in dec.children[2:]:
                                    if hasattr(child, "get_code"):
                                        code = child.get_code().strip()
                                        if code.startswith("(") and code.endswith(")"):
                                            dec_args = code[1:-1]
                                            break
                        if dec_name:
                            decorators.append({
                                "name": dec_name,
                                "arguments": dec_args,
                                "line": dec.start_pos[0]
                            })
        except Exception:
            pass
        return decorators

    def _name_to_definition(
        self, name: Name, file_path: Path
    ) -> tuple[Definition, list[Decorator]] | None:
        """Convert a Jedi Name to a Definition and its Decorators."""
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

            # Get end position
            end_line, end_col = self._get_definition_range(name)

            # Derive parent_full_name from full_name
            parent_full_name = None
            if full_name and "." in full_name:
                parent_full_name = full_name.rsplit(".", 1)[0]

            # Compute search text for FTS
            search_text = make_search_text(name.name, full_name, docstring)

            definition = Definition(
                name=name.name,
                full_name=full_name,
                type=def_type,
                line=line,
                column=column,
                end_line=end_line,
                end_column=end_col,
                signature=signature,
                docstring=docstring,
                parent_full_name=parent_full_name,
                is_public=not name.name.startswith("_"),
                search_text=search_text,
            )

            # Extract decorators for functions and classes
            # Store the parent definition's full_name so we can link after insertion
            decorators = []
            if def_type in ("function", "class"):
                for dec_info in self._extract_decorators(name):
                    dec = Decorator(
                        name=dec_info["name"],
                        full_name=full_name,  # Store parent's full_name temporarily
                        arguments=dec_info.get("arguments"),
                        line=dec_info["line"],
                    )
                    decorators.append(dec)

            return definition, decorators
        except Exception:
            return None

    def _extract_references(
        self, script: jedi.Script, file_path: Path, source: str, resolve_refs: bool = False
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

                # Resolve reference target if requested
                target_full_name = None
                target_module_path = None
                if resolve_refs:
                    try:
                        resolved = name.goto()
                        if resolved:
                            target = resolved[0]
                            target_full_name = target.full_name
                            if target.module_path:
                                target_module_path = str(target.module_path)
                    except Exception:
                        pass

                # Detect call sites by checking if '(' follows the name
                is_call = False
                if context and column is not None:
                    # Find position after the name in the context line
                    # Note: column is 0-indexed, context is stripped
                    full_line = source_lines[line - 1] if 0 < line <= len(source_lines) else ""
                    after_pos = column + len(name.name)
                    if after_pos < len(full_line):
                        after_name = full_line[after_pos:]
                        is_call = after_name.lstrip().startswith("(")

                yield Reference(
                    name=name.name,
                    line=line,
                    column=column,
                    context=context,
                    target_full_name=target_full_name,
                    target_module_path=target_module_path,
                    is_call=is_call,
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
