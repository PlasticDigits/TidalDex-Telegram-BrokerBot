"""
Database operations for mnemonic seed phrases.
"""
import logging
import traceback
from db.connection import execute_query
from db.utils import encrypt_data, decrypt_data

# Configure module logger
logger = logging.getLogger(__name__)

def save_user_mnemonic(user_id, mnemonic):
    """
    Save a single mnemonic phrase for a specific user.
    
    Args:
        user_id: The user ID to save the mnemonic for
        mnemonic (str): The mnemonic seed phrase
        
    Returns:
        bool: True if successful, False otherwise
    """
    if not mnemonic:
        logger.warning(f"No mnemonic provided for user {user_id}")
        return False
    
    user_id_str = str(user_id)
    logger.debug(f"Saving mnemonic for user {user_id_str}")
    
    try:
        # Encrypt the mnemonic
        logger.debug("Encrypting mnemonic")
        encrypted_mnemonic = encrypt_data(mnemonic, user_id)
        
        # Insert or replace mnemonic
        logger.debug(f"Saving encrypted mnemonic for user {user_id_str}")
        execute_query(
            "INSERT OR REPLACE INTO mnemonics (user_id, mnemonic) VALUES (?, ?)",
            (user_id_str, encrypted_mnemonic)
        )
        
        logger.debug(f"Mnemonic saved successfully for user {user_id_str}")
        return True
    except Exception as e:
        logger.error(f"Error saving mnemonic for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        return False

def get_user_mnemonic(user_id):
    """
    Get the mnemonic phrase for a specific user.
    
    Args:
        user_id: The user ID to get the mnemonic for
        
    Returns:
        str: The decrypted mnemonic phrase or None if not found
    """
    user_id_str = str(user_id)
    
    try:
        result = execute_query(
            "SELECT mnemonic FROM mnemonics WHERE user_id = ?",
            (user_id_str,),
            fetch='one'
        )
        
        if not result:
            return None
        
        # Decrypt and return the mnemonic
        return decrypt_data(result['mnemonic'], user_id)
    except Exception as e:
        logger.error(f"Error retrieving mnemonic for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        return None

def delete_user_mnemonic(user_id):
    """
    Delete the mnemonic phrase for a specific user.
    
    Args:
        user_id: The user ID to delete the mnemonic for
        
    Returns:
        bool: True if successful, False otherwise
    """
    user_id_str = str(user_id)
    
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