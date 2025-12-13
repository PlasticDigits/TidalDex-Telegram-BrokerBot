"""
Mock LLMInterface for testing without actual OpenAI API calls.
"""
import json
from typing import Dict, List, Any, Optional
from unittest.mock import AsyncMock


class MockOpenAIResponse:
    """Mock response from OpenAI API."""
    
    def __init__(self, content: Dict[str, Any], status_code: int = 200):
        """Initialize mock response.
        
        Args:
            content: Response content dict
            status_code: HTTP status code
        """
        self.content = content
        self.status_code = status_code
    
    def json(self) -> Dict[str, Any]:
        """Return JSON response."""
        return self.content
    
    def raise_for_status(self) -> None:
        """Raise exception for error status codes."""
        if self.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError(
                f"Client error '{self.status_code}' for url 'https://api.openai.com/v1/chat/completions'",
                request=None,  # type: ignore
                response=self  # type: ignore
            )


class MockHttpxClient:
    """Mock httpx.AsyncClient for testing."""
    
    def __init__(
        self,
        response_content: Optional[Dict[str, Any]] = None,
        status_code: int = 200,
        error_type: Optional[str] = None
    ):
        """Initialize mock client.
        
        Args:
            response_content: Content to return in response
            status_code: HTTP status code to return
            error_type: Type of error to simulate (e.g., 'model_not_found', 'invalid_request')
        """
        self.response_content = response_content
        self.status_code = status_code
        self.error_type = error_type
        self.last_request_payload: Optional[Dict[str, Any]] = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        pass
    
    async def post(
        self,
        url: str,
        headers: Dict[str, str],
        json: Dict[str, Any]
    ) -> MockOpenAIResponse:
        """Mock POST request.
        
        Args:
            url: Request URL
            headers: Request headers
            json: Request JSON payload
            
        Returns:
            MockOpenAIResponse with configured content/status
        """
        self.last_request_payload = json
        
        # Simulate different error types
        if self.error_type == "model_not_found":
            return MockOpenAIResponse(
                content={
                    "error": {
                        "message": f"The model `{json.get('model')}` does not exist or you do not have access to it.",
                        "type": "invalid_request_error",
                        "param": "model",
                        "code": "model_not_found"
                    }
                },
                status_code=404
            )
        
        if self.error_type == "invalid_request":
            return MockOpenAIResponse(
                content={
                    "error": {
                        "message": "Invalid request: json_schema is not supported for this model.",
                        "type": "invalid_request_error",
                        "param": None,
                        "code": "invalid_request"
                    }
                },
                status_code=400
            )
        
        if self.error_type == "rate_limit":
            return MockOpenAIResponse(
                content={
                    "error": {
                        "message": "Rate limit exceeded. Please try again later.",
                        "type": "rate_limit_error",
                        "param": None,
                        "code": "rate_limit_exceeded"
                    }
                },
                status_code=429
            )
        
        if self.error_type == "invalid_api_key":
            return MockOpenAIResponse(
                content={
                    "error": {
                        "message": "Incorrect API key provided. You can find your API key at https://platform.openai.com/account/api-keys.",
                        "type": "invalid_request_error",
                        "param": None,
                        "code": "invalid_api_key"
                    }
                },
                status_code=401
            )
        
        if self.error_type == "connection_error":
            import httpx
            raise httpx.ConnectError("Failed to establish connection")
        
        if self.error_type == "timeout":
            import httpx
            raise httpx.TimeoutException("Request timed out")
        
        # Default successful response
        if self.response_content is None:
            self.response_content = {
                "choices": [{
                    "message": {
                        "content": json.dumps({
                            "response_type": "chat",
                            "message": "Hello! How can I help you today?"
                        })
                    }
                }]
            }
        
        return MockOpenAIResponse(
            content=self.response_content,
            status_code=self.status_code
        )


def create_mock_openai_response(
    response_type: str = "chat",
    message: str = "Hello!",
    contract_call: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Create a mock OpenAI API response structure.
    
    Args:
        response_type: Type of response (chat, view_call, write_call)
        message: Message to include
        contract_call: Optional contract call details
        
    Returns:
        Dict mimicking OpenAI API response structure
    """
    content = {
        "response_type": response_type,
        "message": message
    }
    if contract_call:
        content["contract_call"] = contract_call
    
    return {
        "choices": [{
            "message": {
                "content": json.dumps(content)
            }
        }]
    }


def create_mock_httpx_client(
    response_type: str = "chat",
    message: str = "Hello!",
    contract_call: Optional[Dict[str, Any]] = None,
    error_type: Optional[str] = None,
    status_code: int = 200
) -> MockHttpxClient:
    """Factory function to create a MockHttpxClient with preconfigured response.
    
    Args:
        response_type: Type of response (chat, view_call, write_call)
        message: Message to include
        contract_call: Optional contract call details
        error_type: Type of error to simulate
        status_code: HTTP status code
        
    Returns:
        Configured MockHttpxClient
    """
    if error_type:
        return MockHttpxClient(error_type=error_type)
    
    response_content = create_mock_openai_response(
        response_type=response_type,
        message=message,
        contract_call=contract_call
    )
    
    return MockHttpxClient(
        response_content=response_content,
        status_code=status_code
    )





