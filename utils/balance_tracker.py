"""
Utility for tracking token balances over time.
"""
import logging
import asyncio
from typing import Dict, List, Any, Optional, Union
from decimal import Decimal
from db.connection import execute_query
from db.track import get_user_tracked_tokens, record_token_balance, get_token_balance_history
from services.wallet import get_wallet_balance
from utils.token_utils import get_token_balance
from db.utils import hash_user_id
# Configure module logger
logger = logging.getLogger(__name__)

async def update_tracked_token_balances(user_id: Optional[int] = None) -> None:
    """
    Update balances for a user's tracked tokens.
    This should be run when a token's balance is displayed to the user.
    
    Args:
        user_id (Optional[int]): The user ID to update tokens for, or None for all users
        
    Returns:
        None
    """
    try:
        # Get all tracked tokens with their users
        tracked_tokens: List[Dict[str, Any]] = get_user_tracked_tokens()
        
        if not tracked_tokens:
            logger.info("No tracked tokens found for any users")
            return
            
        logger.info(f"Updating balances for {len(tracked_tokens)} tracked tokens")
        
        for token in tracked_tokens:
            token_user_id: int = token.get('user_id')
            token_id: int = token.get('token_id')
            token_address: str = token.get('token_address')
            wallet_address: str = token.get('wallet_address')
            symbol: str = token.get('token_symbol', 'Unknown')
            
            # Skip if we specified a user_id and this token is for a different user
            if user_id is not None and token_user_id != user_id:
                continue
                
            try:
                # Get current balance
                balance: Union[Decimal, float] = await get_wallet_balance(wallet_address, token_address)
                
                # Record balance
                success: bool = record_token_balance(token_user_id, token_id, wallet_address, balance)
                
                if success:
                    logger.debug(f"Updated balance for user {hash_user_id(token_user_id)} token {symbol}: {balance}")
                else:
                    logger.warning(f"Failed to record balance for user {hash_user_id(token_user_id)} token {symbol}")
            except Exception as e:
                logger.error(f"Error updating balance for user {hash_user_id(token_user_id)} token {symbol}: {e}")
                continue
                
        logger.info("Balance update completed")
    except Exception as e:
        logger.error(f"Error updating tracked token balances: {e}")