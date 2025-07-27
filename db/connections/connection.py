"""
Database connection factory.
Provides unified interface for database connections using either SQLite or PostgreSQL.
"""
import logging
import os
from importlib import import_module
from typing import Any, Callable, Dict, List, Optional, Tuple, Union, TypeVar, ContextManager, Generator, cast
from dotenv import load_dotenv
from db.connections.sqlite3_to_postgresql import convert_sql, adapt_params
# Load environment variables
load_dotenv()

# Configure module logger
logger = logging.getLogger(__name__)

# Type definitions
# Using TypeVar for generic connection types
T = TypeVar('T')
F = TypeVar('F', bound=Callable[..., Any])  # TypeVar for decorator functions
DBConnection = Any  # Could be sqlite3.Connection or psycopg2.connection
DBCursor = Any  # Could be sqlite3.Cursor or psycopg2.cursor
QueryResult = Union[List[Dict[str, Any]], Dict[str, Any], int, None]
DBConnectionGenerator = Generator[DBConnection, None, None]

# Get database configuration from environment variables
DB_TYPE: str = os.getenv('DB_TYPE', 'sqlite3').lower()
DB_NAME: str = os.getenv('DB_NAME', 'tidaldex.db')
DB_HOST: str = os.getenv('DB_HOST', 'localhost')
DB_PORT: int = int(os.getenv('DB_PORT', '5432'))
DB_USER: str = os.getenv('DB_USER', 'postgres')
DB_PASSWORD: str = os.getenv('DB_PASSWORD', 'postgres')

# Path for SQLite database
DB_PATH: Optional[str] = None
if DB_TYPE == 'sqlite3':
    if not os.path.isabs(DB_NAME):
        DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'data', DB_NAME)
    else:
        DB_PATH = DB_NAME
else:
    DB_PATH = None

# Import the correct database module based on DB_TYPE
db_module: Any = None
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
    if not os.path.isabs(DB_NAME):
        DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'data', DB_NAME)
    else:
        DB_PATH = DB_NAME
    db_module = import_module('db.connections.sqlite3')

def create_connection() -> Optional[DBConnection]:
    """
    Create a database connection.
    
    Returns:
        Optional[DBConnection]: Database connection object or None on error
    """
    if DB_TYPE == 'sqlite3':
        return db_module.create_connection(DB_PATH)
    else:  # postgresql
        if not hasattr(db_module, 'POSTGRESQL_AVAILABLE') or not db_module.POSTGRESQL_AVAILABLE:
            logger.error("PostgreSQL support is not available. Please install psycopg2 with 'pip install psycopg2-binary'")
            return None
        return db_module.get_connection(DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT)

def get_connection() -> Optional[DBConnection]:
    """
    Get a database connection, creating it if needed.
    
    Returns:
        Optional[DBConnection]: Database connection object or None on error
    """
    if DB_TYPE == 'sqlite3':
        return db_module.get_connection(DB_PATH)
    else:  # postgresql
        if not hasattr(db_module, 'POSTGRESQL_AVAILABLE') or not db_module.POSTGRESQL_AVAILABLE:
            logger.error("PostgreSQL support is not available. Please install psycopg2 with 'pip install psycopg2-binary'")
            return None
        return db_module.get_connection(DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT)

def close_connection(conn: Optional[DBConnection] = None) -> bool:
    """
    Close a database connection.
    
    Args:
        conn (Optional[DBConnection], optional): Connection to close, or the global one if None
        
    Returns:
        bool: True if successful, False otherwise
    """
    return cast(bool, db_module.close_connection(conn))

def get_db_connection() -> DBConnectionGenerator:
    """
    Context manager for database connections.
    
    Yields:
        DBConnection: Database connection object
        
    Raises:
        Exception: If database connection fails
    """
    if DB_TYPE == 'sqlite3':
        yield from db_module.get_db_connection(DB_PATH)
    else:  # postgresql
        if not hasattr(db_module, 'POSTGRESQL_AVAILABLE') or not db_module.POSTGRESQL_AVAILABLE:
            raise ImportError("PostgreSQL support is not available. Please install psycopg2 with 'pip install psycopg2-binary'")
        yield from db_module.get_db_connection(DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT)

def execute_query(query: str, params: Tuple[Any, ...] = (), fetch: Optional[str] = None) -> QueryResult:
    """
    Execute a SQL query and return the results.
    
    Args:
        query (str): SQL query to execute
        params (Tuple[Any, ...]): Query parameters
        fetch (Optional[str]): One of 'all', 'one', or None for SELECT queries
        
    Returns:
        QueryResult: Query results or row count
    """
    if DB_TYPE == 'sqlite3':
        return cast(QueryResult, db_module.execute_query(query, params, fetch, DB_PATH))
    else:  # postgresql
        if not hasattr(db_module, 'POSTGRESQL_AVAILABLE') or not db_module.POSTGRESQL_AVAILABLE:
            logger.error("PostgreSQL support is not available. Please install psycopg2 with 'pip install psycopg2-binary'")
            return None
        # Don't convert the query or params here - let the postgresql module handle it
        return cast(QueryResult, db_module.execute_query(query, params, fetch, DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT))

def test_connection() -> bool:
    """
    Test the database connection by executing a simple query.
    
    Returns:
        bool: True if successful, False otherwise
    """
    if DB_TYPE == 'sqlite3':
        return cast(bool, db_module.test_connection(DB_PATH))
    else:  # postgresql
        if not hasattr(db_module, 'POSTGRESQL_AVAILABLE') or not db_module.POSTGRESQL_AVAILABLE:
            logger.error("PostgreSQL support is not available. Please install psycopg2 with 'pip install psycopg2-binary'")
            return False
        return cast(bool, db_module.test_connection(DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT))

def init_db() -> bool:
    """
    Initialize the database by creating tables if they don't exist.
    
    Returns:
        bool: True if successful, False otherwise
    """
    # SQLite initialization script
    sqlite_init_script: str = '''
        -- Users table first (no foreign keys)
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            pin_hash TEXT,
            account_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            active_wallet_id INTEGER DEFAULT 0,
            mnemonic_index INTEGER DEFAULT 0,
            settings TEXT
        );
        
        -- Wallets table (referring to users)
        CREATE TABLE IF NOT EXISTS wallets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            address TEXT NOT NULL,
            private_key TEXT,
            path TEXT,
            name TEXT DEFAULT 'Default' NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            is_imported BOOLEAN DEFAULT FALSE,
            created_at INTEGER DEFAULT (strftime('%s', 'now')),
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            UNIQUE(user_id, name)
        );
        
        -- Add foreign key for active_wallet_id in users table (circular reference)
        -- SQLite allows for adding this constraint later
        ALTER TABLE users ADD COLUMN IF NOT EXISTS active_wallet_id INTEGER REFERENCES wallets(id) ON DELETE SET NULL;
        
        -- Mnemonics table for seed phrases
        CREATE TABLE IF NOT EXISTS mnemonics (
            user_id TEXT PRIMARY KEY,
            mnemonic TEXT NOT NULL,
            created_at INTEGER DEFAULT (strftime('%s', 'now')),
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
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
            created_at INTEGER DEFAULT (strftime('%s', 'now')),
            UNIQUE(token_address, chain_id)
        );
        
        -- User tracked tokens table for tracking which tokens a user wants to monitor
        CREATE TABLE IF NOT EXISTS user_tracked_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            token_id INTEGER NOT NULL,
            tracked_at INTEGER DEFAULT (strftime('%s', 'now')),
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
            timestamp INTEGER DEFAULT (strftime('%s', 'now')),
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY (token_id) REFERENCES tokens(id) ON DELETE CASCADE
        );
    '''
    
    # PostgreSQL initialization script - customized for PostgreSQL syntax
    postgres_init_script: str = '''
        -- Users table first (no foreign keys)
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            pin_hash TEXT,
            account_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            active_wallet_id INTEGER DEFAULT 0,
            mnemonic_index INTEGER DEFAULT 0,
            settings TEXT
        );
        
        -- Wallets table (referring to users)
        CREATE TABLE IF NOT EXISTS wallets (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            address TEXT NOT NULL,
            private_key TEXT,
            path TEXT,
            name TEXT DEFAULT 'Default' NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            is_imported BOOLEAN DEFAULT FALSE,
            created_at INTEGER DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)::INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            UNIQUE(user_id, name)
        );
        
        -- Mnemonics table for seed phrases
        CREATE TABLE IF NOT EXISTS mnemonics (
            user_id TEXT PRIMARY KEY,
            mnemonic TEXT NOT NULL,
            created_at INTEGER DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)::INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
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
            id SERIAL PRIMARY KEY,
            token_address TEXT NOT NULL,
            token_symbol TEXT,
            token_name TEXT,
            token_decimals INTEGER DEFAULT 18,
            chain_id INTEGER DEFAULT 56,
            created_at INTEGER DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)::INTEGER,
            UNIQUE(token_address, chain_id)
        );

        -- User tracked tokens table for tracking which tokens a user wants to monitor
        CREATE TABLE IF NOT EXISTS user_tracked_tokens (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            token_id INTEGER NOT NULL,
            tracked_at INTEGER DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)::INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY (token_id) REFERENCES tokens(id) ON DELETE CASCADE,
            UNIQUE(user_id, token_id)
        );
        
        -- User balances table for storing historical token balances (append-only)
        CREATE TABLE IF NOT EXISTS user_balances (
            id SERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            wallet_address TEXT NOT NULL,
            token_id INTEGER NOT NULL,
            balance TEXT NOT NULL,  -- Stored as string to handle large numbers
            balance_usd REAL,       -- USD value at time of snapshot, if available
            timestamp INTEGER DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)::INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
            FOREIGN KEY (token_id) REFERENCES tokens(id) ON DELETE CASCADE
        );
    '''
        
    if DB_TYPE == 'sqlite3':
        return cast(bool, db_module.init_db(DB_PATH, sqlite_init_script))
    else:  # postgresql
        if not hasattr(db_module, 'POSTGRESQL_AVAILABLE') or not db_module.POSTGRESQL_AVAILABLE:
            logger.error("PostgreSQL support is not available. Please install psycopg2 with 'pip install psycopg2-binary'")
            return False
        # For PostgreSQL, use the PostgreSQL-specific script
        return cast(bool, db_module.init_db(DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, postgres_init_script))

# Make functions from the underlying database module available
retry_on_db_lock: Optional[Callable[[int, float], Callable[[F], F]]] = getattr(db_module, 'retry_on_db_lock', None) if DB_TYPE == 'sqlite3' else None
retry_on_db_error: Optional[Callable[[int, float], Callable[[F], F]]] = getattr(db_module, 'retry_on_db_error', None) if DB_TYPE == 'postgresql' else None 