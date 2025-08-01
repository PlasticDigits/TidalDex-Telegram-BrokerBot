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
import httpx

# Configure module logger
logger = logging.getLogger(__name__)

async def refetch_follower_count(access_token: str) -> Optional[int]:
    """
    Refetch follower count from X API.
    
    Args:
        access_token: Valid X API access token
        
    Returns:
        Follower count or None if failed
    """
    try:
        async with httpx.AsyncClient() as client:
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            
            response = await client.get(
                'https://api.twitter.com/2/users/me?user.fields=public_metrics',
                headers=headers
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch follower count from X API: {response.status_code}")
                return None
            
            user_data = response.json()
            public_metrics = user_data.get('data', {}).get('public_metrics', {})
            follower_count = public_metrics.get('followers_count')
            
            if follower_count is not None:
                logger.info(f"Successfully fetched follower count: {follower_count}")
                return int(follower_count)
            else:
                logger.error("No follower count found in X API response")
                return None
                
    except Exception as e:
        logger.error(f"Error refetching follower count: {e}")
        return None

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
    follower_count: Optional[int]
    follower_fetched_at: Optional[int]

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
    pin: Optional[str] = None,
    follower_count: Optional[int] = None,
    follower_fetched_at: Optional[int] = None
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
        follower_count: X account follower count (optional)
        follower_fetched_at: Timestamp when follower count was fetched (optional)
        
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
            "SELECT user_id FROM x_accounts WHERE user_id = %s",
            (user_id_str,),
            fetch='one'
        )
        
        if existing:
            # Update existing connection
            logger.info(f"Updating X account connection for user: {user_id_str}")
            result = execute_query(
                """
                UPDATE x_accounts SET 
                            x_user_id = %s, x_username = %s, x_display_name = %s, x_profile_image_url = %s,
        access_token = %s, refresh_token = %s, token_expires_at = %s, scope = %s, last_updated = %s,
        follower_count = %s, follower_fetched_at = %s
        WHERE user_id = %s
                """,
                (x_user_id, x_username, x_display_name, x_profile_image_url,
                 encrypted_access_token, encrypted_refresh_token, token_expires_at, scope, current_time,
                 follower_count, follower_fetched_at, user_id_str)
            )
        else:
            # Insert new connection
            logger.info(f"Creating new X account connection for user: {user_id_str}")
            result = execute_query(
                """
                INSERT INTO x_accounts 
                (user_id, x_user_id, x_username, x_display_name, x_profile_image_url, 
                 access_token, refresh_token, token_expires_at, scope, connected_at, last_updated,
                 follower_count, follower_fetched_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (user_id_str, x_user_id, x_username, x_display_name, x_profile_image_url,
                 encrypted_access_token, encrypted_refresh_token, token_expires_at, scope, current_time, current_time,
                 follower_count, follower_fetched_at)
            )
        
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
            "SELECT * FROM x_accounts WHERE user_id = %s",
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

async def get_x_account_connection_with_fresh_followers(user_id: Union[int, str], pin: Optional[str] = None) -> Optional[XAccountData]:
    """
    Get X account connection for a user and refresh follower data if needed.
    
    Args:
        user_id: The Telegram user ID
        pin: User PIN for decryption
        
    Returns:
        X account data with fresh follower data or None if not found
    """
    user_id_str: str = hash_user_id(user_id)
    
    # Get the basic account data first
    x_account_data = get_x_account_connection(user_id, pin)
    if not x_account_data:
        return None
    
    # Check if follower data needs refreshing (7 days = 604800 seconds)
    current_time = int(time.time())
    follower_fetched_at = x_account_data.get('follower_fetched_at')
    
    if (follower_fetched_at is None or 
        current_time - follower_fetched_at > 604800):  # 7 days in seconds
        
        logger.info(f"Follower data expired for user {user_id_str}, refetching...")
        
        try:
            # Refetch follower count
            new_follower_count = await refetch_follower_count(x_account_data['access_token'])
            
            if new_follower_count is not None:
                # Update the database with new follower data
                logger.info(f"Updating follower count for user {user_id_str}: {new_follower_count}")
                
                execute_query(
                    "UPDATE x_accounts SET follower_count = %s, follower_fetched_at = %s, last_updated = %s WHERE user_id = %s",
                    (new_follower_count, current_time, current_time, user_id_str)
                )
                
                # Update the returned data
                x_account_data['follower_count'] = new_follower_count
                x_account_data['follower_fetched_at'] = current_time
                x_account_data['last_updated'] = current_time
            else:
                logger.warning(f"Failed to refetch follower count for user {user_id_str}")
                
        except Exception as e:
            logger.error(f"Error refetching follower count for user {user_id_str}: {e}")
    
    return x_account_data

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
            "DELETE FROM x_accounts WHERE user_id = %s",
            (user_id_str,)
        )
        
        logger.info(f"Deleted X account connection for user: {user_id_str}")
        return result is not None
        
    except Exception as e:
        logger.error(f"Error deleting X account connection for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        return False

def has_x_account_connection(user_id: Union[int, str], pin: Optional[str] = None) -> bool:
    """
    Check if user has a valid X account connection that can be decrypted.
    
    Args:
        user_id: The Telegram user ID
        pin: User's PIN for decryption (optional)
        
    Returns:
        True if user has a valid connection, False otherwise
    """
    user_id_str: str = hash_user_id(user_id)
    
    try:
        logger.debug(f"Checking X account connection for user_id_str: {user_id_str}")
        
        # First check if record exists
        result = execute_query(
            "SELECT access_token FROM x_accounts WHERE user_id = %s LIMIT 1",
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
        
        # Check if user has a PIN to determine the right decryption approach
        from services.pin.PINManager import pin_manager
        user_has_pin = pin_manager.has_pin(user_id)
        
        if user_has_pin:
            # User has a PIN, so we need PIN for decryption
            if not pin:
                logger.debug(f"X account record exists but PIN required for user {user_id_str}")
                return False
            
            try:
                test_decrypt = decrypt_data(encrypted_access_token, user_id, pin)
                if test_decrypt:
                    logger.debug(f"Successfully validated X connection (with PIN) for user {user_id_str}")
                    return True
                else:
                    logger.warning(f"X account record exists but PIN decryption failed for user {user_id_str}")
                    return False
            except Exception as e:
                logger.warning(f"Decryption with PIN failed for user {user_id_str}: {e}")
                return False
        else:
            # User doesn't have a PIN, decrypt without PIN
            try:
                test_decrypt = decrypt_data(encrypted_access_token, user_id, None)
                if test_decrypt:
                    logger.debug(f"Successfully validated X connection (no PIN) for user {user_id_str}")
                    return True
                else:
                    logger.warning(f"X account record exists but decryption failed for user {user_id_str}")
                    return False
            except Exception as e:
                logger.warning(f"Decryption without PIN failed for user {user_id_str}: {e}")
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
            "DELETE FROM x_accounts WHERE user_id = %s",
            (user_id_str,)
        )
        
        logger.info(f"Cleaned up corrupted X account record for user: {user_id_str}")
        return result is not None
        
    except Exception as e:
        logger.error(f"Error cleaning up corrupted X account for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        return False

def migrate_x_accounts_table() -> bool:
    """
    Migrate the x_accounts table to add follower columns if they don't exist.
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # PostgreSQL: Use information_schema to check column existence
        result = execute_query("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'x_accounts' 
            AND table_schema = 'public'
        """, fetch='all')
        
        # If result is None or empty, table doesn't exist
        if not result:
            logger.info("x_accounts table doesn't exist, will be created with new schema")
            return True
        
        # Extract column names from result
        columns = [row['column_name'] if isinstance(row, dict) else row[0] for row in result]
        
        has_follower_count = 'follower_count' in columns
        has_follower_fetched_at = 'follower_fetched_at' in columns
        
        if has_follower_count and has_follower_fetched_at:
            logger.info("X accounts table already has follower columns")
            return True
        
        # Add missing columns
        if not has_follower_count:
            logger.info("Adding follower_count column to x_accounts table")
            execute_query("ALTER TABLE x_accounts ADD COLUMN follower_count INTEGER")
        
        if not has_follower_fetched_at:
            logger.info("Adding follower_fetched_at column to x_accounts table")
            execute_query("ALTER TABLE x_accounts ADD COLUMN follower_fetched_at INTEGER")
        
        logger.info("Successfully migrated x_accounts table")
        return True
        
    except Exception as e:
        logger.error(f"Error migrating x_accounts table: {e}")
        logger.error(traceback.format_exc())
        return False

def create_x_accounts_table() -> bool:
    """
    Create the x_accounts table if it doesn't exist and migrate existing tables.
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # First run migration to add columns to existing tables
        if not migrate_x_accounts_table():
            logger.error("Failed to migrate x_accounts table")
            return False
        
        # PostgreSQL table creation  
        postgres_sql = """
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
            follower_count INTEGER,
            follower_fetched_at INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        );
        """
        
        result = execute_query(postgres_sql)
        logger.info("X accounts table created/verified successfully")
        return result is not None
        
    except Exception as e:
        logger.error(f"Error creating X accounts table: {e}")
        logger.error(traceback.format_exc())
        return False 