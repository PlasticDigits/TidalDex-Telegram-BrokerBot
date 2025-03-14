"""
Command to export the private key for the currently selected wallet.
This is useful for moving a single wallet to another wallet software.
"""
from telegram import Update
from telegram.ext import ContextTypes
from typing import Optional, Dict, Any, Callable, Union
import logging
import traceback
from utils.self_destruction_message import send_self_destructing_message
from services.pin import require_pin, pin_manager
from services.wallet import wallet_manager
from db.wallet import WalletData
# Enable logging
logger = logging.getLogger(__name__)

async def export_key_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Export the private key for the currently selected wallet.
    This works for both mnemonic-derived wallets and imported private key wallets.
    """
    if update.effective_user is None:
        logger.error("No effective user in update")
        return
        
    # Get the user ID as an integer (native type from Telegram)
    user_id_int: int = update.effective_user.id
    # For wallet manager, we need the user ID as a string
    user_id_str: str = str(user_id_int)
    
    logger.info(f"Export key command called by user {user_id_int}")
    
    try:
        # Get PIN from PINManager - needs integer user_id
        pin: Optional[str] = pin_manager.get_pin(user_id_int)

        # Wallet manager methods need string user_id
        wallet_name: Optional[str] = wallet_manager.get_active_wallet_name(user_id_str)
        user_wallet: Optional[WalletData] = wallet_manager.get_user_wallet(user_id_str, wallet_name, pin)
        
        if update.message is None:
            logger.error(f"No message in update for user {user_id_int}")
            return
            
        if not user_wallet:
            await update.message.reply_text("You don't have a wallet yet. Use /wallet to create one.")
            return
        
        # Check if we have a private key
        if not user_wallet.get('private_key'):
            await update.message.reply_text(
                "No private key found for your wallet. This may be due to:\n"
                "• Your wallet was created externally\n"
                "• There was an error during wallet creation\n\n"
                "Try importing a new wallet with /recover."
            )
            return
        
        # We have the private key, display it with security warnings
        private_key: Union[str, None] = user_wallet.get('private_key', None)
        address: Union[str, None] = user_wallet.get('address', None)

        if private_key is None:
            await update.message.reply_text(
                "No private key found for your wallet. This may be due to:\n"
                "• There was an error during wallet creation\n\n"
                "Try importing a new wallet with /recover."
            )
            return
        
        if address is None:
            await update.message.reply_text(
                "No address found for your wallet. This may be due to:\n"
                "• There was an error during wallet creation\n\n"
                "Try importing a new wallet with /recover."
            )
            return
        
        # Use self-destructing message for security
        await send_self_destructing_message(
            update,
            context,
            f"⚠️ *PRIVATE KEY EXPORT* ⚠️\n\n"
            f"Wallet: *{wallet_name}*\n"
            f"Address: `{address}`\n\n"
            f"Private Key: `{private_key}`\n\n"
            "⚠️ *WARNING* ⚠️\n"
            "• Never share this private key with anyone\n"
            "• Never enter it on any website\n"
            "• Anyone with this key has full access to your funds\n\n"
            "This message will self-destruct for your security.",
            parse_mode='Markdown'
        )
        logger.info(f"Private key successfully displayed to user {user_id_int}")
        
    except Exception as e:
        logger.error(f"Error in export_key_command: {e}")
        logger.error(traceback.format_exc())
        if update.message is not None:
            await update.message.reply_text(
                "❌ An error occurred while exporting your private key. Please try again later."
            )

# Create a PIN-protected version of the command
pin_protected_export_key: Callable[[Update, ContextTypes.DEFAULT_TYPE], Any] = require_pin(
    "🔒 This command requires your PIN for security.\nPlease enter your PIN:"
)(export_key_command) 