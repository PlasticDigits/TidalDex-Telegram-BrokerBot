from telegram import Update
from telegram.ext import ContextTypes
import db
import wallet
import logging
import traceback
from wallet.mnemonic import derive_wallet_from_mnemonic
from utils.message_security import send_self_destructing_message

# Enable logging
logger = logging.getLogger(__name__)

async def wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show active wallet information and a summary of all wallets."""
    user_id = update.effective_user.id
    logger.info(f"Wallet command called by user {user_id}")
    
    try:
        # Check if user already has a wallet
        logger.debug(f"Checking if user {user_id} has an existing wallet")
        user_wallet = db.get_user_wallet(user_id)
        logger.debug(f"User wallet result: {user_wallet is not None}")
        
        if not user_wallet:
            # Check if user already has a mnemonic
            existing_mnemonic = db.get_user_mnemonic(user_id)
            
            if existing_mnemonic:
                # User has existing mnemonic, derive wallet with index 0
                logger.info(f"Creating first wallet for user {user_id} from existing mnemonic")
                logger.debug("User has existing mnemonic, deriving new wallet")
                
                # Derive a new wallet from the existing mnemonic (first wallet = index 0)
                new_wallet = derive_wallet_from_mnemonic(existing_mnemonic, index=0)
                
                # Save the wallet
                wallet_to_save = {
                    'address': new_wallet['address'],
                    'private_key': new_wallet['private_key'],
                    'path': new_wallet['path']
                }
                
                # Save wallet
                logger.debug(f"Saving wallet for user {user_id}")
                db.save_user_wallet(user_id, wallet_to_save, "Default")
                logger.debug("Wallet saved successfully")
                
                await update.message.reply_text(
                    "🎉 Your wallet has been created from your existing seed phrase!\n\n"
                    f"Address: <code>{new_wallet['address']}</code>\n\n"
                    "Use /backup to backup your recovery phrase\n"
                    "Use /balance to check your balances\n"
                    "Use /send to send funds\n"
                    "Use /receive to get your address for receiving funds",
                    parse_mode='HTML'
                )
                
                # Suggest setting up a PIN for security
                await update.message.reply_text(
                    "🔐 <b>Security Recommendation</b>\n\n"
                    "For enhanced wallet security, consider setting up a PIN code.\n"
                    "Your PIN will protect sensitive operations and wallet access.\n\n"
                    "Use /set_pin to create your security PIN.",
                    parse_mode='HTML'
                )
            else:
                # Generate a new mnemonic phrase
                logger.info(f"Creating new wallet with new mnemonic for user {user_id}")
                logger.debug("Generating new mnemonic phrase")
                mnemonic = wallet.create_mnemonic()
                logger.debug("Mnemonic generated successfully")
                
                # Create a wallet from the mnemonic
                logger.debug("Creating wallet from mnemonic")
                new_wallet = wallet.create_mnemonic_wallet(mnemonic)
                logger.debug(f"Wallet created with address: {new_wallet['address']}")
                
                # Remove mnemonic from wallet object before saving
                wallet_to_save = {
                    'address': new_wallet['address'],
                    'private_key': new_wallet['private_key'],
                    'path': new_wallet['path']
                }
                
                # Save wallet without mnemonic
                logger.debug(f"Saving wallet for user {user_id}")
                db.save_user_wallet(user_id, wallet_to_save, "Default")
                logger.debug("Wallet saved successfully")
                
                # Save mnemonic separately
                logger.debug("Saving mnemonic separately")
                db.save_user_mnemonic(user_id, mnemonic)
                logger.debug("Mnemonic saved successfully")
                
                # Instead of showing the seed phrase, only show the wallet address
                await update.message.reply_text(
                    "🎉 Your wallet has been created!\n\n"
                    f"Address: <code>{new_wallet['address']}</code>\n\n"
                    "Your recovery phrase is securely stored. Use /backup when you're ready to save it\n"
                    "<b>⚠️ Without your recovery phrase, you will <i>NOT be able to recover your wallet!</i></b>",
                    parse_mode='HTML'
                )
                
                # Send follow-up info message
                await update.message.reply_text(
                    "Use /backup to backup your recovery phrase\n"
                    "Use /balance to check your balances\n"
                    "Use /send to send funds\n"
                    "Use /receive to get your address for receiving funds",
                    parse_mode='HTML'
                )
                
                # Suggest setting up a PIN for security
                await update.message.reply_text(
                    "🔐 <b>Security Recommendation</b>\n\n"
                    "For enhanced wallet security, consider setting up a PIN code.\n"
                    "Your PIN will protect sensitive operations and wallet access.\n\n"
                    "Use /set_pin to create your security PIN.",
                    parse_mode='HTML'
                )
        else:
            logger.info(f"Displaying existing wallet info for user {user_id}")
            # Get all user wallets
            logger.debug("Getting all user wallets")
            user_wallets = db.get_user_wallets(user_id)
            logger.debug(f"Found {len(user_wallets)} wallets")
            
            # Get active wallet name
            active_wallet_name = next((name for name, info in user_wallets.items() if info['is_active']), "Default")
            logger.debug(f"Active wallet: {active_wallet_name}")
            
            # Show all wallets with active wallet highlighted
            wallets_text = "Your wallets:\n"
            for name, info in user_wallets.items():
                prefix = "🔷 " if info['is_active'] else "○ "
                # Use HTML code tags instead of Markdown backticks for code formatting
                address = info['address']
                wallets_text += f"{prefix}{name}: <code>{address}</code>\n"
            
            # Check if user has a master mnemonic
            logger.debug("Checking if user has a mnemonic")
            has_mnemonic = db.get_user_mnemonic(user_id) is not None
            wallet_type = "Seed Phrase Wallet" if has_mnemonic else "Private Key Wallet"
            logger.debug(f"Wallet type: {wallet_type}")
            
            # Show active wallet details with HTML formatting
            logger.debug("Sending wallet info message")
            await update.message.reply_text(
                f"{wallets_text}\n"
                f"Currently active: <b>{active_wallet_name}</b> ({wallet_type})\n\n"
                "Use /wallets to switch between wallets\n"
                "Use /addwallet to add a new wallet\n"
                "Use /balance to check your balances\n"
                "Use /send to send funds\n"
                "Use /receive to get your address for receiving funds",
                parse_mode='HTML'  # Changed from Markdown to HTML
            )
            logger.debug("Wallet info message sent")
    except Exception as e:
        logger.error(f"Error in wallet command: {e}")
        logger.error(traceback.format_exc())
        
        # Notify the user about the error
        try:
            await update.message.reply_text(
                "⚠️ An error occurred while processing your wallet command.\n"
                "Please try again later or contact support."
            )
        except Exception as send_error:
            logger.error(f"Error sending error message: {send_error}")
    
    logger.info("Wallet command completed") 