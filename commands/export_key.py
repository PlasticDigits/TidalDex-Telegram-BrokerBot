"""
Command to export the private key for the currently selected wallet.
This is useful for moving a single wallet to another wallet software.
"""
from telegram import Update
from telegram.ext import ContextTypes
from db.utils import hash_user_id
import db
from db.wallet import get_active_wallet_name
import logging
import traceback
from utils.self_destruction_message import send_self_destructing_message
from services.pin import require_pin, pin_manager

# Enable logging
logger = logging.getLogger(__name__)

async def export_key_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Export the private key for the currently selected wallet.
    This works for both mnemonic-derived wallets and imported private key wallets.
    """
    user_id = update.effective_user.id
    logger.info(f"Export key command called by user {user_id}")
    
    try:
        # Get PIN from PINManager
        pin = pin_manager.get_pin(user_id)
        
        # Get the active wallet name
        wallet_name = get_active_wallet_name(user_id)
        
        # Get user wallet with PIN if available
        user_wallet = db.get_user_wallet(user_id, wallet_name, pin)
        
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
        private_key = user_wallet.get('private_key')
        address = user_wallet.get('address')
        
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
        logger.info(f"Private key successfully displayed to user {user_id}")
        
    except Exception as e:
        logger.error(f"Error in export_key_command: {e}")
        logger.error(traceback.format_exc())
        await update.message.reply_text(
            "❌ An error occurred while exporting your private key. Please try again later."
        )

# Create a PIN-protected version of the command
pin_protected_export_key = require_pin(
    "🔒 This command requires your PIN for security.\nPlease enter your PIN:"
)(export_key_command) 