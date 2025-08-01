"""
Database connection factory for PostgreSQL.
Provides interface for PostgreSQL database connections.
"""
import logging
import os
from importlib import import_module
from typing import Any, Callable, Dict, List, Optional, Tuple, Union, TypeVar, ContextManager, Generator, cast
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure module logger
logger = logging.getLogger(__name__)

# Type definitions
T = TypeVar('T')
F = TypeVar('F', bound=Callable[..., Any])  # TypeVar for decorator functions
DBConnection = Any  # psycopg2.connection
DBCursor = Any  # psycopg2.cursor
QueryResult = Union[List[Dict[str, Any]], Dict[str, Any], int, None]
DBConnectionGenerator = Generator[DBConnection, None, None]

# Get database configuration from environment variables
DB_NAME: str = os.getenv('DB_NAME', 'tidaldex')
DB_HOST: str = os.getenv('DB_HOST', 'localhost')
DB_PORT: int = int(os.getenv('DB_PORT', '5432'))
DB_USER: str = os.getenv('DB_USER', 'postgres')
DB_PASSWORD: str = os.getenv('DB_PASSWORD', 'postgres')

# Import PostgreSQL database module
db_module: Any = None
try:
    db_module = import_module('db.connections.postgresql')
    logger.info(f"Using PostgreSQL database at {DB_HOST}:{DB_PORT}/{DB_NAME}")
except ImportError as e:
    logger.error(f"Error importing PostgreSQL module: {e}")
    logger.error("Please install psycopg2 with 'pip install psycopg2-binary'")
    raise ImportError("PostgreSQL support is required") from e

def create_connection() -> Optional[DBConnection]:
    """
    Create a database connection.
    
    Returns:
        Optional[DBConnection]: Database connection object or None on error
    """
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
    if not hasattr(db_module, 'POSTGRESQL_AVAILABLE') or not db_module.POSTGRESQL_AVAILABLE:
        logger.error("PostgreSQL support is not available. Please install psycopg2 with 'pip install psycopg2-binary'")
        return None
    return cast(QueryResult, db_module.execute_query(query, params, fetch, DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT))

def test_connection() -> bool:
    """
    Test the database connection by executing a simple query.
    
    Returns:
        bool: True if successful, False otherwise
    """
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
    # PostgreSQL initialization script
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
        
        -- X accounts table for storing X (Twitter) OAuth connections
        CREATE TABLE IF NOT EXISTS x_accounts (
            user_id TEXT PRIMARY KEY,
            x_user_id TEXT NOT NULL,
            x_username TEXT NOT NULL,
            x_display_name TEXT,
            x_profile_image_url TEXT,
            access_token TEXT NOT NULL,
            refresh_token TEXT,
            token_expires_at INTEGER,
            scope TEXT NOT NULL,
            connected_at INTEGER NOT NULL,
            last_updated INTEGER NOT NULL,
            follower_count INTEGER,
            follower_fetched_at INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        );
        
        -- Application table for version management and instance control
        CREATE TABLE IF NOT EXISTS application (
            id INTEGER PRIMARY KEY,
            version INTEGER NOT NULL,
            updated_at INTEGER DEFAULT EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)::INTEGER
        );
    '''
    
    if not hasattr(db_module, 'POSTGRESQL_AVAILABLE') or not db_module.POSTGRESQL_AVAILABLE:
        logger.error("PostgreSQL support is not available. Please install psycopg2 with 'pip install psycopg2-binary'")
        return False
    
    result = cast(bool, db_module.init_db(DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, postgres_init_script))
    if result:
        # Run X accounts table migration after successful initialization
        try:
            from db.x_account import migrate_x_accounts_table
            migrate_x_accounts_table()
        except Exception as e:
            logger.warning(f"Error running X accounts migration: {e}")
    return result

# Make functions from the underlying database module available
retry_on_db_error: Optional[Callable[[int, float], Callable[[F], F]]] = getattr(db_module, 'retry_on_db_error', None) 