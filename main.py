import os
import logging
import sys
import atexit
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler, ContextTypes
from telegram import Update
from telegram.error import TelegramError
import traceback

# Import custom modules
from utils.chat import create_private_chat_wrapper
from utils.config import TELEGRAM_BOT_TOKEN
# Import restructured database module
import db

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
    recover_command, recovery_choice_callback, process_private_key, 
    process_mnemonic, process_wallet_name as recovery_process_wallet_name,
    backup_command, CHOOSING_RECOVERY_TYPE, WAITING_FOR_PRIVATE_KEY,
    WAITING_FOR_MNEMONIC, ENTERING_WALLET_NAME as RECOVERY_ENTERING_WALLET_NAME
)
from commands.help import help_command, universal_help_command
from commands.wallets import wallets_command, wallet_selection_callback, SELECTING_WALLET
from commands.addwallet import (
    addwallet_command, action_choice_callback, process_wallet_name, process_private_key as add_process_private_key,
    CHOOSING_ACTION as ADD_CHOOSING_ACTION, ENTERING_NAME, ENTERING_PRIVATE_KEY
)
from commands.export_key import export_key_command

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log')
    ]
)
# Set specific module log levels
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('asyncio').setLevel(logging.WARNING)
logging.getLogger('telegram').setLevel(logging.INFO)

# Create logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def main() -> None:
    """Start the bot."""
    # Initialize the database first
    logger.info("Initializing database...")
    if not db.init_db():
        logger.error("Failed to initialize database. Exiting.")
        return
    
    # Register database cleanup on exit
    atexit.register(db.close_connection)
    
    # Test database connection
    try:
        logger.info("Testing database connection...")
        if db.test_connection():
            logger.info("Database connection test passed")
        else:
            logger.warning("Database connection test failed")
            return
    except Exception as e:
        logger.error(f"Database test failed: {e}")
        logger.error(traceback.format_exc())
        return

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
    wallets_wrapper = create_private_chat_wrapper(wallets_command)
    addwallet_wrapper = create_private_chat_wrapper(addwallet_command)
    export_key_wrapper = create_private_chat_wrapper(export_key_command)

    # Add command handlers with the private chat wrappers
    application.add_handler(CommandHandler("start", start_wrapper))
    application.add_handler(CommandHandler("wallet", wallet_wrapper))
    application.add_handler(CommandHandler("balance", balance_wrapper))
    application.add_handler(CommandHandler("receive", receive_wrapper))
    application.add_handler(CommandHandler("backup", backup_wrapper))
    application.add_handler(CommandHandler("export_key", export_key_wrapper))
    application.add_handler(CommandHandler("help", universal_help_command))
    
    # Add conversation handler for switching wallets
    wallets_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("wallets", wallets_wrapper)],
        states={
            SELECTING_WALLET: [CallbackQueryHandler(wallet_selection_callback, pattern=r'^wallet:')],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )
    
    # Add conversation handler for adding a new wallet
    addwallet_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("addwallet", addwallet_wrapper)],
        states={
            ADD_CHOOSING_ACTION: [CallbackQueryHandler(action_choice_callback)],
            ENTERING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_wallet_name)],
            ENTERING_PRIVATE_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_process_private_key)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )
    
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
            CHOOSING_RECOVERY_TYPE: [CallbackQueryHandler(recovery_choice_callback)],
            WAITING_FOR_PRIVATE_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_private_key)],
            WAITING_FOR_MNEMONIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_mnemonic)],
            RECOVERY_ENTERING_WALLET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, recovery_process_wallet_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )
    
    application.add_handler(send_conv_handler)
    application.add_handler(recover_conv_handler)
    application.add_handler(wallets_conv_handler)
    application.add_handler(addwallet_conv_handler)
    
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
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        # Make sure database connection is closed
        db.close_connection()
    except Exception as e:
        logger.error(f"Unhandled exception: {e}")
        logger.error(traceback.format_exc())
        # Make sure database connection is closed
        db.close_connection() 