from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
import db
from db.wallet import get_active_wallet_name
import wallet
from utils import token
from wallet.utils import validate_address
from utils.status_updates import create_status_callback
from utils.gas_estimation import estimate_bnb_transfer_gas, estimate_token_transfer_gas, estimate_max_bnb_transfer
from services.pin import require_pin, pin_manager
import logging

# Enable logging
logger = logging.getLogger(__name__)

# Conversation states
CHOOSING_ACTION, SEND_BNB_AMOUNT, SEND_BNB_ADDRESS, SEND_TOKEN_SYMBOL, SEND_TOKEN_AMOUNT, SEND_TOKEN_ADDRESS = range(6)

# Constants for input validation
MAX_ADDRESS_LENGTH = 100  # Ethereum addresses are 42 chars with 0x prefix
MAX_AMOUNT_LENGTH = 30    # Financial amounts shouldn't need more than this
MAX_SYMBOL_LENGTH = 20    # Token symbols are typically short

async def send_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the send process."""
    user_id = update.effective_user.id
    
    # Get active wallet name and use pin_manager for PIN
    wallet_name = get_active_wallet_name(user_id)
    pin = pin_manager.get_pin(user_id)
    user_wallet = db.get_user_wallet(user_id, wallet_name, pin)
    
    if not user_wallet:
        await update.message.reply_text("You don't have a wallet yet. Use /wallet to create one.")
        return ConversationHandler.END
    
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
        keyboard = [
            [InlineKeyboardButton("Send BNB", callback_data='send_bnb')],
            [InlineKeyboardButton("Send Token", callback_data='send_token')],
            [InlineKeyboardButton("❌ Cancel", callback_data='send_cancel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "What would you like to send?", 
            reply_markup=reply_markup
        )
    
    return CHOOSING_ACTION

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle button callbacks for the send process."""
    query = update.callback_query
    await query.answer()
    
    choice = query.data
    
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
    input_text = update.message.text.strip()
    
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
        amount = float(input_text)
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
    recipient_address = update.message.text.strip()
    
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
    send_all = context.user_data.get('send_all_bnb', False)
    
    if not send_all:
        amount = context.user_data.get('send_amount')
        if not amount:
            await update.message.reply_text("Something went wrong. Please start over with /send")
            return ConversationHandler.END
    
    user_id = update.effective_user.id
    
    # Get PIN from pin_manager instead of context
    pin = pin_manager.get_pin(user_id)
    
    # Get active wallet name
    wallet_name = get_active_wallet_name(user_id)
    
    # Get user wallet with PIN if required
    user_wallet = db.get_user_wallet(user_id, wallet_name, pin)
    
    if not user_wallet:
        await update.message.reply_text("You don't have a wallet yet. Use /wallet to create one.")
        return ConversationHandler.END
    
    # Check if we have a valid private key
    if not user_wallet.get('private_key') or user_wallet.get('decryption_failed', False):
        error_message = "Cannot send transaction: Unable to access wallet private key."
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
            await status_callback("✓ Recipient address validated")
        except ValueError as e:
            logger.error(f"Invalid recipient address: {e}")
            await response.edit_text(f"❌ Transaction failed: Invalid recipient address.\n{str(e)}")
            return ConversationHandler.END
        
        # Get user address in checksum format
        user_address = user_wallet['address']
        
        # Check user's BNB balance
        await status_callback("Checking your BNB balance...")
        bnb_balance = wallet.get_bnb_balance(user_address)
        
        # Calculate amount to send
        amount = None  # Will be set based on balance and gas estimate
        
        if send_all:
            # If sending all, use utility function to calculate max amount
            try:
                amount = estimate_max_bnb_transfer(
                    user_address,
                    valid_recipient,
                    bnb_balance,
                    status_callback
                )
                await status_callback(f"Sending {amount} BNB (entire balance minus gas)")
            except ValueError as e:
                await status_callback(f"❌ Insufficient balance for gas fees.")
                await response.edit_text(
                    f"❌ Transaction failed: {str(e)}\n\n"
                    f"Your balance is too low to send BNB after accounting for gas fees."
                )
                return ConversationHandler.END
        else:
            # Regular case (not sending all)
            amount = context.user_data.get('send_amount')
            
            try:
                # Use utility function to estimate gas
                gas_info = estimate_bnb_transfer_gas(
                    user_address, 
                    valid_recipient, 
                    amount, 
                    status_callback
                )
                
                gas_cost_bnb = gas_info['gas_bnb']
                required_amount = amount + gas_cost_bnb
                
                if bnb_balance < required_amount:
                    await status_callback(f"❌ Insufficient balance. You have {bnb_balance} BNB but need {required_amount} BNB (including gas).")
                    await response.edit_text(
                        f"❌ Transaction failed: Insufficient balance.\n\n"
                        f"Your balance: {bnb_balance} BNB\n"
                        f"Transaction amount: {amount} BNB\n"
                        f"Estimated gas cost: {gas_cost_bnb} BNB\n"
                        f"Total required: {required_amount} BNB\n\n"
                        f"Please add funds to your wallet and try again."
                    )
                    return ConversationHandler.END
                
                await status_callback(f"✓ Balance sufficient: {bnb_balance} BNB")
            except Exception as e:
                logger.error(f"Error estimating gas: {e}")
                await response.edit_text(
                    f"❌ Transaction failed: Error estimating gas.\n\n"
                    f"Error: {str(e)}\n\n"
                    f"Please try again later."
                )
                return ConversationHandler.END
        
        # Send BNB with status updates
        tx_result = wallet.send_bnb(
            user_wallet['private_key'], 
            valid_recipient, 
            amount, 
            status_callback=status_callback
        )
        
        # Final success message
        await response.edit_text(
            f"✅ Transaction successful!\n\n"
            f"Amount: {amount} BNB{' (entire balance minus gas)' if send_all else ''}\n"
            f"Recipient: {valid_recipient}\n"
            f"TX Hash: `{tx_result['tx_hash']}`\n"
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
    symbol = update.message.text.strip().upper()
    
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
    
    token_info = token.find_token(symbol=symbol)
    
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
    input_text = update.message.text.strip()
    
    # Input size limiting
    if len(input_text) > MAX_AMOUNT_LENGTH:
        await update.message.reply_text(
            f"❌ Input too long. Please enter an amount with fewer than {MAX_AMOUNT_LENGTH} characters.\n\n"
            "Type /cancel to cancel the transaction."
        )
        return SEND_TOKEN_AMOUNT
    
    # Check if user wants to cancel
    if input_text.lower() == "/cancel":
        await update.message.reply_text("Transaction cancelled.")
        return ConversationHandler.END
    
    token_info = context.user_data.get('send_token_info')
    
    # Check if user wants to send all
    if input_text.lower() == "all":
        context.user_data['send_all_token'] = True
        await update.message.reply_text(f"You've chosen to send all your {token_info['symbol']}. Please enter the recipient address:")
        return SEND_TOKEN_ADDRESS
    
    try:
        amount = float(input_text)
        if amount <= 0:
            await update.message.reply_text("Amount must be greater than 0. Please try again:")
            return SEND_TOKEN_AMOUNT
        
        context.user_data['send_amount'] = amount
        await update.message.reply_text("Please enter the recipient address:")
        return SEND_TOKEN_ADDRESS
    except ValueError:
        await update.message.reply_text("Invalid amount. Please enter a number or type 'all' to send your entire balance:")
        return SEND_TOKEN_AMOUNT

async def send_token_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process recipient address and send token with status updates."""
    recipient_address = update.message.text.strip()
    
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
    
    token_info = context.user_data.get('send_token_info')
    
    # Handle sending entire balance case differently
    send_all = context.user_data.get('send_all_token', False)
    
    if not send_all:
        amount = context.user_data.get('send_amount')
        if not amount or not token_info:
            await update.message.reply_text("Something went wrong. Please start over with /send")
            return ConversationHandler.END
    elif not token_info:
        await update.message.reply_text("Something went wrong. Please start over with /send")
        return ConversationHandler.END
    
    user_id = update.effective_user.id
    
    # Get PIN from pin_manager instead of context
    pin = pin_manager.get_pin(user_id)
    
    # Get active wallet name
    wallet_name = get_active_wallet_name(user_id)
    
    # Get user wallet with PIN if required
    user_wallet = db.get_user_wallet(user_id, wallet_name, pin)
    
    if not user_wallet:
        await update.message.reply_text("You don't have a wallet yet. Use /wallet to create one.")
        return ConversationHandler.END
    
    # Check if we have a valid private key
    if not user_wallet.get('private_key') or user_wallet.get('decryption_failed', False):
        error_message = "Cannot send transaction: Unable to access wallet private key."
        await update.message.reply_text(f"❌ {error_message}")
        return ConversationHandler.END
    
    # Initial response with loading indicator
    token_amount_text = f"Sending entire {token_info['symbol']} balance" if send_all else f"Amount: {context.user_data.get('send_amount')} {token_info['symbol']}"
    response_text = (
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
            valid_recipient = validate_address(recipient_address)
            valid_token_address = validate_address(token_info['address'])
            await status_callback("✓ Addresses validated")
        except ValueError as e:
            logger.error(f"Invalid address: {e}")
            await response.edit_text(f"❌ Transaction failed: Invalid address.\n{str(e)}")
            return ConversationHandler.END
        
        # Get user address in checksum format
        user_address = user_wallet['address']
        
        # Get token contract and balance
        await status_callback(f"Checking your {token_info['symbol']} balance...")
        
        token_balance_info = wallet.get_token_balance(valid_token_address, user_address)
        token_balance = token_balance_info['balance']
        decimals = token_balance_info['decimals']
        
        # Determine amount to send
        if send_all:
            amount = token_balance
            await status_callback(f"Sending entire balance: {amount} {token_info['symbol']}")
        else:
            amount = context.user_data.get('send_amount')
            
            # Check if user has enough tokens
            if token_balance < amount:
                await status_callback(f"❌ Insufficient {token_info['symbol']} balance. You have {token_balance} but need {amount}.")
                await response.edit_text(
                    f"❌ Transaction failed: Insufficient token balance.\n\n"
                    f"Your balance: {token_balance} {token_info['symbol']}\n"
                    f"Required: {amount} {token_info['symbol']}\n\n"
                    f"Please add funds to your wallet and try again."
                )
                return ConversationHandler.END
        
        await status_callback(f"✓ Token balance sufficient: {token_balance} {token_info['symbol']}")
        
        # Use utility function to estimate gas
        try:
            gas_info = estimate_token_transfer_gas(
                user_address,
                valid_recipient,
                valid_token_address,
                amount,
                decimals,
                status_callback
            )
            
            gas_required = gas_info['gas_bnb']
        except Exception as e:
            logger.warning(f"Gas estimation failed: {e}. Using default estimate.")
            await status_callback("Gas estimation failed. Using conservative default value.")
            gas_required = 0.002  # Default gas cost for BSC token transfers
        
        # Check BNB balance for gas
        await status_callback("Checking your BNB balance for gas fees...")
        bnb_balance = wallet.get_bnb_balance(user_address)
        
        if bnb_balance < gas_required:
            await status_callback(f"❌ Insufficient BNB for gas fees. You have {bnb_balance} BNB but need {gas_required} BNB for gas.")
            await response.edit_text(
                f"❌ Transaction failed: Insufficient BNB for gas fees.\n\n"
                f"Your BNB balance: {bnb_balance} BNB\n"
                f"Estimated gas cost: {gas_required} BNB\n\n"
                f"Please add some BNB to your wallet to cover gas fees and try again."
            )
            return ConversationHandler.END
        
        await status_callback(f"✓ BNB balance sufficient for gas: {bnb_balance} BNB")
        
        # Send token with status updates
        tx_result = wallet.send_token(
            user_wallet['private_key'], 
            valid_token_address, 
            valid_recipient, 
            amount,
            status_callback=status_callback
        )
        
        # Final success message
        await response.edit_text(
            f"✅ Transaction successful!\n\n"
            f"Amount: {amount} {token_info['symbol']}{' (entire balance)' if send_all else ''}\n"
            f"Recipient: {valid_recipient}\n"
            f"TX Hash: `{tx_result['tx_hash']}`\n"
            f"Block: {tx_result['block_number']}",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error sending token: {e}")
        await response.edit_text(
            f"❌ Transaction failed: {str(e)}\n\n"
            "Please check your balance and try again."
        )
    
    return ConversationHandler.END

# Create PIN-protected versions of the conversation handlers
pin_protected_send = require_pin(
    "🔒 Sending assets requires PIN verification.\nPlease enter your PIN:"
)(send_command) 