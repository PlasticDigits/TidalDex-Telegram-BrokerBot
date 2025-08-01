"""
Database operations for token tracking functionality.
"""
import logging
import traceback
from typing import List, Dict, Any, Optional, Union, Tuple, cast
from db.connections.connection import QueryResult
from db.connection import execute_query
from db.utils import hash_user_id

# Configure module logger
logger = logging.getLogger(__name__)

def get_user_tracked_tokens(user_id: Union[int, str]) -> List[Dict[str, Any]]:
    """
    Get all tokens tracked by a user.
    
    Args:
        user_id: The user ID
        
    Returns:
        List of tracked tokens with token info
    """
    user_id_str: str = hash_user_id(user_id) if isinstance(user_id, int) else str(user_id)
    
    result: QueryResult = execute_query(
        """
        SELECT utt.id, t.id as token_id, t.token_address, t.token_symbol, t.token_name, t.token_decimals
        FROM user_tracked_tokens utt
        JOIN tokens t ON utt.token_id = t.id
        WHERE utt.user_id = %s
        """,
        (user_id_str,),
        fetch='all'
    )
    
    # Ensure we return a list of dictionaries
    if result is None:
        return []
    elif isinstance(result, list):
        return result
    else:
        logger.error(f"Unexpected result type from execute_query: {type(result)}")
        return []

def get_token_by_address(token_address: str) -> Optional[Dict[str, Any]]:
    """
    Get token information by its address.
    
    Args:
        token_address: The token address
        
    Returns:
        Token information or None if not found
    """
    result: QueryResult = execute_query(
        "SELECT id, token_address, token_symbol, token_name, token_decimals, chain_id FROM tokens WHERE token_address = %s",
        (token_address,),
        fetch='one'
    )
    
    if not result or not isinstance(result, dict):
        return None
    
    return result

def get_tracked_token_by_id(tracking_id: int) -> Optional[Dict[str, Any]]:
    """
    Get tracked token information by its ID.
    
    Args:
        tracking_id: The tracking ID
        
    Returns:
        Tracked token information or None if not found
    """
    result: QueryResult = execute_query(
        """
        SELECT utt.id, t.id as token_id, t.token_address, t.token_symbol, t.token_name, t.token_decimals
        FROM user_tracked_tokens utt
        JOIN tokens t ON utt.token_id = t.id
        WHERE utt.id = %s
        """,
        (tracking_id,),
        fetch='one'
    )
    
    if not result or not isinstance(result, dict):
        return None
    
    return result

def add_token(token_address: str, token_symbol: str, token_name: str, token_decimals: int, chain_id: int = 56) -> Optional[int]:
    """
    Add a new token to the tokens table.
    
    Args:
        token_address: The token address
        token_symbol: The token symbol
        token_name: The token name
        token_decimals: The token decimals
        chain_id: The chain ID (default: 56 for BSC)
        
    Returns:
        The ID of the inserted token or None on failure
    """
    try:
        execute_query(
            """
            INSERT INTO tokens 
            (token_address, token_symbol, token_name, token_decimals, chain_id) 
            VALUES (%s, %s, %s, %s, %s)
            """,
            (token_address, token_symbol, token_name, token_decimals, chain_id)
        )
        
        # Get the token ID we just inserted
        token: Optional[Dict[str, Any]] = get_token_by_address(token_address)
        return token.get('id') if token else None
    except Exception as e:
        logger.error(f"Error adding token {token_address}: {e}")
        return None

def track_token(user_id: Union[int, str], token_id: int) -> Optional[int]:
    """
    Add a token to a user's tracked tokens.
    
    Args:
        user_id: The user ID
        token_id: The token ID to track
        
    Returns:
        The ID of the tracking entry or None on failure
    """
    user_id_str: str = str(hash_user_id(user_id))
    
    try:
        # Check if token is already tracked by this user
        result: QueryResult = execute_query(
            "SELECT id FROM user_tracked_tokens WHERE user_id = %s AND token_id = %s",
            (user_id_str, token_id),
            fetch='one'
        )
        
        existing = None
        if result and isinstance(result, dict):
            existing = result
        
        if existing:
            logger.info(f"Token ID {token_id} is already tracked by user {user_id_str}")
            return existing.get('id')
        
        # Insert the tracking entry
        execute_query(
            "INSERT INTO user_tracked_tokens (user_id, token_id) VALUES (%s, %s)",
            (user_id_str, token_id)
        )
        
        # Get the newly created tracking ID
        new_tracking_entry: QueryResult = execute_query(
            "SELECT id FROM user_tracked_tokens WHERE user_id = %s AND token_id = %s",
            (user_id_str, token_id),
            fetch='one'
        )
        
        if not new_tracking_entry or not isinstance(new_tracking_entry, dict):
            return None
            
        return new_tracking_entry.get('id')
    except Exception as e:
        logger.error(f"Error tracking token {token_id} for user {user_id_str[:8]}...: {e}")
        return None

def stop_tracking_token(tracking_id: int) -> bool:
    """
    Remove a token from a user's tracked tokens.
    
    Args:
        tracking_id: The tracking entry ID
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Get the tracking entry first to confirm it exists
        tracking = execute_query(
            "SELECT id FROM user_tracked_tokens WHERE id = %s",
            (tracking_id,),
            fetch='one'
        )
        
        if not tracking:
            logger.info(f"Tracking entry {tracking_id} not found")
            return False
        
        # Delete the tracking entry
        execute_query(
            "DELETE FROM user_tracked_tokens WHERE id = %s",
            (tracking_id,)
        )
        
        return True
    except Exception as e:
        logger.error(f"Error stopping tracking for entry {tracking_id}: {e}")
        return False

def record_token_balance(user_id: Union[int, str], token_id: int, wallet_address: str, balance: int) -> bool:
    """
    Record the current balance of a token for a user.
    
    Args:
        user_id: The user ID
        token_id: The token ID
        wallet_address: The wallet address
        balance: The token balance
        
    Returns:
        True if successful, False otherwise
    """
    user_id_str: str = hash_user_id(user_id) if isinstance(user_id, int) else str(user_id)
    
    try:
        # Insert the balance record
        execute_query(
            """
            INSERT INTO token_balances 
            (user_id, token_id, wallet_address, balance, timestamp) 
            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
            """,
            (user_id_str, token_id, wallet_address, balance)
        )
        
        return True
    except Exception as e:
        logger.error(f"Error recording balance for token {token_id}, user {user_id_str}: {e}")
        return False

def get_token_balance_history(user_id: Union[int, str], token_id: int, limit: int = 30) -> List[Dict[str, Any]]:
    """
    Get the balance history for a token.
    
    Args:
        user_id: The user ID
        token_id: The token ID
        limit: The maximum number of entries to return
        
    Returns:
        List of balance entries with timestamps
    """
    user_id_str: str = hash_user_id(user_id) if isinstance(user_id, int) else str(user_id)
    
    try:
        result: QueryResult = execute_query(
            """
            SELECT id, wallet_address, balance, timestamp 
            FROM token_balances 
            WHERE user_id = %s AND token_id = %s 
            ORDER BY timestamp DESC 
            LIMIT %s
            """,
            (user_id_str, token_id, limit),
            fetch='all'
        )
        
        # Ensure we return a list of dictionaries
        if result is None:
            return []
        elif isinstance(result, list):
            return result
        else:
            logger.error(f"Unexpected result type from execute_query: {type(result)}")
            return []
    except Exception as e:
        logger.error(f"Error getting balance history for token {token_id}, user {user_id_str[:8]}...: {e}")
        return []

def get_all_tracked_tokens_with_wallets() -> List[Dict[str, Any]]:
    """
    Get all tracked tokens with the wallets they belong to.
    Used for syncing balances with blockchain.
    
    Returns:
        List of tokens with tracking and user wallet data for all wallets
    """
    try:
        result: QueryResult = execute_query(
            """
            SELECT 
                utt.id as tracking_id, 
                utt.user_id, 
                t.id as token_id, 
                t.token_address, 
                t.token_symbol,
                t.chain_id,
                w.address as wallet_address
            FROM user_tracked_tokens utt
            JOIN tokens t ON utt.token_id = t.id
            JOIN wallets w ON utt.user_id = w.user_id
            """,
            fetch='all'
        )
        
        # Ensure we return a list of dictionaries
        if result is None:
            return []
        elif isinstance(result, list):
            return result
        else:
            logger.error(f"Unexpected result type from execute_query: {type(result)}")
            return []
    except Exception as e:
        logger.error(f"Error getting tracked tokens with wallets: {e}")
        return [] 