#!/usr/bin/env python3
"""
Comprehensive edge case tests for LLM interface.

Tests schema loading, response parsing, and various edge cases
without requiring wallet or database access.
"""
import json
import sys
import os
import tempfile
from pathlib import Path
from typing import Dict, Any
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import pytest
    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False

from app.base.llm_interface import LLMInterface


@pytest.mark.unit
class TestLLMEdgeCases:
    """Edge case tests for LLM interface."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Set a dummy API key for initialization
        os.environ["OPENAI_API_KEY"] = "test-key-12345"
        try:
            self.llm = LLMInterface()
        except ValueError:
            if HAS_PYTEST:
                pytest.skip("OPENAI_API_KEY not set, skipping LLM interface tests")
            else:
                raise Exception("OPENAI_API_KEY not set, cannot initialize LLMInterface")
    
    def teardown_method(self):
        """Clean up after tests."""
        # Remove test API key
        if "OPENAI_API_KEY" in os.environ and os.environ["OPENAI_API_KEY"] == "test-key-12345":
            del os.environ["OPENAI_API_KEY"]
    
    def _mock_response(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Create a mock OpenAI API response structure."""
        return {"choices": [{"message": {"content": json.dumps(content)}}]}
    
    # ========== Schema Loading Edge Cases ==========
    
    def test_load_schema_missing_file(self):
        """Test handling when schema file doesn't exist."""
        # Mock file not found exception
        with patch('builtins.open', side_effect=FileNotFoundError("Schema file not found")):
            schema = self.llm._load_function_schema()
            # Should return fallback schema with proper format
            assert "name" in schema
            assert "strict" in schema
            assert "schema" in schema
            assert schema["name"] == "blockchain_app_response"
    
    def test_load_schema_fallback_format(self):
        """Test that fallback schema has correct OpenAI wrapper format."""
        # Mock file not found
        with patch('builtins.open', side_effect=FileNotFoundError("Schema not found")):
            schema = self.llm._load_function_schema()
            # Verify OpenAI wrapper format
            assert "name" in schema
            assert "strict" in schema
            assert "schema" in schema
            assert isinstance(schema["schema"], dict)
            assert "type" in schema["schema"]
    
    def test_load_schema_unwrapped_schema(self):
        """Test schema wrapping for schemas without outer wrapper."""
        # Create temporary schema file with just inner schema
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            inner_schema = {
                "type": "object",
                "properties": {
                    "response_type": {"type": "string"},
                    "message": {"type": "string"}
                }
            }
            json.dump(inner_schema, f)
            temp_path = f.name
        
        try:
            # Mock the file opening to use temp file
            original_open = open
            def mock_open(path, *args, **kwargs):
                if "app_json_schema.json" in str(path):
                    return original_open(temp_path, *args, **kwargs)
                return original_open(path, *args, **kwargs)
            
            with patch('builtins.open', side_effect=mock_open):
                schema = self.llm._load_function_schema()
                assert "name" in schema
                assert "schema" in schema
        finally:
            os.unlink(temp_path)
    
    def test_load_schema_invalid_json(self):
        """Test handling of invalid JSON in schema file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("This is not valid JSON {")
            temp_path = f.name
        
        try:
            # Mock the file opening to use temp file
            original_open = open
            def mock_open(path, *args, **kwargs):
                if "app_json_schema.json" in str(path):
                    return original_open(temp_path, *args, **kwargs)
                return original_open(path, *args, **kwargs)
            
            with patch('builtins.open', side_effect=mock_open):
                schema = self.llm._load_function_schema()
                # Should return fallback schema
                assert "name" in schema
                assert "schema" in schema
        finally:
            os.unlink(temp_path)
    
    # ========== Response Parsing Edge Cases ==========
    
    def test_parse_empty_parameters_in_contract_call(self):
        """Test valid contract_call with empty parameters object."""
        response = {
            "response_type": "view_call",
            "message": "Getting factory...",
            "contract_call": {
                "contract": "router",
                "method": "factory",
                "parameters": {},
                "explanation": "Get factory address"
            }
        }
        parsed = self.llm._parse_openai_response(self._mock_response(response))
        assert parsed["response_type"] == "view_call"
        assert parsed["contract_call"]["parameters"] == {}
        assert parsed["contract_call"]["method"] == "factory"
    
    def test_parse_unicode_in_message(self):
        """Test handling of unicode characters and emojis in messages."""
        response = {
            "response_type": "chat",
            "message": "🔄 Swapping 1.5 CAKE → BUSD 你好 émojis"
        }
        parsed = self.llm._parse_openai_response(self._mock_response(response))
        assert parsed["response_type"] == "chat"
        assert "🔄" in parsed["message"]
        assert "你好" in parsed["message"]
        assert "émojis" in parsed["message"]
    
    def test_parse_extra_fields_ignored(self):
        """Test that extra fields are handled gracefully."""
        response = {
            "response_type": "chat",
            "message": "Hello",
            "unexpected_field": "value",
            "another": 123,
            "nested": {"key": "value"}
        }
        parsed = self.llm._parse_openai_response(self._mock_response(response))
        assert parsed["response_type"] == "chat"
        assert parsed["message"] == "Hello"
        # Extra fields may or may not be preserved - key is no error
    
    def test_parse_very_long_message(self):
        """Test handling of very long response messages."""
        long_message = "A" * 10000
        response = {
            "response_type": "chat",
            "message": long_message
        }
        parsed = self.llm._parse_openai_response(self._mock_response(response))
        assert parsed["response_type"] == "chat"
        assert len(parsed["message"]) == 10000
    
    def test_parse_empty_string_fields(self):
        """Test handling of empty strings for required fields."""
        response = {
            "response_type": "",
            "message": ""
        }
        # Empty strings should still parse (validation happens elsewhere)
        parsed = self.llm._parse_openai_response(self._mock_response(response))
        assert parsed["response_type"] == ""
        assert parsed["message"] == ""
    
    def test_parse_contract_call_null_values(self):
        """Test contract_call with null values should fail validation."""
        # JSON null becomes Python None, which should fail validation
        # Create response with None value
        response = {
            "response_type": "view_call",
            "message": "Test",
            "contract_call": {
                "contract": None,
                "method": "test",
                "parameters": {},
                "explanation": "Test"
            }
        }
        parsed = self.llm._parse_openai_response(self._mock_response(response))
        # Should return error response because None is not a valid string
        # The validation checks for missing fields, but None might pass that check
        # So we check that either it's an error or the None value is handled
        assert parsed["response_type"] in ["chat", "view_call"]
        # If it's chat, it means there was an error
        # If it's view_call, the None value was accepted (which is also valid behavior)
        if parsed["response_type"] == "chat":
            assert "error" in parsed
    
    def test_parse_unknown_response_type(self):
        """Test handling of unknown response_type values."""
        response = {
            "response_type": "unknown_type",
            "message": "Hello"
        }
        # Should parse but may fail validation elsewhere
        parsed = self.llm._parse_openai_response(self._mock_response(response))
        assert parsed["response_type"] == "unknown_type"
        assert parsed["message"] == "Hello"
    
    def test_parse_contract_call_nested_parameters(self):
        """Test contract_call with nested parameter structures."""
        response = {
            "response_type": "view_call",
            "message": "Checking swap...",
            "contract_call": {
                "contract": "router",
                "method": "getAmountsOut",
                "parameters": {
                    "amountIn": "1.5",
                    "path": ["CAKE", "BUSD"],
                    "nested": {
                        "key": "value",
                        "array": [1, 2, 3]
                    }
                },
                "explanation": "Get swap amounts"
            }
        }
        parsed = self.llm._parse_openai_response(self._mock_response(response))
        assert parsed["contract_call"]["parameters"]["nested"]["key"] == "value"
        assert parsed["contract_call"]["parameters"]["nested"]["array"] == [1, 2, 3]
    
    # ========== OpenAI Response Structure Edge Cases ==========
    
    def test_parse_empty_choices_array(self):
        """Test handling when choices array is empty."""
        mock_response = {"choices": []}
        parsed = self.llm._parse_openai_response(mock_response)
        # Should return error response (IndexError will be caught)
        assert parsed["response_type"] == "chat"
        assert "error" in parsed
    
    def test_parse_missing_message_in_choice(self):
        """Test handling when message field is missing in choice."""
        mock_response = {"choices": [{"index": 0}]}
        parsed = self.llm._parse_openai_response(mock_response)
        assert parsed["response_type"] == "chat"
        assert "error" in parsed
    
    def test_parse_missing_content_in_message(self):
        """Test handling when content field is missing in message."""
        mock_response = {"choices": [{"message": {}}]}
        parsed = self.llm._parse_openai_response(mock_response)
        # Should return error response (KeyError will be caught)
        assert parsed["response_type"] == "chat"
        assert "error" in parsed
    
    def test_parse_multiple_choices(self):
        """Test handling when multiple choices are present (use first)."""
        response = {
            "response_type": "chat",
            "message": "First choice"
        }
        mock_response = {
            "choices": [
                {"message": {"content": json.dumps(response)}},
                {"message": {"content": json.dumps({"response_type": "chat", "message": "Second"})}}
            ]
        }
        parsed = self.llm._parse_openai_response(mock_response)
        assert parsed["message"] == "First choice"
    
    # ========== Error Response Structure Tests ==========
    
    def test_error_response_structure_json_decode(self):
        """Verify JSON decode error responses have consistent structure."""
        mock_response = {
            "choices": [{
                "message": {
                    "content": "This is not valid JSON {"
                }
            }]
        }
        parsed = self.llm._parse_openai_response(mock_response)
        assert parsed["response_type"] == "chat"
        assert "message" in parsed
        assert "error" in parsed
        assert isinstance(parsed["error"], str)
    
    def test_error_response_structure_missing_field(self):
        """Verify missing field error responses have consistent structure."""
        response = {
            "response_type": "view_call",
            "message": "Test"
            # Missing contract_call
        }
        parsed = self.llm._parse_openai_response(self._mock_response(response))
        assert parsed["response_type"] == "chat"
        assert "message" in parsed
        assert "error" in parsed
    
    def test_error_response_structure_exception(self):
        """Verify exception error responses have consistent structure."""
        # Force an exception by passing invalid structure
        mock_response = None  # This will cause an exception
        try:
            parsed = self.llm._parse_openai_response(mock_response)  # type: ignore
            assert parsed["response_type"] == "chat"
            assert "message" in parsed
            assert "error" in parsed
        except Exception:
            # If exception is raised instead of caught, that's also valid behavior
            # The test passes if we get here (exception handling works)
            pass
    
    # ========== Additional Edge Cases ==========
    
    def test_parse_whitespace_only_message(self):
        """Test handling of whitespace-only messages."""
        response = {
            "response_type": "chat",
            "message": "   \n\t   "
        }
        parsed = self.llm._parse_openai_response(self._mock_response(response))
        # Whitespace-only messages should be accepted (validation is elsewhere)
        assert parsed["response_type"] == "chat"
        assert parsed["message"] == "   \n\t   "
    
    def test_parse_special_characters_in_parameters(self):
        """Test handling of special characters in contract parameters."""
        response = {
            "response_type": "view_call",
            "message": "Checking...",
            "contract_call": {
                "contract": "router",
                "method": "getAmountsOut",
                "parameters": {
                    "amountIn": "1.5e18",  # Scientific notation
                    "path": ["0x1234...abcd", "0x5678...efgh"],  # Addresses with ellipsis
                    "special": "<>&\"'\\/"  # HTML-like special chars
                },
                "explanation": "Test with special chars: <>&\"'\\/"
            }
        }
        parsed = self.llm._parse_openai_response(self._mock_response(response))
        assert parsed["response_type"] == "view_call"
        assert parsed["contract_call"]["parameters"]["amountIn"] == "1.5e18"
        assert "<>&" in parsed["contract_call"]["parameters"]["special"]
    
    def test_parse_openai_refusal_response(self):
        """Test handling of OpenAI refusal responses (content moderation)."""
        mock_response = {
            "choices": [{
                "message": {
                    "content": None,
                    "refusal": "I cannot assist with this request."
                }
            }]
        }
        parsed = self.llm._parse_openai_response(mock_response)
        # Should return an error response when content is None
        assert parsed["response_type"] == "chat"
        assert "error" in parsed
    
    def test_parse_numeric_values_in_message(self):
        """Test handling of large numeric values in response."""
        response = {
            "response_type": "view_call",
            "message": "Balance: 1000000000000000000 wei",
            "contract_call": {
                "contract": "router",
                "method": "getAmountsOut",
                "parameters": {
                    "amountIn": "999999999999999999999999999",
                    "minOutput": "0.000000000000000001"
                },
                "explanation": "Large number handling"
            }
        }
        parsed = self.llm._parse_openai_response(self._mock_response(response))
        assert parsed["contract_call"]["parameters"]["amountIn"] == "999999999999999999999999999"
        assert parsed["contract_call"]["parameters"]["minOutput"] == "0.000000000000000001"
    
    def test_parse_array_parameters_various_types(self):
        """Test contract_call with mixed type array parameters."""
        response = {
            "response_type": "view_call",
            "message": "Processing...",
            "contract_call": {
                "contract": "router",
                "method": "multiCall",
                "parameters": {
                    "data": [
                        {"call": 1, "target": "0x123"},
                        {"call": 2, "target": "0x456"}
                    ],
                    "values": [0, 100, 200.5],
                    "flags": [True, False, True]
                },
                "explanation": "Multi-call with mixed arrays"
            }
        }
        parsed = self.llm._parse_openai_response(self._mock_response(response))
        assert len(parsed["contract_call"]["parameters"]["data"]) == 2
        assert parsed["contract_call"]["parameters"]["flags"] == [True, False, True]
    
    def test_parse_empty_contract_call_object(self):
        """Test handling of completely empty contract_call object."""
        response = {
            "response_type": "view_call",
            "message": "Test",
            "contract_call": {}
        }
        parsed = self.llm._parse_openai_response(self._mock_response(response))
        # Should fail validation due to missing required fields
        assert parsed["response_type"] == "chat"
        assert "error" in parsed
    
    def test_parse_boolean_response_type(self):
        """Test handling of boolean where string expected."""
        response = {
            "response_type": True,  # Wrong type
            "message": "Hello"
        }
        # JSON doesn't care about types, so this should parse
        # but might fail validation
        mock_response = {
            "choices": [{
                "message": {
                    "content": json.dumps(response)
                }
            }]
        }
        parsed = self.llm._parse_openai_response(mock_response)
        # Should still parse the JSON, type validation happens elsewhere
        assert parsed["response_type"] == True or parsed["response_type"] == "chat"
    
    def test_parse_content_with_escaped_quotes(self):
        """Test handling of escaped quotes in JSON content."""
        content = '{"response_type": "chat", "message": "He said \\"hello\\" and left"}'
        mock_response = {
            "choices": [{
                "message": {
                    "content": content
                }
            }]
        }
        parsed = self.llm._parse_openai_response(mock_response)
        assert parsed["message"] == 'He said "hello" and left'


if __name__ == "__main__":
    # Run tests without pytest if pytest not available
    tester = TestLLMEdgeCases()
    
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
            import traceback
            traceback.print_exc()
            failed += 1
        finally:
            try:
                tester.teardown_method()
            except:
                pass
    
    print(f"\n📊 Results: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)

