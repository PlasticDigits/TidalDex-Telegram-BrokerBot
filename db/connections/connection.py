"""
Database connection factory.
Provides unified interface for database connections using either SQLite or PostgreSQL.
"""
import logging
import os
from importlib import import_module
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure module logger
logger = logging.getLogger(__name__)

# Get database configuration from environment variables
DB_TYPE = os.getenv('DB_TYPE', 'sqlite3').lower()
DB_NAME = os.getenv('DB_NAME', 'tidaldex.db')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', '5432'))
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')

# Path for SQLite database
if DB_TYPE == 'sqlite3':
    if not os.path.isabs(DB_NAME):
        DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'data', DB_NAME)
    else:
        DB_PATH = DB_NAME
else:
    DB_PATH = None

# Import the correct database module based on DB_TYPE
try:
    if DB_TYPE == 'sqlite3':
        db_module = import_module('db.connections.sqlite3')
        logger.info(f"Using SQLite database at {DB_PATH}")
    elif DB_TYPE == 'postgresql':
        db_module = import_module('db.connections.postgresql')
        logger.info(f"Using PostgreSQL database at {DB_HOST}:{DB_PORT}/{DB_NAME}")
    else:
        logger.error(f"Unsupported database type: {DB_TYPE}. Falling back to SQLite")
        DB_TYPE = 'sqlite3'
        db_module = import_module('db.connections.sqlite3')
except ImportError as e:
    logger.error(f"Error importing database module: {e}")
    logger.error("Falling back to SQLite")
    DB_TYPE = 'sqlite3'
    db_module = import_module('db.connections.sqlite3')

def create_connection():
    """
    Create a database connection.
    
    Returns:
        Connection: Database connection object or None on error
    """
    if DB_TYPE == 'sqlite3':
        return db_module.create_connection(DB_PATH)
    else:  # postgresql
        if not hasattr(db_module, 'POSTGRESQL_AVAILABLE') or not db_module.POSTGRESQL_AVAILABLE:
            logger.error("PostgreSQL support is not available. Please install psycopg2 with 'pip install psycopg2-binary'")
            return None
        return db_module.get_connection(DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT)

def get_connection():
    """
    Get a database connection, creating it if needed.
    
    Returns:
        Connection: Database connection object or None on error
    """
    if DB_TYPE == 'sqlite3':
        return db_module.get_connection(DB_PATH)
    else:  # postgresql
        if not hasattr(db_module, 'POSTGRESQL_AVAILABLE') or not db_module.POSTGRESQL_AVAILABLE:
            logger.error("PostgreSQL support is not available. Please install psycopg2 with 'pip install psycopg2-binary'")
            return None
        return db_module.get_connection(DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT)

def close_connection(conn=None):
    """
    Close a database connection.
    
    Args:
        conn (Connection, optional): Connection to close, or the global one if None
        
    Returns:
        bool: True if successful, False otherwise
    """
    return db_module.close_connection(conn)

def get_db_connection():
    """
    Context manager for database connections.
    
    Yields:
        Connection: Database connection object
        
    Raises:
        Exception: If database connection fails
    """
    if DB_TYPE == 'sqlite3':
        yield from db_module.get_db_connection(DB_PATH)
    else:  # postgresql
        if not hasattr(db_module, 'POSTGRESQL_AVAILABLE') or not db_module.POSTGRESQL_AVAILABLE:
            raise ImportError("PostgreSQL support is not available. Please install psycopg2 with 'pip install psycopg2-binary'")
        yield from db_module.get_db_connection(DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT)

def execute_query(query, params=(), fetch=None):
    """
    Execute a SQL query.
    
    Args:
        query (str): SQL query to execute
        params (tuple): Query parameters
        fetch (str): One of 'all', 'one', or None for SELECT queries
        
    Returns:
        list|dict|int: Query results or row count
    """
    if DB_TYPE == 'sqlite3':
        return db_module.execute_query(query, params, fetch, DB_PATH)
    else:  # postgresql
        if not hasattr(db_module, 'POSTGRESQL_AVAILABLE') or not db_module.POSTGRESQL_AVAILABLE:
            logger.error("PostgreSQL support is not available. Please install psycopg2 with 'pip install psycopg2-binary'")
            return None
        return db_module.execute_query(query, params, fetch, DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT)

def test_connection():
    """
    Test the database connection by executing a simple query.
    
    Returns:
        bool: True if successful, False otherwise
    """
    if DB_TYPE == 'sqlite3':
        return db_module.test_connection(DB_PATH)
    else:  # postgresql
        if not hasattr(db_module, 'POSTGRESQL_AVAILABLE') or not db_module.POSTGRESQL_AVAILABLE:
            logger.error("PostgreSQL support is not available. Please install psycopg2 with 'pip install psycopg2-binary'")
            return False
        return db_module.test_connection(DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT)

def init_db():
    """
    Initialize the database by creating tables if they don't exist.
    
    Returns:
        bool: True if successful, False otherwise
    """
    # SQL script to initialize the database (same for both SQLite and PostgreSQL)
    init_script = '''
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
        
        -- Tokens table for storing token information
        CREATE TABLE IF NOT EXISTS tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_address TEXT NOT NULL,
            token_symbol TEXT,
            token_name TEXT,
            token_decimals INTEGER DEFAULT 18,
            chain_id INTEGER DEFAULT 56,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(token_address, chain_id)
        );
        
        -- User tracked tokens table for tracking which tokens a user wants to monitor
        CREATE TABLE IF NOT EXISTS user_tracked_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            token_id INTEGER NOT NULL,
            tracked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY (token_id) REFERENCES tokens(id) ON DELETE CASCADE,
            UNIQUE(user_id, token_id)
        );
        
        -- User balances table for storing historical token balances (append-only)
        CREATE TABLE IF NOT EXISTS user_balances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            wallet_address TEXT NOT NULL,
            token_id INTEGER NOT NULL,
            balance TEXT NOT NULL,  -- Stored as string to handle large numbers
            balance_usd REAL,       -- USD value at time of snapshot, if available
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY (token_id) REFERENCES tokens(id) ON DELETE CASCADE
        );
    '''
    
    # Adjust SQL syntax for PostgreSQL if needed
    if DB_TYPE == 'postgresql':
        # Replace SQLite-specific keywords with PostgreSQL equivalents
        init_script = init_script.replace('INTEGER PRIMARY KEY AUTOINCREMENT', 'SERIAL PRIMARY KEY')
        init_script = init_script.replace('INSERT OR IGNORE', 'INSERT')
        init_script = init_script.replace('NOT IN (SELECT token_address FROM tokens)', 
                                        'NOT IN (SELECT token_address FROM tokens) ON CONFLICT DO NOTHING')
        
    if DB_TYPE == 'sqlite3':
        return db_module.init_db(DB_PATH, init_script)
    else:  # postgresql
        if not hasattr(db_module, 'POSTGRESQL_AVAILABLE') or not db_module.POSTGRESQL_AVAILABLE:
            logger.error("PostgreSQL support is not available. Please install psycopg2 with 'pip install psycopg2-binary'")
            return False
        return db_module.init_db(DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, init_script)

# Make functions from the underlying database module available
retry_on_db_lock = getattr(db_module, 'retry_on_db_lock', None) if DB_TYPE == 'sqlite3' else None
retry_on_db_error = getattr(db_module, 'retry_on_db_error', None) if DB_TYPE == 'postgresql' else None 