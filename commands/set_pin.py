"""
Command for setting or changing the user's PIN.
"""
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
import logging
from utils.pin_ops import save_user_pin, verify_pin, has_pin, validate_pin_complexity, can_attempt_pin

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
        # Check if user is allowed to attempt PIN entry (not in lockout period)
        can_attempt, lockout_remaining = can_attempt_pin(user_id)
        if not can_attempt:
            # User is in lockout period
            minutes = lockout_remaining // 60
            seconds = lockout_remaining % 60
            time_str = f"{minutes} minute(s) and {seconds} second(s)" if minutes > 0 else f"{seconds} second(s)"
            
            await update.message.reply_text(
                f"⚠️ Your account is temporarily locked due to too many failed PIN attempts.\n\n"
                f"Please try again in {time_str}."
            )
            return ConversationHandler.END
        
        await update.message.reply_text(
            "You already have a PIN set.\n\n"
            "Please enter your current PIN to continue, or use /cancel to abort."
        )
        return ENTERING_CURRENT_PIN
    else:
        await update.message.reply_text(
            "🔐 Setting a PIN adds an extra layer of security to your wallet.\n\n"
            "Your PIN will be required for sensitive operations such as viewing private keys "
            "and making transactions.\n\n"
            "PIN requirements:\n"
            "• Must be 4-48 characters long\n"
            "• Can include letters, numbers, and special characters\n"
            "• Its your responsibility to choose a secure PIN\n"
            "• 1111 is better than nothing, but not secure\n"
            "Please create your PIN:"
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
    
    # Check if user is allowed to attempt PIN entry
    can_attempt, lockout_remaining = can_attempt_pin(user_id)
    if not can_attempt:
        # User is in lockout period
        minutes = lockout_remaining // 60
        seconds = lockout_remaining % 60
        time_str = f"{minutes} minute(s) and {seconds} second(s)" if minutes > 0 else f"{seconds} second(s)"
        
        await update.message.reply_text(
            f"⚠️ Your account is temporarily locked due to too many failed PIN attempts.\n\n"
            f"Please try again in {time_str}."
        )
        return ConversationHandler.END
    
    # Verify the current PIN
    if verify_pin(user_id, current_pin):
        await update.message.reply_text(
            "PIN verified.\n\n"
            "PIN requirements:\n"
            "• Must be 4-48 characters long\n"
            "• Can include letters, numbers, and special characters\n"
            "• Its your responsibility to choose a secure PIN\n"
            "• 1111 is better than nothing, but not secure\n"
            "Please enter your new PIN:"
        )
        return ENTERING_PIN
    else:
        # Get updated lockout status after the failed attempt
        can_attempt, lockout_remaining = can_attempt_pin(user_id)
        
        if not can_attempt:
            # User is now in lockout period after this failed attempt
            minutes = lockout_remaining // 60
            seconds = lockout_remaining % 60
            time_str = f"{minutes} minute(s) and {seconds} second(s)" if minutes > 0 else f"{seconds} second(s)"
            
            await update.message.reply_text(
                f"❌ Incorrect PIN. Too many failed attempts.\n\n"
                f"Your account is temporarily locked for {time_str}."
            )
            return ConversationHandler.END
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
    
    # Validate PIN format using enhanced complexity validation
    is_valid, error_message = validate_pin_complexity(new_pin)
    if not is_valid:
        await update.message.reply_text(
            f"❌ {error_message}\n\n"
            "PIN requirements:\n"
            "• Must be 6-8 digits long\n"
            "• Must contain only numbers\n"
            "• Cannot contain the same digit repeated more than 3 times in a row\n"
            "• Cannot contain sequential digits like 1234 or 4321\n"
            "• Cannot be all the same digit\n\n"
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
    
    # Save the PIN with the new function that returns success status and error message
    success, error_message = save_user_pin(user_id, original_pin)
    
    # Clean up temp data
    if user_id in user_temp_data:
        del user_temp_data[user_id]
    
    if success:
        await update.message.reply_text(
            "✅ PIN set successfully!\n\n"
            "Your PIN will now be required for sensitive operations. "
            "Please remember this PIN as it's used to secure your wallet data.\n\n"
            "⚠️ If you enter an incorrect PIN too many times, your account will be temporarily locked "
            "as a security measure."
        )
    else:
        await update.message.reply_text(
            f"❌ Failed to set PIN. {error_message}\n\n"
            "Please try again later."
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