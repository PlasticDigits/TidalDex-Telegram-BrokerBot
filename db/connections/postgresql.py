"""
PostgreSQL database connection implementation.
Provides functions to create, test, and manage PostgreSQL database connections.
"""
import logging
import traceback
import time
from contextlib import contextmanager
from functools import wraps

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

def retry_on_db_error(max_attempts=5, initial_wait=0.1, error_classes=(psycopg2.OperationalError,)):
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
    Execute a SQL query with retry on database errors.
    
    Args:
        query (str): SQL query to execute
        params (tuple): Query parameters
        fetch (str): One of 'all', 'one', or None for SELECT queries
        db_name (str): Database name
        db_user (str): Database user
        db_password (str): Database password
        db_host (str): Database host
        db_port (int): Database port
        
    Returns:
        list|dict|int: Query results or row count
    """
    if not POSTGRESQL_AVAILABLE:
        logger.error("psycopg2 is not installed. Please install it with 'pip install psycopg2-binary'")
        return None
        
    with get_db_connection(db_name, db_user, db_password, db_host, db_port) as conn:
        cursor = None
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(query, params)
            
            if fetch == 'all':
                result = cursor.fetchall()
                logger.debug(f"Query fetched {len(result)} rows")
                return result
            elif fetch == 'one':
                row = cursor.fetchone()
                return row
            else:
                conn.commit()
                rows_affected = cursor.rowcount
                logger.debug(f"Query affected {rows_affected} rows")
                return rows_affected
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"PostgreSQL database error executing query: {e}")
            logger.error(f"Query: {query}")
            logger.error(f"Params: {params}")
            logger.error(traceback.format_exc())
            raise
        finally:
            if cursor:
                cursor.close()

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
        result = execute_query(
            "SELECT 1", 
            fetch='one', 
            db_name=db_name, 
            db_user=db_user, 
            db_password=db_password, 
            db_host=db_host, 
            db_port=db_port
        )
        return result is not None and '1' in result and result['1'] == 1
    except Exception as e:
        logger.error(f"PostgreSQL database connection test failed: {e}")
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
            cursor.execute(init_script)
            conn.commit()
            cursor.close()
            
            logger.info("PostgreSQL database initialized successfully")
            return True
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"PostgreSQL database initialization error: {e}")
            logger.error(traceback.format_exc())
            return False 