"""
Database package initialization.
This module exports the public functions and initializes the database.
"""
import logging

# Import core DB functionality
from db.connection import (
    init_db, execute_query, get_connection,
    create_connection, close_connection, test_connection
)

# Import wallet operations
from db.wallet import (
    get_user_wallet, save_user_wallet, delete_user_wallet,
    get_user_wallets, set_active_wallet, rename_wallet
)

# Import mnemonic operations
from db.mnemonic import (
    save_user_mnemonic, get_user_mnemonic, delete_user_mnemonic
)

# Import PIN operations
from db.pin import (
    save_user_pin, get_user_pin_hash, has_pin
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
    
    # Mnemonic operations
    'save_user_mnemonic', 'get_user_mnemonic', 'delete_user_mnemonic',
    
    # PIN operations
    'save_user_pin', 'get_user_pin_hash', 'has_pin',
] 