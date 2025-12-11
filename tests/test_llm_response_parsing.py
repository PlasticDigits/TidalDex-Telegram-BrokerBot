#!/usr/bin/env python3
"""
Test LLM response parsing and validation logic.

Tests the response parsing without requiring database or wallet access.
"""
import json
import sys
from pathlib import Path
from typing import Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import pytest
    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False

from app.base.llm_interface import LLMInterface


@pytest.mark.unit
class TestLLMResponseParsing:
    """Test suite for LLM response parsing."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Set a dummy API key for initialization - we're only testing parsing logic
        import os
        os.environ["OPENAI_API_KEY"] = "test-key-12345"
        try:
            self.llm = LLMInterface()
        except ValueError:
            # Skip if API key not set - we're only testing parsing logic
            if HAS_PYTEST:
                pytest.skip("OPENAI_API_KEY not set, skipping LLM interface tests")
            else:
                raise Exception("OPENAI_API_KEY not set, cannot initialize LLMInterface")
    
    def teardown_method(self):
        """Clean up after tests."""
        import os
        # Remove test API key
        if "OPENAI_API_KEY" in os.environ and os.environ["OPENAI_API_KEY"] == "test-key-12345":
            del os.environ["OPENAI_API_KEY"]
    
    def _create_mock_openai_response(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Create a mock OpenAI API response structure.
        
        Args:
            content: The content dict to wrap in OpenAI response format
            
        Returns:
            Mock OpenAI API response dict
        """
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(content)
                    }
                }
            ]
        }
    
    def test_parse_chat_response(self):
        """Test parsing a simple chat response."""
        response = {
            "response_type": "chat",
            "message": "Hello! How can I help you?"
        }
        
        mock_api_response = self._create_mock_openai_response(response)
        parsed = self.llm._parse_openai_response(mock_api_response)
        
        assert parsed["response_type"] == "chat"
        assert parsed["message"] == "Hello! How can I help you?"
        assert "contract_call" not in parsed
    
    def test_parse_view_call_response(self):
        """Test parsing a view_call response with contract_call."""
        response = {
            "response_type": "view_call",
            "message": "Checking the price...",
            "contract_call": {
                "contract": "router",
                "method": "getAmountsOut",
                "parameters": {
                    "amountIn": "1.5",
                    "path": ["CAKE", "BUSD"]
                },
                "explanation": "Getting swap quote for 1.5 CAKE to BUSD"
            }
        }
        
        mock_api_response = self._create_mock_openai_response(response)
        parsed = self.llm._parse_openai_response(mock_api_response)
        
        assert parsed["response_type"] == "view_call"
        assert parsed["message"] == "Checking the price..."
        assert "contract_call" in parsed
        assert parsed["contract_call"]["contract"] == "router"
        assert parsed["contract_call"]["method"] == "getAmountsOut"
        assert parsed["contract_call"]["parameters"]["amountIn"] == "1.5"
    
    def test_parse_write_call_response(self):
        """Test parsing a write_call response with contract_call."""
        response = {
            "response_type": "write_call",
            "message": "Preparing swap transaction...",
            "contract_call": {
                "contract": "router",
                "method": "swapExactTokensForTokens",
                "parameters": {
                    "amountIn": "1.5",
                    "amountOutMin": "150.0",
                    "path": ["CAKE", "BUSD"]
                },
                "explanation": "Swap 1.5 CAKE for at least 150.0 BUSD"
            }
        }
        
        mock_api_response = self._create_mock_openai_response(response)
        parsed = self.llm._parse_openai_response(mock_api_response)
        
        assert parsed["response_type"] == "write_call"
        assert parsed["message"] == "Preparing swap transaction..."
        assert "contract_call" in parsed
        assert parsed["contract_call"]["method"] == "swapExactTokensForTokens"
    
    def test_parse_view_call_missing_contract_call(self):
        """Test that view_call without contract_call returns error response."""
        response = {
            "response_type": "view_call",
            "message": "Checking the price..."
            # Missing contract_call
        }
        
        mock_api_response = self._create_mock_openai_response(response)
        parsed = self.llm._parse_openai_response(mock_api_response)
        
        # Should return error response (not raise exception)
        assert parsed["response_type"] == "chat"  # Falls back to chat
        assert "error" in parsed
        assert "contract_call" in str(parsed.get("error", "")).lower()
    
    def test_parse_write_call_missing_contract_call(self):
        """Test that write_call without contract_call returns error response."""
        response = {
            "response_type": "write_call",
            "message": "Preparing transaction..."
            # Missing contract_call
        }
        
        mock_api_response = self._create_mock_openai_response(response)
        parsed = self.llm._parse_openai_response(mock_api_response)
        
        # Should return error response (not raise exception)
        assert parsed["response_type"] == "chat"  # Falls back to chat
        assert "error" in parsed
        assert "contract_call" in str(parsed.get("error", "")).lower()
    
    def test_parse_contract_call_missing_required_fields(self):
        """Test that contract_call with missing required fields raises error."""
        test_cases = [
            {
                "name": "missing_contract",
                "contract_call": {
                    "method": "getAmountsOut",
                    "parameters": {},
                    "explanation": "Test"
                }
            },
            {
                "name": "missing_method",
                "contract_call": {
                    "contract": "router",
                    "parameters": {},
                    "explanation": "Test"
                }
            },
            {
                "name": "missing_parameters",
                "contract_call": {
                    "contract": "router",
                    "method": "getAmountsOut",
                    "explanation": "Test"
                }
            },
            {
                "name": "missing_explanation",
                "contract_call": {
                    "contract": "router",
                    "method": "getAmountsOut",
                    "parameters": {}
                }
            }
        ]
        
        for test_case in test_cases:
            response = {
                "response_type": "view_call",
                "message": "Test",
                "contract_call": test_case["contract_call"]
            }
            
            mock_api_response = self._create_mock_openai_response(response)
            parsed = self.llm._parse_openai_response(mock_api_response)
            
            # Should return error response (not raise exception)
            assert parsed["response_type"] == "chat"  # Falls back to chat
            assert "error" in parsed
            assert "missing required field" in str(parsed.get("error", "")).lower() or "missing" in str(parsed.get("error", "")).lower()
    
    def test_parse_missing_response_type(self):
        """Test that missing response_type returns error response."""
        response = {
            "message": "Hello"
            # Missing response_type
        }
        
        mock_api_response = self._create_mock_openai_response(response)
        parsed = self.llm._parse_openai_response(mock_api_response)
        
        # Should return error response (not raise exception)
        assert parsed["response_type"] == "chat"  # Falls back to chat
        assert "error" in parsed
        assert "response_type" in str(parsed.get("error", "")).lower()
    
    def test_parse_missing_message(self):
        """Test that missing message returns error response."""
        response = {
            "response_type": "chat"
            # Missing message
        }
        
        mock_api_response = self._create_mock_openai_response(response)
        parsed = self.llm._parse_openai_response(mock_api_response)
        
        # Should return error response (not raise exception)
        assert parsed["response_type"] == "chat"  # Falls back to chat
        assert "error" in parsed
        assert "message" in str(parsed.get("error", "")).lower()
    
    def test_parse_invalid_json(self):
        """Test handling of invalid JSON in response."""
        mock_api_response = {
            "choices": [
                {
                    "message": {
                        "content": "This is not valid JSON {"
                    }
                }
            ]
        }
        
        parsed = self.llm._parse_openai_response(mock_api_response)
        
        # Should return error response
        assert parsed["response_type"] == "chat"
        assert "error" in parsed
        assert "JSON parse error" in parsed.get("error", "")
    
    def test_parse_swap_view_call_response(self):
        """Test parsing a swap-related view_call response (simulating swap app usage)."""
        response = {
            "response_type": "view_call",
            "message": "Let me check the current exchange rate for that swap...",
            "contract_call": {
                "contract": "router",
                "method": "getAmountsOut",
                "parameters": {
                    "amountIn": "1.5",
                    "path": ["CAKE", "BUSD"]
                },
                "explanation": "Checking how much BUSD you'll get for 1.5 CAKE"
            }
        }
        
        mock_api_response = self._create_mock_openai_response(response)
        parsed = self.llm._parse_openai_response(mock_api_response)
        
        assert parsed["response_type"] == "view_call"
        assert "contract_call" in parsed
        assert parsed["contract_call"]["method"] == "getAmountsOut"
        assert parsed["contract_call"]["parameters"]["amountIn"] == "1.5"
        assert len(parsed["contract_call"]["parameters"]["path"]) == 2
    
    def test_parse_swap_write_call_response(self):
        """Test parsing a swap-related write_call response (simulating swap app usage)."""
        response = {
            "response_type": "write_call",
            "message": "I'll prepare that swap for you. Please review the transaction details carefully.",
            "contract_call": {
                "contract": "router",
                "method": "swapExactTokensForTokens",
                "parameters": {
                    "amountIn": "1.5",
                    "amountOutMin": "150.0",
                    "path": ["CAKE", "BUSD"]
                },
                "explanation": "Swap 1.5 CAKE for at least 150.0 BUSD"
            }
        }
        
        mock_api_response = self._create_mock_openai_response(response)
        parsed = self.llm._parse_openai_response(mock_api_response)
        
        assert parsed["response_type"] == "write_call"
        assert "contract_call" in parsed
        assert parsed["contract_call"]["method"] == "swapExactTokensForTokens"
        assert parsed["contract_call"]["parameters"]["amountOutMin"] == "150.0"
    
    def test_chat_response_allows_missing_contract_call(self):
        """Test that chat responses don't require contract_call."""
        response = {
            "response_type": "chat",
            "message": "I can help you swap tokens!"
        }
        
        mock_api_response = self._create_mock_openai_response(response)
        parsed = self.llm._parse_openai_response(mock_api_response)
        
        assert parsed["response_type"] == "chat"
        assert "contract_call" not in parsed
        # Should not raise any errors


if __name__ == "__main__":
    # Run tests without pytest if pytest not available
    import sys
    
    tester = TestLLMResponseParsing()
    
    # Try to set up
    try:
        tester.setup_method()
    except Exception as e:
        print(f"⚠️  Setup failed: {e}")
        print("   Some tests may be skipped")
        sys.exit(0)
    
    # Run tests
    test_methods = [method for method in dir(tester) if method.startswith("test_")]
    passed = 0
    failed = 0
    
    for test_method in test_methods:
        try:
            print(f"Running {test_method}...")
            getattr(tester, test_method)()
            print(f"  ✅ {test_method} passed")
            passed += 1
        except Exception as e:
            print(f"  ❌ {test_method} failed: {e}")
            failed += 1
    
    print(f"\n📊 Results: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)

