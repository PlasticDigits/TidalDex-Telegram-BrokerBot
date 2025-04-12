"""
Command for stopping the tracking of token balances.
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, User, Message
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from typing import List, Dict, Any, Optional, Union, Callable, cast
from utils.web3_connection import w3
from db.utils import hash_user_id
from services.pin.pin_decorators import conversation_pin_helper, PIN_REQUEST, PIN_FAILED, handle_conversation_pin_request

from services import token_manager

# Configure module logger
logger = logging.getLogger(__name__)

# Define conversation states
TOKEN_SELECTION = 1

async def track_stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start the process of stopping token tracking.
    Send a list of currently tracked tokens to the user.
    """
    user: Optional[User] = update.effective_user
    if not user:
        logger.error("Effective user is None in track_stop_command")
        return ConversationHandler.END
        
    user_id: int = user.id

    helper_result: Optional[int] = await conversation_pin_helper('track_stop_command', context, update, "Stopping token tracking requires your PIN for security. Please enter your PIN.")
    if helper_result is not None:
        return helper_result
    
    # Get existing tracked tokens for the user
    tracked_tokens = await token_manager.get_tracked_tokens(str(user_id))
    
    if not tracked_tokens:
        initial_message: Optional[Message] = update.message
        if initial_message:
            await initial_message.reply_text(
                "You are not tracking any tokens currently.\n"
                "Use the /track command to start tracking tokens."
            )
        return ConversationHandler.END
    
    # Create keyboard with token options
    keyboard: List[List[InlineKeyboardButton]] = []
    for token in tracked_tokens:
        token_address = token.get('token_address')
        if not token_address:
            continue
            
        symbol: str = token.get('symbol', 'Unknown')
        name: str = token.get('name', 'Unknown')
        
        # Add a button for each token, with the token address as callback data
        keyboard.append([
            InlineKeyboardButton(f"{symbol} ({name})", callback_data=f"stop_track_{token_address}")
        ])
    
    # Add a cancel button
    keyboard.append([InlineKeyboardButton("Cancel", callback_data="stop_track_cancel")])
    
    reply_markup: InlineKeyboardMarkup = InlineKeyboardMarkup(keyboard)
    
    selection_message: Optional[Message] = update.message
    if selection_message:
        await selection_message.reply_text(
            "Select a token you want to stop tracking:",
            reply_markup=reply_markup
        )
    
    return TOKEN_SELECTION

async def process_token_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Process the selected token and remove it from tracked tokens.
    """
    query: Optional[CallbackQuery] = update.callback_query
    if not query:
        logger.error("Callback query is None in process_token_selection")
        return ConversationHandler.END
        
    await query.answer()
    
    # Extract token address from callback data
    callback_data: Optional[str] = query.data
    if not callback_data:
        logger.error("Callback data is None in process_token_selection")
        await query.edit_message_text("Error: Invalid selection. Please try again.")
        return ConversationHandler.END
    
    if callback_data == "stop_track_cancel":
        await query.edit_message_text("Token tracking removal canceled.")
        return ConversationHandler.END
    
    # Extract token address from callback_data (format: "stop_track_{address}")
    token_address: str = callback_data.split("_")[-1]
    
    user: Optional[User] = update.effective_user
    if not user:
        logger.error("Effective user is None in process_token_selection")
        return ConversationHandler.END
        
    user_id: int = user.id
    
    try:
        # Get token info before untracking
        token_info = await token_manager.get_token_info(token_address)
        
        if not token_info:
            await query.edit_message_text("Error: Token not found. Please try again.")
            return ConversationHandler.END
        
        symbol: str = token_info.get('symbol', 'Unknown')
        name: str = token_info.get('name', 'Unknown')
        
        # Stop tracking the token
        await token_manager.untrack(str(user_id), token_address)
        
        await query.edit_message_text(
            f"You have stopped tracking {symbol} ({name}).\n\n"
            "Balance history for this token will be preserved, but no new balances will be recorded."
        )
        
        logger.info(f"User {hash_user_id(user_id)} stopped tracking token {symbol} ({token_address})")
        
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error stopping token tracking: {e}")
        await query.edit_message_text(
            "Error removing token tracking. Please try again later."
        )
        return ConversationHandler.END

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancel the conversation.
    """
    message: Optional[Message] = update.message
    if message:
        await message.reply_text("Command canceled.")
    return ConversationHandler.END

# Setup conversation handler
track_stop_conv_handler: ConversationHandler[ContextTypes.DEFAULT_TYPE] = ConversationHandler(
    entry_points=[CommandHandler("track_stop", track_stop_command)],
    states={
        PIN_REQUEST: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_conversation_pin_request)
        ],
        PIN_FAILED: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_conversation_pin_request)
        ],
        TOKEN_SELECTION: [
            CallbackQueryHandler(process_token_selection, pattern=r"^stop_track_")
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel_command)]
)

async def track_stop_command_web3(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start the process of stopping token tracking using a token address.
    """
    # Get the message from the update
    web3_message = update.message
    if not web3_message:
        return ConversationHandler.END
        
    user = web3_message.from_user
    if not user:
        return ConversationHandler.END
        
    user_id = user.id
    
    # Get the token address from the message text
    token_address = web3_message.text
    if not token_address:
        await web3_message.reply_text("Please provide a token address.")
        return ConversationHandler.END
        
    # Remove any whitespace
    token_address = token_address.strip()
    
    # Validate the token address
    if not w3.is_address(token_address):
        await web3_message.reply_text("Invalid token address. Please try again.")
        return ConversationHandler.END
        
    # Convert to checksum address
    token_address = w3.to_checksum_address(token_address)
    
    # Stop tracking the token
    try:
        success = await token_manager.untrack(str(user_id), token_address)
        if success:
            await web3_message.reply_text(f"Stopped tracking token {token_address}")
        else:
            await web3_message.reply_text(f"Failed to stop tracking token {token_address}")
    except Exception as e:
        logger.error(f"Error stopping token tracking: {e}")
        await web3_message.reply_text("An error occurred while stopping token tracking. Please try again later.")
        
    return ConversationHandler.END 