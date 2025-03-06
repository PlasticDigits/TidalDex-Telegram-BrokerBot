from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler
import db
import logging

# Enable logging
logger = logging.getLogger(__name__)

# Conversation states
SELECTING_WALLET = 0

async def wallets_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show available wallets and let the user select one."""
    user_id = update.effective_user.id
    user_wallets = db.get_user_wallets(user_id)
    
    if not user_wallets:
        await update.message.reply_text(
            "You don't have any wallets yet. Use /wallet to create your first wallet or /addwallet to add a new one."
        )
        return ConversationHandler.END
    
    # Create keyboard with wallet options
    keyboard = []
    for name, wallet_info in user_wallets.items():
        # Add indicator for active wallet
        label = f"🔷 {name} ({wallet_info['address'][:6]}...{wallet_info['address'][-4:]})" if wallet_info['is_active'] else f"{name} ({wallet_info['address'][:6]}...{wallet_info['address'][-4:]})"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"wallet:{name}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Your wallets:\nSelect a wallet to switch to it:",
        reply_markup=reply_markup
    )
    
    return SELECTING_WALLET

async def wallet_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle wallet selection."""
    query = update.callback_query
    await query.answer()
    
    # Extract wallet name from callback data
    wallet_name = query.data.split(':', 1)[1]
    user_id = update.effective_user.id
    
    # Set the selected wallet as active
    if db.set_active_wallet(user_id, wallet_name):
        wallet = db.get_user_wallet(user_id)
        await query.edit_message_text(
            f"Switched to wallet: {wallet_name}\n"
            f"Address: `{wallet['address']}`\n\n"
            "Use /balance to check your balances\n"
            "Use /send to send funds\n"
            "Use /receive to get your address for receiving funds",
            parse_mode='Markdown'
        )
    else:
        await query.edit_message_text(f"Error: Could not switch to wallet '{wallet_name}'. It may have been deleted.")
    
    return ConversationHandler.END 