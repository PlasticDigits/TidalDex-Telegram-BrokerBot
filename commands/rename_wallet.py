"""
Command for renaming a wallet.
"""
import logging
from telegram import Update, Message, User
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
from typing import Dict, Any, Optional, cast
from services.wallet import wallet_manager
from services.pin import pin_manager
from db.wallet import WalletData
from services.pin.pin_decorators import conversation_pin_helper, PIN_REQUEST, PIN_FAILED, handle_conversation_pin_request
from db.utils import hash_user_id
# Configure module logger
logger = logging.getLogger(__name__)

# Define conversation states
WAITING_FOR_NAME = 1

async def rename_wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start the process of renaming a wallet.
    Ask the user for a new wallet name.
    """
    user = update.effective_user
    if not user:
        logger.error("No user found in update")
        return ConversationHandler.END
    
    helper_result: Optional[int] = await conversation_pin_helper('rename_wallet_command', context, update, "Renaming a wallet requires your PIN for security. Please enter your PIN.")
    if helper_result is not None:
        return helper_result
        
    user_id_int: int = user.id
    user_id_str: str = str(user_id_int)
    
    # Get the PIN from the manager - PIN manager expects int
    pin: Optional[str] = pin_manager.get_pin(user_id_int)
    
    # Get the active wallet name - Wallet manager expects str
    wallet_name: Optional[str] = wallet_manager.get_active_wallet_name(user_id_str)
    
    # Check if there's an active wallet - Wallet manager expects str
    user_wallet: Optional[WalletData] = wallet_manager.get_user_wallet(user_id_str, wallet_name, pin)
    
    message = update.message
    if not message:
        logger.error("No message found in update")
        return ConversationHandler.END
        
    if not user_wallet:
        await message.reply_text(
            "You don't have an active wallet to rename.\n"
            "Use /wallet to create one first."
        )
        return ConversationHandler.END
    
    # Store the current wallet name in user_data
    if context.user_data is None:
        context.user_data = {}
    context.user_data['current_wallet_name'] = wallet_name
    
    await message.reply_text(
        f"Current wallet name: {wallet_name}\n\n"
        "Please enter a new name for your wallet:"
    )
    
    return WAITING_FOR_NAME

async def process_new_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Process the new wallet name entered by the user.
    """
    user = update.effective_user
    if not user:
        logger.error("No user found in update")
        return ConversationHandler.END
        
    user_id_int: int = user.id
    user_id_str: str = str(user_id_int)
    
    # Check if message is available
    if not update.message or not update.message.text:
        await context.bot.send_message(
            chat_id=user_id_int,  # Using int for telegram API
            text="Invalid input. Please enter a valid wallet name or use /cancel to abort."
        )
        return WAITING_FOR_NAME
        
    new_name: str = update.message.text.strip()
    
    # Validate the new name
    if not new_name or len(new_name) > 20:
        message = update.message
        await message.reply_text(
            "Invalid wallet name. Please enter a name between 1 and 20 characters."
        )
        return WAITING_FOR_NAME
    
    # Get the current wallet name from context
    if context.user_data is None:
        message =update.message
        await message.reply_text(
            "Error: User data not available.\n"
            "Please try the rename command again."
        )
        return ConversationHandler.END
        
    current_wallet_name: Optional[str] = context.user_data.get('current_wallet_name')
    if not current_wallet_name:
        message = update.message
        await message.reply_text(
            "Error: Could not retrieve current wallet name.\n"
            "Please try the rename command again."
        )
        return ConversationHandler.END
    
    # Rename the wallet - Wallet manager expects str
    success: bool = wallet_manager.rename_wallet(user_id_str, current_wallet_name, new_name)
    
    message = update.message
    if success:
        await message.reply_text(
            f"✅ Wallet successfully renamed from '{current_wallet_name}' to '{new_name}'."
        )
    else:
        await message.reply_text(
            f"❌ Failed to rename wallet from '{current_wallet_name}' to '{new_name}'.\n"
            f"Try a different name or use /addwallet to create a new wallet.\n"
        )
    
    # Clear the stored wallet name
    if context.user_data is not None and 'current_wallet_name' in context.user_data:
        del context.user_data['current_wallet_name']
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancel the wallet renaming process.
    """
    # Clear any stored data
    if context.user_data is not None and 'current_wallet_name' in context.user_data:
        del context.user_data['current_wallet_name']
    
    message = update.message
    if message:
        await message.reply_text(
            "Wallet renaming canceled."
        )
    
    return ConversationHandler.END

# Create the conversation handler
rename_wallet_conv_handler: ConversationHandler[ContextTypes.DEFAULT_TYPE] = ConversationHandler(
    entry_points=[CommandHandler("rename_wallet", rename_wallet_command)],
    states={
        PIN_REQUEST: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_conversation_pin_request)],
        PIN_FAILED: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_conversation_pin_request)],
        WAITING_FOR_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_new_name)],
    },
    fallbacks=[CommandHandler("cancel", cancel)]
) 