"""
Message handlers for PIN input and other special message types.

This module contains handlers for processing user input that isn't
directly tied to commands, such as PIN input and other confirmation
responses.
"""
import logging
import traceback
from typing import Dict, Any, Callable, Awaitable, Optional, List, Union, cast
from telegram import Update
from telegram.ext import ContextTypes
from services.pin.PINManager import pin_manager

logger = logging.getLogger(__name__)

async def handle_pin_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    if not update.effective_user or not update.message or not update.message.text:
        logger.warning("Missing user or message data in PIN input handler")
        return
        
    user_id: int = update.effective_user.id
    input_text: str = update.message.text
    
    # Check if user_data exists, if not initialize it
    if context.user_data is None:
        logger.warning("User data is None in PIN input handler")
        return
    
    # Check if there's a pending command that requires PIN
    if 'pending_command' not in context.user_data:
        # No pending command, ignore this input
        return
    
    pending_command: str = context.user_data['pending_command']
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
        from commands.backup import backup_command
        from commands.export_key import export_key_command
        from commands.addwallet import addwallet_command
        from commands.balance import balance_command
        from commands.scan import scan_command
        # Map of command names to handlers
        # Only works with commands that are not ConversationHandlers
        command_handlers: Dict[str, Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[Any]]] = {
            'backup_command': backup_command,
            'export_key_command': export_key_command,
            'addwallet_command': addwallet_command,
            'balance_command': balance_command,
            'scan_command': scan_command,
            # Add more command handlers as needed
        }
        
        # Execute the appropriate handler
        logger.info(f"Checking {pending_command} is in command_handlers")
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