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
        await query.message.reply_text("Please enter the amount of BNB to send:")
        return SEND_BNB_AMOUNT
    elif query.data == 'send_token':
        await query.message.reply_text("Please enter the token symbol to send (e.g., BUSD):")
        return SEND_TOKEN_SYMBOL
    
    return ConversationHandler.END

async def send_bnb_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process BNB amount and ask for recipient address."""
    try:
        amount = float(update.message.text.strip())
        if amount <= 0:
            await update.message.reply_text("Amount must be greater than 0. Please try again:")
            return SEND_BNB_AMOUNT
        
        context.user_data['send_amount'] = amount
        await update.message.reply_text("Please enter the recipient address:")
        return SEND_BNB_ADDRESS
    except ValueError:
        await update.message.reply_text("Invalid amount. Please enter a number:")
        return SEND_BNB_AMOUNT

async def send_bnb_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process recipient address and send BNB with status updates."""
    recipient_address = update.message.text.strip()
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
    response = await update.message.reply_text(
        f"🔄 Processing your transaction...\n"
        f"Amount: {amount} BNB\n"
        f"To: {recipient_address}\n\n"
        f"Please wait while the transaction is being processed... ⏳"
    )
    
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
            f"Amount: {amount} BNB\n"
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
    await update.message.reply_text(f"Please enter the amount of {token_symbol} to send:")
    return SEND_TOKEN_AMOUNT

async def send_token_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process token amount and ask for recipient address."""
    try:
        amount = float(update.message.text.strip())
        if amount <= 0:
            await update.message.reply_text("Amount must be greater than 0. Please try again:")
            return SEND_TOKEN_AMOUNT
        
        context.user_data['send_amount'] = amount
        await update.message.reply_text("Please enter the recipient address:")
        return SEND_TOKEN_ADDRESS
    except ValueError:
        await update.message.reply_text("Invalid amount. Please enter a number:")
        return SEND_TOKEN_AMOUNT

async def send_token_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process recipient address and send token with status updates."""
    recipient_address = update.message.text.strip()
    amount = context.user_data.get('send_amount')
    token_info = context.user_data.get('token_info')
    
    if not amount or not token_info:
        await update.message.reply_text("Something went wrong. Please start over with /send")
        return ConversationHandler.END
    
    user_id = update.effective_user.id
    user_wallet = db.get_user_wallet(user_id)
    
    if not user_wallet:
        await update.message.reply_text("You don't have a wallet yet. Use /wallet to create one.")
        return ConversationHandler.END
    
    # Initial response with loading indicator
    response = await update.message.reply_text(
        f"🔄 Processing your transaction...\n"
        f"Amount: {amount} {token_info['symbol']}\n"
        f"To: {recipient_address}\n\n"
        f"Please wait while the transaction is being processed... ⏳"
    )
    
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
            f"Amount: {amount} {token_info['symbol']}\n"
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