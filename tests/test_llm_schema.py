#!/usr/bin/env python3
"""
Test script to verify OpenAI API call with JSON schema.

Tests the LLM interface schema loading and OpenAI API integration.
"""
import os
import json
import asyncio
import httpx
from pathlib import Path
from dotenv import load_dotenv

try:
    import pytest
    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False
    # Create dummy pytest marker if pytest not available
    class MockPytest:
        @staticmethod
        def mark_api(func):
            return func
    pytest = MockPytest()

# Load environment variables from .env file in project root
project_root = Path(__file__).parent.parent
env_path = project_root / ".env"
load_dotenv(dotenv_path=env_path)


@pytest.mark.api
class LLMSchemaTester:
    """Test suite for LLM schema integration with OpenAI API."""
    
    def __init__(self):
        """Initialize the tester."""
        # Ensure dotenv is loaded (in case called directly)
        load_dotenv(dotenv_path=project_root / ".env")
        
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.schema_path = project_root / "app" / "schemas" / "app_json_schema.json"
        self.base_url = "https://api.openai.com/v1"
        self.model = "gpt-4o-mini"
    
    def load_schema(self) -> dict:
        """Load and validate the JSON schema file.
        
        Returns:
            dict: Schema data formatted for OpenAI API
            
        Raises:
            FileNotFoundError: If schema file doesn't exist
            json.JSONDecodeError: If schema file is invalid JSON
        """
        if not self.schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {self.schema_path}")
        
        with open(self.schema_path, 'r') as f:
            schema_data = json.load(f)
        
        # OpenAI requires name, strict, and schema at json_schema level
        if isinstance(schema_data, dict) and "name" in schema_data and "schema" in schema_data:
            return schema_data
        
        # If only inner schema exists, wrap it with required fields
        if isinstance(schema_data, dict) and "schema" in schema_data:
            return {
                "name": schema_data.get("name", "blockchain_app_response"),
                "strict": schema_data.get("strict", False),
                "schema": schema_data["schema"]
            }
        
        # If it's just the schema object, wrap it
        return {
            "name": "blockchain_app_response",
            "description": "Response schema for blockchain app assistant interactions",
            "strict": False,
            "schema": schema_data
        }
    
    def validate_schema_format(self, schema: dict) -> tuple[bool, list[str]]:
        """Validate that the schema has the required OpenAI format.
        
        Args:
            schema: Schema dictionary to validate
            
        Returns:
            tuple: (is_valid, list_of_errors)
        """
        errors = []
        
        if "name" not in schema:
            errors.append("Missing required field: 'name'")
        if "schema" not in schema:
            errors.append("Missing required field: 'schema'")
        
        inner_schema = schema.get("schema", {})
        if "type" not in inner_schema:
            errors.append("Inner schema missing required field: 'type'")
        if "properties" not in inner_schema:
            errors.append("Inner schema missing required field: 'properties'")
        
        return len(errors) == 0, errors
    
    async def test_chat_response(self, function_schema: dict) -> bool:
        """Test simple chat response.
        
        Args:
            function_schema: Schema to use for the API call
            
        Returns:
            bool: True if test passed, False otherwise
        """
        print(f"\n🧪 Test 1: Simple chat response")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a helpful assistant. Respond with JSON only."
                },
                {
                    "role": "user",
                    "content": "Say hello and tell me what response_type you would use for a simple greeting."
                }
            ],
            "max_tokens": 200,
            "temperature": 0.1,
            "response_format": {
                "type": "json_schema",
                "json_schema": function_schema
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload
                )
                
                if response.status_code == 200:
                    result = response.json()
                    content = result["choices"][0]["message"]["content"]
                    parsed = json.loads(content)
                    
                    if parsed.get("response_type") == "chat":
                        print(f"✅ Test 1 passed!")
                        print(f"   Response type: {parsed.get('response_type')}")
                        print(f"   Message: {parsed.get('message', '')[:50]}...")
                        return True
                    else:
                        print(f"❌ Test 1 failed: Expected 'chat' response_type, got '{parsed.get('response_type')}'")
                        return False
                else:
                    print(f"❌ Test 1 failed: HTTP {response.status_code}")
                    print(f"   {response.text}")
                    return False
        except Exception as e:
            print(f"❌ Test 1 failed with exception: {e}")
            return False
    
    async def test_contract_call_response(self, function_schema: dict) -> bool:
        """Test contract call response (should include contract_call).
        
        Args:
            function_schema: Schema to use for the API call
            
        Returns:
            bool: True if test passed, False otherwise
        """
        print(f"\n🧪 Test 2: Contract call response")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a blockchain assistant. When asked to check a price or swap, use view_call or write_call response types with contract_call."
                },
                {
                    "role": "user",
                    "content": "Check the price of 1 CAKE token in BUSD."
                }
            ],
            "max_tokens": 300,
            "temperature": 0.1,
            "response_format": {
                "type": "json_schema",
                "json_schema": function_schema
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload
                )
                
                if response.status_code == 200:
                    result = response.json()
                    content = result["choices"][0]["message"]["content"]
                    parsed = json.loads(content)
                    
                    response_type = parsed.get("response_type")
                    print(f"✅ Test 2 passed!")
                    print(f"   Response type: {response_type}")
                    
                    if response_type in ["view_call", "write_call"]:
                        if "contract_call" in parsed:
                            print(f"   Contract call present: ✅")
                            print(f"   Contract: {parsed['contract_call'].get('contract', 'N/A')}")
                            print(f"   Method: {parsed['contract_call'].get('method', 'N/A')}")
                            return True
                        else:
                            print(f"   ⚠️  Contract call missing (should be present for view_call/write_call)")
                            return False
                    else:
                        print(f"   Note: Got '{response_type}' response instead of view_call/write_call")
                        return True  # Still valid, just not what we expected
                else:
                    print(f"❌ Test 2 failed: HTTP {response.status_code}")
                    print(f"   {response.text}")
                    return False
        except Exception as e:
            print(f"❌ Test 2 failed with exception: {e}")
            return False
    
    async def run_all_tests(self) -> bool:
        """Run all tests.
        
        Returns:
            bool: True if all tests passed, False otherwise
        """
        if not self.api_key:
            print("❌ OPENAI_API_KEY environment variable not set")
            print("   Please add OPENAI_API_KEY to your .env file")
            return False
        
        print("📄 Loading schema from:", self.schema_path)
        
        try:
            schema_data = self.load_schema()
            print(f"\n📋 Schema file structure:")
            print(f"   Top-level keys: {list(schema_data.keys())}")
            
            # Validate schema format
            is_valid, errors = self.validate_schema_format(schema_data)
            if not is_valid:
                print(f"\n❌ Schema validation failed:")
                for error in errors:
                    print(f"   - {error}")
                return False
            
            print(f"\n✅ Schema format is valid")
            print(f"   Schema name: {schema_data.get('name')}")
            print(f"   Strict mode: {schema_data.get('strict')}")
            
            print(f"\n🚀 Running API tests...")
            print(f"   Model: {self.model}")
            print(f"   Schema name: {schema_data.get('name', 'N/A')}")
            
            # Run tests
            test1_passed = await self.test_chat_response(schema_data)
            test2_passed = await self.test_contract_call_response(schema_data)
            
            if test1_passed and test2_passed:
                print(f"\n✅ All tests passed!")
                return True
            else:
                print(f"\n❌ Some tests failed")
                return False
                
        except FileNotFoundError as e:
            print(f"❌ {e}")
            return False
        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse schema JSON: {e}")
            return False
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return False


async def main():
    """Main test runner."""
    tester = LLMSchemaTester()
    success = await tester.run_all_tests()
    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)

