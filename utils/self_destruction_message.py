"""
Self-destructing message utilities for sensitive information handling.

This module provides functionality for sending self-destructing messages
that automatically delete after a specified time period.
"""
import asyncio
import logging
from telegram import Message, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from telegram.error import TelegramError
import traceback

logger = logging.getLogger(__name__)

# Callback data prefixes for buttons - MUST MATCH EXACTLY in all functions
SHOW_SENSITIVE_INFO = "show_sensitive_info:"
DELETE_NOW = "delete_sensitive_info:"

# Define a function to create the delete button to ensure consistency
def create_delete_button(message_id, countdown=None):
    """Create a standardized delete button with consistent callback data format"""
    button_text = "🗑️ Delete Now" if countdown is None else f"🗑️ Delete Now ({countdown}s)"
    callback_data = f"{DELETE_NOW}{message_id}"
    logger.debug(f"Creating delete button with callback data: '{callback_data}'")
    return InlineKeyboardButton(button_text, callback_data=callback_data)

async def send_self_destructing_message(update: Update, context: CallbackContext, text: str, parse_mode: str = None, countdown_seconds: int = 10):
    """
    Send a message that will self-destruct after a countdown.
    First warns the user and requires confirmation before showing sensitive info.
    Also provides a "Delete Now" option to immediately destroy the message.
    
    Args:
        update (Update): Telegram update object
        context (CallbackContext): Telegram context object for storing data
        text (str): Message text to send (sensitive information)
        parse_mode (str, optional): Telegram parse mode (Markdown, HTML)
        countdown_seconds (int): Number of seconds before deletion
        
    Returns:
        Message: The sent message object
    """
    try:
        # Generate a unique identifier for this message
        # Use a timestamp to make it unique
        import time
        message_id = str(int(time.time()))
        
        # Initialize the sensitive_messages dict if it doesn't exist
        if 'sensitive_messages' not in context.user_data:
            context.user_data['sensitive_messages'] = {}
        
        # Store the sensitive information for later use
        context.user_data['sensitive_messages'][message_id] = {
            "text": text,
            "parse_mode": parse_mode,
            "countdown_seconds": countdown_seconds,
            "timestamp": time.time()
        }
        
        # Create buttons for the initial security warning
        keyboard = [
            [
                InlineKeyboardButton("📄 Show Information", callback_data=f"{SHOW_SENSITIVE_INFO}{message_id}")
            ],
            [
                create_delete_button(message_id)
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Send the initial security warning
        warning_message = (
            "⚠️ *Security Warning* ⚠️\n\n"
            "You are about to view sensitive information.\n\n"
            "• Make sure no one can see your screen\n"
            "• The information will self-destruct in a few seconds\n"
            "• You can delete it immediately using the Delete button\n\n"
            "Click 'Show Information' when you're ready."
        )
        
        sent_message = await update.message.reply_text(
            warning_message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        # Store the message ID for later reference
        context.user_data['sensitive_messages'][message_id]["warning_message_id"] = sent_message.message_id
        
        return sent_message
    except Exception as e:
        logger.error(f"Error in send_self_destructing_message: {e}")
        logger.error(traceback.format_exc())
        await update.message.reply_text(
            "❌ An error occurred while processing your request. Please try again later."
        )
        return None

async def show_sensitive_information_with_id(update: Update, context: CallbackContext, message_id: str):
    """
    Show sensitive information for a specific message ID.
    This is called when the user clicks the "Show Information" button.
    
    Args:
        update: The update containing the callback query
        context: The context for the handler
        message_id: The message ID of the sensitive information
    """
    query = update.callback_query
    await query.answer()
    
    # Check if the sensitive message data exists
    if 'sensitive_messages' not in context.user_data or message_id not in context.user_data['sensitive_messages']:
        await query.edit_message_text(
            "❌ The information you're trying to access has expired or been deleted."
        )
        return
    
    sensitive_data = context.user_data['sensitive_messages'][message_id]
    text = sensitive_data.get("text", "No information available.")
    parse_mode = sensitive_data.get("parse_mode")
    countdown_seconds = sensitive_data.get("countdown_seconds", 10)
    
    # Edit the message to show the sensitive information
    try:
        message = await query.edit_message_text(
            text,
            parse_mode=parse_mode
        )
        
        # Store the sensitive message ID in the context for later access
        context.user_data['sensitive_messages'][message_id]["sensitive_message_id"] = message.message_id
        
        # Start the countdown to auto-delete
        await run_countdown(update, context, message_id, message, text, parse_mode, countdown_seconds)
        
    except TelegramError as e:
        logger.error(f"Error showing sensitive information: {e}")
        try:
            await query.edit_message_text(
                "❌ Error displaying the information. Please try again later."
            )
        except:
            pass
        return

async def show_sensitive_information(update: Update, context: CallbackContext):
    """
    Show sensitive information when the user clicks the "Show Information" button.
    
    Args:
        update: The update containing the callback query
        context: The context for the handler
    """
    query = update.callback_query
    data = query.data
    
    # Extract the message ID from the callback data
    if data.startswith(SHOW_SENSITIVE_INFO):
        message_id = data[len(SHOW_SENSITIVE_INFO):]
        await show_sensitive_information_with_id(update, context, message_id)

async def delete_sensitive_information(update: Update, context: CallbackContext):
    """
    Delete sensitive information when the user clicks the "Delete Now" button.
    
    Args:
        update: The update containing the callback query
        context: The context for the handler
    """
    query = update.callback_query
    data = query.data
    
    logger.info(f"delete_sensitive_information called with data: '{data}'")
    
    # Extract the message ID from the callback data
    if not data.startswith(DELETE_NOW):
        logger.warning(f"Callback data does not start with DELETE_NOW prefix: '{data}'")
        return
        
    message_id = data[len(DELETE_NOW):]
    logger.info(f"Extracted message_id: '{message_id}' from callback data")
    
    # Always acknowledge the callback query to provide user feedback
    await query.answer("Message deleted successfully")
    
    # Clean up stored data regardless of whether we can delete the message or not
    # This prevents duplicated deletion attempts
    if 'sensitive_messages' in context.user_data and message_id in context.user_data['sensitive_messages']:
        # Remove from context before attempting deletion to prevent race conditions
        context.user_data['sensitive_messages'].pop(message_id, None)
        logger.info(f"Cleaned up sensitive message data for message {message_id}")
    else:
        # Message data already removed (likely already deleted by countdown)
        logger.info(f"Message {message_id} already cleaned up, possibly deleted by countdown")
        return
    
    # Try to delete the message that contains the button
    try:
        # Get message and chat info
        chat_id = update.effective_chat.id
        current_message_id = query.message.message_id
        
        # Try to delete the message
        await context.bot.delete_message(chat_id=chat_id, message_id=current_message_id)
        logger.info(f"Successfully deleted message {current_message_id} by user request")
    except Exception as e:
        # Message might have already been deleted by the countdown
        if "Message to delete not found" in str(e):
            logger.info(f"Message {current_message_id} was already deleted (likely by countdown)")
        else:
            logger.error(f"Error deleting message {current_message_id}: {e}")
            # Only try to edit the message if it's not a "not found" error
            try:
                await query.edit_message_text("✅ Information deleted.")
                logger.info(f"Edited message {current_message_id} as fallback")
            except Exception as edit_error:
                logger.error(f"Failed to edit message: {edit_error}")

async def run_countdown(update: Update, context: CallbackContext, message_id: str, message: Message, text: str, parse_mode: str, countdown_seconds: int):
    """
    Run a countdown for self-destruction of a message.
    
    Args:
        update: The update containing the message
        context: The context for the handler
        message_id: The ID of the message in context storage
        message: The Telegram message object
        text: The original message text
        parse_mode: The parse mode for the message
        countdown_seconds: The number of seconds for the countdown
    """
    chat_id = update.effective_chat.id
    current_message_id = message.message_id
    
    # Run the countdown
    for i in range(countdown_seconds, 0, -1):
        # Check if message was already deleted by user
        if 'sensitive_messages' not in context.user_data or message_id not in context.user_data['sensitive_messages']:
            logger.info(f"Message {message_id} already deleted by user, aborting countdown")
            return
            
        # Only update once per second
        if i <= countdown_seconds:
            # Update the message with just the countdown text in footer
            footer_text = f"\n\n⏱️ Auto-deletes in {i} seconds..."
            
            try:
                # Try to update the message text with countdown
                await message.edit_text(
                    text + footer_text,
                    parse_mode=parse_mode
                )
            except Exception as e:
                if "Message to edit not found" in str(e):
                    logger.info(f"Message {current_message_id} was already deleted manually, aborting countdown")
                    
                    # Clean up stored data if it hasn't been cleaned already
                    if 'sensitive_messages' in context.user_data and message_id in context.user_data['sensitive_messages']:
                        context.user_data['sensitive_messages'].pop(message_id, None)
                        logger.info(f"Cleaned up sensitive message data for already deleted message {message_id}")
                    return
                else:
                    logger.warning(f"Failed to update countdown: {e}")
            
        # Wait 1 second
        await asyncio.sleep(1)
        
    # Before trying to delete, check if the message was already deleted manually
    if 'sensitive_messages' not in context.user_data or message_id not in context.user_data['sensitive_messages']:
        logger.info(f"Message {message_id} already deleted by user, no need to auto-delete")
        return
    
    # Countdown complete, now delete the message
    try:
        # Try to delete using the bot and chat_id/message_id
        await context.bot.delete_message(chat_id=chat_id, message_id=current_message_id)
        logger.info(f"Deleted sensitive message {message_id} after countdown")
    except Exception as e:
        if "Message to delete not found" in str(e):
            logger.info(f"Message {current_message_id} was already deleted manually")
        else:
            logger.error(f"Failed to delete sensitive message: {e}")
            # Only try to edit if not a "not found" error
            try:
                await message.edit_text(
                    "✅ This information has expired and been deleted.",
                    parse_mode=None
                )
            except Exception as edit_error:
                logger.error(f"Failed to edit message after deletion failed: {edit_error}")
    
    # Clean up stored data if it hasn't been cleaned already
    if 'sensitive_messages' in context.user_data and message_id in context.user_data['sensitive_messages']:
        context.user_data['sensitive_messages'].pop(message_id, None)
        logger.info(f"Cleaned up sensitive message data for message {message_id} after countdown")

# Register these handlers in main.py:
"""
# Add handlers for sensitive information buttons
application.add_handler(CallbackQueryHandler(
    show_sensitive_information, 
    pattern=f"^{SHOW_SENSITIVE_INFO}"
))
application.add_handler(CallbackQueryHandler(
    delete_sensitive_information, 
    pattern=f"^{DELETE_NOW}"
))
""" 