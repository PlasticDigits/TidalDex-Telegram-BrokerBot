from telegram import Update
from telegram.ext import ContextTypes
import db
import logging
import traceback

# Enable logging
logger = logging.getLogger(__name__)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help information."""
    user_id = update.effective_user.id
    has_wallet = db.get_user_wallet(user_id) is not None
    
    # Use plain text without Markdown for safer rendering
    help_text = (
        "🤖 BSC Wallet Bot Commands\n\n"
        
        "Wallet Management:\n"
        "/wallet - Show all wallets and active wallet info\n"
        "/wallets - List all wallets and switch between them\n"
        "/addwallet - Add a new wallet (create or import)\n"
        "/rename_wallet - Rename your currently active wallet\n"
        "/backup - Backup your active wallet's seed phrase\n"
        "/export_key - Export private key of your active wallet\n"
        "/recover - Recover a wallet using a private key\n\n"
        
        "Security:\n"
        "/set_pin - Set or change your security PIN\n\n"
        
        "Transactions:\n"
        "/balance - Check BNB and token balances\n"
        "/send - Send BNB or tokens\n"
        "/receive - Show your wallet address for receiving funds\n\n"
        
        "Other:\n"
        "/help - Show this help message\n"
        "/start - Start or restart the bot\n"
        "/cancel - Cancel the current operation\n\n"
        
        "Security Tips:\n"
        "• Never share your private keys or seed phrases\n"
        "• Set a PIN for additional security\n"
        "• Always backup your wallet private keys\n"
        "• Double-check addresses when sending funds\n"
        "• This bot encrypts your private keys but still use at your own risk"
    )
    
    if not has_wallet:
        help_text += "\n\n💡 You don't have a wallet yet. Use /wallet to create one."
    
    # Send without parse_mode to avoid Markdown parsing issues
    await update.message.reply_text(help_text)

async def universal_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help information, even in group chats."""
    # Use plain text without Markdown for safer rendering
    help_text = (
        "🤖 BSC Wallet Bot Commands\n\n"
        
        "Wallet Management:\n"
        "/wallet - Show all wallets and active wallet info\n"
        "/wallets - List all wallets and switch between them\n"
        "/addwallet - Add a new wallet (create or import)\n"
        "/rename_wallet - Rename your currently active wallet\n"
        "/backup - Backup your active wallet's seed phrase\n"
        "/export_key - Export private key of your active wallet\n"
        "/recover - Recover a wallet using a private key\n\n"
        
        "Security:\n"
        "/set_pin - Set or change your security PIN\n\n"
        
        "Transactions:\n"
        "/balance - Check BNB and token balances\n"
        "/send - Send BNB or tokens\n"
        "/receive - Show your wallet address for receiving funds\n\n"
        
        "Other:\n"
        "/help - Show this help message\n"
        "/start - Start or restart the bot\n"
        "/cancel - Cancel the current operation\n\n"
        
        "⚠️ For security, use this bot in a private chat only."
    )
    
    # Send without parse_mode to avoid Markdown parsing issues
    await update.message.reply_text(help_text) 