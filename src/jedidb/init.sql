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

-- Note: class_bases table is loaded conditionally in Python (open_parquet)
-- to handle older indexes that don't have this table

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
