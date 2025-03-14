"""
SQLite3 database connection implementation.
Provides functions to create, test, and manage SQLite database connections.
"""
import logging
import os
import sqlite3
import time
import traceback
from contextlib import contextmanager
from functools import wraps
from typing import Callable
# Configure module logger
logger = logging.getLogger(__name__)

# Global connection cache
_connection = None

def retry_on_db_lock(max_attempts: int = 5, initial_wait: float = 0.1) -> Callable:
    """
    Decorator to retry a database operation on SQLite database is locked errors.
    
    Args:
        max_attempts (int): Maximum number of retry attempts
        initial_wait (float): Initial wait time in seconds
        
    Returns:
        Decorator function
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            wait_time = initial_wait
            last_error = None
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e):
                        last_error = e
                        # Exponential backoff
                        wait_time *= 2
                        logger.warning(f"Database locked, retrying in {wait_time:.2f}s (attempt {attempt+1}/{max_attempts})")
                        time.sleep(wait_time)
                    else:
                        # Re-raise other SQLite operational errors
                        raise
            
            # If we got here, all retries failed
            logger.error(f"Database still locked after {max_attempts} attempts: {last_error}")
            raise last_error
        
        return wrapper
    
    return decorator

def create_connection(db_path):
    """
    Create a database connection to the SQLite database file.
    
    Args:
        db_path (str): Path to the SQLite database file
        
    Returns:
        sqlite3.Connection: Database connection or None on error
    """
    try:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        # Create connection with extended timeout
        conn = sqlite3.connect(
            db_path,
            timeout=30.0,  # 30 second timeout
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        
        # Enable foreign keys
        conn.execute("PRAGMA foreign_keys = ON")
        
        # Row factory for dictionary-like access
        conn.row_factory = sqlite3.Row
        
        logger.debug(f"Connected to SQLite database at {db_path}")
        return conn
    except Exception as e:
        logger.error(f"Error connecting to SQLite database: {e}")
        logger.error(traceback.format_exc())
        return None

def get_connection(db_path):
    """
    Get the database connection, creating it if needed.
    
    Args:
        db_path (str): Path to the SQLite database file
        
    Returns:
        sqlite3.Connection: Database connection or None on error
    """
    global _connection
    
    if _connection is None:
        _connection = create_connection(db_path)
    
    return _connection

def close_connection(conn=None):
    """
    Close the specified database connection or the global one.
    
    Args:
        conn (sqlite3.Connection, optional): Connection to close, or global if None
        
    Returns:
        bool: True if successful, False otherwise
    """
    global _connection
    
    if conn is None:
        conn = _connection
        _connection = None
    
    if conn:
        try:
            conn.close()
            logger.debug("SQLite database connection closed")
            return True
        except Exception as e:
            logger.error(f"Error closing SQLite database connection: {e}")
            logger.error(traceback.format_exc())
    
    return False

@contextmanager
def get_db_connection(db_path):
    """
    Context manager for database connections.
    
    Args:
        db_path (str): Path to the SQLite database file
        
    Yields:
        sqlite3.Connection: Database connection
        
    Raises:
        Exception: If database connection fails
    """
    conn = None
    try:
        conn = get_connection(db_path)
        if conn is None:
            raise Exception("Failed to get SQLite database connection")
        yield conn
    finally:
        # We don't close the connection here as it's a global singleton
        pass

def execute_query(query, params=(), fetch=None, db_path=None):
    """
    Execute a SQL query with retry on database locks.
    
    Args:
        query (str): SQL query to execute
        params (tuple): Query parameters
        fetch (str): One of 'all', 'one', or None for SELECT queries
        db_path (str): Path to the SQLite database file
        
    Returns:
        list|dict|int: Query results or row count
    """
    conn = get_connection(db_path)
    if conn is None:
        logger.error("No SQLite database connection for query execution")
        return None
    
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        
        if fetch == 'all':
            result = [dict(row) for row in cursor.fetchall()]
            logger.debug(f"Query fetched {len(result)} rows")
            return result
        elif fetch == 'one':
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
        else:
            conn.commit()
            rows_affected = cursor.rowcount
            logger.debug(f"Query affected {rows_affected} rows")
            return rows_affected
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"SQLite database error executing query: {e}")
        logger.error(f"Query: {query}")
        logger.error(f"Params: {params}")
        logger.error(traceback.format_exc())
        raise
    finally:
        if cursor:
            cursor.close()

def test_connection(db_path):
    """
    Test the database connection by executing a simple query.
    
    Args:
        db_path (str): Path to the SQLite database file
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        execute_query("SELECT 1", fetch='one', db_path=db_path)
        return True
    except Exception as e:
        logger.error(f"SQLite database connection test failed: {e}")
        return False

def init_db(db_path, init_script):
    """
    Initialize the database by creating tables if they don't exist.
    
    Args:
        db_path (str): Path to the SQLite database file
        init_script (str): SQL script to initialize the database
        
    Returns:
        bool: True if successful, False otherwise
    """
    conn = get_connection(db_path)
    if conn is None:
        logger.error("Failed to initialize SQLite database: No connection")
        return False
    
    try:
        # Create tables if they don't exist
        conn.executescript(init_script)
        
        conn.commit()
        logger.info("SQLite database initialized successfully")
        return True
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"SQLite database initialization error: {e}")
        logger.error(traceback.format_exc())
        return False 