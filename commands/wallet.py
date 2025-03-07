"""
Wallet management commands.
"""
from telegram import Update
from telegram.ext import ContextTypes
from db.utils import hash_user_id
import db
import logging
import traceback
from wallet.mnemonic import derive_wallet_from_mnemonic, create_mnemonic
from services.pin import require_pin, pin_manager

# Enable logging
logger = logging.getLogger(__name__)

async def wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show active wallet information and a summary of all wallets."""
    user_id = update.effective_user.id
    logger.info(f"Wallet command called by user {user_id}")
    
    try:
        # Get PIN from PINManager
        pin = pin_manager.get_pin(user_id)
        
        # Check if user already has a wallet
        logger.debug(f"Checking if user {user_id} has an existing wallet")
        user_wallet = db.get_user_wallet(user_id, pin=pin)
        logger.debug(f"User wallet result: {user_wallet is not None}")
        
        # Get all wallets for the user
        all_wallets = db.get_user_wallets(user_id)
        wallet_count = len(all_wallets) if all_wallets else 0
        
        if not user_wallet:
            # No wallet found, generate a new one
            logger.info(f"No wallet found for user {user_id}, creating a new wallet")
            
            # First, generate a new mnemonic
            mnemonic = create_mnemonic()
            logger.debug(f"New mnemonic generated for user {user_id}")
            
            # Now derive a wallet from this mnemonic
            wallet_info = derive_wallet_from_mnemonic(mnemonic, index=0)
            
            if not wallet_info:
                logger.error(f"Failed to generate wallet for user {user_id}")
                await update.message.reply_text(
                    "❌ Failed to create a wallet. Please try again later."
                )
                return
            
            # Save the mnemonic and wallet to the database, with PIN if provided
            db.save_user_mnemonic(user_id, mnemonic, pin)
            db.save_user_wallet(user_id, wallet_info, "Default", pin)
            
            # Get the saved wallet
            user_wallet = db.get_user_wallet(user_id, pin)
            
            # Show welcome message
            await update.message.reply_text(
                "🎉 Your new wallet has been created!\n\n"
                f"Address: `{wallet_info['address']}`\n\n"
                "Remember to back up your recovery phrase with /backup\n"
                "Use /send to send tokens and /receive to receive tokens",
                parse_mode='Markdown'
            )
            
            logger.info(f"New wallet created for user {user_id}")
            return
        
        # We have a wallet with decrypted data
        wallet_name = user_wallet.get('name', 'Default')
        address = user_wallet.get('address')
        
        # Format the wallet info message
        message = f"💼 *Wallet: {wallet_name}*\n\n"
        message += f"🔑 Address: `{address}`\n\n"
        
        # Add total wallet count if user has multiple wallets
        if wallet_count > 1:
            message += f"You have {wallet_count} wallets. Use /wallets to view and switch between them.\n\n"
        
        # Add helpful commands
        message += "Commands:\n"
        message += "• /send - Send tokens\n"
        message += "• /receive - Show address to receive tokens\n"
        message += "• /balance - Check your balance\n"
        message += "• /backup - Show recovery phrase\n"
        
        if wallet_count > 1:
            message += "• /wallets - Manage multiple wallets\n"
        else:
            message += "• /addwallet - Add another wallet\n"
        
        await update.message.reply_text(
            message,
            parse_mode='Markdown'
        )
        
        logger.info(f"Wallet info displayed for user {user_id}")
        
    except Exception as e:
        logger.error(f"Error in wallet_command: {e}")
        logger.error(traceback.format_exc())
        await update.message.reply_text(
            "❌ An error occurred while retrieving your wallet information. Please try again later."
        )

# Create a PIN-protected version of the command
pin_protected_wallet = require_pin(
    "🔒 Your wallet information requires PIN verification.\nPlease enter your PIN:"
)(wallet_command) 