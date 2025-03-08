from telegram import Update
from telegram.ext import ContextTypes
import db
from services.wallet import get_active_wallet_name, get_user_wallet, get_wallet_balance
from services.pin import pin_manager
import logging
from web3 import Web3
import traceback
import json
import requests
from utils.config import BSC_RPC_URL

# Configure module logger
logger = logging.getLogger(__name__)

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display wallet balance."""
    user_id = update.effective_user.id
    wallet_name = get_active_wallet_name(user_id)
    pin = pin_manager.get_pin(user_id)
    
    user_wallet = get_user_wallet(user_id, wallet_name, pin)
    
    if not user_wallet:
        await update.message.reply_text(
            "You don't have an active wallet. Use /wallet to create one."
        )
        return
    
    wallet_address = user_wallet['address']
    await update.message.reply_text(f"Fetching balance for {wallet_name}...")
    
    try:
        # Connect to BSC
        w3 = Web3(Web3.HTTPProvider(BSC_RPC_URL))
        
        # Get BNB balance
        balance_wei = await get_wallet_balance(wallet_address)
        balance_bnb = w3.from_wei(balance_wei, 'ether')
        
        # Format with comma separators and fixed decimal places
        formatted_balance = f"{balance_bnb:,.4f}"
        
        # Try to get USD price
        try:
            price_response = requests.get('https://api.binance.com/api/v3/ticker/price?symbol=BNBUSDT')
            if price_response.status_code == 200:
                price_data = price_response.json()
                bnb_price = float(price_data['price'])
                usd_value = balance_bnb * bnb_price
                formatted_usd = f"${usd_value:,.2f}"
                
                await update.message.reply_text(
                    f"🔍 Wallet: {wallet_name}\n"
                    f"📬 Address: `{wallet_address}`\n\n"
                    f"💰 Balance: {formatted_balance} BNB\n"
                    f"💵 Value: {formatted_usd} USD\n\n"
                    f"Use /send to transfer funds.",
                    parse_mode='Markdown'
                )
            else:
                # No price data available
                await update.message.reply_text(
                    f"🔍 Wallet: {wallet_name}\n"
                    f"📬 Address: `{wallet_address}`\n\n"
                    f"💰 Balance: {formatted_balance} BNB\n\n"
                    f"Use /send to transfer funds.",
                    parse_mode='Markdown'
                )
        except Exception as e:
            # Error getting price data
            logger.error(f"Error getting BNB price: {e}")
            await update.message.reply_text(
                f"🔍 Wallet: {wallet_name}\n"
                f"📬 Address: `{wallet_address}`\n\n"
                f"💰 Balance: {formatted_balance} BNB\n\n"
                f"Use /send to transfer funds.",
                parse_mode='Markdown'
            )
    except Exception as e:
        logger.error(f"Error in balance command: {e}")
        logger.error(traceback.format_exc())
        await update.message.reply_text(
            "Error retrieving wallet balance. Please try again later."
        ) 