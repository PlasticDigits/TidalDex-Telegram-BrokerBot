from telegram import Update
from telegram.ext import ContextTypes
import db
from services.wallet import get_active_wallet_name, get_user_wallet
from services.pin import pin_manager
import logging
import qrcode
from io import BytesIO

# Configure module logger
logger = logging.getLogger(__name__)

async def receive_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show receive address."""
    user_id = update.effective_user.id
    wallet_name = get_active_wallet_name(user_id)
    pin = pin_manager.get_pin(user_id)
    
    user_wallet = get_user_wallet(user_id, wallet_name, pin)
    
    if not user_wallet:
        await update.message.reply_text(
            "You don't have a wallet yet. Use /wallet to create one."
        )
        return
    
    wallet_address = user_wallet['address']
    
    # Create QR code
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(wallet_address)
        qr.make(fit=True)
        
        # Create an image from the QR Code
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Save the image to a bytes buffer
        buffer = BytesIO()
        img.save(buffer)
        buffer.seek(0)
        
        # Send QR code image and address
        await update.message.reply_photo(
            photo=buffer,
            caption=f"Wallet: {wallet_name}\n\nYour BNB and BSC tokens receive address:\n\n`{wallet_address}`\n\nShare this address with others to receive funds.",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error creating QR code: {e}")
        # Fallback to text-only if QR code fails
        await update.message.reply_text(
            f"Wallet: {wallet_name}\n\nYour BNB and BSC tokens receive address:\n\n`{wallet_address}`\n\nShare this address with others to receive funds.",
            parse_mode='Markdown'
        ) 