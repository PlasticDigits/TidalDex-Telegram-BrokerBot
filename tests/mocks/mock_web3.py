"""
Mock Web3 for testing without actual blockchain connections.
"""
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock


class MockWeb3:
    """Mock Web3 instance for testing."""
    
    # Known test addresses for validation
    VALID_ADDRESSES = {
        "0x1234567890123456789012345678901234567890",
        "0xABCDEF1234567890ABCDEF1234567890ABCDEF12",
        "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82",
        "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56",
        "0x55d398326f99059fF775485246999027B3197955",
        "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",  # WBNB
    }
    
    def __init__(self) -> None:
        """Initialize the mock Web3 instance."""
        self.eth = MagicMock()
    
    def is_address(self, value: str) -> bool:
        """Check if a value looks like an Ethereum address.
        
        Args:
            value: Value to check
            
        Returns:
            bool: True if it looks like an address (starts with 0x and is 42 chars)
        """
        if not isinstance(value, str):
            return False
        
        # Check format: 0x followed by 40 hex characters
        if not value.startswith("0x"):
            return False
        
        if len(value) != 42:
            return False
        
        try:
            # Check that the rest is hex
            int(value[2:], 16)
            return True
        except ValueError:
            return False
    
    def to_checksum_address(self, address: str) -> str:
        """Convert an address to checksum format.
        
        For testing purposes, this just returns the address with proper casing.
        
        Args:
            address: Address to convert
            
        Returns:
            str: Checksummed address
        """
        if not self.is_address(address):
            raise ValueError(f"Invalid address: {address}")
        
        # Simple mock: return with standard checksum-like formatting
        # Real Web3 uses EIP-55 checksumming
        return "0x" + address[2:10].upper() + address[10:].lower()


def create_mock_web3() -> MockWeb3:
    """Factory function to create a MockWeb3 instance.
    
    Returns:
        MockWeb3 instance
    """
    return MockWeb3()

