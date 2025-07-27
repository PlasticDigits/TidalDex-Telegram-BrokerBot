"""
Database operations for X (Twitter) account connections.
"""
import logging
import traceback
from typing import Optional, Union, Dict, Any, TypedDict, cast, List
from db.connections.connection import QueryResult
from db.connection import execute_query
from db.utils import encrypt_data, decrypt_data, hash_user_id
import time

# Configure module logger
logger = logging.getLogger(__name__)

# Define TypedDict for X account data
class XAccountData(TypedDict, total=False):
    """TypedDict for X account data"""
    user_id: str
    x_user_id: str
    x_username: str
    x_display_name: Optional[str]
    x_profile_image_url: Optional[str]
    access_token: str
    refresh_token: Optional[str]
    token_expires_at: Optional[int]
    scope: str
    connected_at: int
    last_updated: int

def save_x_account_connection(
    user_id: Union[int, str],
    x_user_id: str,
    x_username: str,
    access_token: str,
    refresh_token: Optional[str] = None,
    token_expires_at: Optional[int] = None,
    scope: str = "tweet.read users.read follows.read like.read",
    x_display_name: Optional[str] = None,
    x_profile_image_url: Optional[str] = None,
    pin: Optional[str] = None
) -> bool:
    """
    Save or update X account connection for a user.
    
    Args:
        user_id: The Telegram user ID
        x_user_id: The X (Twitter) user ID
        x_username: The X (Twitter) username
        access_token: OAuth access token
        refresh_token: OAuth refresh token (optional)
        token_expires_at: Token expiration timestamp (optional)
        scope: OAuth scopes granted
        x_display_name: X display name (optional)
        x_profile_image_url: X profile image URL (optional)
        pin: User PIN for encryption
        
    Returns:
        True if successful, False otherwise
    """
    user_id_str: str = hash_user_id(user_id)
    current_time: int = int(time.time())
    
    try:
        # Encrypt sensitive data
        encrypted_access_token = encrypt_data(access_token, user_id, pin)
        encrypted_refresh_token = None
        if refresh_token:
            encrypted_refresh_token = encrypt_data(refresh_token, user_id, pin)
        
        # Check if connection already exists
        existing = execute_query(
            "SELECT user_id FROM x_accounts WHERE user_id = ?",
            (user_id_str,),
            fetch='one'
        )
        
        logger.info(f"🔍 Debug: Existing check result: {existing} (type: {type(existing)})")
        logger.info(f"🔍 Debug: Will {'UPDATE' if existing else 'INSERT'}")
        
        if existing:
            # Update existing connection
            logger.info(f"Updating X account connection for user: {user_id_str}")
            result = execute_query(
                """
                UPDATE x_accounts SET 
                    x_user_id = ?, x_username = ?, x_display_name = ?, x_profile_image_url = ?,
                    access_token = ?, refresh_token = ?, token_expires_at = ?, scope = ?, last_updated = ?
                WHERE user_id = ?
                """,
                (x_user_id, x_username, x_display_name, x_profile_image_url,
                 encrypted_access_token, encrypted_refresh_token, token_expires_at, scope, current_time, user_id_str)
            )
            logger.info(f"🔍 Debug: UPDATE result: {result} (type: {type(result)})")
        else:
            # Insert new connection
            logger.info(f"Creating new X account connection for user: {user_id_str}")
            result = execute_query(
                """
                INSERT INTO x_accounts 
                (user_id, x_user_id, x_username, x_display_name, x_profile_image_url, 
                 access_token, refresh_token, token_expires_at, scope, connected_at, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id_str, x_user_id, x_username, x_display_name, x_profile_image_url,
                 encrypted_access_token, encrypted_refresh_token, token_expires_at, scope, current_time, current_time)
            )
            logger.info(f"🔍 Debug: INSERT result: {result} (type: {type(result)})")
        
        # Add immediate verification to debug the issue
        if result is not None:
            # Verify the record was actually saved
            query_sql = "SELECT user_id, x_username FROM x_accounts WHERE user_id = ?"
            query_params = (user_id_str,)
            fetch_param = 'one'
            
            logger.info(f"🔍 Debug: About to execute verification query:")
            logger.info(f"🔍 Debug: SQL: {query_sql}")
            logger.info(f"🔍 Debug: Params: {query_params}")
            logger.info(f"🔍 Debug: Fetch: '{fetch_param}' (type: {type(fetch_param)})")
            
            verification = execute_query(query_sql, query_params, fetch=fetch_param)
            logger.info(f"🔍 Debug: Verification query result type: {type(verification)}, value: {verification}")
            
            if verification and isinstance(verification, dict):
                logger.info(f"✅ Verification successful - X account record exists for user {user_id_str} with username @{verification.get('x_username')}")
            elif verification:
                logger.warning(f"⚠️ Verification returned unexpected type: {type(verification)} = {verification}")
                # Try a different verification approach
                count_check = execute_query(
                    "SELECT COUNT(*) as count FROM x_accounts WHERE user_id = ?",
                    (user_id_str,),
                    fetch='one'
                )
                logger.info(f"🔍 Debug: Count check result: {count_check}")
                if count_check and isinstance(count_check, dict) and count_check.get('count', 0) > 0:
                    logger.info(f"✅ Count verification successful - record exists for user {user_id_str}")
                else:
                    logger.error(f"❌ Count verification FAILED - no record found for user {user_id_str}")
                    return False
            else:
                logger.error(f"❌ Verification FAILED - X account record NOT found immediately after save for user {user_id_str}")
                return False
        
        return result is not None
        
    except Exception as e:
        logger.error(f"Error saving X account connection for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        return False

def get_x_account_connection(user_id: Union[int, str], pin: Optional[str] = None) -> Optional[XAccountData]:
    """
    Get X account connection for a user.
    
    Args:
        user_id: The Telegram user ID
        pin: User PIN for decryption
        
    Returns:
        X account data or None if not found
    """
    user_id_str: str = hash_user_id(user_id)
    
    try:
        logger.info(f"Getting X account connection for user: {user_id_str}")
        result = execute_query(
            "SELECT * FROM x_accounts WHERE user_id = ?",
            (user_id_str,),
            fetch='one'
        )
        
        if not result or not isinstance(result, dict):
            logger.error(f"No X account connection found for user: {user_id_str}")
            return None
        
        # Decrypt sensitive data
        x_account_data: XAccountData = cast(XAccountData, dict(result))
        
        if x_account_data.get('access_token'):
            try:
                access_token = decrypt_data(x_account_data['access_token'], user_id, pin)
                if access_token:
                    x_account_data['access_token'] = access_token
                    logger.debug(f"Successfully decrypted access token for user {user_id_str}")
                else:
                    logger.error(f"Failed to decrypt access token for user {user_id_str} - data corruption or wrong PIN")
                    return None
            except Exception as e:
                logger.error(f"Error decrypting access token for user {user_id_str}: {e}")
                logger.error(f"This may indicate data corruption - consider cleaning up record for user {user_id_str}")
                return None
        
        if x_account_data.get('refresh_token'):
            try:
                refresh_token = decrypt_data(x_account_data['refresh_token'], user_id, pin)
                if refresh_token:
                    x_account_data['refresh_token'] = refresh_token
                else:
                    logger.warning(f"Failed to decrypt refresh token for user {user_id_str}")
                    x_account_data['refresh_token'] = None
            except Exception as e:
                logger.warning(f"Error decrypting refresh token for user {user_id_str}: {e}")
                x_account_data['refresh_token'] = None
        
        logger.info(f"Successfully retrieved and decrypted X account data for user {user_id_str}")
        return x_account_data
        
    except Exception as e:
        logger.error(f"Error getting X account connection for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        return None

def delete_x_account_connection(user_id: Union[int, str]) -> bool:
    """
    Delete X account connection for a user.
    
    Args:
        user_id: The Telegram user ID
        
    Returns:
        True if successful, False otherwise
    """
    user_id_str: str = hash_user_id(user_id)
    
    try:
        result = execute_query(
            "DELETE FROM x_accounts WHERE user_id = ?",
            (user_id_str,)
        )
        
        logger.info(f"Deleted X account connection for user: {user_id_str}")
        return result is not None
        
    except Exception as e:
        logger.error(f"Error deleting X account connection for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        return False

def has_x_account_connection(user_id: Union[int, str]) -> bool:
    """
    Check if user has a valid X account connection that can be decrypted.
    
    Args:
        user_id: The Telegram user ID
        
    Returns:
        True if user has a valid connection, False otherwise
    """
    user_id_str: str = hash_user_id(user_id)
    
    try:
        logger.debug(f"Checking X account connection for user_id_str: {user_id_str}")
        
        # First check if record exists
        result = execute_query(
            "SELECT access_token FROM x_accounts WHERE user_id = ? LIMIT 1",
            (user_id_str,),
            fetch='one'
        )
        
        if not result or not isinstance(result, dict):
            logger.debug(f"No X account record found for user {user_id_str}")
            return False
        
        # Check if we can decrypt the access token (validates data integrity)
        encrypted_access_token = result.get('access_token')
        if not encrypted_access_token:
            logger.warning(f"X account record exists but no access_token for user {user_id_str}")
            return False
        
        # Try to decrypt without PIN first (for users without PIN requirement)
        try:
            test_decrypt = decrypt_data(encrypted_access_token, user_id, None)
            if test_decrypt:
                logger.debug(f"Successfully validated X connection (no PIN) for user {user_id_str}")
                return True
        except Exception as e:
            logger.debug(f"Decryption without PIN failed for user {user_id_str}: {e}")
        
        # If decryption without PIN fails, the data might require a PIN or be corrupted
        # We'll return False to indicate the connection is not usable without proper decryption
        logger.warning(f"X account record exists but cannot decrypt data for user {user_id_str}")
        return False
        
    except Exception as e:
        logger.error(f"Error checking X account connection for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        return False

def cleanup_corrupted_x_account(user_id: Union[int, str]) -> bool:
    """
    Clean up corrupted X account record for a user.
    
    Args:
        user_id: The Telegram user ID
        
    Returns:
        True if successful, False otherwise
    """
    user_id_str: str = hash_user_id(user_id)
    
    try:
        result = execute_query(
            "DELETE FROM x_accounts WHERE user_id = ?",
            (user_id_str,)
        )
        
        logger.info(f"Cleaned up corrupted X account record for user: {user_id_str}")
        return result is not None
        
    except Exception as e:
        logger.error(f"Error cleaning up corrupted X account for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        return False

def create_x_accounts_table() -> bool:
    """
    Create the x_accounts table if it doesn't exist.
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # SQLite table creation
        sqlite_sql = """
        CREATE TABLE IF NOT EXISTS x_accounts (
            user_id TEXT PRIMARY KEY,
            x_user_id TEXT NOT NULL,
            x_username TEXT NOT NULL,
            x_display_name TEXT,
            x_profile_image_url TEXT,
            access_token TEXT NOT NULL,
            refresh_token TEXT,
            token_expires_at INTEGER,
            scope TEXT NOT NULL,
            connected_at INTEGER NOT NULL,
            last_updated INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        );
        """
        
        result = execute_query(sqlite_sql)
        logger.info("X accounts table created successfully")
        return result is not None
        
    except Exception as e:
        logger.error(f"Error creating X accounts table: {e}")
        logger.error(traceback.format_exc())
        return False 