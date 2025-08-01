"""
App command for conversational blockchain app interactions.
Allows users to interact with any configured app using natural language.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import ContextTypes, ConversationHandler
from typing import Dict, List, Any, Optional, Union
import logging
import asyncio
from services.pin.pin_decorators import conversation_pin_helper
from services.wallet import wallet_manager
from services.pin import pin_manager
from app.base import app_manager, llm_interface
from app.base.app_session import SessionState, AppSession
from utils.status_updates import create_status_callback
from utils.config import BSC_SCANNER_URL
from db.utils import hash_user_id

logger = logging.getLogger(__name__)

# Conversation states
CHOOSING_APP, CONVERSING, CONFIRMING_TRANSACTION = range(3)

async def app_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the app system or show available apps."""
    
    if update.effective_user is None:
        logger.error("Effective user is None in app_command")
        return ConversationHandler.END
    
    if update.message is None:
        logger.error("Message is None in app_command")
        return ConversationHandler.END
    
    user_id_int: int = update.effective_user.id
    user_id_str: str = str(user_id_int)
    
    # Initialize app manager if needed
    try:
        await app_manager.initialize()
    except Exception as e:
        logger.error(f"Failed to initialize app manager: {str(e)}")
        await update.message.reply_text(
            "❌ Failed to initialize app system. Please try again later."
        )
        return ConversationHandler.END
    
    # Check if user specified an app name
    command_args = context.args if context.args else []
    
    if command_args:
        app_name = command_args[0].lower()
        return await start_specific_app(update, context, user_id_str, app_name)
    else:
        return await show_available_apps(update, context, user_id_str)

async def show_available_apps(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str) -> int:
    """Show available apps for user to choose from."""
    
    # Check wallet requirement
    wallet_name = wallet_manager.get_active_wallet_name(user_id)
    if not wallet_name:
        await update.message.reply_text(
            "❌ You need an active wallet to use apps. Use /wallet to create one first."
        )
        return ConversationHandler.END
    
    # Get available apps
    available_apps = app_manager.get_available_apps()
    
    if not available_apps:
        await update.message.reply_text(
            "❌ No apps are currently available. Please check the configuration."
        )
        return ConversationHandler.END
    
    # Create keyboard with available apps
    keyboard: List[List[InlineKeyboardButton]] = []
    
    for app in available_apps:
        keyboard.append([
            InlineKeyboardButton(
                f"🚀 {app['name'].title()}",
                callback_data=f"app_start_{app['name']}"
            )
        ])
    
    # Add cancel button
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="app_cancel")])
    
    await update.message.reply_text(
        f"🤖 **Blockchain Apps**\n\n"
        f"Choose an app to start conversing:\n\n"
        + "\n".join([f"• **{app['name'].title()}**: {app['description']}" for app in available_apps]) +
        f"\n\n💡 You can also use `/app {available_apps[0]['name']}` to start directly.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return CHOOSING_APP

async def start_specific_app(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str, app_name: str) -> int:
    """Start a specific app directly."""
    
    # Check if app exists
    app_config = app_manager.get_app_config(app_name)
    if not app_config:
        available_apps = app_manager.get_available_apps()
        app_names = [app['name'] for app in available_apps]
        
        await update.message.reply_text(
            f"❌ App '{app_name}' not found.\n\n"
            f"Available apps: {', '.join(app_names)}\n\n"
            f"Use `/app` to see all available apps."
        )
        return ConversationHandler.END
    
    # PIN check with conversation helper
    helper_result = await conversation_pin_helper(
        'app_command', 
        context, 
        update, 
        f"Starting {app_name} app requires your PIN for security. Please enter your PIN."
    )
    if helper_result is not None:
        return helper_result
    
    # Start the app session
    session = await app_manager.start_app_session(user_id, app_name)
    if not session:
        await update.message.reply_text(
            f"❌ Failed to start {app_name} app. Please check your wallet and try again."
        )
        return ConversationHandler.END
    
    # Store session in context for later use
    if context.user_data is None:
        context.user_data = {}
    context.user_data['app_session'] = session
    
    # Send welcome message
    style_guide = app_manager.load_app_style_guide(app_name)
    welcome_msg = f"🚀 **{app_name.title()} App Started**\n\n{app_config['description']}\n\n"
    
    if app_name == "swap":
        welcome_msg += (
            "I can help you swap tokens on TidalDex! Here are some things you can try:\n\n"
            "• \"swap 1.5 cake for busd\"\n"
            "• \"trade 100 usdt for bnb with low slippage\"\n"
            "• \"what's the price of cake in busd?\"\n"
            "• \"show me current swap rates\"\n\n"
            "What would you like to do?"
        )
    else:
        welcome_msg += "How can I help you today?"
    
    await update.message.reply_text(welcome_msg, parse_mode='Markdown')
    
    return CONVERSING

async def handle_app_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle app selection from inline keyboard."""
    
    if update.callback_query is None:
        return ConversationHandler.END
    
    query: CallbackQuery = update.callback_query
    await query.answer()
    
    if query.data is None:
        return ConversationHandler.END
    
    if query.data == "app_cancel":
        await query.edit_message_text("App selection cancelled.")
        return ConversationHandler.END
    
    # Extract app name from callback data
    if query.data.startswith("app_start_"):
        app_name = query.data.replace("app_start_", "")
        user_id = str(update.effective_user.id)
        
        # Start the specific app
        return await start_specific_app_from_callback(query, context, user_id, app_name)
    
    return ConversationHandler.END

async def start_specific_app_from_callback(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, user_id: str, app_name: str) -> int:
    """Start a specific app from callback query."""
    
    try:
        # Start the app session
        session = await app_manager.start_app_session(user_id, app_name)
        if not session:
            await query.edit_message_text(
                f"❌ Failed to start {app_name} app. Please check your wallet and try again."
            )
            return ConversationHandler.END
        
        # Store session in context
        if context.user_data is None:
            context.user_data = {}
        context.user_data['app_session'] = session
        
        # Get app config for welcome message
        app_config = app_manager.get_app_config(app_name)
        welcome_msg = f"🚀 **{app_name.title()} App Started**\n\n{app_config['description']}\n\n"
        
        if app_name == "swap":
            welcome_msg += (
                "I can help you swap tokens on TidalDex! Here are some things you can try:\n\n"
                "• \"swap 1.5 cake for busd\"\n"
                "• \"trade 100 usdt for bnb with low slippage\"\n"
                "• \"what's the price of cake in busd?\"\n"
                "• \"show me current swap rates\"\n\n"
                "What would you like to do?"
            )
        else:
            welcome_msg += "How can I help you today?"
        
        await query.edit_message_text(welcome_msg, parse_mode='Markdown')
        return CONVERSING
        
    except Exception as e:
        logger.error(f"Failed to start app {app_name}: {str(e)}")
        await query.edit_message_text(f"❌ Failed to start {app_name} app: {str(e)}")
        return ConversationHandler.END

async def handle_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle conversational input from user."""
    
    if update.message is None or update.message.text is None:
        return CONVERSING
    
    user_message = update.message.text.strip()
    user_id = str(update.effective_user.id)
    
    # Get session from context
    session: Optional[AppSession] = context.user_data.get('app_session') if context.user_data else None
    if not session:
        await update.message.reply_text(
            "❌ No active app session. Use `/app` to start an app."
        )
        return ConversationHandler.END
    
    try:
        # Show typing indicator
        await update.message.chat.send_action("typing")
        
        # Process message with LLM
        response = await llm_interface.process_user_message(session, user_message)
        
        if response["response_type"] == "chat":
            # Simple conversational response
            await update.message.reply_text(response["message"])
            return CONVERSING
            
        elif response["response_type"] == "view_call":
            # Handle view (read-only) call
            return await handle_view_call(update, context, session, response)
            
        elif response["response_type"] == "write_call":
            # Handle write (transaction) call
            return await handle_write_call(update, context, session, response)
            
        else:
            await update.message.reply_text(
                "❌ I received an unexpected response type. Please try again."
            )
            return CONVERSING
            
    except Exception as e:
        logger.error(f"Error handling conversation for user {hash_user_id(user_id)}: {str(e)}")
        await update.message.reply_text(
            f"❌ Sorry, I encountered an error processing your request: {str(e)}\n\n"
            f"Please try rephrasing your request or use `/cancel` to start over."
        )
        return CONVERSING

async def handle_view_call(update: Update, context: ContextTypes.DEFAULT_TYPE, session: AppSession, response: Dict[str, Any]) -> int:
    """Handle a view (read-only) contract call."""
    
    try:
        contract_call = response["contract_call"]
        
        # Show status message
        status_msg = await update.message.reply_text(
            f"🔍 {response['message']}\n\n"
            f"⏳ {contract_call['explanation']}..."
        )
        
        # Create status callback
        status_callback = create_status_callback(status_msg, max_lines=10, header_lines=2)
        
        # Execute the view call
        result = await session.handle_view_call(
            contract_call["method"],
            contract_call["parameters"],
            status_callback
        )
        
        # Format and display result
        formatted_result = await format_view_result(contract_call["method"], result, session)
        
        await status_msg.edit_text(
            f"✅ {response['message']}\n\n"
            f"**Result:**\n{formatted_result}"
        )
        
        return CONVERSING
        
    except Exception as e:
        logger.error(f"Error handling view call: {str(e)}")
        await update.message.reply_text(
            f"❌ Failed to execute view call: {str(e)}"
        )
        return CONVERSING

async def handle_write_call(update: Update, context: ContextTypes.DEFAULT_TYPE, session: AppSession, response: Dict[str, Any]) -> int:
    """Handle a write (transaction) contract call."""
    
    try:
        contract_call = response["contract_call"]
        
        # Show status message
        status_msg = await update.message.reply_text(
            f"⚙️ {response['message']}\n\n"
            f"⏳ Preparing transaction: {contract_call['explanation']}..."
        )
        
        # Prepare the transaction
        preview = await session.prepare_write_call(
            contract_call["method"],
            contract_call["parameters"]
        )
        
        # Store for confirmation
        if context.user_data is None:
            context.user_data = {}
        context.user_data['app_session'] = session
        
        # Format confirmation message
        confirmation_msg = await session.format_confirmation_message()
        keyboard = session.get_confirmation_keyboard()
        
        await status_msg.edit_text(
            confirmation_msg,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        
        return CONFIRMING_TRANSACTION
        
    except Exception as e:
        logger.error(f"Error handling write call: {str(e)}")
        await update.message.reply_text(
            f"❌ Failed to prepare transaction: {str(e)}"
        )
        return CONVERSING

async def handle_transaction_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle transaction confirmation or cancellation."""
    
    if update.callback_query is None:
        return CONFIRMING_TRANSACTION
    
    query: CallbackQuery = update.callback_query
    await query.answer()
    
    if query.data is None:
        return CONFIRMING_TRANSACTION
    
    # Get session from context
    session: Optional[AppSession] = context.user_data.get('app_session') if context.user_data else None
    if not session:
        await query.edit_message_text("❌ No active app session.")
        return ConversationHandler.END
    
    if query.data.startswith("app_cancel_"):
        # Cancel transaction
        session.cancel_pending_transaction()
        await query.edit_message_text(
            "❌ Transaction cancelled.\n\n"
            "What else would you like to do?"
        )
        return CONVERSING
    
    elif query.data.startswith("app_confirm_"):
        # Confirm and execute transaction
        return await execute_confirmed_transaction(query, context, session)
    
    return CONFIRMING_TRANSACTION

async def execute_confirmed_transaction(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, session: AppSession) -> int:
    """Execute the confirmed transaction."""
    
    try:
        # Update message to show execution
        await query.edit_message_text(
            "⚡ **Executing Transaction**\n\n"
            "🔄 Preparing transaction...\n"
            "⏳ Please wait..."
        )
        
        # Create status callback
        status_callback = create_status_callback(query.message, max_lines=15, header_lines=2)
        
        # Execute the transaction
        result = await session.execute_pending_transaction(status_callback)
        
        if result and result.get('status') == 1:
            tx_hash = result.get('tx_hash', '')
            await query.edit_message_text(
                f"✅ **Transaction Successful!**\n\n"
                f"🔗 **Transaction Hash:** `{tx_hash}`\n"
                f"🌐 **View on BSCScan:** [Click here]({BSC_SCANNER_URL}/tx/{tx_hash})\n\n"
                f"What else would you like to do?"
            , parse_mode='Markdown')
        else:
            await query.edit_message_text(
                "❌ **Transaction Failed**\n\n"
                "The transaction was not successful. Please check your wallet and try again.\n\n"
                "What else would you like to do?"
            )
        
        return CONVERSING
        
    except Exception as e:
        logger.error(f"Error executing transaction: {str(e)}")
        await query.edit_message_text(
            f"❌ **Transaction Failed**\n\n"
            f"Error: {str(e)}\n\n"
            f"What else would you like to do?"
        )
        return CONVERSING

async def format_view_result(method_name: str, result: Any, session: AppSession) -> str:
    """Format the result of a view call for display."""
    
    try:
        if method_name == "getAmountsOut":
            # Format swap quote result
            if isinstance(result, list) and len(result) >= 2:
                # Get token info for formatting
                from services.tokens import token_manager
                
                # Result is [amountIn, amountOut] or [amountIn, intermediate, amountOut]
                amount_out = result[-1]  # Last amount is the output
                
                # Try to get token decimals for formatting (simplified)
                formatted_amount = amount_out / (10 ** 18)  # Default to 18 decimals
                
                return f"Expected output: {formatted_amount:.6f} tokens"
            else:
                return f"Raw result: {result}"
                
        elif method_name == "factory":
            return f"Factory address: `{result}`"
            
        else:
            # Generic formatting
            if isinstance(result, (int, float)):
                return f"{result:,}"
            elif isinstance(result, str):
                return f"`{result}`"
            elif isinstance(result, list):
                return f"Array with {len(result)} items: {result[:3]}{'...' if len(result) > 3 else ''}"
            else:
                return str(result)
                
    except Exception as e:
        logger.error(f"Error formatting view result: {str(e)}")
        return str(result)

async def cancel_app_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the app conversation."""
    
    # Close any active session
    if context.user_data and 'app_session' in context.user_data:
        session = context.user_data['app_session']
        if isinstance(session, AppSession):
            session.cancel_pending_transaction()
        del context.user_data['app_session']
    
    # Close session in app manager
    user_id = str(update.effective_user.id)
    await app_manager.close_session(user_id)
    
    if update.message:
        await update.message.reply_text("App conversation cancelled.")
    elif update.callback_query:
        await update.callback_query.edit_message_text("App conversation cancelled.")
    
    return ConversationHandler.END