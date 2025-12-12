"""
Unit and regression tests for PIN requirement handling in LLM app conversations.

Tests that when PIN is required but not available, the system requests PIN
from the user instead of calling the LLM.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from commands.llm_app import CONVERSING, handle_conversation, start_specific_app
from services.pin.pin_decorators import PIN_FAILED, PIN_REQUEST, handle_conversation_pin_request
from services.pin import pin_manager


class TestLLMAppPINRequirement:
    """Test PIN requirement handling in LLM app conversations."""
    
    @pytest.fixture
    def mock_update(self) -> Update:
        """Create a mocked Telegram update compatible with handler code."""
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock()
        update.effective_user.id = 12345
        update.message = MagicMock()
        update.message.text = "What are my balances"
        update.message.reply_text = AsyncMock()
        update.message.delete = AsyncMock()
        update.message.chat = MagicMock()
        update.message.chat.send_action = AsyncMock()
        return update  # type: ignore[return-value]
    
    @pytest.fixture
    def mock_context(self) -> ContextTypes.DEFAULT_TYPE:
        """Create a mock context with a placeholder LLM app session."""
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {}
        context.user_data["llm_app_session"] = MagicMock()
        return context

    @pytest.fixture
    def mock_callback_update(self) -> Update:
        """Create a mocked update representing an inline keyboard callback."""
        from telegram import CallbackQuery

        update = MagicMock(spec=Update)
        update.effective_user = MagicMock()
        update.effective_user.id = 12345

        query = MagicMock(spec=CallbackQuery)
        query.data = "llm_app_start_swap"
        query.answer = AsyncMock()
        query.edit_message_text = AsyncMock()

        update.callback_query = query
        update.message = None
        return update  # type: ignore[return-value]
    
    @pytest.mark.asyncio
    async def test_pin_required_but_not_available_requests_pin(
        self,
        mock_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Test that when PIN is required but not available, PIN is requested instead of calling LLM."""
        # Mock needs_to_verify_pin directly for clarity (returns True when PIN needed but not verified)
        with patch.object(pin_manager, 'needs_to_verify_pin', return_value=True), \
             patch('commands.llm_app.get_llm_interface') as mock_llm_interface:
            
            # Call handle_conversation
            result = await handle_conversation(mock_update, mock_context)
            
            # Should return PIN_REQUEST state
            assert result == PIN_REQUEST, f"Expected PIN_REQUEST, got {result}"
            
            # Should store pending message
            assert 'pending_llm_message' in mock_context.user_data
            assert mock_context.user_data['pending_llm_message'] == "What are my balances"
            assert mock_context.user_data['pending_command'] == 'llm_app_conversation'
            
            # Should NOT call LLM
            mock_llm_interface.assert_not_called()
            
            # Should send PIN request message
            mock_update.message.reply_text.assert_awaited_once()
            call_args = mock_update.message.reply_text.call_args[0][0]
            assert "PIN" in call_args
    
    @pytest.mark.asyncio
    async def test_pin_available_processes_message_normally(
        self,
        mock_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Test that when PIN is already verified, message is processed normally."""
        # Mock needs_to_verify_pin to return False (PIN already verified or not needed)
        with patch.object(pin_manager, 'needs_to_verify_pin', return_value=False), \
             patch('commands.llm_app.get_llm_interface') as mock_llm_interface:
            
            # Mock LLM interface
            mock_llm = MagicMock()
            mock_llm.process_user_message = AsyncMock(return_value={
                "response_type": "chat",
                "message": "Here are your balances..."
            })
            mock_llm_interface.return_value = mock_llm
            
            # Call handle_conversation
            result = await handle_conversation(mock_update, mock_context)
            
            # Should process message and return CONVERSING
            assert result == CONVERSING
            
            # Should call LLM
            mock_llm.process_user_message.assert_called_once()
            
            # Should NOT request PIN
            assert 'pending_llm_message' not in mock_context.user_data
    
    @pytest.mark.asyncio
    async def test_no_pin_required_processes_message_normally(
        self,
        mock_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Test that when user has no PIN set, message is processed normally."""
        # Mock needs_to_verify_pin to return False (user has no PIN)
        with patch.object(pin_manager, 'needs_to_verify_pin', return_value=False), \
             patch('commands.llm_app.get_llm_interface') as mock_llm_interface:
            
            # Mock LLM interface
            mock_llm = MagicMock()
            mock_llm.process_user_message = AsyncMock(return_value={
                "response_type": "chat",
                "message": "Here are your balances..."
            })
            mock_llm_interface.return_value = mock_llm
            
            # Call handle_conversation
            result = await handle_conversation(mock_update, mock_context)
            
            # Should process message and return CONVERSING
            assert result == CONVERSING
            
            # Should call LLM
            mock_llm.process_user_message.assert_called_once()
            
            # Should NOT request PIN
            assert 'pending_llm_message' not in mock_context.user_data
    
    @pytest.mark.asyncio
    async def test_pin_verification_continues_conversation(
        self,
        mock_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Test that after PIN verification, the stored message is processed."""
        # Set up context with pending message
        mock_context.user_data['pending_llm_message'] = "What are my balances"
        mock_context.user_data['pending_command'] = 'llm_app_conversation'
        
        # Mock PIN verification
        with patch.object(pin_manager, 'verify_pin', return_value=True), \
             patch('commands.llm_app._process_llm_message') as mock_process:
            
            mock_process.return_value = CONVERSING
            
            # Call handle_conversation_pin_request
            result = await handle_conversation_pin_request(mock_update, mock_context)
            
            # Should process the pending message
            mock_process.assert_called_once()
            call_args = mock_process.call_args
            assert call_args[0][2] == "What are my balances"  # user_message parameter
            
            # Should clear pending message
            assert 'pending_llm_message' not in mock_context.user_data
            assert 'pending_command' not in mock_context.user_data
            
            # Should store PIN in context
            assert mock_context.user_data.get('pin') == mock_update.message.text
            assert result == CONVERSING
    
    @pytest.mark.asyncio
    async def test_invalid_pin_returns_pin_failed(
        self,
        mock_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Test that invalid PIN returns PIN_FAILED state."""
        # Set up context with pending message
        mock_context.user_data['pending_llm_message'] = "What are my balances"
        mock_context.user_data['pending_command'] = 'llm_app_conversation'
        
        # Mock PIN verification to fail
        with patch.object(pin_manager, 'verify_pin', return_value=False):
            
            # Call handle_conversation_pin_request
            result = await handle_conversation_pin_request(mock_update, mock_context)
            
            # Should return PIN_FAILED
            assert result == PIN_FAILED
            
            # Should NOT process message
            assert 'pending_llm_message' in mock_context.user_data  # Still pending
            
            # Should send error message
            mock_update.message.reply_text.assert_awaited_once()
            call_args = mock_update.message.reply_text.call_args[0][0]
            assert "Invalid" in call_args or "invalid" in call_args.lower()
    
    @pytest.mark.asyncio
    async def test_no_session_returns_end(
        self,
        mock_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Test that when no session exists, returns ConversationHandler.END."""
        # Remove session from context
        mock_context.user_data.pop('llm_app_session', None)
        
        # Mock PIN manager - no PIN verification needed
        with patch.object(pin_manager, 'needs_to_verify_pin', return_value=False):
            
            # Call handle_conversation
            result = await handle_conversation(mock_update, mock_context)
            
            # Should return END
            assert result == ConversationHandler.END
            
            # Should send error message
            mock_update.message.reply_text.assert_awaited_once()
            call_args = mock_update.message.reply_text.call_args[0][0]
            assert "No active LLM app session" in call_args

    @pytest.mark.asyncio
    async def test_callback_start_with_missing_pin_requests_pin(
        self,
        mock_callback_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """If user starts app via callback and PIN isn't verified, ask for PIN and do not start session."""
        from commands.llm_app import handle_app_choice

        with patch.object(pin_manager, "needs_to_verify_pin", return_value=True), \
             patch("commands.llm_app.llm_app_manager.start_llm_app_session") as mock_start_session:
            result = await handle_app_choice(mock_callback_update, mock_context)

            assert result == PIN_REQUEST
            assert mock_context.user_data["pending_command"] == "llm_app_start_from_callback"
            assert mock_context.user_data["pending_llm_app_name"] == "swap"
            mock_start_session.assert_not_called()
            mock_callback_update.callback_query.edit_message_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_pin_verification_can_start_app_from_callback(
        self,
        mock_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """After PIN entry, the pending callback-start app should be started and session stored."""
        # Simulate "pending start" set by callback handler
        mock_context.user_data.pop("llm_app_session", None)
        mock_context.user_data["pending_command"] = "llm_app_start_from_callback"
        mock_context.user_data["pending_llm_app_name"] = "swap"

        with patch.object(pin_manager, "verify_pin", return_value=True), \
             patch("app.base.llm_app_manager.start_llm_app_session", new=AsyncMock(return_value=MagicMock())) as mock_start, \
             patch("app.base.llm_app_manager.get_llm_app_config", return_value={"description": "Test swap app"}):
            result = await handle_conversation_pin_request(mock_update, mock_context)

            assert result == CONVERSING
            assert "llm_app_session" in mock_context.user_data
            mock_start.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_direct_command_with_missing_pin_requests_pin(
        self,
        mock_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Test that /llm_app swap command requests PIN when PIN is set but not verified."""
        # Mock conversation_pin_helper to return PIN_REQUEST (simulating PIN needed)
        with patch('commands.llm_app.conversation_pin_helper', new=AsyncMock(return_value=PIN_REQUEST)), \
             patch('commands.llm_app.llm_app_manager') as mock_manager:
            
            mock_manager.get_llm_app_config.return_value = {"description": "Test app"}
            
            result = await start_specific_app(mock_update, mock_context, "12345", "swap")
            
            # Should return PIN_REQUEST
            assert result == PIN_REQUEST
            
            # Should NOT start session
            mock_manager.start_llm_app_session.assert_not_called()

    @pytest.mark.asyncio
    async def test_direct_command_with_verified_pin_starts_session(
        self,
        mock_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Test that /llm_app swap command starts session when PIN is already verified."""
        mock_session = MagicMock()
        
        with patch('commands.llm_app.conversation_pin_helper', new=AsyncMock(return_value=None)), \
             patch('commands.llm_app.llm_app_manager') as mock_manager:
            
            mock_manager.get_llm_app_config.return_value = {"description": "Test app"}
            mock_manager.start_llm_app_session = AsyncMock(return_value=mock_session)
            mock_manager.load_llm_app_style_guide.return_value = None
            
            result = await start_specific_app(mock_update, mock_context, "12345", "swap")
            
            # Should return CONVERSING
            assert result == CONVERSING
            
            # Should start session
            mock_manager.start_llm_app_session.assert_awaited_once_with("12345", "swap")
            
            # Should store session in context
            assert mock_context.user_data.get('llm_app_session') == mock_session

    @pytest.mark.asyncio
    async def test_session_initialization_failure_after_pin(
        self,
        mock_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Test error handling when session fails to start after PIN verification."""
        mock_context.user_data.pop("llm_app_session", None)
        mock_context.user_data["pending_command"] = "llm_app_start_from_callback"
        mock_context.user_data["pending_llm_app_name"] = "swap"

        with patch.object(pin_manager, "verify_pin", return_value=True), \
             patch("app.base.llm_app_manager.start_llm_app_session", new=AsyncMock(return_value=None)):
            result = await handle_conversation_pin_request(mock_update, mock_context)

            # Should return END since session failed
            assert result == ConversationHandler.END
            
            # Should send error message
            error_msg = mock_update.message.reply_text.call_args_list[-1][0][0]
            assert "Failed" in error_msg or "failed" in error_msg.lower()

    @pytest.mark.asyncio  
    async def test_pending_message_missing_after_pin(
        self,
        mock_update: Update,
        mock_context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """Test error handling when pending message is missing after PIN verification."""
        mock_context.user_data["pending_command"] = "llm_app_conversation"
        # Note: NOT setting pending_llm_message
        
        with patch.object(pin_manager, "verify_pin", return_value=True):
            result = await handle_conversation_pin_request(mock_update, mock_context)
            
            # Should return END
            assert result == ConversationHandler.END
            
            # Should send error message about no message
            error_msg = mock_update.message.reply_text.call_args_list[-1][0][0]
            assert "No message" in error_msg or "error" in error_msg.lower()
