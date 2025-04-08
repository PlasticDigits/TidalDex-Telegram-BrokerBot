from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import ContextTypes, ConversationHandler
from typing import Dict, List, Any, Optional, Union, cast, Callable, Coroutine, Awaitable
from services.wallet import wallet_manager
from wallet.utils import validate_address
from utils.status_updates import create_status_callback
from utils.gas_estimation import estimate_bnb_transfer_gas, estimate_token_transfer_gas
from services.pin import require_pin, pin_manager
import logging
from db.wallet import WalletData
from web3 import Web3 as w3
from decimal import Decimal
from utils.config import BSC_SCANNER_URL, get_env_var
from wallet.send import send_token, send_bnb
import json
import os
from web3.types import ChecksumAddress
from services.swap import swap_manager
from services import token_manager
import traceback

# Enable logging
logger = logging.getLogger(__name__)

# Conversation states
CHOOSING_FROM_TOKEN, CHOOSING_TO_TOKEN, ENTERING_AMOUNT, ENTERING_SLIPPAGE, CONFIRMING_SWAP = range(5)

# Constants for input validation
MAX_ADDRESS_LENGTH: int = 100  # Ethereum addresses are 42 chars with 0x prefix
MAX_AMOUNT_LENGTH: int = 30    # Financial amounts shouldn't need more than this
MAX_SYMBOL_LENGTH: int = 20    # Token symbols are typically short

# Default slippage in basis points (1% = 100)
DEFAULT_SLIPPAGE_BPS: int = 100

# Helper function to ensure status_callback always returns a proper awaitable
async def ensure_awaitable(callback_result: Optional[Awaitable[None]]) -> None:
    """Ensure callback result is properly awaited if it's not None."""
    if callback_result is not None:
        await callback_result

# Create a properly typed wrapper for callbacks that works with external functions
def create_callback_wrapper(status_callback: Callable[[str], Awaitable[None] | None]) -> Callable[[str], Awaitable[None]]:
    """Create a properly typed callback wrapper that always returns an Awaitable[None]."""
    async def wrapper(message: str) -> None:
        result = status_callback(message)
        if result is not None:
            await result
    return wrapper

async def swap_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the swap process."""
        
    if update.effective_user is None:
        logger.error("Effective user is None in swap_command")
        return ConversationHandler.END
    
    if update.message is None:
        logger.error("Message is None in swap_command")
        return ConversationHandler.END
    
    # Get the user ID as an integer (native type from Telegram)
    user_id_int: int = update.effective_user.id
    # For wallet manager, we need the user ID as a string
    user_id_str: str = str(user_id_int)
    
    # Get active wallet name and use pin_manager for PIN
    wallet_name: Optional[str] = wallet_manager.get_active_wallet_name(user_id_str)
    pin: Optional[str] = pin_manager.get_pin(user_id_int)
    user_wallet: Optional[WalletData] = wallet_manager.get_user_wallet(user_id_str, wallet_name, pin)
    
    if not user_wallet:
        await update.message.reply_text("You don't have a wallet yet. Use /wallet to create one.")
        return ConversationHandler.END
    
    # Ensure context.user_data exists and is a dictionary
    if context.user_data is None:
        context.user_data = {}
    
    # Get tracked tokens for the user
    tracked_tokens = await token_manager.get_tracked_tokens(user_id_str)
    
    if not tracked_tokens:
        await update.message.reply_text(
            "You don't have any tracked tokens yet. Use /track to add tokens to your wallet."
        )
        return ConversationHandler.END
    
    # Create keyboard with tracked tokens
    keyboard: List[List[InlineKeyboardButton]] = []
    row: List[InlineKeyboardButton] = []
    
    # Add BNB as first option
    keyboard.append([InlineKeyboardButton("BNB", callback_data='swap_from_bnb')])
    
    # Add tracked tokens
    for token in tracked_tokens:
        button = InlineKeyboardButton(
            f"{token['symbol']} ({token['name']})",
            callback_data=f"swap_from_{token['token_address']}"
        )
        row.append(button)
        if len(row) == 2:  # 2 buttons per row
            keyboard.append(row)
            row = []
    
    # Add any remaining buttons
    if row:
        keyboard.append(row)
    
    # Add cancel button
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data='swap_cancel')])
    
    await update.message.reply_text(
        f"🔍 Active Wallet: {wallet_name}\n\n"
        "💱 What would you like to swap from?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return CHOOSING_FROM_TOKEN

async def choose_from_token(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the selection of token to swap from."""
    if update.callback_query is None:
        logger.error("Callback query is None in choose_from_token")
        return ConversationHandler.END
        
    query: CallbackQuery = update.callback_query
    await query.answer()
    
    # Ensure context.user_data exists and is a dictionary
    if context.user_data is None:
        context.user_data = {}
    
    if query.data is None:
        logger.error("Query data is None in choose_from_token")
        return ConversationHandler.END
        
    choice: str = query.data
    
    if choice == 'swap_cancel':
        await query.edit_message_text("Swap cancelled.")
        return ConversationHandler.END
    
    # Store the selected token in context
    if choice == 'swap_from_bnb':
        context.user_data['from_token'] = {
            'address': 'BNB',
            'symbol': 'BNB',
            'name': 'BNB',
            'decimals': 18
        }
    else:
        # Extract token address from callback data
        token_address = choice.replace('swap_from_', '')
        
        # Get token details from TokenManager
        token_info = await token_manager.get_token_info(token_address)
        
        if not token_info:
            await query.edit_message_text("Error: Could not get token information. Please try again.")
            return ConversationHandler.END
            
        context.user_data['from_token'] = {
            'address': token_info['token_address'],
            'symbol': token_info['symbol'],
            'name': token_info['name'],
            'decimals': token_info['decimals']
        }
    
    # Get default token list for destination tokens
    await token_manager._parse_default_token_list()
    
    # Create keyboard with default tokens
    keyboard: List[List[InlineKeyboardButton]] = []
    row: List[InlineKeyboardButton] = []
    
    # Add BNB as first option
    keyboard.append([InlineKeyboardButton("BNB", callback_data='swap_to_bnb')])
    
    # Add default tokens
    for token_address, token_details in token_manager.default_tokens.items():
        button = InlineKeyboardButton(
            f"{token_details['symbol']} ({token_details['name']})",
            callback_data=f"swap_to_{token_address}"
        )
        row.append(button)
        if len(row) == 2:  # 2 buttons per row
            keyboard.append(row)
            row = []
    
    # Add any remaining buttons
    if row:
        keyboard.append(row)
    
    # Add custom address option
    keyboard.append([InlineKeyboardButton("Enter Custom Address", callback_data='swap_to_custom')])
    
    # Add cancel button
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data='swap_cancel')])
    
    await query.edit_message_text(
        f"Selected: {context.user_data['from_token']['symbol']}\n\n"
        "What would you like to swap to?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return CHOOSING_TO_TOKEN 

async def choose_to_token(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle the selection of token to swap to."""
    if update.callback_query is None:
        logger.error("Callback query is None in choose_to_token")
        return ConversationHandler.END
        
    query: CallbackQuery = update.callback_query
    await query.answer()
    
    # Ensure context.user_data exists and is a dictionary
    if context.user_data is None:
        context.user_data = {}
    
    if query.data is None:
        logger.error("Query data is None in choose_to_token")
        return ConversationHandler.END
        
    choice: str = query.data
    
    if choice == 'swap_cancel':
        await query.edit_message_text("Swap cancelled.")
        return ConversationHandler.END
    
    if choice == 'swap_to_custom':
        await query.edit_message_text(
            "Please enter the token address you want to swap to:"
        )
        return CHOOSING_TO_TOKEN
    
    # Store the selected token in context
    if choice == 'swap_to_bnb':
        context.user_data['to_token'] = {
            'address': 'BNB',
            'symbol': 'BNB',
            'name': 'BNB',
            'decimals': 18
        }
    else:
        # Extract token address from callback data
        token_address = choice.replace('swap_to_', '')
        
        # Get token details from TokenManager
        token_info = await token_manager.get_token_info(token_address)
        
        if not token_info:
            await query.edit_message_text("Error: Could not get token information. Please try again.")
            return ConversationHandler.END
            
        context.user_data['to_token'] = {
            'address': token_info['token_address'],
            'symbol': token_info['symbol'],
            'name': token_info['name'],
            'decimals': token_info['decimals']
        }
    
    await query.edit_message_text(
        f"Selected: {context.user_data['from_token']['symbol']} → {context.user_data['to_token']['symbol']}\n\n"
        "Please enter the amount you want to swap:"
    )
    
    return ENTERING_AMOUNT

async def handle_custom_token_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle custom token address input."""
    if update.message is None:
        logger.error("Message is None in handle_custom_token_address")
        return ConversationHandler.END
    
    token_address = update.message.text.strip()
    
    # Validate address
    if not w3.is_address(token_address):
        await update.message.reply_text(
            "Invalid token address. Please enter a valid BSC token address:"
        )
        return CHOOSING_TO_TOKEN
    
    # Get token details
    token_info = await token_manager.get_token_info(token_address)
    
    if not token_info:
        await update.message.reply_text(
            "Could not get token information. Please enter a valid BSC token address:"
        )
        return CHOOSING_TO_TOKEN
    
    # Store token info in context
    if context.user_data is None:
        context.user_data = {}
        
    context.user_data['to_token'] = {
        'address': token_info['token_address'],
        'symbol': token_info['symbol'],
        'name': token_info['name'],
        'decimals': token_info['decimals']
    }
    
    await update.message.reply_text(
        f"Selected: {context.user_data['from_token']['symbol']} → {context.user_data['to_token']['symbol']}\n\n"
        "Please enter the amount you want to swap:"
    )
    
    return ENTERING_AMOUNT

async def enter_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle amount input for the swap."""
    if update.message is None:
        logger.error("Message is None in enter_amount")
        return ConversationHandler.END
    
    if context.user_data is None:
        logger.error("User data is None in enter_amount")
        return ConversationHandler.END
    
    amount_str = update.message.text.strip()
    
    try:
        # Convert amount to float and validate
        amount = float(amount_str)
        if amount <= 0:
            raise ValueError("Amount must be positive")
            
        # Store amount in context
        context.user_data['amount'] = amount
        
        # Get user's wallet
        user_id_int = update.effective_user.id
        user_id_str = str(user_id_int)
        wallet_name = wallet_manager.get_active_wallet_name(user_id_str)
        pin = pin_manager.get_pin(user_id_int)
        user_wallet = wallet_manager.get_user_wallet(user_id_str, wallet_name, pin)
        
        if not user_wallet:
            await update.message.reply_text("Error: Could not get wallet information.")
            return ConversationHandler.END
        
        # Ensure user_wallet is a dictionary with the required fields
        if not isinstance(user_wallet, dict) or 'address' not in user_wallet:
            logger.error(f"Invalid wallet data format: {user_wallet}")
            await update.message.reply_text("Error: Invalid wallet data format.")
            return ConversationHandler.END
        
        # Check if user has enough balance
        from_token = context.user_data['from_token']
        if from_token['address'] == 'BNB':
            balance = w3.eth.get_balance(user_wallet['address'])
            if balance < w3.to_wei(amount, 'ether'):
                await update.message.reply_text(
                    f"Error: Insufficient BNB balance. You have {w3.from_wei(balance, 'ether')} BNB."
                )
                return ConversationHandler.END
        else:
            balance = await token_manager.get_token_balance(
                from_token['address'],
                user_wallet['address']
            )
            if balance < amount * (10 ** from_token['decimals']):
                await update.message.reply_text(
                    f"Error: Insufficient {from_token['symbol']} balance. "
                    f"You have {balance / (10 ** from_token['decimals'])} {from_token['symbol']}."
                )
                return ConversationHandler.END
        
        # Ask for slippage
        await update.message.reply_text(
            f"Selected: {context.user_data['from_token']['symbol']} → {context.user_data['to_token']['symbol']}\n"
            f"Amount: {amount} {context.user_data['from_token']['symbol']}\n\n"
            f"Please enter the slippage percentage (default: {DEFAULT_SLIPPAGE_BPS/100}%):"
        )
        
        return ENTERING_SLIPPAGE
        
    except ValueError as e:
        await update.message.reply_text(f"Error: {str(e)}")
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error in enter_amount: {e}")
        logger.error(traceback.format_exc())
        await update.message.reply_text("An error occurred while processing your request.")
        return ConversationHandler.END

async def enter_slippage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle slippage input for the swap."""
    if update.message is None:
        logger.error("Message is None in enter_slippage")
        return ConversationHandler.END
    
    if context.user_data is None:
        logger.error("User data is None in enter_slippage")
        return ConversationHandler.END
    
    slippage_str = update.message.text.strip()
    
    try:
        # Parse slippage
        if not slippage_str:
            slippage_bps = DEFAULT_SLIPPAGE_BPS
        else:
            slippage = float(slippage_str)
            if slippage <= 0 or slippage > 100:
                raise ValueError("Slippage must be between 0 and 100")
            slippage_bps = int(slippage * 100)  # Convert to basis points
        
        # Store slippage in context
        context.user_data['slippage_bps'] = slippage_bps
        
        # Get user's wallet
        user_id_int = update.effective_user.id
        user_id_str = str(user_id_int)
        wallet_name = wallet_manager.get_active_wallet_name(user_id_str)
        pin = pin_manager.get_pin(user_id_int)
        user_wallet = wallet_manager.get_user_wallet(user_id_str, wallet_name, pin)
        
        if not user_wallet:
            await update.message.reply_text("Error: Could not get wallet information.")
            return ConversationHandler.END
        
        # Get swap quote
        from_token = context.user_data['from_token']
        to_token = context.user_data['to_token']
        amount = context.user_data['amount']
        
        # Use the swap_manager singleton
        quote = await swap_manager.get_swap_quote(
            from_token['address'],
            to_token['address'],
            amount * (10 ** from_token['decimals']),
            slippage_bps
        )
        
        if not quote:
            await update.message.reply_text("Error: Could not get swap quote. Please try again.")
            return ConversationHandler.END
        
        # Store quote in context
        context.user_data['quote'] = quote
        
        # Show swap preview
        await update.message.reply_text(
            f"Swap Preview:\n\n"
            f"From: {amount} {from_token['symbol']}\n"
            f"To: {quote['amount_out'] / (10 ** to_token['decimals'])} {to_token['symbol']}\n"
            f"Slippage: {slippage_bps/100}%\n"
            f"Price Impact: {quote['price_impact']}%\n\n"
            f"Do you want to proceed with the swap?",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Yes", callback_data="swap_confirm"),
                    InlineKeyboardButton("❌ No", callback_data="swap_cancel")
                ]
            ])
        )
        
        return CONFIRMING_SWAP
        
    except ValueError as e:
        await update.message.reply_text(
            f"Invalid slippage: {str(e)}\n\n"
            f"Please enter a valid slippage percentage (default: {DEFAULT_SLIPPAGE_BPS/100}%):"
        )
        return ENTERING_SLIPPAGE

async def confirm_swap(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle swap confirmation."""
    if update.callback_query is None:
        logger.error("Callback query is None in confirm_swap")
        return ConversationHandler.END
        
    query: CallbackQuery = update.callback_query
    await query.answer()
    
    if context.user_data is None:
        logger.error("User data is None in confirm_swap")
        return ConversationHandler.END
    
    if query.data is None:
        logger.error("Query data is None in confirm_swap")
        return ConversationHandler.END
        
    choice: str = query.data
    
    if choice == 'swap_cancel':
        await query.edit_message_text("Swap cancelled.")
        return ConversationHandler.END
    
    # Get user's wallet
    user_id_int = update.effective_user.id
    user_id_str = str(user_id_int)
    wallet_name = wallet_manager.get_active_wallet_name(user_id_str)
    pin = pin_manager.get_pin(user_id_int)
    user_wallet = wallet_manager.get_user_wallet(user_id_str, wallet_name, pin)
    
    if not user_wallet:
        await query.edit_message_text("Error: Could not get wallet information.")
        return ConversationHandler.END
    
    # Execute swap
    from_token = context.user_data['from_token']
    to_token = context.user_data['to_token']
    amount = context.user_data['amount']
    slippage_bps = context.user_data['slippage_bps']
    quote = context.user_data['quote']
    
    await query.edit_message_text("Executing swap...")
    
    # Use the swap_manager singleton
    tx_hash = await swap_manager.execute_swap(
        user_wallet,
        from_token['address'],
        to_token['address'],
        amount * (10 ** from_token['decimals']),
        slippage_bps,
        quote
    )
    
    if not tx_hash:
        await query.edit_message_text("Error: Swap failed. Please try again.")
        return ConversationHandler.END
    
    # Show transaction details
    await query.edit_message_text(
        f"Swap executed successfully!\n\n"
        f"Transaction: {BSC_SCANNER_URL}/tx/{tx_hash}\n"
        f"From: {amount} {from_token['symbol']}\n"
        f"To: {quote['amount_out'] / (10 ** to_token['decimals'])} {to_token['symbol']}\n"
        f"Slippage: {slippage_bps/100}%\n"
        f"Price Impact: {quote['price_impact']}%"
    )
    
    return ConversationHandler.END 

# Create PIN-protected version of the swap command
pin_protected_swap: Callable[[Update, ContextTypes.DEFAULT_TYPE], Coroutine[Any, Any, int]] = require_pin(
    "🔒 Swapping tokens requires PIN verification.\nPlease enter your PIN:"
)(swap_command)