"""
Database operations for token management.
Provides functions to interact with the tokens, user_tracked_tokens, and user_balances tables.
"""
import logging
from typing import List, Dict, Any, Optional, TypedDict, Awaitable, cast
from utils.web3_connection import w3
from db.connection import execute_query, retry_decorator
from db.utils import hash_user_id
# Configure module logger
logger = logging.getLogger(__name__)

class TokenInfo(TypedDict):
    """Type definition for token information."""
    token_address: str
    symbol: Optional[str]
    name: Optional[str]
    decimals: Optional[int]
    chain_id: Optional[int]

@retry_decorator(5, 0.1)
def track_token(user_id: str, token_address: str, chain_id: int = 56, 
                     symbol: Optional[str] = None, name: Optional[str] = None, 
                     decimals: Optional[int] = None) -> None:
    """Add a new token to the tracked tokens for a specific user."""
    logger.info(f"tracking token {symbol} ({token_address}) for user {hash_user_id(user_id)}")
    # First, hash the user_id
    user_id = hash_user_id(user_id)
    
    # First, ensure the token exists in the tokens table
    token_query = """
    INSERT INTO tokens (token_address, token_symbol, token_name, token_decimals, chain_id)
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (token_address, chain_id) DO UPDATE SET
        token_symbol = EXCLUDED.token_symbol,
        token_name = EXCLUDED.token_name,
        token_decimals = EXCLUDED.token_decimals
    """
    
    execute_query(token_query, (token_address, symbol, name, decimals, chain_id))

    # Then, get the token_id
    get_token_id_query = "SELECT id FROM tokens WHERE token_address = %s AND chain_id = %s"
    token_result = execute_query(get_token_id_query, (token_address, chain_id), fetch='one')
    
    if not token_result:
        raise ValueError(f"Failed to get token_id for {token_address}")
        
    token_id = token_result['id']

    # Finally, add to user_tracked_tokens
    track_query = """
    INSERT INTO user_tracked_tokens (user_id, token_id)
    VALUES (%s, %s)
    ON CONFLICT (user_id, token_id) DO NOTHING
    """
    execute_query(track_query, (user_id, token_id))

@retry_decorator(5, 0.1)
def untrack_token(user_id: str, token_address: str, chain_id: int = 56) -> None:
    """Remove a token from the tracked tokens for a specific user."""
    # First, hash the user_id
    user_id = hash_user_id(user_id)
    # Get the token_id
    get_token_id_query = "SELECT id FROM tokens WHERE token_address = %s AND chain_id = %s"
    token_result = execute_query(get_token_id_query, (token_address, chain_id), fetch='one')
    if not token_result:
        return  # Token not found, nothing to untrack
    token_id = token_result['id']
    
    # Remove from user_tracked_tokens
    untrack_query = "DELETE FROM user_tracked_tokens WHERE user_id = %s AND token_id = %s"
    execute_query(untrack_query, (user_id, token_id))

@retry_decorator(5, 0.1)
def get_tracked_tokens(user_id: str) -> List[TokenInfo]:
    """Get all tracked tokens for a specific user."""
    # First, hash the user_id
    user_id = hash_user_id(user_id)
    query = """
    SELECT t.token_address, t.token_symbol as symbol, t.token_name as name, 
           t.token_decimals as decimals, t.chain_id
    FROM tokens t
    JOIN user_tracked_tokens utt ON t.id = utt.token_id
    WHERE utt.user_id = %s
    """
    result = execute_query(query, (user_id,), fetch='all')
    if not result:
        return []
    return [TokenInfo(
        token_address=row['token_address'],
        symbol=row['symbol'],
        name=row['name'],
        decimals=row['decimals'],
        chain_id=row['chain_id']
    ) for row in result]

@retry_decorator(5, 0.1)
def is_token_tracked(user_id: str, token_address: str, chain_id: int = 56) -> bool:
    """Check if a token is already being tracked for a specific user."""
    # First, hash the user_id
    user_id = hash_user_id(user_id)
    query = """
    SELECT 1 
    FROM user_tracked_tokens utt
    JOIN tokens t ON t.id = utt.token_id
    WHERE utt.user_id = %s AND t.token_address = %s AND t.chain_id = %s
    """
    result = execute_query(query, (user_id, token_address, chain_id), fetch='one')
    # Return True if we found a row (result is not None), False otherwise
    return result is not None

@retry_decorator(5, 0.1)
def get_token_by_address(token_address: str, chain_id: int = 56) -> Optional[Dict[str, Any]]:
    """Get token information by address.
    
    Args:
        token_address: The token address to look up
        chain_id: The chain ID to filter by (default: 56 for BSC)
        
    Returns:
        Optional[Dict[str, Any]]: Token information if found, None otherwise
    """
    query = """
    SELECT id, token_address, token_symbol, token_name, token_decimals, chain_id
    FROM tokens
    WHERE token_address = %s AND chain_id = %s
    """
    result = execute_query(query, (token_address, chain_id), fetch='one')
    
    if not result:
        return None
        
    return {
        'id': result['id'],
        'token_address': result['token_address'],
        'symbol': result['token_symbol'],
        'name': result['token_name'],
        'decimals': result['token_decimals'],
        'chain_id': result['chain_id']
    }

@retry_decorator(5, 0.1)
def get_all_tracked_tokens_by_symbol(symbol: str) -> List[Dict[str, Any]]:
    """Get all tracked tokens across all users by symbol.
    
    Used for token migration cleanup - when a token symbol appears in the default
    token list, we need to find all user-tracked tokens with that symbol to check
    if they need to be untracked (if they're different from the default list address).
    
    Args:
        symbol: Token symbol to search for (case-insensitive)
        
    Returns:
        List[Dict[str, Any]]: List of tracked token entries with user_id, token_address, chain_id
    """
    query = """
    SELECT DISTINCT
        utt.user_id,
        t.token_address,
        t.token_symbol,
        t.chain_id
    FROM user_tracked_tokens utt
    JOIN tokens t ON t.id = utt.token_id
    WHERE UPPER(t.token_symbol) = UPPER(%s)
    """
    result = execute_query(query, (symbol,), fetch='all')
    if not result:
        return []
    return [
        {
            'user_id': row['user_id'],
            'token_address': row['token_address'],
            'symbol': row['token_symbol'],
            'chain_id': row['chain_id']
        }
        for row in result
    ] 