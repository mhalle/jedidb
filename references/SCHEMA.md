# JediDB Database Schema

JediDB stores indexed data in Parquet files queried via DuckDB.

## Tables

### files

Indexed source files with modification tracking.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| path | TEXT | Relative file path |
| hash | TEXT | File content hash |
| size | INTEGER | File size in bytes |
| modified_at | TIMESTAMP | File modification time |
| indexed_at | TIMESTAMP | When file was indexed |

### definitions

Functions, classes, variables, parameters, and modules.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| file_id | INTEGER | FK to files.id |
| name | TEXT | Simple name (e.g., `my_function`) |
| full_name | TEXT | Qualified name (e.g., `mymodule.MyClass.my_function`) |
| type | TEXT | `function`, `class`, `variable`, `param`, `module` |
| line | INTEGER | Start line (1-indexed) |
| col | INTEGER | Start column |
| end_line | INTEGER | End line (nullable) |
| end_col | INTEGER | End column (nullable) |
| signature | TEXT | Function/method signature |
| docstring | TEXT | Docstring content |
| parent_id | INTEGER | FK to parent definition |
| parent_full_name | TEXT | Parent's full_name |
| is_public | BOOLEAN | FALSE if name starts with `_` |
| search_text | TEXT | Tokenized text for FTS |

### refs

References/usages of names in code.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| file_id | INTEGER | FK to files.id |
| definition_id | INTEGER | FK to enclosing definition |
| name | TEXT | Referenced name |
| line | INTEGER | Line number |
| col | INTEGER | Column number |
| context | TEXT | Source line containing reference |
| target_full_name | TEXT | Resolved target (if resolved) |
| target_module_path | TEXT | Target's module path |
| is_call | BOOLEAN | TRUE if this is a function call |
| call_order | INTEGER | Execution order within caller |
| call_depth | INTEGER | Nesting depth (1=top-level) |

### imports

Import statements.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| file_id | INTEGER | FK to files.id |
| module | TEXT | Imported module name |
| name | TEXT | Imported name (for `from X import Y`) |
| alias | TEXT | Alias (for `import X as Y`) |
| line | INTEGER | Line number |

### decorators

Decorators on functions/classes.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| definition_id | INTEGER | FK to definitions.id |
| name | TEXT | Decorator name (e.g., `property`) |
| full_name | TEXT | Qualified decorator name |
| arguments | TEXT | Decorator arguments as string |
| line | INTEGER | Line number |

### class_bases

Class inheritance relationships.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| class_id | INTEGER | FK to definitions.id (the class) |
| base_name | TEXT | Base class name |
| base_full_name | TEXT | Qualified base class name |
| base_id | INTEGER | FK to definitions.id (if resolved) |
| position | INTEGER | Position in base class list (0-indexed) |

### calls

Call graph (caller -> callee relationships).

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| file_id | INTEGER | FK to files.id |
| caller_full_name | TEXT | Calling function's full_name |
| caller_id | INTEGER | FK to definitions.id |
| callee_full_name | TEXT | Called function's full_name (if resolved) |
| callee_name | TEXT | Called function's simple name |
| callee_id | INTEGER | FK to definitions.id (if resolved) |
| line | INTEGER | Call site line number |
| col | INTEGER | Call site column |
| context | TEXT | Source line containing call |
| call_order | INTEGER | Execution order within caller |
| call_depth | INTEGER | Nesting depth (1=top-level) |

## Convenience Views

JediDB creates these views at runtime for common queries.

### definitions_with_path

All definitions with file path included.

```sql
SELECT d.*, f.path AS file_path
FROM definitions d JOIN files f ON d.file_id = f.id
```

### functions

Functions and methods only.

```sql
SELECT d.*, f.path AS file_path
FROM definitions d JOIN files f ON d.file_id = f.id
WHERE d.type = 'function'
```

### classes

Classes only.

```sql
SELECT d.*, f.path AS file_path
FROM definitions d JOIN files f ON d.file_id = f.id
WHERE d.type = 'class'
```

### refs_with_path

References with file path.

```sql
SELECT r.*, f.path AS file_path
FROM refs r JOIN files f ON r.file_id = f.id
```

### imports_with_path

Imports with file path.

```sql
SELECT i.*, f.path AS file_path
FROM imports i JOIN files f ON i.file_id = f.id
```

### calls_with_context

Calls with file paths for caller and callee.

```sql
SELECT c.*, f.path AS file_path,
       caller_def.name AS caller_name,
       callee_def.name AS callee_name_resolved,
       callee_file.path AS callee_file_path
FROM calls c
JOIN files f ON c.file_id = f.id
LEFT JOIN definitions caller_def ON c.caller_id = caller_def.id
LEFT JOIN definitions callee_def ON c.callee_id = callee_def.id
LEFT JOIN files callee_file ON callee_def.file_id = callee_file.id
```

### class_hierarchy

Classes with their base classes (one row per base).

```sql
SELECT d.id AS class_id, d.name AS class_name, d.full_name AS class_full_name,
       f.path AS file_path, cb.base_name, cb.base_full_name, cb.position
FROM definitions d
JOIN files f ON d.file_id = f.id
LEFT JOIN class_bases cb ON cb.class_id = d.id
WHERE d.type = 'class'
```

### decorated_definitions

Definitions with decorators (one row per decorator).

```sql
SELECT d.id AS definition_id, d.name, d.full_name, d.type, d.line,
       f.path AS file_path, dec.name AS decorator_name, dec.arguments AS decorator_args
FROM definitions d
JOIN files f ON d.file_id = f.id
JOIN decorators dec ON dec.definition_id = d.id
```

## Key Joins

| Relationship | Join |
|--------------|------|
| Definition's file | `definitions.file_id = files.id` |
| Call's caller | `calls.caller_id = definitions.id` |
| Call's callee | `calls.callee_id = definitions.id` |
| Decorator's target | `decorators.definition_id = definitions.id` |
| Class's bases | `class_bases.class_id = definitions.id` |
| Reference's file | `refs.file_id = files.id` |
| Import's file | `imports.file_id = files.id` |
