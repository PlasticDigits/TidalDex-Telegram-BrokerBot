from telegram import Update
from telegram.ext import ContextTypes
import db
import wallet

async def wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Create or show wallet information."""
    user_id = update.effective_user.id
    user_wallet = db.get_user_wallet(user_id)
    
    if not user_wallet:
        # Create a new wallet
        new_wallet = wallet.create_wallet()
        db.save_user_wallet(user_id, new_wallet)
        
        await update.message.reply_text(
            "🎉 New wallet created!\n\n"
            f"Address: `{new_wallet['address']}`\n\n"
            f"Private Key: `{new_wallet['private_key']}`\n\n"
            "⚠️ IMPORTANT: Save your private key somewhere safe. "
            "Anyone with access to your private key can access your wallet."
            "Your wallet is encrypted and cannot be recovered if lost."
            "I won't show it again for security reasons.",
            parse_mode='Markdown'
        )
    else:
        # Show existing wallet
        await update.message.reply_text(
            "Your wallet:\n\n"
            f"Address: `{user_wallet['address']}`\n\n"
            "Use /balance to check your balances\n"
            "Use /send to send funds\n"
            "Use /receive to get your address for receiving funds",
            parse_mode='Markdown'
        ) 