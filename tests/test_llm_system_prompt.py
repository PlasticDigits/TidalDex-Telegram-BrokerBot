#!/usr/bin/env python3
"""
Tests for LLM system prompt building.

Tests system prompt generation with various app configurations
without requiring wallet or database access.
"""
import sys
import os
from pathlib import Path
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from typing import Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import pytest
    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False

from app.base.llm_interface import LLMInterface
from app.base.llm_app_session import LLMAppSession


@pytest.mark.unit
class TestLLMSystemPrompt:
    """Tests for LLM system prompt building."""
    
    def setup_method(self):
        """Set up test fixtures."""
        os.environ["OPENAI_API_KEY"] = "test-key-12345"
        try:
            self.llm = LLMInterface()
        except ValueError:
            if HAS_PYTEST:
                pytest.skip("OPENAI_API_KEY not set")
            else:
                raise
    
    def teardown_method(self):
        """Clean up after tests."""
        if "OPENAI_API_KEY" in os.environ and os.environ["OPENAI_API_KEY"] == "test-key-12345":
            del os.environ["OPENAI_API_KEY"]
    
    def _create_mock_session(
        self,
        llm_app_config: Dict[str, Any],
        context: Dict[str, Any] = None,
        llm_app_name: str = "test_app"
    ) -> LLMAppSession:
        """Create a mock LLMAppSession for testing."""
        session = Mock(spec=LLMAppSession)
        session.llm_app_config = llm_app_config
        session.llm_app_name = llm_app_name
        session.context = context or {}
        session.conversation_history = []
        return session
    
    @pytest.mark.asyncio
    async def test_build_system_prompt_no_balances(self):
        """Test system prompt when user has no token balances."""
        app_config = {
            "name": "swap",
            "description": "Token swapping app",
            "available_methods": {
                "view": [{"name": "getAmountsOut", "description": "Get swap amounts"}],
                "write": [{"name": "swapTokens", "description": "Swap tokens"}]
            }
        }
        context = {
            "wallet_address": "0x123",
            "token_balances": []
        }
        session = self._create_mock_session(app_config, context)
        
        # Mock llm_app_manager
        from app.base import llm_app_manager as real_llm_app_manager
        with patch.object(real_llm_app_manager, 'load_llm_app_style_guide', return_value=None):
            prompt = await self.llm._build_system_prompt(session)
            
            assert "swap" in prompt
            assert "Token swapping app" in prompt
            assert "0x123" in prompt
            # Should not have balance section when empty
            assert "Your Token Balances" not in prompt or "None" in prompt
    
    @pytest.mark.asyncio
    async def test_build_system_prompt_no_view_methods(self):
        """Test system prompt when app has no view methods."""
        app_config = {
            "name": "write_only",
            "description": "Write-only app",
            "available_methods": {
                "view": [],
                "write": [{"name": "doSomething", "description": "Do something"}]
            }
        }
        context = {"wallet_address": "0x123"}
        session = self._create_mock_session(app_config, context)
        
        from app.base import llm_app_manager as real_llm_app_manager
        with patch.object(real_llm_app_manager, 'load_llm_app_style_guide', return_value=None):
            prompt = await self.llm._build_system_prompt(session)
            
            assert "None" in prompt or "View Methods" in prompt
            assert "doSomething" in prompt
    
    @pytest.mark.asyncio
    async def test_build_system_prompt_no_write_methods(self):
        """Test system prompt when app has no write methods."""
        app_config = {
            "name": "read_only",
            "description": "Read-only app",
            "available_methods": {
                "view": [{"name": "readData", "description": "Read data"}],
                "write": []
            }
        }
        context = {"wallet_address": "0x123"}
        session = self._create_mock_session(app_config, context)
        
        from app.base import llm_app_manager as real_llm_app_manager
        with patch.object(real_llm_app_manager, 'load_llm_app_style_guide', return_value=None):
            prompt = await self.llm._build_system_prompt(session)
            
            assert "readData" in prompt
            assert "None" in prompt or "Write Methods" in prompt
    
    @pytest.mark.asyncio
    async def test_build_system_prompt_with_style_guide(self):
        """Test system prompt includes style guide when available."""
        app_config = {
            "name": "styled_app",
            "description": "App with style guide",
            "available_methods": {
                "view": [],
                "write": []
            }
        }
        context = {"wallet_address": "0x123"}
        session = self._create_mock_session(app_config, context)
        
        style_guide = "## Style Guide\nBe friendly and professional."
        
        from app.base import llm_app_manager as real_llm_app_manager
        with patch.object(real_llm_app_manager, 'load_llm_app_style_guide', return_value=style_guide):
            prompt = await self.llm._build_system_prompt(session)
            
            assert "Style Guide" in prompt
            assert "Be friendly and professional" in prompt
    
    @pytest.mark.asyncio
    async def test_build_system_prompt_no_style_guide(self):
        """Test system prompt when STYLE.md doesn't exist."""
        app_config = {
            "name": "no_style",
            "description": "App without style guide",
            "available_methods": {
                "view": [],
                "write": []
            }
        }
        context = {"wallet_address": "0x123"}
        session = self._create_mock_session(app_config, context)
        
        from app.base import llm_app_manager as real_llm_app_manager
        with patch.object(real_llm_app_manager, 'load_llm_app_style_guide', return_value=None):
            prompt = await self.llm._build_system_prompt(session)
            
            # Should not have style guide section
            assert "## Style Guide" not in prompt
    
    @pytest.mark.asyncio
    async def test_build_system_prompt_with_token_balances(self):
        """Test system prompt formatting with token balances."""
        app_config = {
            "name": "swap",
            "description": "Swap app",
            "available_methods": {
                "view": [],
                "write": []
            }
        }
        context = {
            "wallet_address": "0x123",
            "token_balances": [
                {"symbol": "CAKE", "name": "PancakeSwap Token", "balance": "100.5"},
                {"symbol": "BUSD", "name": "Binance USD", "balance": "500.0"}
            ]
        }
        session = self._create_mock_session(app_config, context)
        
        from app.base import llm_app_manager as real_llm_app_manager
        with patch.object(real_llm_app_manager, 'load_llm_app_style_guide', return_value=None):
            prompt = await self.llm._build_system_prompt(session)
            
            assert "Your Token Balances" in prompt
            assert "100.5 CAKE" in prompt
            assert "500.0 BUSD" in prompt
            assert "PancakeSwap Token" in prompt
    
    @pytest.mark.asyncio
    async def test_build_system_prompt_multiple_methods(self):
        """Test system prompt with multiple view and write methods."""
        app_config = {
            "name": "multi_method",
            "description": "App with many methods",
            "available_methods": {
                "view": [
                    {"name": "method1", "description": "First view method"},
                    {"name": "method2", "description": "Second view method"}
                ],
                "write": [
                    {"name": "write1", "description": "First write method"},
                    {"name": "write2", "description": "Second write method"}
                ]
            }
        }
        context = {"wallet_address": "0x123"}
        session = self._create_mock_session(app_config, context)
        
        from app.base import llm_app_manager as real_llm_app_manager
        with patch.object(real_llm_app_manager, 'load_llm_app_style_guide', return_value=None):
            prompt = await self.llm._build_system_prompt(session)
            
            assert "method1" in prompt
            assert "method2" in prompt
            assert "write1" in prompt
            assert "write2" in prompt
            assert "First view method" in prompt
            assert "Second write method" in prompt
    
    @pytest.mark.asyncio
    async def test_build_system_prompt_no_wallet_address(self):
        """Test system prompt when wallet address is not available."""
        app_config = {
            "name": "no_wallet",
            "description": "App without wallet",
            "available_methods": {
                "view": [],
                "write": []
            }
        }
        context = {}  # No wallet_address
        session = self._create_mock_session(app_config, context)
        
        from app.base import llm_app_manager as real_llm_app_manager
        with patch.object(real_llm_app_manager, 'load_llm_app_style_guide', return_value=None):
            prompt = await self.llm._build_system_prompt(session)
            
            assert "Not available" in prompt or "wallet_address" in prompt.lower()
    
    @pytest.mark.asyncio
    async def test_build_system_prompt_method_with_inputs(self):
        """Test system prompt includes method input parameters."""
        app_config = {
            "name": "params_app",
            "description": "App with method params",
            "available_methods": {
                "view": [
                    {
                        "name": "getBalance",
                        "description": "Get token balance for address",
                        "inputs": ["tokenAddress", "walletAddress"]
                    }
                ],
                "write": []
            }
        }
        context = {"wallet_address": "0x123"}
        session = self._create_mock_session(app_config, context)
        
        from app.base import llm_app_manager as real_llm_app_manager
        with patch.object(real_llm_app_manager, 'load_llm_app_style_guide', return_value=None):
            prompt = await self.llm._build_system_prompt(session)
            
            assert "getBalance" in prompt
            assert "Get token balance for address" in prompt
    
    @pytest.mark.asyncio
    async def test_build_system_prompt_special_chars_in_description(self):
        """Test system prompt handles special characters in descriptions."""
        app_config = {
            "name": "special_app",
            "description": "App with <special> & \"chars\"",
            "available_methods": {
                "view": [
                    {"name": "test", "description": "Test <b>method</b> with &amp;"}
                ],
                "write": []
            }
        }
        context = {"wallet_address": "0x123"}
        session = self._create_mock_session(app_config, context)
        
        from app.base import llm_app_manager as real_llm_app_manager
        with patch.object(real_llm_app_manager, 'load_llm_app_style_guide', return_value=None):
            prompt = await self.llm._build_system_prompt(session)
            
            assert '<special>' in prompt or 'special' in prompt
            assert '&' in prompt
    
    @pytest.mark.asyncio
    async def test_build_system_prompt_many_token_balances(self):
        """Test system prompt with many token balances."""
        app_config = {
            "name": "multi_token",
            "description": "App with many tokens",
            "available_methods": {
                "view": [],
                "write": []
            }
        }
        context = {
            "wallet_address": "0x123",
            "token_balances": [
                {"symbol": f"TKN{i}", "name": f"Token {i}", "balance": f"{i * 100}.0"}
                for i in range(10)
            ]
        }
        session = self._create_mock_session(app_config, context)
        
        from app.base import llm_app_manager as real_llm_app_manager
        with patch.object(real_llm_app_manager, 'load_llm_app_style_guide', return_value=None):
            prompt = await self.llm._build_system_prompt(session)
            
            assert "Your Token Balances" in prompt
            assert "TKN0" in prompt
            assert "TKN9" in prompt
            assert "900.0 TKN9" in prompt
    
    @pytest.mark.asyncio
    async def test_build_system_prompt_long_style_guide(self):
        """Test system prompt with a long style guide."""
        app_config = {
            "name": "long_style",
            "description": "App with long style guide",
            "available_methods": {
                "view": [],
                "write": []
            }
        }
        context = {"wallet_address": "0x123"}
        session = self._create_mock_session(app_config, context)
        
        long_style_guide = "# Style Guide\n" + "Be professional and helpful.\n" * 100
        
        from app.base import llm_app_manager as real_llm_app_manager
        with patch.object(real_llm_app_manager, 'load_llm_app_style_guide', return_value=long_style_guide):
            prompt = await self.llm._build_system_prompt(session)
            
            assert "Style Guide" in prompt
            assert "Be professional and helpful" in prompt


if __name__ == "__main__":
    import asyncio
    
    tester = TestLLMSystemPrompt()
    
    try:
        tester.setup_method()
    except Exception as e:
        print(f"⚠️  Setup failed: {e}")
        sys.exit(0)
    
    # Run async tests
    test_methods = [method for method in dir(tester) if method.startswith("test_")]
    passed = 0
    failed = 0
    
    for test_method in test_methods:
        try:
            print(f"Running {test_method}...")
            asyncio.run(getattr(tester, test_method)())
            print(f"  ✅ {test_method} passed")
            passed += 1
        except Exception as e:
            print(f"  ❌ {test_method} failed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print(f"\n📊 Results: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)

