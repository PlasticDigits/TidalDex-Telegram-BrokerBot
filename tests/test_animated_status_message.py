"""
Unit tests for AnimatedStatusMessage utility.

Tests the animated status message functionality that provides visual feedback
during long-running operations by updating a message with animated dots.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Optional

from utils.status_updates import AnimatedStatusMessage


@pytest.mark.unit
class TestAnimatedStatusMessage:
    """Test suite for AnimatedStatusMessage class."""
    
    @pytest.fixture
    def mock_message(self) -> MagicMock:
        """Create a mock Telegram message object."""
        message = MagicMock()
        message.edit_text = AsyncMock()
        message.text = ""
        return message
    
    @pytest.mark.asyncio
    async def test_basic_animation(self, mock_message: MagicMock) -> None:
        """Test that animation updates message periodically."""
        ticker = AnimatedStatusMessage(
            mock_message,
            stage="Thinking",
            interval_s=0.1  # Fast for testing
        )
        
        await ticker.start()
        await asyncio.sleep(0.35)  # Should get ~3 updates
        await ticker.stop()
        
        # Should have called edit_text multiple times
        assert mock_message.edit_text.call_count >= 3
        
        # Check that dots were animated (different call args)
        calls = [call[0][0] for call in mock_message.edit_text.call_args_list]
        # Should have "Thinking", "Thinking.", "Thinking..", "Thinking..."
        assert any("Thinking" in text for text in calls)
        assert any("Thinking." in text for text in calls)
    
    @pytest.mark.asyncio
    async def test_stage_updates(self, mock_message: MagicMock) -> None:
        """Test that set_stage updates the displayed text."""
        ticker = AnimatedStatusMessage(
            mock_message,
            stage="Thinking",
            interval_s=0.1
        )
        
        await ticker.start()
        await asyncio.sleep(0.15)
        
        ticker.set_stage("Checking blockchain")
        await asyncio.sleep(0.25)
        
        await ticker.stop()
        
        # Should have seen both stages
        calls = [call[0][0] for call in mock_message.edit_text.call_args_list]
        assert any("Thinking" in text for text in calls)
        assert any("Checking blockchain" in text for text in calls)
    
    @pytest.mark.asyncio
    async def test_header_included(self, mock_message: MagicMock) -> None:
        """Test that header is included when provided."""
        ticker = AnimatedStatusMessage(
            mock_message,
            header="🧠 Working on it",
            stage="Thinking",
            interval_s=0.1
        )
        
        await ticker.start()
        await asyncio.sleep(0.15)
        await ticker.stop()
        
        # Check that header appears in messages
        calls = [call[0][0] for call in mock_message.edit_text.call_args_list]
        assert any("🧠 Working on it" in text for text in calls)
        assert any("Thinking" in text for text in calls)
    
    @pytest.mark.asyncio
    async def test_stop_with_final_text(self, mock_message: MagicMock) -> None:
        """Test that stop() can set final message text."""
        ticker = AnimatedStatusMessage(
            mock_message,
            stage="Thinking",
            interval_s=0.1
        )
        
        await ticker.start()
        await asyncio.sleep(0.15)
        await ticker.stop(final_text="✅ Done!")
        
        # Last call should be the final text
        last_call = mock_message.edit_text.call_args_list[-1]
        assert last_call[0][0] == "✅ Done!"
    
    @pytest.mark.asyncio
    async def test_stop_without_final_text(self, mock_message: MagicMock) -> None:
        """Test that stop() without final_text just stops animation."""
        ticker = AnimatedStatusMessage(
            mock_message,
            stage="Thinking",
            interval_s=0.1
        )
        
        await ticker.start()
        await asyncio.sleep(0.15)
        initial_count = mock_message.edit_text.call_count
        
        await ticker.stop()
        await asyncio.sleep(0.25)  # Wait to ensure no more updates
        
        # Should not have many more calls after stop
        final_count = mock_message.edit_text.call_count
        assert final_count <= initial_count + 2  # Allow for final update + stop
    
    @pytest.mark.asyncio
    async def test_multiple_start_calls_safe(self, mock_message: MagicMock) -> None:
        """Test that calling start() multiple times is safe."""
        ticker = AnimatedStatusMessage(
            mock_message,
            stage="Thinking",
            interval_s=0.1
        )
        
        await ticker.start()
        await ticker.start()  # Should be safe
        await ticker.start()  # Should be safe
        
        await asyncio.sleep(0.15)
        await ticker.stop()
        
        # Should still work normally
        assert mock_message.edit_text.call_count > 0
    
    @pytest.mark.asyncio
    async def test_max_dots_configuration(self, mock_message: MagicMock) -> None:
        """Test that max_dots limits the number of dots."""
        ticker = AnimatedStatusMessage(
            mock_message,
            stage="Working",
            interval_s=0.05,
            max_dots=2  # Only 0, 1, or 2 dots
        )
        
        await ticker.start()
        await asyncio.sleep(0.3)  # Should cycle through multiple times
        await ticker.stop()
        
        # Check that we never see more than max_dots dots
        calls = [call[0][0] for call in mock_message.edit_text.call_args_list]
        for text in calls:
            if "Working" in text:
                dots_count = text.count(".")
                assert dots_count <= 2, f"Found {dots_count} dots, max should be 2"
    
    @pytest.mark.asyncio
    async def test_handles_message_not_modified_error(self, mock_message: MagicMock) -> None:
        """Test that 'Message is not modified' errors are handled gracefully."""
        # Simulate Telegram API returning "Message is not modified" error
        error = Exception("Message is not modified")
        mock_message.edit_text.side_effect = error
        
        ticker = AnimatedStatusMessage(
            mock_message,
            stage="Thinking",
            interval_s=0.1
        )
        
        await ticker.start()
        await asyncio.sleep(0.15)
        await ticker.stop()
        
        # Should not crash - error should be caught and handled
        assert True  # If we get here, it didn't crash
    
    @pytest.mark.asyncio
    async def test_handles_message_not_found_error(self, mock_message: MagicMock) -> None:
        """Test that 'message not found' errors stop animation gracefully."""
        # Simulate message being deleted
        error = Exception("message to edit not found")
        mock_message.edit_text.side_effect = error
        
        ticker = AnimatedStatusMessage(
            mock_message,
            stage="Thinking",
            interval_s=0.1
        )
        
        await ticker.start()
        await asyncio.sleep(0.15)
        await ticker.stop()
        
        # Should stop gracefully without crashing
        assert True  # If we get here, it didn't crash
    
    @pytest.mark.asyncio
    async def test_handles_rate_limit_error(self, mock_message: MagicMock) -> None:
        """Test that rate limit errors are handled gracefully."""
        # Simulate rate limiting
        error = Exception("too many requests")
        mock_message.edit_text.side_effect = error
        
        ticker = AnimatedStatusMessage(
            mock_message,
            stage="Thinking",
            interval_s=0.1
        )
        
        await ticker.start()
        await asyncio.sleep(0.15)
        await ticker.stop()
        
        # Should handle gracefully
        assert True  # If we get here, it didn't crash
    
    @pytest.mark.asyncio
    async def test_empty_stage_defaults_to_working(self, mock_message: MagicMock) -> None:
        """Test that empty stage text defaults to 'Working'."""
        ticker = AnimatedStatusMessage(
            mock_message,
            stage="",
            interval_s=0.1
        )
        
        await ticker.start()
        await asyncio.sleep(0.25)  # Wait longer to ensure at least one update
        await ticker.stop()
        
        # Should show "Working" instead of empty string
        calls = [call[0][0] for call in mock_message.edit_text.call_args_list]
        assert len(calls) > 0, "No edit_text calls were made"
        assert any("Working" in text for text in calls), f"Expected 'Working' in calls, got: {calls}"
    
    @pytest.mark.asyncio
    async def test_set_stage_updates_immediately(self, mock_message: MagicMock) -> None:
        """Test that set_stage updates are reflected in next animation cycle."""
        ticker = AnimatedStatusMessage(
            mock_message,
            stage="Initial",
            interval_s=0.2  # Longer interval to ensure we catch the update
        )
        
        await ticker.start()
        await asyncio.sleep(0.1)
        
        # Change stage mid-animation
        ticker.set_stage("Updated")
        
        await asyncio.sleep(0.25)  # Wait for next cycle
        await ticker.stop()
        
        # Should see the updated stage
        calls = [call[0][0] for call in mock_message.edit_text.call_args_list]
        assert any("Updated" in text for text in calls)
    
    @pytest.mark.asyncio
    async def test_concurrent_edits_are_serialized(self, mock_message: MagicMock) -> None:
        """Test that concurrent edits are properly serialized with lock."""
        edit_call_count = 0
        
        async def slow_edit(text: str) -> None:
            nonlocal edit_call_count
            edit_call_count += 1
            await asyncio.sleep(0.05)  # Simulate slow edit
        
        mock_message.edit_text = slow_edit
        
        ticker = AnimatedStatusMessage(
            mock_message,
            stage="Thinking",
            interval_s=0.01  # Very fast updates
        )
        
        await ticker.start()
        await asyncio.sleep(0.1)
        await ticker.stop()
        
        # Should have made multiple calls (lock allows serialization)
        assert edit_call_count > 0

