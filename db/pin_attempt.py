"""
Database operations for PIN attempt tracking.
Manages storing and retrieving PIN attempt data in the database.
"""
import logging
import traceback
import time
from db.connection import execute_query
from db.utils import hash_user_id

# Configure module logger
logger = logging.getLogger(__name__)

def create_pin_attempts_table():
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

def get_pin_attempt_data(user_id):
    """
    Get PIN attempt data for a specific user.
    
    Args:
        user_id: The user ID
        
    Returns:
        dict: PIN attempt data (failure_count and last_attempt_time) or None if not found
    """
    # Hash the user ID for database lookup
    user_id_str = hash_user_id(user_id)
    
    try:
        result = execute_query(
            "SELECT failure_count, last_attempt_time FROM pin_attempts WHERE user_id = ?",
            (user_id_str,),
            fetch='one'
        )
        
        if not result:
            return None
            
        return {
            'failure_count': result.get('failure_count', 0),
            'last_attempt_time': result.get('last_attempt_time', 0)
        }
    except Exception as e:
        logger.error(f"Error retrieving PIN attempt data for user {user_id_str[:8]}...: {e}")
        logger.error(traceback.format_exc())
        return None

def save_pin_attempt_data(user_id, failure_count, last_attempt_time=None):
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
    user_id_str = hash_user_id(user_id)
    
    # Use current time if not provided
    if last_attempt_time is None:
        last_attempt_time = int(time.time())
    
    try:
        # First ensure user exists in users table
        execute_query(
            "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
            (user_id_str,)
        )
        
        # Insert or update pin attempt data
        execute_query(
            """
            INSERT INTO pin_attempts (user_id, failure_count, last_attempt_time)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                failure_count = ?,
                last_attempt_time = ?
            """,
            (user_id_str, failure_count, last_attempt_time, failure_count, last_attempt_time)
        )
        
        logger.debug(f"PIN attempt data saved for user {user_id_str[:8]}...")
        return True
    except Exception as e:
        logger.error(f"Error saving PIN attempt data for user {user_id_str[:8]}...: {e}")
        logger.error(traceback.format_exc())
        return False

def reset_pin_attempts(user_id):
    """
    Reset PIN attempt counter for a specific user.
    
    Args:
        user_id: The user ID
        
    Returns:
        bool: True if successful, False otherwise
    """
    # Hash the user ID for database lookup
    user_id_str = hash_user_id(user_id)
    
    try:
        # Reset failure count and update last attempt time
        current_time = int(time.time())
        execute_query(
            """
            INSERT INTO pin_attempts (user_id, failure_count, last_attempt_time)
            VALUES (?, 0, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                failure_count = 0,
                last_attempt_time = ?
            """,
            (user_id_str, current_time, current_time)
        )
        
        logger.debug(f"PIN attempts reset for user {user_id_str[:8]}...")
        return True
    except Exception as e:
        logger.error(f"Error resetting PIN attempts for user {user_id_str[:8]}...: {e}")
        logger.error(traceback.format_exc())
        return False

def increment_pin_attempt(user_id):
    """
    Increment the PIN attempt counter for a specific user.
    
    Args:
        user_id: The user ID
        
    Returns:
        tuple: (bool, int) - (success, new_failure_count)
    """
    # Hash the user ID for database lookup
    user_id_str = hash_user_id(user_id)
    current_time = int(time.time())
    
    try:
        # Get current attempt data
        attempt_data = get_pin_attempt_data(user_id)
        
        if attempt_data:
            new_failure_count = attempt_data.get('failure_count', 0) + 1
        else:
            new_failure_count = 1
        
        # Update with incremented count
        success = save_pin_attempt_data(user_id, new_failure_count, current_time)
        
        return success, new_failure_count
    except Exception as e:
        logger.error(f"Error incrementing PIN attempts for user {user_id_str[:8]}...: {e}")
        logger.error(traceback.format_exc())
        return False, 0 