"""
Command for viewing tracked token balances and history.
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler

from db.connection import execute_query
from db.track import get_user_tracked_tokens, get_tracked_token_by_id, get_token_balance_history
from services.pin import require_pin
from services.wallet import get_active_wallet_name, get_wallet_by_name
from utils.token_utils import get_token_balance, get_token_info, format_token_balance
from utils.self_destruction_message import send_self_destructing_message

# Configure module logger
logger = logging.getLogger(__name__)

# Define conversation states
TOKEN_SELECTION = 1
SHOW_HISTORY = 2

@require_pin
async def track_view_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start the process of viewing tracked token balances.
    Send a list of currently tracked tokens to the user.
    """
    user_id = update.effective_user.id
    
    # Verify the user has a wallet
    wallet_name = get_active_wallet_name(user_id)
    if not wallet_name:
        await update.message.reply_text(
            "You need to create a wallet first to view token balances. Use /wallet to create one."
        )
        return ConversationHandler.END
    
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
        
        # Add a button for each token, with the tracking ID as callback data
        keyboard.append([
            InlineKeyboardButton(f"{symbol} ({name})", callback_data=f"view_token_{tracking_id}")
        ])
    
    # Add a cancel button
    keyboard.append([InlineKeyboardButton("Cancel", callback_data="view_token_cancel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Select a token to view its balance:",
        reply_markup=reply_markup
    )
    
    return TOKEN_SELECTION

async def process_token_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Process the selected token and show its current balance.
    """
    query = update.callback_query
    await query.answer()
    
    # Extract token ID from callback data
    callback_data = query.data
    
    if callback_data == "view_token_cancel":
        await query.edit_message_text("Token view canceled.")
        return ConversationHandler.END
    
    # Extract tracking ID from callback_data (format: "view_token_{id}")
    tracking_id = callback_data.split("_")[-1]
    
    user_id = update.effective_user.id
    
    # Get token info
    token_info = get_tracked_token_by_id(tracking_id)
    
    if not token_info:
        await query.edit_message_text("Error: Token not found. Please try again.")
        return ConversationHandler.END
    
    token_id = token_info.get('token_id')
    token_address = token_info.get('token_address')
    symbol = token_info.get('token_symbol', 'Unknown')
    name = token_info.get('token_name', 'Unknown')
    decimals = token_info.get('token_decimals', 18)
    
    # Get wallet info
    wallet_name = get_active_wallet_name(user_id)
    wallet = get_wallet_by_name(user_id, wallet_name)
    
    if not wallet:
        await query.edit_message_text("Error: Could not find your wallet. Please try again.")
        return ConversationHandler.END
    
    wallet_address = wallet.get('address')
    
    # Get current balance
    try:
        balance = await get_token_balance(wallet_address, token_address)
        formatted_balance = format_token_balance(balance, decimals)
        
        # Store token info in context for history view
        context.user_data['viewing_token'] = {
            'tracking_id': tracking_id,
            'token_id': token_id,
            'address': token_address,
            'symbol': symbol,
            'name': name,
            'decimals': decimals
        }
        
        # Create keyboard for viewing history
        keyboard = [
            [InlineKeyboardButton("View Balance History", callback_data=f"history_{tracking_id}")],
            [InlineKeyboardButton("Back to Token List", callback_data="back_to_tokens")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"Token: {symbol} ({name})\n"
            f"Address: {token_address}\n"
            f"Current Balance: {formatted_balance} {symbol}\n\n"
            f"Wallet: {wallet_name}\n"
            f"Wallet Address: {wallet_address}\n",
            reply_markup=reply_markup
        )
        
        return SHOW_HISTORY
        
    except Exception as e:
        logger.error(f"Error getting balance for token {token_address}: {e}")
        await query.edit_message_text(
            f"Error getting balance for {symbol} ({name}).\n"
            "Please try again later."
        )
        return ConversationHandler.END

async def show_token_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Show the balance history for the selected token.
    """
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    
    if callback_data == "back_to_tokens":
        # Restart the conversation to show token list
        await query.message.delete()
        return await track_view_command(update.callback_query, context)
    
    # Extract tracking ID from callback_data (format: "history_{id}")
    tracking_id = callback_data.split("_")[-1]
    
    user_id = update.effective_user.id
    
    # Get token info from context
    token_info = context.user_data.get('viewing_token', {})
    if not token_info:
        await query.edit_message_text("Error: Token information lost. Please try again.")
        return ConversationHandler.END
    
    token_id = token_info.get('token_id')
    symbol = token_info.get('symbol', 'Unknown')
    name = token_info.get('name', 'Unknown')
    decimals = token_info.get('decimals', 18)
    
    # Get balance history
    history = await get_token_balance_history(user_id, token_id, limit=10)
    
    if not history or len(history) == 0:
        history_text = "No balance history available yet."
    else:
        history_entries = []
        for entry in history:
            balance = entry.get('balance', '0')
            formatted_balance = format_token_balance(int(balance), decimals)
            timestamp = entry.get('timestamp', '').split('.')[0]  # Remove milliseconds
            history_entries.append(f"{timestamp}: {formatted_balance} {symbol}")
        
        history_text = "\n".join(history_entries)
    
    # Create keyboard for going back to token info
    keyboard = [
        [InlineKeyboardButton("Back to Token Info", callback_data=f"view_token_{tracking_id}")],
        [InlineKeyboardButton("Back to Token List", callback_data="back_to_tokens")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"Balance History for {symbol} ({name}):\n\n"
        f"{history_text}",
        reply_markup=reply_markup
    )
    
    return SHOW_HISTORY

# Setup conversation handler
track_view_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("track_view", track_view_command)],
    states={
        TOKEN_SELECTION: [
            CallbackQueryHandler(process_token_selection, pattern=r"^view_token_")
        ],
        SHOW_HISTORY: [
            CallbackQueryHandler(show_token_history, pattern=r"^history_"),
            CallbackQueryHandler(process_token_selection, pattern=r"^view_token_"),
            CallbackQueryHandler(show_token_history, pattern=r"^back_to_tokens$")
        ],
    },
    fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)]
) 