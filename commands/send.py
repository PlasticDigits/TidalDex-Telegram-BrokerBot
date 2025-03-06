from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
import db
import wallet
from utils import token
from wallet.utils import validate_address
from utils.status_updates import create_status_callback
import logging

# Enable logging
logger = logging.getLogger(__name__)

# Conversation states
CHOOSING_ACTION, SEND_BNB_AMOUNT, SEND_BNB_ADDRESS, SEND_TOKEN_SYMBOL, SEND_TOKEN_AMOUNT, SEND_TOKEN_ADDRESS = range(6)

async def send_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the send process."""
    user_id = update.effective_user.id
    user_wallet = db.get_user_wallet(user_id)
    
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
                [InlineKeyboardButton("Send All Token", callback_data='send_token_all')]
            ])
        )
    else:
        context.user_data['send_all'] = False
        keyboard = [
            [InlineKeyboardButton("Send BNB", callback_data='send_bnb')],
            [InlineKeyboardButton("Send Token", callback_data='send_token')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "What would you like to send?", 
            reply_markup=reply_markup
        )
    
    return CHOOSING_ACTION

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle button callbacks."""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'send_bnb':
        await query.message.reply_text("Please enter the amount of BNB to send, or type `all` to send your entire balance:")
        return SEND_BNB_AMOUNT
    elif query.data == 'send_bnb_all':
        # Get the user's BNB balance
        user_id = update.effective_user.id
        user_wallet = db.get_user_wallet(user_id)
        
        if not user_wallet:
            await query.message.reply_text("You don't have a wallet yet. Use /wallet to create one.")
            return ConversationHandler.END
        
        # We'll calculate the exact amount in the next step, accounting for gas
        context.user_data['send_all_bnb'] = True
        
        await query.message.reply_text("Please enter the recipient address for sending all your BNB:")
        return SEND_BNB_ADDRESS
    elif query.data == 'send_token':
        await query.message.reply_text("Please enter the token symbol to send (e.g., BUSD):")
        return SEND_TOKEN_SYMBOL
    elif query.data == 'send_token_all':
        await query.message.reply_text("Please enter the token symbol to send all of (e.g., BUSD):")
        context.user_data['send_all_token'] = True
        return SEND_TOKEN_SYMBOL
    
    return ConversationHandler.END

async def send_bnb_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process BNB amount and ask for recipient address."""
    input_text = update.message.text.strip()
    
    # Check if user wants to send all
    if input_text.lower() == "all":
        context.user_data['send_all_bnb'] = True
        await update.message.reply_text("You've chosen to send all your BNB. Please enter the recipient address:")
        return SEND_BNB_ADDRESS
    
    try:
        amount = float(input_text)
        if amount <= 0:
            await update.message.reply_text("Amount must be greater than 0. Please try again:")
            return SEND_BNB_AMOUNT
        
        context.user_data['send_amount'] = amount
        await update.message.reply_text("Please enter the recipient address:")
        return SEND_BNB_ADDRESS
    except ValueError:
        await update.message.reply_text("Invalid amount. Please enter a number or type 'all' to send your entire balance:")
        return SEND_BNB_AMOUNT

async def send_bnb_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process recipient address and send BNB with status updates."""
    recipient_address = update.message.text.strip()
    
    # Handle sending entire balance case differently
    send_all = context.user_data.get('send_all_bnb', False)
    
    if not send_all:
        amount = context.user_data.get('send_amount')
        if not amount:
            await update.message.reply_text("Something went wrong. Please start over with /send")
            return ConversationHandler.END
    
    user_id = update.effective_user.id
    user_wallet = db.get_user_wallet(user_id)
    
    if not user_wallet:
        await update.message.reply_text("You don't have a wallet yet. Use /wallet to create one.")
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
        checksum_user_address = wallet.utils.validate_address(user_address)
        checksum_recipient = wallet.utils.validate_address(valid_recipient)
        
        # Check user's BNB balance
        await status_callback("Checking your BNB balance...")
        bnb_balance = wallet.get_bnb_balance(user_address)
        
        # Calculate amount to send
        amount = None  # Will be set based on balance and gas estimate
        
        # Estimate gas cost using web3
        await status_callback("Estimating gas fees for transaction...")
        from utils.web3_connection import w3
        from web3 import Web3
        
        if send_all:
            # If sending all, estimate gas for a transaction sending the entire balance first
            # Then subtract that gas cost from the balance to get the actual amount to send
            
            # Get current gas price
            gas_price = w3.eth.gas_price
            
            # Estimate gas for the transaction (need to use a dummy amount for estimation)
            # We'll use 90% of balance for estimation to ensure it's not over the actual balance
            dummy_amount_wei = w3.to_wei(bnb_balance * 0.9, 'ether')
            
            gas_estimate = w3.eth.estimate_gas({
                'to': checksum_recipient,
                'from': checksum_user_address,
                'value': dummy_amount_wei
            })
            
            # Calculate total gas cost in BNB
            gas_cost_wei = gas_price * gas_estimate
            gas_cost_bnb = w3.from_wei(gas_cost_wei, 'ether')
            
            # Calculate the actual amount to send (entire balance minus gas cost)
            amount = bnb_balance - gas_cost_bnb
            
            # Make sure amount is positive
            if amount <= 0:
                await status_callback(f"❌ Insufficient balance. Your balance of {bnb_balance} BNB is not enough to cover gas costs of {gas_cost_bnb} BNB.")
                await response.edit_text(
                    f"❌ Transaction failed: Insufficient balance for gas.\n\n"
                    f"Your balance: {bnb_balance} BNB\n"
                    f"Estimated gas cost: {gas_cost_bnb} BNB\n\n"
                    f"Your balance is too low to send BNB after accounting for gas fees."
                )
                return ConversationHandler.END
            
            await status_callback(f"Sending {amount} BNB (entire balance minus gas)")
        else:
            # Regular case (not sending all)
            amount = context.user_data.get('send_amount')
            
            # Convert amount to wei
            amount_wei = w3.to_wei(amount, 'ether')
            
            # Get current gas price
            gas_price = w3.eth.gas_price
            
            # Estimate gas for the transaction
            gas_estimate = w3.eth.estimate_gas({
                'to': checksum_recipient,
                'from': checksum_user_address,
                'value': amount_wei
            })
            
            # Calculate total gas cost in BNB
            gas_cost_wei = gas_price * gas_estimate
            gas_cost_bnb = w3.from_wei(gas_cost_wei, 'ether')
            
            # No buffer needed as BSC has flat gas costs
            required_amount = amount + gas_cost_bnb
            
            await status_callback(f"Estimated gas cost: {gas_cost_bnb} BNB")
            
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
    token_symbol = update.message.text.strip().upper()
    token_info = token.find_token(symbol=token_symbol)
    
    if not token_info:
        await update.message.reply_text(
            f"Token {token_symbol} not found in the supported tokens list.\n"
            "Please enter a valid token symbol:"
        )
        return SEND_TOKEN_SYMBOL
    
    context.user_data['token_info'] = token_info
    
    # Check if we're sending the entire balance
    if context.user_data.get('send_all_token', False):
        await update.message.reply_text(f"Please enter the recipient address to send all your {token_symbol}:")
        return SEND_TOKEN_ADDRESS
    else:
        await update.message.reply_text(f"Please enter the amount of {token_symbol} to send, or type `all` to send your entire balance:")
        return SEND_TOKEN_AMOUNT

async def send_token_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process token amount and ask for recipient address."""
    input_text = update.message.text.strip()
    token_info = context.user_data.get('token_info')
    
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
    token_info = context.user_data.get('token_info')
    
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
    user_wallet = db.get_user_wallet(user_id)
    
    if not user_wallet:
        await update.message.reply_text("You don't have a wallet yet. Use /wallet to create one.")
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
        checksum_user_address = wallet.utils.validate_address(user_address)
        checksum_recipient = wallet.utils.validate_address(valid_recipient)
        
        # Get token contract and balance
        await status_callback(f"Checking your {token_info['symbol']} balance...")
        from utils.web3_connection import w3
        from utils.token_operations import get_token_contract, convert_to_raw_amount
        
        token_contract = get_token_contract(valid_token_address)
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
        
        # Estimate gas cost using web3
        await status_callback("Estimating gas fees for transaction...")
        
        # Convert token amount to raw amount
        token_amount = convert_to_raw_amount(amount, decimals)
        
        # Get current gas price
        gas_price = w3.eth.gas_price
        
        # Prepare the transfer function data to estimate gas
        transfer_function = token_contract.functions.transfer(
            checksum_recipient,
            token_amount
        )
        
        # Estimate gas
        try:
            gas_estimate = transfer_function.estimate_gas({
                'from': checksum_user_address
            })
            
            # Calculate total gas cost in BNB
            gas_cost_wei = gas_price * gas_estimate
            gas_cost_bnb = w3.from_wei(gas_cost_wei, 'ether')
            
            # No buffer needed as BSC has flat gas costs
            gas_required = gas_cost_bnb
            
            await status_callback(f"Estimated gas cost: {gas_cost_bnb} BNB")
        except Exception as e:
            # If gas estimation fails, use a conservative default
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