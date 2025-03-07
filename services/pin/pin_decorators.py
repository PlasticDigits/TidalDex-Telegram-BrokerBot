"""
PIN decorators for command handlers.

This module provides decorators that can be used to add PIN verification
to command handlers in a clean, declarative way.
"""
import logging
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from services.pin.PINManager import pin_manager

logger = logging.getLogger(__name__)

def require_pin(verification_message="This command requires your PIN for security. Please enter your PIN."):
    """
    Decorator that adds PIN verification to a command handler.
    
    If the user has a PIN set, this decorator will:
    1. Check if a verified PIN is already available
    2. If not, request a PIN from the user
    3. Once verified, the PIN will be available in context.user_data['pin']
    
    Args:
        verification_message: The message to show when requesting a PIN
        
    Returns:
        Decorator function
    """
    def decorator(handler_func):
        @wraps(handler_func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_id = update.effective_user.id
            command_name = handler_func.__name__
            
            # Check if user needs PIN verification
            if not pin_manager.needs_pin(user_id):
                logger.debug(f"No PIN required for user {user_id}, executing {command_name} directly")
                return await handler_func(update, context)
            
            # Check if we already have a verified PIN
            pin = pin_manager.get_pin(user_id)
            
            if pin:
                # PIN is already verified, store it in context for the handler
                logger.debug(f"Using verified PIN for {command_name} for user {user_id}")
                context.user_data['pin'] = pin
                return await handler_func(update, context)
            
            # No verified PIN available, request one
            logger.debug(f"No verified PIN available for user {user_id}, requesting PIN")
            context.user_data['pending_command'] = command_name
            await update.message.reply_text(verification_message)
            return
            
        return wrapper
    return decorator

# For direct use without message customization
pin_protected = require_pin() 