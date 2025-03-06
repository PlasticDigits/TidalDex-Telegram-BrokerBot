"""
Wallet recovery and backup commands.
Provides functionality to restore a wallet from a private key and backup existing wallet.
"""
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
import db
from wallet.utils import validate_address
from eth_account import Account
import logging

# Enable logging
logger = logging.getLogger(__name__)

# Conversation states
WAITING_FOR_PRIVATE_KEY = 0

async def recover_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the wallet recovery process by asking for a private key."""
     
    user_id = update.effective_user.id
    
    # Check if user already has a wallet
    user_wallet = db.get_user_wallet(user_id)
    if user_wallet:
        await update.message.reply_text(
            "⚠️ You already have a wallet. Recovering a different wallet will replace your current one.\n\n"
            "If you want to continue, please enter your private key now.\n\n"
            "Or use /cancel to abort this operation."
        )
    else:
        await update.message.reply_text(
            "🔐 Please enter the private key of the wallet you want to recover.\n\n"
            "⚠️ WARNING: Never share your private key with anyone else!\n"
            "This bot stores your key encrypted, but you should still be careful."
        )
        
    return WAITING_FOR_PRIVATE_KEY

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
    
    # Initial response
    response = await update.message.reply_text("🔄 Attempting to recover wallet... ⏳")
    
    try:
        # Attempt to create an account from the private key
        account = Account.from_key(private_key)
        wallet_address = account.address
        
        # Validate the address
        checksum_address = validate_address(wallet_address)
        
        # Create wallet dictionary
        recovered_wallet = {
            'address': checksum_address,
            'private_key': private_key
        }
        
        # Save to database
        db.save_user_wallet(user_id, recovered_wallet)
        
        # Success message with only partial key shown for security
        masked_key = f"{private_key[:6]}...{private_key[-4:]}"
        await response.edit_text(
            "✅ Wallet successfully recovered!\n\n"
            f"Address: `{checksum_address}`\n\n"
            f"Your private key (partially hidden): `{masked_key}`\n\n"
            "Use /balance to check your wallet balances.",
            parse_mode='Markdown'
        )
        
        logger.info(f"User {user_id} successfully recovered wallet with address {checksum_address}")
    except Exception as e:
        logger.error(f"Error recovering wallet: {e}")
        await response.edit_text(
            "❌ Failed to recover wallet. The private key you provided may be invalid.\n\n"
            "Please try again with a valid private key or use /wallet to create a new wallet."
        )
    
    return ConversationHandler.END

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Provide a backup of the user's wallet private key."""
    # Check if this is a private chat
    if update.effective_chat.type != 'private':
        await update.message.reply_text(
            "⚠️ For security reasons, this command can only be used in private chats. "
            "Please message me directly to backup your wallet."
        )
        return
    
    user_id = update.effective_user.id
    user_wallet = db.get_user_wallet(user_id)
    
    if not user_wallet:
        await update.message.reply_text("You don't have a wallet yet. Use /wallet to create one.")
        return
    
    address = user_wallet['address']
    private_key = user_wallet['private_key']
    
    # Send the private key with a security warning
    await update.message.reply_text(
        "🔐 WALLET BACKUP - KEEP SAFE 🔐\n\n"
        "⚠️ WARNING: Never share your private key with anyone! Anyone with this key can access your funds.\n\n"
        f"Address: `{address}`\n\n"
        f"Private Key: `{private_key}`\n\n"
        "🔒 To recover this wallet in the future, use the /recover command.",
        parse_mode='Markdown'
    )
    
    logger.info(f"User {user_id} backed up their wallet")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the recovery operation."""
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END 