from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import ContextTypes, ConversationHandler, ExtBot
import logging
import traceback
import re
from typing import Dict, List, Any, Optional, Union, Callable, cast, Coroutine
from utils.self_destruction_message import send_self_destructing_message
from services.pin import require_pin, pin_manager
from services.wallet import wallet_manager
from db.wallet import WalletData
from services.pin.pin_decorators import conversation_pin_helper
from db.utils import hash_user_id

# Enable logging
logger = logging.getLogger(__name__)

# Conversation states
CHOOSING_ACTION, ENTERING_NAME, ENTERING_PRIVATE_KEY = range(3)

# Input validation constants
MAX_WALLET_NAME_LENGTH: int = 32
MIN_WALLET_NAME_LENGTH: int = 1
MAX_PRIVATE_KEY_LENGTH: int = 130  # Private keys are 64 hex chars, plus optional '0x' prefix, allow some buffer

# Store temporary data during conversation
user_temp_data: Dict[int, Dict[str, Any]] = {}

async def addwallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the process to add a new wallet."""
    if update.message is None:
        logger.error("Update message is None in addwallet_command")
        return ConversationHandler.END
    
    if update.effective_user is None:
        logger.error("Effective user is None in addwallet_command")
        return ConversationHandler.END
    
    helper_result: Optional[int] = await conversation_pin_helper('addwallet_command', context, update, "Adding a wallet requires your PIN for security. Please enter your PIN.")
    if helper_result is not None:
        return helper_result
        
    keyboard: List[List[InlineKeyboardButton]] = [
        [InlineKeyboardButton("Create New Wallet", callback_data='addwallet_create')],
        [InlineKeyboardButton("Import Existing Wallet", callback_data='addwallet_import')],
        [InlineKeyboardButton("Cancel", callback_data='addwallet_cancel')]
    ]
    reply_markup: InlineKeyboardMarkup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "How would you like to add a wallet?", 
        reply_markup=reply_markup
    )

    return CHOOSING_ACTION

async def action_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle wallet creation method choice."""
    logger.info("Received callback query from user")
    query = update.callback_query
    if query is None:
        logger.error("Callback query is None in action_choice_callback")
        return ConversationHandler.END
        
    await query.answer()

    if query.data == 'addwallet_cancel':
        await query.edit_message_text("Operation cancelled.")
        return ConversationHandler.END

    logger.info("Answered callback query")
    
    if update.effective_user is None:
        logger.error("Effective user is None in action_choice_callback")
        return ConversationHandler.END
        
    user_id: int = update.effective_user.id
    
    if query.data is None:
        logger.error("Callback query data is None in action_choice_callback")
        await query.edit_message_text("Something went wrong. Please try again with /addwallet.")
        return ConversationHandler.END
        
    choice: str = query.data
    logger.info(f"User {hash_user_id(user_id)} chose {choice}")
    # Initialize user temp data
    user_temp_data[user_id] = {'action': choice}
    logger.info(f"User temp data initialized for user {hash_user_id(user_id)}")

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
    if update.effective_user is None:
        logger.error("Effective user is None in process_wallet_name")
        return ConversationHandler.END
        
    user_id: int = update.effective_user.id
    
    if update.message is None:
        logger.error("Update message is None in process_wallet_name")
        return ConversationHandler.END
        
    message_text = update.message.text
    if message_text is None:
        logger.error("Message text is None in process_wallet_name")
        return ConversationHandler.END
        
    wallet_name: str = message_text.strip()
    
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
    if wallet_name != message_text:
        await update.message.reply_text("Wallet name cannot have leading or trailing spaces. Please try again:")
        return ENTERING_NAME
    
    # Check for reserved names
    reserved_names: List[str] = ["default", "wallet", "main", "primary", "backup", "test", "admin", "system"]
    if wallet_name.lower() in reserved_names:
        await update.message.reply_text(f"'{wallet_name}' is a reserved name and cannot be used. Please choose a different name:")
        return ENTERING_NAME
    
    #get pin
    pin: Optional[str] = pin_manager.get_pin(user_id)
    
    # Check if wallet with this name already exists
    user_id_str = str(user_id)
    existing_wallets = wallet_manager.get_user_wallets(user_id_str, pin=pin)
    if isinstance(existing_wallets, dict) and wallet_name in existing_wallets:
        await update.message.reply_text(f"A wallet with name '{wallet_name}' already exists. Please choose a different name:")
        return ENTERING_NAME
    
    # Store wallet name
    user_temp_data[user_id]['wallet_name'] = wallet_name

    
    # Process based on action
    if user_temp_data[user_id]['action'] == 'addwallet_create':
        try:
            # Check if user already has a mnemonic
            has_mnemonic: bool = wallet_manager.has_user_mnemonic(user_id_str, pin=pin)
            
            if has_mnemonic:
                # User already has a mnemonic, derive wallet with next index
                logger.debug("User has existing mnemonic, deriving new wallet")
                mnemonic: Optional[str] = wallet_manager.get_user_mnemonic(user_id_str, pin=pin)
                
                # Derive a new wallet from the existing mnemonic
                new_wallet = wallet_manager.create_wallet(user_id_str, wallet_name, pin=pin)
                
                if new_wallet is None:
                    raise Exception("Failed to create wallet")
                
                # Normal message since no seed phrase is shown
                # Do not need to show path, since we are using the standard BSC/ETH path
                await update.message.reply_text(
                    f"🎉 New wallet '{wallet_name}' created from your existing seed phrase!\n\n"
                    f"Address: `{new_wallet['address']}`\n\n"
                    "Use /switch to switch to this wallet. Use /addwallet to create add new wallets.\n\n"
                    "This wallet is derived from your existing seed phrase, which you can recover using /backup.",
                    parse_mode='Markdown'
                )
                return ConversationHandler.END
            else:
                # User doesn't have a mnemonic, create a new one
                logger.debug("User has no mnemonic, creating new one")
                               
                # Create a new mnemonic
                wallet_manager.create_mnemonic(user_id_str, pin=pin)

                # Create a new wallet from the mnemonic
                created_wallet = wallet_manager.create_wallet(user_id_str, wallet_name, pin=pin)
                
                if created_wallet is None:
                    raise Exception("Failed to create wallet")
                
                # Send self-destructing message with seed phrase
                # Note: This will first show a security warning with a button
                # that the user must click to see the sensitive information
                await update.message.reply_text(
                    f"🎉 New wallet '{wallet_name}' created with new seed phrase!\n\n"
                    f"Address: `{created_wallet['address']}`\n\n"
                    "Use /switch to switch to this wallet. Use /addwallet to create add new wallets.\n\n"
                    "This wallet is derived from your existing seed phrase, which you can recover using /backup.",
                    parse_mode='Markdown'
                )
                return ConversationHandler.END
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
    return ConversationHandler.END

async def process_private_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the private key for wallet import."""
    if update.effective_user is None:
        logger.error("Effective user is None in process_private_key")
        return ConversationHandler.END
        
    user_id: int = update.effective_user.id
    
    if update.message is None:
        logger.error("Update message is None in process_private_key")
        return ConversationHandler.END
        
    message_text = update.message.text
    if message_text is None:
        logger.error("Message text is None in process_private_key")
        return ConversationHandler.END
        
    private_key: str = message_text.strip()
    pin: Optional[str] = pin_manager.get_pin(user_id)
    
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
        if update.effective_chat is None:
            logger.error("Effective chat is None in process_private_key")
            return ConversationHandler.END
            
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Something went wrong. Please try again with /addwallet."
        )
        return ConversationHandler.END
    
    wallet_name: str = user_temp_data[user_id]['wallet_name']
    
    # Basic format validation
    if not re.match(r'^(0x)?[0-9a-fA-F]{64}$', private_key):
        if update.effective_chat is None:
            logger.error("Effective chat is None in process_private_key")
            return ConversationHandler.END
            
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
        address: str = account.address
        
        # Create wallet object
        imported_wallet: WalletData = {
            'address': address,
            'private_key': private_key,
            'name': wallet_name,
            'is_active': False,
            'imported': True
        }
        
        user_id_str = str(user_id)
        
        # Save the wallet
        wallet_manager.save_user_wallet(user_id_str, imported_wallet, wallet_name, pin=pin)
        
        if update.effective_chat is None:
            logger.error("Effective chat is None in process_private_key")
            return ConversationHandler.END
            
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"✅ Wallet '{wallet_name}' imported successfully!\n\n"
                 f"Address: `{address}`\n\n"
                 "Your wallet has been encrypted and stored securely.",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error importing wallet: {e}")
        if update.effective_chat is None:
            logger.error("Effective chat is None in process_private_key error handler")
            return ConversationHandler.END
            
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ Error importing wallet: Invalid private key. Please try again with /addwallet."
        )
    
    # Clean up temp data
    del user_temp_data[user_id]
    return ConversationHandler.END