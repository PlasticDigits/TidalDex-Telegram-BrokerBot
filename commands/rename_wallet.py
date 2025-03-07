"""
Command for renaming the currently active wallet.
"""
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
import db
from db.wallet import get_active_wallet_name
from db.utils import hash_user_id
from services.pin import pin_manager
import logging
# Enable logging
logger = logging.getLogger(__name__)

# Conversation states
WAITING_FOR_NAME = 0

# Store temporary data during conversation
user_temp_data = {}

async def rename_wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start the process to rename the currently active wallet.
    """
    user_id = update.effective_user.id
    user_id_str = hash_user_id(user_id)
    logger.debug(f"Rename wallet command initiated by user {user_id_str}")
    
    # Get active wallet name and PIN
    wallet_name = get_active_wallet_name(user_id)
    pin = pin_manager.get_pin(user_id)
    
    # Check if user has a wallet
    user_wallet = db.get_user_wallet(user_id, wallet_name, pin)
    
    if not user_wallet:
        await update.message.reply_text(
            "You don't have a wallet yet. Use /wallet to create one first."
        )
        return ConversationHandler.END
    
    # Get wallet name
    wallet_name = user_wallet.get('name', 'Default')
    
    await update.message.reply_text(
        f"You are about to rename your active wallet: '{wallet_name}'\n\n"
        "Please enter a new name for this wallet (3-32 characters):\n\n"
        "✅ Letters, numbers, spaces, emoji are allowed\n"
        "❌ Names cannot start or end with spaces\n"
        "❌ Some reserved names and special characters are not allowed"
    )
    
    return WAITING_FOR_NAME

async def process_new_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Process the new wallet name provided by the user.
    Supports enhanced validation including emoji support.
    """
    user_id = update.effective_user.id
    new_name = update.message.text.strip()
    
    # Let the database validation handle the checks
    # The rename_wallet function now has comprehensive validation
    success, message = db.rename_wallet(user_id, new_name)
    
    if success:
        await update.message.reply_text(
            f"✅ Wallet renamed successfully from '{message}' to '{new_name}'!"
        )
        return ConversationHandler.END
    else:
        # Display the detailed validation error message
        await update.message.reply_text(
            f"❌ Failed to rename wallet: {message}\n\n"
            "Please try again with a different name or use /cancel to abort."
        )
        return WAITING_FOR_NAME

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancel the current operation.
    """
    await update.message.reply_text(
        "Wallet renaming cancelled."
    )
    
    return ConversationHandler.END 