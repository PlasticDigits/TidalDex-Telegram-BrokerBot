"""
Example of using status callbacks in Telegram bot handlers.
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, Application
from wallet import get_bnb_balance, get_token_balance, send_bnb, send_token
from wallet.utils import validate_address

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for /balance command with status updates."""
    # Get the wallet address from the command arguments
    if not context.args or len(context.args) < 1:
        await update.message.reply_text("Please provide a wallet address: /balance <address>")
        return

    address = context.args[0]
    
    # Initial response
    response = await update.message.reply_text("Fetching balance... ⏳")
    
    # Create a status update callback function
    async def status_callback(message):
        await response.edit_text(f"{response.text}\n{message}")
    
    try:
        # Validate address
        valid_address = validate_address(address)
        
        # Get BNB balance with status updates
        balance = get_bnb_balance(valid_address, status_callback=status_callback)
        
        # Final update with the balance
        await response.edit_text(f"Balance fetching complete!\n\nAddress: {valid_address}\nBNB Balance: {balance}")
    
    except Exception as e:
        logging.error(f"Error in balance command: {str(e)}")
        await response.edit_text(f"Error fetching balance: {str(e)}")

async def token_balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for /tokenbalance command with status updates."""
    # Get the wallet address and token address from the command arguments
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Please provide token and wallet addresses: /tokenbalance <token_address> <wallet_address>")
        return

    token_address = context.args[0]
    wallet_address = context.args[1]
    
    # Initial response
    response = await update.message.reply_text("Fetching token balance... ⏳")
    
    # Create a status update callback function
    async def status_callback(message):
        await response.edit_text(f"{response.text}\n{message}")
    
    try:
        # Get token balance with status updates
        balance_info = get_token_balance(token_address, wallet_address, status_callback=status_callback)
        
        # Final update with the token balance
        await response.edit_text(
            f"Token balance fetching complete!\n\n"
            f"Token: {balance_info['symbol']}\n"
            f"Balance: {balance_info['balance']} {balance_info['symbol']}\n"
            f"Wallet: {wallet_address}"
        )
    
    except Exception as e:
        logging.error(f"Error in token balance command: {str(e)}")
        await response.edit_text(f"Error fetching token balance: {str(e)}")

async def send_bnb_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for /sendbnb command with status updates."""
    # Get required parameters
    if not context.args or len(context.args) < 3:
        await update.message.reply_text(
            "Please provide all required parameters: "
            "/sendbnb <private_key> <to_address> <amount_bnb>"
        )
        return
    
    private_key = context.args[0]
    to_address = context.args[1]
    try:
        amount_bnb = float(context.args[2])
    except ValueError:
        await update.message.reply_text("Invalid amount. Please provide a valid number.")
        return
    
    # Initial response
    response = await update.message.reply_text("Preparing BNB transaction... ⏳")
    
    # Create a status update callback function
    async def status_callback(message):
        await response.edit_text(f"{response.text}\n{message}")
    
    try:
        # Send BNB with status updates
        tx_result = send_bnb(private_key, to_address, amount_bnb, status_callback=status_callback)
        
        # Final update with transaction results
        status_text = "Successful ✅" if tx_result['status'] == 1 else "Failed ❌"
        await response.edit_text(
            f"BNB transaction {status_text}\n\n"
            f"Transaction Hash: {tx_result['tx_hash']}\n"
            f"Block Number: {tx_result['block_number']}\n"
            f"Amount: {amount_bnb} BNB"
        )
    
    except Exception as e:
        logging.error(f"Error in send BNB command: {str(e)}")
        await response.edit_text(f"Error sending BNB: {str(e)}")

def main() -> None:
    """Run the Telegram bot."""
    # Create application
    application = Application.builder().token("YOUR_TELEGRAM_BOT_TOKEN").build()
    
    # Add command handlers
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CommandHandler("tokenbalance", token_balance_command))
    application.add_handler(CommandHandler("sendbnb", send_bnb_command))
    
    # Start the Bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 