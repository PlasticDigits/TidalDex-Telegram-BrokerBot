"""
Command for renaming a wallet.
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
import db
from services.wallet import get_active_wallet_name, get_user_wallet, rename_wallet
from services.pin import pin_manager

# Configure module logger
logger = logging.getLogger(__name__)

# Define conversation states
WAITING_FOR_NAME = 1

async def rename_wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start the process of renaming a wallet.
    Ask the user for a new wallet name.
    """
    user_id = update.effective_user.id
    
    # Get the PIN from the manager
    pin = pin_manager.get_pin(user_id)
    
    # Get the active wallet name
    wallet_name = get_active_wallet_name(user_id)
    
    # Check if there's an active wallet
    user_wallet = get_user_wallet(user_id, wallet_name, pin)
    
    if not user_wallet:
        await update.message.reply_text(
            "You don't have an active wallet to rename.\n"
            "Use /wallet to create one first."
        )
        return ConversationHandler.END
    
    # Store the current wallet name in user_data
    if not context.user_data:
        context.user_data = {}
    context.user_data['current_wallet_name'] = wallet_name
    
    await update.message.reply_text(
        f"Current wallet name: {wallet_name}\n\n"
        "Please enter a new name for your wallet:"
    )
    
    return WAITING_FOR_NAME

async def process_new_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Process the new wallet name entered by the user.
    """
    user_id = update.effective_user.id
    new_name = update.message.text.strip()
    
    # Validate the new name
    if not new_name or len(new_name) > 20:
        await update.message.reply_text(
            "Invalid wallet name. Please enter a name between 1 and 20 characters."
        )
        return WAITING_FOR_NAME
    
    # Get the current wallet name from context
    current_wallet_name = context.user_data.get('current_wallet_name')
    if not current_wallet_name:
        await update.message.reply_text(
            "Error: Could not retrieve current wallet name.\n"
            "Please try the rename command again."
        )
        return ConversationHandler.END
    
    # Rename the wallet
    success = rename_wallet(user_id, current_wallet_name, new_name)
    
    if success:
        await update.message.reply_text(
            f"✅ Wallet successfully renamed from '{current_wallet_name}' to '{new_name}'."
        )
    else:
        await update.message.reply_text(
            f"❌ Failed to rename wallet from '{current_wallet_name}' to '{new_name}'.\n"
            "Please try again later."
        )
    
    # Clear the stored wallet name
    if 'current_wallet_name' in context.user_data:
        del context.user_data['current_wallet_name']
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancel the wallet renaming process.
    """
    # Clear any stored data
    if context.user_data and 'current_wallet_name' in context.user_data:
        del context.user_data['current_wallet_name']
    
    await update.message.reply_text(
        "Wallet renaming canceled."
    )
    
    return ConversationHandler.END

# Create the conversation handler
rename_wallet_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("rename_wallet", rename_wallet_command)],
    states={
        WAITING_FOR_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_new_name)],
    },
    fallbacks=[CommandHandler("cancel", cancel)]
) 