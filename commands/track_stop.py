"""
Command for stopping the tracking of token balances.
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler
from typing import List, Dict, Any, Optional, Union, Callable, cast

from db.connection import execute_query
from db.track import get_user_tracked_tokens, stop_tracking_token

# Configure module logger
logger = logging.getLogger(__name__)

# Define conversation states
TOKEN_SELECTION = 1

async def track_stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start the process of stopping token tracking.
    Send a list of currently tracked tokens to the user.
    """
    user = update.effective_user
    if user is None:
        logger.error("Effective user is None in track_stop_command")
        return ConversationHandler.END
        
    user_id: int = user.id
    
    # Get existing tracked tokens for the user
    tracked_tokens: List[Dict[str, Any]] = get_user_tracked_tokens(user_id)
    
    if not tracked_tokens or len(tracked_tokens) == 0:
        message = update.message
        if message is None:
            logger.error("Message is None in track_stop_command")
            return ConversationHandler.END
            
        await message.reply_text(
            "You are not tracking any tokens currently.\n"
            "Use the /track command to start tracking tokens."
        )
        return ConversationHandler.END
    
    # Create keyboard with token options
    keyboard: List[List[InlineKeyboardButton]] = []
    for token in tracked_tokens:
        tracking_id_value = token.get('id')
        if tracking_id_value is None:
            continue
        tracking_id: int = int(tracking_id_value)
        symbol: str = token.get('token_symbol', 'Unknown')
        name: str = token.get('token_name', 'Unknown')
        address: str = token.get('token_address', '')
        
        # Add a button for each token, with the tracking entry ID as callback data
        keyboard.append([
            InlineKeyboardButton(f"{symbol} ({name})", callback_data=f"stop_track_{tracking_id}")
        ])
    
    # Add a cancel button
    keyboard.append([InlineKeyboardButton("Cancel", callback_data="stop_track_cancel")])
    
    reply_markup: InlineKeyboardMarkup = InlineKeyboardMarkup(keyboard)
    
    message = update.message
    if message is None:
        logger.error("Message is None when trying to send reply in track_stop_command")
        return ConversationHandler.END
        
    await message.reply_text(
        "Select a token you want to stop tracking:",
        reply_markup=reply_markup
    )
    
    return TOKEN_SELECTION

async def process_token_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Process the selected token and remove it from tracked tokens.
    """
    query = update.callback_query
    if query is None:
        logger.error("Callback query is None in process_token_selection")
        return ConversationHandler.END
        
    callback_query: CallbackQuery = query
    await callback_query.answer()
    
    # Extract token ID from callback data
    callback_data = callback_query.data
    if callback_data is None:
        logger.error("Callback data is None in process_token_selection")
        await callback_query.edit_message_text("Error: Invalid selection. Please try again.")
        return ConversationHandler.END
    
    if callback_data == "stop_track_cancel":
        await callback_query.edit_message_text("Token tracking removal canceled.")
        return ConversationHandler.END
    
    # Extract tracking entry ID from callback_data (format: "stop_track_{id}")
    tracking_id_str: str = callback_data.split("_")[-1]
    
    try:
        tracking_id = int(tracking_id_str)
    except ValueError:
        logger.error(f"Invalid tracking ID format: {tracking_id_str}")
        await callback_query.edit_message_text("Error: Invalid token ID. Please try again.")
        return ConversationHandler.END
    
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
    
    if not token_info or not isinstance(token_info, dict):
        await callback_query.edit_message_text("Error: Token not found. Please try again.")
        return ConversationHandler.END
    
    # Stop tracking the token
    success: bool = stop_tracking_token(tracking_id)
    
    if not success:
        await callback_query.edit_message_text("Error removing tracking. Please try again.")
        return ConversationHandler.END
    
    symbol: str = token_info.get('token_symbol', 'Unknown')
    name: str = token_info.get('token_name', 'Unknown')
    
    await callback_query.edit_message_text(
        f"You have stopped tracking {symbol} ({name}).\n\n"
        "Balance history for this token will be preserved, but no new balances will be recorded."
    )
    
    user = update.effective_user
    if user is not None:
        logger.info(f"User {user.id} stopped tracking token {symbol} (Tracking ID: {tracking_id})")
    else:
        logger.info(f"Unknown user stopped tracking token {symbol} (Tracking ID: {tracking_id})")
    
    return ConversationHandler.END

# Function for cancel command to properly return a coroutine
async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the conversation."""
    return ConversationHandler.END

# Setup conversation handler
track_stop_conv_handler: ConversationHandler[ContextTypes.DEFAULT_TYPE] = ConversationHandler(
    entry_points=[CommandHandler("track_stop", track_stop_command)],
    states={
        TOKEN_SELECTION: [
            CallbackQueryHandler(process_token_selection, pattern=r"^stop_track_")
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel_command)]
) 