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

# Callback data prefixes for buttons
SHOW_SENSITIVE_INFO = "show_sensitive_info:"
DELETE_NOW = "delete_sensitive_info:"

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
        user_id = update.effective_user.id
        
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
                InlineKeyboardButton("❌ Delete", callback_data=f"{DELETE_NOW}{message_id}")
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
    
    # Create button for immediate deletion
    keyboard = [
        [
            InlineKeyboardButton("🗑️ Delete Now", callback_data=f"{DELETE_NOW}{message_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Edit the message to show the sensitive information
    try:
        message = await query.edit_message_text(
            text,
            reply_markup=reply_markup,
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
    
    # Extract the message ID from the callback data
    if data.startswith(DELETE_NOW):
        message_id = data[len(DELETE_NOW):]
        
        # Acknowledge the callback query first
        await query.answer("Deleting message...")
        
        # Delete the message
        try:
            # First check if this is a warning message or a displayed sensitive information message
            if 'sensitive_messages' in context.user_data and message_id in context.user_data['sensitive_messages']:
                message_data = context.user_data['sensitive_messages'][message_id]
                
                # If it's a warning message, delete it
                if "warning_message_id" in message_data:
                    await query.delete_message()
                    logger.debug(f"Warning message {message_id} deleted by user request")
                
                # If sensitive info is displayed, delete that message too
                if "sensitive_message_id" in message_data:
                    try:
                        # Get the chat ID and message ID
                        chat_id = update.effective_chat.id
                        sensitive_message_id = message_data["sensitive_message_id"]
                        
                        # Delete the sensitive message
                        await context.bot.delete_message(chat_id=chat_id, message_id=sensitive_message_id)
                        logger.debug(f"Sensitive information message {sensitive_message_id} deleted by user request")
                    except TelegramError as e:
                        logger.error(f"Error deleting sensitive information message: {e}")
            else:
                # Just delete the current message if we can't find it in the context
                await query.delete_message()
                logger.debug(f"Message deleted by user request (not found in context)")
                
        except TelegramError as e:
            logger.error(f"Error deleting sensitive message: {e}")
            try:
                await query.edit_message_text(
                    "✅ Information deleted."
                )
            except:
                pass
        
        # Clean up stored data
        if 'sensitive_messages' in context.user_data and message_id in context.user_data['sensitive_messages']:
            del context.user_data['sensitive_messages'][message_id]
            logger.debug(f"Cleaned up sensitive message data for message {message_id}")

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
    countdown_complete = False
    delete_failed = False
    
    # Run the countdown
    for i in range(countdown_seconds, 0, -1):
        # Check if message was already deleted by user
        if 'sensitive_messages' not in context.user_data or message_id not in context.user_data['sensitive_messages']:
            logger.debug(f"Message {message_id} already deleted, aborting countdown")
            return
            
        # Only update the countdown every 5 seconds to avoid rate limits
        if i <= 5 or i % 5 == 0:
            # Create button for immediate deletion
            keyboard = [
                [
                    InlineKeyboardButton(f"🗑️ Delete Now ({i}s)", callback_data=f"{DELETE_NOW}{message_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            try:
                # Try to update the message with the countdown
                await message.edit_reply_markup(reply_markup)
            except TelegramError as e:
                logger.warning(f"Failed to update countdown: {e}")
                # Don't break the countdown if we fail to update the button
        
        # Wait 1 second
        await asyncio.sleep(1)
    
    # Countdown complete, delete the message
    try:
        await message.delete()
        countdown_complete = True
        logger.debug(f"Deleted sensitive message {message_id} after countdown")
    except TelegramError as e:
        logger.error(f"Failed to delete sensitive message: {e}")
        delete_failed = True
    
    # Clean up stored data
    if 'sensitive_messages' in context.user_data and message_id in context.user_data['sensitive_messages']:
        del context.user_data['sensitive_messages'][message_id]
        logger.debug(f"Cleaned up sensitive message data for message {message_id}")
    
    # If we couldn't delete, try to edit the message
    if delete_failed:
        try:
            await message.edit_text(
                "✅ This information has expired and been deleted.",
                reply_markup=None
            )
        except:
            pass
        
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