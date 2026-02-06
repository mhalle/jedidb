"""Jedi-based code analyzer for JediDB."""

import ast
import logging
from pathlib import Path
from typing import Generator

import jedi
from jedi.api.classes import Name

from jedidb.core.models import ClassBase, Decorator, Definition, Import, Reference
from jedidb.utils import get_context_lines, make_search_text

logger = logging.getLogger("jedidb.analyzer")


class CallOrderVisitor(ast.NodeVisitor):
    """AST visitor to track call order and depth for call sites."""

    def __init__(self, source_lines: list[str] | None = None):
        self.call_info: dict[tuple[int, int], tuple[int, int]] = {}  # (line, col) -> (order, depth)
        self.call_counter = 0
        self.call_depth = 0
        self.source_lines = source_lines or []

    def visit_Call(self, node: ast.Call):
        self.call_depth += 1
        current_depth = self.call_depth

        # Visit nested calls first (post-order traversal)
        self.generic_visit(node)

        self.call_counter += 1
        # Get the position of the function being called
        # For method calls like obj.method(), we want the position of 'method'
        func = node.func
        if isinstance(func, ast.Attribute):
            # obj.method() or obj.attr.method() - compute position of attribute name
            # AST gives us col_offset of the whole expression (e.g., 'self' in 'self.execute')
            # We need to find where the attribute name starts
            line = func.lineno
            attr_name = func.attr
            # Use end_col_offset if available (Python 3.8+), otherwise search in source
            if hasattr(func, "end_col_offset") and func.end_col_offset is not None:
                # end_col_offset points to the end of the attribute name
                attr_col = func.end_col_offset - len(attr_name)
                self.call_info[(line, attr_col)] = (self.call_counter, current_depth)
            elif self.source_lines and 0 < line <= len(self.source_lines):
                # Fallback: find the last dot before the opening paren in the source
                source_line = self.source_lines[line - 1]
                # Find the opening paren
                paren_pos = source_line.find("(", func.col_offset)
                if paren_pos >= 0:
                    # Find the last dot before the paren
                    search_region = source_line[func.col_offset:paren_pos]
                    last_dot = search_region.rfind(".")
                    if last_dot >= 0:
                        attr_col = func.col_offset + last_dot + 1
                        self.call_info[(line, attr_col)] = (self.call_counter, current_depth)
                    else:
                        self.call_info[(line, func.col_offset)] = (self.call_counter, current_depth)
                else:
                    self.call_info[(line, func.col_offset)] = (self.call_counter, current_depth)
            else:
                self.call_info[(func.lineno, func.col_offset)] = (self.call_counter, current_depth)
        elif isinstance(func, ast.Name):
            # simple_func() - use name position
            self.call_info[(func.lineno, func.col_offset)] = (self.call_counter, current_depth)
        else:
            # Other cases (subscript calls, etc.)
            self.call_info[(node.lineno, node.col_offset)] = (self.call_counter, current_depth)

        self.call_depth -= 1
        return node


class Analyzer:
    """Wraps Jedi to extract code analysis information."""

    def __init__(self, project_path: Path | str | None = None, base_classes: bool = True):
        """Initialize the analyzer.

        Args:
            project_path: Optional project root for Jedi's project detection
            base_classes: Whether to extract class base classes (inheritance)
        """
        self.project_path = Path(project_path) if project_path else None
        self._project = None
        self.base_classes = base_classes

        if self.project_path:
            try:
                self._project = jedi.Project(path=str(self.project_path))
            except (OSError, ValueError) as e:
                logger.debug("Could not create Jedi project for %s: %s", self.project_path, e)

    def analyze_file(
        self, file_path: Path, resolve_refs: bool = False
    ) -> tuple[list[Definition], list[Reference], list[Import], list[Decorator], list[ClassBase]]:
        """Analyze a Python file and extract definitions, references, imports, decorators, and class bases.

        Args:
            file_path: Path to the Python file
            resolve_refs: Whether to resolve reference targets (enables call graph)

        Returns:
            Tuple of (definitions, references, imports, decorators, class_bases)
        """
        try:
            source = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            raise ValueError(f"Could not read file {file_path}: {e}") from e

        try:
            script = jedi.Script(source, path=str(file_path), project=self._project)
        except (ValueError, SyntaxError) as e:
            raise ValueError(f"Could not parse file {file_path}: {e}") from e

        definitions, decorators, class_bases = self._extract_definitions_and_decorators(script, file_path)
        references = list(self._extract_references(script, file_path, source, resolve_refs))
        imports = list(self._extract_imports(script, file_path))

        return definitions, references, imports, decorators, class_bases

    def _extract_definitions_and_decorators(
        self, script: jedi.Script, file_path: Path
    ) -> tuple[list[Definition], list[Decorator], list[ClassBase]]:
        """Extract all definitions, decorators, and class bases from a script."""
        definitions = []
        decorators = []
        class_bases = []

        try:
            names = script.get_names(all_scopes=True, definitions=True, references=False)
        except (AttributeError, ValueError) as e:
            logger.debug("Could not get definitions from script: %s", e)
            return definitions, decorators, class_bases

        for name in names:
            result = self._name_to_definition(name, file_path)
            if result:
                definition, decs = result
                definitions.append(definition)
                decorators.extend(decs)

                # Extract base classes for class definitions
                if self.base_classes and definition.type == "class":
                    bases = self._extract_base_classes(name, script)
                    class_bases.extend(bases)

        return definitions, decorators, class_bases

    def _get_definition_range(self, name: Name) -> tuple[int | None, int | None]:
        """Return (end_line, end_col) using Jedi's public API."""
        try:
            end_pos = name.get_definition_end_position()
            if end_pos:
                return (end_pos[0], end_pos[1])
        except (AttributeError, TypeError) as e:
            logger.debug("Could not get definition end position for %s: %s", name.name, e)
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
        except AttributeError as e:
            # Expected when Jedi internal API changes - decorators are optional
            logger.debug("Could not extract decorators (Jedi internal API): %s", e)
        return decorators

    def _extract_base_classes(self, name: Name, script: jedi.Script) -> list[ClassBase]:
        """Extract base classes from a class definition."""
        bases = []
        try:
            internal = name._name
            if not hasattr(internal, 'tree_name'):
                return bases

            tree = internal.tree_name
            parent = tree.parent
            if not hasattr(parent, 'get_super_arglist'):
                return bases

            arglist = parent.get_super_arglist()
            if not arglist:
                return bases

            # Determine if arglist is a single base or comma-separated list
            # If arglist.type is 'arglist', it has multiple comma-separated children
            # Otherwise, arglist itself is the single base class
            if hasattr(arglist, 'type') and arglist.type == 'arglist':
                children = arglist.children
            else:
                children = [arglist]

            position = 0
            for child in children:
                # Skip commas
                if hasattr(child, 'value') and child.value == ',':
                    continue

                # Get the base class name - handle both simple names and dotted names
                base_name = None
                line, col = None, None

                if hasattr(child, 'type'):
                    if child.type == 'name':
                        # Simple name like "Enum"
                        base_name = child.value
                        line, col = child.start_pos
                    elif child.type in ('power', 'atom_expr'):
                        # Dotted name like "ast.NodeVisitor"
                        # Get the full code representation
                        base_name = child.get_code().strip()
                        # Find rightmost name for goto resolution (e.g., NodeVisitor in ast.NodeVisitor)
                        rightmost = child
                        while hasattr(rightmost, 'children') and rightmost.children:
                            last_child = rightmost.children[-1]
                            if hasattr(last_child, 'type') and last_child.type == 'trailer':
                                # trailer has ['.', name] - get the name
                                if len(last_child.children) >= 2:
                                    rightmost = last_child.children[-1]
                            else:
                                break
                        line, col = rightmost.start_pos
                    elif child.type == 'argument':
                        # Skip keyword arguments like metaclass=X
                        continue

                if not base_name:
                    continue

                # Resolve base class via goto
                base_full_name = None
                try:
                    defs = script.goto(line, col)
                    if defs:
                        base_full_name = defs[0].full_name
                except (AttributeError, IndexError) as e:
                    logger.debug("Could not resolve base class %s: %s", base_name, e)

                bases.append(ClassBase(
                    base_name=base_name,
                    base_full_name=base_full_name,
                    position=position,
                    class_full_name=name.full_name,  # For linking later
                ))
                position += 1
        except AttributeError as e:
            # Expected when Jedi internal API changes - base classes are optional
            logger.debug("Could not extract base classes (Jedi internal API): %s", e)

        return bases

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
                except (AttributeError, IndexError, TypeError) as e:
                    logger.debug("Could not get signature for %s: %s", name.name, e)

            # Get docstring
            docstring = None
            try:
                docstring = name.docstring(raw=True)
                if docstring:
                    docstring = docstring.strip()
                    if not docstring:
                        docstring = None
            except (AttributeError, TypeError) as e:
                logger.debug("Could not get docstring for %s: %s", name.name, e)

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
        except (AttributeError, TypeError, ValueError) as e:
            logger.debug("Could not convert Jedi name to definition: %s", e)
            return None

    def _extract_references(
        self, script: jedi.Script, file_path: Path, source: str, resolve_refs: bool = False
    ) -> Generator[Reference, None, None]:
        """Extract all references from a script."""
        try:
            names = script.get_names(all_scopes=True, definitions=False, references=True)
        except (AttributeError, ValueError) as e:
            logger.debug("Could not get references from script: %s", e)
            return

        source_lines = source.splitlines()

        # Build call order/depth map using AST
        call_info: dict[tuple[int, int], tuple[int, int]] = {}
        try:
            tree = ast.parse(source)
            visitor = CallOrderVisitor(source_lines)
            visitor.visit(tree)
            call_info = visitor.call_info
        except SyntaxError:
            pass  # If AST parsing fails, we just won't have order/depth info

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
                    except (AttributeError, IndexError) as e:
                        logger.debug("Could not resolve reference target for %s: %s", name.name, e)

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

                # Look up call order and depth from AST analysis
                call_order = 0
                call_depth = 0
                if is_call and (line, column) in call_info:
                    call_order, call_depth = call_info[(line, column)]

                yield Reference(
                    name=name.name,
                    line=line,
                    column=column,
                    context=context,
                    target_full_name=target_full_name,
                    target_module_path=target_module_path,
                    is_call=is_call,
                    call_order=call_order,
                    call_depth=call_depth,
                )
            except (AttributeError, TypeError, ValueError) as e:
                logger.debug("Could not process reference: %s", e)
                continue

    def _extract_imports(
        self, script: jedi.Script, file_path: Path
    ) -> Generator[Import, None, None]:
        """Extract all imports from a script."""
        try:
            names = script.get_names(all_scopes=False, definitions=True, references=False)
        except (AttributeError, ValueError) as e:
            logger.debug("Could not get imports from script: %s", e)
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
            except (AttributeError, TypeError) as e:
                logger.debug("Could not process import: %s", e)
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
        except (OSError, UnicodeDecodeError, ValueError, AttributeError) as e:
            logger.debug("Could not get completions: %s", e)
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
        except (OSError, UnicodeDecodeError, ValueError, AttributeError) as e:
            logger.debug("Could not get signatures: %s", e)
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
        except (OSError, UnicodeDecodeError, ValueError, AttributeError) as e:
            logger.debug("Could not get goto definition: %s", e)
            return []
