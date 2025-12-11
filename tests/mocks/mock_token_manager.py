"""
Mock TokenManager for testing without database or network dependencies.
"""
from typing import Dict, List, Any, Optional
from unittest.mock import MagicMock, AsyncMock


class MockTokenDetails:
    """Mock token details structure."""
    
    def __init__(self, symbol: str, name: str, decimals: int):
        self.symbol = symbol
        self.name = name
        self.decimals = decimals
    
    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)
    
    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


class MockTokenManager:
    """Mock TokenManager for testing token resolution without real database/network."""
    
    def __init__(self, default_tokens: Optional[Dict[str, Dict[str, Any]]] = None):
        """Initialize with optional predefined tokens.
        
        Args:
            default_tokens: Dict mapping addresses to token details
        """
        # Default test tokens
        self.default_tokens: Dict[str, Dict[str, Any]] = default_tokens or {
            "0x1234567890123456789012345678901234567890": {
                "symbol": "CL8Y",
                "name": "Clay Token",
                "decimals": 18
            },
            "0xABCDEF1234567890ABCDEF1234567890ABCDEF12": {
                "symbol": "CZUSD",
                "name": "CZ USD",
                "decimals": 18
            },
            "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82": {
                "symbol": "CAKE",
                "name": "PancakeSwap Token",
                "decimals": 18
            },
            "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56": {
                "symbol": "BUSD",
                "name": "Binance USD",
                "decimals": 18
            },
            "0x55d398326f99059fF775485246999027B3197955": {
                "symbol": "USDT",
                "name": "Tether USD",
                "decimals": 18
            },
        }
    
    async def get_token_info(self, token_address: str) -> Optional[Dict[str, Any]]:
        """Get token info by address.
        
        Args:
            token_address: Token contract address
            
        Returns:
            Token info dict or None if not found
        """
        # Normalize address for lookup
        normalized = token_address.lower()
        for addr, details in self.default_tokens.items():
            if addr.lower() == normalized:
                return {
                    "token_address": token_address,
                    "symbol": details["symbol"],
                    "name": details["name"],
                    "decimals": details["decimals"],
                    "chain_id": 56
                }
        return None
    
    async def _parse_default_token_list(self) -> Dict[str, Dict[str, Any]]:
        """Mock parsing of default token list.
        
        Returns the pre-configured default_tokens.
        """
        return self.default_tokens
    
    def add_token(self, address: str, symbol: str, name: str, decimals: int = 18) -> None:
        """Add a token to the mock token list for testing.
        
        Args:
            address: Token contract address
            symbol: Token symbol
            name: Token name  
            decimals: Token decimals (default 18)
        """
        self.default_tokens[address] = {
            "symbol": symbol,
            "name": name,
            "decimals": decimals
        }
    
    def clear_tokens(self) -> None:
        """Clear all tokens from the mock."""
        self.default_tokens = {}


def create_mock_token_manager(tokens: Optional[Dict[str, Dict[str, Any]]] = None) -> MockTokenManager:
    """Factory function to create a MockTokenManager.
    
    Args:
        tokens: Optional dict of tokens to initialize with
        
    Returns:
        MockTokenManager instance
    """
    return MockTokenManager(tokens)

