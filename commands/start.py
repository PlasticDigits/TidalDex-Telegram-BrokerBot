from telegram import Update
from telegram.ext import ContextTypes

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_html(
        f"Hi {user.mention_html()}! I'm your TidalDex Wallet Bot.\n\n"
        f"🔑 <b>Wallet Management</b>\n"
        f"• Use /wallet to create or view your wallet\n"
        f"• Use /backup to securely backup your private key\n"
        f"• Use /recover to restore a wallet from a private key\n\n"
        f"💰 <b>Transactions</b>\n"
        f"• Use /send to send BNB or tokens\n"
        f"• Use /receive to get your wallet address\n"
        f"• Use /balance to check your balances"
    ) 