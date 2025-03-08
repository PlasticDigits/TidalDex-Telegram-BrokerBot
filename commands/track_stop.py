"""
Command for stopping the tracking of token balances.
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler

from db.connection import execute_query
from db.track import get_user_tracked_tokens, stop_tracking_token
from services.pin import require_pin
from utils.self_destruction_message import send_self_destructing_message

# Configure module logger
logger = logging.getLogger(__name__)

# Define conversation states
TOKEN_SELECTION = 1

@require_pin
async def track_stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start the process of stopping token tracking.
    Send a list of currently tracked tokens to the user.
    """
    user_id = update.effective_user.id
    
    # Get existing tracked tokens for the user
    tracked_tokens = get_user_tracked_tokens(user_id)
    
    if not tracked_tokens or len(tracked_tokens) == 0:
        await update.message.reply_text(
            "You are not tracking any tokens currently.\n"
            "Use the /track command to start tracking tokens."
        )
        return ConversationHandler.END
    
    # Create keyboard with token options
    keyboard = []
    for token in tracked_tokens:
        tracking_id = token.get('id')
        symbol = token.get('token_symbol', 'Unknown')
        name = token.get('token_name', 'Unknown')
        address = token.get('token_address')
        
        # Add a button for each token, with the tracking entry ID as callback data
        keyboard.append([
            InlineKeyboardButton(f"{symbol} ({name})", callback_data=f"stop_track_{tracking_id}")
        ])
    
    # Add a cancel button
    keyboard.append([InlineKeyboardButton("Cancel", callback_data="stop_track_cancel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Select a token you want to stop tracking:",
        reply_markup=reply_markup
    )
    
    return TOKEN_SELECTION

async def process_token_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Process the selected token and remove it from tracked tokens.
    """
    query = update.callback_query
    await query.answer()
    
    # Extract token ID from callback data
    callback_data = query.data
    
    if callback_data == "stop_track_cancel":
        await query.edit_message_text("Token tracking removal canceled.")
        return ConversationHandler.END
    
    # Extract tracking entry ID from callback_data (format: "stop_track_{id}")
    tracking_id = callback_data.split("_")[-1]
    
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
        await query.edit_message_text("Error: Token not found. Please try again.")
        return ConversationHandler.END
    
    # Stop tracking the token
    success = stop_tracking_token(tracking_id)
    
    if not success:
        await query.edit_message_text("Error removing tracking. Please try again.")
        return ConversationHandler.END
    
    symbol = token_info.get('token_symbol', 'Unknown')
    name = token_info.get('token_name', 'Unknown')
    
    await query.edit_message_text(
        f"You have stopped tracking {symbol} ({name}).\n\n"
        "Balance history for this token will be preserved, but no new balances will be recorded."
    )
    
    logger.info(f"User {update.effective_user.id} stopped tracking token {symbol} (Tracking ID: {tracking_id})")
    
    return ConversationHandler.END

# Setup conversation handler
track_stop_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("track_stop", track_stop_command)],
    states={
        TOKEN_SELECTION: [
            CallbackQueryHandler(process_token_selection, pattern=r"^stop_track_")
        ],
    },
    fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)]
) 