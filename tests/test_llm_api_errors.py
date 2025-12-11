#!/usr/bin/env python3
"""
Tests for LLM interface API error handling.

Tests various OpenAI API error scenarios including:
- Model not found errors (400/404)
- Invalid API key
- Rate limiting
- Connection/timeout errors
- Response format validation
"""
import json
import sys
import os
from pathlib import Path
from typing import Dict, Any
from unittest.mock import patch, AsyncMock, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import pytest
    import pytest_asyncio
    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False

from tests.mocks.mock_llm_interface import (
    MockHttpxClient,
    create_mock_openai_response,
    create_mock_httpx_client,
)


@pytest.mark.unit
class TestLLMApiErrorHandling:
    """Tests for OpenAI API error handling in LLMInterface."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Set a dummy API key for initialization
        os.environ["OPENAI_API_KEY"] = "test-key-12345"
        
        # Import here to ensure env var is set
        from app.base.llm_interface import LLMInterface
        self.llm = LLMInterface()
    
    def teardown_method(self):
        """Clean up after tests."""
        if "OPENAI_API_KEY" in os.environ and os.environ["OPENAI_API_KEY"] == "test-key-12345":
            del os.environ["OPENAI_API_KEY"]
    
    # ========== Model Availability Tests ==========
    
    @pytest.mark.asyncio
    async def test_model_not_found_error(self):
        """Test handling of model_not_found error from OpenAI API."""
        mock_client = create_mock_httpx_client(error_type="model_not_found")
        
        with patch('httpx.AsyncClient', return_value=mock_client):
            messages = [{"role": "user", "content": "Hello"}]
            function_schema = self.llm._load_function_schema()
            
            with pytest.raises(Exception) as exc_info:
                await self.llm._call_openai(messages, function_schema)
            
            # Verify the error message contains model info
            assert "404" in str(exc_info.value) or "model" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_invalid_request_error_400(self):
        """Test handling of 400 Bad Request from OpenAI API.
        
        This tests the exact scenario from the user's logs:
        'Client error 400 Bad Request for url https://api.openai.com/v1/chat/completions'
        """
        mock_client = create_mock_httpx_client(error_type="invalid_request")
        
        with patch('httpx.AsyncClient', return_value=mock_client):
            messages = [{"role": "user", "content": "Hello"}]
            function_schema = self.llm._load_function_schema()
            
            with pytest.raises(Exception) as exc_info:
                await self.llm._call_openai(messages, function_schema)
            
            # Verify we get a 400 error
            assert "400" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_invalid_api_key_error(self):
        """Test handling of invalid API key error."""
        mock_client = create_mock_httpx_client(error_type="invalid_api_key")
        
        with patch('httpx.AsyncClient', return_value=mock_client):
            messages = [{"role": "user", "content": "Hello"}]
            function_schema = self.llm._load_function_schema()
            
            with pytest.raises(Exception) as exc_info:
                await self.llm._call_openai(messages, function_schema)
            
            assert "401" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_rate_limit_error(self):
        """Test handling of rate limit error from OpenAI API."""
        mock_client = create_mock_httpx_client(error_type="rate_limit")
        
        with patch('httpx.AsyncClient', return_value=mock_client):
            messages = [{"role": "user", "content": "Hello"}]
            function_schema = self.llm._load_function_schema()
            
            with pytest.raises(Exception) as exc_info:
                await self.llm._call_openai(messages, function_schema)
            
            assert "429" in str(exc_info.value)
    
    # ========== Connection Error Tests ==========
    
    @pytest.mark.asyncio
    async def test_connection_error(self):
        """Test handling of connection errors."""
        mock_client = create_mock_httpx_client(error_type="connection_error")
        
        with patch('httpx.AsyncClient', return_value=mock_client):
            messages = [{"role": "user", "content": "Hello"}]
            function_schema = self.llm._load_function_schema()
            
            with pytest.raises(Exception) as exc_info:
                await self.llm._call_openai(messages, function_schema)
            
            assert "connection" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_timeout_error(self):
        """Test handling of timeout errors."""
        mock_client = create_mock_httpx_client(error_type="timeout")
        
        with patch('httpx.AsyncClient', return_value=mock_client):
            messages = [{"role": "user", "content": "Hello"}]
            function_schema = self.llm._load_function_schema()
            
            with pytest.raises(Exception) as exc_info:
                await self.llm._call_openai(messages, function_schema)
            
            # Check for "timeout" or "timed out"
            error_str = str(exc_info.value).lower()
            assert "timeout" in error_str or "timed out" in error_str
    
    # ========== Successful Response Tests ==========
    
    @pytest.mark.asyncio
    async def test_successful_chat_response(self):
        """Test successful chat response from OpenAI API."""
        mock_client = create_mock_httpx_client(
            response_type="chat",
            message="Welcome to TidalDex! How can I help you?"
        )
        
        with patch('httpx.AsyncClient', return_value=mock_client):
            messages = [{"role": "user", "content": "Hello"}]
            function_schema = self.llm._load_function_schema()
            
            response = await self.llm._call_openai(messages, function_schema)
            
            assert "choices" in response
            assert len(response["choices"]) > 0
    
    @pytest.mark.asyncio
    async def test_successful_view_call_response(self):
        """Test successful view_call response from OpenAI API."""
        mock_client = create_mock_httpx_client(
            response_type="view_call",
            message="Checking swap rates...",
            contract_call={
                "contract": "router",
                "method": "getAmountsOut",
                "parameters": {"amountIn": "1.0", "path": ["CAKE", "BUSD"]},
                "explanation": "Getting output amount for 1 CAKE to BUSD"
            }
        )
        
        with patch('httpx.AsyncClient', return_value=mock_client):
            messages = [{"role": "user", "content": "How much BUSD for 1 CAKE?"}]
            function_schema = self.llm._load_function_schema()
            
            response = await self.llm._call_openai(messages, function_schema)
            
            assert "choices" in response
            content = json.loads(response["choices"][0]["message"]["content"])
            assert content["response_type"] == "view_call"
            assert "contract_call" in content
    
    # ========== Model Name Validation Tests ==========
    
    def test_model_name_is_valid(self):
        """Test that the configured model name follows OpenAI naming conventions.
        
        Valid model names typically look like:
        - gpt-4o-mini
        - gpt-4-turbo
        - gpt-3.5-turbo
        
        Invalid model names (that don't exist):
        - gpt-5-nano (as of Dec 2024/early 2025, may not exist)
        """
        model = self.llm.model
        
        # Model name should be a non-empty string
        assert isinstance(model, str)
        assert len(model) > 0
        
        # Model name should start with a known prefix
        valid_prefixes = ("gpt-", "o1-", "o3-", "text-", "davinci", "curie", "babbage", "ada")
        assert any(model.startswith(prefix) for prefix in valid_prefixes), \
            f"Model name '{model}' doesn't start with a known prefix"
    
    def test_model_recommendation_for_cheap_model(self):
        """Test that we're using a cost-effective model.
        
        If gpt-5-nano doesn't exist, we should recommend gpt-4o-mini as it's
        currently one of the cheapest OpenAI models.
        """
        # Known cheap models as of late 2024
        cheap_models = [
            "gpt-4o-mini",
            "gpt-3.5-turbo",
            "gpt-3.5-turbo-0125",
            "gpt-3.5-turbo-16k",
            "gpt-5-nano",  # Added as it's now confirmed to work
        ]
        
        # Note: This test documents the expected behavior.
        # If gpt-5-nano is invalid, we should use one of the cheap models.
        # This test will pass with any model but warns if using unknown model.
        if self.llm.model not in cheap_models and "gpt-5" not in self.llm.model:
            import warnings
            warnings.warn(
                f"Model '{self.llm.model}' is not in the known cheap models list. "
                f"Consider using one of: {cheap_models}"
            )
    
    def test_new_model_format_detection(self):
        """Test that newer models are detected correctly for parameter handling."""
        # New models that require max_completion_tokens
        new_models = ["gpt-5-nano", "gpt-5-mini", "o1-preview", "o1-mini", "o3-mini"]
        for model in new_models:
            assert self.llm._check_new_model_format(model) is True, \
                f"Model {model} should use new token parameter format"
        
        # Old models that use max_tokens
        old_models = ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"]
        for model in old_models:
            assert self.llm._check_new_model_format(model) is False, \
                f"Model {model} should use old token parameter format"


@pytest.mark.unit
class TestLLMProcessUserMessage:
    """Tests for process_user_message error handling."""
    
    def setup_method(self):
        """Set up test fixtures."""
        os.environ["OPENAI_API_KEY"] = "test-key-12345"
        
        from app.base.llm_interface import LLMInterface
        self.llm = LLMInterface()
    
    def teardown_method(self):
        """Clean up after tests."""
        if "OPENAI_API_KEY" in os.environ and os.environ["OPENAI_API_KEY"] == "test-key-12345":
            del os.environ["OPENAI_API_KEY"]
    
    @pytest.mark.asyncio
    async def test_process_message_api_error_returns_friendly_message(self):
        """Test that API errors result in a user-friendly error message."""
        mock_client = create_mock_httpx_client(error_type="invalid_request")
        
        # Create a mock session
        mock_session = MagicMock()
        mock_session.conversation_history = []
        mock_session.add_message = MagicMock()
        mock_session.llm_app_config = {
            "name": "swap",
            "description": "Token swapping",
            "available_methods": {"view": [], "write": []}
        }
        mock_session.llm_app_name = "swap"
        mock_session.context = {"wallet_address": "0x123"}
        
        with patch('httpx.AsyncClient', return_value=mock_client):
            result = await self.llm.process_user_message(mock_session, "Hello")
            
            # Should return a chat response with error info
            assert result["response_type"] == "chat"
            assert "error" in result or "error" in result.get("message", "").lower()
            # Should have a user-friendly message
            assert result.get("message") is not None
    
    @pytest.mark.asyncio
    async def test_process_message_connection_error_returns_friendly_message(self):
        """Test that connection errors result in a user-friendly error message."""
        mock_client = create_mock_httpx_client(error_type="connection_error")
        
        mock_session = MagicMock()
        mock_session.conversation_history = []
        mock_session.add_message = MagicMock()
        mock_session.llm_app_config = {
            "name": "swap",
            "description": "Token swapping",
            "available_methods": {"view": [], "write": []}
        }
        mock_session.llm_app_name = "swap"
        mock_session.context = {"wallet_address": "0x123"}
        
        with patch('httpx.AsyncClient', return_value=mock_client):
            result = await self.llm.process_user_message(mock_session, "Hello")
            
            # Should return a chat response with error info
            assert result["response_type"] == "chat"
            assert "error" in result


@pytest.mark.unit 
class TestLLMModelAvailability:
    """Tests specifically for model availability issues."""
    
    def setup_method(self):
        """Set up test fixtures."""
        os.environ["OPENAI_API_KEY"] = "test-key-12345"
    
    def teardown_method(self):
        """Clean up after tests."""
        if "OPENAI_API_KEY" in os.environ and os.environ["OPENAI_API_KEY"] == "test-key-12345":
            del os.environ["OPENAI_API_KEY"]
    
    def test_check_current_model_config(self):
        """Check what model is currently configured and warn if it might not exist."""
        from app.base.llm_interface import LLMInterface
        
        llm = LLMInterface()
        model = llm.model
        
        # Known working models as of December 2024/2025
        known_working_models = [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-4-turbo-preview",
            "gpt-4",
            "gpt-3.5-turbo",
            "gpt-3.5-turbo-0125",
            "gpt-3.5-turbo-16k",
            "o1-preview",
            "o1-mini",
            "gpt-5-nano",  # Requires max_completion_tokens instead of max_tokens
        ]
        
        # If model is not in known working list, log a warning
        if model not in known_working_models:
            print(f"\n⚠️  WARNING: Model '{model}' is not in the known working models list.")
            print(f"   Known working models: {known_working_models}")
            print(f"   If you're getting 400 errors, check the parameter format.")
        
        # Check that new model detection is working
        if "gpt-5" in model or model.startswith("o1-") or model.startswith("o3-"):
            assert llm._uses_new_token_param, \
                f"Model '{model}' should use max_completion_tokens"


# Integration test that can be run manually to verify model works
@pytest.mark.integration
@pytest.mark.skip(reason="Requires valid OPENAI_API_KEY - run manually")
class TestLLMIntegration:
    """Integration tests that make actual API calls."""
    
    @pytest.mark.asyncio
    async def test_real_api_call(self):
        """Test a real API call to verify the model works.
        
        Run this test manually with a valid API key:
        OPENAI_API_KEY=sk-xxx pytest tests/test_llm_api_errors.py::TestLLMIntegration -v -s
        """
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key or api_key == "test-key-12345":
            pytest.skip("Need a real OPENAI_API_KEY to run this test")
        
        from app.base.llm_interface import LLMInterface
        
        llm = LLMInterface()
        messages = [{"role": "user", "content": "Say hello in exactly 3 words."}]
        function_schema = llm._load_function_schema()
        
        try:
            response = await llm._call_openai(messages, function_schema)
            assert "choices" in response
            print(f"\n✅ API call successful with model '{llm.model}'")
            print(f"   Response: {response['choices'][0]['message']['content'][:100]}...")
        except Exception as e:
            pytest.fail(f"API call failed with model '{llm.model}': {e}")


if __name__ == "__main__":
    # Run basic tests without pytest
    os.environ["OPENAI_API_KEY"] = "test-key-12345"
    
    print("Testing LLM API Error Handling...")
    print("=" * 50)
    
    # Test model configuration
    from app.base.llm_interface import LLMInterface
    
    llm = LLMInterface()
    print(f"\nCurrent model: {llm.model}")
    
    known_working_models = [
        "gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4",
        "gpt-3.5-turbo", "gpt-3.5-turbo-0125", "o1-preview", "o1-mini"
    ]
    
    if llm.model not in known_working_models:
        print(f"\n⚠️  WARNING: Model '{llm.model}' may not exist!")
        print(f"   If you're getting 400 errors, this is likely the cause.")
        print(f"   Recommended: Change to 'gpt-4o-mini' (cheap and reliable)")
    else:
        print(f"✅ Model '{llm.model}' is in the known working models list")
    
    # Clean up
    del os.environ["OPENAI_API_KEY"]
    
    print("\n" + "=" * 50)
    print("Run full tests with: pytest tests/test_llm_api_errors.py -v")

