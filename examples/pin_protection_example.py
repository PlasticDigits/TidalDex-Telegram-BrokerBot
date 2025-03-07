"""
Example of using the new PIN protection system in a command handler.

This example demonstrates how to use the require_pin decorator to add
PIN verification to a command handler and how to use the verified PIN
in the command handler.
"""
from telegram import Update
from telegram.ext import ContextTypes
from services.pin import require_pin, pin_manager
import logging

logger = logging.getLogger(__name__)

# Example of a command handler with PIN protection
@require_pin("🔒 This command requires your PIN for security. Please enter your PIN:")
async def sensitive_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Example of a command that requires PIN verification."""
    user_id = update.effective_user.id
    logger.info(f"Sensitive command called by user {user_id}")
    
    # get PIN from PINManager
    pin = pin_manager.get_pin(user_id)
    
    # If PIN verification was required, but no PIN is available, this suggests a bug
    if pin is None and context.user_data.get('pin_required', False):
        logger.error(f"Expected PIN to be available but not found for user {user_id}")
        await update.message.reply_text(
            "❌ Error: PIN verification was required but no PIN is available. Please contact support."
        )
        return
    
    # Use the PIN to perform sensitive operations
    # For example, get a wallet
    try:
        import db
        # The PIN will be passed automatically if available and required
        user_wallet = db.get_user_wallet(user_id, pin=pin)
        
        if user_wallet:
            # Perform sensitive operations with the wallet
            wallet_address = user_wallet.get('address', 'unknown')
            await update.message.reply_text(
                f"✅ PIN verified successfully! Performing sensitive operation...\n\n"
                f"Your wallet address: `{wallet_address}`\n\n"
                f"Your sensitive data is protected with your PIN.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "❌ Could not find your wallet. Please create one first with /wallet."
            )
    except Exception as e:
        logger.error(f"Error in sensitive_command: {e}")
        await update.message.reply_text(
            "❌ An error occurred while processing your request. Please try again later."
        )

# Example of how to register the command in main.py
"""
In main.py:

from examples.pin_protection_example import sensitive_command

# Register the command
application.add_handler(CommandHandler("sensitive", sensitive_command))

# Add a message handler for PIN input
application.add_handler(
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        services.pin.handle_pin_input
    )
)
""" 