# JediDB SQL Query Patterns

Common SQL queries for exploring Python codebases with JediDB.

## Finding Definitions

### By Name Pattern

```sql
-- Functions starting with "get"
SELECT name, full_name, file_path FROM functions
WHERE name LIKE 'get%' LIMIT 20;

-- Classes ending with "Error"
SELECT name, full_name, file_path FROM classes
WHERE name LIKE '%Error';

-- Definitions in a specific module
SELECT name, type, line FROM definitions_with_path
WHERE file_path LIKE '%mymodule%';
```

### By Type

```sql
-- All public classes
SELECT name, full_name FROM definitions
WHERE type = 'class' AND is_public = TRUE;

-- All parameters (useful for finding common arg names)
SELECT name, COUNT(*) as usage_count FROM definitions
WHERE type = 'param'
GROUP BY name ORDER BY usage_count DESC LIMIT 20;
```

## Call Graph Queries

### Who Calls X?

```sql
-- Find all callers of a function
SELECT c.caller_full_name, f.path, c.line
FROM calls c
JOIN files f ON c.file_id = f.id
WHERE c.callee_full_name = 'mymodule.my_function';

-- Find callers excluding test files
SELECT c.caller_full_name, f.path, c.line
FROM calls c
JOIN files f ON c.file_id = f.id
WHERE c.callee_full_name = 'mymodule.my_function'
  AND f.path NOT LIKE '%test%';
```

### What Does X Call?

```sql
-- Direct calls from a function
SELECT DISTINCT callee_full_name, callee_name
FROM calls
WHERE caller_full_name = 'mymodule.MyClass.__init__'
ORDER BY call_order;

-- Calls with source context
SELECT callee_name, line, context
FROM calls
WHERE caller_full_name = 'mymodule.process'
ORDER BY call_order;
```

### Call Chains

```sql
-- Two-level call chain: A calls B, B calls C
SELECT a.caller_full_name AS source,
       a.callee_full_name AS intermediate,
       b.callee_full_name AS target
FROM calls a
JOIN calls b ON a.callee_full_name = b.caller_full_name
WHERE a.caller_full_name = 'mymodule.start'
LIMIT 50;
```

## Inheritance Queries

### Find Subclasses

```sql
-- Classes inheriting from a base
SELECT d.full_name, f.path
FROM class_bases cb
JOIN definitions d ON cb.class_id = d.id
JOIN files f ON d.file_id = f.id
WHERE cb.base_full_name = 'django.db.models.Model';

-- Or using the view
SELECT class_full_name, file_path
FROM class_hierarchy
WHERE base_full_name LIKE '%Model';
```

### Find Base Classes

```sql
-- What does a class inherit from?
SELECT base_name, base_full_name, position
FROM class_bases cb
JOIN definitions d ON cb.class_id = d.id
WHERE d.full_name = 'mymodule.MyClass'
ORDER BY position;
```

### Multi-Level Inheritance

```sql
-- Grandparent classes (two levels up)
WITH direct_bases AS (
    SELECT cb.base_full_name
    FROM class_bases cb
    JOIN definitions d ON cb.class_id = d.id
    WHERE d.full_name = 'mymodule.MyClass'
)
SELECT cb.base_full_name AS grandparent
FROM class_bases cb
JOIN definitions d ON cb.class_id = d.id
WHERE d.full_name IN (SELECT base_full_name FROM direct_bases);
```

## Decorator Queries

### Find Decorated Functions

```sql
-- All @property methods
SELECT full_name, file_path
FROM decorated_definitions
WHERE decorator_name = 'property';

-- All @pytest.fixture functions
SELECT full_name, file_path
FROM decorated_definitions
WHERE decorator_name = 'fixture';

-- Functions with @staticmethod or @classmethod
SELECT full_name, decorator_name, file_path
FROM decorated_definitions
WHERE decorator_name IN ('staticmethod', 'classmethod');
```

### Find Functions by Decorator Pattern

```sql
-- Decorators with arguments
SELECT full_name, decorator_name, decorator_args
FROM decorated_definitions
WHERE decorator_args IS NOT NULL AND decorator_args != '';

-- Custom app decorators
SELECT full_name, decorator_name
FROM decorated_definitions
WHERE decorator_name LIKE 'my_app%';
```

## Code Quality Queries

### Large Functions

```sql
-- Longest functions by line count
SELECT full_name, (end_line - line) AS lines, file_path
FROM definitions_with_path
WHERE type = 'function' AND end_line IS NOT NULL
ORDER BY lines DESC LIMIT 20;
```

### Missing Docstrings

```sql
-- Public functions without docstrings
SELECT full_name, file_path, line
FROM functions
WHERE is_public = TRUE AND (docstring IS NULL OR docstring = '')
LIMIT 50;
```

### Dead Code Candidates

```sql
-- Definitions with no incoming references
SELECT d.full_name, d.type, f.path
FROM definitions d
JOIN files f ON d.file_id = f.id
LEFT JOIN refs r ON r.target_full_name = d.full_name
WHERE r.id IS NULL
  AND d.type IN ('function', 'class')
  AND d.is_public = TRUE
LIMIT 50;
```

### Complexity Indicators

```sql
-- Classes with the most methods
SELECT parent_full_name AS class_name, COUNT(*) AS method_count
FROM definitions
WHERE type = 'function' AND parent_full_name IS NOT NULL
GROUP BY parent_full_name
ORDER BY method_count DESC LIMIT 20;

-- Files with the most definitions
SELECT f.path, COUNT(*) AS definition_count
FROM definitions d
JOIN files f ON d.file_id = f.id
GROUP BY f.path
ORDER BY definition_count DESC LIMIT 20;
```

## Module Structure

### Nested Definitions

```sql
-- Inner classes
SELECT d.full_name, d.parent_full_name
FROM definitions d
WHERE d.type = 'class' AND d.parent_full_name IS NOT NULL;

-- Nested functions (closures)
SELECT d.full_name, d.parent_full_name
FROM definitions d
WHERE d.type = 'function'
  AND d.parent_full_name IS NOT NULL
  AND d.parent_full_name NOT LIKE '%.%.__init__';
```

### Import Analysis

```sql
-- Most imported modules
SELECT module, COUNT(*) AS import_count
FROM imports
GROUP BY module
ORDER BY import_count DESC LIMIT 20;

-- Find all files importing a specific module
SELECT DISTINCT file_path
FROM imports_with_path
WHERE module = 'json';
```

## Filtering Patterns

### Exclude Tests

```sql
-- Production code only
SELECT name, full_name FROM definitions_with_path
WHERE file_path NOT LIKE '%test%'
  AND file_path NOT LIKE '%tests%'
  AND type = 'function';
```

### Include Only Tests

```sql
-- Test functions only
SELECT full_name, file_path
FROM functions
WHERE file_path LIKE '%test%'
  AND name LIKE 'test_%';
```

### Specific Directory

```sql
-- Definitions in src/core/
SELECT name, type, line FROM definitions_with_path
WHERE file_path LIKE 'src/core/%';
```

## Statistics

### Overview

```sql
-- Definitions by type
SELECT type, COUNT(*) AS count
FROM definitions
GROUP BY type ORDER BY count DESC;

-- Files by size (definitions per file)
SELECT f.path, COUNT(d.id) AS definitions
FROM files f
LEFT JOIN definitions d ON d.file_id = f.id
GROUP BY f.path
ORDER BY definitions DESC LIMIT 20;
```

### Reference Counts

```sql
-- Most referenced functions
SELECT target_full_name, COUNT(*) AS ref_count
FROM refs
WHERE target_full_name IS NOT NULL
GROUP BY target_full_name
ORDER BY ref_count DESC LIMIT 20;
```
