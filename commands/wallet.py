from telegram import Update
from telegram.ext import ContextTypes
import db
import wallet

async def wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show active wallet information and a summary of all wallets."""
    user_id = update.effective_user.id
    user_wallet = db.get_user_wallet(user_id)
    user_wallets = db.get_user_wallets(user_id)
    
    if not user_wallet:
        # Create a new wallet
        new_wallet = wallet.create_wallet()
        db.save_user_wallet(user_id, new_wallet, "Default")
        
        await update.message.reply_text(
            "🎉 New wallet created!\n\n"
            f"Address: `{new_wallet['address']}`\n\n"
            f"Private Key: `{new_wallet['private_key']}`\n\n"
            "⚠️ IMPORTANT: Save your private key somewhere safe. "
            "Anyone with access to your private key can access your wallet. "
            "Your wallet is encrypted and cannot be recovered if lost. "
            "I won't show it again for security reasons.",
            parse_mode='Markdown'
        )
    else:
        # Get active wallet name
        active_wallet_name = next((name for name, info in user_wallets.items() if info['is_active']), "Default")
        
        # Show all wallets with active wallet highlighted
        wallets_text = "Your wallets:\n"
        for name, info in user_wallets.items():
            prefix = "🔷 " if info['is_active'] else "○ "
            wallets_text += f"{prefix}{name}: `{info['address'][:8]}...{info['address'][-6:]}`\n"
        
        # Show active wallet details
        await update.message.reply_text(
            f"{wallets_text}\n"
            f"Currently active: {active_wallet_name}\n\n"
            "Use /wallets to switch between wallets\n"
            "Use /addwallet to add a new wallet\n"
            "Use /balance to check your balances\n"
            "Use /send to send funds\n"
            "Use /receive to get your address for receiving funds",
            parse_mode='Markdown'
        ) 