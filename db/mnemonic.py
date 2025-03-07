"""
Database operations for mnemonic seed phrases.
"""
import logging
import traceback
from db.connection import execute_query
from db.utils import encrypt_data, decrypt_data, hash_user_id
# Configure module logger
logger = logging.getLogger(__name__)

def save_user_mnemonic(user_id, mnemonic, pin=None):
    """
    Save a single mnemonic phrase for a specific user.
    
    Args:
        user_id: The user ID to save the mnemonic for
        mnemonic (str): The mnemonic seed phrase
        pin (str, optional): PIN to use for encryption
        
    Returns:
        bool: True if successful, False otherwise
    """
    if not mnemonic:
        logger.warning(f"No mnemonic provided for user {user_id}")
        return False
    
    # Hash the user ID for database storage
    user_id_str = hash_user_id(user_id)
    logger.debug(f"Saving mnemonic for hashed user_id: {user_id_str}")
    
    encrypted_mnemonic = encrypt_data(mnemonic, user_id, pin)

    # First, create user record if it doesn't exist
    logger.debug(f"Ensuring user {user_id_str} exists in users table")
    execute_query(
        "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
        (user_id_str,)
    )
        
    # Insert or replace mnemonic
    logger.debug(f"Saving encrypted mnemonic for user {user_id_str}")
    execute_query(
        "INSERT OR REPLACE INTO mnemonics (user_id, mnemonic) VALUES (?, ?)",
        (user_id_str, encrypted_mnemonic)
    )
        
    logger.debug(f"Mnemonic saved successfully for user {user_id_str}")
    return True

def get_user_mnemonic(user_id, pin=None):
    """
    Get the mnemonic phrase for a specific user.
    
    Args:
        user_id: The user ID to get the mnemonic for
        pin (str, optional): The PIN to use for decryption
        
    Returns:
        str: The decrypted mnemonic phrase or None if not found
    """
    # Hash the user ID for database lookup
    user_id_str = hash_user_id(user_id)

    logger.debug(f"Querying mnemonic for user: {user_id_str}")
    result = execute_query(
        "SELECT mnemonic FROM mnemonics WHERE user_id = ?",
        (user_id_str,),
        fetch='one'
    )
        
    if not result:
        logger.debug(f"No mnemonic found for user: {user_id_str}")
        return None
        
    # Decrypt and return the mnemonic
    logger.debug(f"Attempting to decrypt mnemonic for user {user_id_str}")
    mnemonic = decrypt_data(result['mnemonic'], user_id, pin)
    
    if mnemonic:
        logger.debug(f"Successfully decrypted mnemonic for user {user_id_str}")
    else:
        logger.error(f"Failed to decrypt mnemonic for user {user_id_str}")
    
    return mnemonic

def delete_user_mnemonic(user_id):
    """
    Delete the mnemonic phrase for a specific user.
    
    Args:
        user_id: The user ID to delete the mnemonic for
        
    Returns:
        bool: True if successful, False otherwise
    """
    # Hash the user ID for database operations
    user_id_str = hash_user_id(user_id)
    
    try:
        execute_query(
            "DELETE FROM mnemonics WHERE user_id = ?", 
            (user_id_str,)
        )
        
        logger.debug(f"Mnemonic deleted for user {user_id_str}")
        return True
    except Exception as e:
        logger.error(f"Error deleting mnemonic for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        return False