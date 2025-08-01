"""
LLM interface for communicating with OpenAI to process user requests.
Handles conversation context, function calling, and response parsing.
"""
import logging
import json
import os
from typing import Dict, List, Any, Optional, Tuple
import httpx
from app.base.app_session import AppSession
from app.base.app_manager import app_manager

logger = logging.getLogger(__name__)

class LLMInterface:
    """Interface for communicating with OpenAI's language models."""
    
    def __init__(self):
        """Initialize the LLM interface."""
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        
        self.base_url = "https://api.openai.com/v1"
        self.model = "gpt-4o-mini"  # Cost-effective model for this use case
        self.max_tokens = 1000
        
    async def process_user_message(
        self,
        session: AppSession,
        user_message: str
    ) -> Dict[str, Any]:
        """Process a user message and return the assistant's response.
        
        Args:
            session: Active app session
            user_message: User's input message
            
        Returns:
            Dict containing response type and content
        """
        try:
            # Add user message to conversation history
            session.add_message("user", user_message)
            
            # Build system prompt
            system_prompt = await self._build_system_prompt(session)
            
            # Prepare messages for OpenAI
            messages = [
                {"role": "system", "content": system_prompt}
            ] + session.conversation_history
            
            # Load the function schema
            function_schema = self._load_function_schema()
            
            # Make API request
            response = await self._call_openai(messages, function_schema)
            
            # Parse response
            parsed_response = self._parse_openai_response(response)
            
            # Add assistant response to history
            if parsed_response.get("message"):
                session.add_message("assistant", parsed_response["message"])
            
            return parsed_response
            
        except Exception as e:
            logger.error(f"Failed to process user message: {str(e)}")
            return {
                "response_type": "chat",
                "message": "I encountered an error processing your request. Please try again.",
                "error": str(e)
            }
    
    async def _build_system_prompt(self, session: AppSession) -> str:
        """Build the system prompt for the LLM.
        
        Args:
            session: Active app session
            
        Returns:
            Complete system prompt string
        """
        app_config = session.app_config
        context = session.context
        
        # Load style guide
        style_guide = app_manager.load_app_style_guide(session.app_name)
        style_section = f"\n\n## Style Guide\n{style_guide}" if style_guide else ""
        
        # Format available methods
        view_methods = []
        write_methods = []
        
        for method in app_config["available_methods"].get("view", []):
            view_methods.append(f"- **{method['name']}**: {method['description']}")
        
        for method in app_config["available_methods"].get("write", []):
            write_methods.append(f"- **{method['name']}**: {method['description']}")
        
        # Format user's token balances
        balance_info = ""
        if context.get("token_balances"):
            balance_lines = []
            for token in context["token_balances"]:
                balance_lines.append(f"- {token['balance']} {token['symbol']} ({token['name']})")
            balance_info = f"\n\n**Your Token Balances:**\n" + "\n".join(balance_lines)
        
        system_prompt = f"""You are an expert assistant for the {app_config['name']} app on TidalDex.

## App Information
**Name:** {app_config['name']}
**Description:** {app_config['description']}

## User Context
**Wallet Address:** {context.get('wallet_address', 'Not available')}
{balance_info}

## Available Contract Methods

### View Methods (Read-only, no gas cost):
{chr(10).join(view_methods) if view_methods else "None"}

### Write Methods (State-changing, requires gas and confirmation):
{chr(10).join(write_methods) if write_methods else "None"}

## Important Instructions

1. **Always respond using the required JSON schema** - you must return valid JSON with response_type, message, and optionally contract_call.

2. **For view calls**: Use response_type "view_call" with the contract_call object containing the method and parameters.

3. **For write calls**: Use response_type "write_call" with the contract_call object. These will require user confirmation.

4. **For general conversation**: Use response_type "chat" with just the message field.

5. **Human-readable amounts**: When users provide amounts like "1.5" or "2.5m", use these exact values in your contract_call parameters. The system will convert them to proper blockchain units automatically.

6. **Token addresses**: Users can refer to tokens by symbol (like "CAKE" or "BUSD"). The system will resolve these to addresses using their tracked tokens.

7. **Path handling**: For swap operations, create path arrays with token addresses. For user-friendly tokens, use the token symbols and the system will resolve them.

8. **Default parameters**: You don't need to specify technical parameters like deadline or recipient address - the system will set appropriate defaults.

## Example Responses

**Chat response:**
```json
{{
  "response_type": "chat",
  "message": "Welcome to TidalDex swapping! I can help you trade tokens. What would you like to swap?"
}}
```

**View call example:**
```json
{{
  "response_type": "view_call", 
  "message": "Let me check the current exchange rate for that swap...",
  "contract_call": {{
    "contract": "router",
    "method": "getAmountsOut",
    "parameters": {{
      "amountIn": "1.5",
      "path": ["CAKE", "BUSD"]
    }},
    "explanation": "Checking how much BUSD you'll get for 1.5 CAKE"
  }}
}}
```

**Write call example:**
```json
{{
  "response_type": "write_call",
  "message": "I'll prepare that swap for you. Please review the transaction details carefully.",
  "contract_call": {{
    "contract": "router", 
    "method": "swapExactTokensForTokens",
    "parameters": {{
      "amountIn": "1.5",
      "amountOutMin": "150.0",
      "path": ["CAKE", "BUSD"]
    }},
    "explanation": "Swap 1.5 CAKE for at least 150.0 BUSD"
  }}
}}
```

{style_section}

Remember: Always be helpful, accurate, and security-conscious. Users should understand exactly what transactions they're confirming."""
        
        return system_prompt
    
    async def _call_openai(
        self, 
        messages: List[Dict[str, str]], 
        function_schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Make API call to OpenAI.
        
        Args:
            messages: Conversation messages
            function_schema: JSON schema for function calling
            
        Returns:
            OpenAI API response
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": 0.1,  # Lower temperature for more consistent responses
            "response_format": {
                "type": "json_schema",
                "json_schema": function_schema
            }
        }
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            return response.json()
    
    def _parse_openai_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse OpenAI API response.
        
        Args:
            response: Raw OpenAI API response
            
        Returns:
            Parsed response dict
        """
        try:
            # Extract the assistant's message
            content = response["choices"][0]["message"]["content"]
            
            # Parse JSON response
            parsed = json.loads(content)
            
            # Validate required fields
            if "response_type" not in parsed:
                raise ValueError("Missing response_type in LLM response")
            
            if "message" not in parsed:
                raise ValueError("Missing message in LLM response")
            
            return parsed
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from LLM response: {str(e)}")
            logger.error(f"Raw response content: {content}")
            return {
                "response_type": "chat",
                "message": "I had trouble processing that request. Could you please rephrase it?",
                "error": "JSON parse error"
            }
        except Exception as e:
            logger.error(f"Failed to parse OpenAI response: {str(e)}")
            return {
                "response_type": "chat", 
                "message": "I encountered an error processing your request.",
                "error": str(e)
            }
    
    def _load_function_schema(self) -> Dict[str, Any]:
        """Load the JSON schema for OpenAI function calling.
        
        Returns:
            JSON schema dict
        """
        try:
            schema_path = "app/schemas/app_json_schema.json"
            with open(schema_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load function schema: {str(e)}")
            # Return a basic fallback schema
            return {
                "name": "app_response",
                "description": "Response from blockchain app assistant",
                "schema": {
                    "type": "object",
                    "properties": {
                        "response_type": {
                            "type": "string",
                            "enum": ["chat", "view_call", "write_call"]
                        },
                        "message": {"type": "string"}
                    },
                    "required": ["response_type", "message"]
                }
            }

# Create singleton instance
llm_interface = LLMInterface()