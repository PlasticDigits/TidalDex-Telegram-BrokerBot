from telegram import Update
from telegram.ext import ContextTypes
import db

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help information."""
    user_id = update.effective_user.id
    has_wallet = db.get_user_wallet(user_id) is not None
    
    help_text = (
        "🤖 *BSC Wallet Bot Commands*\n\n"
        
        "*Wallet Management*\n"
        "/wallet - Show all wallets and active wallet info\n"
        "/wallets - List all wallets and switch between them\n"
        "/addwallet - Add a new wallet (create or import)\n"
        "/backup - Backup your active wallet's private key\n"
        "/recover - Recover a wallet using a private key\n\n"
        
        "*Transactions*\n"
        "/balance - Check BNB and token balances\n"
        "/send - Send BNB or tokens\n"
        "/receive - Show your wallet address for receiving funds\n\n"
        
        "*Other*\n"
        "/help - Show this help message\n"
        "/start - Start or restart the bot\n"
        "/cancel - Cancel the current operation\n\n"
        
        "*Security Tips*\n"
        "• Never share your private keys with anyone\n"
        "• Always backup your wallet private keys\n"
        "• Double-check addresses when sending funds\n"
        "• This bot encrypts your private keys but still use at your own risk"
    )
    
    if not has_wallet:
        help_text += "\n\n💡 You don't have a wallet yet. Use /wallet to create one."
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def universal_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help information, even in group chats."""
    help_text = (
        "🤖 *BSC Wallet Bot Commands*\n\n"
        
        "*Wallet Management*\n"
        "/wallet - Show all wallets and active wallet info\n"
        "/wallets - List all wallets and switch between them\n"
        "/addwallet - Add a new wallet (create or import)\n"
        "/backup - Backup your active wallet's private key\n"
        "/recover - Recover a wallet using a private key\n\n"
        
        "*Transactions*\n"
        "/balance - Check BNB and token balances\n"
        "/send - Send BNB or tokens\n"
        "/receive - Show your wallet address for receiving funds\n\n"
        
        "*Other*\n"
        "/help - Show this help message\n"
        "/start - Start or restart the bot\n"
        "/cancel - Cancel the current operation\n\n"
        
        "⚠️ For security, use this bot in a private chat only."
    )
    
    await update.message.reply_text(help_text, parse_mode='Markdown') 