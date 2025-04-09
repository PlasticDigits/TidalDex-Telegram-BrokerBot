"""
Status update utilities for long-running operations.
Provides decorators and helper functions for implementing status updates.
"""
import functools
from typing import Any, Callable, TypeVar, Optional, Union, cast, Coroutine, Awaitable

# Define type variables for generics
T = TypeVar('T')
StatusCallback = Callable[[str], Union[None, Awaitable[None]]]

def create_status_callback(
    message_obj: Any, 
    update_method: str = 'edit_text', 
    max_lines: int = 15, 
    header_lines: int = 4
) -> StatusCallback:
    """
    Create a status callback function for use with messaging platforms.
    
    This function creates a callback that can be passed to functions that accept
    status_callback parameters. It will update a message object (like a Telegram message)
    with new status information while keeping the message at a reasonable length.
    
    Args:
        message_obj: The message object to update (e.g., Telegram message)
        update_method (str): The method of message_obj to call for updates
        max_lines (int): Maximum number of lines to keep in the message
        header_lines (int): Number of header lines to always preserve
        
    Returns:
        StatusCallback: A callback function that can be passed to operations
        
    Example:
        # In a Telegram bot handler:
        response = await update.message.reply_text("Starting operation...")
        status_cb = create_status_callback(response)
        result = some_long_operation(status_callback=status_cb)
    """
    async def callback(message: str) -> None:
        current_text = getattr(message_obj, 'text', '')
        
        # Keep message at a reasonable length
        lines = current_text.split('\n')
        if len(lines) > max_lines:
            # Keep header lines and the most recent updates
            current_text = '\n'.join(
                lines[:header_lines] + 
                ["..."] + 
                lines[-(max_lines - header_lines - 1):]
            )
        
        # Call the update method on the message object
        update_func = getattr(message_obj, update_method)
        await update_func(f"{current_text}\n{message}")
        
    return callback 