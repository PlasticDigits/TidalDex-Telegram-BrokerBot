from typing import Any, Callable, Awaitable, Optional, Coroutine
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from db.utils import hash_user_id

async def private_chat_only(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE, 
    next_handler: Callable[[Update, ContextTypes.DEFAULT_TYPE], Coroutine[Any, Any, Any]]
) -> Optional[Any]:
    """
    Check if the chat is private, otherwise redirect to DM.
    
    Args:
        update: The update object
        context: The context object
        next_handler: The handler function to call if the chat is private
        
    Returns:
        Optional[Any]: The result of the next_handler or None if not in a private chat
    """
    if update.effective_chat and update.effective_chat.type != 'private':
        bot_username = context.bot.username
        
        # Safely get command from update.message
        command: str = "/start"
        if hasattr(update, 'message') and update.message and hasattr(update.message, 'text') and update.message.text:
            command = update.message.text.split()[0]
        
        # Check if we can reply to the message
        if hasattr(update, 'message') and update.message:
            try:
                await update.message.reply_text(
                    f"⚠️ For security reasons, I only work in private messages.\n\n"
                    f"Please send me a direct message by clicking @{bot_username}, pressing 'Start', "
                    f"and then sending the {command} command."
                )
            except Exception:
                pass
        # If there's no message to reply to (e.g., callback query)
        elif hasattr(update, 'callback_query') and update.callback_query:
            try:
                await update.callback_query.answer(
                    f"⚠️ Please message me privately @{bot_username}"
                )
            except Exception:
                pass
        return None
    
    # If it's a private chat, proceed with the original handler
    return await next_handler(update, context)

# Create wrapper functions for each command handler
def create_private_chat_wrapper(
    handler_func: Callable[[Update, ContextTypes.DEFAULT_TYPE], Coroutine[Any, Any, Any]]
) -> Callable[[Update, ContextTypes.DEFAULT_TYPE], Coroutine[Any, Any, Any]]:
    """
    Factory function to create private chat wrappers for handlers.
    
    Args:
        handler_func: The handler function to wrap
        
    Returns:
        Callable: A wrapped handler function that only works in private chats
    """
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
        # For any handler, first check if it's in a private chat
        # If not, private_chat_only will send the redirect message
        result = await private_chat_only(update, context, handler_func)
        
        # If we're in a group chat, the original handler won't run
        # For conversation handlers, we need to end the conversation
        if hasattr(update, 'effective_chat') and update.effective_chat and update.effective_chat.type != 'private':
            return result  # Will be None for group chats
        # For private chats, just return whatever the handler returned
        return result
    return wrapper 