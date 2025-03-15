"""
Database operations for mnemonic seed phrases.
"""
import logging
import traceback
from typing import Optional, Union, Dict, Any, List, Tuple, cast
from db.connections.connection import QueryResult
from db.connection import execute_query
from db.utils import encrypt_data, decrypt_data, hash_user_id
# Configure module logger
logger = logging.getLogger(__name__)

def save_user_mnemonic(user_id: Union[int, str], mnemonic: str, pin: Optional[str] = None) -> bool:
    """
    Save a single mnemonic phrase for a specific user.
    Resets the mnenmonic index to 0.
    
    Args:
        user_id: The user ID to save the mnemonic for
        mnemonic: The mnemonic seed phrase
        pin: PIN to use for encryption
        
    Returns:
        True if successful, False otherwise
    """
    if not mnemonic:
        logger.warning(f"No mnemonic provided for user {user_id}")
        return False
    
    # Hash the user ID for database storage
    user_id_str: str = hash_user_id(user_id)
    logger.debug(f"Saving mnemonic for hashed user_id: {user_id_str}")
    
    encrypted_mnemonic: Optional[str] = encrypt_data(mnemonic, user_id, pin)
    if not encrypted_mnemonic:
        logger.error(f"Failed to encrypt mnemonic for user {user_id_str}")
        return False

    # First, create user record if it doesn't exist
    # Explicitly set active_wallet_id to NULL to avoid foreign key constraint
    logger.debug(f"Ensuring user {user_id_str} exists in users table")
    execute_query(
        "INSERT OR IGNORE INTO users (user_id, active_wallet_id) VALUES (?, NULL)",
        (user_id_str,)
    )
        
    # Insert or replace mnemonic
    logger.debug(f"Saving encrypted mnemonic for user {user_id_str}")
    execute_query(
        "INSERT OR REPLACE INTO mnemonics (user_id, mnemonic) VALUES (?, ?)",
        (user_id_str, encrypted_mnemonic)
    )

    # Reset the mnemonic index to 0
    logger.debug(f"Resetting mnemonic index for user {user_id_str}")
    execute_query(
        "UPDATE users SET mnemonic_index = 0 WHERE user_id = ?",
        (user_id_str,)
    )
        
    logger.debug(f"Mnemonic saved successfully for user {user_id_str}")
    return True

def increment_user_mnemonic_index(user_id: Union[int, str]) -> bool:
    """
    Increment the mnemonic index for a specific user.
    """
    user_id_str: str = hash_user_id(user_id)

    try:
        result: QueryResult = execute_query(
            "UPDATE users SET mnemonic_index = mnemonic_index + 1 WHERE user_id = ?",
            (user_id_str,)
        )
        
        if not result or not isinstance(result, dict):
            logger.debug(f"No mnemonic index found for user: {user_id_str}")
            return False
        
        return True
    except Exception as e:
        logger.error(f"Error incrementing mnemonic index for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        return False
    

def get_user_mnemonic_index(user_id: Union[int, str]) -> Optional[int]:
    """
    Get the mnemonic index for a specific user.
    """
    user_id_str: str = hash_user_id(user_id)
    
    try:
        result: QueryResult = execute_query(
            "SELECT mnemonic_index FROM users WHERE user_id = ?",
            (user_id_str,),
            fetch='one'
        )
        
        if not result or not isinstance(result, dict):
            logger.debug(f"No mnemonic index found for user: {user_id_str}")
            return None
        
        return cast(Optional[int], result['mnemonic_index'])
    except Exception as e:
        logger.error(f"Error getting mnemonic index for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        return None

def get_user_mnemonic(user_id: Union[int, str], pin: Optional[str] = None) -> Optional[str]:
    """
    Get the mnemonic phrase for a specific user.
    
    Args:
        user_id: The user ID to get the mnemonic for
        pin: The PIN to use for decryption
        
    Returns:
        The decrypted mnemonic phrase or None if not found
    """
    # Hash the user ID for database lookup
    user_id_str: str = hash_user_id(user_id)

    logger.debug(f"Querying mnemonic for user: {user_id_str}")
    result: QueryResult = execute_query(
        "SELECT mnemonic FROM mnemonics WHERE user_id = ?",
        (user_id_str,),
        fetch='one'
    )
        
    if not result or not isinstance(result, dict):
        logger.debug(f"No mnemonic found for user: {user_id_str}")
        return None
        
    # Decrypt and return the mnemonic
    logger.debug(f"Attempting to decrypt mnemonic for user {user_id_str}")
    mnemonic: Optional[str] = decrypt_data(result['mnemonic'], user_id, pin)
    
    if mnemonic:
        logger.debug(f"Successfully decrypted mnemonic for user {user_id_str}")
    else:
        logger.error(f"Failed to decrypt mnemonic for user {user_id_str}")
    
    return mnemonic

def delete_user_mnemonic(user_id: Union[int, str]) -> bool:
    """
    Delete the mnemonic phrase for a specific user.
    
    Args:
        user_id: The user ID to delete the mnemonic for
        
    Returns:
        True if successful, False otherwise
    """
    # Hash the user ID for database operations
    user_id_str: str = hash_user_id(user_id)
    
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