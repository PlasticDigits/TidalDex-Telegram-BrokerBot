"""
Utility for tracking token balances over time.
"""
import logging
import asyncio
from db.connection import execute_query
from db.track import get_all_tracked_tokens_with_wallets, record_token_balance, get_token_balance_history
from services.wallet import get_wallet_balance
from utils.token_utils import get_token_balance

# Configure module logger
logger = logging.getLogger(__name__)

async def update_tracked_token_balances():
    """
    Update balances for all tracked tokens across all users.
    This should be run periodically to maintain balance history.
    """
    try:
        # Get all tracked tokens with their users
        tracked_tokens = get_all_tracked_tokens_with_wallets()
        
        if not tracked_tokens:
            logger.info("No tracked tokens found for any users")
            return
            
        logger.info(f"Updating balances for {len(tracked_tokens)} tracked tokens")
        
        for token in tracked_tokens:
            user_id = token.get('user_id')
            token_id = token.get('token_id')
            token_address = token.get('token_address')
            wallet_address = token.get('wallet_address')
            symbol = token.get('token_symbol', 'Unknown')
            
            try:
                # Get current balance
                balance = await get_wallet_balance(wallet_address, token_address)
                
                # Record balance
                success = record_token_balance(user_id, token_id, wallet_address, balance)
                
                if success:
                    logger.debug(f"Updated balance for user {user_id} token {symbol}: {balance}")
                else:
                    logger.warning(f"Failed to record balance for user {user_id} token {symbol}")
            except Exception as e:
                logger.error(f"Error updating balance for user {user_id} token {symbol}: {e}")
                continue
                
        logger.info("Balance update completed")
    except Exception as e:
        logger.error(f"Error updating tracked token balances: {e}")

def setup_periodic_balance_updates(application):
    """
    Set up periodic balance updates for tracked tokens.
    
    Args:
        application: The Telegram application instance
    """
    async def job_update_balances(context):
        await update_tracked_token_balances()
    
    # Schedule the job to run every hour
    application.job_queue.run_repeating(
        job_update_balances, 
        interval=3600,  # 1 hour
        first=300  # Start after 5 minutes
    )
    
    logger.info("Scheduled periodic balance updates every hour") 