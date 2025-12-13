"""
Unit tests for balance formatting helper function.

Tests the _format_token_balances helper function that formats token balances
for display, including handling of duplicate symbols.
"""
import pytest
from typing import Dict, Any, List


class TestFormatTokenBalances:
    """Test the _format_token_balances helper function."""
    
    @pytest.fixture
    def mock_format_token_balance(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Mock the format_token_balance function to return predictable values."""
        def mock_format(raw_balance: int, decimals: int) -> str:
            # Simple mock that just converts to string
            return str(raw_balance / (10 ** decimals))[:10]
        
        from utils import token_utils
        monkeypatch.setattr(token_utils, 'format_token_balance', mock_format)
    
    def test_empty_balances_returns_empty_list(self, mock_format_token_balance: None) -> None:
        """Test that empty token_balances returns empty list."""
        from commands.balance import _format_token_balances
        
        result = _format_token_balances({})
        assert result == []
    
    def test_single_token_no_address_shown(self, mock_format_token_balance: None) -> None:
        """Test that a single token doesn't show address abbreviation."""
        from commands.balance import _format_token_balances
        
        token_balances = {
            "0x1234567890123456789012345678901234567890": {
                "symbol": "CAKE",
                "name": "PancakeSwap Token",
                "raw_balance": 1000000000000000000,
                "decimals": 18
            }
        }
        
        result = _format_token_balances(token_balances)
        
        assert len(result) == 1
        assert "CAKE" in result[0]
        assert "PancakeSwap Token" in result[0]
        # No address should be shown for single token
        assert "[" not in result[0]
    
    def test_duplicate_symbols_show_addresses(self, mock_format_token_balance: None) -> None:
        """Test that duplicate symbols show abbreviated addresses."""
        from commands.balance import _format_token_balances
        
        token_balances = {
            "0x1234567890123456789012345678901234567890": {
                "symbol": "CL8Y",
                "name": "CeramicLiberty.com",
                "raw_balance": 13552103200785384,
                "decimals": 18
            },
            "0xABCDEF1234567890ABCDEF1234567890ABCDEF12": {
                "symbol": "CL8Y",
                "name": "CeramicLiberty.com",
                "raw_balance": 12689072202450769,
                "decimals": 18
            }
        }
        
        result = _format_token_balances(token_balances)
        
        assert len(result) == 2
        # Both should show abbreviated addresses
        for line in result:
            assert "CL8Y" in line
            assert "[" in line and "]" in line  # Address abbreviation present
            assert "..." in line  # Abbreviated address format
    
    def test_mixed_unique_and_duplicate_symbols(self, mock_format_token_balance: None) -> None:
        """Test that only duplicate symbols show addresses."""
        from commands.balance import _format_token_balances
        
        token_balances = {
            "0x1234567890123456789012345678901234567890": {
                "symbol": "CL8Y",
                "name": "CeramicLiberty.com",
                "raw_balance": 13552103200785384,
                "decimals": 18
            },
            "0xABCDEF1234567890ABCDEF1234567890ABCDEF12": {
                "symbol": "CL8Y",
                "name": "CeramicLiberty.com (Old)",
                "raw_balance": 12689072202450769,
                "decimals": 18
            },
            "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82": {
                "symbol": "CAKE",
                "name": "PancakeSwap Token",
                "raw_balance": 1000000000000000000,
                "decimals": 18
            }
        }
        
        result = _format_token_balances(token_balances)
        
        assert len(result) == 3
        
        # Find CL8Y and CAKE lines
        cl8y_lines = [line for line in result if "CL8Y" in line]
        cake_lines = [line for line in result if "CAKE" in line]
        
        # CL8Y lines should have addresses
        assert len(cl8y_lines) == 2
        for line in cl8y_lines:
            assert "[" in line
        
        # CAKE line should not have address
        assert len(cake_lines) == 1
        assert "[" not in cake_lines[0]
    
    def test_handles_missing_name_gracefully(self, mock_format_token_balance: None) -> None:
        """Test that missing name defaults to 'Unknown'."""
        from commands.balance import _format_token_balances
        
        token_balances = {
            "0x1234567890123456789012345678901234567890": {
                "symbol": "TEST",
                # No 'name' key
                "raw_balance": 1000000000000000000,
                "decimals": 18
            }
        }
        
        result = _format_token_balances(token_balances)
        
        assert len(result) == 1
        assert "Unknown" in result[0]
    
    def test_case_insensitive_symbol_duplicate_detection(self, mock_format_token_balance: None) -> None:
        """Test that duplicate detection is case-insensitive."""
        from commands.balance import _format_token_balances
        
        token_balances = {
            "0x1234567890123456789012345678901234567890": {
                "symbol": "CL8Y",
                "name": "CeramicLiberty.com",
                "raw_balance": 13552103200785384,
                "decimals": 18
            },
            "0xABCDEF1234567890ABCDEF1234567890ABCDEF12": {
                "symbol": "cl8y",  # lowercase
                "name": "CeramicLiberty.com (Old)",
                "raw_balance": 12689072202450769,
                "decimals": 18
            }
        }
        
        result = _format_token_balances(token_balances)
        
        assert len(result) == 2
        # Both should show addresses due to case-insensitive duplicate detection
        for line in result:
            assert "[" in line


