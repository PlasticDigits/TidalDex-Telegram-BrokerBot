from telegram import Update
from telegram.ext import ContextTypes
from typing import Optional
from services.wallet import get_active_wallet_name, has_user_wallet
from services.pin import pin_manager
import logging
from db.wallet import WalletData

# Enable logging
logger = logging.getLogger(__name__)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help information."""
    user = update.effective_user
    
    if user is None:
        logger.error("Failed to get effective user from update")
        return
        
    user_id: int = user.id
    
    # Get active wallet name and PIN
    wallet_name: Optional[str] = get_active_wallet_name(str(user_id))
    pin: Optional[str] = pin_manager.get_pin(user_id)
    
    # Check if the user has a wallet
    has_wallet: bool = has_user_wallet(str(user_id), pin)
    
    # Use plain text without Markdown for safer rendering
    help_text: str = (
        "🤖 BSC Wallet Bot Commands\n\n"
        
        "Wallet Management:\n"
        "/wallet - Show all wallets and active wallet info\n"
        "/wallets - List all wallets and switch between them\n"
        "/addwallet - Add a new wallet (create or import)\n"
        "/rename_wallet - Rename your currently active wallet\n"
        "/backup - Backup your active wallet's seed phrase\n"
        "/export_key - Export private key of your active wallet\n"
        "/recover - Recover a wallet using a private key\n"
        "/deletewalletsall - Delete all wallets and mnemonic keys (DANGER!)\n\n"
        
        "Security:\n"
        "/set_pin - Set or change your security PIN\n"
        "/lock - Lock your wallet (clear cached PIN)\n\n"
        
        "Transactions:\n"
        "/balance - Check BNB and token balances\n"
        "/send - Send BNB or tokens\n"
        "/receive - Show your wallet address for receiving funds\n\n"
        
        "Token Tracking:\n"
        "/track - Track a token's balance over time\n"
        "/track_view - View your tracked token balances and history\n"
        "/track_stop - Stop tracking a token\n\n"
        
        "Other:\n"
        "/help - Show this help message\n"
        "/start - Start or restart the bot\n"
        "/cancel - Cancel the current operation\n\n"
        
        "Security Tips:\n"
        "• Never share your private keys or seed phrases\n"
        "• Set a PIN for additional security\n"
        "• Use /lock when you're done to secure your wallet\n"
        "• Always backup your wallet private keys\n"
        "• Double-check addresses when sending funds\n"
        "• This bot encrypts your private keys but still use at your own risk"
    )
    
    if not has_wallet:
        help_text += "\n\n💡 You don't have a wallet yet. Use /wallet to create one."
    
    # Send without parse_mode to avoid Markdown parsing issues
    message = update.message
    if message:
        await message.reply_text(help_text)

async def universal_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help information, even in group chats."""
    # Use plain text without Markdown for safer rendering
    help_text: str = (
        "🤖 BSC Wallet Bot Commands\n\n"
        
        "Wallet Management:\n"
        "/wallet - Show all wallets and active wallet info\n"
        "/wallets - List all wallets and switch between them\n"
        "/switch - Switch to a different wallet\n"
        "/addwallet - Add a new wallet (create or import)\n"
        "/rename_wallet - Rename your currently active wallet\n"
        "/backup - Backup your active wallet's seed phrase\n"
        "/export_key - Export private key of your active wallet\n"
        "/recover - Recover a wallet using a private key\n"
        "/deletewalletsall - Delete all wallets and mnemonic keys (DANGER!)\n\n"
        
        "Security:\n"
        "/set_pin - Set or change your security PIN\n"
        "/lock - Lock your wallet (clear cached PIN)\n\n"
        
        "Transactions:\n"
        "/balance - Check BNB and token balances\n"
        "/send - Send BNB or tokens\n"
        "/receive - Show your wallet address for receiving funds\n\n"
        
        "Token Tracking:\n"
        "/track - Track a token's balance over time\n"
        "/track_view - View your tracked token balances and history\n"
        "/track_stop - Stop tracking a token\n\n"
        
        "Other:\n"
        "/help - Show this help message\n"
        "/start - Start or restart the bot\n"
        "/cancel - Cancel the current operation\n\n"
        
        "⚠️ For security, use this bot in a private chat only."
    )
    
    # Send without parse_mode to avoid Markdown parsing issues
    message = update.message
    if message:
        await message.reply_text(help_text) 