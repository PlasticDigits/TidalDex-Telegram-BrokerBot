"""
Tests for default parameter handling in transaction_manager.

This test module covers the fix for the issue where required parameters with
default values (like "to" and "deadline") were not being applied when missing
from the LLM's response, causing KeyError exceptions.

Issue: When a user asks "Swap 1 CL8Y for CZB", the LLM returns parameters
without the "to" parameter. The system should apply the default value
"user_wallet_address" and resolve it to the actual wallet address.
"""
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, Optional

from tests.mocks.mock_web3 import create_mock_web3

# Test token data - extend with CZB for this test
TEST_TOKENS = {
    "0x1234567890123456789012345678901234567890": {
        "symbol": "CL8Y",
        "name": "CeramicLiberty.com",
        "decimals": 18
    },
    "0xABCDEF1234567890ABCDEF1234567890ABCDEF12": {
        "symbol": "CZB",
        "name": "CZBlue",
        "decimals": 18
    },
}

# Test wallet address
TEST_WALLET_ADDRESS = "0x3fC4D8a13207A2cbcb09758eaa8c22C62857DfAF"


class TestDefaultParameterHandling:
    """Test cases for default parameter handling."""
    
    @pytest.fixture
    def mock_web3(self) -> MagicMock:
        """Create a mock Web3 instance."""
        return create_mock_web3()
    
    @pytest.fixture
    def mock_find_token(self) -> AsyncMock:
        """Create a mock find_token function."""
        async def _find_token(
            symbol: Optional[str] = None, 
            address: Optional[str] = None
        ) -> Optional[Dict[str, Any]]:
            if symbol:
                symbol_upper = symbol.upper()
                for addr, details in TEST_TOKENS.items():
                    if details["symbol"].upper() == symbol_upper:
                        return {
                            "address": addr,
                            "symbol": details["symbol"],
                            "name": details["name"],
                            "decimals": details["decimals"]
                        }
            return None
        
        return AsyncMock(side_effect=_find_token)
    
    @pytest.fixture
    def mock_token_manager(self) -> MagicMock:
        """Create a mock token_manager."""
        token_manager = MagicMock()
        token_manager.default_tokens = TEST_TOKENS
        
        async def get_token_info(token_address: str) -> Optional[Dict[str, Any]]:
            normalized = token_address.lower()
            for addr, details in TEST_TOKENS.items():
                if addr.lower() == normalized:
                    return {
                        "token_address": token_address,
                        "symbol": details["symbol"],
                        "name": details["name"],
                        "decimals": details["decimals"],
                        "chain_id": 56
                    }
            return None
        
        async def parse_token_list() -> Dict[str, Dict[str, Any]]:
            return TEST_TOKENS
        
        token_manager.get_token_info = AsyncMock(side_effect=get_token_info)
        token_manager._parse_default_token_list = AsyncMock(side_effect=parse_token_list)
        
        return token_manager
    
    @pytest.fixture
    def transaction_manager(self, mock_web3: MagicMock) -> Any:
        """Create a TransactionManager with mocked dependencies."""
        from services.transaction.transaction_manager import TransactionManager
        
        manager = TransactionManager()
        manager.web3 = mock_web3
        return manager
    
    @pytest.fixture
    def swap_app_config(self) -> Dict[str, Any]:
        """Create a mock swap app configuration."""
        return {
            "name": "swap",
            "description": "TidalDex token swapping interface",
            "contracts": {
                "router": {
                    "address_env_var": "DEX_ROUTER_ADDRESS",
                    "abi_file": "abi/TidalDexRouter.json"
                }
            },
            "available_methods": {
                "write": [
                    {
                        "name": "swapExactTokensForTokens",
                        "description": "Swap exact amount of tokens for tokens",
                        "inputs": ["amountIn", "amountOutMin", "path", "to", "deadline"],
                        "contract": "router",
                        "requires_token_approval": True,
                        "token_amount_pairs": [
                            {
                                "token_param": "path[0]",
                                "amount_param": "amountIn",
                                "direction": "input"
                            },
                            {
                                "token_param": "path[-1]",
                                "amount_param": "amountOutMin",
                                "direction": "output"
                            }
                        ]
                    }
                ]
            },
            "parameter_processing": {
                "amountIn": {
                    "type": "token_amount",
                    "convert_from_human": True,
                    "get_decimals_from": "path[0]"
                },
                "amountOutMin": {
                    "type": "token_amount",
                    "convert_from_human": True,
                    "get_decimals_from": "path[-1]"
                },
                "to": {
                    "type": "address",
                    "default": "user_wallet_address"
                },
                "deadline": {
                    "type": "timestamp",
                    "default": "current_time + 5_minutes"
                }
            }
        }
    
    @pytest.mark.asyncio
    async def test_process_parameters_applies_default_to(
        self,
        transaction_manager: Any,
        mock_find_token: AsyncMock,
        mock_token_manager: MagicMock,
        swap_app_config: Dict[str, Any]
    ) -> None:
        """Test that process_parameters applies default 'to' parameter when missing."""
        method_config = {
            "name": "swapExactTokensForTokens",
            "inputs": ["amountIn", "amountOutMin", "path", "to", "deadline"]
        }
        
        # Raw params missing "to" and "deadline" - simulating LLM response
        raw_params = {
            "amountIn": "1",
            "amountOutMin": "0.8",
            "path": ["CL8Y", "CZB"]
        }
        
        with patch('utils.token.find_token', mock_find_token), \
             patch('services.tokens.token_manager', mock_token_manager):
            
            processed = await transaction_manager.process_parameters(
                method_config, raw_params, swap_app_config
            )
            
            # Verify "to" was applied with default value
            assert "to" in processed
            assert processed["to"] == "user_wallet_address"
            
            # Verify "deadline" was applied with timestamp
            assert "deadline" in processed
            assert isinstance(processed["deadline"], int)
            assert processed["deadline"] > time.time()
            assert processed["deadline"] <= time.time() + 310  # Within 5 minutes + small buffer
    
    @pytest.mark.asyncio
    async def test_process_parameters_applies_default_deadline(
        self,
        transaction_manager: Any,
        mock_find_token: AsyncMock,
        mock_token_manager: MagicMock,
        swap_app_config: Dict[str, Any]
    ) -> None:
        """Test that process_parameters applies default 'deadline' parameter when missing."""
        method_config = {
            "name": "swapExactTokensForTokens",
            "inputs": ["amountIn", "amountOutMin", "path", "to", "deadline"]
        }
        
        raw_params = {
            "amountIn": "1",
            "amountOutMin": "0.8",
            "path": ["CL8Y", "CZB"],
            "to": "0x1234567890123456789012345678901234567890"  # Explicit to
        }
        
        with patch('utils.token.find_token', mock_find_token), \
             patch('services.tokens.token_manager', mock_token_manager):
            
            processed = await transaction_manager.process_parameters(
                method_config, raw_params, swap_app_config
            )
            
            # Verify "deadline" was applied
            assert "deadline" in processed
            assert isinstance(processed["deadline"], int)
            current_time = int(time.time())
            assert processed["deadline"] >= current_time + 295  # At least 4m55s
            assert processed["deadline"] <= current_time + 305  # At most 5m5s
    
    @pytest.mark.asyncio
    async def test_process_parameters_preserves_explicit_values(
        self,
        transaction_manager: Any,
        mock_find_token: AsyncMock,
        mock_token_manager: MagicMock,
        swap_app_config: Dict[str, Any]
    ) -> None:
        """Test that explicit parameter values are preserved and not overridden by defaults."""
        method_config = {
            "name": "swapExactTokensForTokens",
            "inputs": ["amountIn", "amountOutMin", "path", "to", "deadline"]
        }
        
        explicit_to = "0x9999999999999999999999999999999999999999"
        explicit_deadline = int(time.time()) + 600  # 10 minutes
        
        raw_params = {
            "amountIn": "1",
            "amountOutMin": "0.8",
            "path": ["CL8Y", "CZB"],
            "to": explicit_to,
            "deadline": explicit_deadline
        }
        
        with patch('utils.token.find_token', mock_find_token), \
             patch('services.tokens.token_manager', mock_token_manager):
            
            processed = await transaction_manager.process_parameters(
                method_config, raw_params, swap_app_config
            )
            
            # Verify explicit values are preserved
            assert processed["to"] == explicit_to
            assert processed["deadline"] == explicit_deadline
    
    @pytest.mark.asyncio
    async def test_prepare_transaction_preview_resolves_user_wallet_address(
        self,
        transaction_manager: Any,
        mock_find_token: AsyncMock,
        mock_token_manager: MagicMock,
        swap_app_config: Dict[str, Any]
    ) -> None:
        """Test that prepare_transaction_preview resolves 'user_wallet_address' to actual address."""
        method_config = {
            "name": "swapExactTokensForTokens",
            "inputs": ["amountIn", "amountOutMin", "path", "to", "deadline"],
            "contract": "router"
        }
        
        raw_params = {
            "amountIn": "1",
            "amountOutMin": "0.8",
            "path": ["CL8Y", "CZB"]
        }
        
        wallet_address = TEST_WALLET_ADDRESS
        
        # Mock transaction formatter
        mock_formatter = MagicMock()
        mock_formatter.validate_token_amount_pairs = AsyncMock()
        mock_formatter.format_transaction_summary = AsyncMock(return_value="Swap 1 CL8Y for at least 0.8 CZB")
        transaction_manager.formatter = mock_formatter
        
        # Mock number converter
        mock_number_converter = MagicMock()
        mock_number_converter.to_raw_amount = MagicMock(return_value=1000000000000000000)  # 1 token with 18 decimals
        mock_number_converter.format_gas_estimate = MagicMock(return_value={"total_cost_bnb": "0.001"})
        transaction_manager.number_converter = mock_number_converter
        
        # Mock gas estimation
        transaction_manager.estimate_gas = AsyncMock(return_value={
            "gas_estimate": 250000,
            "gas_price": 5000000000,
            "gas_wei": 1250000000000000,
            "gas_bnb": 0.00125
        })
        
        # Mock ABI loading - mock the file reading directly
        import json
        mock_abi = [{"type": "function", "name": "swapExactTokensForTokens", "inputs": []}]
        
        # Patch both the file open and json.load to return our mock ABI
        mock_file_content = MagicMock()
        mock_file_content.__enter__.return_value.read.return_value = json.dumps(mock_abi)
        mock_file_content.__exit__.return_value = None
        
        with patch('builtins.open', return_value=mock_file_content), \
             patch('os.getenv', return_value="0x10ED43C718714eb63d5aA57B78B54704E256024E"), \
             patch('utils.token.find_token', mock_find_token), \
             patch('services.tokens.token_manager', mock_token_manager):
            
            preview = await transaction_manager.prepare_transaction_preview(
                method_config, raw_params, swap_app_config, wallet_address
            )
            
            # Verify preview was created successfully
            assert preview is not None
            assert "processed_params" in preview
            
            # Verify "to" was resolved to wallet address
            processed_params = preview["processed_params"]
            assert "to" in processed_params
            assert processed_params["to"] == wallet_address
            assert processed_params["to"] != "user_wallet_address"
    
    @pytest.mark.asyncio
    async def test_swap_without_to_parameter_scenario(
        self,
        transaction_manager: Any,
        mock_find_token: AsyncMock,
        mock_token_manager: MagicMock,
        swap_app_config: Dict[str, Any]
    ) -> None:
        """
        Test the exact scenario that caused the original error:
        User: "Swap 1 CL8Y for CZB"
        LLM returns: parameters without "to"
        
        Before fix: KeyError: 'to'
        After fix: "to" should be set to user_wallet_address and resolved
        """
        method_config = {
            "name": "swapExactTokensForTokens",
            "inputs": ["amountIn", "amountOutMin", "path", "to", "deadline"],
            "contract": "router"
        }
        
        # Simulate LLM response - missing "to" parameter
        raw_params = {
            "amountIn": "1",
            "amountOutMin": "0.8",
            "path": ["CL8Y", "CZB"]
        }
        
        with patch('utils.token.find_token', mock_find_token), \
             patch('services.tokens.token_manager', mock_token_manager):
            
            # Process parameters - should not raise KeyError
            processed = await transaction_manager.process_parameters(
                method_config, raw_params, swap_app_config
            )
            
            # Verify all required parameters are present
            for param in method_config["inputs"]:
                assert param in processed, f"Required parameter '{param}' missing from processed params"
            
            # Verify "to" has default value
            assert processed["to"] == "user_wallet_address"
            
            # Verify path was resolved
            assert len(processed["path"]) == 2
            assert transaction_manager.web3.is_address(processed["path"][0])
            assert transaction_manager.web3.is_address(processed["path"][1])
    
    @pytest.mark.asyncio
    async def test_multiple_default_parameters(
        self,
        transaction_manager: Any,
        mock_find_token: AsyncMock,
        mock_token_manager: MagicMock,
        swap_app_config: Dict[str, Any]
    ) -> None:
        """Test that multiple default parameters can be applied simultaneously."""
        method_config = {
            "name": "swapExactTokensForTokens",
            "inputs": ["amountIn", "amountOutMin", "path", "to", "deadline"]
        }
        
        # Only provide required non-default params
        raw_params = {
            "amountIn": "1",
            "amountOutMin": "0.8",
            "path": ["CL8Y", "CZB"]
        }
        
        with patch('utils.token.find_token', mock_find_token), \
             patch('services.tokens.token_manager', mock_token_manager):
            
            processed = await transaction_manager.process_parameters(
                method_config, raw_params, swap_app_config
            )
            
            # Verify both defaults were applied
            assert "to" in processed
            assert processed["to"] == "user_wallet_address"
            
            assert "deadline" in processed
            assert isinstance(processed["deadline"], int)
            assert processed["deadline"] > time.time()
    
    @pytest.mark.asyncio
    async def test_no_default_for_required_param_raises_error(
        self,
        transaction_manager: Any,
        mock_find_token: AsyncMock,
        mock_token_manager: MagicMock,
        swap_app_config: Dict[str, Any]
    ) -> None:
        """Test that missing required parameter without default raises error during args building."""
        method_config = {
            "name": "swapExactTokensForTokens",
            "inputs": ["amountIn", "amountOutMin", "path", "to", "deadline", "requiredParam"]
        }
        
        # Missing requiredParam which has no default
        raw_params = {
            "amountIn": "1",
            "amountOutMin": "0.8",
            "path": ["CL8Y", "CZB"]
        }
        
        with patch('utils.token.find_token', mock_find_token), \
             patch('services.tokens.token_manager', mock_token_manager):
            
            processed = await transaction_manager.process_parameters(
                method_config, raw_params, swap_app_config
            )
            
            # Process should succeed, but requiredParam won't be in processed
            # This will cause an error when building args, which is expected
            assert "requiredParam" not in processed
            assert "to" in processed  # Default was applied
            assert "deadline" in processed  # Default was applied

