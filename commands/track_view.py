"""
Command for viewing tracked token balances and history.
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, User, Message, MaybeInaccessibleMessage
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler, ExtBot, CallbackContext
from typing import List, Dict, Any, Optional, Union, Callable, TypeVar, Awaitable, cast

from services import token_manager
from services.wallet import get_active_wallet_name, get_wallet_by_name
from utils.token_utils import get_token_balance, get_token_info, format_token_balance

# Configure module logger
logger = logging.getLogger(__name__)

# Define conversation states
TOKEN_SELECTION = 1
SHOW_HISTORY = 2

# Type variable for handler functions
HandlerType = TypeVar('HandlerType', bound=Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[int]])

async def track_view_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start the process of viewing tracked token balances.
    Send a list of currently tracked tokens to the user.
    """
    user: Optional[User] = update.effective_user
    if not user:
        return ConversationHandler.END
        
    user_id: int = user.id
    
    # Verify the user has a wallet
    wallet_name: Optional[str] = get_active_wallet_name(str(user_id))
    if not wallet_name:
        user_message: Optional[Message] = update.message
        if user_message:
            await user_message.reply_text(
                "You need to create a wallet first to view token balances. Use /wallet to create one."
            )
        return ConversationHandler.END
    
    # Get existing tracked tokens for the user
    tracked_tokens = await token_manager.get_tracked_tokens(str(user_id))
    
    if not tracked_tokens:
        user_message2: Optional[Message] = update.message
        if user_message2:
            await user_message2.reply_text(
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
            InlineKeyboardButton(f"{symbol} ({name})", callback_data=f"view_token_{token_address}")
        ])
    
    # Add a cancel button
    keyboard.append([InlineKeyboardButton("Cancel", callback_data="view_token_cancel")])
    
    reply_markup: InlineKeyboardMarkup = InlineKeyboardMarkup(keyboard)
    
    user_message3: Optional[Message] = update.message
    if user_message3:
        await user_message3.reply_text(
            "Select a token to view its balance:",
            reply_markup=reply_markup
        )
    
    return TOKEN_SELECTION

async def process_token_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Process the selected token and show its current balance.
    """
    query: Optional[CallbackQuery] = update.callback_query
    if not query:
        return ConversationHandler.END
        
    await query.answer()
    
    # Extract token address from callback data
    callback_data: Optional[str] = query.data
    if not callback_data:
        return ConversationHandler.END
    
    if callback_data == "view_token_cancel":
        await query.edit_message_text("Token view canceled.")
        return ConversationHandler.END
    
    # Extract token address from callback_data (format: "view_token_{address}")
    token_address = callback_data.split("_")[-1]
    
    user: Optional[User] = update.effective_user
    if not user:
        return ConversationHandler.END
        
    user_id: int = user.id
    
    # Get token info
    token_info: Optional[Dict[str, Any]] = await get_token_info(token_address)
    
    if not token_info:
        await query.edit_message_text("Error: Token not found. Please try again.")
        return ConversationHandler.END
    
    symbol: str = token_info.get('symbol', 'Unknown')
    name: str = token_info.get('name', 'Unknown')
    decimals: int = token_info.get('decimals', 18)
    
    # Get wallet info
    wallet_name: Optional[str] = get_active_wallet_name(str(user_id))
    wallet = None
    if wallet_name:
        wallet = get_wallet_by_name(str(user_id), wallet_name, None)
    
    if not wallet:
        await query.edit_message_text("Error: Could not find your wallet. Please try again.")
        return ConversationHandler.END
    
    wallet_address: str = wallet.get('address', '')
    
    # Get current balance
    try:
        balance: int = await get_token_balance(wallet_address, token_address)
        formatted_balance: str = format_token_balance(balance, decimals)
        
        # Store token info in context for history view
        if context.user_data is not None:
            context.user_data['viewing_token'] = {
                'address': token_address,
                'symbol': symbol,
                'name': name,
                'decimals': decimals
            }
        
        # Create keyboard for viewing history
        keyboard: List[List[InlineKeyboardButton]] = [
            [InlineKeyboardButton("View Balance History", callback_data=f"history_{token_address}")],
            [InlineKeyboardButton("Back to Token List", callback_data="back_to_tokens")]
        ]
        
        reply_markup: InlineKeyboardMarkup = InlineKeyboardMarkup(keyboard)
        
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
    query: Optional[CallbackQuery] = update.callback_query
    if not query:
        return ConversationHandler.END
        
    await query.answer()
    
    callback_data: Optional[str] = query.data
    if not callback_data:
        return ConversationHandler.END
    
    if callback_data == "back_to_tokens":
        # Restart the conversation to show token list
        query_message = query.message
        if query_message and hasattr(query_message, 'delete'):
            try:
                await query_message.delete()
            except Exception as e:
                logger.error(f"Error deleting message: {e}")
            
        # Create a new update with the original callback query
        return await track_view_command(update, context)
        
    token_address = callback_data.split("_")[-1]
    
    user: Optional[User] = update.effective_user
    if not user:
        return ConversationHandler.END
        
    user_id: int = user.id
    
    # Get token info from context
    token_info: Optional[Dict[str, Any]] = None
    if context.user_data is not None:
        token_info = context.user_data.get('viewing_token', {})
        
    if not token_info:
        await query.edit_message_text("Error: Token information lost. Please try again.")
        return ConversationHandler.END
    
    symbol: str = token_info.get('symbol', 'Unknown')
    name: str = token_info.get('name', 'Unknown')
    decimals: int = token_info.get('decimals', 18)
    
    # Get balance history
    try:
        history = await token_manager.get_token_balance_history(str(user_id), token_address)
        
        history_text_value: str
        if not history:
            history_text_value = "No balance history available yet."
        else:
            history_entries: List[str] = []
            for entry in history:
                balance: str = entry.get('balance', '0')
                formatted_balance: str = format_token_balance(int(balance), decimals)
                timestamp_str = str(entry.get('timestamp', ''))
                timestamp: str = timestamp_str.split('.')[0]  # Remove milliseconds
                history_entries.append(f"{timestamp}: {formatted_balance} {symbol}")
            
            history_text_value = "\n".join(history_entries)
        
        # Create keyboard for going back to token info
        keyboard: List[List[InlineKeyboardButton]] = [
            [InlineKeyboardButton("Back to Token Info", callback_data=f"view_token_{token_address}")],
            [InlineKeyboardButton("Back to Token List", callback_data="back_to_tokens")]
        ]
        
        reply_markup: InlineKeyboardMarkup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"Balance History for {symbol} ({name}):\n\n"
            f"{history_text_value}",
            reply_markup=reply_markup
        )
        
        return SHOW_HISTORY
    except Exception as e:
        logger.error(f"Error getting balance history: {e}")
        await query.edit_message_text("Error retrieving balance history. Please try again later.")
        return ConversationHandler.END

# Define a simple async function for the cancel command
async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancel the conversation.
    """
    message: Optional[Message] = update.message
    if message:
        await message.reply_text("Command canceled.")
    return ConversationHandler.END

# Setup conversation handler
track_view_conv_handler: ConversationHandler[ContextTypes.DEFAULT_TYPE] = ConversationHandler(
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
    fallbacks=[
        CommandHandler("cancel", cancel_command)
    ]
) 