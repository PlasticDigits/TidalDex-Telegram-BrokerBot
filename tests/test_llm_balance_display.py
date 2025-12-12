"""
Unit tests for LLM balance display with token addresses.

Tests that token addresses are included in the LLM system prompt
to help disambiguate tokens with the same symbol.
"""
import pytest
import os
from unittest.mock import MagicMock, patch


class TestLLMBalanceDisplay:
    """Test LLM balance display formatting."""
    
    @pytest.fixture
    def mock_llm_interface(self) -> MagicMock:
        """Create a LLMInterface with mocked OpenAI key."""
        # Mock the environment variable
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-api-key"}):
            from app.base.llm_interface import LLMInterface
            interface = LLMInterface()
            return interface
    
    @pytest.fixture
    def sample_context_with_duplicate_symbols(self) -> dict:
        """Sample context with duplicate token symbols."""
        return {
            "token_balances": [
                {
                    "symbol": "CL8Y",
                    "name": "CeramicLiberty.com",
                    "balance": 13.55,
                    "address": "0x1234567890123456789012345678901234567890"
                },
                {
                    "symbol": "CL8Y",
                    "name": "CeramicLiberty.com",
                    "balance": 12.69,
                    "address": "0xABCDEF1234567890ABCDEF1234567890ABCDEF12"
                },
                {
                    "symbol": "CAKE",
                    "name": "PancakeSwap Token",
                    "balance": 0.1,
                    "address": "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82"
                }
            ]
        }
    
    @pytest.mark.asyncio
    async def test_balance_display_includes_addresses(
        self,
        mock_llm_interface: MagicMock,
        sample_context_with_duplicate_symbols: dict
    ) -> None:
        """
        Test that balance display includes abbreviated addresses for disambiguation.
        """
        # Create a mock session with required attributes
        session = MagicMock()
        session.llm_app_name = "swap"
        session.llm_app_config = {
            "name": "swap",
            "description": "Test swap app",
            "available_methods": {"view": [], "write": []}
        }
        session.context = sample_context_with_duplicate_symbols
        session.conversation_history = []
        
        # Build system prompt
        system_prompt = await mock_llm_interface._build_system_prompt(session)
        
        # Check that addresses are included (format: first 10 chars + ... + last 6 chars)
        assert "0x12345678...567890" in system_prompt
        assert "0xABCDEF12...CDEF12" in system_prompt
        assert "0x0E09FaBB...81cE82" in system_prompt
        
        # Check that balances are included
        assert "13.55" in system_prompt
        assert "12.69" in system_prompt
        assert "0.1" in system_prompt
        
        # Check that symbols are included
        assert "CL8Y" in system_prompt
        assert "CAKE" in system_prompt
    
    @pytest.mark.asyncio
    async def test_balance_display_handles_missing_address(
        self,
        mock_llm_interface: MagicMock
    ) -> None:
        """
        Test that balance display handles missing addresses gracefully.
        """
        context = {
            "token_balances": [
                {
                    "symbol": "CAKE",
                    "name": "PancakeSwap Token",
                    "balance": 0.1,
                    "address": ""  # Empty address
                }
            ]
        }
        
        session = MagicMock()
        session.llm_app_name = "swap"
        session.llm_app_config = {
            "name": "swap",
            "description": "Test swap app",
            "available_methods": {"view": [], "write": []}
        }
        session.context = context
        session.conversation_history = []
        
        # Should not crash
        system_prompt = await mock_llm_interface._build_system_prompt(session)
        
        # Should still include balance and symbol
        assert "0.1" in system_prompt
        assert "CAKE" in system_prompt
    
    @pytest.mark.asyncio
    async def test_balance_display_handles_short_address(
        self,
        mock_llm_interface: MagicMock
    ) -> None:
        """
        Test that balance display handles short addresses gracefully.
        """
        context = {
            "token_balances": [
                {
                    "symbol": "CAKE",
                    "name": "PancakeSwap Token",
                    "balance": 0.1,
                    "address": "0x123"  # Too short
                }
            ]
        }
        
        session = MagicMock()
        session.llm_app_name = "swap"
        session.llm_app_config = {
            "name": "swap",
            "description": "Test swap app",
            "available_methods": {"view": [], "write": []}
        }
        session.context = context
        session.conversation_history = []
        
        # Should not crash
        system_prompt = await mock_llm_interface._build_system_prompt(session)
        
        # Should still include balance and symbol (without address abbreviation)
        assert "0.1" in system_prompt
        assert "CAKE" in system_prompt
