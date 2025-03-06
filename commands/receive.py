from telegram import Update
from telegram.ext import ContextTypes
import db

async def receive_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display the user's wallet address for receiving funds."""
    user_id = update.effective_user.id
    user_wallet = db.get_user_wallet(user_id)
    
    if not user_wallet:
        await update.message.reply_text("You don't have a wallet yet. Use /wallet to create one.")
        return
    
    address = user_wallet['address']
    
    await update.message.reply_text(
        "📥 Your receiving address:\n\n"
        f"`{address}`\n\n"
        "Share this address to receive BNB and BEP20 tokens.",
        parse_mode='Markdown'
    ) 