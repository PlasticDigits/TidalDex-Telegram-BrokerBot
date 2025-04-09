"""
Command for tracking token balances.
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, User, Message, MaybeInaccessibleMessage
from telegram.ext import MessageHandler, filters, ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler, ExtBot, CallbackContext
from typing import List, Dict, Any, Optional, Union, Callable, TypeVar, Awaitable, cast

from services import token_manager
from services.wallet import get_active_wallet_name, get_wallet_by_name
from utils.token_utils import get_token_info, format_token_balance
from utils.web3_connection import w3
from services.pin.pin_decorators import conversation_pin_helper, PIN_REQUEST, PIN_FAILED, handle_conversation_pin_request


# Configure module logger
logger = logging.getLogger(__name__)

# Define conversation states
TOKEN_INPUT = 1
TOKEN_CONFIRMATION = 2

# Type variable for handler functions
HandlerType = TypeVar('HandlerType', bound=Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[int]])

async def track_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start the process of tracking a new token.
    """
    user: Optional[User] = update.effective_user
    if not user:
        return ConversationHandler.END
    
    helper_result: Optional[int] = await conversation_pin_helper('track_command', context, update, "Tracking a token requires your PIN for security. Please enter your PIN.")
    if helper_result is not None:
        return helper_result
        
    user_id: int = user.id
    
    # Verify the user has a wallet
    wallet_name: Optional[str] = get_active_wallet_name(str(user_id))
    if not wallet_name:
        user_message: Optional[Message] = update.message
        if user_message:
            await user_message.reply_text(
                "You need to create a wallet first to track tokens. Use /wallet to create one."
            )
        return ConversationHandler.END
    
    user_message2: Optional[Message] = update.message
    if user_message2:
        await user_message2.reply_text(
            "Please enter the token address you want to track.\n"
            "You can find this on BscScan or other blockchain explorers."
        )
    
    return TOKEN_INPUT

async def process_token_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Process the entered token address and show token information for confirmation.
    """
    user: Optional[User] = update.effective_user
    if not user:
        return ConversationHandler.END
        
    user_id: int = user.id
    message: Optional[Message] = update.message
    if not message:
        return ConversationHandler.END
        
    # Get the token address from the message text
    token_address = message.text
    if not token_address:
        await message.reply_text("Please provide a token address.")
        return ConversationHandler.END
        
    # Remove any whitespace
    token_address = token_address.strip() if token_address else ""
    
    # Get token info
    token_info: Optional[Dict[str, Any]] = await get_token_info(token_address)
    
    if not token_info:
        await message.reply_text(
            "Invalid token address or token not found.\n"
            "Please enter a valid BEP-20 token address."
        )
        return TOKEN_INPUT
    
    symbol: str = token_info.get('symbol', 'Unknown')
    name: str = token_info.get('name', 'Unknown')
    decimals: int = token_info.get('decimals', 18)
    
    # Check if token is already being tracked
    is_tracked: bool = await token_manager.is_token_tracked(str(user_id), token_address)
    
    if is_tracked:
        await message.reply_text(
            f"You are already tracking {symbol} ({name}).\n"
            "Use /balance to see your tracked token balances."
        )
        return ConversationHandler.END
    
    # Store token info in context for confirmation
    if context.user_data is not None:
        context.user_data['tracking_token'] = {
            'address': token_address,
            'symbol': symbol,
            'name': name,
            'decimals': decimals
        }
    
    # Create confirmation keyboard
    keyboard: List[List[InlineKeyboardButton]] = [
        [InlineKeyboardButton("Yes, track this token", callback_data="confirm_track")],
        [InlineKeyboardButton("No, cancel", callback_data="cancel_track")]
    ]
    
    reply_markup: InlineKeyboardMarkup = InlineKeyboardMarkup(keyboard)
    
    await message.reply_text(
        f"Token Information:\n\n"
        f"Name: {name}\n"
        f"Symbol: {symbol}\n"
        f"Decimals: {decimals}\n"
        f"Address: {token_address}\n\n"
        f"Do you want to track this token?",
        reply_markup=reply_markup
    )
    
    return TOKEN_CONFIRMATION

async def process_tracking_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Process the user's confirmation to track the token.
    """
    query: Optional[CallbackQuery] = update.callback_query
    if not query:
        return ConversationHandler.END
        
    await query.answer()
    
    callback_data: Optional[str] = query.data
    if not callback_data:
        return ConversationHandler.END
    
    if callback_data == "cancel_track":
        await query.edit_message_text("Token tracking canceled.")
        return ConversationHandler.END
    
    user: Optional[User] = update.effective_user
    if not user:
        return ConversationHandler.END
        
    user_id: int = user.id
    
    # Get token info from context
    token_info: Optional[Dict[str, Any]] = None
    if context.user_data is not None:
        token_info = context.user_data.get('tracking_token', {})
        
    if not token_info:
        await query.edit_message_text("Error: Token information lost. Please try again.")
        return ConversationHandler.END
    
    token_address: str = token_info.get('address', '')
    symbol: str = token_info.get('symbol', 'Unknown')
    name: str = token_info.get('name', 'Unknown')
    
    try:
        # Track the token
        await token_manager.track(str(user_id), token_address)
        
        await query.edit_message_text(
            f"Successfully started tracking {symbol} ({name}).\n"
            f"Use /balance to see your token balances."
        )
        
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error tracking token {token_address}: {e}")
        await query.edit_message_text(
            f"Error tracking {symbol} ({name}).\n"
            "Please try again later."
        )
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
track_conv_handler: ConversationHandler[ContextTypes.DEFAULT_TYPE] = ConversationHandler(
    entry_points=[CommandHandler("track", track_command)],
    states={
        PIN_REQUEST: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_conversation_pin_request)
        ],
        PIN_FAILED: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_conversation_pin_request)
        ],
        TOKEN_INPUT: [
            CallbackQueryHandler(process_token_address)
        ],
        TOKEN_CONFIRMATION: [
            CallbackQueryHandler(process_tracking_confirmation, pattern=r"^(confirm|cancel)_track$")
        ],
    },
    fallbacks=[
        CommandHandler("cancel", cancel_command)
    ]
) 