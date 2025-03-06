from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters
import db
import wallet
import logging

# Enable logging
logger = logging.getLogger(__name__)

# Conversation states
CHOOSING_ACTION, ENTERING_NAME, ENTERING_PRIVATE_KEY = range(3)

# Store temporary data during conversation
user_temp_data = {}

async def addwallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the process to add a new wallet."""
    keyboard = [
        [InlineKeyboardButton("Create New Wallet", callback_data='create_wallet')],
        [InlineKeyboardButton("Import Existing Wallet", callback_data='import_wallet')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "How would you like to add a wallet?", 
        reply_markup=reply_markup
    )
    
    return CHOOSING_ACTION

async def action_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle wallet creation method choice."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    choice = query.data
    
    # Initialize user temp data
    user_temp_data[user_id] = {'action': choice}
    
    await query.edit_message_text("Please enter a name for this wallet:")
    
    return ENTERING_NAME

async def process_wallet_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the wallet name."""
    user_id = update.effective_user.id
    wallet_name = update.message.text.strip()
    
    # Check if user has temp data
    if user_id not in user_temp_data:
        await update.message.reply_text("Something went wrong. Please try again with /addwallet.")
        return ConversationHandler.END
    
    # Check if name is valid
    if not wallet_name or len(wallet_name) > 32:
        await update.message.reply_text("Wallet name must be between 1 and 32 characters. Please try again:")
        return ENTERING_NAME
    
    # Check if wallet with this name already exists
    existing_wallets = db.get_user_wallets(user_id)
    if wallet_name in existing_wallets:
        await update.message.reply_text(f"A wallet with name '{wallet_name}' already exists. Please choose a different name:")
        return ENTERING_NAME
    
    # Store wallet name
    user_temp_data[user_id]['wallet_name'] = wallet_name
    
    # Process based on action
    if user_temp_data[user_id]['action'] == 'create_wallet':
        # Create new wallet
        new_wallet = wallet.create_wallet()
        db.save_user_wallet(user_id, new_wallet, wallet_name)
        
        await update.message.reply_text(
            f"🎉 New wallet '{wallet_name}' created!\n\n"
            f"Address: `{new_wallet['address']}`\n\n"
            f"Private Key: `{new_wallet['private_key']}`\n\n"
            "⚠️ IMPORTANT: Save your private key somewhere safe. "
            "Anyone with access to your private key can access your wallet. "
            "Your wallet is encrypted and cannot be recovered if lost. "
            "I won't show it again for security reasons.",
            parse_mode='Markdown'
        )
        
        # Clean up temp data
        del user_temp_data[user_id]
        return ConversationHandler.END
    else:
        # Import wallet from private key
        await update.message.reply_text(
            "Please enter the private key for this wallet:\n\n"
            "⚠️ WARNING: Never share your private keys with anyone!"
        )
        return ENTERING_PRIVATE_KEY

async def process_private_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the private key for wallet import."""
    user_id = update.effective_user.id
    private_key = update.message.text.strip()
    
    # Delete the message with private key for security
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Could not delete message with private key: {e}")
    
    # Check if user has temp data
    if user_id not in user_temp_data:
        await update.message.reply_text("Something went wrong. Please try again with /addwallet.")
        return ConversationHandler.END
    
    wallet_name = user_temp_data[user_id]['wallet_name']
    
    try:
        # Validate and import the private key
        from eth_account import Account
        
        if not private_key.startswith('0x'):
            private_key = '0x' + private_key
        
        account = Account.from_key(private_key)
        address = account.address
        
        # Create wallet object
        imported_wallet = {
            'address': address,
            'private_key': private_key
        }
        
        # Save the wallet
        db.save_user_wallet(user_id, imported_wallet, wallet_name)
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"✅ Wallet '{wallet_name}' imported successfully!\n\n"
                 f"Address: `{address}`\n\n"
                 "Your wallet has been encrypted and stored securely.",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error importing wallet: {e}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ Error importing wallet: Invalid private key format. Please try again with /addwallet."
        )
    
    # Clean up temp data
    del user_temp_data[user_id]
    return ConversationHandler.END 