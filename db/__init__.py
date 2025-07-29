"""
Database package initialization.
This module exports the public functions and initializes the database.
"""
import logging
from typing import Dict, List, Optional, Any, Union

# Import core DB functionality
from db.connection import (
    init_db, execute_query, get_connection,
    create_connection, close_connection, test_connection
)

# Import wallet operations and types
from db.wallet import (
    get_user_wallet, save_user_wallet, delete_user_wallet,
    get_user_wallets, set_active_wallet, rename_wallet,
    WalletData  # Export the WalletData TypedDict
)

# Import mnemonic operations
from db.mnemonic import (
    save_user_mnemonic, get_user_mnemonic, delete_user_mnemonic
)

# Import PIN operations
from db.pin import (
    save_user_pin, get_user_pin_hash, has_pin, verify_pin
)

# Import PIN attempt operations
from db.pin_attempt import (
    get_pin_attempt_data, save_pin_attempt_data, reset_pin_attempts,
    increment_pin_attempt, create_pin_attempts_table
)

# Import X account operations
from db.x_account import (
    save_x_account_connection, get_x_account_connection, get_x_account_connection_with_fresh_followers,
    delete_x_account_connection, has_x_account_connection, create_x_accounts_table, XAccountData, cleanup_corrupted_x_account,
    migrate_x_accounts_table
)

# Import types
from db.connections.connection import (
    DBConnection, DBCursor, QueryResult, DBConnectionGenerator
)

# Configure module logger
logger = logging.getLogger(__name__)

# Public exports
__all__ = [
    # Connection management
    'init_db', 'execute_query', 'get_connection', 
    'create_connection', 'close_connection', 'test_connection',
    
    # Wallet operations
    'get_user_wallet', 'save_user_wallet', 'delete_user_wallet',
    'get_user_wallets', 'set_active_wallet', 'rename_wallet',
    'WalletData',  # Include the TypedDict in exports
    
    # Mnemonic operations
    'save_user_mnemonic', 'get_user_mnemonic', 'delete_user_mnemonic',
    
    # PIN operations
    'save_user_pin', 'get_user_pin_hash', 'has_pin', 'verify_pin',
    
    # PIN attempt operations
    'get_pin_attempt_data', 'save_pin_attempt_data', 'reset_pin_attempts',
    'increment_pin_attempt',
    
    # X account operations
    'save_x_account_connection', 'get_x_account_connection', 'get_x_account_connection_with_fresh_followers',
    'delete_x_account_connection', 'has_x_account_connection', 'cleanup_corrupted_x_account', 
    'create_x_accounts_table', 'migrate_x_accounts_table', 'XAccountData',
    
    # Type definitions
    'QueryResult',
] 