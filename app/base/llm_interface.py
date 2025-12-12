"""
LLM interface for communicating with OpenAI to process user requests.
Handles conversation context, function calling, and response parsing.
"""
import logging
import json
import os
import re
from typing import Dict, List, Any, Optional
import httpx
from dotenv import load_dotenv
from app.base.llm_app_session import LLMAppSession
from app.base.llm_app_manager import llm_app_manager

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class LLMInterface:
    """Interface for communicating with OpenAI's language models."""
    
    def __init__(self):
        """Initialize the LLM interface."""
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        
        self.base_url = "https://api.openai.com/v1"
        # Default to gpt-5-nano (cheapest: $0.10/$0.40 per 1M tokens)
        # Requires max_completion_tokens instead of max_tokens
        self.model = os.getenv("OPENAI_MODEL", "gpt-5-nano")
        self.max_tokens = 1000
        
        # Newer models (gpt-5-*, o1-*, o3-*) use max_completion_tokens instead of max_tokens
        self._uses_new_token_param = self._check_new_model_format(self.model)
        
    def _check_new_model_format(self, model: str) -> bool:
        """Check if model uses new API parameters (max_completion_tokens vs max_tokens).
        
        Args:
            model: Model name string
            
        Returns:
            True if model uses new parameter format (gpt-5-*, o1-*, o3-*)
        """
        new_model_prefixes = ("gpt-5", "o1-", "o3-")
        return any(model.startswith(prefix) for prefix in new_model_prefixes)
    
    async def process_user_message(
        self,
        session: LLMAppSession,
        user_message: str
    ) -> Dict[str, Any]:
        """Process a user message and return the assistant's response.
        
        Args:
            session: Active LLM app session
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
            
        except httpx.HTTPStatusError as e:
            error_msg = str(e)
            logger.error(f"Failed to process user message (HTTP error): {error_msg}")
            
            # Provide more specific error messages
            if "400" in error_msg or "404" in error_msg:
                user_message = (
                    "I'm having trouble connecting to the AI service. "
                    "This might be a configuration issue. Please try again later."
                )
            elif "401" in error_msg:
                user_message = (
                    "There's an authentication issue with the AI service. "
                    "Please contact support."
                )
            elif "429" in error_msg:
                user_message = (
                    "The AI service is currently busy. "
                    "Please wait a moment and try again."
                )
            else:
                user_message = "I encountered an error processing your request. Please try again."
            
            return {
                "response_type": "chat",
                "message": user_message,
                "error": error_msg
            }
        except httpx.ConnectError as e:
            logger.error(f"Failed to connect to OpenAI API: {str(e)}")
            return {
                "response_type": "chat",
                "message": "Unable to connect to the AI service. Please check your internet connection.",
                "error": str(e)
            }
        except httpx.TimeoutException as e:
            logger.error(f"OpenAI API request timed out: {str(e)}")
            return {
                "response_type": "chat",
                "message": "The AI service is taking too long to respond. Please try again.",
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"Failed to process user message: {str(e)}")
            return {
                "response_type": "chat",
                "message": "I encountered an error processing your request. Please try again.",
                "error": str(e)
            }
    
    async def _build_system_prompt(self, session: LLMAppSession) -> str:
        """Build the system prompt for the LLM.
        
        Args:
            session: Active LLM app session
            
        Returns:
            Complete system prompt string
        """
        llm_app_config = session.llm_app_config
        context = session.context
        
        # Load style guide
        style_guide = llm_app_manager.load_llm_app_style_guide(session.llm_app_name)
        style_section = f"\n\n## Style Guide\n{style_guide}" if style_guide else ""
        
        # Format available methods
        view_methods = []
        write_methods = []
        
        for method in llm_app_config["available_methods"].get("view", []):
            view_methods.append(f"- **{method['name']}**: {method['description']}")
        
        for method in llm_app_config["available_methods"].get("write", []):
            write_methods.append(f"- **{method['name']}**: {method['description']}")
        
        # Format user's token balances
        balance_info = ""
        if context.get("token_balances"):
            balance_lines = []
            for token in context["token_balances"]:
                balance_lines.append(f"- {token['balance']} {token['symbol']} ({token['name']})")
            balance_info = f"\n\n**Your Token Balances:**\n" + "\n".join(balance_lines)
        
        system_prompt = f"""You are an expert assistant for the {llm_app_config['name']} LLM app on TidalDex.

## LLM App Information
**Name:** {llm_app_config['name']}
**Description:** {llm_app_config['description']}

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
        
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": function_schema
            }
        }
        
        # Use appropriate token parameter based on model type
        if self._uses_new_token_param:
            payload["max_completion_tokens"] = self.max_tokens
            # Note: temperature may not be supported for all reasoning models
        else:
            payload["max_tokens"] = self.max_tokens
            payload["temperature"] = 0.1  # Lower temperature for more consistent responses
        
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload
            )
            
            # Check for errors before raising
            if response.status_code >= 400:
                error_detail = self._parse_api_error(response)
                logger.error(f"OpenAI API error ({response.status_code}): {error_detail}")
                response.raise_for_status()
            
            return response.json()

    def _extract_json_text(self, raw_text: str) -> str:
        """Best-effort extraction of a JSON object from model output text.

        The OpenAI API is asked to return strict JSON, but in practice models may:
        - Wrap JSON in Markdown fences (```json ... ```)
        - Add leading/trailing commentary
        This helper tries to recover a parseable JSON object string.
        """
        text = raw_text.strip()
        if not text:
            return text

        # Prefer extracting from fenced blocks first.
        fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, flags=re.IGNORECASE)
        if fenced:
            return fenced.group(1).strip()

        # Fall back to slicing the outer-most JSON object.
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1].strip()

        return text

    def _coerce_openai_content_to_text(self, content: Any) -> Optional[str]:
        """Convert OpenAI 'message.content' into a plain text string when possible."""
        if content is None:
            return None
        if isinstance(content, str):
            return content

        # Some clients / versions may represent message content as a list of parts.
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if isinstance(item, dict):
                    # Common shapes: {"type":"text","text":"..."}, {"type":"output_text","text":"..."}
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
                        continue
                    # Fallback keys seen in some SDKs
                    alt = item.get("content")
                    if isinstance(alt, str):
                        parts.append(alt)
                        continue
            if parts:
                return "".join(parts)
            return None

        # Unknown/unsupported type
        return None
    
    def _parse_openai_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse OpenAI API response.
        
        Args:
            response: Raw OpenAI API response
            
        Returns:
            Parsed response dict
        """
        try:
            # Extract the first choice/message (best-effort; be defensive about shape)
            choices = response.get("choices")
            if not isinstance(choices, list) or not choices:
                raise ValueError("OpenAI response missing non-empty 'choices' array")

            choice0 = choices[0] if isinstance(choices[0], dict) else {}
            finish_reason = choice0.get("finish_reason")
            message = choice0.get("message") if isinstance(choice0.get("message"), dict) else {}

            raw_content = message.get("content")
            content_text = self._coerce_openai_content_to_text(raw_content)
            refusal_text = message.get("refusal") if isinstance(message.get("refusal"), str) else None

            # Handle refusals/content filters/empty responses explicitly.
            if content_text is None or content_text.strip() == "":
                if refusal_text:
                    logger.warning(
                        "OpenAI returned a refusal (finish_reason=%s).",
                        finish_reason,
                    )
                    return {
                        "response_type": "chat",
                        "message": refusal_text,
                        "error": "refusal",
                    }

                if finish_reason == "content_filter":
                    logger.warning("OpenAI response was blocked by content_filter.")
                    return {
                        "response_type": "chat",
                        "message": (
                            "The AI service could not return a response due to content filtering. "
                            "Please try rephrasing your request."
                        ),
                        "error": "content_filter",
                    }

                logger.error(
                    "OpenAI returned empty message content (finish_reason=%s, message_keys=%s).",
                    finish_reason,
                    sorted(list(message.keys())),
                )
                return {
                    "response_type": "chat",
                    "message": (
                        "The AI service returned an empty response. Please try again. "
                        "If this keeps happening, the service may be refusing or failing upstream."
                    ),
                    "error": "empty_llm_response",
                }

            # Normalize to JSON text (strip fences / leading text if any)
            json_text = self._extract_json_text(content_text)
            
            # Parse JSON response
            parsed = json.loads(json_text)
            
            # Validate required fields
            if "response_type" not in parsed:
                raise ValueError("Missing response_type in LLM response")
            
            if "message" not in parsed:
                raise ValueError("Missing message in LLM response")
            
            # Validate contract_call is present for view_call and write_call
            response_type = parsed["response_type"]
            if response_type in ["view_call", "write_call"]:
                if "contract_call" not in parsed:
                    raise ValueError(
                        f"Missing contract_call in LLM response for {response_type}. "
                        f"contract_call is required when response_type is 'view_call' or 'write_call'."
                    )
                # Validate contract_call structure
                contract_call = parsed["contract_call"]
                required_fields = ["contract", "method", "parameters", "explanation"]
                for field in required_fields:
                    if field not in contract_call:
                        raise ValueError(f"Missing required field '{field}' in contract_call")
            
            return parsed
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from LLM response: {str(e)}")
            try:
                raw = response.get("choices", [{}])[0].get("message", {}).get("content")  # type: ignore[union-attr]
            except Exception:
                raw = None
            logger.error(f"Raw response content: {raw}")
            return {
                "response_type": "chat",
                "message": (
                    "I couldn't parse the AI response as valid JSON. "
                    "Please try rephrasing your request."
                ),
                "error": "json_parse_error",
            }
        except Exception as e:
            logger.error(f"Failed to parse OpenAI response: {str(e)}")
            return {
                "response_type": "chat", 
                "message": "I encountered an error processing your request.",
                "error": str(e)
            }
    
    def _parse_api_error(self, response: httpx.Response) -> str:
        """Parse and format OpenAI API error response.
        
        Args:
            response: httpx Response object with error
            
        Returns:
            Human-readable error message
        """
        try:
            error_json = response.json()
            if "error" in error_json:
                error = error_json["error"]
                error_type = error.get("type", "unknown")
                error_code = error.get("code", "unknown")
                error_message = error.get("message", "Unknown error")
                
                # Provide specific guidance for common errors
                if error_code == "model_not_found":
                    return (
                        f"Model '{self.model}' not found. "
                        f"Try setting OPENAI_MODEL env var to 'gpt-4o-mini' or 'gpt-3.5-turbo'. "
                        f"Original error: {error_message}"
                    )
                elif error_code == "invalid_api_key":
                    return "Invalid API key. Check your OPENAI_API_KEY environment variable."
                elif error_type == "invalid_request_error":
                    return f"Invalid request: {error_message}"
                elif error_type == "rate_limit_error":
                    return f"Rate limit exceeded. Please try again later. {error_message}"
                else:
                    return f"{error_type} ({error_code}): {error_message}"
            return str(error_json)
        except Exception:
            return f"HTTP {response.status_code}: {response.text[:200]}"

    def _load_function_schema(self) -> Dict[str, Any]:
        """Load the JSON schema for OpenAI function calling.
        
        Returns:
            JSON schema dict formatted for OpenAI API (with name, strict, and schema fields)
            OpenAI requires: name, strict, and schema at the json_schema level
        """
        try:
            # Get absolute path to schema file
            current_dir = os.path.dirname(os.path.abspath(__file__))
            app_dir = os.path.dirname(current_dir)  # Go up from app/base to app/
            schema_path = os.path.join(app_dir, "schemas", "app_json_schema.json")
            with open(schema_path, 'r') as f:
                schema_data = json.load(f)
            
            # OpenAI requires name, strict, and schema fields at the json_schema level
            # The schema file already has the correct structure, so return it as-is
            if isinstance(schema_data, dict) and "name" in schema_data and "schema" in schema_data:
                return schema_data
            
            # If only inner schema exists, wrap it with required fields
            if isinstance(schema_data, dict) and "schema" in schema_data:
                return {
                    "name": schema_data.get("name", "blockchain_llm_app_response"),
                    "description": schema_data.get("description", "Response schema for blockchain LLM app assistant"),
                    "strict": schema_data.get("strict", True),
                    "schema": schema_data["schema"]
                }
            
            # If it's just the schema object, wrap it
            return {
                "name": "blockchain_llm_app_response",
                "description": "Response schema for blockchain LLM app assistant interactions",
                "strict": True,
                "schema": schema_data
            }
        except Exception as e:
            logger.error(f"Failed to load function schema: {str(e)}")
            # Return a basic fallback schema with proper OpenAI wrapper format
            return {
                "name": "blockchain_llm_app_response",
                "description": "Response schema for blockchain LLM app assistant interactions (fallback)",
                "strict": False,
                "schema": {
                    "type": "object",
                    "properties": {
                        "response_type": {
                            "type": "string",
                            "enum": ["chat", "view_call", "write_call"]
                        },
                        "message": {"type": "string"}
                    },
                    "required": ["response_type", "message"],
                    "additionalProperties": False
                }
            }

# Singleton instance (lazy initialization)
_llm_interface_instance: Optional[LLMInterface] = None

def get_llm_interface() -> LLMInterface:
    """Get or create the singleton LLMInterface instance.
    
    Returns:
        LLMInterface instance
        
    Raises:
        ValueError: If OPENAI_API_KEY is not set
    """
    global _llm_interface_instance
    if _llm_interface_instance is None:
        _llm_interface_instance = LLMInterface()
    return _llm_interface_instance

# Backward compatibility: create instance at module level if API key is available
# This allows existing code to use llm_interface directly, but won't fail if key is missing
try:
    llm_interface = LLMInterface()
except ValueError:
    # API key not set - will be created lazily when get_llm_interface() is called
    llm_interface = None  # type: ignore