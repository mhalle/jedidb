"""Full-text search interface for JediDB."""

import logging

import duckdb

from jedidb.core.database import Database
from jedidb.core.models import Definition, Reference, SearchResult
from jedidb.utils import split_identifier

logger = logging.getLogger("jedidb.search")


class SearchEngine:
    """Full-text search interface for definitions."""

    def __init__(self, db: Database):
        """Initialize search engine.

        Args:
            db: Database instance
        """
        self.db = db

    def search(
        self,
        query: str,
        type: str | None = None,
        limit: int = 20,
        include_private: bool = False,
    ) -> list[SearchResult]:
        """Search definitions using hybrid search.

        Uses LIKE on search_text for wildcard queries (containing *),
        and FTS for phrase/word queries.

        Args:
            query: Search query string (use * for wildcards, e.g., 'get*', '*Parser')
            type: Filter by definition type (function, class, variable, etc.)
            limit: Maximum number of results
            include_private: Include private definitions (starting with _)

        Returns:
            List of SearchResult objects ordered by relevance
        """
        # Wildcard search: use LIKE on search_text
        if "*" in query:
            return self._wildcard_search(query, type, limit, include_private)

        # Word/phrase search: try FTS first, fall back to LIKE
        if not self.db._fts_available:
            return self._like_search(query, type, limit, include_private)

        try:
            return self._fts_search(query, type, limit, include_private)
        except duckdb.Error as e:
            logger.debug("FTS search failed, falling back to LIKE: %s", e)
            return self._like_search(query, type, limit, include_private)

    def _convert_wildcard_pattern(self, pattern: str) -> str:
        """Convert user wildcard pattern to SQL LIKE pattern.

        - Escapes literal % and _ characters (SQL LIKE wildcards)
        - Converts * to % (user-friendly wildcard)
        - Lowercases for case-insensitive matching

        Args:
            pattern: User search pattern with * wildcards

        Returns:
            SQL LIKE pattern
        """
        # Lowercase for case-insensitive search
        pattern = pattern.lower()
        # Escape SQL LIKE special characters (% and _)
        pattern = pattern.replace("%", r"\%").replace("_", r"\_")
        # Convert user wildcards (*) to SQL wildcards (%)
        pattern = pattern.replace("*", "%")
        return pattern

    def _wildcard_search(
        self,
        query: str,
        type: str | None,
        limit: int,
        include_private: bool,
    ) -> list[SearchResult]:
        """Perform wildcard search using LIKE on name column.

        Supports * as wildcard: 'get*' (prefix), '*Parser' (suffix), 'get*Value' (pattern).
        Escapes SQL wildcards (% and _) so they match literally.
        """
        search_term = self._convert_wildcard_pattern(query)

        # For ranking, extract the non-wildcard prefix if it exists
        rank_prefix = query.split("*")[0].lower() if query.split("*")[0] else None

        sql = """
            SELECT
                d.id, d.file_id, d.name, d.full_name, d.type,
                d.line, d.col, d.end_line, d.end_col,
                d.signature, d.docstring, d.parent_id, d.is_public,
                f.path
            FROM definitions d
            JOIN files f ON d.file_id = f.id
            WHERE lower(d.name) LIKE ? ESCAPE '\\'
        """
        params: list = [search_term]

        if type:
            sql += " AND d.type = ?"
            params.append(type)

        if not include_private:
            sql += " AND d.is_public = TRUE"

        # Order by: exact prefix match first, then others
        if rank_prefix:
            sql += """
                ORDER BY
                    CASE
                        WHEN lower(d.name) = ? THEN 0
                        WHEN lower(d.name) LIKE ? ESCAPE '\\' THEN 1
                        ELSE 2
                    END,
                    d.name
                LIMIT ?
            """
            params.extend([rank_prefix, f"{rank_prefix}%", limit])
        else:
            sql += " ORDER BY d.name LIMIT ?"
            params.append(limit)

        results = self.db.execute(sql, params).fetchall()

        return [
            SearchResult(
                definition=Definition.from_row(r),
                score=1.0 if rank_prefix and r[2].lower() == rank_prefix else 0.5,
            )
            for r in results
        ]

    def _fts_search(
        self,
        query: str,
        type: str | None,
        limit: int,
        include_private: bool,
    ) -> list[SearchResult]:
        """Perform FTS search on search_text column."""
        # Ensure FTS is initialized
        self.db.init_fts()

        # Tokenize query for better FTS matching (handles camelCase, snake_case)
        tokenized_query = split_identifier(query)

        # Build query - FTS index is on search_text column
        sql = """
            SELECT
                d.id, d.file_id, d.name, d.full_name, d.type,
                d.line, d.col, d.end_line, d.end_col,
                d.signature, d.docstring, d.parent_id, d.is_public,
                f.path,
                fts_main_definitions.match_bm25(d.id, ?) as score
            FROM definitions d
            JOIN files f ON d.file_id = f.id
            WHERE fts_main_definitions.match_bm25(d.id, ?) IS NOT NULL
        """
        params = [tokenized_query, tokenized_query]

        if type:
            sql += " AND d.type = ?"
            params.append(type)

        if not include_private:
            sql += " AND d.is_public = TRUE"

        sql += " ORDER BY score DESC LIMIT ?"
        params.append(limit)

        results = self.db.execute(sql, params).fetchall()

        return [
            SearchResult(
                definition=Definition.from_row(r),
                score=r[14] if r[14] else 0.0,
            )
            for r in results
        ]

    def _like_search(
        self,
        query: str,
        type: str | None,
        limit: int,
        include_private: bool,
    ) -> list[SearchResult]:
        """Perform LIKE-based search as FTS fallback."""
        # Tokenize and lowercase for search_text matching
        tokenized = split_identifier(query)
        search_term = f"%{tokenized}%"

        sql = """
            SELECT
                d.id, d.file_id, d.name, d.full_name, d.type,
                d.line, d.col, d.end_line, d.end_col,
                d.signature, d.docstring, d.parent_id, d.is_public,
                f.path
            FROM definitions d
            JOIN files f ON d.file_id = f.id
            WHERE lower(d.search_text) LIKE ?
        """
        params = [search_term]

        if type:
            sql += " AND d.type = ?"
            params.append(type)

        if not include_private:
            sql += " AND d.is_public = TRUE"

        # Order by exact match first, then prefix match, then others
        sql += """
            ORDER BY
                CASE
                    WHEN lower(d.name) = ? THEN 0
                    WHEN lower(d.name) LIKE ? THEN 1
                    ELSE 2
                END,
                d.name
            LIMIT ?
        """
        params.extend([query.lower(), f"{query.lower()}%", limit])

        results = self.db.execute(sql, params).fetchall()

        return [
            SearchResult(
                definition=Definition.from_row(r),
                score=1.0 if r[2].lower() == query.lower() else 0.5,
            )
            for r in results
        ]

    def get_definition(self, name: str) -> Definition | None:
        """Get a definition by name or full name.

        Prefers actual definitions (with bodies) over imports.

        Args:
            name: Name or full name of the definition

        Returns:
            Definition object or None if not found
        """
        sql = """
            SELECT
                d.id, d.file_id, d.name, d.full_name, d.type,
                d.line, d.col, d.end_line, d.end_col,
                d.signature, d.docstring, d.parent_id, d.is_public,
                f.path
            FROM definitions d
            JOIN files f ON d.file_id = f.id
            WHERE d.full_name = ? OR d.name = ?
            ORDER BY
                CASE WHEN d.full_name = ? THEN 0 ELSE 1 END,
                COALESCE(d.end_line, d.line) - d.line DESC
            LIMIT 1
        """

        result = self.db.execute(sql, (name, name, name)).fetchone()

        if result:
            return Definition.from_row(result)
        return None

    def get_definition_by_id(self, def_id: int) -> Definition | None:
        """Get a definition by its ID.

        Args:
            def_id: Definition ID

        Returns:
            Definition object or None if not found
        """
        sql = """
            SELECT
                d.id, d.file_id, d.name, d.full_name, d.type,
                d.line, d.col, d.end_line, d.end_col,
                d.signature, d.docstring, d.parent_id, d.is_public,
                f.path
            FROM definitions d
            JOIN files f ON d.file_id = f.id
            WHERE d.id = ?
        """

        result = self.db.execute(sql, (def_id,)).fetchone()

        if result:
            return Definition.from_row(result)
        return None

    def find_references(self, name: str) -> list[Reference]:
        """Find all references to a definition by name or full name.

        If name contains a dot (qualified name), matches against target_full_name
        for precise results. Otherwise falls back to matching by short name.

        Args:
            name: Name or full name to find references for

        Returns:
            List of Reference objects
        """
        if "." in name:
            # Qualified name — search by resolved target for precision
            sql = """
                SELECT
                    r.id, r.file_id, r.definition_id, r.name,
                    r.line, r.col, r.context,
                    f.path
                FROM refs r
                JOIN files f ON r.file_id = f.id
                WHERE r.target_full_name = ?
                ORDER BY f.path, r.line
            """
        else:
            sql = """
                SELECT
                    r.id, r.file_id, r.definition_id, r.name,
                    r.line, r.col, r.context,
                    f.path
                FROM refs r
                JOIN files f ON r.file_id = f.id
                WHERE r.name = ?
                ORDER BY f.path, r.line
            """

        results = self.db.execute(sql, (name,)).fetchall()

        return [
            Reference(
                id=r[0],
                file_id=r[1],
                definition_id=r[2],
                name=r[3],
                line=r[4],
                column=r[5],
                context=r[6],
                file_path=r[7],
            )
            for r in results
        ]

    def list_definitions(
        self,
        type: str | None = None,
        file_path: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Definition]:
        """List definitions with optional filters.

        Args:
            type: Filter by definition type
            file_path: Filter by file path
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of Definition objects
        """
        sql = """
            SELECT
                d.id, d.file_id, d.name, d.full_name, d.type,
                d.line, d.col, d.end_line, d.end_col,
                d.signature, d.docstring, d.parent_id, d.is_public,
                f.path
            FROM definitions d
            JOIN files f ON d.file_id = f.id
            WHERE 1=1
        """
        params = []

        if type:
            sql += " AND d.type = ?"
            params.append(type)

        if file_path:
            sql += " AND f.path = ?"
            params.append(file_path)

        sql += " ORDER BY f.path, d.line LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        results = self.db.execute(sql, params).fetchall()

        return [Definition.from_row(r) for r in results]
