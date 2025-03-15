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
        sql = re.sub(r'(?<=\W)1(?=\W)', 'true', sql)
        sql = re.sub(r'(?<=\W)0(?=\W)', 'false', sql)
        
        # Convert PRAGMA statements
        sql = SQLiteToPostgreSQLConverter._convert_pragma(sql)
        
        # Handle LIMIT and OFFSET clauses
        sql = SQLiteToPostgreSQLConverter._convert_limit_offset(sql)

        # handle create index
        sql = SQLiteToPostgreSQLConverter.convert_create_index(sql)

        # handle create table
        sql = SQLiteToPostgreSQLConverter.convert_create_table(sql)

        # handle insert
        sql = SQLiteToPostgreSQLConverter.convert_insert(sql)
        
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
        sql = SQLiteToPostgreSQLConverter.convert_sql(create_sql)
        
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
        
        return SQLiteToPostgreSQLConverter.convert_sql(sql)
    
    @staticmethod
    def convert_insert(insert_sql: str) -> str:
        """
        Convert a SQLite INSERT statement to PostgreSQL syntax.
        
        Args:
            insert_sql (str): SQLite INSERT statement
            
        Returns:
            str: PostgreSQL compatible INSERT statement
        """
        sql = SQLiteToPostgreSQLConverter.convert_sql(insert_sql)
        
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
                    logger.warning(f"Converted INSERT OR REPLACE to ON CONFLICT - may need manual adjustment")
            
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
        Adapt SQLite parameters to PostgreSQL format if needed.
        
        Args:
            params: Query parameters in SQLite format
            
        Returns:
            Adapted parameters for PostgreSQL
        """
        # In most cases, parameters are compatible
        # This method exists to handle special cases if needed
        return params

# Convenience functions

def convert_sql(sql: str) -> str:
    """
    Convert a SQLite SQL statement to PostgreSQL syntax.
    
    Args:
        sql (str): SQLite SQL statement
        
    Returns:
        str: PostgreSQL compatible SQL statement
    """
    return SQLiteToPostgreSQLConverter.convert_sql(sql)

def convert_create_table(sql: str) -> str:
    """
    Convert a SQLite CREATE TABLE statement to PostgreSQL syntax.
    
    Args:
        sql (str): SQLite CREATE TABLE statement
        
    Returns:
        str: PostgreSQL compatible CREATE TABLE statement
    """
    return SQLiteToPostgreSQLConverter.convert_create_table(sql)

def convert_create_index(sql: str) -> str:
    """
    Convert a SQLite CREATE INDEX statement to PostgreSQL syntax.
    
    Args:
        sql (str): SQLite CREATE INDEX statement
        
    Returns:
        str: PostgreSQL compatible CREATE INDEX statement
    """
    return SQLiteToPostgreSQLConverter.convert_create_index(sql)

def convert_insert(sql: str) -> str:
    """
    Convert a SQLite INSERT statement to PostgreSQL syntax.
    
    Args:
        sql (str): SQLite INSERT statement
        
    Returns:
        str: PostgreSQL compatible INSERT statement
    """
    return SQLiteToPostgreSQLConverter.convert_insert(sql)

def adapt_params(params: Union[List[Any], Tuple[Any, ...], Dict[str, Any]]) -> Union[List[Any], Tuple[Any, ...], Dict[str, Any]]:
    """
    Adapt SQLite parameters to PostgreSQL format if needed.
    
    Args:
        params: Query parameters in SQLite format
        
    Returns:
        Adapted parameters for PostgreSQL
    """
    return SQLiteToPostgreSQLConverter.adapt_params(params) 