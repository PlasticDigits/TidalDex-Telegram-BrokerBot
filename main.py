import os
import logging
import sys
import atexit
import asyncio
import threading
import signal
import time
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler, ContextTypes
from telegram import Update
from telegram.error import Conflict
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
# Import FastAPI server
from services.api import run_api_server
# Import version manager
from services.version import version_manager

# Import command handlers from commands package
from commands.start import start
from commands.wallet import wallet_command
from commands.balance import pin_protected_balance
from commands.receive import receive_command
from commands.send import (
    send_command,
    button_callback, 
    send_bnb_amount, send_bnb_address, 
    send_token_symbol, send_token_amount, send_token_address,
    CHOOSING_ACTION, SEND_BNB_AMOUNT, SEND_BNB_ADDRESS, 
    SEND_TOKEN_SYMBOL, SEND_TOKEN_AMOUNT, SEND_TOKEN_ADDRESS
)
from commands.lock import lock_command
from commands.cancel import cancel
from commands.recover import (
    recover_command,
    recovery_choice_callback, 
    process_mnemonic, process_wallet_name as recovery_process_wallet_name,
    CHOOSING_RECOVERY_TYPE,
    WAITING_FOR_MNEMONIC, ENTERING_WALLET_NAME as RECOVERY_ENTERING_WALLET_NAME
)
from commands.backup import pin_protected_backup
from commands.help import universal_help_command
from commands.wallets import (
    wallets_command, wallet_selection_callback, SELECTING_WALLET
)
from commands.addwallet import (
    action_choice_callback, process_wallet_name, process_private_key as add_process_private_key,
    CHOOSING_ACTION as ADD_CHOOSING_ACTION, ENTERING_NAME, ENTERING_PRIVATE_KEY,
    addwallet_command
)
from commands.export_key import pin_protected_export_key
from commands.rename_wallet import (
    rename_wallet_command, process_new_name, WAITING_FOR_NAME
)
from commands.set_pin import (
    set_pin_command, process_pin, confirm_pin, process_current_pin,
    ENTERING_PIN, CONFIRMING_PIN, ENTERING_CURRENT_PIN
)
# Import track-related commands
from commands.track import track_conv_handler
from commands.track_stop import track_stop_conv_handler
from commands.scan import pin_protected_scan
# Import delete all wallets command
from commands.deletewalletsall import deletewalletsall_conv_handler
# Import swap-related commands
from commands.swap import (
    swap_command, choose_from_token, choose_to_token, handle_custom_token_address,
    enter_amount, enter_slippage, confirm_swap,
    CHOOSING_FROM_TOKEN, CHOOSING_TO_TOKEN, ENTERING_AMOUNT, ENTERING_SLIPPAGE, CONFIRMING_SWAP,
    swap_command
)
# Import X account management command
from commands.x import (
    x_command, x_conv_handler, cancel_x_command, x_action_callback,
    CHOOSING_X_ACTION, WAITING_FOR_OAUTH
)
from services.pin.pin_decorators import PIN_REQUEST, PIN_FAILED, handle_conversation_pin_request

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

# Global application instance for signal handling
application_instance = None
shutdown_event = threading.Event()

def graceful_shutdown(signum: int, frame) -> None:
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {signum}. Initiating graceful shutdown...")
    shutdown_event.set()
    
    if application_instance:
        logger.info("Stopping bot application...")
        try:
            # Schedule the shutdown in the event loop
            loop = None
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # No running loop, create a new one
                pass
            
            if loop and not loop.is_closed():
                # Create shutdown task in existing loop
                def shutdown_task():
                    try:
                        if hasattr(application_instance, 'stop'):
                            asyncio.create_task(application_instance.stop())
                    except Exception as e:
                        logger.error(f"Error scheduling shutdown: {e}")
                
                loop.call_soon_threadsafe(shutdown_task)
            else:
                # Fallback - force stop via updater
                if hasattr(application_instance, 'updater') and application_instance.updater:
                    application_instance.updater.stop()
                    
            logger.info("Bot shutdown initiated")
        except Exception as e:
            logger.error(f"Error stopping application: {e}")
    
    # Close database connections
    try:
        db.close_connection()
        logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Error closing database: {e}")
    
    # Clean up version manager
    try:
        version_manager.cleanup_version()
    except Exception as e:
        logger.error(f"Error cleaning up version manager: {e}")
    
    logger.info("Graceful shutdown completed")
    # Use os._exit to force exit
    os._exit(0)

def setup_signal_handlers() -> None:
    """Setup signal handlers for graceful shutdown."""
    signal.signal(signal.SIGTERM, graceful_shutdown)
    signal.signal(signal.SIGINT, graceful_shutdown)
    # Add SIGUSR1 for custom shutdown signal
    signal.signal(signal.SIGUSR1, graceful_shutdown)
    logger.info("Signal handlers configured")

def start_api_server_thread() -> None:
    """Start the API server in a separate thread."""
    try:
        logger.info("Starting API server thread...")
        run_api_server()
    except Exception as e:
        logger.error(f"Error in API server thread: {e}")
        logger.error(traceback.format_exc())

def main() -> None:
    """Start the bot and API server."""
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
    
    # Initialize application version
    try:
        logger.info("Initializing application version...")
        if not version_manager.initialize_version():
            logger.error("Failed to initialize application version. Exiting.")
            return
        current_version = version_manager.get_current_version()
        logger.info(f"Application version initialized: {current_version}")
    except Exception as e:
        logger.error(f"Version initialization failed: {e}")
        logger.error(traceback.format_exc())
        return
    
    # Start API server in a separate thread
    api_thread = threading.Thread(target=start_api_server_thread, daemon=True)
    api_thread.start()
    logger.info("API server thread started")
    
    # Create the Application
    token = TELEGRAM_BOT_TOKEN
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not found in environment variables!")
        return
    
    application = Application.builder().token(token).build()
    global application_instance
    application_instance = application
    
    setup_signal_handlers()
    
    # Create private chat wrappers for all command handlers
    start_wrapper = create_private_chat_wrapper(start)
    wallet_wrapper = create_private_chat_wrapper(wallet_command)
    receive_wrapper = create_private_chat_wrapper(receive_command)
    wallets_wrapper = create_private_chat_wrapper(wallets_command)
    set_pin_wrapper = create_private_chat_wrapper(set_pin_command)
    rename_wallet_wrapper = create_private_chat_wrapper(rename_wallet_command)
    lock_wrapper = create_private_chat_wrapper(lock_command)

    # private chat wrappers for pin protected commands with ConversationHandler
    swap_wrapper = create_private_chat_wrapper(swap_command)

    # private chat wrappers for pin protected commands
    addwallet_wrapper = create_private_chat_wrapper(addwallet_command)
    export_key_wrapper = create_private_chat_wrapper(pin_protected_export_key)
    send_wrapper = create_private_chat_wrapper(send_command)
    backup_wrapper = create_private_chat_wrapper(pin_protected_backup)
    recover_wrapper = create_private_chat_wrapper(recover_command)
    balance_wrapper = create_private_chat_wrapper(pin_protected_balance)
    scan_wrapper = create_private_chat_wrapper(pin_protected_scan)
    x_wrapper = create_private_chat_wrapper(x_command)

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
    application.add_handler(CommandHandler("scan", scan_wrapper))

    # Add conversation handler for switching wallets
    wallets_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("wallets", wallets_wrapper),CommandHandler("switch", wallets_wrapper)],
        states={
            PIN_REQUEST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_conversation_pin_request)
            ],
            PIN_FAILED: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_conversation_pin_request)
            ],
            #regex should match select_wallet:wallet_name and cancel_wallet_selection
            SELECTING_WALLET: [CallbackQueryHandler(wallet_selection_callback, pattern=r'^(wallets_.*)$')],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Add conversation handler for adding a new wallet
    addwallet_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("addwallet", addwallet_wrapper)],
        states={
            PIN_REQUEST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_conversation_pin_request)
            ],
            PIN_FAILED: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_conversation_pin_request)
            ],
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
            PIN_REQUEST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_conversation_pin_request)
            ],
            PIN_FAILED: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_conversation_pin_request)
            ],
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
            PIN_REQUEST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_conversation_pin_request)
            ],
            PIN_FAILED: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_conversation_pin_request)
            ],
            CHOOSING_RECOVERY_TYPE: [CallbackQueryHandler(recovery_choice_callback, pattern=r'^(recover_.*)$')],
            WAITING_FOR_MNEMONIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_mnemonic)],
            RECOVERY_ENTERING_WALLET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, recovery_process_wallet_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Add conversation handler for renaming wallet
    rename_wallet_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("rename_wallet", rename_wallet_wrapper)],
        states={
            PIN_REQUEST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_conversation_pin_request)
            ],
            PIN_FAILED: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_conversation_pin_request)
            ],
            WAITING_FOR_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_new_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Add conversation handler for setting PIN
    set_pin_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("set_pin", set_pin_wrapper)],
        states={
            PIN_REQUEST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_conversation_pin_request)
            ],
            PIN_FAILED: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_conversation_pin_request)
            ],
            ENTERING_PIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_pin)],
            CONFIRMING_PIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_pin)],
            ENTERING_CURRENT_PIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_current_pin)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Add conversation handler for swapping tokens
    swap_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("swap", swap_wrapper)],
        states={
            PIN_REQUEST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_conversation_pin_request)
            ],
            PIN_FAILED: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_conversation_pin_request)
            ],
            CHOOSING_FROM_TOKEN: [
                CallbackQueryHandler(choose_from_token, pattern=r'^swap_from_.*$'),
                CallbackQueryHandler(choose_from_token, pattern=r'^swap_cancel$')
            ],
            CHOOSING_TO_TOKEN: [
                CallbackQueryHandler(choose_to_token, pattern=r'^swap_to_.*$'),
                CallbackQueryHandler(choose_to_token, pattern=r'^swap_cancel$'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_custom_token_address)
            ],
            ENTERING_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_amount)
            ],
            ENTERING_SLIPPAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_slippage)
            ],
            CONFIRMING_SWAP: [
                CallbackQueryHandler(confirm_swap, pattern=r'^(swap_confirm|swap_cancel)$')
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    application.add_handler(send_conv_handler)
    application.add_handler(recover_conv_handler)
    application.add_handler(wallets_conv_handler)
    application.add_handler(addwallet_conv_handler)
    application.add_handler(rename_wallet_conv_handler)
    application.add_handler(set_pin_conv_handler)
    application.add_handler(swap_conv_handler)
    
    # Add X conversation handler with proper configuration
    x_conv_handler_configured = ConversationHandler(
        entry_points=[CommandHandler("x", x_wrapper)],
        states={
            PIN_REQUEST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_conversation_pin_request)
            ],
            PIN_FAILED: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_conversation_pin_request)
            ],
            CHOOSING_X_ACTION: [
                CallbackQueryHandler(x_action_callback, pattern=r'^x_(connect|view|view_after_connect|disconnect|disconnect_confirm|cancel|back|retry|cleanup_connect)$')
            ],
            WAITING_FOR_OAUTH: [
                CallbackQueryHandler(x_action_callback, pattern=r'^x_(cancel|retry|view_after_connect)$')
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_x_command)],
        name="x_conversation"
    )
    application.add_handler(x_conv_handler_configured)
    
    # Add token tracking handlers
    application.add_handler(track_conv_handler)
    application.add_handler(track_stop_conv_handler)
    
    # Add delete all wallets handler
    application.add_handler(deletewalletsall_conv_handler)
    
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
    
    # Add error handler
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Log the error and send a telegram message to notify the developer."""
        # Log the error before we do anything else
        logger.error("Exception while handling an update:", exc_info=context.error)
        
        # Check if this is a Conflict error indicating another bot instance
        if isinstance(context.error, Conflict):
            logger.warning("Telegram Conflict error detected - checking if another instance has started...")
            
            # Check if this instance's version is still current
            if not version_manager.is_version_current():
                logger.warning("Version check failed during error handling - another instance has started. Shutting down gracefully.")
                # Schedule graceful shutdown
                def shutdown_task():
                    graceful_shutdown(signal.SIGUSR1, None)
                
                # Run shutdown in a thread to avoid blocking the async context
                shutdown_thread = threading.Thread(target=shutdown_task, daemon=True)
                shutdown_thread.start()
                return
            else:
                logger.info("Version check passed - this instance is still current. Conflict may be temporary.")
        
        # Send an error message for non-conflict errors or if version is still current
        if update and hasattr(update, 'effective_message') and update.effective_message:
            try:
                await update.effective_message.reply_text('An error occurred while processing your request.')
            except Exception as e:
                logger.error(f"Failed to send error message to user: {e}")
    
    application.add_error_handler(error_handler)
    
    # Add startup delay to prevent overlapping instances
    startup_delay = int(os.getenv('STARTUP_DELAY', '0'))  # Default 0 seconds
    if startup_delay > 0:
        logger.info(f"Waiting {startup_delay} seconds before starting polling to prevent instance overlap...")
        time.sleep(startup_delay)
    
    # Check if shutdown was requested during startup delay
    if shutdown_event.is_set():
        logger.info("Shutdown requested during startup delay. Exiting.")
        return
    
    # Start the Bot with better error handling
    logger.info("Starting bot polling...")
    try:
        application.run_polling(
            drop_pending_updates=True,  # Clear any pending updates
            close_loop=False,           # Let the application manage the loop
            stop_signals=None           # We handle signals manually
        )
    except Exception as e:
        if "Conflict" in str(e) and "getUpdates" in str(e):
            logger.warning("Bot conflict detected - another instance may be running. Checking version...")
            
            # Check if this instance's version is still current
            if not version_manager.is_version_current():
                logger.warning("Version check failed - another instance has started. Shutting down gracefully.")
                graceful_shutdown(signal.SIGUSR1, None)
                return
            
            logger.info("Version check passed. Waiting before retry...")
            time.sleep(15)  # Wait 15 seconds before potential restart
            if not shutdown_event.is_set():
                logger.info("Retrying bot startup...")
                try:
                    application.run_polling(
                        drop_pending_updates=True,
                        close_loop=False,
                        stop_signals=None
                    )
                except Exception as retry_e:
                    logger.error(f"Retry failed: {retry_e}")
                    
                    # Check version again on retry failure
                    if not version_manager.is_version_current():
                        logger.warning("Version check failed on retry - another instance has started. Shutting down gracefully.")
                        graceful_shutdown(signal.SIGUSR1, None)
                        return
                    
                    raise
        else:
            logger.error(f"Bot polling failed: {e}")
            
            # Check version on any polling failure
            if not version_manager.is_version_current():
                logger.warning("Version check failed after polling error - another instance has started. Shutting down gracefully.")
                graceful_shutdown(signal.SIGUSR1, None)
                return
            
            raise

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