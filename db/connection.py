"""
Database connection management.
Provides functions to create, test, and manage database connections.
"""
import logging
import os
import sqlite3
import time
import traceback
from contextlib import contextmanager
from functools import wraps

from utils.config import DATABASE_PATH

# Configure module logger
logger = logging.getLogger(__name__)

# Global connection cache
_connection = None

def retry_on_db_lock(max_attempts=5, initial_wait=0.1):
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

def create_connection():
    """
    Create a database connection to the SQLite database file.
    
    Returns:
        sqlite3.Connection: Database connection or None on error
    """
    try:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
        
        # Create connection with extended timeout
        conn = sqlite3.connect(
            DATABASE_PATH,
            timeout=30.0,  # 30 second timeout
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        
        # Enable foreign keys
        conn.execute("PRAGMA foreign_keys = ON")
        
        # Row factory for dictionary-like access
        conn.row_factory = sqlite3.Row
        
        logger.debug(f"Connected to database at {DATABASE_PATH}")
        return conn
    except Exception as e:
        logger.error(f"Error connecting to database: {e}")
        logger.error(traceback.format_exc())
        return None

def get_connection():
    """
    Get the database connection, creating it if needed.
    
    Returns:
        sqlite3.Connection: Database connection or None on error
    """
    global _connection
    
    if _connection is None:
        _connection = create_connection()
    
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
            logger.debug("Database connection closed")
            return True
        except Exception as e:
            logger.error(f"Error closing database connection: {e}")
            logger.error(traceback.format_exc())
    
    return False

@contextmanager
def get_db_connection():
    """
    Context manager for database connections.
    
    Yields:
        sqlite3.Connection: Database connection
        
    Raises:
        Exception: If database connection fails
    """
    conn = None
    try:
        conn = get_connection()
        if conn is None:
            raise Exception("Failed to get database connection")
        yield conn
    finally:
        # We don't close the connection here as it's a global singleton
        pass

@retry_on_db_lock()
def execute_query(query, params=(), fetch=None):
    """
    Execute a SQL query with retry on database locks.
    
    Args:
        query (str): SQL query to execute
        params (tuple): Query parameters
        fetch (str): One of 'all', 'one', or None for SELECT queries
        
    Returns:
        list|dict|int: Query results or row count
    """
    conn = get_connection()
    if conn is None:
        logger.error("No database connection for query execution")
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
        logger.error(f"Database error executing query: {e}")
        logger.error(f"Query: {query}")
        logger.error(f"Params: {params}")
        logger.error(traceback.format_exc())
        raise
    finally:
        if cursor:
            cursor.close()

def test_connection():
    """
    Test the database connection by executing a simple query.
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        result = execute_query("SELECT 1", fetch='one')
        return result is not None and result.get('1') == 1
    except Exception as e:
        logger.error(f"Database connection test failed: {e}")
        return False

def init_db():
    """
    Initialize the database by creating tables if they don't exist.
    
    Returns:
        bool: True if successful, False otherwise
    """
    conn = get_connection()
    if conn is None:
        logger.error("Failed to initialize database: No connection")
        return False
    
    try:
        # Create tables if they don't exist
        conn.executescript('''
            -- Users table
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                pin_hash TEXT,
                account_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                settings TEXT
            );
            
            -- Mnemonics table for seed phrases
            CREATE TABLE IF NOT EXISTS mnemonics (
                user_id TEXT PRIMARY KEY,
                mnemonic TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );
            
            -- Wallets table
            CREATE TABLE IF NOT EXISTS wallets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                address TEXT NOT NULL,
                private_key TEXT,
                path TEXT,
                name TEXT DEFAULT 'Default',
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                UNIQUE(user_id, name)
            );
            
            -- PIN attempts table for tracking failed attempts
            CREATE TABLE IF NOT EXISTS pin_attempts (
                user_id TEXT PRIMARY KEY,
                failure_count INTEGER NOT NULL DEFAULT 0,
                last_attempt_time INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );
        ''')
        
        conn.commit()
        logger.info("Database initialized successfully")
        return True
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Database initialization error: {e}")
        logger.error(traceback.format_exc())
        return False 