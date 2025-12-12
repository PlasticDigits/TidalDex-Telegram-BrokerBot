"""
PIN decorators for command handlers.

This module provides decorators that can be used to add PIN verification
to command handlers in a clean, declarative way.
"""
import logging
from functools import wraps
from typing import Callable, Any, Optional, TypeVar, cast
from telegram import Update, CallbackQuery
from telegram.ext import ContextTypes
from services.pin.PINManager import pin_manager
from db.utils import hash_user_id
from telegram.ext import ConversationHandler
logger = logging.getLogger(__name__)

# Define a type variable for the handler function
HandlerType = TypeVar('HandlerType', bound=Callable[[Update, ContextTypes.DEFAULT_TYPE], Any])

# Conversation states
PIN_REQUEST: int = 255+0
PIN_FAILED: int = 255+1

async def conversation_pin_helper(command_name: str, context: ContextTypes.DEFAULT_TYPE, update: Update, pin_message: str = "{command_name} requires your PIN for security. Please enter your PIN.") -> Optional[int]:
    """
    Helper function to verify the PIN and execute the pending command.
    """

    if pin_manager.needs_to_verify_pin(update.effective_user.id):
        # Set the pending command in context before requesting PIN
        if context.user_data is None:
            context.user_data = {}
        context.user_data['pending_command'] = command_name
        await update.message.reply_text(pin_message)
        return PIN_REQUEST
    return None

async def handle_conversation_pin_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Verify the pin and store it in the context.
    """
    if update.message is None:
        logger.error("Message is None in handle_conversation_pin_request")
        return PIN_FAILED
    
    user_id: int = update.effective_user.id
    input_text: str = update.message.text

    # First try to delete the PIN message for security
    try:
        await update.message.delete()
        logger.debug(f"Deleted PIN input message for security")
    except Exception as e:
        logger.warning(f"Could not delete PIN message: {e}")

    # Try to verify the PIN
    if not pin_manager.verify_pin(user_id, input_text):
        await update.message.reply_text("Invalid PIN. Please try again.")
        return PIN_FAILED
    
    # Store the PIN in context
    context.user_data['pin'] = input_text

    # Get the pending command from context
    pending_command = context.user_data.get('pending_command')
    if not pending_command:
        logger.error("No pending command found in context")
        await update.message.reply_text("Error: No command to execute. Please try your command again.")
        return ConversationHandler.END

    # Handle LLM app start continuation (when user started via inline keyboard callback)
    if pending_command == 'llm_app_start_from_callback':
        llm_app_name = context.user_data.get('pending_llm_app_name')
        if not llm_app_name:
            logger.error("No pending LLM app name found in context")
            await update.message.reply_text("Error: No LLM app to start. Please try again.")
            return ConversationHandler.END

        # Clear pending info before performing work (avoid duplicate execution on retries)
        del context.user_data['pending_llm_app_name']
        del context.user_data['pending_command']

        await update.message.reply_text("PIN verified. Starting the LLM app...")

        try:
            # Import lazily to avoid circular import at module load time.
            from app.base import llm_app_manager

            user_id_str = str(update.effective_user.id)
            session = await llm_app_manager.start_llm_app_session(user_id_str, llm_app_name)
            if not session:
                await update.message.reply_text(
                    f"❌ Failed to start {llm_app_name} LLM app. Please check your wallet and try again."
                )
                return ConversationHandler.END

            context.user_data['llm_app_session'] = session

            llm_app_config = llm_app_manager.get_llm_app_config(llm_app_name)
            description = ""
            if isinstance(llm_app_config, dict):
                description = str(llm_app_config.get("description", ""))
            
            # Import welcome message helper to avoid duplication
            from commands.llm_app import get_llm_app_welcome_message
            welcome_msg = get_llm_app_welcome_message(llm_app_name, description)

            await update.message.reply_text(welcome_msg, parse_mode='Markdown')
            # Import state constant lazily (keeps this module generic)
            from commands.llm_app import CONVERSING
            return CONVERSING
        except Exception as e:
            logger.error(f"Error starting LLM app after PIN verification: {e}")
            await update.message.reply_text("Error starting the LLM app. Please try again.")
            return ConversationHandler.END

    # Handle LLM app conversation continuation
    if pending_command == 'llm_app_conversation':
        # Get the stored user message
        pending_message = context.user_data.get('pending_llm_message')
        if not pending_message:
            logger.error("No pending LLM message found in context")
            await update.message.reply_text("Error: No message to process. Please try again.")
            return ConversationHandler.END
        
        # Clear the pending message
        del context.user_data['pending_llm_message']
        del context.user_data['pending_command']
        
        # Update the message to show the PIN was verified
        await update.message.reply_text("PIN verified. Processing your request...")
        
        # Import and call the internal processing function with the stored message.
        # NOTE: Do not mutate `update.message.text` here. PTB Message fields may be
        # immutable / not intended for mutation, and `_process_llm_message` takes
        # the user message as an explicit argument anyway.
        try:
            from commands.llm_app import _process_llm_message
            return await _process_llm_message(update, context, pending_message)
        except Exception as e:
            logger.error(f"Error processing LLM app conversation after PIN verification: {e}")
            await update.message.reply_text("Error processing your request. Please try again.")
            return ConversationHandler.END
    
    # Update the message to show the PIN was verified
    await update.message.reply_text("PIN verified. Continuing with your command...")
    
    # Execute the pending command
    try:
        # Import the command module dynamically
        # Remove '_command' suffix if present
        module_name = pending_command.replace('_command', '')
        command_module = __import__(f"commands.{module_name}", fromlist=[module_name])
        # Use the original pending_command name to get the function
        command_func = getattr(command_module, pending_command)
        
        # Execute the command
        return await command_func(update, context)
    except Exception as e:
        logger.error(f"Error executing pending command {pending_command}: {e}")
        await update.message.reply_text("Error executing command. Please try again.")
        return ConversationHandler.END

# Do NOT use this for conversation handlers. Use handle_conversation_pin_request instead.     
def require_pin(verification_message: str = "This command requires your PIN for security. Please enter your PIN.") -> Callable[[HandlerType], HandlerType]:
    """
    Decorator that adds PIN verification to a CommandHandler.
    
    If the user has a PIN set, this decorator will:
    1. Check if a verified PIN is already available
    2. If not, request a PIN from the user
    3. Once verified, the PIN will be available in context.user_data['pin']
    
    Args:
        verification_message: The message to show when requesting a PIN
        
    Returns:
        Decorator function
    """
    def decorator(handler_func: HandlerType) -> HandlerType:
        @wraps(handler_func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
            logger.info(f"Wrapper called for {handler_func.__name__}")
            if not update.effective_user:
                return None
                
            user_id: int = update.effective_user.id
            command_name: str = handler_func.__name__

            logger.info(f"Checking PIN for user {hash_user_id(user_id)} for command {command_name}")
            
            # Check if user needs PIN verification
            if not pin_manager.needs_pin(user_id):
                logger.info(f"No PIN required for user {hash_user_id(user_id)}, executing {command_name} directly")
                return await handler_func(update, context)
            
            # Check if we already have a verified PIN
            pin: Optional[str] = pin_manager.get_pin(user_id)
            
            if pin:
                # PIN is already verified, store it in context for the handler
                logger.info(f"Using verified PIN for {command_name} for user {hash_user_id(user_id)}")
                if context.user_data is not None:
                    context.user_data['pin'] = pin
                return await handler_func(update, context)
            
            # No verified PIN available, request one
            if not update.message:
                return None
                
            logger.info(f"No verified PIN available for user {hash_user_id(user_id)}, requesting PIN")
            if context.user_data is not None:
                context.user_data['pending_command'] = command_name
            await update.message.reply_text(verification_message)
            return None
            
        return cast(HandlerType, wrapper)
    return decorator

# For direct use without message customization
pin_protected: Callable[[HandlerType], HandlerType] = require_pin() 