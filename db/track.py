"""
Database operations for token tracking functionality.
"""
import logging
from db.connection import execute_query

# Configure module logger
logger = logging.getLogger(__name__)

def get_user_tracked_tokens(user_id):
    """
    Get all tokens tracked by a user.
    
    Args:
        user_id (str): The user ID
        
    Returns:
        list: List of tracked tokens with token info
    """
    return execute_query(
        """
        SELECT utt.id, t.id as token_id, t.token_address, t.token_symbol, t.token_name, t.token_decimals
        FROM user_tracked_tokens utt
        JOIN tokens t ON utt.token_id = t.id
        WHERE utt.user_id = ?
        """,
        (str(user_id),),
        fetch='all'
    )

def get_token_by_address(token_address):
    """
    Get token information by its address.
    
    Args:
        token_address (str): The token address
        
    Returns:
        dict: Token information or None if not found
    """
    return execute_query(
        "SELECT id, token_symbol, token_name, token_decimals FROM tokens WHERE token_address = ?",
        (token_address,),
        fetch='one'
    )

def get_tracked_token_by_id(tracking_id):
    """
    Get detailed information about a tracked token by its tracking ID.
    
    Args:
        tracking_id (int): The tracking entry ID
        
    Returns:
        dict: Tracking and token information or None if not found
    """
    return execute_query(
        """
        SELECT t.id as token_id, t.token_address, t.token_symbol, t.token_name, t.token_decimals
        FROM user_tracked_tokens utt
        JOIN tokens t ON utt.token_id = t.id
        WHERE utt.id = ?
        """,
        (tracking_id,),
        fetch='one'
    )

def add_token(token_address, token_symbol, token_name, token_decimals, chain_id=56):
    """
    Add a new token to the tokens table.
    
    Args:
        token_address (str): The token address
        token_symbol (str): The token symbol
        token_name (str): The token name
        token_decimals (int): The token decimals
        chain_id (int): The chain ID (default: 56 for BSC)
        
    Returns:
        int: The ID of the inserted token or None on failure
    """
    try:
        execute_query(
            """
            INSERT INTO tokens 
            (token_address, token_symbol, token_name, token_decimals, chain_id) 
            VALUES (?, ?, ?, ?, ?)
            """,
            (token_address, token_symbol, token_name, token_decimals, chain_id)
        )
        
        # Get the token ID we just inserted
        token = get_token_by_address(token_address)
        return token.get('id') if token else None
    except Exception as e:
        logger.error(f"Error adding token {token_address}: {e}")
        return None

def track_token(user_id, token_id):
    """
    Start tracking a token for a user.
    
    Args:
        user_id (str): The user ID
        token_id (int): The token ID
        
    Returns:
        int: The ID of the tracking entry or None on failure
    """
    try:
        # Check if user is already tracking this token
        existing = execute_query(
            "SELECT id FROM user_tracked_tokens WHERE user_id = ? AND token_id = ?",
            (str(user_id), token_id),
            fetch='one'
        )
        
        if existing:
            return existing.get('id')
        
        # Add to user_tracked_tokens
        execute_query(
            """
            INSERT INTO user_tracked_tokens 
            (user_id, token_id) 
            VALUES (?, ?)
            """,
            (str(user_id), token_id)
        )
        
        # Get the tracking ID we just inserted
        tracking = execute_query(
            "SELECT id FROM user_tracked_tokens WHERE user_id = ? AND token_id = ?",
            (str(user_id), token_id),
            fetch='one'
        )
        
        return tracking.get('id') if tracking else None
    except Exception as e:
        logger.error(f"Error tracking token {token_id} for user {user_id}: {e}")
        return None

def stop_tracking_token(tracking_id):
    """
    Stop tracking a token for a user.
    
    Args:
        tracking_id (int): The tracking entry ID
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Get token info before deleting
        token_info = execute_query(
            """
            SELECT t.token_symbol, t.token_name
            FROM user_tracked_tokens utt
            JOIN tokens t ON utt.token_id = t.id
            WHERE utt.id = ?
            """,
            (tracking_id,),
            fetch='one'
        )
        
        if not token_info:
            return False
        
        # Remove token from tracked tokens
        execute_query(
            "DELETE FROM user_tracked_tokens WHERE id = ?",
            (tracking_id,)
        )
        
        return True
    except Exception as e:
        logger.error(f"Error stopping tracking for entry {tracking_id}: {e}")
        return False

def record_token_balance(user_id, token_id, wallet_address, balance):
    """
    Record a token balance.
    
    Args:
        user_id (str): The user ID
        token_id (int): The token ID
        wallet_address (str): The wallet address
        balance (str): The token balance
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Insert balance record
        execute_query(
            """
            INSERT INTO user_balances 
            (user_id, wallet_address, token_id, balance) 
            VALUES (?, ?, ?, ?)
            """,
            (str(user_id), wallet_address, token_id, str(balance))
        )
        
        return True
    except Exception as e:
        logger.error(f"Error recording balance for token {token_id} for user {user_id}: {e}")
        return False

def get_token_balance_history(user_id, token_id, limit=30):
    """
    Get historical balance data for a specific token.
    
    Args:
        user_id (str): User ID
        token_id (int): Token ID
        limit (int): Maximum number of records to return
        
    Returns:
        list: List of balance records with timestamp
    """
    try:
        # Get balance history
        balance_history = execute_query(
            """
            SELECT balance, timestamp 
            FROM user_balances 
            WHERE user_id = ? AND token_id = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
            """,
            (str(user_id), token_id, limit),
            fetch='all'
        )
        
        return balance_history
    except Exception as e:
        logger.error(f"Error getting balance history for user {user_id} token {token_id}: {e}")
        return []

def get_all_tracked_tokens_with_wallets():
    """
    Get all tracked tokens across all users with their wallet addresses.
    Used for periodic updates.
    
    Returns:
        list: List of tracked tokens with user and wallet info
    """
    return execute_query(
        """
        SELECT utt.user_id, t.id as token_id, t.token_address, t.token_symbol, w.address as wallet_address
        FROM user_tracked_tokens utt
        JOIN tokens t ON utt.token_id = t.id
        JOIN users u ON utt.user_id = u.user_id
        JOIN wallets w ON utt.user_id = w.user_id
        WHERE w.is_active = 1
        """,
        fetch='all'
    ) 