"""
Wallet recovery and backup commands.
Provides functionality to restore a wallet from a private key or mnemonic phrase, and backup existing wallet.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler
from db.wallet import get_user_wallet, save_user_wallet, get_user_wallets, get_active_wallet_name
from db.mnemonic import save_user_mnemonic
import wallet
from eth_account import Account
import logging
from services.pin import require_pin, pin_manager

# Enable logging
logger = logging.getLogger(__name__)

# Conversation states
CHOOSING_RECOVERY_TYPE, WAITING_FOR_PRIVATE_KEY, WAITING_FOR_MNEMONIC, ENTERING_WALLET_NAME = range(4)

# Store temporary data during conversation
user_temp_data = {}

async def recover_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the wallet recovery process by asking for recovery method."""
    user_id = update.effective_user.id
    
    # Get active wallet name and PIN
    wallet_name = get_active_wallet_name(user_id)
    pin = pin_manager.get_pin(user_id)
    
    # Initialize user temp data
    user_temp_data[user_id] = {}
    
    # Check if user already has a wallet
    user_wallet = get_user_wallet(user_id, wallet_name, pin)
    warning_text = ""
    if user_wallet:
        warning_text = "⚠️ You already have a wallet. Recovering a different wallet will replace your current one.\n\n"
    
    # Create keyboard with recovery options
    keyboard = [
        [InlineKeyboardButton("Recover with Private Key", callback_data='recover_privatekey')],
        [InlineKeyboardButton("Recover with Seed Phrase", callback_data='recover_mnemonic')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"{warning_text}How would you like to recover your wallet?",
        reply_markup=reply_markup
    )
    
    return CHOOSING_RECOVERY_TYPE

async def recovery_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle recovery method choice."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    choice = query.data
    
    if choice == 'recover_privatekey':
        user_temp_data[user_id]['recovery_type'] = 'privatekey'
        await query.edit_message_text(
            "🔐 Please enter the private key of the wallet you want to recover.\n\n"
            "⚠️ WARNING: Never share your private key with anyone else!\n"
            "This bot stores your key encrypted, but you should still be careful."
        )
        return WAITING_FOR_PRIVATE_KEY
    
    elif choice == 'recover_mnemonic':
        user_temp_data[user_id]['recovery_type'] = 'mnemonic'
        await query.edit_message_text(
            "🔑 Please enter your seed phrase (mnemonic).\n\n"
            "This should be 12 or 24 words separated by spaces.\n\n"
            "⚠️ WARNING: Never share your seed phrase with anyone else!\n"
            "This bot stores it encrypted, but you should still be careful."
        )
        return WAITING_FOR_MNEMONIC
    
    return ConversationHandler.END

async def process_private_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the private key entered by the user and recover the wallet."""
    # Delete the user's message containing the private key for security
    try:
        await update.message.delete()
    except Exception:
        # Couldn't delete message, possibly due to permissions
        pass
    
    user_id = update.effective_user.id
    private_key = update.message.text.strip()
    
    # Ask for wallet name
    user_temp_data[user_id]['private_key'] = private_key
    await update.message.reply_text("Please enter a name for this wallet:")
    return ENTERING_WALLET_NAME

async def process_mnemonic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the mnemonic phrase entered by the user and recover the wallet."""
    # Delete the user's message containing the mnemonic for security
    try:
        await update.message.delete()
    except Exception:
        # Couldn't delete message, possibly due to permissions
        pass
    
    user_id = update.effective_user.id
    mnemonic = update.message.text.strip()
    
    # Store the mnemonic for later use
    user_temp_data[user_id]['mnemonic'] = mnemonic
    
    # Ask for wallet name
    await update.message.reply_text("Please enter a name for this wallet:")
    return ENTERING_WALLET_NAME

async def process_wallet_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the wallet name and finalize wallet recovery."""
    user_id = update.effective_user.id
    wallet_name = update.message.text.strip()
    
    # Check if user has temp data
    if user_id not in user_temp_data:
        await update.message.reply_text("Something went wrong. Please try again with /recover.")
        return ConversationHandler.END
    
    # Check if name is valid
    if not wallet_name or len(wallet_name) > 32:
        await update.message.reply_text("Wallet name must be between 1 and 32 characters. Please try again:")
        return ENTERING_WALLET_NAME
    
    # Check if wallet with this name already exists
    existing_wallets = get_user_wallets(user_id, pin_manager.get_pin(user_id))
    if wallet_name in existing_wallets:
        await update.message.reply_text(f"A wallet with name '{wallet_name}' already exists. Please choose a different name:")
        return ENTERING_WALLET_NAME
    
    recovery_type = user_temp_data[user_id]['recovery_type']
    
    try:
        recovered_wallet = None
        
        # Process based on recovery type
        if recovery_type == 'privatekey':
            private_key = user_temp_data[user_id]['private_key']
            
            # Handle '0x' prefix for private key
            if not private_key.startswith('0x'):
                private_key = '0x' + private_key
            
            # Create account from private key
            account = Account.from_key(private_key)
            
            # Create wallet object
            recovered_wallet = {
                'address': account.address,
                'private_key': private_key
            }
        
        elif recovery_type == 'mnemonic':
            mnemonic = user_temp_data[user_id]['mnemonic']
            
            # Create wallet from mnemonic
            full_wallet = wallet.create_mnemonic_wallet(mnemonic)
            
            # Remove mnemonic from wallet object before saving
            recovered_wallet = {
                'address': full_wallet['address'],
                'private_key': full_wallet['private_key'],
                'path': full_wallet['path']
            }
            
            # Save mnemonic separately
            save_user_mnemonic(user_id, mnemonic, pin_manager.get_pin(user_id))
        
        # Save the wallet
        save_user_wallet(user_id, recovered_wallet, wallet_name, pin_manager.get_pin(user_id))
        
        # Clean up sensitive data
        del user_temp_data[user_id]
        
        # Show success message with appropriate details based on recovery type
        if recovery_type == 'privatekey':
            await update.message.reply_text(
                f"✅ Wallet successfully recovered and saved as '{wallet_name}'!\n\n"
                f"Address: `{recovered_wallet['address']}`\n\n"
                "You can now use this wallet for transactions.",
                parse_mode='Markdown'
            )
        else:  # mnemonic
            await update.message.reply_text(
                f"✅ Wallet successfully recovered from seed phrase and saved as '{wallet_name}'!\n\n"
                f"Address: `{recovered_wallet['address']}`\n\n"
                "You can now use this wallet for transactions.",
                parse_mode='Markdown'
            )
        
    except ValueError as e:
        error_message = str(e)
        if 'Invalid mnemonic' in error_message:
            await update.message.reply_text(
                "❌ Invalid seed phrase. Please make sure you've entered the correct 12 or 24 words in the right order.\n\n"
                "Use /recover to try again."
            )
        else:
            await update.message.reply_text(
                f"❌ Error recovering wallet: {error_message}\n\n"
                "Please check your input and try again with /recover."
            )
        
        # Clean up temp data on error
        if user_id in user_temp_data:
            del user_temp_data[user_id]
            
    except Exception as e:
        # Log the error
        logger.error(f"Wallet recovery error: {str(e)}")
        
        # User-friendly error message
        await update.message.reply_text(
            "❌ Something went wrong while recovering your wallet.\n\n"
            f"Error: {str(e)}\n\n"
            "Please try again with /recover."
        )
        
        # Clean up temp data on error
        if user_id in user_temp_data:
            del user_temp_data[user_id]
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the current operation and end the conversation."""
    user_id = update.effective_user.id
    
    # Clean up any temporary data
    if user_id in user_temp_data:
        del user_temp_data[user_id]
    
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END 

# Create a PIN-protected version of the command
pin_protected_recover = require_pin(
    "🔒 Wallet recovery requires PIN verification.\nPlease enter your PIN:"
)(recover_command) 