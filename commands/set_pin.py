"""
Set PIN command for wallet security.

This module handles setting and updating the user's PIN for wallet security.
"""
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
import logging
import traceback
import re
from db.utils import hash_user_id
from services.pin.PINManager import pin_manager

# Enable logging
logger = logging.getLogger(__name__)

# Conversation states
ENTERING_CURRENT_PIN, ENTERING_PIN, CONFIRMING_PIN = range(3)

# Store temporary data during conversation
user_temp_data = {}

async def set_pin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start the process of setting or updating a PIN.
    If the user already has a PIN, they will be asked to enter it first.
    Otherwise, they will be asked to set a new PIN.
    """
    user_id = update.effective_user.id
    user_id_str = hash_user_id(user_id)
    
    logger.info(f"Set PIN command initiated by user {user_id_str}")
    
    # Initialize user temp data
    if user_id not in user_temp_data:
        user_temp_data[user_id] = {}
    
    # Check if user already has a PIN
    has_existing_pin = pin_manager.needs_pin(user_id)
    user_temp_data[user_id]['is_updating'] = has_existing_pin
    
    if has_existing_pin:
        logger.info(f"User {user_id_str} already has a PIN, will update it")
        await update.message.reply_text(
            "🔐 You already have a PIN set. "
            "To update your PIN, please enter your current PIN first:"
        )
        return ENTERING_CURRENT_PIN
    else:
        logger.info(f"User {user_id_str} does not have a PIN, will set a new one")
        await update.message.reply_text(
            "🔐 Setting a PIN will encrypt your wallet's sensitive data.\n\n"
            "PIN requirements:\n"
            "• Must be 6-48 characters long\n"
            "• Can include letters, numbers, and special characters\n"
            "• You are responsible for picking a secure PIN\n"
            "Please enter your new PIN:"
        )
        return ENTERING_PIN

async def process_current_pin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Verify the user's current PIN before allowing an update.
    """
    user_id = update.effective_user.id
    user_id_str = hash_user_id(user_id)
    current_pin = update.message.text.strip()
    
    # Delete the message with PIN for security
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Could not delete message with current PIN: {e}")
    
    # Verify the current PIN
    if not pin_manager.verify_pin(user_id, current_pin):
        logger.warning(f"Invalid current PIN provided by user {user_id_str}")
        await update.message.reply_text(
            "❌ Invalid PIN. Please try again or use /cancel to abort."
        )
        return ENTERING_CURRENT_PIN
    
    # Store the verified current PIN
    user_temp_data[user_id]['old_pin'] = current_pin
    
    # Request new PIN
    logger.info(f"Current PIN verified for user {user_id_str}, requesting new PIN")
    await update.message.reply_text(
        "✅ Current PIN verified. Please enter your new PIN:\n\n"
        "PIN requirements:\n"
        "PIN requirements:\n"
        "• Must be 6-48 characters long\n"
        "• Can include letters, numbers, and special characters\n"
        "• You are responsible for picking a secure PIN\n"
        "Please enter your new PIN:"
    )
    return ENTERING_PIN

async def process_pin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Process the new PIN entry and check if it meets requirements.
    """
    user_id = update.effective_user.id
    user_id_str = hash_user_id(user_id)
    new_pin = update.message.text.strip()
    
    # Delete the message with PIN for security
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Could not delete message with new PIN: {e}")
    
    # Validate PIN complexity
    is_valid, error_message = validate_pin_complexity(new_pin)
    
    if not is_valid:
        await update.message.reply_text(
            f"❌ {error_message}\n\n"
            "PIN requirements:\n"
            "• Must be 6-48 characters long\n"
            "• You are responsible for picking a secure PIN\n"
            "Please try again or use /cancel to abort."
        )
        return ENTERING_PIN
    
    # Ensure the user temp data structure exists
    if user_id not in user_temp_data:
        user_temp_data[user_id] = {}
    
    # Store PIN temporarily
    user_temp_data[user_id]['pin'] = new_pin
    
    # Preserve is_updating and old_pin flags if this is a PIN update
    if 'is_updating' not in user_temp_data[user_id]:
        user_temp_data[user_id]['is_updating'] = False
    
    # Ask for confirmation
    await update.message.reply_text(
        "Please confirm your PIN by entering it again."
    )
    return CONFIRMING_PIN

async def confirm_pin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Confirm the PIN and save it if it matches."""
    user_id = update.effective_user.id
    user_id_str = hash_user_id(user_id)
    confirmation_pin = update.message.text.strip()
    
    # Delete the message with PIN for security
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Could not delete message with PIN: {e}")
    
    # Check if we have the user's temporary data
    if user_id not in user_temp_data:
        logger.error(f"User temp data not found for user {user_id_str}")
        await update.message.reply_text(
            "❌ An error occurred. Please start over with /set_pin."
        )
        return ConversationHandler.END
    
    # Get the PIN from temporary data
    new_pin = user_temp_data[user_id].get('pin')
    is_updating = user_temp_data[user_id].get('is_updating', False)
    
    # Check if PINs match
    if new_pin != confirmation_pin:
        logger.warning(f"PIN confirmation failed for user {user_id_str}")
        await update.message.reply_text(
            "❌ PINs do not match. Please start over."
        )
        if user_id in user_temp_data:
            del user_temp_data[user_id]
        return ConversationHandler.END
    
    # PINs match, save to database
    try:
        if is_updating:
                # Update the PIN in the PIN manager as well
            logger.info(f"Updating PIN for user {user_id_str} with data re-encryption")
            success = pin_manager.set_pin(user_id, new_pin)
            if success:
                logger.info(f"Successfully updated PIN for user {user_id_str}")
                await update.message.reply_text(
                    "✅ Your PIN has been updated successfully!\n\n"
                    "All your wallets and sensitive data have been re-encrypted with this new PIN.\n\n"
                    "Remember to use this PIN for all sensitive operations"
                )
            else:
                logger.error(f"Failed to update PIN for user {user_id_str}")
                await update.message.reply_text(
                    f"❌ Failed to update PIN. Please try again later."
                )
        else:
            # Set initial PIN in database and encrypt wallet data
            logger.info(f"Setting initial PIN for user {user_id_str} with data re-encryption")
            success = pin_manager.set_pin(user_id, new_pin)
            if success:
                logger.info(f"Successfully set initial PIN for user {user_id_str}")
                await update.message.reply_text(
                    "✅ Your PIN has been set successfully!\n\n"
                    "All your wallets and sensitive data have been re-encrypted with this PIN.\n\n"
                    "You'll need to enter this PIN for all sensitive operations from now on."
                )
            else:
                logger.error(f"Failed to set PIN for user {user_id_str}: {error}")
                await update.message.reply_text(
                    f"❌ Failed to set PIN. Please try again later."
                )
    except Exception as e:
        logger.error(f"Error in PIN operation for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        await update.message.reply_text(
            "❌ An error occurred while setting your PIN. Please try again later."
        )
    
    # Clean up temp data
    if user_id in user_temp_data:
        del user_temp_data[user_id]
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the PIN setting process."""
    user_id = update.effective_user.id
    user_id_str = hash_user_id(user_id)
    
    # Clean up any temporary data
    if user_id in user_temp_data:
        del user_temp_data[user_id]
    
    logger.info(f"PIN setting canceled by user {user_id_str}")
    await update.message.reply_text(
        "🚫 PIN setting canceled. Your current PIN settings remain unchanged."
    )
    return ConversationHandler.END

def validate_pin_complexity(pin):
    """
    Validate that the PIN meets complexity requirements.
    
    Args:
        pin (str): The PIN to validate
        
    Returns:
        tuple: (is_valid, error_message)
    """
    # Check length (6-48 characters)
    if len(pin) < 6 or len(pin) > 48:
        return False, "PIN must be between 6 and 48 characters long."
    
    return True, "" 