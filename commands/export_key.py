"""
Command to export the private key for the currently selected wallet.
This is useful for moving a single wallet to another wallet software.
"""
from telegram import Update
from telegram.ext import ContextTypes
import db
import logging
import traceback
from utils.message_security import send_self_destructing_message

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
        # Check if user has a wallet
        user_wallet = db.get_user_wallet(user_id)
        
        if not user_wallet:
            logger.debug(f"User {user_id} has no wallet to export")
            await update.message.reply_text(
                "❌ You don't have a wallet yet. Use /wallet to create one."
            )
            return
        
        # Check if the wallet has a private key
        if 'private_key' not in user_wallet or not user_wallet['private_key']:
            logger.warning(f"Wallet for user {user_id} does not have a private key")
            await update.message.reply_text(
                "❌ Could not find the private key for your wallet. "
                "Please contact support."
            )
            return
        
        # Get wallet name 
        wallet_name = user_wallet.get('name', 'Default')
        
        # Send the private key to the user with self-destruct timer
        message_text = (
            f"🔑 Private Key for wallet '{wallet_name}':\n\n"
            f"Address: `{user_wallet['address']}`\n\n"
            f"Private Key: `{user_wallet['private_key']}`\n\n"
            "⚠️ IMPORTANT: Never share your private key with anyone. "
            "Anyone with access to your private key has full control of your wallet.\n\n"
            "This private key only controls this specific wallet address. "
            "If you have a seed phrase wallet, other addresses derived from the same seed "
            "will have different private keys."
        )
        
        await send_self_destructing_message(
            update,
            message_text,
            parse_mode='Markdown'
        )
        
        logger.info(f"Private key successfully exported for user {user_id}")
        
    except Exception as e:
        logger.error(f"Error in export_key command: {e}")
        logger.error(traceback.format_exc())
        
        await update.message.reply_text(
            "❌ An error occurred while exporting your private key.\n"
            "Please try again later or contact support."
        ) 