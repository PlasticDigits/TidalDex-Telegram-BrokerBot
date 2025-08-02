"""
Command for displaying wallet information and creating a wallet.
"""
import logging
import traceback
from typing import Dict, List, Any, Optional, Union, cast
from telegram import Update, Message
from telegram.ext import ContextTypes
from services.wallet import get_active_wallet_name, get_user_wallets, create_wallet, has_user_wallet, set_active_wallet, has_user_mnemonic, create_mnemonic
from services.pin import pin_manager
from db.wallet import WalletData
from db.utils import hash_user_id
# Configure module logger
logger = logging.getLogger(__name__)

def escape_markdown_v2(text: str) -> str:
    """Escape special characters for MarkdownV2 formatting."""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text

async def wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Display wallet information or create a wallet if none exists.
    """
    # Ensure update.effective_user is not None before accessing id
    if update.effective_user is None:
        logger.error("No effective user found in update")
        return
    
    user_id_str: str = str(update.effective_user.id)
    
    # Check if the user has any wallets
    pin: Optional[str] = pin_manager.get_pin(update.effective_user.id)
    user_has_wallet: bool = has_user_wallet(user_id_str, pin)
    logger.info(f"User {hash_user_id(user_id_str)} has wallet: {user_has_wallet}")
    
    if user_has_wallet:
        # Get context data
        wallet_name: Optional[str] = get_active_wallet_name(user_id_str)
        logger.info(f"User {hash_user_id(user_id_str)} has active wallet: {wallet_name}")
        
        # Get all wallets (returns a dictionary with wallet names as keys)
        all_wallets: Dict[str, WalletData] = get_user_wallets(user_id_str, False, pin)
        
        # If no active wallet is set but wallets exist, set the first one as active
        if not wallet_name and all_wallets and len(all_wallets) > 0:
            # Get the first wallet name from the dictionary keys
            first_wallet_name: str = next(iter(all_wallets))
            success: bool = set_active_wallet(user_id_str, first_wallet_name)
            if success:
                wallet_name = first_wallet_name
                logger.info(f"Set first wallet '{first_wallet_name}' as active for user {hash_user_id(user_id_str)}")

        # Seperate private key wallets and mnemonic wallets
        private_key_wallets: List[str] = []
        mnemonic_wallets: List[str] = []
        for name, wallet_data in all_wallets.items():
            escaped_name = escape_markdown_v2(name)
            escaped_address = escape_markdown_v2(wallet_data.get('address', ''))
            line: str = f"{escaped_name}: `{escaped_address}`"
            if name == wallet_name:
                line = f"✅ **{line}**"
            if wallet_data.get('derivation_path'):
                mnemonic_wallets.append(line)
            else:
                private_key_wallets.append(line)

        mnemonic_wallets_info: str = len(mnemonic_wallets) > 0 and "Mnemonic wallets:\n" + "\n".join(mnemonic_wallets) + "\n\n" or ""
        private_key_wallets_info: str = len(private_key_wallets) > 0 and "Private key wallets:\n" + "\n".join(private_key_wallets) + "\n\n" or ""
        
        # Ensure message is not None before calling reply_text
        if update.message is not None:
            # use MarkdownV2 without html or error handling
            await update.message.reply_text(
                f"🔑 Your wallets \\({len(all_wallets)}\\):\n\n"
                f"{mnemonic_wallets_info}"
                f"{private_key_wallets_info}"
                "Use /addwallet to add more wallets or /rename\\_wallet to rename the active wallet\\.\n"
                "Use /send to send funds\\.\n"
                "Use /swap to trade BNB or tokens\\.\n"
                "Use /receive to receive funds\\.\n"
                "Use /switch to switch to a different wallet\\.\n"
                f"🔐 **Security**\n"
                f"• Use /set\\_pin to set or change a PIN for your wallet\n",
                parse_mode='MarkdownV2'
            )
    else:
        # Create a new wallet for the user
        try:                
            # Create new wallet with default name
            new_wallet_name: str = "Default"
            # create new mnemonic for the user
            mnemonic: Optional[str] = create_mnemonic(user_id_str, pin)
            if mnemonic is None:
                raise Exception("Failed to create mnemonic")
            new_wallet: Optional[WalletData] = create_wallet(user_id_str, new_wallet_name, pin)
            
            if new_wallet and update.message is not None:
                new_wallet_address: str = new_wallet.get('address', '')
                # Escape special characters for MarkdownV2
                escaped_wallet_name = escape_markdown_v2(new_wallet_name)
                escaped_address = escape_markdown_v2(new_wallet_address)
                # use MarkdownV2 without html or error handling
                await update.message.reply_text(
                    f"✅ Created a new wallet named '{escaped_wallet_name}'\n\n"
                    f"Address: `{escaped_address}`\n\n"
                    "You can now use /send to send funds and /receive to view your address\\.\n"
                    "Use /swap to trade BNB or tokens\\.\n"
                    "Use /addwallet to create additional wallets\\.\n\n"
                    f"🔐 **Security**\n"
                    f"• Use /set\\_pin to set or change a PIN for your wallet\n"
                    f"• Important: Use /backup to save your recovery phrase\\!",
                    parse_mode='MarkdownV2'
                )
            elif update.message is not None:
                await update.message.reply_text(
                    "Error creating a wallet. Please try again later."
                )
        except Exception as e:
            logger.error(f"Error creating wallet: {e}")
            logger.error(traceback.format_exc())
            if update.message is not None:
                await update.message.reply_text(
                    "There was an error creating your wallet. Please try again later."
                )

# since wallet command is NOT protected by PIN, this is end of file.