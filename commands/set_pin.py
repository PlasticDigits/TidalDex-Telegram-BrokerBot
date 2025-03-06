"""
Command for setting or changing the user's PIN.
"""
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
import re
import logging
from utils.pin_ops import save_user_pin, verify_pin, has_pin

# Enable logging
logger = logging.getLogger(__name__)

# Conversation states
ENTERING_PIN, CONFIRMING_PIN, ENTERING_CURRENT_PIN = range(3)

# Temporary data storage
user_temp_data = {}

async def set_pin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the process of setting or changing a PIN."""
    user_id = update.effective_user.id
    
    # Check if user already has a PIN
    if has_pin(user_id):
        await update.message.reply_text(
            "You already have a PIN set.\n\n"
            "Please enter your current PIN to continue, or use /cancel to abort."
        )
        return ENTERING_CURRENT_PIN
    else:
        await update.message.reply_text(
            "Setting a PIN adds an extra layer of security to your wallet.\n\n"
            "Your PIN will be required for sensitive operations such as viewing private keys "
            "and making transactions.\n\n"
            "Please enter a 4-8 digit PIN. For security, the PIN should only contain numbers."
        )
        return ENTERING_PIN

async def process_current_pin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Verify the current PIN before allowing changes."""
    user_id = update.effective_user.id
    current_pin = update.message.text.strip()
    
    # Delete the message with PIN for security
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Could not delete message with PIN: {e}")
    
    # Verify the current PIN
    if verify_pin(user_id, current_pin):
        await update.message.reply_text(
            "PIN verified.\n\n"
            "Please enter your new PIN. For security, the PIN should be 4-8 digits."
        )
        return ENTERING_PIN
    else:
        await update.message.reply_text(
            "❌ Incorrect PIN. Please try again or use /cancel to abort."
        )
        return ENTERING_CURRENT_PIN

async def process_pin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the user's new PIN."""
    user_id = update.effective_user.id
    new_pin = update.message.text.strip()
    
    # Delete the message with PIN for security
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Could not delete message with PIN: {e}")
    
    # Validate PIN format
    if not re.match(r'^\d{4,8}$', new_pin):
        await update.message.reply_text(
            "❌ Invalid PIN format. The PIN must be 4-8 digits.\n\n"
            "Please try again or use /cancel to abort."
        )
        return ENTERING_PIN
    
    # Store PIN temporarily
    user_temp_data[user_id] = {'pin': new_pin}
    
    # Ask for confirmation
    await update.message.reply_text(
        "Please confirm your PIN by entering it again."
    )
    return CONFIRMING_PIN

async def confirm_pin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirm the PIN and save it if it matches."""
    user_id = update.effective_user.id
    confirmation_pin = update.message.text.strip()
    
    # Delete the message with PIN for security
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Could not delete message with PIN: {e}")
    
    # Check if user has temp data
    if user_id not in user_temp_data or 'pin' not in user_temp_data[user_id]:
        await update.message.reply_text(
            "❌ Something went wrong. Please start over with /set_pin."
        )
        return ConversationHandler.END
    
    original_pin = user_temp_data[user_id]['pin']
    
    # Check if PINs match
    if confirmation_pin != original_pin:
        await update.message.reply_text(
            "❌ PINs do not match. Please try again."
        )
        return ENTERING_PIN
    
    # Save the PIN
    success = save_user_pin(user_id, original_pin)
    
    # Clean up temp data
    if user_id in user_temp_data:
        del user_temp_data[user_id]
    
    if success:
        await update.message.reply_text(
            "✅ PIN set successfully!\n\n"
            "Your PIN will now be required for sensitive operations. "
            "Please remember this PIN as it's used to secure your wallet data."
        )
    else:
        await update.message.reply_text(
            "❌ Failed to set PIN. Please try again later."
        )
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the PIN setting process."""
    user_id = update.effective_user.id
    
    # Clean up temp data
    if user_id in user_temp_data:
        del user_temp_data[user_id]
    
    await update.message.reply_text(
        "PIN setup cancelled. Your PIN remains unchanged."
    )
    
    return ConversationHandler.END 