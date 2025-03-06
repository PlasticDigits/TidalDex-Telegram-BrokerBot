from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters
import db
import wallet
import logging
import traceback
from wallet.mnemonic import derive_wallet_from_mnemonic
from utils.message_security import send_self_destructing_message

# Enable logging
logger = logging.getLogger(__name__)

# Conversation states
CHOOSING_ACTION, ENTERING_NAME, ENTERING_PRIVATE_KEY = range(3)

# Store temporary data during conversation
user_temp_data = {}

async def addwallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the process to add a new wallet."""
    keyboard = [
        [InlineKeyboardButton("Create New Wallet", callback_data='create_wallet')],
        [InlineKeyboardButton("Import Existing Wallet", callback_data='import_wallet')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "How would you like to add a wallet?", 
        reply_markup=reply_markup
    )
    
    return CHOOSING_ACTION

async def action_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle wallet creation method choice."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    choice = query.data
    
    # Initialize user temp data
    user_temp_data[user_id] = {'action': choice}
    
    await query.edit_message_text("Please enter a name for this wallet:")
    
    return ENTERING_NAME

async def process_wallet_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the wallet name."""
    user_id = update.effective_user.id
    wallet_name = update.message.text.strip()
    
    # Check if user has temp data
    if user_id not in user_temp_data:
        await update.message.reply_text("Something went wrong. Please try again with /addwallet.")
        return ConversationHandler.END
    
    # Check if name is valid
    if not wallet_name or len(wallet_name) > 32:
        await update.message.reply_text("Wallet name must be between 1 and 32 characters. Please try again:")
        return ENTERING_NAME
    
    # Check if wallet with this name already exists
    existing_wallets = db.get_user_wallets(user_id)
    if wallet_name in existing_wallets:
        await update.message.reply_text(f"A wallet with name '{wallet_name}' already exists. Please choose a different name:")
        return ENTERING_NAME
    
    # Store wallet name
    user_temp_data[user_id]['wallet_name'] = wallet_name
    
    # Process based on action
    if user_temp_data[user_id]['action'] == 'create_wallet':
        try:
            # Check if user already has a mnemonic
            existing_mnemonic = db.get_user_mnemonic(user_id)
            
            if existing_mnemonic:
                # User has existing mnemonic, derive wallet with next index
                logger.debug("User has existing mnemonic, deriving new wallet")
                
                # Get current wallet count to use as index
                existing_wallets = db.get_user_wallets(user_id)
                wallet_index = len(existing_wallets)
                
                # Derive a new wallet from the existing mnemonic
                new_wallet = derive_wallet_from_mnemonic(existing_mnemonic, index=wallet_index)
                
                # Save the wallet
                wallet_to_save = {
                    'address': new_wallet['address'],
                    'private_key': new_wallet['private_key'],
                    'path': new_wallet['path']
                }
                
                # Save wallet
                db.save_user_wallet(user_id, wallet_to_save, wallet_name)
                
                # Normal message since no seed phrase is shown
                await update.message.reply_text(
                    f"🎉 New wallet '{wallet_name}' created from your existing seed phrase!\n\n"
                    f"Address: `{new_wallet['address']}`\n\n"
                    "This wallet is derived from your existing seed phrase, which you can recover using /backup.",
                    parse_mode='Markdown'
                )
            else:
                # User doesn't have a mnemonic, create a new one
                logger.debug("User has no mnemonic, creating new one")
                mnemonic = wallet.create_mnemonic()
                
                # Create a new wallet from the mnemonic
                new_wallet = wallet.create_mnemonic_wallet(mnemonic)
                
                # Remove mnemonic from wallet object before saving
                wallet_to_save = {
                    'address': new_wallet['address'],
                    'private_key': new_wallet['private_key'],
                    'path': new_wallet['path']
                }
                
                # Save wallet
                db.save_user_wallet(user_id, wallet_to_save, wallet_name)
                
                # Save mnemonic separately
                db.save_user_mnemonic(user_id, mnemonic)
                
                # Send self-destructing message with seed phrase
                message_text = (
                    f"🎉 New wallet '{wallet_name}' created with new seed phrase!\n\n"
                    f"Address: `{new_wallet['address']}`\n\n"
                    f"Seed Phrase: `{mnemonic}`\n\n"
                    "⚠️ IMPORTANT: Write down and save your seed phrase somewhere safe.\n"
                    "Anyone with access to your seed phrase can access your wallet.\n"
                    "Your wallet is encrypted but cannot be recovered without this phrase."
                )
                
                await send_self_destructing_message(
                    update,
                    message_text,
                    parse_mode='Markdown'
                )
        except Exception as e:
            logger.error(f"Error creating wallet: {e}")
            logger.error(traceback.format_exc())
            await update.message.reply_text(
                "❌ Error creating wallet. Please try again with /addwallet.\n"
                f"Error: {str(e)}"
            )
            
        # Clean up temp data
        del user_temp_data[user_id]
        return ConversationHandler.END
    else:
        # Import wallet from private key
        await update.message.reply_text(
            "Please enter the private key for this wallet:\n\n"
            "⚠️ WARNING: Never share your private keys with anyone!"
        )
        return ENTERING_PRIVATE_KEY

async def process_private_key(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the private key for wallet import."""
    user_id = update.effective_user.id
    private_key = update.message.text.strip()
    
    # Delete the message with private key for security
    try:
        await update.message.delete()
    except Exception as e:
        logger.warning(f"Could not delete message with private key: {e}")
    
    # Check if user has temp data
    if user_id not in user_temp_data:
        await update.message.reply_text("Something went wrong. Please try again with /addwallet.")
        return ConversationHandler.END
    
    wallet_name = user_temp_data[user_id]['wallet_name']
    
    try:
        # Validate and import the private key
        from eth_account import Account
        
        if not private_key.startswith('0x'):
            private_key = '0x' + private_key
        
        account = Account.from_key(private_key)
        address = account.address
        
        # Create wallet object
        imported_wallet = {
            'address': address,
            'private_key': private_key
        }
        
        # Save the wallet
        db.save_user_wallet(user_id, imported_wallet, wallet_name)
        
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"✅ Wallet '{wallet_name}' imported successfully!\n\n"
                 f"Address: `{address}`\n\n"
                 "Your wallet has been encrypted and stored securely.",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error importing wallet: {e}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ Error importing wallet: Invalid private key format. Please try again with /addwallet."
        )
    
    # Clean up temp data
    del user_temp_data[user_id]
    return ConversationHandler.END 