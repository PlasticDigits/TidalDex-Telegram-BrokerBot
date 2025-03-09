import os
import logging
import sys
import atexit
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler, ContextTypes
from telegram import Update
import traceback

from warnings import filterwarnings
from telegram.warnings import PTBUserWarning

# Import custom modules
from utils.chat import create_private_chat_wrapper
from utils.config import TELEGRAM_BOT_TOKEN
from utils.self_destruction_message import (
    show_sensitive_information, delete_sensitive_information,
    SHOW_SENSITIVE_INFO, DELETE_NOW
)
# Import PIN management system
from services.pin import handle_pin_input
# Import restructured database module
import db
# Import balance tracking utilities
from utils.balance_tracker import setup_periodic_balance_updates

# Import command handlers from commands package
from commands.start import start
from commands.wallet import wallet_command
from commands.balance import balance_command
from commands.receive import receive_command
from commands.send import (
    button_callback, 
    send_bnb_amount, send_bnb_address, 
    send_token_symbol, send_token_amount, send_token_address,
    CHOOSING_ACTION, SEND_BNB_AMOUNT, SEND_BNB_ADDRESS, 
    SEND_TOKEN_SYMBOL, SEND_TOKEN_AMOUNT, SEND_TOKEN_ADDRESS,
    pin_protected_send
)
from commands.lock import lock_command
from commands.cancel import cancel
from commands.recover import (
    recovery_choice_callback, process_private_key, 
    process_mnemonic, process_wallet_name as recovery_process_wallet_name,
    pin_protected_recover, CHOOSING_RECOVERY_TYPE, WAITING_FOR_PRIVATE_KEY,
    WAITING_FOR_MNEMONIC, ENTERING_WALLET_NAME as RECOVERY_ENTERING_WALLET_NAME
)
from commands.backup import pin_protected_backup
from commands.help import universal_help_command
from commands.wallets import wallets_command, wallet_selection_callback, SELECTING_WALLET
from commands.addwallet import (
    action_choice_callback, process_wallet_name, process_private_key as add_process_private_key,
    CHOOSING_ACTION as ADD_CHOOSING_ACTION, ENTERING_NAME, ENTERING_PRIVATE_KEY,
    pin_protected_addwallet
)
from commands.export_key import pin_protected_export_key
from commands.rename_wallet import rename_wallet_command, process_new_name, WAITING_FOR_NAME
from commands.set_pin import (
    set_pin_command, process_pin, confirm_pin, process_current_pin,
    ENTERING_PIN, CONFIRMING_PIN, ENTERING_CURRENT_PIN
)
# Import track-related commands
from commands.track import track_conv_handler
from commands.track_stop import track_stop_conv_handler
from commands.track_view import track_view_conv_handler


filterwarnings(action="ignore", message=r".*CallbackQueryHandler", category=PTBUserWarning)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log')
    ]
)
# Set specific module log levels
logging.getLogger('httpx').setLevel(logging.ERROR)  # Disable httpx request logs
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
    wallets_wrapper = create_private_chat_wrapper(wallets_command)
    set_pin_wrapper = create_private_chat_wrapper(set_pin_command)
    rename_wallet_wrapper = create_private_chat_wrapper(rename_wallet_command)
    lock_wrapper = create_private_chat_wrapper(lock_command)

    # private chat wrappers for pin protected commands
    addwallet_wrapper = create_private_chat_wrapper(pin_protected_addwallet)
    export_key_wrapper = create_private_chat_wrapper(pin_protected_export_key)
    send_wrapper = create_private_chat_wrapper(pin_protected_send)
    backup_wrapper = create_private_chat_wrapper(pin_protected_backup)
    recover_wrapper = create_private_chat_wrapper(pin_protected_recover)

    # Add command handlers for public commands
    application.add_handler(CommandHandler("start", start_wrapper))
    application.add_handler(CommandHandler("help", universal_help_command))
    
    # Add handlers for private commands
    application.add_handler(CommandHandler("wallet", wallet_wrapper))
    application.add_handler(CommandHandler("balance", balance_wrapper))
    application.add_handler(CommandHandler("receive", receive_wrapper))
    application.add_handler(CommandHandler("rename", rename_wallet_wrapper))
    application.add_handler(CommandHandler("lock", lock_wrapper))
    application.add_handler(CommandHandler("backup", backup_wrapper))
    application.add_handler(CommandHandler("export_key", export_key_wrapper))

    # Add conversation handler for switching wallets
    wallets_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("wallets", wallets_wrapper)],
        states={
            #regex should match select_wallet:wallet_name and cancel_wallet_selection
            SELECTING_WALLET: [CallbackQueryHandler(wallet_selection_callback, pattern=r'^(wallets_.*)$')],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Add conversation handler for adding a new wallet
    addwallet_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("addwallet", addwallet_wrapper)],
        states={
            ADD_CHOOSING_ACTION: [
                CallbackQueryHandler(action_choice_callback, pattern=r'^(addwallet_.*)$')
            ],
            ENTERING_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_wallet_name)
            ],
            ENTERING_PRIVATE_KEY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_process_private_key)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="addwallet_conversation"
    )
    
    # Add conversation handler for sending funds
    send_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("send", send_wrapper)],
        states={
            CHOOSING_ACTION: [CallbackQueryHandler(button_callback, pattern=r'^(send_.*)$')],
            SEND_BNB_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_bnb_amount)],
            SEND_BNB_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_bnb_address)],
            SEND_TOKEN_SYMBOL: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_token_symbol)],
            SEND_TOKEN_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_token_amount)],
            SEND_TOKEN_ADDRESS: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_token_address)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Add conversation handler for wallet recovery
    recover_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("recover", recover_wrapper)],
        states={
            CHOOSING_RECOVERY_TYPE: [CallbackQueryHandler(recovery_choice_callback, pattern=r'^(recover_.*)$')],
            WAITING_FOR_PRIVATE_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_private_key)],
            WAITING_FOR_MNEMONIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_mnemonic)],
            RECOVERY_ENTERING_WALLET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, recovery_process_wallet_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Add conversation handler for renaming wallet
    rename_wallet_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("rename_wallet", rename_wallet_wrapper)],
        states={
            WAITING_FOR_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_new_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Add conversation handler for setting PIN
    set_pin_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("set_pin", set_pin_wrapper)],
        states={
            ENTERING_PIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_pin)],
            CONFIRMING_PIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_pin)],
            ENTERING_CURRENT_PIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_current_pin)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    application.add_handler(send_conv_handler)
    application.add_handler(recover_conv_handler)
    application.add_handler(wallets_conv_handler)
    application.add_handler(addwallet_conv_handler)
    application.add_handler(rename_wallet_conv_handler)
    application.add_handler(set_pin_conv_handler)
    
    # Add token tracking handlers
    application.add_handler(track_conv_handler)
    application.add_handler(track_stop_conv_handler)
    application.add_handler(track_view_conv_handler)
    
    # Add handlers for sensitive message buttons (self-destructing messages)
    logger.info(f"Registering sensitive message button handlers with patterns: '{SHOW_SENSITIVE_INFO}' and '{DELETE_NOW}'")
    application.add_handler(CallbackQueryHandler(
        show_sensitive_information, 
        pattern=f"^{SHOW_SENSITIVE_INFO}"
    ))
    application.add_handler(CallbackQueryHandler(
        delete_sensitive_information, 
        pattern=f"^{DELETE_NOW}"
    ))
    
    # Add handler for PIN input
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & ~filters.REPLY,
        handle_pin_input
    ))
    
    # Setup periodic balance updates for tracked tokens
    setup_periodic_balance_updates(application)
    
    # Add error handler
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Log the error and send a telegram message to notify the developer."""
        # Log the error before we do anything else
        logger.error("Exception while handling an update:", exc_info=context.error)
        
        # Send an error message
        if update and hasattr(update, 'effective_message') and update.effective_message:
            await update.effective_message.reply_text('An error occurred while processing your request.')
    
    application.add_error_handler(error_handler)

    #DEBUGGING
    # Add this near the end of your main() function, before application.run_polling()
    async def debug_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Debug callback to see if button clicks are being captured."""
        query = update.callback_query
        logger.info(f"DEBUG: Received callback with data: {query.data}")
        
        # Check if this is one of our wallet buttons
        if query.data in ['create_wallet', 'import_wallet']:
            logger.info("This is a wallet creation button!")
        
        await query.answer(text=f"Button click detected: {query.data}")
        
        # For testing, try to manually trigger the action_choice_callback
        if query.data in ['create_wallet', 'import_wallet']:
            from commands.addwallet import action_choice_callback
            try:
                logger.info("Manually calling action_choice_callback")
                await action_choice_callback(update, context)
            except Exception as e:
                logger.error(f"Error calling action_choice_callback: {e}")
                logger.error(traceback.format_exc())
    # Add this handler AFTER all your conversation handlers
    application.add_handler(CallbackQueryHandler(debug_callback))
    
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