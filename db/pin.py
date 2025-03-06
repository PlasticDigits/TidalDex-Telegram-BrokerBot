"""
Database operations for PIN management.
"""
import logging
import traceback
from db.connection import execute_query
from db.utils import hash_user_id

# Configure module logger
logger = logging.getLogger(__name__)

def save_user_pin(user_id, pin_hash):
    """
    Save a hashed PIN for a user to the database.
    
    Args:
        user_id: The user ID
        pin_hash (str): The hashed PIN to save
        
    Returns:
        bool: True if successful, False otherwise
    """
    if not pin_hash:
        logger.warning(f"Invalid PIN hash provided for user {user_id}")
        return False
    
    # Hash the user ID for database lookup
    user_id_str = hash_user_id(user_id)
    
    try:
        # Update the user's PIN hash in the database
        execute_query(
            "UPDATE users SET pin_hash = ? WHERE user_id = ?",
            (pin_hash, user_id_str)
        )
        
        logger.info(f"PIN saved for user {user_id_str[:8]}...")
        return True
    except Exception as e:
        logger.error(f"Error saving PIN for user {user_id_str[:8]}...: {e}")
        logger.error(traceback.format_exc())
        return False

def get_user_pin_hash(user_id):
    """
    Get the hashed PIN for a user from the database.
    
    Args:
        user_id: The user ID
        
    Returns:
        str: The hashed PIN or None if not found
    """
    # Hash the user ID for database lookup
    user_id_str = hash_user_id(user_id)
    
    try:
        result = execute_query(
            "SELECT pin_hash FROM users WHERE user_id = ?",
            (user_id_str,),
            fetch='one'
        )
        
        if not result:
            return None
            
        return result.get('pin_hash')
    except Exception as e:
        logger.error(f"Error retrieving PIN hash for user {user_id_str[:8]}...: {e}")
        logger.error(traceback.format_exc())
        return None

def has_pin(user_id):
    """
    Check if the user has set a PIN in the database.
    
    Args:
        user_id: The user ID
        
    Returns:
        bool: True if the user has a PIN, False otherwise
    """
    return get_user_pin_hash(user_id) is not None 