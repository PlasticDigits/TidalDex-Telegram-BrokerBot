"""
X (Twitter) account connection command handler.
"""
import logging
import asyncio
import time
import hashlib
import base64
import secrets
from typing import Optional, Dict, Any, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters
from urllib.parse import urlencode

from utils.config import X_CLIENT_ID, X_CLIENT_SECRET, X_REDIRECT_URI, X_SCOPES
from services.api import create_oauth_state, get_oauth_state_data, cleanup_oauth_state
from services.pin import pin_protected
from db import (
    save_x_account_connection, get_x_account_connection, 
    delete_x_account_connection, has_x_account_connection,
    cleanup_corrupted_x_account,
)
from requests_oauth2client import OAuth2Client
import httpx

# Configure logging
logger = logging.getLogger(__name__)

# Conversation states
CHOOSING_X_ACTION = "choosing_x_action"
WAITING_FOR_OAUTH = "waiting_for_oauth"

# Store PKCE verifiers temporarily
pkce_verifiers: Dict[str, str] = {}

def generate_pkce_challenge() -> Tuple[str, str]:
    """
    Generate PKCE code verifier and challenge.
    
    Returns:
        Tuple of (code_verifier, code_challenge)
    """
    # Generate code verifier (43-128 characters, base64url)
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
    
    # Generate code challenge (SHA256 hash of verifier, base64url encoded)
    digest = hashlib.sha256(code_verifier.encode('utf-8')).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode('utf-8').rstrip('=')
    
    return code_verifier, code_challenge

# X OAuth client
def get_x_oauth_client() -> OAuth2Client:
    """Get configured X OAuth2 client."""
    return OAuth2Client(
        token_endpoint="https://api.twitter.com/2/oauth2/token",
        authorization_endpoint="https://twitter.com/i/oauth2/authorize",
        redirect_uri=X_REDIRECT_URI,
        client_id=X_CLIENT_ID,
        client_secret=X_CLIENT_SECRET,
    )

@pin_protected
async def x_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Handle the /x command to manage X (Twitter) account connections.
    
    Args:
        update: Telegram update object
        context: Telegram context object
        
    Returns:
        Next conversation state
    """
    if not update.effective_user or not update.message:
        return ConversationHandler.END
    
    user_id = update.effective_user.id
    
    try:
        # Check if user has an existing X connection with detailed logging
        logger.info(f"Checking X account connection for user {user_id}")
        has_connection = has_x_account_connection(user_id)
        logger.info(f"Connection check result for user {user_id}: {has_connection}")
        
        # Create action buttons
        keyboard = []
        
        if has_connection:
            keyboard.extend([
                [InlineKeyboardButton("👀 View Connected Account", callback_data="x_view")],
                [InlineKeyboardButton("🔄 Reconnect Account", callback_data="x_connect")],
                [InlineKeyboardButton("❌ Disconnect Account", callback_data="x_disconnect")]
            ])
            message_text = (
                "🐦 <b>X Account Management</b>\n\n"
                "✅ You have an X account connected!\n\n"
                "Choose an action:"
            )
        else:
            keyboard.extend([
                [InlineKeyboardButton("🔗 Connect X Account", callback_data="x_connect")]
            ])
            message_text = (
                "🐦 <b>X Account Management</b>\n\n"
                "❌ No X account connected.\n\n"
                "Connect your X account to enable X-related features!\n\n"
                "Choose an action:"
            )
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_html(message_text, reply_markup=reply_markup)
        return CHOOSING_X_ACTION
        
    except Exception as e:
        logger.error(f"Error in x_command for user {user_id}: {e}")
        await update.message.reply_html(
            "❌ An error occurred while processing your request. Please try again."
        )
        return ConversationHandler.END

async def x_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Handle X action button callbacks.
    
    Args:
        update: Telegram update object
        context: Telegram context object
        
    Returns:
        Next conversation state
    """
    query = update.callback_query
    if not query or not query.data or not update.effective_user:
        return ConversationHandler.END
    
    await query.answer()
    user_id = update.effective_user.id
    action = query.data
    
    try:
        if action == "x_connect":
            return await handle_x_connect(update, context)
        elif action == "x_view":
            return await handle_x_view(update, context)
        elif action == "x_view_after_connect":
            # Handle viewing account after successful OAuth connection
            # First, end the current conversation and start a fresh one
            return await handle_x_view(update, context)
        elif action == "x_disconnect":
            return await handle_x_disconnect(update, context)
        elif action == "x_retry":
            # Restart the x command from the beginning
            return await x_command_callback(update, context)
        elif action == "x_back":
            # Go back to main menu
            return await x_command_callback(update, context)
        elif action == "x_cancel":
            await query.edit_message_text("❌ X account management cancelled.")
            return ConversationHandler.END
        elif action == "x_cleanup_connect":
            return await handle_x_cleanup_connect(update, context)
        elif action == "x_disconnect_confirm":
            return await handle_x_disconnect_confirm(update, context)
        else:
            await query.edit_message_text("❌ Unknown action. Please try again.")
            return ConversationHandler.END
            
    except Exception as e:
        logger.error(f"Error in x_action_callback: {e}")
        await query.edit_message_text(
            "❌ An error occurred while processing your request. Please try again."
        )
        return ConversationHandler.END

async def x_command_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Callback version of x_command that works with query updates.
    
    Args:
        update: Telegram update object
        context: Telegram context object
        
    Returns:
        Next conversation state
    """
    query = update.callback_query
    if not query or not update.effective_user:
        return ConversationHandler.END
    
    user_id = update.effective_user.id
    
    try:
        # Check if user has an existing X connection with detailed logging
        logger.info(f"Checking X account connection for user {user_id}")
        has_connection = has_x_account_connection(user_id)
        logger.info(f"Connection check result for user {user_id}: {has_connection}")
        
        # Create action buttons
        keyboard = []
        
        if has_connection:
            keyboard.extend([
                [InlineKeyboardButton("👀 View Connected Account", callback_data="x_view")],
                [InlineKeyboardButton("🔄 Reconnect Account", callback_data="x_connect")],
                [InlineKeyboardButton("❌ Disconnect Account", callback_data="x_disconnect")]
            ])
            message_text = (
                "🐦 <b>X Account Management</b>\n\n"
                "✅ You have an X account connected!\n\n"
                "Choose an action:"
            )
        else:
            keyboard.extend([
                [InlineKeyboardButton("🔗 Connect X Account", callback_data="x_connect")]
            ])
            message_text = (
                "🐦 <b>X Account Management</b>\n\n"
                "❌ No X account connected.\n\n"
                "Connect your X account to enable X-related features!\n\n"
                "Choose an action:"
            )
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='HTML')
        return CHOOSING_X_ACTION
        
    except Exception as e:
        logger.error(f"Error in x_command_callback for user {user_id}: {e}")
        await query.edit_message_text(
            "❌ An error occurred while processing your request. Please try again."
        )
        return ConversationHandler.END
            
    except Exception as e:
        logger.error(f"Error in x_action_callback: {e}")
        await query.edit_message_text(
            "❌ An error occurred while processing your request. Please try again."
        )
        return ConversationHandler.END

async def handle_x_connect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Handle X account connection.
    
    Args:
        update: Telegram update object
        context: Telegram context object
        
    Returns:
        Next conversation state
    """
    query = update.callback_query
    if not query or not update.effective_user:
        return ConversationHandler.END
    
    user_id = update.effective_user.id
    chat_id = query.message.chat_id if query.message else update.effective_chat.id
    
    try:
        # Create OAuth state
        state = create_oauth_state(user_id, chat_id)
        
        # Generate PKCE parameters
        code_verifier, code_challenge = generate_pkce_challenge()
        
        # Store code verifier for later use during token exchange
        pkce_verifiers[state] = code_verifier
        
        # Build authorization URL with PKCE
        auth_params = {
            'response_type': 'code',
            'client_id': X_CLIENT_ID,
            'redirect_uri': X_REDIRECT_URI,
            'scope': X_SCOPES,
            'state': state,
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
        }
        
        auth_url = f"https://twitter.com/i/oauth2/authorize?{urlencode(auth_params)}"
        
        # Store state in context for later use
        context.user_data['oauth_state'] = state
        
        # Create button to open authorization URL
        keyboard = [
            [InlineKeyboardButton("🔗 Connect to X", url=auth_url)],
            [InlineKeyboardButton("❌ Cancel", callback_data="x_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message_text = (
            "🐦 <b>Connect Your X Account</b>\n\n"
            "1️⃣ Click the button below to authorize the TidalDex Bot\n"
            "2️⃣ Sign in to your X account if needed\n"
            "3️⃣ Grant the requested permissions\n"
            "4️⃣ Return here and wait for confirmation\n\n"
            "⏰ This authorization will expire in 5 minutes."
        )
        
        await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='HTML')
        
        # Start polling for OAuth completion
        asyncio.create_task(poll_oauth_completion(context, user_id, chat_id, state, query.message.message_id))
        
        return WAITING_FOR_OAUTH
        
    except Exception as e:
        logger.error(f"Error in handle_x_connect: {e}")
        await query.edit_message_text(
            "❌ An error occurred while setting up OAuth. Please try again."
        )
        return ConversationHandler.END

async def handle_x_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Handle viewing connected X account.
    
    Args:
        update: Telegram update object
        context: Telegram context object
        
    Returns:
        Next conversation state
    """
    query = update.callback_query
    if not query or not update.effective_user:
        return ConversationHandler.END
    
    user_id = update.effective_user.id
    
    try:
        # Get user's PIN from context (should be available from pin_protected decorator)
        pin = context.user_data.get('pin') if context.user_data else None
        
        # If no PIN in context but user needs one, we need to handle this gracefully
        if not pin:
            # Check if user actually needs a PIN
            from services.pin.PINManager import pin_manager
            if pin_manager.needs_pin(user_id):
                # User needs PIN but we don't have it - should restart the command flow
                keyboard = [
                    [InlineKeyboardButton("🔄 Restart /x Command", callback_data="x_retry")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="x_cancel")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    "🔐 <b>PIN Required</b>\n\n"
                    "Your account requires PIN verification to view X account details.\n"
                    "Please restart the /x command to enter your PIN.",
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
                return CHOOSING_X_ACTION
        
        # Get X account connection
        x_account = get_x_account_connection(user_id, pin)
        
        if not x_account:
            # Check if there's a corrupted record
            logger.warning(f"Could not retrieve X account for user {user_id}, checking for corruption")
            
            # Offer to clean up corrupted data
            keyboard = [
                [InlineKeyboardButton("🔧 Clean Up & Reconnect", callback_data="x_cleanup_connect")],
                [InlineKeyboardButton("◀️ Back", callback_data="x_back")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "⚠️ <b>X Account Connection Issue</b>\n\n"
                "There seems to be an issue with your X account data.\n"
                "This might be due to:\n"
                "• Data corruption\n"
                "• PIN mismatch\n"
                "• Invalid encryption\n\n"
                "Would you like to clean up the corrupted data and reconnect?",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            return CHOOSING_X_ACTION
        
        # Format connection info
        connected_at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(x_account.get('connected_at', 0)))
        last_updated = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(x_account.get('last_updated', 0)))
        
        message_text = (
            f"🐦 <b>Connected X Account</b>\n\n"
            f"👤 <b>Username:</b> @{x_account.get('x_username', 'Unknown')}\n"
            f"📝 <b>Display Name:</b> {x_account.get('x_display_name', 'Not provided')}\n"
            f"🆔 <b>User ID:</b> {x_account.get('x_user_id', 'Unknown')}\n"
            f"🔐 <b>Scopes:</b> {x_account.get('scope', 'Unknown')}\n"
            f"📅 <b>Connected:</b> {connected_at}\n"
            f"🔄 <b>Last Updated:</b> {last_updated}\n\n"
            f"✅ Your X account is successfully connected!"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔄 Reconnect", callback_data="x_connect")],
            [InlineKeyboardButton("❌ Disconnect", callback_data="x_disconnect")],
            [InlineKeyboardButton("◀️ Back", callback_data="x_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='HTML')
        return CHOOSING_X_ACTION
        
    except Exception as e:
        logger.error(f"Error in handle_x_view: {e}")
        await query.edit_message_text(
            "❌ An error occurred while retrieving account information. Please try again."
        )
        return ConversationHandler.END

async def handle_x_disconnect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Handle X account disconnection.
    
    Args:
        update: Telegram update object
        context: Telegram context object
        
    Returns:
        Next conversation state
    """
    query = update.callback_query
    if not query or not update.effective_user:
        return ConversationHandler.END
    
    user_id = update.effective_user.id
    
    try:
        # Confirm disconnection
        keyboard = [
            [InlineKeyboardButton("✅ Yes, Disconnect", callback_data="x_disconnect_confirm")],
            [InlineKeyboardButton("❌ Cancel", callback_data="x_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        message_text = (
            "⚠️ <b>Disconnect X Account</b>\n\n"
            "Are you sure you want to disconnect your X account?\n\n"
            "This will:\n"
            "• Remove your stored X credentials\n"
            "• Disable X-related features\n"
            "• Require re-authentication to reconnect\n\n"
            "This action cannot be undone."
        )
        
        await query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='HTML')
        return CHOOSING_X_ACTION
        
    except Exception as e:
        logger.error(f"Error in handle_x_disconnect: {e}")
        await query.edit_message_text(
            "❌ An error occurred. Please try again."
        )
        return ConversationHandler.END

async def handle_x_disconnect_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Handle confirmed X account disconnection.
    
    Args:
        update: Telegram update object
        context: Telegram context object
        
    Returns:
        Next conversation state
    """
    query = update.callback_query
    if not query or not update.effective_user:
        return ConversationHandler.END
    
    user_id = update.effective_user.id
    
    try:
        # Delete X account connection
        success = delete_x_account_connection(user_id)
        
        if success:
            await query.edit_message_text(
                "✅ <b>X Account Disconnected</b>\n\n"
                "Your X account has been successfully disconnected.\n"
                "You can reconnect anytime using the /x command.",
                parse_mode='HTML'
            )
        else:
            await query.edit_message_text(
                "❌ Failed to disconnect X account. Please try again."
            )
        
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error in handle_x_disconnect_confirm: {e}")
        await query.edit_message_text(
            "❌ An error occurred while disconnecting. Please try again."
        )
        return ConversationHandler.END

async def handle_x_cleanup_connect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Handle cleaning up corrupted X account data and reconnecting.
    
    Args:
        update: Telegram update object
        context: Telegram context object
        
    Returns:
        Next conversation state
    """
    query = update.callback_query
    if not query or not update.effective_user:
        return ConversationHandler.END
    
    user_id = update.effective_user.id
    
    try:
        # Attempt to clean up corrupted data
        success = cleanup_corrupted_x_account(user_id)
        
        if success:
            await query.edit_message_text(
                "✅ <b>Corrupted X Account Data Cleaned</b>\n\n"
                "Your corrupted X account data has been cleaned up.\n"
                "You can now try to reconnect your X account.",
                parse_mode='HTML'
            )
            # Restart the x command to show fresh options
            return await x_command_callback(update, context)
        else:
            await query.edit_message_text(
                "❌ Failed to clean up corrupted data. Please try again."
            )
            return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Error in handle_x_cleanup_connect: {e}")
        await query.edit_message_text(
            "❌ An error occurred while cleaning up corrupted data. Please try again."
        )
        return ConversationHandler.END

async def poll_oauth_completion(
    context: ContextTypes.DEFAULT_TYPE, 
    user_id: int, 
    chat_id: int, 
    state: str, 
    message_id: int
) -> None:
    """
    Poll for OAuth completion and handle token exchange.
    
    Args:
        context: Telegram context object
        user_id: User ID
        chat_id: Chat ID
        state: OAuth state
        message_id: Message ID to update
    """
    try:
        # Poll for up to 5 minutes
        for _ in range(60):  # 60 attempts with 5-second intervals
            await asyncio.sleep(5)
            
            state_data = get_oauth_state_data(state)
            if not state_data:
                logger.warning(f"State data not found for polling: {state}")
                break
            
            if state_data.get('status') == 'completed' and state_data.get('authorization_code'):
                # Exchange code for tokens
                success = await exchange_oauth_code(
                    user_id, 
                    state_data['authorization_code'], 
                    state,
                    context
                )
                
                if success:
                    # Update message with success and create button to restart /x command
                    try:
                        keyboard = [
                            [InlineKeyboardButton("👀 View Account Details", callback_data="x_view_after_connect")]
                        ]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        
                        await context.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=(
                                "✅ <b>X Account Connected Successfully!</b>\n\n"
                                "Your X account has been connected and is ready to use.\n"
                                "Click the button below to view your connection details."
                            ),
                            reply_markup=reply_markup,
                            parse_mode='HTML'
                        )
                    except Exception as e:
                        logger.error(f"Error updating success message: {e}")
                else:
                    # Update message with error and provide retry option
                    try:
                        keyboard = [
                            [InlineKeyboardButton("🔄 Try Again", callback_data="x_retry")]
                        ]
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        
                        await context.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=(
                                "❌ <b>Connection Failed</b>\n\n"
                                "Failed to connect your X account. This might be due to:\n"
                                "• Authorization was denied\n"
                                "• Token exchange failed\n"
                                "• Network issues\n\n"
                                "Please try connecting again."
                            ),
                            reply_markup=reply_markup,
                            parse_mode='HTML'
                        )
                    except Exception as e:
                        logger.error(f"Error updating error message: {e}")
                
                # Clean up state
                cleanup_oauth_state(state)
                break
        else:
            # Timeout - provide retry option
            try:
                keyboard = [
                    [InlineKeyboardButton("🔄 Try Again", callback_data="x_retry")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=(
                        "⏰ <b>Authorization Timeout</b>\n\n"
                        "The authorization process timed out after 5 minutes.\n"
                        "This might happen if:\n"
                        "• You didn't complete the authorization\n"
                        "• There were network issues\n"
                        "• The authorization page was closed\n\n"
                        "Please try connecting again."
                    ),
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Error updating timeout message: {e}")
            
            cleanup_oauth_state(state)
            
    except Exception as e:
        logger.error(f"Error in poll_oauth_completion: {e}")
        cleanup_oauth_state(state)

async def exchange_oauth_code(
    user_id: int, 
    authorization_code: str, 
    state: str,
    context: ContextTypes.DEFAULT_TYPE
) -> bool:
    """
    Exchange authorization code for access token and save user data.
    
    Args:
        user_id: User ID
        authorization_code: OAuth authorization code
        state: OAuth state
        context: Telegram context object
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Get stored code verifier
        code_verifier = pkce_verifiers.get(state)
        if not code_verifier:
            logger.error(f"Code verifier not found for state: {state}")
            return False
        
        # Exchange code for token using PKCE
        token_data = {
            'grant_type': 'authorization_code',
            'client_id': X_CLIENT_ID,
            'code': authorization_code,
            'redirect_uri': X_REDIRECT_URI,
            'code_verifier': code_verifier
        }
        
        # Create Basic auth header with client credentials
        auth_string = f"{X_CLIENT_ID}:{X_CLIENT_SECRET}"
        auth_bytes = auth_string.encode('utf-8')
        auth_header = base64.b64encode(auth_bytes).decode('utf-8')
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                'https://api.twitter.com/2/oauth2/token',
                data=token_data,
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Authorization': f'Basic {auth_header}'
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to exchange code for token: {response.status_code} - {response.text}")
                return False
            
            token_response = response.json()
            access_token = token_response.get('access_token')
            
            if not access_token:
                logger.error("No access token in response")
                return False
        
        # Get user info from X API
        async with httpx.AsyncClient() as client:
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            
            response = await client.get(
                'https://api.twitter.com/2/users/me?user.fields=id,username,name,profile_image_url',
                headers=headers
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to get user info from X API: {response.status_code}")
                return False
            
            user_data = response.json()
            x_user_info = user_data.get('data', {})
        
        # Get user's PIN from context
        pin = context.user_data.get('pin')
        
        # Save X account connection
        success = save_x_account_connection(
            user_id=user_id,
            x_user_id=x_user_info.get('id'),
            x_username=x_user_info.get('username'),
            access_token=access_token,
            refresh_token=token_response.get('refresh_token'),
            token_expires_at=token_response.get('expires_in'),
            scope=X_SCOPES,
            x_display_name=x_user_info.get('name'),
            x_profile_image_url=x_user_info.get('profile_image_url'),
            pin=pin
        )
        
        # Clean up the code verifier
        pkce_verifiers.pop(state, None)
        
        if success:
            logger.info(f"Successfully saved X account connection for user {user_id}")
            return True
        else:
            logger.error(f"Failed to save X account connection for user {user_id}")
            return False
            
    except Exception as e:
        logger.error(f"Error in exchange_oauth_code: {e}")
        # Clean up the code verifier on error
        pkce_verifiers.pop(state, None)
        return False

async def cancel_x_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancel the X command conversation.
    
    Args:
        update: Telegram update object
        context: Telegram context object
        
    Returns:
        ConversationHandler.END
    """
    if update.message:
        await update.message.reply_text("❌ X account management cancelled.")
    elif update.callback_query:
        await update.callback_query.edit_message_text("❌ X account management cancelled.")
    
    return ConversationHandler.END

# Create conversation handler
x_conv_handler = ConversationHandler(
    entry_points=[],  # Will be set when imported in main.py
    states={
        CHOOSING_X_ACTION: [
            CallbackQueryHandler(x_action_callback, pattern=r'^x_(connect|view|view_after_connect|disconnect|disconnect_confirm|cancel|back|retry|cleanup_connect)$')
        ],
        WAITING_FOR_OAUTH: [
            CallbackQueryHandler(x_action_callback, pattern=r'^x_(cancel|retry|view_after_connect)$')
        ],
    },
    fallbacks=[],  # Will be set when imported in main.py
    name="x_conversation"
) 