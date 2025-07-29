"""
SQLite3 to PostgreSQL syntax converter.
Utility functions to convert SQLite3 SQL statements to PostgreSQL syntax.
"""
import logging
import re
from typing import Dict, List, Optional, Tuple, Union, Any

# Configure module logger
logger = logging.getLogger(__name__)

class SQLiteToPostgreSQLConverter:
    """
    Converter class to transform SQLite SQL statements to PostgreSQL compatible syntax.
    
    This class handles the differences between SQLite and PostgreSQL including:
    - Data type mapping
    - SQLite AUTOINCREMENT to PostgreSQL SERIAL
    - PRAGMA statements to appropriate PostgreSQL alternatives
    - Function name differences (e.g., IFNULL vs COALESCE)
    - Quote style standardization (' vs ")
    - RETURNING clause addition for data manipulation operations
    - Pagination syntax differences (LIMIT/OFFSET)
    """
    
    # Mapping of SQLite data types to PostgreSQL types
    TYPE_MAPPING = {
        'INTEGER PRIMARY KEY AUTOINCREMENT': 'SERIAL PRIMARY KEY',
        'INTEGER PRIMARY KEY': 'SERIAL PRIMARY KEY',
        'INTEGER': 'INTEGER',
        'REAL': 'DOUBLE PRECISION',
        'TEXT': 'TEXT',
        'BLOB': 'BYTEA',
        'BOOLEAN': 'BOOLEAN',
        'TIMESTAMP': 'TIMESTAMP',
        'DATETIME': 'TIMESTAMP',
        'DATE': 'DATE',
        'TIME': 'TIME',
    }
    
    # Mapping of SQLite functions to PostgreSQL equivalents
    FUNCTION_MAPPING = {
        'IFNULL': 'COALESCE',
        'strftime': 'to_char',
        'datetime': 'to_timestamp',
        'random()': 'random()',
        'changes()': 'pg_affected_rows()',
        'total_changes()': '(SELECT sum(pg_total_relation_size(c.oid)) FROM pg_class c)',
        'last_insert_rowid()': 'lastval()'
    }
    
    @staticmethod
    def convert_sql(sql: str) -> str:
        """
        Convert a SQLite SQL statement to PostgreSQL syntax.
        
        Args:
            sql (str): SQLite SQL statement
            
        Returns:
            str: PostgreSQL compatible SQL statement
        """
        # Keep original for logging
        original_sql = sql
        
        # Handle SQLite's "INSERT OR REPLACE" syntax (convert to PostgreSQL "ON CONFLICT DO UPDATE")
        if "INSERT OR REPLACE" in sql.upper():
            # Remove the OR REPLACE part
            sql = sql.replace("OR REPLACE", "")
            # Extract table name
            table_match = re.search(r'INTO\s+([^\s(]+)', sql, re.IGNORECASE)
            if table_match:
                table_name = table_match.group(1)
                # Add ON CONFLICT clause for UPSERT
                if 'ON CONFLICT' not in sql.upper():
                    sql = sql.rstrip(';')
                    sql += f" ON CONFLICT (token_address, chain_id) DO UPDATE SET "
                    # Update all columns except the primary key
                    sql += "token_symbol = EXCLUDED.token_symbol, "
                    sql += "token_name = EXCLUDED.token_name, "
                    sql += "token_decimals = EXCLUDED.token_decimals;"
        
        # Handle SQLite's "INSERT OR IGNORE" syntax (convert to PostgreSQL "ON CONFLICT DO NOTHING")
        elif "INSERT OR IGNORE" in sql.upper():
            # Remove the OR IGNORE part
            sql = sql.replace("OR IGNORE", "")
            # Add ON CONFLICT DO NOTHING
            if 'ON CONFLICT' not in sql.upper():
                sql = sql.rstrip(';')
                sql += " ON CONFLICT DO NOTHING;"
        
        # Convert SQLite parameter placeholders (?) to psycopg2 placeholders (%s)
        # psycopg2 handles the parameter substitution internally
        processed_sql = ""
        
        # Process SQL one character at a time to handle ? placeholders safely
        i = 0
        in_string = False
        string_char = None
        
        while i < len(sql):
            char = sql[i]
            
            # Handle string literals
            if char in ["'", '"'] and (i == 0 or sql[i-1] != '\\'):
                if not in_string:
                    in_string = True
                    string_char = char
                elif char == string_char:
                    in_string = False
                    string_char = None
                processed_sql += char
            elif char == '?' and not in_string:
                # Replace ? with %s for psycopg2, but only if it's not in a string
                processed_sql += "%s"
            else:
                processed_sql += char
            
            i += 1
        
        sql = processed_sql
        
        # Handle SQLite ALTER TABLE statements differently for PostgreSQL
        # PostgreSQL has different syntax for ALTER TABLE ADD CONSTRAINT
        alter_table_match = re.search(
            r"ALTER\s+TABLE\s+(\w+)\s+ADD\s+CONSTRAINT\s+(\w+)\s+FOREIGN\s+KEY\s+\(([^)]+)\)\s+REFERENCES\s+(\w+)\(([^)]+)\)(\s+ON\s+DELETE\s+CASCADE)?",
            sql, 
            re.IGNORECASE
        )
        if alter_table_match:
            table, constraint, column, ref_table, ref_column, on_delete = alter_table_match.groups()
            on_delete = on_delete or ""  # Use empty string if on_delete is None
            # For PostgreSQL, it's better to use the ALTER TABLE ADD CONSTRAINT syntax
            # directly rather than the SQLite-style syntax
            sql = f"ALTER TABLE {table} ADD CONSTRAINT {constraint} FOREIGN KEY ({column}) REFERENCES {ref_table}({ref_column}){on_delete};"
            return sql
        
        # Handle case conversion
        # SQLite is case-insensitive but PostgreSQL is case-sensitive for identifiers
        # This is a complex issue but we'll assume standard SQL casing conventions
        
        # Replace SQLite specific types with PostgreSQL types
        for sqlite_type, pg_type in SQLiteToPostgreSQLConverter.TYPE_MAPPING.items():
            pattern = re.compile(r'\b' + re.escape(sqlite_type) + r'\b', re.IGNORECASE)
            sql = pattern.sub(pg_type, sql)
            
        # Convert AUTOINCREMENT to SERIAL if not already handled by type mapping
        sql = re.sub(r'AUTOINCREMENT', 'SERIAL', sql, flags=re.IGNORECASE)
        
        # Convert SQLite functions to PostgreSQL equivalents
        for sqlite_func, pg_func in SQLiteToPostgreSQLConverter.FUNCTION_MAPPING.items():
            pattern = re.compile(r'\b' + re.escape(sqlite_func) + r'\b', re.IGNORECASE)
            sql = pattern.sub(pg_func, sql)
            
        # Handle RETURNING clause for INSERT statements if needed
        if re.match(r'^\s*INSERT\s+INTO', sql, re.IGNORECASE) and 'RETURNING' not in sql.upper():
            sql = sql.rstrip(';')
            sql += ' RETURNING id;'
        
        # Handle boolean literals (SQLite uses 0/1, PostgreSQL uses true/false)
        # Only convert standalone 0/1 values, not those that might be used for integer columns
        # For example, convert "WHERE active = 0" but not "DEFAULT 0" for integer columns
        
        # More selective boolean conversion - only convert specific known boolean columns
        # Define the actual boolean columns from our database schema
        known_boolean_columns = ['is_active', 'is_imported']
        
        # Convert 0/1 to boolean values only for known boolean columns
        if re.search(r'WHERE\s', sql, re.IGNORECASE):
            for col_name in known_boolean_columns:
                # Convert 0 to false for specific boolean columns
                sql = re.sub(
                    rf'(\s+{re.escape(col_name)}\s*=\s*)0(\s+|$|\)|,)', 
                    r'\1false\2', 
                    sql, 
                    flags=re.IGNORECASE
                )
                # Convert 1 to true for specific boolean columns  
                sql = re.sub(
                    rf'(\s+{re.escape(col_name)}\s*=\s*)1(\s+|$|\)|,)', 
                    r'\1true\2', 
                    sql, 
                    flags=re.IGNORECASE
                )
        
        # Handle INSERT statements with boolean columns
        if re.search(r'INSERT\s+INTO\s+wallets', sql, re.IGNORECASE):
            # For wallets table, convert the boolean column values
            # This needs to be done carefully to match the exact positions
            pass  # We'll handle this in the postgresql.py execute_query function instead
        
        # Convert PRAGMA statements
        sql = SQLiteToPostgreSQLConverter._convert_pragma(sql)
        
        # Handle LIMIT and OFFSET clauses
        sql = SQLiteToPostgreSQLConverter._convert_limit_offset(sql)

        # IMPORTANT: Removing recursive calls that cause infinite recursion
        # These statements below were causing recursion:
        # sql = SQLiteToPostgreSQLConverter.convert_create_index(sql)
        # sql = SQLiteToPostgreSQLConverter.convert_create_table(sql)
        # sql = SQLiteToPostgreSQLConverter.convert_insert(sql)
        
        # Replace double-quoted identifiers with schema-qualified identifiers
        # This is complex and may need manual intervention in some cases
        
        # Log the conversion for debugging
        if sql != original_sql:
            logger.debug(f"SQL conversion:\nFrom: {original_sql}\nTo:   {sql}")
        
        return sql
    
    @staticmethod
    def _convert_pragma(sql: str) -> str:
        """
        Convert SQLite PRAGMA statements to PostgreSQL alternatives.
        
        Args:
            sql (str): SQL statement possibly containing PRAGMA
            
        Returns:
            str: SQL with converted PRAGMA statements
        """
        # Handle common PRAGMA statements
        if re.match(r'^\s*PRAGMA\s+foreign_keys\s*=\s*ON', sql, re.IGNORECASE):
            return "SET session_replication_role = 'origin';"
        elif re.match(r'^\s*PRAGMA\s+foreign_keys\s*=\s*OFF', sql, re.IGNORECASE):
            return "SET session_replication_role = 'replica';"
        elif re.match(r'^\s*PRAGMA\s+table_info\s*\(\s*([^)]+)\s*\)', sql, re.IGNORECASE):
            # Convert PRAGMA table_info(table_name) to PostgreSQL information_schema query
            table_match = re.search(r'PRAGMA\s+table_info\s*\(\s*([^)]+)\s*\)', sql, re.IGNORECASE)
            if table_match:
                table_name = table_match.group(1).strip('\'"')
                return f"""SELECT 
                    column_name as name,
                    ordinal_position as cid,
                    data_type as type,
                    CASE WHEN is_nullable = 'NO' THEN 1 ELSE 0 END as "notnull",
                    column_default as dflt_value,
                    CASE WHEN column_name IN (
                        SELECT kcu.column_name
                        FROM information_schema.table_constraints tc
                        JOIN information_schema.key_column_usage kcu
                        ON tc.constraint_name = kcu.constraint_name
                        WHERE tc.table_name = '{table_name}' AND tc.constraint_type = 'PRIMARY KEY'
                    ) THEN 1 ELSE 0 END as pk
                FROM information_schema.columns 
                WHERE table_name = '{table_name}' 
                AND table_schema = 'public'
                ORDER BY ordinal_position"""
        elif re.match(r'^\s*PRAGMA', sql, re.IGNORECASE):
            # Other PRAGMA statements need to be handled case by case
            # or removed if no PostgreSQL equivalent exists
            logger.warning(f"Unsupported PRAGMA statement: {sql}")
            return "-- " + sql + " -- Unsupported in PostgreSQL"
        
        return sql
    
    @staticmethod
    def _convert_limit_offset(sql: str) -> str:
        """
        Convert SQLite LIMIT/OFFSET clauses to PostgreSQL syntax.
        
        Args:
            sql (str): SQL statement with SQLite-style LIMIT/OFFSET
            
        Returns:
            str: SQL with PostgreSQL-style LIMIT/OFFSET
        """
        # SQLite: LIMIT X OFFSET Y
        # PostgreSQL: LIMIT X OFFSET Y (Same syntax, but making sure it's consistent)
        
        # Handle the case of 'LIMIT X, Y' syntax in SQLite (meaning LIMIT Y OFFSET X)
        limit_offset_match = re.search(r'LIMIT\s+(\d+)\s*,\s*(\d+)', sql, re.IGNORECASE)
        if limit_offset_match:
            offset, limit = limit_offset_match.groups()
            sql = re.sub(
                r'LIMIT\s+\d+\s*,\s*\d+', 
                f'LIMIT {limit} OFFSET {offset}', 
                sql, 
                flags=re.IGNORECASE
            )
        
        return sql
    
    @staticmethod
    def convert_create_table(create_sql: str) -> str:
        """
        Convert a SQLite CREATE TABLE statement to PostgreSQL syntax.
        
        Args:
            create_sql (str): SQLite CREATE TABLE statement
            
        Returns:
            str: PostgreSQL compatible CREATE TABLE statement
        """
        # Special handling for CREATE TABLE statements
        # Apply transformations directly instead of calling convert_sql to avoid recursion
        sql = create_sql
        
        # Replace SQLite specific types with PostgreSQL types
        for sqlite_type, pg_type in SQLiteToPostgreSQLConverter.TYPE_MAPPING.items():
            pattern = re.compile(r'\b' + re.escape(sqlite_type) + r'\b', re.IGNORECASE)
            sql = pattern.sub(pg_type, sql)
            
        # Convert AUTOINCREMENT to SERIAL if not already handled by type mapping
        sql = re.sub(r'AUTOINCREMENT', 'SERIAL', sql, flags=re.IGNORECASE)
        
        # Handle IF NOT EXISTS syntax (supported in both but ensuring compatibility)
        if "IF NOT EXISTS" not in sql.upper():
            sql = sql.replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS", 1)
            
        # Handle WITHOUT ROWID (SQLite specific, no PostgreSQL equivalent)
        sql = re.sub(r'WITHOUT\s+ROWID', '', sql, flags=re.IGNORECASE)
        
        return sql
    
    @staticmethod
    def convert_create_index(create_index_sql: str) -> str:
        """
        Convert a SQLite CREATE INDEX statement to PostgreSQL syntax.
        
        Args:
            create_index_sql (str): SQLite CREATE INDEX statement
            
        Returns:
            str: PostgreSQL compatible CREATE INDEX statement
        """
        # Handle IF NOT EXISTS for indexes
        sql = create_index_sql
        
        # Ensure IF NOT EXISTS is included
        if "IF NOT EXISTS" not in sql.upper():
            sql = re.sub(
                r'CREATE\s+INDEX', 
                'CREATE INDEX IF NOT EXISTS', 
                sql, 
                flags=re.IGNORECASE
            )
        
        # Convert WHERE clause syntax if needed
        # In most cases this should be compatible
        
        # IMPORTANT: Instead of recursively calling convert_sql, we apply the 
        # relevant transformations directly to avoid infinite recursion
        
        # Replace SQLite specific types with PostgreSQL types
        for sqlite_type, pg_type in SQLiteToPostgreSQLConverter.TYPE_MAPPING.items():
            pattern = re.compile(r'\b' + re.escape(sqlite_type) + r'\b', re.IGNORECASE)
            sql = pattern.sub(pg_type, sql)
            
        # Convert SQLite functions to PostgreSQL equivalents
        for sqlite_func, pg_func in SQLiteToPostgreSQLConverter.FUNCTION_MAPPING.items():
            pattern = re.compile(r'\b' + re.escape(sqlite_func) + r'\b', re.IGNORECASE)
            sql = pattern.sub(pg_func, sql)
        
        return sql
    
    @staticmethod
    def convert_insert(insert_sql: str) -> str:
        """
        Convert a SQLite INSERT statement to PostgreSQL syntax.
        
        Args:
            insert_sql (str): SQLite INSERT statement
            
        Returns:
            str: PostgreSQL compatible INSERT statement
        """
        # Apply transformations directly instead of calling convert_sql to avoid recursion
        sql = insert_sql
        
        # Replace SQLite specific types with PostgreSQL types
        for sqlite_type, pg_type in SQLiteToPostgreSQLConverter.TYPE_MAPPING.items():
            pattern = re.compile(r'\b' + re.escape(sqlite_type) + r'\b', re.IGNORECASE)
            sql = pattern.sub(pg_type, sql)
            
        # Convert SQLite functions to PostgreSQL equivalents
        for sqlite_func, pg_func in SQLiteToPostgreSQLConverter.FUNCTION_MAPPING.items():
            pattern = re.compile(r'\b' + re.escape(sqlite_func) + r'\b', re.IGNORECASE)
            sql = pattern.sub(pg_func, sql)
        
        # Handle RETURNING clause for INSERT statements if needed
        if re.match(r'^\s*INSERT\s+INTO', sql, re.IGNORECASE) and 'RETURNING' not in sql.upper():
            sql = sql.rstrip(';')
            sql += ' RETURNING id;'
        
        # Handle SQLite's INSERT OR REPLACE/INSERT OR IGNORE syntax
        if re.match(r'^\s*INSERT\s+OR\s+REPLACE', sql, re.IGNORECASE):
            sql = re.sub(
                r'^\s*INSERT\s+OR\s+REPLACE', 
                'INSERT', 
                sql, 
                flags=re.IGNORECASE
            )
            # Extract table name
            table_match = re.search(r'INTO\s+([^\s(]+)', sql, re.IGNORECASE)
            if table_match:
                table_name = table_match.group(1)
                # Add ON CONFLICT clause for UPSERT
                if 'ON CONFLICT' not in sql.upper():
                    # This requires knowledge of the primary key, which we may not have
                    # A more complete solution would need to consult schema information
                    sql = sql.rstrip(';')
                    sql += ' ON CONFLICT (id) DO UPDATE SET '
                    # This is a simplistic approach - in practice you need to know all columns
                    sql += 'updated_at = EXCLUDED.updated_at;'
            
        elif re.match(r'^\s*INSERT\s+OR\s+IGNORE', sql, re.IGNORECASE):
            sql = re.sub(
                r'^\s*INSERT\s+OR\s+IGNORE', 
                'INSERT', 
                sql, 
                flags=re.IGNORECASE
            )
            # Add ON CONFLICT DO NOTHING
            if 'ON CONFLICT' not in sql.upper():
                sql = sql.rstrip(';')
                sql += ' ON CONFLICT DO NOTHING;'
        
        return sql
    
    @staticmethod
    def adapt_params(params: Union[List[Any], Tuple[Any, ...], Dict[str, Any]]) -> Union[List[Any], Tuple[Any, ...], Dict[str, Any]]:
        """
        Adapt SQLite parameter values to PostgreSQL compatible values.
        
        Args:
            params: Parameter collection (list, tuple, or dict)
            
        Returns:
            Adapted parameter collection
        """
        # If params is None or empty, return as is
        if not params:
            return params
            
        # For tuple/list parameters, convert to list for processing, then back to tuple
        if isinstance(params, (list, tuple)):
            # For PostgreSQL, parameters must be passed as a tuple (not a list)
            # Make sure we return a tuple of values
            return tuple(params)
        
        # For dict parameters, PostgreSQL uses keys like "%(key)s"
        # but we've already converted to numbered params, so we can convert
        # the dict to a tuple with the values in the right order
        elif isinstance(params, dict):
            # Extract values as a tuple in lexical key order for numbered parameters
            return tuple(value for _, value in sorted(params.items()))
            
        # If params is a single value, wrap it in a tuple
        return (params,)

# Convenience functions

def convert_sql(sql: str) -> str:
    """
    Convenience function to convert a SQLite SQL statement to PostgreSQL syntax.
    
    Args:
        sql (str): SQLite SQL statement
        
    Returns:
        str: PostgreSQL compatible SQL statement
    """
    return SQLiteToPostgreSQLConverter.convert_sql(sql)

def convert_create_table(sql: str) -> str:
    """
    Convenience function to convert a SQLite CREATE TABLE statement to PostgreSQL syntax.
    
    Args:
        sql (str): SQLite CREATE TABLE statement
        
    Returns:
        str: PostgreSQL compatible CREATE TABLE statement
    """
    return SQLiteToPostgreSQLConverter.convert_create_table(sql)

def convert_create_index(sql: str) -> str:
    """
    Convenience function to convert a SQLite CREATE INDEX statement to PostgreSQL syntax.
    
    Args:
        sql (str): SQLite CREATE INDEX statement
        
    Returns:
        str: PostgreSQL compatible CREATE INDEX statement
    """
    return SQLiteToPostgreSQLConverter.convert_create_index(sql)

def convert_insert(sql: str) -> str:
    """
    Convenience function to convert a SQLite INSERT statement to PostgreSQL syntax.
    
    Args:
        sql (str): SQLite INSERT statement
        
    Returns:
        str: PostgreSQL compatible INSERT statement
    """
    return SQLiteToPostgreSQLConverter.convert_insert(sql)

def adapt_params(params: Union[List[Any], Tuple[Any, ...], Dict[str, Any]]) -> Union[List[Any], Tuple[Any, ...], Dict[str, Any]]:
    """
    Adapt SQLite parameter values to PostgreSQL compatible values.
    
    Args:
        params: Parameter collection (list, tuple, or dict)
        
    Returns:
        Adapted parameter collection
    """
    return SQLiteToPostgreSQLConverter.adapt_params(params) 