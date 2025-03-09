from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler
import db
from services.wallet import get_active_wallet_name, get_user_wallets, get_user_wallet, set_active_wallet
from services.pin import pin_manager
import logging

# Configure module logger
logger = logging.getLogger(__name__)

# Define conversation state
SELECTING_WALLET = 1

async def wallets_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """List all wallets and allow switching between them."""
    user_id = update.effective_user.id
    pin = pin_manager.get_pin(user_id)
    
    # Get the current active wallet name
    active_wallet_name = get_active_wallet_name(user_id)
    
    # Get all wallets for the user
    user_wallets = get_user_wallets(user_id, pin)
    
    if not user_wallets:
        await update.message.reply_text(
            "You don't have any wallets. Use /wallet to create one."
        )
        return ConversationHandler.END
    
    # Create a keyboard with all wallets
    keyboard = []
    logger.info(f"User wallets: {user_wallets}")
    for wallet in user_wallets:
        logger.info(f"Wallet: {wallet}")
        wallet_name = wallet.get('name', 'Unnamed')
        is_active = (wallet_name == active_wallet_name)
        active_marker = "✅ " if is_active else ""
        
        # Limit the displayed address to first and last few characters
        address = wallet.get('address', '')
        if len(address) > 15:
            address = f"{address[:8]}...{address[-6:]}"
        
        label = f"{active_marker}{wallet_name} ({address})"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"wallets_select:{wallet_name}")])
    
    # Add a cancel button
    keyboard.append([InlineKeyboardButton("Cancel", callback_data="wallets_select_cancel")])
    
    # Send the message with the inline keyboard
    await update.message.reply_text(
        f"You have {len(user_wallets)} wallet(s). Select a wallet to make it active:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    
    return SELECTING_WALLET

async def wallet_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process wallet selection."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    pin = pin_manager.get_pin(user_id)
    
    # Extract the selected wallet name from callback data
    callback_data = query.data
    
    if callback_data == "wallets_select_cancel":
        await query.edit_message_text("Wallet selection canceled.")
        return ConversationHandler.END
    
    # Format: "wallets_select:WalletName"
    selected_wallet_name = callback_data.split(":", 1)[1]
    
    # Verify the wallet exists
    wallet = get_user_wallet(user_id, selected_wallet_name, pin)
    
    if not wallet:
        await query.edit_message_text(f"Error: Wallet '{selected_wallet_name}' not found.")
        return ConversationHandler.END
    
    # Set the wallet as active
    success = set_active_wallet(user_id, selected_wallet_name)
    
    if success:
        address = wallet.get('address', '')
        if len(address) > 20:
            address = f"{address[:10]}...{address[-10:]}"
            
        await query.edit_message_text(
            f"✅ Wallet '{selected_wallet_name}' is now active.\n\n"
            f"Address: `{address}`\n\n"
            f"Use /wallet to see details or /send to send funds.",
            parse_mode='Markdown'
        )
    else:
        await query.edit_message_text(
            f"Error setting '{selected_wallet_name}' as active wallet. Please try again."
        )
    
    return ConversationHandler.END 