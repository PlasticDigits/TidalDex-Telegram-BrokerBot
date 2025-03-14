from telegram import Update, User
from telegram.ext import ContextTypes

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message when the command /start is issued."""
    if not update.effective_user or not update.message:
        return
        
    user: User = update.effective_user
    await update.message.reply_html(
        f"Hi {user.mention_html()}! I'm your TidalDex Wallet Bot.\n\n"
        f"🔑 <b>Wallet Management</b>\n"
        f"• Use /wallet to create or view your wallet\n"
        f"• Use /backup to securely backup your private key\n"
        f"• Use /recover to restore a wallet from a recovery phrase or private key\n\n"
        f"💰 <b>Transactions</b>\n"
        f"• Use /send to send BNB or tokens\n"
        f"• Use /receive to get your wallet address\n"
        f"• Use /balance to check your balances\n\n"
        f"🔐 <b>Security</b>\n"
        f"• Use /set_pin to set or change a PIN for your wallet\n"
    ) 