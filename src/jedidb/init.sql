-- JediDB initialization SQL
-- This file is executed when opening a parquet-backed database.
-- The 'parquet_dir' variable must be set before running this script.

-- Create tables from parquet files (preserve IDs to maintain foreign key relationships)
CREATE OR REPLACE TABLE files AS
SELECT * FROM read_parquet(getvariable('parquet_dir') || '/files.parquet');

CREATE OR REPLACE TABLE definitions AS
SELECT * FROM read_parquet(getvariable('parquet_dir') || '/definitions.parquet');

CREATE OR REPLACE TABLE refs AS
SELECT * FROM read_parquet(getvariable('parquet_dir') || '/refs.parquet');

CREATE OR REPLACE TABLE imports AS
SELECT * FROM read_parquet(getvariable('parquet_dir') || '/imports.parquet');

CREATE OR REPLACE TABLE decorators AS
SELECT * FROM read_parquet(getvariable('parquet_dir') || '/decorators.parquet');

-- Note: class_bases is created in Python (open_parquet) to handle older indexes
-- that don't have this table. A placeholder is created here for view definitions.
CREATE TABLE IF NOT EXISTS class_bases (
    id INTEGER PRIMARY KEY,
    class_id INTEGER NOT NULL,
    base_name TEXT NOT NULL,
    base_full_name TEXT,
    base_id INTEGER,
    position INTEGER NOT NULL
);

CREATE OR REPLACE TABLE calls AS
SELECT * FROM read_parquet(getvariable('parquet_dir') || '/calls.parquet');

-- Install and load FTS extension
INSTALL fts;
LOAD fts;

-- Create FTS index on definitions (search_text contains original + split tokens + docstring)
PRAGMA create_fts_index(
    'definitions',
    'id',
    'search_text',
    stemmer = 'none',
    stopwords = 'none'
);

-- Convenience views for common queries

-- Definitions with file path included
CREATE OR REPLACE VIEW definitions_with_path AS
SELECT d.*, f.path AS file_path
FROM definitions d
JOIN files f ON d.file_id = f.id;

-- Calls with file paths for both caller and callee
CREATE OR REPLACE VIEW calls_with_context AS
SELECT
    c.*,
    f.path AS file_path,
    caller_def.name AS caller_name,
    callee_def.name AS callee_name_resolved,
    callee_file.path AS callee_file_path
FROM calls c
JOIN files f ON c.file_id = f.id
LEFT JOIN definitions caller_def ON c.caller_id = caller_def.id
LEFT JOIN definitions callee_def ON c.callee_id = callee_def.id
LEFT JOIN files callee_file ON callee_def.file_id = callee_file.id;

-- Classes with their base classes (flattened)
CREATE OR REPLACE VIEW class_hierarchy AS
SELECT
    d.id AS class_id,
    d.name AS class_name,
    d.full_name AS class_full_name,
    f.path AS file_path,
    cb.base_name,
    cb.base_full_name,
    cb.position AS base_position
FROM definitions d
JOIN files f ON d.file_id = f.id
LEFT JOIN class_bases cb ON cb.class_id = d.id
WHERE d.type = 'class';

-- Functions/methods with their decorators (one row per decorator)
CREATE OR REPLACE VIEW decorated_definitions AS
SELECT
    d.id AS definition_id,
    d.name,
    d.full_name,
    d.type,
    d.line,
    f.path AS file_path,
    dec.name AS decorator_name,
    dec.arguments AS decorator_args
FROM definitions d
JOIN files f ON d.file_id = f.id
JOIN decorators dec ON dec.definition_id = d.id;

-- References with file paths
CREATE OR REPLACE VIEW refs_with_path AS
SELECT r.*, f.path AS file_path
FROM refs r
JOIN files f ON r.file_id = f.id;

-- Imports with file paths
CREATE OR REPLACE VIEW imports_with_path AS
SELECT i.*, f.path AS file_path
FROM imports i
JOIN files f ON i.file_id = f.id;

-- Functions and methods only (common filter)
CREATE OR REPLACE VIEW functions AS
SELECT d.*, f.path AS file_path
FROM definitions d
JOIN files f ON d.file_id = f.id
WHERE d.type = 'function';

-- Classes only
CREATE OR REPLACE VIEW classes AS
SELECT d.*, f.path AS file_path
FROM definitions d
JOIN files f ON d.file_id = f.id
WHERE d.type = 'class';
