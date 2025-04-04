"""
Command for scanning and automatically tracking tokens with non-zero balances.
"""
import logging
from telegram import Update, User, Message
from telegram.ext import ContextTypes, CommandHandler
from typing import Optional, List, Dict, Any, Union, Callable, cast, Sequence
from web3 import Web3
from web3.types import ChecksumAddress # type: ignore[attr-defined]

from services import token_manager
from services.wallet import get_active_wallet_name, get_wallet_by_name

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
        
    user_id: int = user.id
    
    # Verify the user has a wallet
    wallet_name: Optional[str] = get_active_wallet_name(str(user_id))
    if not wallet_name:
        message: Optional[Message] = update.message
        if message:
            await message.reply_text(
                "You need to create a wallet first to scan for tokens. Use /wallet to create one."
            )
        return
    
    # Get wallet address
    wallet = get_wallet_by_name(str(user_id), wallet_name, None)
    if not wallet:
        message2: Optional[Message] = update.message
        if message2:
            await message2.reply_text(
                "Error: Could not find your wallet. Please try again later."
            )
        return
    
    wallet_address: str = wallet.get('address', '')
    if not wallet_address:
        message3: Optional[Message] = update.message
        if message3:
            await message3.reply_text(
                "Error: Invalid wallet address. Please try again later."
            )
        return
    
    # Send initial message
    message4: Optional[Message] = update.message
    if message4:
        await message4.reply_text(
            "Scanning for tokens with non-zero balances...\n"
            "This may take a few moments."
        )
    
    try:
        # Scan for tokens
        newly_tracked: Sequence[ChecksumAddress] = await token_manager.scan(str(user_id))
        
        if not newly_tracked:
            message5: Optional[Message] = update.message
            if message5:
                await message5.reply_text(
                    "No new tokens found with non-zero balances.\n"
                    "Use /track to manually add tokens you want to track."
                )
            return
        
        # Format the list of newly tracked tokens
        token_list: str = "\n".join([
            f"• {token}" for token in newly_tracked
        ])
        
        message6: Optional[Message] = update.message
        if message6:
            await message6.reply_text(
                f"Successfully started tracking {len(newly_tracked)} new tokens:\n\n"
                f"{token_list}\n\n"
                "Use /track_view to see your token balances."
            )
            
        logger.info(f"User {user_id} scanned and started tracking {len(newly_tracked)} new tokens")
        
    except Exception as e:
        logger.error(f"Error scanning tokens for user {user_id}: {e}")
        message7: Optional[Message] = update.message
        if message7:
            await message7.reply_text(
                "Error scanning for tokens. Please try again later."
            )

# Setup command handler
scan_handler = CommandHandler("scan", scan_command) 