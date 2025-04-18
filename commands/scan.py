"""
Command for scanning and automatically tracking tokens with non-zero balances.
"""
import logging
from telegram import Update, User, Message
from telegram.ext import ContextTypes, CommandHandler
from typing import Optional, List, Dict, Any, Union, Callable, cast, Sequence, Coroutine
from utils.web3_connection import w3
from web3.types import ChecksumAddress # type: ignore[attr-defined]

from services import token_manager
from services.wallet import wallet_manager
from services.pin import require_pin, pin_manager
from db.wallet import WalletData
from db.utils import hash_user_id
# Configure module logger
logger = logging.getLogger(__name__)

async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Scan for tokens with non-zero balances and automatically track them.
    """
    user: Optional[User] = update.effective_user
    if not user:
        logger.error("Effective user is None in scan_command")
        return
    
    logger.info(f"Scan command called by user {hash_user_id(user.id)}")
    
    # Get the user ID as an integer (native type from Telegram)
    user_id_int: int = update.effective_user.id
    # For wallet manager, we need the user ID as a string
    user_id_str: str = str(user_id_int)
    
    # Get active wallet name and use pin_manager for PIN
    wallet_name: Optional[str] = wallet_manager.get_active_wallet_name(user_id_str)
    pin: Optional[str] = pin_manager.get_pin(user_id_int)
    user_wallet: Optional[WalletData] = wallet_manager.get_user_wallet(user_id_str, wallet_name, pin)
    
    if not wallet_name or not user_wallet:
        message: Optional[Message] = update.message
        if message:
            await message.reply_text(
                "You need to create a wallet first to scan for tokens. Use /wallet to create one."
            )
        return
    
    wallet_address: str = user_wallet['address']
    
    # Send initial message
    message4: Optional[Message] = update.message
    if not message4:
        return
        
    status_message = await message4.reply_text(
        "Scanning for tokens with non-zero balances...\n"
        "This may take a few moments."
    )
    
    try:
        # Define status callback to update the message
        async def status_callback(status: str) -> None:
            try:
                await status_message.edit_text(
                    f"Scanning for tokens with non-zero balances...\n\n"
                    f"Current status: {status}"
                )
            except Exception as e:
                logger.error(f"Failed to update status message: {e}")
        
        # Scan for tokens with status updates
        logger.info(f"Scanning for tokens with status updates for user {hash_user_id(user_id_int)}")
        newly_tracked: Sequence[ChecksumAddress] = await token_manager.scan(
            user_id_str,
            status_callback=status_callback
        )
        logger.info(f"Scanned {len(newly_tracked)} tokens for user {hash_user_id(user_id_int)}")
        
        if not newly_tracked:
            await status_message.edit_text(
                "No new tokens found with non-zero balances.\n"
                "Use /track to manually add tokens you want to track."
            )
            return
        
        # Format the list of newly tracked tokens
        token_list: str = "\n".join([
            f"• {token}" for token in newly_tracked
        ])
        
        await status_message.edit_text(
            f"Successfully started tracking {len(newly_tracked)} new tokens:\n\n"
            f"{token_list}\n\n"
            "Use /balance to see your token balances."
        )
            
        logger.info(f"User {hash_user_id(user_id_int)} scanned and started tracking {len(newly_tracked)} new tokens")
        
    except Exception as e:
        logger.error(f"Error scanning tokens for user {hash_user_id(user_id_int)}: {e}")
        await status_message.edit_text(
            "Error scanning for tokens. Please try again later."
        )

# Create PIN-protected version of the command
pin_protected_scan: Callable[[Update, ContextTypes.DEFAULT_TYPE], Coroutine[Any, Any, None]] = require_pin(
    "🔒 Scanning for tokens requires PIN verification.\nPlease enter your PIN:"
)(scan_command)

# Setup command handler
scan_handler = CommandHandler("scan", pin_protected_scan) 