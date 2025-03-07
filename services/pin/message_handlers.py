"""
Message handlers for PIN input and other special message types.

This module contains handlers for processing user input that isn't
directly tied to commands, such as PIN input and other confirmation
responses.
"""
import logging
import traceback
from telegram import Update
from telegram.ext import ContextTypes
from services.pin.PINManager import pin_manager

logger = logging.getLogger(__name__)

async def handle_pin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle direct PIN input from the user.
    
    This function is triggered when a user sends a message that might be
    a PIN in response to a PIN request. It checks if there's a pending
    command that requires PIN verification, verifies the PIN, and then
    executes the appropriate command handler.
    
    Args:
        update: The update containing the message
        context: The context for the handler
        
    Returns:
        None
    """
    user_id = update.effective_user.id
    input_text = update.message.text
    
    # Check if there's a pending command that requires PIN
    if 'pending_command' not in context.user_data:
        # No pending command, ignore this input
        return
    
    pending_command = context.user_data['pending_command']
    logger.debug(f"Processing potential PIN input for pending command: {pending_command}")
    
    # First try to delete the PIN message for security
    try:
        await update.message.delete()
        logger.debug(f"Deleted PIN input message for security")
    except Exception as e:
        logger.warning(f"Could not delete PIN message: {e}")
    
    # Try to verify the PIN
    if not pin_manager.verify_pin(user_id, input_text):
        # Send this as a new message since we deleted the original
        await update.message.reply_text(
            "❌ Invalid PIN. Please try again or use the original command."
        )
        # Keep the pending command to allow retry
        return
    
    # PIN is verified, store it in context for the handler
    context.user_data['pin'] = input_text
    
    # Clear the pending command
    del context.user_data['pending_command']
    
    # Try to execute the appropriate command handler
    try:
        # Import command handlers here to avoid circular imports
        from commands.wallet import wallet_command
        from commands.backup import backup_command
        from commands.export_key import export_key_command
        
        # Map of command names to handlers
        command_handlers = {
            'wallet_command': wallet_command,
            'backup_command': backup_command,
            'export_key_command': export_key_command
            # Add more command handlers as needed
        }
        
        # Execute the appropriate handler
        if pending_command in command_handlers:
            logger.info(f"Executing {pending_command} with verified PIN")
            await command_handlers[pending_command](update, context)
        else:
            logger.warning(f"No handler found for pending command: {pending_command}")
            await update.message.reply_text(
                "✅ PIN verified, but I couldn't find the appropriate handler. "
                "Please try the command again."
            )
    except Exception as e:
        logger.error(f"Error executing command {pending_command} after PIN verification: {e}")
        logger.error(traceback.format_exc())
        await update.message.reply_text(
            "❌ An error occurred while processing your request. Please try again later."
        ) 