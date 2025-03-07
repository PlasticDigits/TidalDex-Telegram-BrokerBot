from telegram import Update
from telegram.ext import ContextTypes
import db
from db.wallet import get_active_wallet_name
from services.pin import pin_manager
import logging

async def receive_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display wallet address for receiving funds."""
    user_id = update.effective_user.id
    
    # Get active wallet name and PIN
    wallet_name = get_active_wallet_name(user_id)
    pin = pin_manager.get_pin(user_id)
    
    # Get user wallet
    user_wallet = db.get_user_wallet(user_id, wallet_name, pin)
    
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