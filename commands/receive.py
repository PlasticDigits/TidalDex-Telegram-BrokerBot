from telegram import Update
from telegram.ext import ContextTypes
from typing import Optional, Dict, Any
from services.wallet import get_active_wallet_name, get_user_wallet
from services.pin import pin_manager
from db.wallet import WalletData
import logging
import qrcode
from io import BytesIO
from db.utils import hash_user_id

# Configure module logger
logger = logging.getLogger(__name__)

async def receive_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show receive address."""
    user = update.effective_user
    if not user:
        logger.error("No effective user found in update")
        return
    
    user_id: int = user.id  
    user_id_str: str = str(user_id) # Convert int to str as expected by the functions
    wallet_name: Optional[str] = get_active_wallet_name(user_id_str)
    pin: Optional[str] = pin_manager.get_pin(user_id)
    
    user_wallet: Optional[WalletData] = get_user_wallet(user_id_str, wallet_name, pin)
    
    message = update.message
    if not message:
        logger.error("No message found in update")
        return
    
    if not user_wallet:
        await message.reply_text(
            "You don't have a wallet yet. Use /wallet to create one."
        )
        return
    
    wallet_address: str = user_wallet['address']
    
    # Create QR code
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
    await message.reply_photo(
        photo=buffer,
        caption=f"Wallet: {wallet_name}\n\nYour active wallet's BNB and BSC tokens receive address:\n\n`{wallet_address}`\n\nShare this address with others to receive funds.",
        parse_mode='Markdown'
    )