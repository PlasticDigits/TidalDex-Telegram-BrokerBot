"""
Database operations for token management.
Provides functions to interact with the tokens, user_tracked_tokens, and user_balances tables.
"""
import logging
from typing import List, Dict, Any, Optional, TypedDict, Awaitable, cast
from web3 import Web3
from db.connection import execute_query, retry_decorator

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
    # First, ensure the token exists in the tokens table
    token_query = """
    INSERT OR IGNORE INTO tokens (token_address, token_symbol, token_name, token_decimals, chain_id)
    VALUES (?, ?, ?, ?, ?)
    """
    execute_query(token_query, (token_address, symbol, name, decimals, chain_id))
    
    # Then, get the token_id
    get_token_id_query = "SELECT id FROM tokens WHERE token_address = ? AND chain_id = ?"
    token_result = execute_query(get_token_id_query, (token_address, chain_id))
    if not token_result:
        raise ValueError(f"Failed to get token_id for {token_address}")
    token_id = token_result[0]['id']
    
    # Finally, add to user_tracked_tokens
    track_query = """
    INSERT OR IGNORE INTO user_tracked_tokens (user_id, token_id)
    VALUES (?, ?)
    """
    execute_query(track_query, (user_id, token_id))

@retry_decorator(5, 0.1)
def untrack_token(user_id: str, token_address: str, chain_id: int = 56) -> None:
    """Remove a token from the tracked tokens for a specific user."""
    # Get the token_id
    get_token_id_query = "SELECT id FROM tokens WHERE token_address = ? AND chain_id = ?"
    token_result = execute_query(get_token_id_query, (token_address, chain_id))
    if not token_result:
        return  # Token not found, nothing to untrack
    token_id = token_result[0]['id']
    
    # Remove from user_tracked_tokens
    untrack_query = "DELETE FROM user_tracked_tokens WHERE user_id = ? AND token_id = ?"
    execute_query(untrack_query, (user_id, token_id))

@retry_decorator(5, 0.1)
def get_tracked_tokens(user_id: str) -> List[TokenInfo]:
    """Get all tracked tokens for a specific user."""
    query = """
    SELECT t.token_address, t.token_symbol as symbol, t.token_name as name, 
           t.token_decimals as decimals, t.chain_id
    FROM tokens t
    JOIN user_tracked_tokens utt ON t.id = utt.token_id
    WHERE utt.user_id = ?
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
    query = """
    SELECT 1 
    FROM user_tracked_tokens utt
    JOIN tokens t ON t.id = utt.token_id
    WHERE utt.user_id = ? AND t.token_address = ? AND t.chain_id = ?
    """
    result = execute_query(query, (user_id, token_address, chain_id))
    return len(result) > 0 

@retry_decorator(5, 0.1)
def get_token_by_address(token_address: str, chain_id: int = 56) -> Optional[Dict[str, Any]]:
    """Get token information by its address.
    
    Args:
        token_address: The token address to look up
        chain_id: The chain ID where the token exists (default: 56 for BSC)
        
    Returns:
        Optional[Dict[str, Any]]: Token information if found, None otherwise
    """
    try:
        query = """
        SELECT id, token_address, token_symbol, token_name, token_decimals, chain_id
        FROM tokens
        WHERE token_address = ? AND chain_id = ?
        """
        result = execute_query(query, (token_address, chain_id), fetch='one')
        
        if not result:
            return None
            
        return {
            'id': result['id'],
            'token_address': result['token_address'],
            'token_symbol': result['token_symbol'],
            'token_name': result['token_name'],
            'token_decimals': result['token_decimals'],
            'chain_id': result['chain_id']
        }
    except Exception as e:
        logger.error(f"Failed to get token by address {token_address}: {str(e)}")
        return None 