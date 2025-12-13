"""
Command for displaying wallet balances including BNB and tracked tokens.
"""
from telegram import Update
from telegram.ext import ContextTypes
from typing import Optional, Dict, Any, Union, cast, List
from decimal import Decimal
from services.wallet import get_active_wallet_name, get_user_wallet, get_wallet_balance
from services.pin import pin_manager
from services import token_manager
import logging
from db.wallet import WalletData
from utils.web3_connection import w3
import traceback
import httpx
from utils.config import BSC_RPC_URL
from typing import Callable, Coroutine
from services.pin import require_pin
from utils.number_display import number_display_with_sigfig
from utils.token_utils import format_token_balance
from telegram.ext import ConversationHandler
from db.utils import hash_user_id

# Configure module logger
logger = logging.getLogger(__name__)


def _format_token_balances(token_balances: Dict[str, Any]) -> List[str]:
    """Format token balances for display, showing addresses for duplicate symbols.
    
    Args:
        token_balances: Dictionary of token address -> balance info
        
    Returns:
        List of formatted balance strings
    """
    if not token_balances:
        return []
    
    # Group by symbol to detect duplicates
    symbol_counts: Dict[str, int] = {}
    for balance_info in token_balances.values():
        symbol = str(balance_info.get('symbol', '')).strip().upper()
        symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1
    
    balance_lines: List[str] = []
    for token_addr, balance_info in token_balances.items():
        symbol: str = str(balance_info.get('symbol', '')).strip()
        name: str = balance_info.get('name', 'Unknown')
        if balance_info.get("error"):
            formatted_balance = "⚠️ unavailable"
        else:
            formatted_balance = format_token_balance(
                balance_info.get('raw_balance', 0),
                balance_info.get('decimals', 18)
            )
        # Show address if duplicate symbol exists
        if symbol_counts.get(symbol.upper(), 0) > 1:
            addr_short = token_addr[:8] + '...' + token_addr[-6:]
            balance_lines.append(f"• {symbol} ({name}) [{addr_short}]: {formatted_balance}")
        else:
            balance_lines.append(f"• {symbol} ({name}): {formatted_balance}")
    
    return balance_lines

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display wallet balance including BNB and tracked tokens."""
    user = update.effective_user
    if not user:
        logger.error("No effective user found in update")
        return
    
    user_id: int = user.id
    user_id_str: str = str(user_id)  # Convert int to str as expected by the functions
    wallet_name: Optional[str] = get_active_wallet_name(user_id_str)
    pin: Optional[str] = pin_manager.get_pin(user_id)
    
    user_wallet: Optional[WalletData] = get_user_wallet(user_id_str, wallet_name, pin)
    
    message = update.message
    if not message:
        logger.error("No message found in update")
        return
    
    if not user_wallet:
        await message.reply_text(
            "You don't have an active wallet. Use /wallet to create one."
        )
        return
    
    wallet_address: str = user_wallet['address']
    
    # Check if address decryption failed
    if not wallet_address:
        await message.reply_text(
            f"⚠️ **Address Decryption Issue**\n\n"
            f"Unable to decrypt wallet address for '{wallet_name}'. This may be due to:\n"
            f"• PIN mismatch\n"
            f"• Corrupted wallet data\n\n"
            f"Please try:\n"
            f"1. Setting your PIN again with /set_pin\n"
            f"2. If the issue persists, contact support\n\n"
            f"Use /wallets to check other wallets."
        )
        return
        
    await message.reply_text(f"Fetching balances for {wallet_name}...")

    httpxClient: httpx.AsyncClient = httpx.AsyncClient()
    token_balances: Dict[str, Any] = {}  # Initialize token_balances as empty dict
    
    try:
        
        # Get BNB balance
        balance_wei: int = await get_wallet_balance(wallet_address, "BNB")
        balance_bnb: Decimal = Decimal(w3.from_wei(balance_wei, 'ether'))
        
        # Format with comma separators and fixed decimal places
        formatted_balance: str = f"{number_display_with_sigfig(balance_bnb, 6)}"
        
        # Get token balances
        try:
            token_balances = await token_manager.balances(user_id_str)
        except Exception as e:
            logger.error(f"Error getting token balances: {e}")
            token_balances = {}
        
        # Try to get USD price
        try:
            price_response: httpx.Response = await httpxClient.get('https://api.binance.com/api/v3/ticker/price?symbol=BNBUSDT')
            if price_response.status_code == 200:
                price_data: Dict[str, str] = price_response.json()
                bnb_price: float = float(price_data['price'])
                usd_value: float = float(balance_bnb) * bnb_price
                formatted_usd: str = f"${number_display_with_sigfig(usd_value, 6)}"
                
                # Build message with BNB balance
                msg_text: List[str] = [
                    f"🔍 Wallet: {wallet_name}",
                    f"📬 Address: `{wallet_address}`\n",
                    f"💰 BNB Balance: {formatted_balance} BNB",
                    f"💵 BNB Value: {formatted_usd} USD\n"
                ]
                
                # Add token balances if any
                if token_balances:
                    msg_text.append("📊 Token Balances:")
                    msg_text.extend(_format_token_balances(token_balances))
                
                msg_text.append("\nUse /send to transfer funds.")
                msg_text.append("Use /scan to search for tokens.")
                msg_text.append("Use /track to add balance display for a token.")
                msg_text.append("Use /swap to trade tokens.")
                
                await message.reply_text(
                    "\n".join(msg_text),
                    parse_mode='Markdown'
                )
            else:
                # No price data available
                balance_msg_text: List[str] = [
                    f"🔍 Wallet: {wallet_name}",
                    f"📬 Address: `{wallet_address}`\n",
                    f"💰 BNB Balance: {formatted_balance} BNB\n"
                ]
                
                # Add token balances if any
                if token_balances:
                    balance_msg_text.append("📊 Token Balances:")
                    balance_msg_text.extend(_format_token_balances(token_balances))
                
                balance_msg_text.append("\nUse /send to transfer funds.")
                balance_msg_text.append("Use /swap to trade BNB or tokens.")
                balance_msg_text.append("Use /scan to find other tokens in your wallet")
                
                await message.reply_text(
                    "\n".join(balance_msg_text),
                    parse_mode='Markdown'
                )
        except Exception as e:
            # Error getting price data
            logger.error(f"Error getting BNB price: {e}")
            error_msg_text: List[str] = [
                f"🔍 Wallet: {wallet_name}",
                f"📬 Address: `{wallet_address}`\n",
                f"💰 BNB Balance: {formatted_balance} BNB\n"
            ]
            
            # Add token balances if any
            if token_balances:
                error_msg_text.append("📊 Token Balances:")
                error_msg_text.extend(_format_token_balances(token_balances))
            
            error_msg_text.append("\nUse /send to transfer funds.")
            error_msg_text.append("Use /swap to trade BNB or tokens.")
            
            await message.reply_text(
                "\n".join(error_msg_text),
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"Error in balance command: {e}")
        logger.error(traceback.format_exc())
        await message.reply_text(
            "Error retrieving wallet balances. Please try again later."
        ) 

# Create a PIN-protected version of the command
pin_protected_balance: Callable[[Update, ContextTypes.DEFAULT_TYPE], Coroutine[Any, Any, None]] = require_pin(
    "🔒 Viewing your balance requires PIN verification.\nPlease enter your PIN:"
)(balance_command) 