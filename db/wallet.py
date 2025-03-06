"""
Database operations for wallets.
"""
import logging
import traceback
from db.connection import execute_query
from db.utils import encrypt_data, decrypt_data, hash_user_id

# Configure module logger
logger = logging.getLogger(__name__)

def get_user_wallet(user_id):
    """
    Get active wallet for a specific user.
    
    Args:
        user_id: The user ID to get the wallet for
        
    Returns:
        dict: Wallet data with decrypted private key or None if not found
    """
    # Hash the user ID for database lookup
    user_id_str = hash_user_id(user_id)
    logger.debug(f"Getting wallet for hashed user_id: {user_id_str}")
    
    try:
        # Get the active wallet directly from the wallets table using is_active flag
        logger.debug(f"Querying active wallet for user: {user_id_str}")
        wallet = execute_query(
            "SELECT * FROM wallets WHERE user_id = ? AND is_active = 1", 
            (user_id_str,), 
            fetch='one'
        )
        
        # If no active wallet is found, try to get any wallet for this user
        if not wallet:
            logger.debug(f"No active wallet found, getting any wallet for user: {user_id_str}")
            wallet = execute_query(
                "SELECT * FROM wallets WHERE user_id = ? LIMIT 1",
                (user_id_str,),
                fetch='one'
            )
            
            # If we found a wallet but it's not set as active, update it to be active
            if wallet:
                logger.debug(f"Setting wallet {wallet['name']} as active")
                execute_query(
                    "UPDATE wallets SET is_active = 1 WHERE id = ?",
                    (wallet['id'],)
                )
        
        if not wallet:
            logger.debug(f"No wallet found for user: {user_id_str}")
            return None
        
        logger.debug(f"Found wallet with name: {wallet['name']}")
        
        # Convert to dictionary
        wallet_data = dict(wallet)
        
        # Decrypt private key if present
        if wallet_data.get('private_key'):
            logger.debug("Decrypting private key")
            wallet_data['private_key'] = decrypt_data(wallet_data['private_key'], user_id)
        
        logger.debug(f"Successfully retrieved wallet for user: {user_id_str}")
        return wallet_data
    except Exception as e:
        logger.error(f"Error getting wallet for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        return None

def save_user_wallet(user_id, wallet_data, wallet_name="Default"):
    """
    Save a wallet for a specific user.
    
    Args:
        user_id: The user ID to save the wallet for
        wallet_data (dict): The wallet data to save
        wallet_name (str): The name of the wallet
        
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
        
        # Get count of existing wallets
        existing_wallet_count = execute_query(
            "SELECT COUNT(*) as count FROM wallets WHERE user_id = ?",
            (user_id_str,),
            fetch='one'
        )
        
        # Determine if this should be the active wallet (first wallet is active by default)
        is_active = 1 if existing_wallet_count is None or existing_wallet_count['count'] == 0 else 0
        logger.debug(f"Setting wallet is_active={is_active}")
        
        # Prepare wallet data
        address = wallet_data.get('address')
        path = wallet_data.get('path')
        
        # Encrypt private key if present
        private_key = None
        if 'private_key' in wallet_data and wallet_data['private_key']:
            logger.debug("Encrypting private key")
            private_key = encrypt_data(wallet_data['private_key'], user_id)
        
        # Insert or update wallet
        logger.debug(f"Saving wallet data for {wallet_name}")
        execute_query(
            """
            INSERT OR REPLACE INTO wallets 
            (user_id, address, private_key, path, name, is_active)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id_str, address, private_key, path, wallet_name, is_active)
        )
        
        logger.debug(f"Wallet '{wallet_name}' saved successfully for user {user_id_str}")
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

def get_user_wallets(user_id):
    """
    Get all wallets for a specific user.
    
    Args:
        user_id: The user ID to get wallets for
        
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