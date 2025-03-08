from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
import db
import wallet
import logging
import traceback
import re
from wallet.mnemonic import derive_wallet_from_mnemonic
from utils.self_destruction_message import send_self_destructing_message
from services.pin import require_pin, pin_manager

# Enable logging
logger = logging.getLogger(__name__)

# Conversation states
CHOOSING_ACTION, ENTERING_NAME, ENTERING_PRIVATE_KEY = range(3)

# Input validation constants
MAX_WALLET_NAME_LENGTH = 32
MIN_WALLET_NAME_LENGTH = 3
MAX_PRIVATE_KEY_LENGTH = 130  # Private keys are 64 hex chars, plus optional '0x' prefix, allow some buffer

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
    logger.info("Received callback query from user")
    query = update.callback_query
    await query.answer()
    logger.info("Answered callback query")
    
    user_id = update.effective_user.id
    choice = query.data
    logger.info(f"User {user_id} chose {choice}")
    # Initialize user temp data
    user_temp_data[user_id] = {'action': choice}
    logger.info(f"User temp data initialized for user {user_id}")

    logger.info("Editing message text to prompt user for wallet name")
    await query.edit_message_text(
        "Please enter a name for this wallet:\n\n"
        f"• Names must be {MIN_WALLET_NAME_LENGTH}-{MAX_WALLET_NAME_LENGTH} characters long\n"
        "• Letters, numbers, spaces, and emoji are allowed\n"
        "• Names cannot start or end with spaces\n"
        "• Special characters like \" ' < > ` ; are not allowed"
    )
    logger.info("Message text edited successfully")
    return ENTERING_NAME

async def process_wallet_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the wallet name."""
    user_id = update.effective_user.id
    wallet_name = update.message.text.strip()
    
    # Check if user has temp data
    if user_id not in user_temp_data:
        await update.message.reply_text("Something went wrong. Please try again with /addwallet.")
        return ConversationHandler.END
    
    # Length validation
    if not wallet_name:
        await update.message.reply_text("Wallet name cannot be empty. Please enter a name:")
        return ENTERING_NAME
        
    if len(wallet_name) > MAX_WALLET_NAME_LENGTH:
        await update.message.reply_text(f"Wallet name is too long. Maximum length is {MAX_WALLET_NAME_LENGTH} characters. Please try again:")
        return ENTERING_NAME
        
    if len(wallet_name) < MIN_WALLET_NAME_LENGTH:
        await update.message.reply_text(f"Wallet name is too short. Minimum length is {MIN_WALLET_NAME_LENGTH} characters. Please try again:")
        return ENTERING_NAME
    
    # Check for dangerous characters
    if re.search(r'[\'";`<>]', wallet_name):
        await update.message.reply_text("Wallet name contains invalid characters. Please avoid using: ' \" ; ` < >")
        return ENTERING_NAME
        
    # Check for leading/trailing whitespace (the strip above removes it, but we should tell the user)
    if wallet_name != update.message.text:
        await update.message.reply_text("Wallet name cannot have leading or trailing spaces. Please try again:")
        return ENTERING_NAME
    
    # Check for reserved names
    reserved_names = ["default", "wallet", "main", "primary", "backup", "test", "admin", "system"]
    if wallet_name.lower() in reserved_names:
        await update.message.reply_text(f"'{wallet_name}' is a reserved name and cannot be used. Please choose a different name:")
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
        try:
            # Check if user already has a mnemonic
            existing_mnemonic = db.get_user_mnemonic(user_id, pin_manager.get_pin(user_id))
            
            if existing_mnemonic:
                # User has existing mnemonic, derive wallet with next index
                logger.debug("User has existing mnemonic, deriving new wallet")
                
                # Get current wallet count to use as index
                existing_wallets = db.get_user_wallets(user_id)
                wallet_index = len(existing_wallets)
                
                # Derive a new wallet from the existing mnemonic
                new_wallet = derive_wallet_from_mnemonic(existing_mnemonic, index=wallet_index)
                
                # Save the wallet
                wallet_to_save = {
                    'address': new_wallet['address'],
                    'private_key': new_wallet['private_key'],
                    'path': new_wallet['path']
                }
                
                # Save wallet
                db.save_user_wallet(user_id, wallet_to_save, wallet_name, pin_manager.get_pin(user_id))
                
                # Normal message since no seed phrase is shown
                # Do not need to show path, since we are using the standard BSC/ETH path
                await update.message.reply_text(
                    f"🎉 New wallet '{wallet_name}' created from your existing seed phrase!\n\n"
                    f"Address: `{new_wallet['address']}`\n\n"
                    "This wallet is derived from your existing seed phrase, which you can recover using /backup.",
                    parse_mode='Markdown'
                )
            else:
                # User doesn't have a mnemonic, create a new one
                logger.debug("User has no mnemonic, creating new one")
                mnemonic = wallet.create_mnemonic()
                
                # Create a new wallet from the mnemonic
                new_wallet = wallet.create_mnemonic_wallet(mnemonic)
                
                # Remove mnemonic from wallet object before saving
                wallet_to_save = {
                    'address': new_wallet['address'],
                    'private_key': new_wallet['private_key'],
                    'path': new_wallet['path']
                }
                
                # Save wallet
                db.save_user_wallet(user_id, wallet_to_save, wallet_name, pin_manager.get_pin(user_id))
                
                # Save mnemonic separately
                db.save_user_mnemonic(user_id, mnemonic, pin_manager.get_pin(user_id))
                
                # Send self-destructing message with seed phrase
                # Note: This will first show a security warning with a button
                # that the user must click to see the sensitive information
                message_text = (
                    f"🎉 New wallet '{wallet_name}' created with new seed phrase!\n\n"
                    f"Address: `{new_wallet['address']}`\n\n"
                    f"Seed Phrase: `{mnemonic}`\n\n"
                    "⚠️ IMPORTANT: Write down and save your seed phrase somewhere safe.\n"
                    "Anyone with access to your seed phrase can access your wallet.\n"
                    "Your wallet is encrypted but cannot be recovered without this phrase."
                )
                
                await send_self_destructing_message(
                    update,
                    context,
                    message_text,
                    parse_mode='Markdown'
                )
        except Exception as e:
            logger.error(f"Error creating wallet: {e}")
            logger.error(traceback.format_exc())
            await update.message.reply_text(
                "❌ Error creating wallet. Please try again with /addwallet.\n"
                f"Error: {str(e)}"
            )
            
        # Clean up temp data
        del user_temp_data[user_id]
        return ConversationHandler.END
    else:
        # Import wallet from private key
        await update.message.reply_text(
            "Please enter the private key for this wallet:\n\n"
            "• Private keys are typically 64 characters (hexadecimal)\n"
            "• The '0x' prefix is optional\n\n"
            "⚠️ WARNING: Never share your private keys with anyone!"
        )
        return ENTERING_PRIVATE_KEY

async def process_private_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the private key for wallet import."""
    user_id = update.effective_user.id
    private_key = update.message.text.strip()
    
    # Input size validation for private key
    if len(private_key) > MAX_PRIVATE_KEY_LENGTH:
        # Create a secure response with no sensitive data
        await update.message.reply_text(
            f"❌ Private key too long. Please enter a valid private key (max {MAX_PRIVATE_KEY_LENGTH} characters)."
        )
        # Try to delete the original message which contains the too-long key
        try:
            await update.message.delete()
        except Exception as e:
            logger.warning(f"Could not delete message with invalid private key: {e}")
        return ENTERING_PRIVATE_KEY
    
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
    
    # Basic format validation
    if not re.match(r'^(0x)?[0-9a-fA-F]{64}$', private_key):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ Invalid private key format. Private keys must be 64 hexadecimal characters with an optional '0x' prefix.\n\n"
                 "Please try again with /addwallet."
        )
        # Clean up temp data
        del user_temp_data[user_id]
        return ConversationHandler.END
    
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
        db.save_user_wallet(user_id, imported_wallet, wallet_name, pin_manager.get_pin(user_id))
        
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
            text=f"❌ Error importing wallet: Invalid private key. Please try again with /addwallet."
        )
    
    # Clean up temp data
    del user_temp_data[user_id]
    return ConversationHandler.END 

# Create a PIN-protected version of the command
pin_protected_addwallet = require_pin(
    "🔒 Adding a wallet requires PIN verification.\nPlease enter your PIN:"
)(addwallet_command) 