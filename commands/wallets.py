from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, Message, User
from telegram.ext import ContextTypes, ConversationHandler
from services.wallet import wallet_manager
from services.pin import pin_manager
import logging
from typing import Dict, List, Any, Optional, cast
from db.wallet import WalletData
from services.pin.pin_decorators import conversation_pin_helper
from db.utils import hash_user_id, test_secure_encryption

# Configure module logger
logger = logging.getLogger(__name__)

# Define conversation state
SELECTING_WALLET = 1

def escape_markdown_v2(text: str) -> str:
    """Escape special characters for MarkdownV2 formatting."""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text

async def wallets_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """List all wallets and allow switching between them."""
    user = update.effective_user
    if user is None:
        logger.error("User is None in wallets_command")
        return ConversationHandler.END
    
    helper_result: Optional[int] = await conversation_pin_helper('wallets_command', context, update, "Viewing wallets requires your PIN for security. Please enter your PIN.")
    if helper_result is not None:
        return helper_result
    
    user_id: int = user.id
    user_id_str: str = str(user_id)
    pin: Optional[str] = pin_manager.get_pin(user_id)
    
    # Test secure encryption
    if not test_secure_encryption(user_id, pin):
        logger.error(f"❌ Secure encryption test FAILED for user {hash_user_id(user_id)}")
    
    # Get the current active wallet name
    active_wallet_name: Optional[str] = wallet_manager.get_active_wallet_name(user_id_str)
    
    # Get all wallets for the user
    user_wallets: Dict[str, WalletData] = wallet_manager.get_user_wallets(user_id_str, False, pin)
    
    message = update.message
    if message is None:
        logger.error("Message is None in wallets_command")
        return ConversationHandler.END
        
    if not user_wallets:
        await message.reply_text(
            "You don't have any wallets. Use /wallet to create one."
        )
        return ConversationHandler.END
    
    # Create a keyboard with all wallets
    keyboard: List[List[InlineKeyboardButton]] = []
    for wallet_name, wallet_data in user_wallets.items():
        logger.info(f"Wallet: {wallet_name}")
        is_active: bool = wallet_data.get('is_active', False)
        active_marker: str = "✅ " if is_active else ""
        
        # Limit the displayed address to first and last few characters
        address: str = wallet_data.get('address', '') or ''
        if not address:
            address = "Unable to decrypt"
        elif len(address) > 15:
            address = f"{address[:8]}...{address[-6:]}"
        
        label: str = f"{active_marker}{wallet_name} ({address})"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"wallets_select:{wallet_name}")])

    # Add a cancel button
    keyboard.append([InlineKeyboardButton("Cancel", callback_data="wallets_select_cancel")])
    
    # Send the message with the inline keyboard
    await message.reply_text(
        f"You have {len(user_wallets)} wallet(s).\n"
        f"Use /addwallet to create a new wallet.\n\n"
        f"Select a wallet to make it active:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    
    return SELECTING_WALLET

async def wallet_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process wallet selection."""
    query = update.callback_query
    if query is None:
        logger.error("Query is None in wallet_selection_callback")
        return ConversationHandler.END
        
    await query.answer()
    
    user = update.effective_user
    if user is None:
        logger.error("User is None in wallet_selection_callback")
        return ConversationHandler.END
        
    user_id: int = user.id
    user_id_str: str = str(user_id)
    pin: Optional[str] = pin_manager.get_pin(user_id)
    
    # Extract the selected wallet name from callback data
    callback_data = query.data
    if callback_data is None:
        logger.error("Callback data is None in wallet_selection_callback")
        return ConversationHandler.END
    
    if callback_data == "wallets_select_cancel":
        await query.edit_message_text("Wallet selection canceled.")
        return ConversationHandler.END
    
    # Format: "wallets_select:WalletName"
    selected_wallet_name: str = callback_data.split(":", 1)[1]
    
    # Verify the wallet exists
    wallet: Optional[WalletData] = wallet_manager.get_user_wallet(user_id_str, selected_wallet_name, pin)
    
    if not wallet:
        await query.edit_message_text(f"Error: Wallet '{selected_wallet_name}' not found.")
        return ConversationHandler.END
    
    # Set the wallet as active
    success: bool = wallet_manager.set_active_wallet(user_id_str, selected_wallet_name)
    
    if success:
        address: str = wallet.get('address', '') or ''
        
        if not address:
            escaped_wallet_name = escape_markdown_v2(selected_wallet_name)
            await query.edit_message_text(
                f"✅ Wallet '{escaped_wallet_name}' is now active\\.\n\n"
                f"⚠️ **Address Decryption Issue**: Unable to decrypt wallet address\\. Please contact support\\.\n\n"
                f"Use /wallet to see details, /addwallet to add a new wallet\\.\n\n"
                f"🔐 **Security**\n"
                f"• Use /set\\_pin to set or change a PIN for your wallet\n"
                f"• Use /backup to save your recovery phrase\n",
                parse_mode='MarkdownV2'
            )
        else:
            # Escape special characters for MarkdownV2
            escaped_wallet_name = escape_markdown_v2(selected_wallet_name)
            escaped_address = escape_markdown_v2(address)
            
            await query.edit_message_text(
                f"✅ Wallet '{escaped_wallet_name}' is now active\\.\n\n"
                f"Address: `{escaped_address}`\n\n"
                f"Use /wallet to see details, /addwallet to add a new wallet, /receive to receive funds, /balance to check your balances, or /send to send funds\\.\n\n"
                f"Use /swap to trade BNB or tokens\\.\n\n"
                f"🔐 **Security**\n"
                f"• Use /set\\_pin to set or change a PIN for your wallet\n"
                f"• Use /backup to save your recovery phrase\n",
                parse_mode='MarkdownV2'
            )
    else:
        await query.edit_message_text(
            f"Error setting '{selected_wallet_name}' as active wallet. Please try again."
        )
    
    return ConversationHandler.END 