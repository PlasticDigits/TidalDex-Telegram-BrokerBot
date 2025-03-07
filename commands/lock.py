"""
Lock command to secure the wallet by clearing stored PIN.
"""
from telegram import Update
from telegram.ext import ContextTypes
from services.pin import pin_manager
from db.utils import hash_user_id
import logging

# Enable logging
logger = logging.getLogger(__name__)

async def lock_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Lock the wallet by clearing the stored PIN.
    
    This provides a way for users to manually secure their wallet
    without waiting for the PIN to expire automatically.
    """
    user_id = update.effective_user.id
    user_id_str = hash_user_id(user_id)
    
    # Check if the user has a PIN stored
    pin = pin_manager.get_pin(user_id)
    
    if pin:
        # User has a PIN stored, clear it
        pin_manager.clear_pin(user_id)
        logger.info(f"Wallet locked for user {user_id_str}")
        await update.message.reply_text(
            "🔒 Your wallet has been locked.\n\n"
            "You'll need to enter your PIN again for sensitive operations."
        )
    else:
        # No PIN stored, already locked
        logger.info(f"Wallet already locked for user {user_id_str}")
        await update.message.reply_text(
            "🔒 Your wallet cannot be locked!\n\n"
            "Run /set_pin to set a PIN for locking your wallet."
        ) 