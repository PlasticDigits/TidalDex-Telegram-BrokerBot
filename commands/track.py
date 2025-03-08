"""
Command for tracking token balances over time.
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters

from db.connection import execute_query
from db.track import get_user_tracked_tokens, get_token_by_address, add_token, track_token, record_token_balance
from services.pin import require_pin
from services.wallet import get_active_wallet_name, get_wallet_by_name, get_wallet_balance
from utils.self_destruction_message import send_self_destructing_message
from web3 import Web3
from utils.token_utils import validate_token_address, get_token_info

# Define conversation states
TOKEN_INPUT = 1

# Configure module logger
logger = logging.getLogger(__name__)

@require_pin
async def track_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start the process of tracking a token's balance.
    Ask the user to input a token address or symbol.
    """
    user_id = update.effective_user.id
    
    # Verify the user has a wallet
    wallet_name = get_active_wallet_name(user_id)
    if not wallet_name:
        await update.message.reply_text(
            "You need to create a wallet first before tracking tokens. Use /wallet to create one."
        )
        return ConversationHandler.END
    
    # Get existing tracked tokens for the user
    tracked_tokens = get_user_tracked_tokens(user_id)
    
    # Display currently tracked tokens
    if tracked_tokens and len(tracked_tokens) > 0:
        tokens_list = "\n".join([f"• {token.get('token_symbol', 'Unknown')} ({token.get('token_name', 'Unknown')}): {token.get('token_address')}" for token in tracked_tokens])
        await update.message.reply_text(
            f"You are currently tracking these tokens:\n\n{tokens_list}\n\n"
            "To track a new token, please enter the token address or symbol."
        )
    else:
        await update.message.reply_text(
            "You are not tracking any tokens yet.\n\n"
            "Please enter the token address or symbol you want to track."
        )
    
    return TOKEN_INPUT

async def process_token_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Process the token address or symbol input from the user.
    Validate the token and add it to tracked tokens.
    """
    user_id = update.effective_user.id
    token_input = update.message.text.strip()
    
    await update.message.reply_text("Validating token... Please wait.")
    
    # Validate if this is a token address
    if Web3.is_address(token_input):
        token_address = Web3.to_checksum_address(token_input)
        
        # Check if token exists in tokens table
        token = get_token_by_address(token_address)
        
        token_id = None
        
        # If token doesn't exist, get info and add it
        if not token:
            # Validate token and get info
            try:
                token_info = await get_token_info(token_address)
                
                if not token_info:
                    await update.message.reply_text(
                        "Could not validate this token address. Please check the address and try again."
                    )
                    return ConversationHandler.END
                    
                token_symbol = token_info.get('symbol')
                token_name = token_info.get('name')
                token_decimals = token_info.get('decimals', 18)
                
                # Add to tokens table
                token_id = add_token(token_address, token_symbol, token_name, token_decimals)
                
                if not token_id:
                    await update.message.reply_text(
                        "Error adding the token. Please try again later."
                    )
                    return ConversationHandler.END
                
            except Exception as e:
                logger.error(f"Error validating token {token_input}: {e}")
                await update.message.reply_text(
                    "Error validating token. Please check the address and try again."
                )
                return ConversationHandler.END
        else:
            # Token already exists in the database
            token_id = token.get('id')
            token_symbol = token.get('token_symbol', 'Unknown')
            token_name = token.get('token_name', 'Unknown')
        
        # Add token to user's tracked tokens
        tracking_id = track_token(user_id, token_id)
        
        if not tracking_id:
            await update.message.reply_text(
                "Error tracking the token. Please try again later."
            )
            return ConversationHandler.END
        
        # Get initial balance
        wallet_name = get_active_wallet_name(user_id)
        wallet = get_wallet_by_name(user_id, wallet_name)
        
        if wallet:
            wallet_address = wallet.get('address')
            # Get token balance
            balance = await get_wallet_balance(wallet_address, token_address)
            # Record balance
            await record_token_balance_wrapper(user_id, token_id, token_address, wallet_address, balance)
        
        await update.message.reply_text(
            f"You are now tracking the token: {token_symbol} ({token_name})\n"
            f"Address: {token_address}\n\n"
            "Your balance will be periodically recorded."
        )
        
        return ConversationHandler.END
    
    else:
        # Later could implement symbol lookup
        await update.message.reply_text(
            "Please enter a valid token address (0x...).\n"
            "Symbol lookup is not supported yet."
        )
        return TOKEN_INPUT

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the conversation."""
    await update.message.reply_text(
        "Token tracking canceled."
    )
    return ConversationHandler.END

async def record_token_balance_wrapper(user_id, token_id, token_address=None, wallet_address=None, balance=None):
    """
    Wrapper for recording token balance that handles fetching wallet and balance if needed.
    
    Args:
        user_id (str): Telegram user ID
        token_id (int): Token ID from tokens table
        token_address (str, optional): Token contract address, required if balance is None
        wallet_address (str, optional): Wallet address, fetched from active wallet if None
        balance (int, optional): Balance to record, fetched from blockchain if None
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # If wallet_address is not provided, get it from the active wallet
        if wallet_address is None:
            wallet_name = get_active_wallet_name(user_id)
            if not wallet_name:
                logger.error(f"No active wallet for user {user_id}")
                return False
                
            wallet = get_wallet_by_name(user_id, wallet_name)
            if not wallet:
                logger.error(f"Could not get wallet for user {user_id}")
                return False
                
            wallet_address = wallet.get('address')
        
        # If token_address is not provided but balance is None, get it from the token_id
        if balance is None:
            if token_address is None:
                token_info = execute_query(
                    "SELECT token_address FROM tokens WHERE id = ?",
                    (token_id,),
                    fetch='one'
                )
                if not token_info:
                    logger.error(f"Token not found with ID {token_id}")
                    return False
                token_address = token_info.get('token_address')
            
            # Get token balance
            balance = await get_wallet_balance(wallet_address, token_address)
        
        # Record balance
        return record_token_balance(user_id, token_id, wallet_address, balance)
        
    except Exception as e:
        logger.error(f"Error recording token balance: {e}")
        return False

# Setup conversation handler
track_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("track", track_command)],
    states={
        TOKEN_INPUT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, process_token_input)
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)]
) 