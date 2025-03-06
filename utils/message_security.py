"""
Message security utilities for sensitive information handling.
"""
import asyncio
import logging
from telegram import Message, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
from telegram.error import TelegramError
from utils.pin_ops import verify_pin, has_pin

logger = logging.getLogger(__name__)

# Callback data prefixes for buttons
SHOW_SENSITIVE_INFO = "show_sensitive_info:"
DELETE_NOW = "delete_sensitive_info:"
VERIFY_PIN = "verify_pin:"

# Store PIN verification attempts
pin_verification_attempts = {}
MAX_PIN_ATTEMPTS = 3

async def send_self_destructing_message(update: Update, context: CallbackContext, text: str, parse_mode: str = None, countdown_seconds: int = 10):
    """
    Send a message that will self-destruct after a countdown.
    First warns the user and requires confirmation before showing sensitive info.
    If user has a PIN set, requires PIN verification first.
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
        
        # Check if user has a PIN set
        if has_pin(user_id):
            # Create PIN verification message with inline keyboard
            keyboard = [
                [InlineKeyboardButton("🔐 Enter PIN to Continue", callback_data=f"{VERIFY_PIN}{message_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Send PIN verification message
            warning_message = await update.message.reply_text(
                "🔒 *SECURITY VERIFICATION REQUIRED*\n\n"
                "This operation requires your security PIN.\n"
                "Click the button below to enter your PIN.",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
            
            # Initialize PIN verification attempts
            pin_verification_attempts[user_id] = 0
        else:
            # Create warning message with inline keyboard
            keyboard = [
                [InlineKeyboardButton("✅ Show Sensitive Information", callback_data=f"{SHOW_SENSITIVE_INFO}{message_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Send warning message first
            warning_message = await update.message.reply_text(
                "⚠️ *SECURITY WARNING*\n\n"
                "You are about to view sensitive information that will automatically "
                f"self-destruct after {countdown_seconds} seconds.\n\n"
                "• Make sure no one is looking at your screen\n"
                "• Be ready to note down the information\n"
                "• This data is critical for wallet access/recovery\n\n"
                "Click the button below when you're ready to view the sensitive information.",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        
        # Initialize the sensitive_messages dict if it doesn't exist
        if 'sensitive_messages' not in context.user_data:
            context.user_data['sensitive_messages'] = {}
        
        # Store both the text and warning message for later use
        context.user_data['sensitive_messages'][message_id] = {
            "text": text,
            "parse_mode": parse_mode,
            "warning_message": warning_message,
            "countdown_seconds": countdown_seconds,
            "chat_id": update.effective_chat.id,
            "user_id": update.effective_user.id,
            "requires_pin": has_pin(user_id)
        }
        
        # The actual sensitive info will be shown when the user clicks the button
        # via a callback handler that should be registered elsewhere
        
        # Return None for now - actual message will be sent later
        return None
    except Exception as e:
        logger.error(f"Error setting up self-destructing message: {e}")
        # Try to send the message normally if the setup fails
        return await update.message.reply_text(
            "❌ Failed to set up secure message. Please try again later.", 
            parse_mode="Markdown"
        )

async def verify_pin_callback(update: Update, context: CallbackContext):
    """
    Callback handler for when user clicks to verify PIN.
    Should be registered with the Application's callback_query_handler.
    """
    query = update.callback_query
    await query.answer()
    
    # Extract message_id from callback data
    message_id = query.data.replace(VERIFY_PIN, "")
    user_id = update.effective_user.id
    
    # Get stored sensitive info from user data
    if 'sensitive_messages' not in context.user_data or message_id not in context.user_data['sensitive_messages']:
        await query.edit_message_text("❌ Information expired or not available.")
        return
    
    # Ask user to enter PIN
    await query.edit_message_text(
        "🔐 Please enter your PIN to continue.\n\n"
        "Reply to this message with your PIN."
    )
    
    # Store the message ID for reference
    if 'pin_verification' not in context.user_data:
        context.user_data['pin_verification'] = {}
    
    context.user_data['pin_verification'][user_id] = {
        'message_id': message_id,
        'verification_message_id': query.message.message_id
    }

async def process_pin_verification(update: Update, context: CallbackContext):
    """
    Process PIN verification for sensitive operations.
    This should be registered as a message handler.
    """
    user_id = update.effective_user.id
    pin = update.message.text.strip()
    
    # Delete the message with PIN for security
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Could not delete message with PIN: {e}")
    
    # Check if we're expecting a PIN from this user
    if 'pin_verification' not in context.user_data or user_id not in context.user_data['pin_verification']:
        return
    
    # Get the message ID for the sensitive content
    verification_data = context.user_data['pin_verification'][user_id]
    message_id = verification_data.get('message_id')
    verification_message_id = verification_data.get('verification_message_id')
    
    # Verify the PIN
    if verify_pin(user_id, pin):
        # PIN is correct, show the sensitive information
        # Delete the verification message
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=verification_message_id
            )
        except:
            pass
        
        # Show the sensitive information
        await show_sensitive_information_with_id(update, context, message_id)
        
        # Clean up verification data
        del context.user_data['pin_verification'][user_id]
    else:
        # PIN is incorrect
        pin_verification_attempts[user_id] = pin_verification_attempts.get(user_id, 0) + 1
        
        if pin_verification_attempts[user_id] >= MAX_PIN_ATTEMPTS:
            # Too many failed attempts
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=verification_message_id,
                text="❌ Too many failed PIN attempts. Operation cancelled for security."
            )
            
            # Clean up verification data
            del context.user_data['pin_verification'][user_id]
            if user_id in pin_verification_attempts:
                del pin_verification_attempts[user_id]
                
            # Delete the sensitive data
            if 'sensitive_messages' in context.user_data and message_id in context.user_data['sensitive_messages']:
                del context.user_data['sensitive_messages'][message_id]
        else:
            # Allow retry
            await context.bot.edit_message_text(
                chat_id=update.effective_chat.id,
                message_id=verification_message_id,
                text=f"❌ Incorrect PIN. Please try again. ({pin_verification_attempts[user_id]}/{MAX_PIN_ATTEMPTS} attempts)\n\n"
                     "Reply to this message with your PIN."
            )

async def show_sensitive_information_with_id(update: Update, context: CallbackContext, message_id: str):
    """
    Show sensitive information based on message ID.
    """
    # Get stored sensitive info
    if 'sensitive_messages' not in context.user_data or message_id not in context.user_data['sensitive_messages']:
        return
    
    info = context.user_data['sensitive_messages'][message_id]
    text = info["text"]
    parse_mode = info["parse_mode"]
    countdown_seconds = info["countdown_seconds"]
    warning_message = info.get("warning_message")
    chat_id = info.get("chat_id", update.effective_chat.id)
    
    # Delete the warning message if it exists
    if warning_message:
        try:
            await warning_message.delete()
        except:
            pass
    
    # Add "Delete Now" button to sensitive content
    delete_keyboard = [
        [InlineKeyboardButton("🗑️ Delete Now", callback_data=f"{DELETE_NOW}{message_id}")]
    ]
    delete_markup = InlineKeyboardMarkup(delete_keyboard)
    
    # Send the actual sensitive message with countdown
    countdown_marker = f"\n\n⏱️ This message will self-destruct in {countdown_seconds} seconds"
    countdown_text = text + countdown_marker
    
    sensitive_message = await context.bot.send_message(
        chat_id=chat_id,
        text=countdown_text, 
        parse_mode=parse_mode,
        reply_markup=delete_markup
    )
    
    # Store message reference
    context.user_data['sensitive_messages'][message_id]["sensitive_message"] = sensitive_message
    
    # Start countdown in background task
    asyncio.create_task(
        run_countdown(update, context, message_id, sensitive_message, text, parse_mode, countdown_seconds)
    )

async def show_sensitive_information(update: Update, context: CallbackContext):
    """
    Callback handler for when user clicks to show sensitive information.
    Should be registered with the Application's callback_query_handler.
    """
    query = update.callback_query
    await query.answer()
    
    # Extract message_id from callback data
    message_id = query.data.replace(SHOW_SENSITIVE_INFO, "")
    
    # Show the sensitive information
    await show_sensitive_information_with_id(update, context, message_id)

async def delete_sensitive_information(update: Update, context: CallbackContext):
    """
    Callback handler for when user clicks "Delete Now".
    Should be registered with the Application's callback_query_handler.
    """
    query = update.callback_query
    await query.answer("Deleting sensitive information...")
    
    # Extract message_id from callback data
    message_id = query.data.replace(DELETE_NOW, "")
    
    # Get stored info
    if 'sensitive_messages' not in context.user_data or message_id not in context.user_data['sensitive_messages']:
        return
    
    info = context.user_data['sensitive_messages'][message_id]
    sensitive_message = info.get("sensitive_message")
    chat_id = update.effective_chat.id
    
    # Delete the sensitive message immediately
    if sensitive_message:
        try:
            await sensitive_message.delete()
            # Send confirmation directly to the chat
            await context.bot.send_message(
                chat_id=chat_id,
                text="🔒 Message containing sensitive information has been deleted for security."
            )
        except TelegramError as e:
            logger.warning(f"Error deleting sensitive message: {e}")
    
    # Clean up stored data
    del context.user_data['sensitive_messages'][message_id]

async def run_countdown(update: Update, context: CallbackContext, message_id: str, message: Message, text: str, parse_mode: str, countdown_seconds: int):
    """
    Run the countdown timer and delete the message when done.
    """
    try:
        # Store the last text we sent to avoid redundant updates
        last_text = None
        chat_id = message.chat_id
        
        # Send countdown updates
        for i in range(countdown_seconds, 0, -1):
            # Check if message was deleted early
            if 'sensitive_messages' not in context.user_data or message_id not in context.user_data['sensitive_messages']:
                return
                
            # Update every second
            await asyncio.sleep(1)
            
            # Update the countdown text and keep the Delete Now button
            delete_keyboard = [
                [InlineKeyboardButton("🗑️ Delete Now", callback_data=f"{DELETE_NOW}{message_id}")]
            ]
            delete_markup = InlineKeyboardMarkup(delete_keyboard)
            
            # Update the countdown text
            updated_text = text + f"\n\n⏱️ This message will self-destruct in {i} seconds"
            
            # Only send update if text has changed
            if updated_text != last_text:
                try:
                    await message.edit_text(updated_text, parse_mode=parse_mode, reply_markup=delete_markup)
                    last_text = updated_text
                except TelegramError as e:
                    if "Message is not modified" in str(e):
                        # This is expected if the content hasn't changed
                        logger.debug("Message content unchanged, skipping update")
                    else:
                        logger.warning(f"Error updating countdown: {e}")
                        # Message might have been deleted by user or another error occurred
                        return
        
        # Delete the message after countdown
        try:
            await message.delete()
            
            # Send confirmation to the chat directly instead of replying to a deleted message
            await context.bot.send_message(
                chat_id=chat_id,
                text="🔒 Message containing sensitive information has been deleted for security."
            )
        except TelegramError as e:
            logger.warning(f"Error deleting message after countdown: {e}")
            # Message might have already been deleted
            
        # Clean up stored data
        if 'sensitive_messages' in context.user_data and message_id in context.user_data['sensitive_messages']:
            del context.user_data['sensitive_messages'][message_id]
            
    except Exception as e:
        logger.error(f"Error in countdown: {e}")
        try:
            # Try to delete anyway
            await message.delete()
        except:
            pass 