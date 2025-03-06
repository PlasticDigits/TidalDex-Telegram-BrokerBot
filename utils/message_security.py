"""
Message security utilities for sensitive information handling.
"""
import asyncio
import logging
from telegram import Message, Update
from telegram.error import TelegramError

logger = logging.getLogger(__name__)

async def send_self_destructing_message(update: Update, text: str, parse_mode: str = None, countdown_seconds: int = 10):
    """
    Send a message that will self-destruct after a countdown.
    
    Args:
        update (Update): Telegram update object
        text (str): Message text to send
        parse_mode (str, optional): Telegram parse mode (Markdown, HTML)
        countdown_seconds (int): Number of seconds before deletion
        
    Returns:
        Message: The sent message object
    """
    try:
        # Send the initial message
        message = await update.message.reply_text(text, parse_mode=parse_mode)
        
        # Calculate initial message length for consistent UI
        countdown_marker = f"\n\n⏱️ This message will self-destruct in {countdown_seconds} seconds"
        countdown_text = text + countdown_marker
        
        # Send countdown updates
        for i in range(countdown_seconds, 0, -1):
            # Update every second
            await asyncio.sleep(1)
            try:
                # Update the countdown text
                updated_text = text + f"\n\n⏱️ This message will self-destruct in {i} seconds"
                await message.edit_text(updated_text, parse_mode=parse_mode)
            except TelegramError as e:
                logger.warning(f"Error updating countdown: {e}")
        
        # Delete the message
        await message.delete()
        
        # Send confirmation that sensitive info was deleted
        await update.message.reply_text(
            "🔒 Message containing sensitive information has been deleted for security."
        )
        
        return message
    except Exception as e:
        logger.error(f"Error in self-destructing message: {e}")
        # Try to send the message normally if the countdown fails
        return await update.message.reply_text(
            text + "\n\n⚠️ Failed to setup auto-deletion. Please delete this message manually.", 
            parse_mode=parse_mode
        ) 