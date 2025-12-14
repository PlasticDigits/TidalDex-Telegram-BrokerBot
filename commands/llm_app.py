"""
LLM app command for conversational blockchain LLM app interactions.
Allows users to interact with any configured LLM app using natural language.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import ContextTypes, ConversationHandler
from typing import Dict, List, Any, Optional, Union
import logging
import asyncio
from services.pin.pin_decorators import conversation_pin_helper, PIN_REQUEST
from services.wallet import wallet_manager
from services.pin import pin_manager
from app.base import llm_app_manager
from app.base.llm_interface import get_llm_interface
from app.base.llm_app_session import SessionState, LLMAppSession
from utils.status_updates import create_status_callback, AnimatedStatusMessage
from utils.config import BSC_SCANNER_URL
from utils.swap_intent import is_swap_intent, parse_slippage_bps
from db.utils import hash_user_id

logger = logging.getLogger(__name__)

# Conversation states
CHOOSING_APP, CONVERSING, CONFIRMING_TRANSACTION = range(3)


def get_llm_app_welcome_message(llm_app_name: str, description: str) -> str:
    """Generate welcome message for an LLM app.
    
    Args:
        llm_app_name: Name of the LLM app
        description: Description of the LLM app from config
        
    Returns:
        Formatted welcome message string
    """
    welcome_msg = f"🚀 **{llm_app_name.title()} LLM App Started**\n\n{description}\n\n"
    
    if llm_app_name == "swap":
        welcome_msg += (
            "I can help you swap tokens on TidalDex! Here are some things you can try:\n\n"
            "• \"swap 1.5 cake for busd\"\n"
            "• \"trade 100 usdt for bnb with low slippage\"\n"
            "• \"what's the price of cake in busd?\"\n"
            "• \"show me current swap rates\"\n\n"
            "What would you like to do?"
        )
    elif llm_app_name == "ustc_preregister":
        welcome_msg += (
            "I can help you interact with the USTC+ Preregister! Here are some things you can try:\n\n"
            "• \"show global stats\" or \"how many users have deposited?\"\n"
            "• \"how much have I deposited?\" or \"check my deposit\"\n"
            "• \"deposit 10 USTC-cb\" or \"deposit ALL\"\n"
            "• \"withdraw 5 USTC-cb\" or \"withdraw ALL\"\n\n"
            "What would you like to do?"
        )
    else:
        welcome_msg += "How can I help you today?"
    
    return welcome_msg

async def app_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the LLM app system or show available LLM apps."""
    
    if update.effective_user is None:
        logger.error("Effective user is None in app_command")
        return ConversationHandler.END
    
    if update.message is None:
        logger.error("Message is None in app_command")
        return ConversationHandler.END
    
    user_id_int: int = update.effective_user.id
    user_id_str: str = str(user_id_int)
    
    # Initialize LLM app manager if needed
    try:
        await llm_app_manager.initialize()
    except Exception as e:
        logger.error(f"Failed to initialize LLM app manager: {str(e)}")
        await update.message.reply_text(
            "❌ Failed to initialize LLM app system. Please try again later."
        )
        return ConversationHandler.END
    
    # Check if user specified an LLM app name
    command_args = context.args if context.args else []
    
    if command_args:
        llm_app_name = command_args[0].lower()
        return await start_specific_app(update, context, user_id_str, llm_app_name)
    else:
        return await show_available_apps(update, context, user_id_str)

async def show_available_apps(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str) -> int:
    """Show available LLM apps for user to choose from."""
    
    # Check wallet requirement
    wallet_name = wallet_manager.get_active_wallet_name(user_id)
    if not wallet_name:
        await update.message.reply_text(
            "❌ You need an active wallet to use LLM apps. Use /wallet to create one first."
        )
        return ConversationHandler.END
    
    # Get available LLM apps
    available_llm_apps = llm_app_manager.get_available_llm_apps()
    
    if not available_llm_apps:
        await update.message.reply_text(
            "❌ No LLM apps are currently available. Please check the configuration."
        )
        return ConversationHandler.END
    
    # Create keyboard with available LLM apps
    keyboard: List[List[InlineKeyboardButton]] = []
    
    for llm_app in available_llm_apps:
        keyboard.append([
            InlineKeyboardButton(
                f"🚀 {llm_app['name'].title()}",
                callback_data=f"llm_app_start_{llm_app['name']}"
            )
        ])
    
    # Add cancel button
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="llm_app_cancel")])
    
    await update.message.reply_text(
        f"🤖 **Blockchain LLM Apps**\n\n"
        f"Choose an LLM app to start conversing:\n\n"
        + "\n".join([f"• **{llm_app['name'].title()}**: {llm_app['description']}" for llm_app in available_llm_apps]) +
        f"\n\n💡 You can also use `/llm_app {available_llm_apps[0]['name']}` to start directly.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return CHOOSING_APP

async def start_specific_app(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: str, llm_app_name: str) -> int:
    """Start a specific LLM app directly."""
    
    # Check if LLM app exists
    llm_app_config = llm_app_manager.get_llm_app_config(llm_app_name)
    if not llm_app_config:
        available_llm_apps = llm_app_manager.get_available_llm_apps()
        llm_app_names = [llm_app['name'] for llm_app in available_llm_apps]
        
        await update.message.reply_text(
            f"❌ LLM app '{llm_app_name}' not found.\n\n"
            f"Available LLM apps: {', '.join(llm_app_names)}\n\n"
            f"Use `/llm_app` to see all available LLM apps."
        )
        return ConversationHandler.END
    
    # PIN check with conversation helper
    helper_result = await conversation_pin_helper(
        'app_command', 
        context, 
        update, 
        f"Starting {llm_app_name} LLM app requires your PIN for security. Please enter your PIN."
    )
    if helper_result is not None:
        return helper_result
    
    # Start the LLM app session
    session = await llm_app_manager.start_llm_app_session(user_id, llm_app_name)
    if not session:
        await update.message.reply_text(
            f"❌ Failed to start {llm_app_name} LLM app. Please check your wallet and try again."
        )
        return ConversationHandler.END
    
    # Store session in context for later use
    if context.user_data is None:
        context.user_data = {}
    context.user_data['llm_app_session'] = session
    
    # Send welcome message
    style_guide = llm_app_manager.load_llm_app_style_guide(llm_app_name)
    welcome_msg = get_llm_app_welcome_message(llm_app_name, llm_app_config['description'])
    
    await update.message.reply_text(welcome_msg, parse_mode='Markdown')
    
    return CONVERSING

async def handle_app_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle LLM app selection from inline keyboard."""
    
    if update.callback_query is None:
        return ConversationHandler.END
    
    query: CallbackQuery = update.callback_query
    await query.answer()
    
    if query.data is None:
        return ConversationHandler.END
    
    if query.data == "llm_app_cancel":
        await query.edit_message_text("LLM app selection cancelled.")
        return ConversationHandler.END
    
    # Extract LLM app name from callback data
    if query.data.startswith("llm_app_start_"):
        llm_app_name = query.data.replace("llm_app_start_", "")
        user_id = str(update.effective_user.id)
        
        # Start the specific LLM app
        return await start_specific_app_from_callback(update, query, context, user_id, llm_app_name)
    
    return ConversationHandler.END

async def start_specific_app_from_callback(
    update: Update,
    query: CallbackQuery,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: str,
    llm_app_name: str
) -> int:
    """Start a specific LLM app from callback query."""
    
    try:
        # If the user has a PIN set but hasn't verified it yet, request it BEFORE
        # starting the app session. This prevents wallet decryption attempts and
        # downstream "PIN required but not available" errors during session init.
        user_id_int = int(user_id)
        if pin_manager.needs_to_verify_pin(user_id_int):
            if context.user_data is None:
                context.user_data = {}
            context.user_data['pending_command'] = 'llm_app_start_from_callback'
            context.user_data['pending_llm_app_name'] = llm_app_name
            await query.edit_message_text(
                f"🔒 Starting **{llm_app_name.title()}** requires your PIN for security.\n\n"
                f"Please enter your PIN.",
                parse_mode='Markdown',
            )
            return PIN_REQUEST

        # Start the LLM app session
        session = await llm_app_manager.start_llm_app_session(user_id, llm_app_name)
        if not session:
            await query.edit_message_text(
                f"❌ Failed to start {llm_app_name} LLM app. Please check your wallet and try again."
            )
            return ConversationHandler.END
        
        # Store session in context
        if context.user_data is None:
            context.user_data = {}
        context.user_data['llm_app_session'] = session
        
        # Get LLM app config for welcome message
        llm_app_config = llm_app_manager.get_llm_app_config(llm_app_name)
        welcome_msg = get_llm_app_welcome_message(llm_app_name, llm_app_config['description'])
        
        await query.edit_message_text(welcome_msg, parse_mode='Markdown')
        return CONVERSING
        
    except Exception as e:
        logger.error(f"Failed to start LLM app {llm_app_name}: {str(e)}")
        await query.edit_message_text(f"❌ Failed to start {llm_app_name} LLM app: {str(e)}")
        return ConversationHandler.END

async def _process_llm_message(update: Update, context: ContextTypes.DEFAULT_TYPE, user_message: str) -> int:
    """Process a user message with the LLM (internal helper function).
    
    Args:
        update: Telegram update object
        context: Context object
        user_message: The user's message to process
        
    Returns:
        Next conversation state
    """
    user_id = str(update.effective_user.id)
    
    # Get session from context
    session: Optional[LLMAppSession] = context.user_data.get('llm_app_session') if context.user_data else None
    if not session:
        await update.message.reply_text(
            "❌ No active LLM app session. Use `/llm_app` to start an LLM app."
        )
        return ConversationHandler.END
    
    try:
        # Show animated "thinking" status while processing
        work_msg = await update.message.reply_text("🧠 Thinking...")
        ticker = AnimatedStatusMessage(
            work_msg,
            header="🧠 Working on it",
            stage="Thinking",
            interval_s=1.0
        )
        await ticker.start()
        
        try:
            # Process message with LLM (use get_llm_interface to handle missing API key gracefully)
            ticker.set_stage("Calling LLM")
            llm_interface = get_llm_interface()
            response = await llm_interface.process_user_message(session, user_message)
            
            # Stop animation and handle response
            if response["response_type"] == "chat":
                # Simple conversational response - reuse the same message
                await ticker.stop(final_text=response["message"])
                return CONVERSING
                
            elif response["response_type"] == "view_call":
                # Stop animation - handle_view_call will show its own status
                await ticker.stop()
                return await handle_view_call(update, context, session, response)
                
            elif response["response_type"] == "write_call":
                # Stop animation - handle_write_call will show its own status
                await ticker.stop()
                return await handle_write_call(update, context, session, response)
                
            else:
                await ticker.stop(final_text="❌ I received an unexpected response type. Please try again.")
                return CONVERSING
                
        except Exception as e:
            # Ensure ticker stops even if there's an error
            await ticker.stop()
            raise
            
    except Exception as e:
        logger.error(f"Error handling conversation for user {hash_user_id(user_id)}: {str(e)}")
        await update.message.reply_text(
            f"❌ Sorry, I encountered an error processing your request: {str(e)}\n\n"
            f"Please try rephrasing your request or use `/cancel` to start over."
        )
        return CONVERSING

async def handle_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle conversational input from user."""
    
    if update.message is None or update.message.text is None:
        return CONVERSING
    
    user_message = update.message.text.strip()
    user_id_int = update.effective_user.id
    user_id = str(user_id_int)
    
    # If a PIN is set but not verified yet, request it and do NOT call the LLM.
    if pin_manager.needs_to_verify_pin(user_id_int):
        logger.info(
            f"PIN required but not available for user {hash_user_id(user_id)} in LLM app conversation"
        )
        if context.user_data is None:
            context.user_data = {}
        # Store the user message to process after PIN verification
        context.user_data['pending_llm_message'] = user_message
        context.user_data['pending_command'] = 'llm_app_conversation'
        await update.message.reply_text(
            "🔒 This LLM app requires your PIN to access your wallet. Please enter your PIN."
        )
        return PIN_REQUEST
    
    # Process the message
    return await _process_llm_message(update, context, user_message)

async def handle_view_call(update: Update, context: ContextTypes.DEFAULT_TYPE, session: LLMAppSession, response: Dict[str, Any]) -> int:
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

        # Swap UX improvement:
        # If the user clearly asked to *swap* (not just price-check), then after quoting
        # we automatically prepare the transaction preview and show the inline confirm
        # keyboard. This removes the need for the user to say "Proceed" multiple times.
        if (
            session.llm_app_name == "swap"
            and contract_call.get("method") == "getAmountsOut"
            and session.last_swap_quote
        ):
            # Find the last user message (LLMInterface appends it to session history)
            last_user_msg = ""
            for msg in reversed(session.conversation_history):
                if msg.get("role") == "user":
                    last_user_msg = str(msg.get("content") or "")
                    break

            if is_swap_intent(last_user_msg):
                slippage_bps = parse_slippage_bps(last_user_msg) or 100  # default 1%

                quote_amount_out = int(session.last_swap_quote["amount_out_raw"])
                quote_amount_in = int(session.last_swap_quote["amount_in_raw"])
                quote_path = list(session.last_swap_quote["path"])

                # For native token swaps (BNB/ETH placeholders), skip auto-prepare for now.
                # Those require picking a different write method and/or wrapping logic.
                if any(tok in ("BNB", "ETH") for tok in (quote_path[0], quote_path[-1])):
                    return CONVERSING

                amount_out_min = (quote_amount_out * (10000 - slippage_bps)) // 10000

                preparing_msg = await update.message.reply_text(
                    f"⏳ Preparing transaction preview (slippage {slippage_bps / 100:.2f}%)..."
                )

                # Prefer fee-on-transfer-safe method when available.
                preferred_methods = [
                    "swapExactTokensForTokensSupportingFeeOnTransferTokens",
                    "swapExactTokensForTokens",
                ]
                prepared = False
                last_err: Optional[Exception] = None
                for method in preferred_methods:
                    try:
                        await session.prepare_write_call(
                            method,
                            {
                                "amountIn": quote_amount_in,
                                "amountOutMin": amount_out_min,
                                "path": quote_path,
                            },
                        )
                        prepared = True
                        break
                    except Exception as e:
                        last_err = e
                        continue

                if not prepared:
                    if last_err:
                        logger.error(f"Auto-prepare swap preview failed: {str(last_err)}")
                    return CONVERSING

                if context.user_data is None:
                    context.user_data = {}
                context.user_data["llm_app_session"] = session

                confirmation_msg = await session.format_confirmation_message()
                keyboard = session.get_confirmation_keyboard()
                await preparing_msg.edit_text(
                    confirmation_msg,
                    reply_markup=keyboard,
                    parse_mode="Markdown",
                )
                return CONFIRMING_TRANSACTION

        return CONVERSING
        
    except Exception as e:
        logger.error(f"Error handling view call: {str(e)}")
        await update.message.reply_text(
            f"❌ Failed to execute view call: {str(e)}"
        )
        return CONVERSING

async def handle_write_call(update: Update, context: ContextTypes.DEFAULT_TYPE, session: LLMAppSession, response: Dict[str, Any]) -> int:
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
        context.user_data['llm_app_session'] = session
        
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
    session: Optional[LLMAppSession] = context.user_data.get('llm_app_session') if context.user_data else None
    if not session:
        await query.edit_message_text("❌ No active LLM app session.")
        return ConversationHandler.END
    
    if query.data.startswith("llm_app_cancel_"):
        # Cancel transaction
        session.cancel_pending_transaction()
        await query.edit_message_text(
            "❌ Transaction cancelled.\n\n"
            "What else would you like to do?"
        )
        return CONVERSING
    
    elif query.data.startswith("llm_app_confirm_"):
        # Confirm and execute transaction
        return await execute_confirmed_transaction(query, context, session)
    
    return CONFIRMING_TRANSACTION

async def execute_confirmed_transaction(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, session: LLMAppSession) -> int:
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
            # Ensure tx_hash has 0x prefix for display and URL
            tx_hash_with_prefix = tx_hash if tx_hash.startswith('0x') else f'0x{tx_hash}'
            await query.edit_message_text(
                f"✅ **Transaction Successful!**\n\n"
                f"🔗 **Transaction Hash:** `{tx_hash_with_prefix}`\n"
                f"🌐 **View on BSCScan:** [Click here]({BSC_SCANNER_URL}/tx/{tx_hash_with_prefix})\n\n"
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

async def format_view_result(method_name: str, result: Any, session: LLMAppSession) -> str:
    """Format the result of a view call for display."""
    
    try:
        # USTC Preregister app formatting
        if session.llm_app_name == "ustc_preregister":
            from services.tokens import token_manager
            from utils.config import USTC_CB_TOKEN_ADDRESS
            
            # USTC-cb token address from config (with default)
            USTC_CB_ADDRESS = USTC_CB_TOKEN_ADDRESS
            
            if method_name == "getTotalDeposits":
                # Get token info for decimals
                token_info = await token_manager.get_token_info(USTC_CB_ADDRESS)
                decimals = token_info['decimals'] if token_info else 18
                
                # Convert raw uint256 to human-readable
                raw_amount = int(result) if result else 0
                human_amount = raw_amount / (10 ** decimals)
                
                return f"**Total Deposits:** {human_amount:,.6f} USTC-cb"
                
            elif method_name == "getUserCount":
                # Format as integer with commas
                count = int(result) if result else 0
                return f"**Total Users:** {count:,}"
                
            elif method_name == "getUserDeposit":
                # Get token info for decimals
                token_info = await token_manager.get_token_info(USTC_CB_ADDRESS)
                decimals = token_info['decimals'] if token_info else 18
                
                # Convert raw uint256 to human-readable
                raw_amount = int(result) if result else 0
                human_amount = raw_amount / (10 ** decimals)
                
                return f"**Your Deposit:** {human_amount:,.6f} USTC-cb"
        
        # Swap app formatting
        elif method_name == "getAmountsOut":
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
    """Cancel the LLM app conversation."""
    
    # Close any active session
    if context.user_data and 'llm_app_session' in context.user_data:
        session = context.user_data['llm_app_session']
        if isinstance(session, LLMAppSession):
            session.cancel_pending_transaction()
        del context.user_data['llm_app_session']
    
    # Close session in LLM app manager
    user_id = str(update.effective_user.id)
    await llm_app_manager.close_session(user_id)
    
    if update.message:
        await update.message.reply_text("LLM app conversation cancelled.")
    elif update.callback_query:
        await update.callback_query.edit_message_text("LLM app conversation cancelled.")
    
    return ConversationHandler.END