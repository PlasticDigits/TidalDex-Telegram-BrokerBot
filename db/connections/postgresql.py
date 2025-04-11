"""
PostgreSQL database connection implementation.
Provides functions to create, test, and manage PostgreSQL database connections.
"""
import logging
import traceback
import time
from contextlib import contextmanager
from functools import wraps
from typing import Callable, Any, Dict, List, Optional, Tuple, Union, Generator, cast
try:
    import psycopg2
    from psycopg2 import pool
    from psycopg2.extras import RealDictCursor
    POSTGRESQL_AVAILABLE = True
except ImportError:
    POSTGRESQL_AVAILABLE = False
    psycopg2 = None
    pool = None
    RealDictCursor = None

# Configure module logger
logger = logging.getLogger(__name__)

# Global connection pool
_connection_pool = None

# Import QueryResult type from local module instead of db
from db.connections.connection import QueryResult

def retry_on_db_error(max_attempts: int = 5, initial_wait: float = 0.1, error_classes: tuple = (psycopg2.OperationalError,)) -> Callable:
    """
    Decorator to retry a database operation on specific PostgreSQL errors.
    
    Args:
        max_attempts (int): Maximum number of retry attempts
        initial_wait (float): Initial wait time in seconds
        error_classes (tuple): Tuple of error classes to catch and retry
        
    Returns:
        Decorator function
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not POSTGRESQL_AVAILABLE:
                raise ImportError("psycopg2 is not installed. Please install it with 'pip install psycopg2-binary'")
                
            wait_time = initial_wait
            last_error = None
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except error_classes as e:
                    last_error = e
                    # Exponential backoff
                    wait_time *= 2
                    logger.warning(f"Database error, retrying in {wait_time:.2f}s (attempt {attempt+1}/{max_attempts}): {str(e)}")
                    time.sleep(wait_time)
            
            # If we got here, all retries failed
            logger.error(f"Database still failing after {max_attempts} attempts: {last_error}")
            raise last_error
        
        return wrapper
    
    return decorator

def create_connection_pool(db_name, db_user, db_password, db_host, db_port, min_connections=1, max_connections=10):
    """
    Create a connection pool to the PostgreSQL database.
    
    Args:
        db_name (str): Database name
        db_user (str): Database user
        db_password (str): Database password
        db_host (str): Database host
        db_port (int): Database port
        min_connections (int): Minimum number of connections in the pool
        max_connections (int): Maximum number of connections in the pool
        
    Returns:
        psycopg2.pool.ThreadedConnectionPool: Connection pool or None on error
    """
    if not POSTGRESQL_AVAILABLE:
        logger.error("psycopg2 is not installed. Please install it with 'pip install psycopg2-binary'")
        return None
        
    try:
        connection_pool = pool.ThreadedConnectionPool(
            min_connections,
            max_connections,
            database=db_name,
            user=db_user,
            password=db_password,
            host=db_host,
            port=db_port
        )
        
        logger.debug(f"Connected to PostgreSQL database at {db_host}:{db_port}/{db_name}")
        return connection_pool
    except Exception as e:
        logger.error(f"Error connecting to PostgreSQL database: {e}")
        logger.error(traceback.format_exc())
        return None

def get_connection_pool(db_name, db_user, db_password, db_host, db_port):
    """
    Get the database connection pool, creating it if needed.
    
    Args:
        db_name (str): Database name
        db_user (str): Database user
        db_password (str): Database password
        db_host (str): Database host
        db_port (int): Database port
        
    Returns:
        psycopg2.pool.ThreadedConnectionPool: Connection pool or None on error
    """
    global _connection_pool
    
    if _connection_pool is None:
        _connection_pool = create_connection_pool(db_name, db_user, db_password, db_host, db_port)
    
    return _connection_pool

def get_connection(db_name, db_user, db_password, db_host, db_port):
    """
    Get a connection from the pool.
    
    Args:
        db_name (str): Database name
        db_user (str): Database user
        db_password (str): Database password
        db_host (str): Database host
        db_port (int): Database port
        
    Returns:
        psycopg2.extensions.connection: Database connection or None on error
    """
    if not POSTGRESQL_AVAILABLE:
        logger.error("psycopg2 is not installed. Please install it with 'pip install psycopg2-binary'")
        return None
        
    pool = get_connection_pool(db_name, db_user, db_password, db_host, db_port)
    if pool is None:
        logger.error("No connection pool available")
        return None
    
    try:
        conn = pool.getconn()
        logger.debug("Obtained connection from the pool")
        return conn
    except Exception as e:
        logger.error(f"Error getting connection from the pool: {e}")
        logger.error(traceback.format_exc())
        return None

def close_connection(conn):
    """
    Return a connection to the pool.
    
    Args:
        conn (psycopg2.extensions.connection): Connection to return to the pool
        
    Returns:
        bool: True if successful, False otherwise
    """
    if not POSTGRESQL_AVAILABLE:
        logger.error("psycopg2 is not installed. Please install it with 'pip install psycopg2-binary'")
        return False
        
    global _connection_pool
    
    if _connection_pool is None:
        logger.error("No connection pool to return connection to")
        return False
    
    if conn:
        try:
            _connection_pool.putconn(conn)
            logger.debug("Connection returned to the pool")
            return True
        except Exception as e:
            logger.error(f"Error returning connection to the pool: {e}")
            logger.error(traceback.format_exc())
    
    return False

def close_all_connections():
    """
    Close all connections in the pool.
    
    Returns:
        bool: True if successful, False otherwise
    """
    if not POSTGRESQL_AVAILABLE:
        logger.error("psycopg2 is not installed. Please install it with 'pip install psycopg2-binary'")
        return False
        
    global _connection_pool
    
    if _connection_pool:
        try:
            _connection_pool.closeall()
            _connection_pool = None
            logger.debug("All connections closed and pool destroyed")
            return True
        except Exception as e:
            logger.error(f"Error closing all connections: {e}")
            logger.error(traceback.format_exc())
    
    return False

@contextmanager
def get_db_connection(db_name, db_user, db_password, db_host, db_port):
    """
    Context manager for database connections.
    
    Args:
        db_name (str): Database name
        db_user (str): Database user
        db_password (str): Database password
        db_host (str): Database host
        db_port (int): Database port
        
    Yields:
        psycopg2.extensions.connection: Database connection
        
    Raises:
        Exception: If database connection fails
    """
    if not POSTGRESQL_AVAILABLE:
        raise ImportError("psycopg2 is not installed. Please install it with 'pip install psycopg2-binary'")
        
    conn = None
    try:
        conn = get_connection(db_name, db_user, db_password, db_host, db_port)
        if conn is None:
            raise Exception("Failed to get PostgreSQL database connection")
        yield conn
    finally:
        if conn:
            close_connection(conn)

@retry_on_db_error()
def execute_query(query, params=(), fetch=None, db_name=None, db_user=None, db_password=None, db_host=None, db_port=None):
    """
    Execute a SQL query and return the results.
    
    Args:
        query (str): SQL query to execute
        params (tuple or dict, optional): Query parameters
        fetch (str, optional): Fetch mode ('all', 'one', 'many', or None for execute only)
        db_name (str, optional): Database name
        db_user (str, optional): Database user
        db_password (str, optional): Database password
        db_host (str, optional): Database host
        db_port (int, optional): Database port
        
    Returns:
        QueryResult: Query results based on fetch mode
    """
    if not POSTGRESQL_AVAILABLE:
        raise ImportError("psycopg2 is not installed. Please install it with 'pip install psycopg2-binary'")
    
    conn = None
    try:
        conn = get_connection(db_name, db_user, db_password, db_host, db_port)
        if conn is None:
            raise Exception("Failed to get PostgreSQL database connection")
        
        # Convert SQLite-specific syntax to PostgreSQL
        pg_query = query
        
        # Handle INSERT OR IGNORE syntax
        if "INSERT OR IGNORE INTO" in pg_query.upper():
            # Extract table name and the rest of the query
            parts = pg_query.split("VALUES")
            if len(parts) == 2:
                # Get table and columns from first part
                table_part = parts[0].replace("INSERT OR IGNORE INTO", "INSERT INTO").strip()
                # Build the transformed query
                pg_query = f"{table_part} VALUES {parts[1].strip()} ON CONFLICT DO NOTHING"
            else:
                # If the query structure is not as expected, try a regex approach
                import re
                match = re.match(r"INSERT\s+OR\s+IGNORE\s+INTO\s+(\w+)(.*)", pg_query, re.IGNORECASE)
                if match:
                    table_name, rest_of_query = match.groups()
                    # Transform to PostgreSQL syntax
                    pg_query = f"INSERT INTO {table_name}{rest_of_query} ON CONFLICT DO NOTHING"
        
        # Handle INSERT OR REPLACE/UPDATE syntax
        if "INSERT OR REPLACE INTO" in pg_query.upper():
            # Split the query into parts
            parts = pg_query.split("VALUES")
            if len(parts) == 2:
                # Get table and columns from first part
                table_part = parts[0].replace("INSERT OR REPLACE INTO", "").strip()
                table_name = table_part.split("(")[0].strip()
                columns = table_part.split("(")[1].split(")")[0].strip()
                
                # Get values from second part
                values = parts[1].strip().strip("()")
                
                # Split columns for identifying the primary key (assuming first column is primary key)
                column_list = [c.strip() for c in columns.split(',')]
                primary_key = column_list[0]  # Typically user_id for this app
                
                # For the ON CONFLICT clause, we need to update all columns except the primary key
                update_clause = ", ".join([f"{col} = EXCLUDED.{col}" for col in column_list if col != primary_key])
                
                # First ensure the unique constraint exists
                try:
                    cursor = conn.cursor()
                    cursor.execute(f"""
                        DO $$ 
                        BEGIN
                            IF NOT EXISTS (
                                SELECT 1 FROM pg_constraint 
                                WHERE conname = '{table_name}_{primary_key}_key'
                            ) THEN
                                ALTER TABLE {table_name} ADD CONSTRAINT {table_name}_{primary_key}_key UNIQUE ({primary_key});
                            END IF;
                        END $$;
                    """)
                except Exception as e:
                    logger.warning(f"Could not add unique constraint: {e}")
                
                # Transform to PostgreSQL syntax
                pg_query = f"INSERT INTO {table_name} ({columns}) VALUES ({values}) ON CONFLICT ({primary_key}) DO UPDATE SET {update_clause}"
        
        # Replace ? with %s for psycopg2 (it will handle the conversion to $1, $2 internally)
        pg_query = pg_query.replace('?', '%s')
        logger.debug(f"Modified query: {pg_query}")
        
        # Identify boolean columns and convert integer parameters (0/1) to boolean values
        # Look for column names like "imported", "is_active", etc.
        boolean_column_names = ["imported", "is_active", "active"]
        boolean_column_indices = []
        
        # Identify boolean columns in the query
        if "INSERT INTO" in pg_query.upper() and "(" in pg_query and ")" in pg_query:
            # Extract column names from INSERT query
            col_start = pg_query.find("(", pg_query.find("INSERT INTO")) + 1
            col_end = pg_query.find(")", col_start)
            if col_start > 0 and col_end > col_start:
                column_list = [c.strip() for c in pg_query[col_start:col_end].split(',')]
                # Find indices of boolean columns
                for i, col in enumerate(column_list):
                    if any(bool_name in col.lower() for bool_name in boolean_column_names):
                        boolean_column_indices.append(i)
                        logger.debug(f"Identified boolean column: {col} at index {i}")
        
        # Convert integer parameters to boolean values
        if isinstance(params, tuple) and boolean_column_indices:
            param_list = list(params)
            for idx in boolean_column_indices:
                if idx < len(param_list):
                    # Convert 0/1 to False/True
                    if param_list[idx] == 0 or param_list[idx] == '0':
                        param_list[idx] = False
                        logger.debug(f"Converted parameter at index {idx} from 0 to False")
                    elif param_list[idx] == 1 or param_list[idx] == '1':
                        param_list[idx] = True
                        logger.debug(f"Converted parameter at index {idx} from 1 to True")
            params = tuple(param_list)
        
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Log parameters
        logger.debug(f"Parameters (type {type(params).__name__}): {params}")
        
        # Execute the query
        if not params:
            logger.debug("Executing query without parameters")
            cursor.execute(pg_query)
        else:
            logger.debug("Executing query with parameters")
            cursor.execute(pg_query, params)
            
        conn.commit()
        
        result = None
        if fetch == 'all':
            result = cursor.fetchall()
            logger.debug(f"Fetched all results: {len(result) if result else 0} rows")
        elif fetch == 'one':
            result = cursor.fetchone()
            logger.debug(f"Fetched one result: {result is not None}")
        elif fetch == 'many':
            result = cursor.fetchmany()
            logger.debug(f"Fetched many results: {len(result) if result else 0} rows")
        else:
            logger.debug(f"No fetch requested, rowcount: {cursor.rowcount}")
        
        cursor.close()
        if result is None:
            return -1 # compatibility with sqlite3
        return result
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"PostgreSQL database error executing query: {e}")
        logger.error(f"Query: {query}")
        logger.error(f"Params: {params}")
        logger.error(f"Param type: {type(params).__name__}")
        logger.error(traceback.format_exc())
        raise
    finally:
        if conn:
            close_connection(conn)

def test_connection(db_name, db_user, db_password, db_host, db_port):
    """
    Test the database connection by executing a simple query.
    
    Args:
        db_name (str): Database name
        db_user (str): Database user
        db_password (str): Database password
        db_host (str): Database host
        db_port (int): Database port
        
    Returns:
        bool: True if successful, False otherwise
    """
    if not POSTGRESQL_AVAILABLE:
        logger.error("psycopg2 is not installed. Please install it with 'pip install psycopg2-binary'")
        return False
        
    try:
        # Use a simpler approach to test the connection
        with get_db_connection(db_name, db_user, db_password, db_host, db_port) as conn:
            if conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 as test_value")
                result = cursor.fetchone()
                cursor.close()
                return result is not None
        return False
    except Exception as e:
        logger.error(f"PostgreSQL database connection test failed: {e}")
        logger.error(traceback.format_exc())
        return False

def init_db(db_name, db_user, db_password, db_host, db_port, init_script):
    """
    Initialize the database by creating tables if they don't exist.
    
    Args:
        db_name (str): Database name
        db_user (str): Database user
        db_password (str): Database password
        db_host (str): Database host
        db_port (int): Database port
        init_script (str): SQL script to initialize the database
        
    Returns:
        bool: True if successful, False otherwise
    """
    if not POSTGRESQL_AVAILABLE:
        logger.error("psycopg2 is not installed. Please install it with 'pip install psycopg2-binary'")
        return False
        
    with get_db_connection(db_name, db_user, db_password, db_host, db_port) as conn:
        try:
            cursor = conn.cursor()
            
            # Split the script into individual statements and execute them one by one
            # This is important for handling dependencies between tables
            statements = init_script.split(';')
            
            for statement in statements:
                # Skip empty statements
                statement = statement.strip()
                if statement:
                    try:
                        cursor.execute(statement + ';')
                        conn.commit()
                    except Exception as e:
                        # Log the error but continue with other statements
                        logger.warning(f"Error executing statement: {e}")
                        logger.warning(f"Statement: {statement}")
                        conn.rollback()
            
            logger.info("PostgreSQL database initialized successfully")
            return True
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"PostgreSQL database initialization error: {e}")
            logger.error(traceback.format_exc())
            return False 