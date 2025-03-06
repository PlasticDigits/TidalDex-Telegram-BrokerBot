import os
import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler, ContextTypes
from telegram import Update
from telegram.error import TelegramError

# Import custom modules
from utils.chat import create_private_chat_wrapper
from utils.config import TELEGRAM_BOT_TOKEN

# Import command handlers from commands package
from commands.start import start
from commands.wallet import wallet_command
from commands.balance import balance_command
from commands.receive import receive_command
from commands.send import (
    send_command, button_callback, 
    send_bnb_amount, send_bnb_address, 
    send_token_symbol, send_token_amount, send_token_address,
    CHOOSING_ACTION, SEND_BNB_AMOUNT, SEND_BNB_ADDRESS, 
    SEND_TOKEN_SYMBOL, SEND_TOKEN_AMOUNT, SEND_TOKEN_ADDRESS
)
from commands.cancel import cancel
from commands.recovery import (
    recover_command, process_private_key, backup_command,
    WAITING_FOR_PRIVATE_KEY
)
from commands.help import help_command, universal_help_command

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main() -> None:
    """Start the bot."""
    # Create the Application
    token = TELEGRAM_BOT_TOKEN
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables!")
        return
    
    application = Application.builder().token(token).build()

    # Create private chat wrappers for all command handlers
    start_wrapper = create_private_chat_wrapper(start)
    wallet_wrapper = create_private_chat_wrapper(wallet_command)
    balance_wrapper = create_private_chat_wrapper(balance_command)
    receive_wrapper = create_private_chat_wrapper(receive_command)
    send_wrapper = create_private_chat_wrapper(send_command)
    backup_wrapper = create_private_chat_wrapper(backup_command)
    recover_wrapper = create_private_chat_wrapper(recover_command)
    help_wrapper = create_private_chat_wrapper(help_command)

    # Add command handlers with the private chat wrappers
    application.add_handler(CommandHandler("start", start_wrapper))
    application.add_handler(CommandHandler("wallet", wallet_wrapper))
    application.add_handler(CommandHandler("balance", balance_wrapper))
    application.add_handler(CommandHandler("receive", receive_wrapper))
    application.add_handler(CommandHandler("backup", backup_wrapper))
    application.add_handler(CommandHandler("help", universal_help_command))
    
    # Add conversation handler for sending funds
    send_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("send", send_wrapper)],
        states={
            CHOOSING_ACTION: [CallbackQueryHandler(button_callback)],
            SEND_BNB_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_bnb_amount)],
            SEND_BNB_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_bnb_address)],
            SEND_TOKEN_SYMBOL: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_token_symbol)],
            SEND_TOKEN_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_token_amount)],
            SEND_TOKEN_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_token_address)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )
    
    # Add conversation handler for wallet recovery
    recover_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("recover", recover_wrapper)],
        states={
            WAITING_FOR_PRIVATE_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_private_key)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )
    
    application.add_handler(send_conv_handler)
    application.add_handler(recover_conv_handler)
    
    # Add error handler
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Log the error and send a telegram message to notify the developer."""
        # Log the error before we do anything else
        logger.error("Exception while handling an update:", exc_info=context.error)
        
        # Send an error message
        if update and hasattr(update, 'effective_message') and update.effective_message:
            await update.effective_message.reply_text('An error occurred while processing your request.')
    
    application.add_error_handler(error_handler)
    
    # Start the Bot
    application.run_polling()

    return

if __name__ == '__main__':
    main() 