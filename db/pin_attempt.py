"""
Database operations for PIN attempt tracking.
Manages storing and retrieving PIN attempt data in the database.
"""
import logging
import traceback
import time
from typing import Optional, Union, Dict, Any, Tuple, cast
from db.connections.connection import QueryResult
from db.connection import execute_query
from db.utils import hash_user_id

# Configure module logger
logger = logging.getLogger(__name__)

def create_pin_attempts_table() -> bool:
    """
    Create the pin_attempts table if it doesn't exist.
    Should be called during database initialization.
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Create pin_attempts table if it doesn't exist
        execute_query('''
            CREATE TABLE IF NOT EXISTS pin_attempts (
                user_id TEXT PRIMARY KEY,
                failure_count INTEGER NOT NULL DEFAULT 0,
                last_attempt_time INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            );
        ''')
        
        logger.info("PIN attempts table initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Error creating PIN attempts table: {e}")
        logger.error(traceback.format_exc())
        return False

def get_pin_attempt_data(user_id: Union[int, str]) -> Optional[Dict[str, int]]:
    """
    Get PIN attempt data for a specific user.
    
    Args:
        user_id: The user ID
        
    Returns:
        dict: PIN attempt data (failure_count and last_attempt_time) or None if not found
    """
    # Hash the user ID for database lookup
    user_id_str: str = hash_user_id(user_id)
    
    try:
        # The return type of execute_query with fetch='one' can be Dict[str, Any] or None
        result: QueryResult = execute_query(
            "SELECT failure_count, last_attempt_time FROM pin_attempts WHERE user_id = %s",
            (user_id_str,),
            fetch='one'
        )
        
        if not result or not isinstance(result, dict):
            return None
            
        return {
            'failure_count': result.get('failure_count', 0),
            'last_attempt_time': result.get('last_attempt_time', 0)
        }
    except Exception as e:
        logger.error(f"Error retrieving PIN attempt data for user {user_id_str[:8]}...: {e}")
        logger.error(traceback.format_exc())
        return None

def save_pin_attempt_data(user_id: Union[int, str], failure_count: int, last_attempt_time: Optional[int] = None) -> bool:
    """
    Save PIN attempt data for a specific user.
    
    Args:
        user_id: The user ID
        failure_count (int): The number of failed attempts
        last_attempt_time (int, optional): The timestamp of the last attempt, or current time if None
        
    Returns:
        bool: True if successful, False otherwise
    """
    # Hash the user ID for database lookup
    user_id_str: str = hash_user_id(user_id)
    
    # Use current time if not provided
    if last_attempt_time is None:
        last_attempt_time = int(time.time())
    
    try:
        # First ensure user exists in users table
        execute_query(
            "INSERT INTO users (user_id, active_wallet_id) VALUES (%s, NULL) ON CONFLICT (user_id) DO NOTHING",
            (user_id_str,)
        )
        
        # Insert or update pin attempt data
        execute_query(
            """
            INSERT INTO pin_attempts (user_id, failure_count, last_attempt_time)
            VALUES (%s, %s, %s)
            ON CONFLICT(user_id) DO UPDATE SET
                failure_count = %s,
                last_attempt_time = %s
            """,
            (user_id_str, failure_count, last_attempt_time, failure_count, last_attempt_time)
        )
        
        logger.debug(f"PIN attempt data saved for user {user_id_str[:8]}...")
        return True
    except Exception as e:
        logger.error(f"Error saving PIN attempt data for user {user_id_str[:8]}...: {e}")
        logger.error(traceback.format_exc())
        return False

def reset_pin_attempts(user_id: Union[int, str]) -> bool:
    """
    Reset PIN attempt counter for a specific user.
    
    Args:
        user_id: The user ID
        
    Returns:
        bool: True if successful, False otherwise
    """
    # Hash the user ID for database lookup
    user_id_str: str = hash_user_id(user_id)
    
    try:
        # Reset failure count and update last attempt time
        current_time: int = int(time.time())
        execute_query(
            """
            INSERT INTO pin_attempts (user_id, failure_count, last_attempt_time)
            VALUES (%s, 0, %s)
            ON CONFLICT(user_id) DO UPDATE SET
                failure_count = 0,
                last_attempt_time = %s
            """,
            (user_id_str, current_time, current_time)
        )
        
        logger.debug(f"PIN attempts reset for user {user_id_str[:8]}...")
        return True
    except Exception as e:
        logger.error(f"Error resetting PIN attempts for user {user_id_str[:8]}...: {e}")
        logger.error(traceback.format_exc())
        return False

def increment_pin_attempt(user_id: Union[int, str]) -> Tuple[bool, int]:
    """
    Increment the PIN attempt counter for a specific user.
    
    Args:
        user_id: The user ID
        
    Returns:
        tuple: (bool, int) - (success, new_failure_count)
    """
    # Hash the user ID for database lookup
    user_id_str: str = hash_user_id(user_id)
    current_time: int = int(time.time())
    
    try:
        # Get current attempt data
        attempt_data: Optional[Dict[str, int]] = get_pin_attempt_data(user_id)
        
        if attempt_data:
            new_failure_count: int = attempt_data.get('failure_count', 0) + 1
        else:
            new_failure_count = 1
        
        # Update with incremented count
        success: bool = save_pin_attempt_data(user_id, new_failure_count, current_time)
        
        return success, new_failure_count
    except Exception as e:
        logger.error(f"Error incrementing PIN attempts for user {user_id_str[:8]}...: {e}")
        logger.error(traceback.format_exc())
        return False, 0 