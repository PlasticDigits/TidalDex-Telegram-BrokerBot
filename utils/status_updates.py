"""
Status update utilities for long-running operations.
Provides decorators and helper functions for implementing status updates.
"""
import asyncio
import contextlib
import functools
import logging
from typing import Any, Callable, TypeVar, Optional, Union, cast, Coroutine, Awaitable

# Define type variables for generics
T = TypeVar('T')
StatusCallback = Callable[[str], Union[None, Awaitable[None]]]

logger = logging.getLogger(__name__)

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


class AnimatedStatusMessage:
    """
    Edit a single Telegram message every `interval_s` to show liveness, e.g.:

      🧠 Thinking.
      🧠 Thinking..
      🧠 Thinking...

    Call `set_stage()` as you move through steps (LLM, RPC, building tx, etc).
    The animation runs in a background task and can be stopped with `stop()`.
    
    Args:
        message_obj: The Telegram message object to update (must have edit_text method)
        header: Optional header text to display above the animated stage
        stage: Initial stage text to display
        interval_s: How often to update the message (in seconds)
        max_dots: Maximum number of dots to show (cycles: 0, 1, 2, ..., max_dots)
        
    Example:
        work_msg = await update.message.reply_text("🧠 Thinking...")
        ticker = AnimatedStatusMessage(work_msg, header="🧠 Working on it", stage="Thinking")
        await ticker.start()
        
        # Do work...
        ticker.set_stage("Checking blockchain")
        
        # When done:
        await ticker.stop(final_text="✅ Done!")
    """
    
    def __init__(
        self,
        message_obj: Any,
        *,
        header: Optional[str] = None,
        stage: str = "Working",
        interval_s: float = 1.0,
        max_dots: int = 3,
    ) -> None:
        self._message_obj = message_obj
        self._header = header
        self._stage = stage.strip() or "Working"
        self._interval_s = interval_s
        self._max_dots = max_dots
        
        self._task: Optional[asyncio.Task[None]] = None
        self._stop = asyncio.Event()
        self._lock = asyncio.Lock()
    
    def set_stage(self, stage: str) -> None:
        """Update the stage text (e.g., 'Thinking' -> 'Checking blockchain').
        
        Args:
            stage: New stage text to display
        """
        self._stage = stage.strip() or "Working"
    
    async def start(self) -> None:
        """Start the animation loop. Safe to call multiple times."""
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run())
    
    async def stop(self, *, final_text: Optional[str] = None) -> None:
        """Stop the animation and optionally set final message text.
        
        Args:
            final_text: Optional text to set as the final message content.
                       If None, the animation just stops without updating.
        """
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        
        if final_text is not None:
            await self._safe_edit(final_text)
    
    async def _run(self) -> None:
        """Internal animation loop that updates the message periodically."""
        tick = 0
        try:
            while not self._stop.is_set():
                dots = "." * (tick % (self._max_dots + 1))
                body = f"{self._stage}{dots}"
                text = f"{self._header}\n\n{body}" if self._header else body
                await self._safe_edit(text)
                tick += 1
                await asyncio.sleep(self._interval_s)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("AnimatedStatusMessage loop crashed")
    
    async def _safe_edit(self, text: str) -> None:
        """Safely edit the message, handling common Telegram errors gracefully."""
        async with self._lock:
            try:
                await self._message_obj.edit_text(text)
            except Exception as e:
                # Handle common Telegram API errors gracefully
                error_str = str(e)
                if "Message is not modified" in error_str:
                    # Message content hasn't changed - this is fine
                    return
                elif "message to edit not found" in error_str.lower():
                    # Message was deleted - stop animation
                    self._stop.set()
                    return
                elif "too many requests" in error_str.lower() or "retry after" in error_str.lower():
                    # Rate limited - skip this update, next tick will retry
                    return
                else:
                    # Log unexpected errors but don't crash
                    logger.warning(f"Unexpected error editing animated status message: {error_str}")
                    return