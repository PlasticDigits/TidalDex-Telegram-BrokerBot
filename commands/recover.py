"""
Wallet recovery and backup commands.
Provides functionality to restore a wallet from a private key or mnemonic phrase, and backup existing wallet.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message, User
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, ConversationHandler
import logging
from typing import Dict, List, Any, Optional, Union, Callable, cast, Coroutine
from services.pin import require_pin, pin_manager
from services.wallet import wallet_manager
from db.wallet import WalletData
from services.pin.pin_decorators import conversation_pin_helper

# Enable logging
logger = logging.getLogger(__name__)

# Conversation states
CHOOSING_RECOVERY_TYPE, WAITING_FOR_MNEMONIC, ENTERING_WALLET_NAME = range(3)

# Store temporary data during conversation
user_temp_data: Dict[int, Dict[str, Any]] = {}

async def recover_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the wallet recovery process by asking for recovery method."""
    user = update.effective_user
    # Add null check for user
    if not user:
        logger.error("No user found in update")
        return ConversationHandler.END
        
    user_id: int = user.id
    
    helper_result: Optional[int] = await conversation_pin_helper('recover_command', context, update, "Wallet recovery requires your PIN for security. Please enter your PIN.")
    if helper_result is not None:
        return helper_result
    
    pin: Optional[str] = pin_manager.get_pin(user_id)
    
    # Get active wallet name - Convert user_id to string
    wallet_name: Optional[str] = wallet_manager.get_active_wallet_name(str(user_id))
    
    # Initialize user temp data
    user_temp_data[user_id] = {}
    
    # Check if user already has a wallet - Convert user_id to string
    user_wallet: Optional[WalletData] = wallet_manager.get_user_wallet(str(user_id), wallet_name, pin)
    warning_text: str = ""
    # warn user that if they already have a wallet, recovering will delete their existing wallets.
    # if they have a private key, they can use /addwallet instead.
    if user_wallet:
        warning_text = "⚠️ You already have a wallet. Recovering a different wallet will replace your current one.\n\n"
        warning_text += "If you have a private key, you can use /addwallet to add a new wallet.\n\n"
        warning_text += "ATTN: THIS WILL DELETE ALL YOUR WALLETS. Make sure you have a backup of your private keys.\n\n"
    
    # Create keyboard with recovery options
    keyboard: List[List[InlineKeyboardButton]] = [
        [InlineKeyboardButton("Recover with Seed Phrase", callback_data='recover_mnemonic')],
        [InlineKeyboardButton("Cancel", callback_data='recover_cancel')]
    ]
    reply_markup: InlineKeyboardMarkup = InlineKeyboardMarkup(keyboard)
    
    message = update.message
    if not message:
        logger.error("No message found in update")
        return ConversationHandler.END
        
    await message.reply_text(
        f"{warning_text}How would you like to recover your wallet?",
        reply_markup=reply_markup
    )
    
    return CHOOSING_RECOVERY_TYPE

async def recovery_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle recovery method choice."""
    query = update.callback_query
    if not query:
        logger.error("No callback query found in update")
        return ConversationHandler.END
        
    await query.answer()

    if query.data == 'recover_cancel':
        await query.edit_message_text("Operation cancelled.")
        return ConversationHandler.END
    
    user = update.effective_user
    if not user:
        logger.error("No user found in update")
        return ConversationHandler.END
        
    user_id: int = user.id
    query_data = query.data
    if not query_data:
        logger.error("No data found in callback query")
        return ConversationHandler.END
        
    choice: str = query_data
    
    if choice == 'recover_mnemonic':
        user_temp_data[user_id]['recovery_type'] = 'mnemonic'
        await query.edit_message_text(
            "🔑 Please enter your seed phrase (mnemonic).\n\n"
            "This should be 12 or 24 words separated by spaces.\n\n"
            "⚠️ WARNING: Never share your seed phrase with anyone else!\n"
            "This bot stores it encrypted, but you should still be careful."
        )
        return WAITING_FOR_MNEMONIC
    
    return ConversationHandler.END

async def process_mnemonic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the mnemonic phrase entered by the user and recover the wallet."""
    # Delete the user's message containing the mnemonic for security
    message = update.message
    if message:
        try:
            await message.delete()
        except Exception:
            # Couldn't delete message, possibly due to permissions
            pass
    
    user = update.effective_user
    if not user:
        logger.error("No user found in update")
        return ConversationHandler.END
        
    user_id: int = user.id
    
    # Check if message is available
    if not message or not message.text:
        await context.bot.send_message(
            chat_id=user_id,
            text="Invalid mnemonic format. Please try again or use /cancel to abort."
        )
        return WAITING_FOR_MNEMONIC
        
    mnemonic: str = message.text.strip()
    
    # Store the mnemonic for later use
    user_temp_data[user_id]['mnemonic'] = mnemonic
    
    # Ask for wallet name
    await message.reply_text("Please enter a name for this wallet:")
    return ENTERING_WALLET_NAME

async def process_wallet_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the wallet name and finalize wallet recovery."""
    user = update.effective_user
    if not user:
        logger.error("No user found in update")
        return ConversationHandler.END
        
    user_id: int = user.id
    
    # Check if message is available
    message = update.message
    if not message or not message.text:
        await context.bot.send_message(
            chat_id=user_id,
            text="Invalid wallet name. Please try again or use /cancel to abort."
        )
        return ENTERING_WALLET_NAME
        
    wallet_name: str = message.text.strip()

    pin: Optional[str] = pin_manager.get_pin(user_id)
    
    # Check if user has temp data
    if user_id not in user_temp_data:
        await message.reply_text("Something went wrong. Please try again with /recover.")
        return ConversationHandler.END
    
    # Check if name is valid
    if not wallet_name or len(wallet_name) > 32:
        await message.reply_text("Wallet name must be between 1 and 32 characters. Please try again:")
        return ENTERING_WALLET_NAME
    
    # Check if wallet with this name already exists - Convert user_id to string
    user_wallets_dict = wallet_manager.get_user_wallets(str(user_id), pin=pin)
    existing_wallets: Dict[str, WalletData] = {}
    
    # Handle the potential Union type
    if isinstance(user_wallets_dict, dict):
        existing_wallets = user_wallets_dict
    
    if wallet_name in existing_wallets:
        await message.reply_text(f"A wallet with name '{wallet_name}' already exists. Please choose a different name:")
        return ENTERING_WALLET_NAME
    
    recovery_type: str = user_temp_data[user_id]['recovery_type']
    
    try:
        
        if recovery_type == 'mnemonic':

            mnemonic: str = user_temp_data[user_id]['mnemonic']

            # Convert user_id to string
            wallet_manager.save_user_mnemonic(str(user_id), mnemonic, pin)

            # Convert user_id to string
            wallet_data = wallet_manager.create_wallet(str(user_id), wallet_name, pin)
            if not wallet_data:
                raise ValueError("Failed to create wallet")
                
            wallet: WalletData = wallet_data
                
        # Clean up sensitive data
        del user_temp_data[user_id]

        if recovery_type == 'mnemonic':
            await message.reply_text(
                f"✅ Wallet successfully recovered from seed phrase and saved as '{wallet_name}'!\n\n"
                f"Address: `{wallet['address']}`\n\n"
                "You can now use this wallet for transactions.",
                parse_mode=ParseMode.MARKDOWN
            )
        
    except ValueError as e:
        error_message: str = str(e)
        if 'Invalid mnemonic' in error_message:
            await message.reply_text(
                "❌ Invalid seed phrase. Please make sure you've entered the correct 12 or 24 words in the right order.\n\n"
                "Use /recover to try again."
            )
        else:
            await message.reply_text(
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
        await message.reply_text(
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
    user = update.effective_user
    if not user:
        logger.error("No user found in update")
        return ConversationHandler.END
        
    user_id: int = user.id
    
    # Clean up any temporary data
    if user_id in user_temp_data:
        del user_temp_data[user_id]
    
    message = update.message
    if not message:
        logger.error("No message found in update")
        return ConversationHandler.END
        
    await message.reply_text("Operation cancelled.")
    return ConversationHandler.END