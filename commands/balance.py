from telegram import Update
from telegram.ext import ContextTypes
from typing import Optional, Dict, Any, Union, cast
from decimal import Decimal
from services.wallet import get_active_wallet_name, get_user_wallet, get_wallet_balance
from services.pin import pin_manager
import logging
from db.wallet import WalletData
from web3 import Web3
import traceback
import httpx
from utils.config import BSC_RPC_URL

# Configure module logger
logger = logging.getLogger(__name__)

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display wallet balance."""
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
    await message.reply_text(f"Fetching balance for {wallet_name}...")

    httpxClient: httpx.AsyncClient = httpx.AsyncClient()
    
    try:
        # Connect to BSC
        w3: Web3 = Web3(Web3.HTTPProvider(BSC_RPC_URL))
        
        # Get BNB balance
        balance_wei: int = await get_wallet_balance(wallet_address, pin)
        balance_bnb: Decimal = Decimal(w3.from_wei(balance_wei, 'ether'))
        
        # Format with comma separators and fixed decimal places
        formatted_balance: str = f"{balance_bnb:,.4f}"
        
        # Try to get USD price
        try:
            price_response: httpx.Response = await httpxClient.get('https://api.binance.com/api/v3/ticker/price?symbol=BNBUSDT')
            if price_response.status_code == 200:
                price_data: Dict[str, str] = price_response.json()
                bnb_price: float = float(price_data['price'])
                usd_value: float = float(balance_bnb) * bnb_price
                formatted_usd: str = f"${usd_value:,.2f}"
                
                await message.reply_text(
                    f"🔍 Wallet: {wallet_name}\n"
                    f"📬 Address: `{wallet_address}`\n\n"
                    f"💰 Balance: {formatted_balance} BNB\n"
                    f"💵 Value: {formatted_usd} USD\n\n"
                    f"Use /send to transfer funds.",
                    parse_mode='Markdown'
                )
            else:
                # No price data available
                await message.reply_text(
                    f"🔍 Wallet: {wallet_name}\n"
                    f"📬 Address: `{wallet_address}`\n\n"
                    f"💰 Balance: {formatted_balance} BNB\n\n"
                    f"Use /send to transfer funds.",
                    parse_mode='Markdown'
                )
        except Exception as e:
            # Error getting price data
            logger.error(f"Error getting BNB price: {e}")
            await message.reply_text(
                f"🔍 Wallet: {wallet_name}\n"
                f"📬 Address: `{wallet_address}`\n\n"
                f"💰 Balance: {formatted_balance} BNB\n\n"
                f"Use /send to transfer funds.",
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"Error in balance command: {e}")
        logger.error(traceback.format_exc())
        await message.reply_text(
            "Error retrieving wallet balance. Please try again later."
        ) 