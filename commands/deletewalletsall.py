"""
Command for deleting all wallets and mnemonic keys.

This module provides functionality to delete all wallets and mnemonic keys
for a user after confirmation.
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message, User
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from typing import Dict, List, Any, Optional, Union, Callable, Coroutine, cast
from services.wallet import wallet_manager, delete_wallets_all
from services.pin import require_pin
from db.utils import hash_user_id
from db.wallet import WalletData
from services.pin.pin_decorators import conversation_pin_helper, PIN_REQUEST, PIN_FAILED, handle_conversation_pin_request
# Configure module logger
logger = logging.getLogger(__name__)

# Define conversation states
CONFIRMING_DELETE = 1

async def deletewalletsall_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start the process of deleting all wallets and mnemonic keys.
    Warn the user and ask for confirmation.
    """
    user: Optional[User] = update.effective_user
    if not user:
        logger.error("No user found in update")
        return ConversationHandler.END
    
    helper_result: Optional[int] = await conversation_pin_helper('deletewalletsall_command', context, update, "Deleting all wallets requires your PIN for security. Please enter your PIN.")
    if helper_result is not None:
        return helper_result
    
    user_id: int = user.id
    user_id_str: str = hash_user_id(user_id)
    
    logger.info(f"Delete all wallets command initiated by user {user_id_str}")
    
    # Get PIN for wallet operations
    from services.pin import pin_manager
    pin: Optional[str] = pin_manager.get_pin(user_id)
    
    # Check if the user has any wallets
    wallets: Union[List[WalletData], Dict[str, WalletData]] = wallet_manager.get_user_wallets(user_id_str, False, pin)
    
    message: Optional[Message] = update.message
    if not message:
        logger.error("No message found in update")
        return ConversationHandler.END
    
    if not wallets:
        await message.reply_text(
            "❌ You don't have any wallets to delete."
        )
        return ConversationHandler.END
    
    # Create keyboard with confirmation buttons
    keyboard: List[List[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("⚠️ Yes, delete everything", callback_data="delete_all_confirm"),
            InlineKeyboardButton("❌ Cancel", callback_data="delete_all_cancel")
        ]
    ]
    reply_markup: InlineKeyboardMarkup = InlineKeyboardMarkup(keyboard)
    
    # Send warning message with confirmation buttons
    await message.reply_text(
        f"⚠️ *DANGER ZONE* ⚠️\n\n"
        f"You are about to delete *ALL* your wallets and mnemonic keys.\n\n"
        f"⚠️ This action *CANNOT* be undone!\n\n"
        f"Before proceeding, make sure you have:\n"
        f"• Backed up your mnemonic phrase using /backup\n"
        f"• Exported your private keys using /export_key\n"
        f"• Saved this information in a secure location\n\n"
        f"Are you absolutely sure you want to delete everything?",
        reply_markup=reply_markup
    )
    
    return CONFIRMING_DELETE

async def process_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the user's confirmation to delete all wallets."""
    query: Optional[CallbackQuery] = update.callback_query
    if not query:
        logger.error("No callback query found in update")
        return ConversationHandler.END
        
    await query.answer()
    
    user: Optional[User] = update.effective_user
    if not user:
        logger.error("No user found in update")
        return ConversationHandler.END
        
    user_id: int = user.id
    user_id_str: str = hash_user_id(user_id)
    
    if query.data == "delete_all_cancel":
        await query.edit_message_text(
            "Operation cancelled. Your wallets and keys are safe."
        )
        return ConversationHandler.END
    
    # User confirmed deletion
    logger.warning(f"User {user_id_str} confirmed deletion of all wallets and keys")
    
    # Delete all wallets and mnemonic
    success: bool = delete_wallets_all(user_id_str, None)
    
    if success:
        await query.edit_message_text(
            "✅ All wallets and keys have been deleted.\n\n"
            "If you want to create a new wallet, use the /wallet command."
        )
    else:
        await query.edit_message_text(
            "❌ There was an error deleting your wallets and keys.\n"
            "Please try again later or contact support."
        )
    
    return ConversationHandler.END

# Create a PIN-protected version of the command
pin_protected_deletewalletsall: Callable[[Update, ContextTypes.DEFAULT_TYPE], Coroutine[Any, Any, int]] = require_pin(
    "🔒 Deleting all wallets requires PIN verification.\nPlease enter your PIN:"
)(deletewalletsall_command)

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the conversation."""
    return ConversationHandler.END

# Setup conversation handler
deletewalletsall_conv_handler: ConversationHandler[ContextTypes.DEFAULT_TYPE] = ConversationHandler(
    entry_points=[CommandHandler("deletewalletsall", pin_protected_deletewalletsall)],
    states={
        PIN_REQUEST: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_conversation_pin_request)
        ],
        PIN_FAILED: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_conversation_pin_request)
        ],
        CONFIRMING_DELETE: [
            CallbackQueryHandler(process_confirmation, pattern=r"^delete_all_")
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel_command)]
) 