"""
Database operations for wallets.
"""
import logging
import traceback
from db.connection import execute_query
from db.utils import encrypt_data, decrypt_data, hash_user_id
from db.pin import has_pin
from db.mnemonic import get_user_mnemonic
from wallet.mnemonic import derive_wallet_from_mnemonic
import time

# Configure module logger
logger = logging.getLogger(__name__)

def get_user_wallet(user_id, wallet_name=None, pin=None):
    """
    Get the active wallet for a specific user.
    
    Args:
        user_id: The user ID to get the wallet for
        wallet_name: Optional wallet name to retrieve a specific wallet
        pin (str, optional): The PIN to use for decryption
        
    Returns:
        dict: The wallet data or None if not found
    """
    # Hash the user ID for database lookup
    user_id_str = hash_user_id(user_id)
    
    try:
        # If wallet_name is provided, get that specific wallet
        if wallet_name:
            logger.debug(f"Querying specific wallet {wallet_name} for user: {user_id_str}")
            result = execute_query(
                "SELECT * FROM wallets WHERE user_id = ? AND name = ?",
                (user_id_str, wallet_name),
                fetch='one'
            )
        else:
            # Otherwise, get the active wallet
            logger.debug(f"Querying active wallet for user: {user_id_str}")
            result = execute_query(
                "SELECT * FROM wallets WHERE user_id = ? AND is_active = 1",
                (user_id_str,),
                fetch='one'
            )
        
        if not result:
            if wallet_name:
                logger.debug(f"No wallet with ID {wallet_name} found for user: {user_id_str}")
            else:
                logger.debug(f"No active wallet found for user: {user_id_str}")
            return None
        
        # Decrypt private key if present
        wallet_data = dict(result)
        if wallet_data.get('private_key'):
            logger.debug(f"Attempting to decrypt private key for wallet {wallet_name} for user {user_id_str}")
            try:
                private_key = decrypt_data(wallet_data['private_key'], user_id, pin)
                if private_key:
                    wallet_data['private_key'] = private_key
                    logger.debug(f"Successfully decrypted private key for wallet {wallet_name} for user {user_id_str}")
                    
                else:
                    logger.error(f"Failed to decrypt private key for wallet {wallet_name} for user {user_id_str}")
            except Exception as e:
                logger.error(f"Error decrypting private key for wallet {wallet_name} for user {user_id_str}: {e}")
                logger.error(traceback.format_exc())
                wallet_data['private_key'] = None
        elif wallet_data.get('path'):
            logger.debug(f"Wallet {wallet_name} has no private key, but has a path. It is a mnemonic wallet.")
            try:
                mnemonic = get_user_mnemonic(user_id, pin)
                if mnemonic:
                    wallet_data['private_key'] = derive_wallet_from_mnemonic(mnemonic, wallet_data['path'])
                    logger.debug(f"Successfully derived private key for wallet {wallet_name} for user {user_id_str}")
                else:
                    logger.error(f"Failed to retrieve mnemonic for user {user_id_str}")
            except Exception as e:
                logger.error(f"Error deriving private key from mnemonicfor wallet {wallet_name} for user {user_id_str}: {e}")
                logger.error(traceback.format_exc())
                wallet_data['private_key'] = None
                    
        return wallet_data
    except Exception as e:
        logger.error(f"Error retrieving wallet for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        return None

def save_user_wallet(user_id, wallet_data, wallet_name="Default", pin=None):
    """
    Save a wallet for a specific user.
    
    Args:
        user_id: The user ID to save the wallet for
        wallet_data (dict): The wallet data to save
        wallet_name (str): The name of the wallet
        pin (str, optional): PIN to use for encryption
        
    Returns:
        bool: True if successful, False otherwise
    """
    if not wallet_data or 'address' not in wallet_data:
        logger.warning(f"No wallet data provided for user {user_id}")
        return False
    
    # Hash the user ID for database storage
    user_id_str = hash_user_id(user_id)
    logger.debug(f"Saving wallet '{wallet_name}' for hashed user_id: {user_id_str}")
    logger.debug(f"Wallet address: {wallet_data.get('address')}")
    
    try:
        # First, create user record if it doesn't exist
        logger.debug(f"Ensuring user {user_id_str} exists in users table")
        execute_query(
            "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
            (user_id_str,)
        )
        
        # Encrypt the private key if present
        private_key = wallet_data.get('private_key')
        encrypted_private_key = None
        
        if private_key:
            logger.debug("Encrypting private key")
            encrypted_private_key = encrypt_data(private_key, user_id, pin)
            
            if not encrypted_private_key:
                logger.error(f"Failed to encrypt private key for user {user_id_str}")
                return False
        
        # Check if this wallet name already exists for this user
        existing_wallet = execute_query(
            "SELECT id FROM wallets WHERE user_id = ? AND name = ?",
            (user_id_str, wallet_name),
            fetch='one'
        )
        
        if existing_wallet:
            # Update existing wallet
            logger.debug(f"Updating existing wallet '{wallet_name}' for user {user_id_str}")
            execute_query(
                """
                UPDATE wallets SET 
                    address = ?,
                    private_key = ?,
                    path = ?
                WHERE user_id = ? AND name = ?
                """,
                (
                    wallet_data.get('address'),
                    encrypted_private_key,
                    wallet_data.get('path'),
                    user_id_str,
                    wallet_name
                )
            )
        else:
            # Insert new wallet
            logger.debug(f"Inserting new wallet '{wallet_name}' for user {user_id_str}")
            
            # Get current active status for all wallets
            has_wallets = execute_query(
                "SELECT COUNT(*) as count FROM wallets WHERE user_id = ?",
                (user_id_str,),
                fetch='one'
            )
            
            # If this is the first wallet, set it as active. Otherwise, inactive by default.
            is_active = 1 if not has_wallets or has_wallets['count'] == 0 else 0
            
            execute_query(
                """
                INSERT INTO wallets (user_id, address, private_key, path, name, is_active)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id_str,
                    wallet_data.get('address'),
                    encrypted_private_key,
                    wallet_data.get('path'),
                    wallet_name,
                    is_active
                )
            )
            
            # If this is the first wallet and we're making it active, deactivate all others
            if is_active == 1:
                execute_query(
                    """
                    UPDATE wallets SET is_active = 0
                    WHERE user_id = ? AND name != ?
                    """,
                    (user_id_str, wallet_name)
                )
        
        logger.debug(f"Wallet saved successfully for user {user_id_str}")
        return True
    except Exception as e:
        logger.error(f"Error saving wallet for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        return False

def delete_user_wallet(user_id, wallet_name=None):
    """
    Delete a specific wallet or all wallets for a user.
    
    Args:
        user_id: The user ID to delete the wallet for
        wallet_name (str, optional): The name of the wallet to delete, or None to delete all
        
    Returns:
        bool: True if successful, False otherwise
    """
    # Hash the user ID for database operations
    user_id_str = hash_user_id(user_id)
    
    try:
        if wallet_name:
            # Delete a specific wallet
            wallet = execute_query(
                "SELECT id, is_active FROM wallets WHERE user_id = ? AND name = ?", 
                (user_id_str, wallet_name),
                fetch='one'
            )
            
            if not wallet:
                logger.warning(f"Wallet '{wallet_name}' not found for user {user_id_str}")
                return False
            
            # Delete the wallet
            execute_query(
                "DELETE FROM wallets WHERE user_id = ? AND name = ?", 
                (user_id_str, wallet_name)
            )
            
            # If this was the active wallet, set a new active wallet
            if wallet['is_active'] == 1:
                # Get another wallet if available
                new_active = execute_query(
                    "SELECT id FROM wallets WHERE user_id = ? LIMIT 1", 
                    (user_id_str,),
                    fetch='one'
                )
                
                if new_active:
                    execute_query(
                        "UPDATE wallets SET is_active = 1 WHERE id = ?", 
                        (new_active['id'],)
                    )
            
            logger.debug(f"Deleted wallet '{wallet_name}' for user {user_id_str}")
        else:
            # Delete all wallets for this user
            execute_query("DELETE FROM wallets WHERE user_id = ?", (user_id_str,))
            
            # Delete mnemonic if exists
            execute_query("DELETE FROM mnemonics WHERE user_id = ?", (user_id_str,))
            
            logger.debug(f"Deleted all wallets for user {user_id_str}")
        
        return True
    except Exception as e:
        logger.error(f"Error deleting wallet for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        return False

def get_user_wallets(user_id, pin=None):
    """
    Get all wallets for a specific user.
    
    Args:
        user_id: The user ID to get wallets for
        pin (str, optional): PIN to use for decryption
        
    Returns:
        dict: A dictionary of wallet names to wallet info (address and active status)
    """
    # Hash the user ID for database lookup
    user_id_str = hash_user_id(user_id)
    
    try:
        # Get all wallets with their active status
        wallets_rows = execute_query(
            "SELECT name, address, is_active FROM wallets WHERE user_id = ?", 
            (user_id_str,),
            fetch='all'
        )
        
        wallets = {}
        for wallet in wallets_rows:
            wallets[wallet['name']] = {
                'address': wallet['address'],
                'is_active': wallet['is_active'] == 1
            }
        
        return wallets
    except Exception as e:
        logger.error(f"Error getting wallets for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        return {}

def set_active_wallet(user_id, wallet_name):
    """
    Set the active wallet for a user.
    
    Args:
        user_id: The user ID to set the active wallet for
        wallet_name (str): The name of the wallet to set as active
        
    Returns:
        bool: True if successful, False otherwise
    """
    # Hash the user ID for database operations
    user_id_str = hash_user_id(user_id)
    
    try:
        # Check if wallet exists
        wallet_exists = execute_query(
            "SELECT id FROM wallets WHERE user_id = ? AND name = ?", 
            (user_id_str, wallet_name),
            fetch='one'
        )
        
        if not wallet_exists:
            logger.warning(f"Wallet '{wallet_name}' does not exist for user {user_id_str}")
            return False
        
        # First, set all wallets to inactive
        execute_query(
            "UPDATE wallets SET is_active = 0 WHERE user_id = ?",
            (user_id_str,)
        )
        
        # Then set the selected wallet to active
        execute_query(
            "UPDATE wallets SET is_active = 1 WHERE user_id = ? AND name = ?",
            (user_id_str, wallet_name)
        )
        
        logger.debug(f"Set wallet '{wallet_name}' as active for user {user_id_str}")
        return True
    except Exception as e:
        logger.error(f"Error setting active wallet for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        return False

def rename_wallet(user_id, new_name):
    """
    Rename the currently active wallet for a user.
    
    Args:
        user_id: The user ID
        new_name (str): The new name for the wallet
        
    Returns:
        bool: True if successful, False otherwise
        str: The old name of the wallet or error message if False
    """
    # Hash the user ID for database operations
    user_id_str = hash_user_id(user_id)
    logger.debug(f"Renaming active wallet for hashed user_id: {user_id_str}")
    
    # Basic length validation
    if not new_name:
        return False, "Invalid wallet name. Name cannot be empty."
    
    if len(new_name) > 32:
        return False, "Invalid wallet name. Name must not exceed 32 characters."
    
    if len(new_name) < 3:
        return False, "Invalid wallet name. Name must be at least 3 characters long."
    
    # Check for leading/trailing whitespace
    if new_name != new_name.strip():
        return False, "Wallet name cannot have leading or trailing spaces."
        
    # Check for dangerous characters (SQL injection, command execution)
    import re
    if re.search(r'[\'";`<>]', new_name):
        return False, "Wallet name contains invalid characters. Avoid using: ' \" ; ` < >"
    
    # Check against reserved names
    reserved_names = ["default", "wallet", "main", "primary", "backup", "test", "admin", "system"]
    if new_name.lower() in reserved_names:
        return False, f"'{new_name}' is a reserved name and cannot be used."
    
    try:
        # Check if wallet with new name already exists
        existing = execute_query(
            "SELECT id FROM wallets WHERE user_id = ? AND name = ?", 
            (user_id_str, new_name),
            fetch='one'
        )
        
        if existing:
            return False, f"Wallet with name '{new_name}' already exists."
        
        # Get active wallet
        active_wallet = execute_query(
            "SELECT id, name FROM wallets WHERE user_id = ? AND is_active = 1", 
            (user_id_str,),
            fetch='one'
        )
        
        if not active_wallet:
            return False, "No active wallet found."
        
        old_name = active_wallet['name']
        
        # Update the wallet name
        execute_query(
            "UPDATE wallets SET name = ? WHERE id = ?",
            (new_name, active_wallet['id'])
        )
        
        # Enhanced logging for security audit
        logger.info(f"Wallet renamed from '{old_name}' to '{new_name}' for user ID hash: {user_id_str[:10]}...")
        return True, old_name
    except Exception as e:
        logger.error(f"Error renaming wallet for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        return False, str(e)

def get_user_wallets_with_keys(user_id, pin=None):
    """
    Get all wallets for a specific user, including private keys.
    
    Args:
        user_id: The user ID to get wallets for
        pin (str, optional): PIN to use for decryption
        
    Returns:
        list: A list of wallet objects with complete data including decrypted private keys
    """
    # Hash the user ID for database lookup
    user_id_str = hash_user_id(user_id)
    logger.debug(f"Getting all wallets with keys for hashed user_id: {user_id_str}")
    
    # Check if PIN is required but not provided
    pin_is_set = has_pin(user_id)
    if pin_is_set and pin is None:
        logger.warning(f"User {user_id_str} has PIN set but none provided for wallet retrieval")
    
    try:
        # Get all wallets with complete data
        wallets_rows = execute_query(
            "SELECT * FROM wallets WHERE user_id = ?", 
            (user_id_str,),
            fetch='all'
        )
        
        if not wallets_rows:
            logger.debug(f"No wallets found for user: {user_id_str}")
            return []
        
        logger.debug(f"Found {len(wallets_rows)} wallets for user: {user_id_str}")
        
        # Process each wallet
        wallets = []
        for wallet_row in wallets_rows:
            # Convert to dictionary
            wallet_data = dict(wallet_row)
            
            # Decrypt private key if present
            if wallet_data.get('private_key'):
                try:
                    logger.debug(f"Attempting to decrypt private key for wallet {wallet_data['name']}")
                    wallet_data['private_key'] = decrypt_data(wallet_data['private_key'], user_id, pin)
                    if wallet_data['private_key'] is None:
                        logger.error(f"Private key decryption failed for wallet {wallet_data['name']}, result is None")
                        # Add a flag indicating decryption failure
                        wallet_data['decryption_failed'] = True
                        
                        # Add a flag indicating PIN is required if user has PIN but didn't provide one
                        if pin_is_set and pin is None:
                            wallet_data['pin_required'] = True
                except Exception as e:
                    logger.error(f"Exception during private key decryption for wallet {wallet_data['name']}: {e}")
                    logger.error(traceback.format_exc())
                    # Add error details to the wallet data
                    wallet_data['decryption_failed'] = True
                    wallet_data['decryption_error'] = str(e)
                    
                    # Add a flag indicating PIN is required if user has PIN but didn't provide one
                    if pin_is_set and pin is None:
                        wallet_data['pin_required'] = True
            
            # Add to the list
            wallets.append(wallet_data)
        
        logger.debug(f"Successfully retrieved all wallets for user: {user_id_str}")
        return wallets
    except Exception as e:
        logger.error(f"Error getting wallets with keys for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        return []

def get_active_wallet_name(user_id):
    """
    Get the name of the currently active wallet for a user.
    
    Args:
        user_id: The user ID to get the active wallet name for
        
    Returns:
        str: The name of the active wallet or "Default" if not found
    """
    # Hash the user ID for database lookup
    user_id_str = hash_user_id(user_id)
    
    try:
        # Query for the active wallet
        active_wallet = execute_query(
            "SELECT name FROM wallets WHERE user_id = ? AND is_active = 1",
            (user_id_str,),
            fetch='one'
        )
        
        if active_wallet:
            return active_wallet['name']
        else:
            # Return "Default" if no active wallet is found
            return "Default"
    except Exception as e:
        logger.error(f"Error getting active wallet name for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        return "Default" 