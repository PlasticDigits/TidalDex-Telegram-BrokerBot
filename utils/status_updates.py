"""
Status update utilities for long-running operations.
Provides decorators and helper functions for implementing status updates.
"""
import functools

def with_status_updates(operation_name=None):
    """
    Decorator for functions that provide status updates.
    
    This decorator makes it easier to implement status updates in any function.
    It wraps the function call with proper begin/end messages and error handling.
    
    Args:
        operation_name (str, optional): Name of the operation for logging
        
    Returns:
        function: Decorated function that handles status updates
        
    Example:
        @with_status_updates("Token Transfer")
        def transfer_tokens(from_addr, to_addr, amount, status_callback=None):
            # status_callback will be available even if caller didn't provide one
            status_callback("Preparing transaction...")
            # rest of function
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Extract callback if present
            callback = kwargs.get('status_callback')
            
            # If no callback, create a no-op function
            if callback is None:
                kwargs['status_callback'] = lambda msg: None
            
            # Log start of operation
            op_name = operation_name or func.__name__
            if callback:
                callback(f"Starting {op_name}...")
            
            # Call the original function
            try:
                result = func(*args, **kwargs)
                if callback:
                    callback(f"{op_name} completed successfully")
                return result
            except Exception as e:
                if callback:
                    callback(f"Error in {op_name}: {str(e)}")
                raise
                
        return wrapper
    return decorator

def create_status_callback(message_obj, update_method='edit_text', max_lines=15, header_lines=4):
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
        callable: A callback function that can be passed to operations
        
    Example:
        # In a Telegram bot handler:
        response = await update.message.reply_text("Starting operation...")
        status_cb = create_status_callback(response)
        result = some_long_operation(status_callback=status_cb)
    """
    async def callback(message):
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