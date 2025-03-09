"""
Command for displaying wallet information and creating a wallet.
"""
import logging
import db
import traceback
from telegram import Update
from telegram.ext import ContextTypes
from services.wallet import get_active_wallet_name, get_user_wallets, create_wallet, has_user_wallet, set_active_wallet, has_user_mnemonic
from services.pin import pin_manager

# Configure module logger
logger = logging.getLogger(__name__)

async def wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Display wallet information or create a wallet if none exists.
    """
    user_id = update.effective_user.id
    
    # Check if the user has any wallets
    pin = pin_manager.get_pin(user_id)
    user_has_wallet = has_user_wallet(user_id, pin)
    logger.info(f"User {user_id} has wallet: {user_has_wallet}")
    
    if user_has_wallet:
        # Get context data
        wallet_name = get_active_wallet_name(user_id)
        logger.info(f"User {user_id} has active wallet: {wallet_name}")
        
        # Get all wallets (returns a dictionary with wallet names as keys)
        all_wallets = get_user_wallets(user_id)
        
        # If no active wallet is set but wallets exist, set the first one as active
        if not wallet_name and all_wallets and len(all_wallets) > 0:
            # Get the first wallet name from the dictionary keys
            first_wallet_name = next(iter(all_wallets))
            success = set_active_wallet(user_id, first_wallet_name)
            if success:
                wallet_name = first_wallet_name
                logger.info(f"Set first wallet '{first_wallet_name}' as active for user {user_id}")
        
        # Mark active wallet
        wallet_list = []
        for name, wallet_info in all_wallets.items():
            if wallet_info:  # Make sure wallet_info is not None
                active_marker = "✅ " if name == wallet_name else ""
                address = wallet_info.get('address', '')
                # Format with monospace font
                wallet_list.append(f"{active_marker}{name}: `{address}`")
        
        wallet_info = "\n".join(wallet_list)
        logger.info(f"Wallet info: {wallet_info}")
        # use MarkdownV2 without html or error handling
        await update.message.reply_text(
            f"🔑 Your wallets \({len(all_wallets)}\):\n\n{wallet_info}\n\n"
            "Use /addwallet to add more wallets or /rename\_wallet to rename the active wallet\.\n"
            "Use /send to send funds\.",
            parse_mode='MarkdownV2'
        )
    else:
        # Create a new wallet for the user
        try:                
            # Create new wallet with default name
            new_wallet_name = "Default"
            new_wallet = create_wallet(user_id, new_wallet_name, pin)
            
            if new_wallet:
                address = new_wallet.get('address', '')
                # use MarkdownV2 without html or error handling
                await update.message.reply_text(
                    f"✅ Created a new wallet named '{new_wallet_name}'\n\n"
                    f"Address: `{address}`\n\n"
                    "You can now use /send to send funds and /receive to view your address\.\n"
                    "Important: Use /backup to save your recovery phrase\!",
                    parse_mode='MarkdownV2'
                )
            else:
                await update.message.reply_text(
                    "Error creating a wallet. Please try again later."
                )
        except Exception as e:
            logger.error(f"Error creating wallet: {e}")
            logger.error(traceback.format_exc())
            await update.message.reply_text(
                "There was an error creating your wallet. Please try again later."
            )

# since wallet command is NOT protected by PIN, this is end of file.