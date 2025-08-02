from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import ContextTypes, ConversationHandler
from typing import Dict, List, Any, Optional, Union, cast, Callable, Coroutine, Awaitable
from services.wallet import wallet_manager
from utils import token
from wallet.utils import validate_address
from utils.status_updates import create_status_callback
from utils.gas_estimation import estimate_bnb_transfer_gas, estimate_token_transfer_gas, estimate_max_bnb_transfer
from services.pin import require_pin, pin_manager
import logging
from db.wallet import WalletData
from utils.web3_connection import w3
from decimal import Decimal
from utils.config import BSC_SCANNER_URL
from wallet.send import send_token, send_bnb
from services.pin.pin_decorators import conversation_pin_helper
from utils.number_display import number_display_with_sigfig
from db.utils import hash_user_id

# Import OFAC compliance manager
try:
    from services.compliance import ofac_manager
    OFAC_AVAILABLE = True
except ImportError:
    OFAC_AVAILABLE = False
    ofac_manager = None

# Enable logging
logger = logging.getLogger(__name__)

# Conversation states
CHOOSING_ACTION, SEND_BNB_AMOUNT, SEND_BNB_ADDRESS, SEND_TOKEN_SYMBOL, SEND_TOKEN_AMOUNT, SEND_TOKEN_ADDRESS = range(6)

# Constants for input validation
MAX_ADDRESS_LENGTH: int = 100  # Ethereum addresses are 42 chars with 0x prefix
MAX_AMOUNT_LENGTH: int = 30    # Financial amounts shouldn't need more than this
MAX_SYMBOL_LENGTH: int = 20    # Token symbols are typically short

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

async def send_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the send process."""
        
    if update.effective_user is None:
        logger.error("Effective user is None in send_command")
        return ConversationHandler.END
    
    if update.message is None:
        logger.error("Message is None in send_command")
        return ConversationHandler.END
    
    # Get the user ID as an integer (native type from Telegram)
    user_id_int: int = update.effective_user.id
    # For wallet manager, we need the user ID as a string
    user_id_str: str = str(user_id_int)
    
    helper_result: Optional[int] = await conversation_pin_helper('send_command', context, update, "Sending funds requires your PIN for security. Please enter your PIN.")
    if helper_result is not None:
        return helper_result
    
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
    
    # Check if the command includes "all" parameter
    if context.args and context.args[0].lower() == "all":
        context.user_data['send_all'] = True
        await update.message.reply_text(
            "You've chosen to send your entire balance.\n"
            "What would you like to send?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Send All BNB", callback_data='send_bnb_all')],
                [InlineKeyboardButton("Send All Token", callback_data='send_token_all')],
                [InlineKeyboardButton("❌ Cancel", callback_data='send_cancel')]
            ])
        )
    else:
        context.user_data['send_all'] = False
        keyboard: List[List[InlineKeyboardButton]] = [
            [InlineKeyboardButton("Send BNB", callback_data='send_bnb')],
            [InlineKeyboardButton("Send Token", callback_data='send_token')],
            [InlineKeyboardButton("❌ Cancel", callback_data='send_cancel')]
        ]
        await update.message.reply_text(
            f"🔍 Active Wallet: {wallet_name}\n\n"
            "💸 What would you like to send?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    return CHOOSING_ACTION

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle button callbacks for the send process."""
    if update.callback_query is None:
        logger.error("Callback query is None in button_callback")
        return ConversationHandler.END
        
    query: CallbackQuery = update.callback_query
    await query.answer()
    
    # Ensure context.user_data exists and is a dictionary
    if context.user_data is None:
        context.user_data = {}
    
    if query.data is None:
        logger.error("Query data is None in button_callback")
        return ConversationHandler.END
        
    choice: str = query.data
    
    if choice == 'send_cancel':
        await query.edit_message_text("Transaction cancelled.")
        return ConversationHandler.END
    
    if choice == 'send_bnb':
        await query.edit_message_text(
            "💰 Please enter the amount of BNB to send:\n\n"
            "You can type 'all' to send your entire balance.\n\n"
            "Type /cancel to cancel the transaction."
        )
        return SEND_BNB_AMOUNT
    
    if choice == 'send_bnb_all':
        context.user_data['send_all_bnb'] = True
        await query.edit_message_text(
            "You've chosen to send all your BNB. Please enter the recipient address:\n\n"
            "Type /cancel to cancel the transaction."
        )
        return SEND_BNB_ADDRESS
    
    if choice == 'send_token':
        await query.edit_message_text(
            "🪙 Please enter the token symbol (e.g., BUSD, CAKE):\n\n"
            "Type /cancel to cancel the transaction."
        )
        return SEND_TOKEN_SYMBOL
    
    if choice == 'send_token_all':
        context.user_data['send_all_token'] = True
        await query.edit_message_text(
            "You've chosen to send all of a token. Please enter the token symbol (e.g., BUSD, CAKE):\n\n"
            "Type /cancel to cancel the transaction."
        )
        return SEND_TOKEN_SYMBOL
    
    return ConversationHandler.END

async def send_bnb_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process BNB amount and ask for recipient address."""
    # Ensure context.user_data exists and is a dictionary
    if context.user_data is None:
        context.user_data = {}
    
    if update.message is None:
        logger.error("Message is None in send_bnb_amount")
        return ConversationHandler.END
    
    if update.message.text is None:
        logger.error("Message text is None in send_bnb_amount")
        return ConversationHandler.END
        
    input_text: str = update.message.text.strip()
    
    # Input size limiting
    if len(input_text) > MAX_AMOUNT_LENGTH:
        await update.message.reply_text(
            f"❌ Input too long. Please enter an amount with fewer than {MAX_AMOUNT_LENGTH} characters.\n\n"
            "Type /cancel to cancel the transaction."
        )
        return SEND_BNB_AMOUNT
    
    # Check if user wants to cancel
    if input_text.lower() == "/cancel":
        await update.message.reply_text("Transaction cancelled.")
        return ConversationHandler.END
    
    # Check if user wants to send all
    if input_text.lower() == "all":
        context.user_data['send_all_bnb'] = True
        await update.message.reply_text(
            "You've chosen to send all your BNB. Please enter the recipient address:\n\n"
            "Type /cancel to cancel the transaction."
        )
        return SEND_BNB_ADDRESS
    
    try:
        amount: float = float(input_text)
        if amount <= 0:
            await update.message.reply_text(
                "Amount must be greater than 0. Please try again:\n\n"
                "Type /cancel to cancel the transaction."
            )
            return SEND_BNB_AMOUNT
        
        context.user_data['send_amount'] = amount
        await update.message.reply_text(
            "Please enter the recipient address:\n\n"
            "Type /cancel to cancel the transaction."
        )
        return SEND_BNB_ADDRESS
    except ValueError:
        await update.message.reply_text(
            "Invalid amount. Please enter a number or type 'all' to send your entire balance:\n\n"
            "Type /cancel to cancel the transaction."
        )
        return SEND_BNB_AMOUNT

async def send_bnb_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process recipient address and send BNB with status updates."""
    if update.message is None:
        logger.error("Message is None in send_bnb_address")
        return ConversationHandler.END
    
    if update.message.text is None:
        logger.error("Message text is None in send_bnb_address")
        return ConversationHandler.END
    
    if update.effective_user is None:
        logger.error("Effective user is None in send_bnb_address")
        return ConversationHandler.END
    
    if context.user_data is None:
        context.user_data = {}
        
    recipient_address: str = update.message.text.strip()
    
    # Input size limiting
    if len(recipient_address) > MAX_ADDRESS_LENGTH:
        await update.message.reply_text(
            f"❌ Address too long. Please enter an address with fewer than {MAX_ADDRESS_LENGTH} characters.\n\n"
            "Type /cancel to cancel the transaction."
        )
        return SEND_BNB_ADDRESS
    
    # Check if user wants to cancel
    if recipient_address.lower() == "/cancel":
        await update.message.reply_text("Transaction cancelled.")
        return ConversationHandler.END
    
    # Handle sending entire balance case differently
    send_all: bool = context.user_data.get('send_all_bnb', False)

    amount: Optional[Decimal] = None
    
    if not send_all:
        amount = context.user_data.get('send_amount')
        if not amount:
            await update.message.reply_text("Something went wrong. Please start over with /send")
            return ConversationHandler.END
    
    user_id_int: int = update.effective_user.id
    user_id_str: str = str(user_id_int)
    
    # Get PIN from pin_manager instead of context
    pin: Optional[str] = pin_manager.get_pin(user_id_int)
    
    # Get active wallet name
    wallet_name: Optional[str] = wallet_manager.get_active_wallet_name(user_id_str)
    
    # Get user wallet with PIN if required
    user_wallet: Optional[WalletData] = wallet_manager.get_user_wallet(user_id_str, wallet_name, pin)
    
    if not user_wallet:
        await update.message.reply_text("You don't have a wallet yet. Use /wallet to create one.")
        return ConversationHandler.END
    
    # Check if we have a valid private key
    if not user_wallet.get('private_key') or user_wallet.get('decryption_failed', False):
        error_message: str = "Cannot send transaction: Unable to access wallet private key."
        await update.message.reply_text(f"❌ {error_message}")
        return ConversationHandler.END
    
    # Initial response with loading indicator
    amount_text = "Sending entire BNB balance" if send_all else f"Amount: {context.user_data.get('send_amount')} BNB"
    response_text = (
        f"🔄 Processing your transaction...\n"
        f"{amount_text}\n"
        f"To: {recipient_address}\n\n"
        f"Please wait while the transaction is being processed... ⏳"
    )
    
    response = await update.message.reply_text(response_text)
    
    # Create a status callback using the utility function
    status_callback = create_status_callback(response, max_lines=15, header_lines=4)
    
    try:
        # Validate recipient address
        try:
            valid_recipient = validate_address(recipient_address)
            await ensure_awaitable(status_callback("✓ Recipient address validated"))
        except ValueError as e:
            logger.error(f"Invalid recipient address: {e}")
            await response.edit_text(f"❌ Invalid recipient address: {str(e)}")
            return ConversationHandler.END
        
        # Get wallet information
        user_address = user_wallet.get('address', '')
        private_key = user_wallet.get('private_key', '')
        
        # Check BNB balance
        await ensure_awaitable(status_callback("Checking your BNB balance..."))
        bnb_balance_response = await wallet_manager.get_bnb_balance(user_address)
        bnb_balance = float(bnb_balance_response.get('balance', 0))
        
        if send_all:
            # If sending all, use utility function to calculate max amount
            try:
                # Create a properly typed callback
                callback_wrapper = create_callback_wrapper(status_callback)
                
                max_amount_info = await estimate_max_bnb_transfer(
                    user_address,
                    valid_recipient,
                    bnb_balance,
                    callback_wrapper
                )
                # Ensure we have a Decimal type for amount
                amount_max = Decimal(max_amount_info['max_amount'] if isinstance(max_amount_info, dict) else max_amount_info)
                # Fix: Convert Decimal to string before passing to status_callback
                amount_str = str(amount_max)
                await ensure_awaitable(status_callback(f"Sending {amount_str} BNB (entire balance minus gas)"))
            except ValueError as e:
                await ensure_awaitable(status_callback(f"❌ Insufficient balance for gas fees."))
                await response.edit_text(
                    f"❌ Transaction failed: {str(e)}\n\n"
                    f"Your balance is too low to send BNB after accounting for gas fees."
                )
                return ConversationHandler.END
        else:
            # Regular case (not sending all)
            send_amount = context.user_data.get('send_amount')
            if send_amount is None:
                await response.edit_text("❌ Transaction failed: Amount not specified.")
                return ConversationHandler.END
            
            try:
                # Convert to Decimal for precision
                amount = Decimal(str(send_amount))
                
                # Get gas cost estimate for basic transfer
                try:
                    # Create a properly typed callback wrapper
                    callback_wrapper = create_callback_wrapper(status_callback)
                    
                    # Use the actual amount for gas calculation
                    gas_info = await estimate_bnb_transfer_gas(
                        user_address, 
                        valid_recipient, 
                        amount,  # Actual amount
                        callback_wrapper
                    )
                    
                    gas_cost_bnb = gas_info.get('gas_bnb', 0)
                except Exception as e:
                    logger.error(f"Error estimating gas: {e}")
                    # Define required_amount before using it in error message
                    required_amount = amount + Decimal(str(gas_cost_bnb)) if 'gas_cost_bnb' in locals() else Decimal('0')
                    await response.edit_text(
                        f"❌ Transaction failed: Error estimating gas.\n"
                        f"Your balance: {bnb_balance} BNB\n"
                        f"Amount: {amount} BNB\n"
                        f"Gas cost: {gas_cost_bnb if 'gas_cost_bnb' in locals() else 'unknown'} BNB\n"
                        f"Required: {required_amount} BNB (amount + gas)\n\n"
                        f"{str(e)}"
                    )
                    return ConversationHandler.END
                
                required_amount = amount + Decimal(str(gas_cost_bnb))
                
                # Check if user has sufficient balance
                if bnb_balance < required_amount:
                    await ensure_awaitable(status_callback(f"❌ Insufficient balance. You have {bnb_balance} BNB but need {required_amount} BNB (including gas)."))
                    await response.edit_text(
                        f"❌ Transaction failed: Insufficient balance.\n\n"
                        f"Your balance: {bnb_balance} BNB\n"
                        f"Required: {required_amount} BNB (amount + gas)\n\n"
                        f"Please add funds to your wallet and try again."
                    )
                    return ConversationHandler.END
                
                await ensure_awaitable(status_callback(f"✓ Balance sufficient: {bnb_balance} BNB"))
            except Exception as e:
                logger.error(f"Error checking balance: {e}")
                await response.edit_text(f"❌ Transaction failed: Error checking balance.\n{str(e)}")
                return ConversationHandler.END
        
        # Ensure we have a private key
        private_key = user_wallet.get('private_key')
        if not private_key:
            await response.edit_text("❌ Transaction failed: Unable to access wallet private key.")
            return ConversationHandler.END
        
        # Calculate amount in wei
        if send_all:
            # Use the max amount from earlier calculation if defined, otherwise provide a default
            amount_wei = int(w3.to_wei(amount_max, 'ether')) if 'amount_max' in locals() else 0
        else:
            # Convert regular amount to wei, with None check
            amount_to_convert = amount if amount is not None else Decimal('0')
            amount_wei = int(w3.to_wei(amount_to_convert, 'ether'))
        
        # OFAC Compliance Check
        if OFAC_AVAILABLE and ofac_manager:
            try:
                compliance_result = await ofac_manager.check_transaction_compliance(
                    from_address=user_wallet['address'],
                    to_address=valid_recipient,
                    user_id=str(user_id_int)
                )
                
                if not compliance_result['is_compliant']:
                    await response.edit_text(
                        f"❌ Transaction blocked for compliance reasons:\n"
                        f"{compliance_result['blocked_reason']}\n\n"
                        f"This transaction has been logged and will be reported to the authorities."
                    )
                    return ConversationHandler.END
                    
            except Exception as e:
                logger.error(f"Compliance check failed for BNB transaction: {str(e)} - BLOCKING transaction for safety")
                await response.edit_text(
                    f"❌ Transaction blocked: Compliance check failed.\n\n"
                    f"Unable to verify transaction compliance. Transaction has been blocked for security reasons.\n"
                    f"Please try again later or contact support if this issue persists."
                )
                return ConversationHandler.END
        
        # Create a properly typed asynchronous callback wrapper
        callback_wrapper = create_callback_wrapper(status_callback)
        
        # Send BNB with status updates
        tx_result = await send_bnb(
            private_key, 
            valid_recipient, 
            amount_wei,  
            status_callback=callback_wrapper
        )
        
        # Final success message
        await response.edit_text(
            f"✅ Transaction successful!\n\n"
            f"Amount: {amount} BNB{' (entire balance minus gas)' if send_all else ''}\n"
            f"Recipient: {valid_recipient}\n"
            f"TX Hash: `{tx_result['tx_hash']}`\n"
            f"[View on Scanner]({BSC_SCANNER_URL}/tx/0x{tx_result['tx_hash']})\n"
            f"Block: {tx_result['block_number']}",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error sending BNB: {e}")
        await response.edit_text(
            f"❌ Transaction failed: {str(e)}\n\n"
            "Please check your balance and try again."
        )
    
    return ConversationHandler.END

async def send_token_symbol(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process token symbol and ask for amount."""
    # Ensure context.user_data exists and is a dictionary
    if context.user_data is None:
        context.user_data = {}
    
    if update.message is None:
        logger.error("Message is None in send_token_symbol")
        return ConversationHandler.END
        
    message_text = update.message.text
    if message_text is None:
        await update.message.reply_text("Invalid input. Please enter a valid token symbol.")
        return SEND_TOKEN_SYMBOL
        
    symbol: str = message_text.strip().upper()
    
    # Input size limiting
    if len(symbol) > MAX_SYMBOL_LENGTH:
        await update.message.reply_text(
            f"❌ Symbol too long. Please enter a symbol with fewer than {MAX_SYMBOL_LENGTH} characters.\n\n"
            "Type /cancel to cancel the transaction."
        )
        return SEND_TOKEN_SYMBOL
    
    # Check if user wants to cancel
    if symbol.lower() == "/cancel":
        await update.message.reply_text("Transaction cancelled.")
        return ConversationHandler.END
    
    token_info: Optional[Dict[str, Any]] = await token.find_token(symbol=symbol)
    
    if not token_info:
        await update.message.reply_text(
            f"Token {symbol} not found in the supported tokens list.\n"
            "Please enter a valid token symbol:"
        )
        return SEND_TOKEN_SYMBOL
    
    context.user_data['send_token_info'] = token_info
    
    # Check if we're sending the entire balance
    if context.user_data.get('send_all_token', False):
        await update.message.reply_text(f"Please enter the recipient address to send all your {symbol}:")
        return SEND_TOKEN_ADDRESS
    else:
        await update.message.reply_text(f"Please enter the amount of {symbol} to send, or type `all` to send your entire balance:")
        return SEND_TOKEN_AMOUNT

async def send_token_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process token amount and ask for recipient address."""
    # Ensure context.user_data exists and is a dictionary
    if context.user_data is None:
        context.user_data = {}
    
    if update.message is None:
        logger.error("Message is None in send_token_amount")
        return ConversationHandler.END
        
    message_text = update.message.text
    if message_text is None:
        await update.message.reply_text("Invalid input. Please enter a valid amount.")
        return SEND_TOKEN_AMOUNT
        
    raw_amount: str = message_text.strip()
    
    # Input size limiting
    if len(raw_amount) > MAX_AMOUNT_LENGTH:
        await update.message.reply_text(
            f"❌ Input too long. Please enter an amount with fewer than {MAX_AMOUNT_LENGTH} characters.\n\n"
            "Type /cancel to cancel the transaction."
        )
        return SEND_TOKEN_AMOUNT
    
    # Check if user wants to cancel
    if raw_amount.lower() == "/cancel":
        await update.message.reply_text("Transaction cancelled.")
        return ConversationHandler.END
    
    # Check if user wants to send all
    if raw_amount.lower() == "all":
        context.user_data['send_all_token'] = True
        token_info: Dict[str, Any] = context.user_data.get('send_token_info', {})
        symbol: str = token_info.get('symbol', 'tokens')
        await update.message.reply_text(
            f"You've chosen to send all your {symbol}. Please enter the recipient address:\n\n"
            "Type /cancel to cancel the transaction."
        )
        return SEND_TOKEN_ADDRESS
    
    try:
        amount: float = float(raw_amount)
        if amount <= 0:
            await update.message.reply_text(
                "Amount must be greater than 0. Please try again:\n\n"
                "Type /cancel to cancel the transaction."
            )
            return SEND_TOKEN_AMOUNT
            
        context.user_data['send_token_amount'] = amount
        await update.message.reply_text(
            "Please enter the recipient address:\n\n"
            "Type /cancel to cancel the transaction."
        )
        return SEND_TOKEN_ADDRESS
    except ValueError:
        await update.message.reply_text(
            "Invalid amount. Please enter a number or type 'all' to send your entire balance:\n\n"
            "Type /cancel to cancel the transaction."
        )
        return SEND_TOKEN_AMOUNT

async def send_token_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process recipient address and send token with status updates."""
    # Ensure context.user_data exists and is a dictionary
    if context.user_data is None:
        context.user_data = {}
    
    if update.message is None:
        logger.error("Message is None in send_token_address")
        return ConversationHandler.END
        
    message_text = update.message.text
    if message_text is None:
        await update.message.reply_text("Invalid input. Please enter a valid address.")
        return SEND_TOKEN_ADDRESS
        
    recipient_address: str = message_text.strip()
    
    # Input size limiting
    if len(recipient_address) > MAX_ADDRESS_LENGTH:
        await update.message.reply_text(
            f"❌ Address too long. Please enter an address with fewer than {MAX_ADDRESS_LENGTH} characters.\n\n"
            "Type /cancel to cancel the transaction."
        )
        return SEND_TOKEN_ADDRESS
    
    # Check if user wants to cancel
    if recipient_address.lower() == "/cancel":
        await update.message.reply_text("Transaction cancelled.")
        return ConversationHandler.END
    
    token_info: Optional[Dict[str, Any]] = context.user_data.get('send_token_info')
    
    # Handle sending entire balance case differently
    send_all: bool = context.user_data.get('send_all_token', False)
    
    if not send_all:
        amount: Optional[float] = context.user_data.get('send_token_amount')
        if not amount or not token_info:
            await update.message.reply_text("Something went wrong. Please start over with /send")
            return ConversationHandler.END
    elif not token_info:
        await update.message.reply_text("Something went wrong. Please start over with /send")
        return ConversationHandler.END
    
    if update.effective_user is None:
        logger.error("User is None in send_token_address")
        return ConversationHandler.END
        
    user_id_int: int = update.effective_user.id
    
    # Get PIN from pin_manager instead of context
    pin: Optional[str] = pin_manager.get_pin(user_id_int)
    
    # Get active wallet name
    wallet_name: Optional[str] = wallet_manager.get_active_wallet_name(str(user_id_int))
    
    # Get user wallet with PIN if required
    user_wallet: Optional[WalletData] = wallet_manager.get_user_wallet(str(user_id_int), wallet_name, pin)
    
    if not user_wallet:
        await update.message.reply_text("You don't have a wallet yet. Use /wallet to create one.")
        return ConversationHandler.END
    
    # Check if we have a valid private key
    if not user_wallet.get('private_key') or user_wallet.get('decryption_failed', False):
        error_message: str = "Cannot send transaction: Unable to access wallet private key."
        await update.message.reply_text(f"❌ {error_message}")
        return ConversationHandler.END
    
    # Initial response with loading indicator
    token_amount_text: str = f"Sending entire {token_info['symbol']} balance" if send_all else f"Amount: {context.user_data.get('send_token_amount')} {token_info['symbol']}"
    response_text: str = (
        f"🔄 Processing your transaction...\n"
        f"{token_amount_text}\n"
        f"To: {recipient_address}\n\n"
        f"Please wait while the transaction is being processed... ⏳"
    )
    
    response = await update.message.reply_text(response_text)
    
    # Create a status callback using the utility function
    status_callback = create_status_callback(response, max_lines=15, header_lines=4)
    
    try:
        # Validate addresses
        try:
            valid_recipient: str = validate_address(recipient_address)
            valid_token_address: str = validate_address(token_info['address'])
            await ensure_awaitable(status_callback("✓ Addresses validated"))
        except ValueError as e:
            logger.error(f"Invalid address: {e}")
            await response.edit_text(f"❌ Transaction failed: Invalid address.\n{str(e)}")
            return ConversationHandler.END
        
        # Get user address in checksum format
        user_address: str = user_wallet['address']
        
        # Get token contract and balance
        await ensure_awaitable(status_callback(f"Checking your {token_info['symbol']} balance..."))
        
        token_balance_info: Dict[str, Any] = await wallet_manager.get_token_balance(valid_token_address, user_address)
        token_balance: float = token_balance_info['balance']
        decimals: int = token_balance_info['decimals']
        
        # Determine amount to send
        if send_all:
            amount = token_balance
            await ensure_awaitable(status_callback(f"Sending entire balance: {amount} {token_info['symbol']}"))
        else:
            amount = context.user_data.get('send_token_amount')
            
            # Check if user has enough tokens
            if amount is None:
                # Handle the case where amount is None
                await ensure_awaitable(status_callback(f"❌ Error: Invalid amount specified."))
                await response.edit_text("❌ Transaction failed: Invalid amount specified.")
                return ConversationHandler.END
                
            if token_balance < amount:
                await ensure_awaitable(status_callback(f"❌ Insufficient {token_info['symbol']} balance. You have {token_balance} but need {amount}."))
                await response.edit_text(
                    f"❌ Transaction failed: Insufficient token balance.\n\n"
                    f"Your balance: {token_balance} {token_info['symbol']}\n"
                    f"Required: {amount} {token_info['symbol']}\n\n"
                    f"Please add funds to your wallet and try again."
                )
                return ConversationHandler.END
        
        await ensure_awaitable(status_callback(f"✓ Token balance sufficient: {token_balance} {token_info['symbol']}"))
        
        # Use utility function to estimate gas
        try:
            # Create a properly typed callback wrapper
            callback_wrapper = create_callback_wrapper(status_callback)
            
            gas_info: Dict[str, float] = await estimate_token_transfer_gas(
                user_address,
                valid_recipient,
                valid_token_address,
                float(amount) if amount is not None else 0.0,  # Convert to float with None check
                decimals,
                callback_wrapper
            )
            
            gas_required: float = gas_info['gas_bnb']
        except Exception as e:
            logger.warning(f"Gas estimation failed: {e}. Using default estimate.")
            await ensure_awaitable(status_callback("Gas estimation failed. Using conservative default value."))
            gas_required_default: float = 0.002  # Default gas cost for BSC token transfers
            gas_required = gas_required_default  # Use the default value
        
        # Check BNB balance for gas
        await ensure_awaitable(status_callback("Checking your BNB balance for gas fees..."))
        bnb_balance_response = await wallet_manager.get_bnb_balance(user_address)
        bnb_balance_raw = int(bnb_balance_response.get('raw_balance', 0))
        bnb_balance: float = float(w3.from_wei(bnb_balance_raw, 'ether'))
        
        # Ensure we have enough BNB for gas
        if bnb_balance < gas_required:
            await ensure_awaitable(status_callback(f"❌ Insufficient BNB for gas fees. You have {bnb_balance} BNB but need {gas_required} BNB for gas."))
            await response.edit_text(
                f"❌ Transaction failed: Insufficient BNB for gas fees.\n\n"
                f"Your BNB balance: {bnb_balance} BNB\n"
                f"Required for gas: {gas_required} BNB\n\n"
                f"Please add BNB to your wallet for gas and try again."
            )
            return ConversationHandler.END
        
        # Format balance with a reasonable number of decimals for display
        bnb_balance_str = '{:.6f}'.format(bnb_balance)
        await ensure_awaitable(status_callback(f"✓ BNB balance sufficient for gas: {bnb_balance_str} BNB"))
        
        # Ensure private_key is not None
        private_key = user_wallet.get('private_key', '')
        if not private_key:
            await response.edit_text("❌ Transaction failed: Unable to access wallet private key.")
            return ConversationHandler.END
            
        # OFAC Compliance Check - BLOCK ALL transactions if compliance check fails
        if OFAC_AVAILABLE and ofac_manager:
            try:
                compliance_result = await ofac_manager.check_transaction_compliance(
                    from_address=user_wallet['address'],
                    to_address=valid_recipient,
                    user_id=str(user_id_int)
                )
                
                if not compliance_result['is_compliant']:
                    await response.edit_text(
                        f"❌ Transaction blocked for compliance reasons:\n"
                        f"{compliance_result['blocked_reason']}\n\n"
                        f"This transaction cannot be processed due to sanctions compliance requirements."
                    )
                    return ConversationHandler.END
                    
            except Exception as e:
                logger.error(f"OFAC compliance check failed for token transaction: {str(e)} - BLOCKING transaction for safety")
                await response.edit_text(
                    f"❌ Transaction blocked: Compliance check failed.\n\n"
                    f"Unable to verify transaction compliance. Transaction has been blocked for security reasons.\n"
                    f"Please try again later or contact support if this issue persists."
                )
                return ConversationHandler.END
        
        # Create a properly typed callback wrapper
        callback_wrapper = create_callback_wrapper(status_callback)
        
        # Send the token
        try:
            tx_result = await send_token(
                private_key,
                valid_token_address,
                valid_recipient,
                str(amount),
                status_callback=callback_wrapper
            )
            
            # Format success message
            success_message = (
                f"✅ Transaction successful!\n\n"
                f"Token: {token_info['symbol']}\n"
                f"Amount: {number_display_with_sigfig(amount, 6)}\n"
                f"Recipient: {valid_recipient[:10]}...{valid_recipient[-8:]}\n"
                f"TX Hash: `0x{tx_result['tx_hash']}`\n"
                f"View on Scanner: {BSC_SCANNER_URL}/tx/0x{tx_result['tx_hash']}\n"
                f"Block: {tx_result['block_number']}"
            )
            
            await response.edit_text(success_message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error sending token: {e}")
            error_message = f"❌ Transaction failed: {str(e)}\n\nPlease check your balance and try again."
            await response.edit_text(error_message)
            
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Error sending token: {e}")
        await response.edit_text(
            f"❌ Transaction failed: {str(e)}\n\n"
            "Please check your balance and try again."
        )
    
    return ConversationHandler.END