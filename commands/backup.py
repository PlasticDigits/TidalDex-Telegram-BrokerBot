import time
from telegram import Update
from telegram.error import BadRequest
from telegram.ext import CallbackContext
from telegram.constants import ParseMode
from db.mnemonic import get_user_mnemonic
from db.utils import hash_user_id
from services.pin import require_pin, pin_manager
import logging
import traceback

# Configure module logger
logger = logging.getLogger(__name__)

async def backup_command(update: Update, context: CallbackContext):
    """
    Handle the /backup command to display the mnemonic phrase.
    """
    user_id = update.effective_user.id
    user_id_str = hash_user_id(user_id)
    
    logger.info(f"Backup command initiated by user {user_id_str}")
    
    # Get the PIN from PINManager
    pin = pin_manager.get_pin(user_id)
    
    # Get the mnemonic phrase
    try:
        mnemonic = get_user_mnemonic(user_id, pin)
        
        if not mnemonic:
            logger.error(f"Failed to retrieve mnemonic for user {user_id_str}")
            await update.message.reply_text(
                "❌ Failed to retrieve your recovery phrase. Please try again later."
            )
            return
        
        # Format the mnemonic phrase
        formatted_mnemonic = f"```\n{mnemonic}\n```"
        
        # Send the mnemonic phrase with a warning
        await update.message.reply_text(
            "⚠️ *IMPORTANT SECURITY WARNING* ⚠️\n\n"
            "Below is your recovery phrase. It provides *FULL ACCESS* to your wallet funds.\n\n"
            "🔒 *NEVER* share this with anyone\n"
            "🔒 *NEVER* enter it on any website\n"
            "🔒 Store it in a secure, offline location\n\n"
            f"Your recovery phrase:\n{formatted_mnemonic}\n\n"
            "⚠️ *Screenshot and delete this message immediately* ⚠️",
            parse_mode=ParseMode.MARKDOWN
        )
        
        logger.info(f"Mnemonic phrase successfully displayed to user {user_id_str}")
    except Exception as e:
        logger.error(f"Error in backup command for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        await update.message.reply_text(
            "❌ An error occurred while retrieving your recovery phrase. Please try again later."
        )

# Create a PIN-protected version of the command
pin_protected_backup = require_pin(
    "🔒 Viewing your recovery phrase requires PIN verification.\nPlease enter your PIN:"
)(backup_command) 