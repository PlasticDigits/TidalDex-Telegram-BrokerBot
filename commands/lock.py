"""
Lock command to secure the wallet by clearing stored PIN.
"""
from telegram import Update
from telegram.ext import ContextTypes
from typing import Optional
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
    # Check if effective_user exists
    if update.effective_user is None:
        logger.error("Cannot process lock command: effective_user is None")
        return

    user_id: int = update.effective_user.id
    user_id_str: str = hash_user_id(user_id)
    
    # Check if the user has a PIN stored
    pin: Optional[str] = pin_manager.get_pin(user_id)
    
    # Check if message exists
    if update.message is None:
        logger.error(f"Cannot process lock command for user {user_id_str}: message is None")
        return
    
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