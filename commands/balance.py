from telegram import Update
from telegram.ext import ContextTypes
import db
from db.wallet import get_active_wallet_name
import wallet
from utils import token
from wallet.utils import validate_address
from utils.status_updates import create_status_callback
from services.pin import pin_manager
from services.pin.pin_decorators import require_pin
import logging

# Enable logging
logger = logging.getLogger(__name__)

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show BNB and token balances with real-time status updates."""
    user_id = update.effective_user.id
    
    # Get active wallet and PIN from pin_manager
    wallet_name = get_active_wallet_name(user_id)
    pin = pin_manager.get_pin(user_id)
    user_wallet = db.get_user_wallet(user_id, wallet_name, pin)
    
    if not user_wallet:
        await update.message.reply_text("You don't have a wallet yet. Use /wallet to create one.")
        return
    
    address = user_wallet['address']
    
    # Initial response with loading indicator
    response = await update.message.reply_text("💰 Fetching your wallet balances... ⏳")
    
    # Create a status callback using the utility function
    status_callback = create_status_callback(response, max_lines=15, header_lines=3)
    
    try:
        # Validate the address
        try:
            valid_address = validate_address(address)
        except ValueError as e:
            logger.error(f"Invalid wallet address: {e}")
            await response.edit_text(f"Error: Invalid wallet address. Please recreate your wallet using /wallet.")
            return
        
        balances_text = "💰 Your wallet balances:\n\n"
        
        # Get BNB balance with status updates
        await status_callback("Fetching BNB balance...")
        try:
            bnb_balance = await wallet.get_bnb_balance(valid_address, status_callback=status_callback)
            balances_text += f"BNB: {bnb_balance}\n\n"
        except Exception as e:
            logger.error(f"Error getting BNB balance: {e}")
            balances_text += f"BNB: Error fetching balance\n\n"
        
        # Get token balances for popular tokens
        popular_tokens = token.get_token_list()
        
        token_balances = []
        for token_item in popular_tokens:
            try:
                await status_callback(f"Fetching {token_item['symbol']} balance...")
                token_info = await wallet.get_token_balance(token_item['address'], valid_address, status_callback=status_callback)
                if token_info['balance'] > 0:
                    token_balances.append(f"{token_info['symbol']}: {token_info['balance']}")
            except Exception as e:
                logger.error(f"Error getting balance for {token_item['symbol']}: {e}")
        
        # Add token balances to response
        if token_balances:
            balances_text += '\n'.join(token_balances)
        else:
            balances_text += "No token balances found."
        
        # Show final result
        await response.edit_text(balances_text)
        
    except Exception as e:
        logger.error(f"Unexpected error in balance command: {e}")
        await response.edit_text(f"An error occurred while fetching your balances. Please try again later.\n\nError: {str(e)}") 