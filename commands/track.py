"""
Track command module.
"""
import logging
import traceback
from typing import Dict, Any, Optional, List, Union, cast

from db.connections.connection import QueryResult
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
from db import QueryResult
from db.connection import execute_query
from db.track import get_user_tracked_tokens, get_token_by_address, add_token, track_token, record_token_balance
from services.wallet import get_active_wallet_name, get_wallet_by_name, get_wallet_balance
from db.wallet import WalletData
from web3 import Web3
from utils.token_utils import get_token_info

# Define conversation states
TOKEN_INPUT = 1

# Configure module logger
logger = logging.getLogger(__name__)

async def track_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start the process of tracking a token's balance.
    Ask the user to input a token address or symbol.
    """
    if not update.effective_user:
        logger.error("No effective user found in update")
        return ConversationHandler.END
        
    user_id: int = update.effective_user.id
    
    # Verify the user has a wallet
    wallet_name: Optional[str] = get_active_wallet_name(str(user_id))
    if not wallet_name:
        if not update.message:
            logger.error("No message found in update")
            return ConversationHandler.END
        await update.message.reply_text(
            "You need to create a wallet first before tracking tokens. Use /wallet to create one."
        )
        return ConversationHandler.END
    
    # Get existing tracked tokens for the user
    tracked_tokens: QueryResult = get_user_tracked_tokens(str(user_id))
    
    # Display currently tracked tokens
    if tracked_tokens and isinstance(tracked_tokens, list) and len(tracked_tokens) > 0:
        # Ensure each token in the list is a dictionary
        tokens_list: str = "\n".join([
            f"• {t.get('token_symbol', 'Unknown')} ({t.get('token_name', 'Unknown')}): {t.get('token_address')}" 
            for t in tracked_tokens if isinstance(t, dict)
        ])
        if not update.message:
            logger.error("No message found in update")
            return ConversationHandler.END
        await update.message.reply_text(
            f"You are currently tracking these tokens:\n\n{tokens_list}\n\n"
            "To track a new token, please enter the token address or symbol."
        )
    else:
        if not update.message:
            logger.error("No message found in update")
            return ConversationHandler.END
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
    if not update.effective_user or not update.message:
        logger.error("No effective user or message found in update")
        return ConversationHandler.END
        
    user_id: int = update.effective_user.id
    message_text: Optional[str] = update.message.text
    if not message_text:
        logger.error("No message text found")
        return ConversationHandler.END
        
    token_input: str = message_text.strip()
    
    await update.message.reply_text("Validating token... Please wait.")
    
    # Validate if this is a token address
    if Web3.is_address(token_input):
        token_address: str = Web3.to_checksum_address(token_input)
        
        # Check if token exists in tokens table
        token: Optional[Dict[str, Any]] = get_token_by_address(token_address)
        
        token_id: Optional[int] = None
        token_symbol: str = 'Unknown'
        token_name: str = 'Unknown'
        
        # If token doesn't exist, get info and add it
        if not token:
            # Validate token and get info
            try:
                token_info: Optional[Dict[str, Any]] = await get_token_info(token_address)
                
                if not token_info:
                    await update.message.reply_text(
                        "Could not validate this token address. Please check the address and try again."
                    )
                    return ConversationHandler.END
                    
                if not isinstance(token_info, dict):
                    logger.error(f"Unexpected token info format: {type(token_info)}")
                    await update.message.reply_text(
                        "Error processing token information. Please try again later."
                    )
                    return ConversationHandler.END
                    
                token_symbol = token_info.get('symbol', 'Unknown')
                token_name = token_info.get('name', 'Unknown')
                token_decimals: int = token_info.get('decimals', 18)
                
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
            if not isinstance(token, dict):
                logger.error(f"Unexpected token info format: {type(token)}")
                await update.message.reply_text(
                    "Error processing token information. Please try again later."
                )
                return ConversationHandler.END
                
            token_id = token.get('id')
            token_symbol = token.get('token_symbol', 'Unknown')
            token_name = token.get('token_name', 'Unknown')
        
        if not token_id:
            await update.message.reply_text(
                "Error: Could not get token ID. Please try again later."
            )
            return ConversationHandler.END
            
        # Add token to user's tracked tokens
        tracking_id: Optional[int] = track_token(str(user_id), token_id)
        
        if not tracking_id:
            await update.message.reply_text(
                "Error tracking the token. Please try again later."
            )
            return ConversationHandler.END
        
        # Get initial balance
        wallet_name: Optional[str] = get_active_wallet_name(str(user_id))
        if not wallet_name:
            await update.message.reply_text(
                "Error: No active wallet found. Please try again later."
            )
            return ConversationHandler.END
            
        wallet: Optional[WalletData] = get_wallet_by_name(str(user_id), wallet_name, None)
        if not wallet:
            await update.message.reply_text(
                "Error: Could not get wallet information. Please try again later."
            )
            return ConversationHandler.END
            
        # Ensure wallet is treated as a dictionary
        wallet_dict = cast(Dict[str, Any], wallet)
        wallet_address = wallet_dict.get('address', '')
        if not wallet_address:
            await update.message.reply_text(
                "Error: Invalid wallet address. Please try again later."
            )
            return ConversationHandler.END
            
        # Get token balance
        balance: float = await get_wallet_balance(wallet_address, token_address)
        # Record balance
        await record_token_balance_wrapper(str(user_id), token_id, token_address, wallet_address, balance)
        
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
    if not update.message:
        logger.error("No message found in update")
        return ConversationHandler.END
    await update.message.reply_text(
        "Token tracking canceled."
    )
    return ConversationHandler.END

async def record_token_balance_wrapper(
    user_id: str, 
    token_id: int, 
    token_address: Optional[str] = None, 
    wallet_address: Optional[str] = None, 
    balance: Optional[float] = None
) -> bool:
    """
    Wrapper for recording token balance that handles fetching wallet and balance if needed.
    
    Args:
        user_id (str): Telegram user ID as string
        token_id (int): Token ID from tokens table
        token_address (str, optional): Token contract address, required if balance is None
        wallet_address (str, optional): Wallet address, fetched from active wallet if None
        balance (float, optional): Balance to record, fetched from blockchain if None
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # If wallet_address is not provided, get it from the active wallet
        if wallet_address is None:
            wallet_name: Optional[str] = get_active_wallet_name(user_id)
            if not wallet_name:
                logger.error(f"No active wallet for user {user_id}")
                return False
                
            wallet: Optional[WalletData] = get_wallet_by_name(user_id, wallet_name, None)
            if not wallet:
                logger.error(f"Could not get wallet for user {user_id}")
                return False
                
            # Ensure wallet is treated as a dictionary
            wallet_dict = cast(Dict[str, Any], wallet)
            wallet_address = wallet_dict.get('address', '')
            if not wallet_address:
                logger.error(f"Invalid wallet address for user {user_id}")
                return False
        
        # If token_address is not provided but balance is None, get it from the token_id
        if balance is None:
            if token_address is None:
                token_info: QueryResult = execute_query(
                    "SELECT token_address FROM tokens WHERE id = ?",
                    (str(token_id),),
                    fetch='one'
                )
                if not token_info:
                    logger.error(f"Token not found with ID {token_id}")
                    return False
                if not isinstance(token_info, dict):
                    logger.error(f"Unexpected token info format for token ID {token_id}")
                    return False
                token_address = token_info.get('token_address', '')
                if not token_address:
                    logger.error(f"Invalid token address for token ID {token_id}")
                    return False
            
            # Get token balance
            balance = await get_wallet_balance(wallet_address, token_address)
        
        # Record balance
        return record_token_balance(user_id, token_id, wallet_address, int(balance))
        
    except Exception as e:
        logger.error(f"Error recording token balance: {e}")
        return False

# Setup conversation handler
track_conv_handler: ConversationHandler[ContextTypes.DEFAULT_TYPE] = ConversationHandler(
    entry_points=[CommandHandler("track", track_command)],
    states={
        TOKEN_INPUT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, process_token_input)
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)]
) 