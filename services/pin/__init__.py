"""
PIN management system for the TidalDex Telegram Bot.

This package contains all components for PIN verification, storage, and management.
"""
from typing import Callable, Any, TypeVar
from telegram import Update
from telegram.ext import ContextTypes

# Define the handler type for strong typing
HandlerType = TypeVar('HandlerType', bound=Callable[[Update, ContextTypes.DEFAULT_TYPE], Any])

# Export key components for easier imports
from services.pin.PINManager import pin_manager
from services.pin.pin_decorators import require_pin, pin_protected
from services.pin.message_handlers import handle_pin_input

__all__ = [
    'pin_manager',
    'require_pin',
    'pin_protected',
    'handle_pin_input'
] 