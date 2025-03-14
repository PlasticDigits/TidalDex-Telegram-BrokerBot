"""
Database operations for PIN management.
"""
import logging
import traceback
from typing import Optional, Union, Dict, Any, Tuple, List, cast
from db.connections.connection import QueryResult
from db.connection import execute_query
from db.utils import hash_user_id, hash_pin

# Configure module logger
logger = logging.getLogger(__name__)

def save_user_pin(user_id: Union[int, str], pin: str) -> bool:
    """
    Save a PIN for a user to the database.
    
    Args:
        user_id: The user ID
        pin: The plaintext PIN to save as a hash
        
    Returns:
        True if successful, False otherwise
    """
    if not pin:
        logger.warning(f"Invalid PIN provided for user {user_id}")
        return False
    
    # Hash the user ID for database lookup
    user_id_str: str = hash_user_id(user_id)
    pin_hash: str = hash_pin(pin)
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

def get_user_pin_hash(user_id: Union[int, str]) -> Optional[str]:
    """
    Get the hashed PIN for a user from the database.
    
    Args:
        user_id: The user ID
        
    Returns:
        The hashed PIN or None if not found
    """
    # Hash the user ID for database lookup
    user_id_str: str = hash_user_id(user_id)
    
    try:
        # The return type of execute_query with fetch='one' can be Dict[str, Any] or None
        result: QueryResult = execute_query(
            "SELECT pin_hash FROM users WHERE user_id = ?",
            (user_id_str,),
            fetch='one'
        )
        
        if not result or not isinstance(result, dict):
            return None
            
        return result.get('pin_hash')
    except Exception as e:
        logger.error(f"Error retrieving PIN hash for user {user_id_str[:8]}...: {e}")
        logger.error(traceback.format_exc())
        return None

def has_pin(user_id: Union[int, str]) -> bool:
    """
    Check if the user has set a PIN in the database.
    
    Args:
        user_id: The user ID
        
    Returns:
        True if the user has a PIN, False otherwise
    """
    return get_user_pin_hash(user_id) is not None

def verify_pin(user_id: Union[int, str], pin: str) -> bool:
    """
    Verify if a provided PIN matches the stored hash for a user.
    
    Args:
        user_id: The user ID
        pin: The plain text PIN to verify
        
    Returns:
        True if the PIN is correct, False otherwise
    """
    if not pin:
        logger.warning(f"Empty PIN provided for verification")
        return False
    
    # Hash the user ID for logging
    user_id_str: str = hash_user_id(user_id)
    # Hash the PIN for verification
    pin_hash: str = hash_pin(pin)
    
    try:
        # Get the stored PIN hash
        stored_hash: Optional[str] = get_user_pin_hash(user_id)
        
        if not stored_hash:
            logger.warning(f"No PIN hash found for user {user_id_str[:8]}...")
            return False
        
        # Verify the PIN against the stored hash
        is_valid: bool = pin_hash == stored_hash
        
        if is_valid:
            logger.debug(f"PIN verification successful for user {user_id_str[:8]}...")
        else:
            logger.warning(f"PIN verification failed for user {user_id_str[:8]}...")
        
        return is_valid
    except Exception as e:
        logger.error(f"Error verifying PIN for user {user_id_str[:8]}...: {e}")
        logger.error(traceback.format_exc())
        return False 