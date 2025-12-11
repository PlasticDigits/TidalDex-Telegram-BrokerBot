"""
Tests for token symbol resolution in transaction_manager.

This test module covers the fix for the issue where token symbols like "CL8Y" 
were being passed directly to contract calls instead of being resolved to addresses.

Issue: When a user asks "What's the price of CL8Y in CZUSD?", the LLM returns
a path like ["CL8Y", "CZUSD"]. The system needs to resolve these symbols to
actual token addresses before calling contract methods like getAmountsOut.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List, Optional


# Test token data
TEST_TOKENS = {
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
}


def create_mock_web3() -> MagicMock:
    """Create a mock Web3 instance with is_address and to_checksum_address."""
    mock = MagicMock()
    
    def is_address(value: str) -> bool:
        if not isinstance(value, str):
            return False
        if not value.startswith("0x"):
            return False
        if len(value) != 42:
            return False
        try:
            int(value[2:], 16)
            return True
        except ValueError:
            return False
    
    def to_checksum_address(address: str) -> str:
        if not is_address(address):
            raise ValueError(f"Invalid address: {address}")
        return address  # Return as-is for tests
    
    mock.is_address = is_address
    mock.to_checksum_address = to_checksum_address
    
    return mock


class TestTokenSymbolResolution:
    """Test cases for token symbol to address resolution."""
    
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
        # Import inside fixture to avoid module-level import issues
        from services.transaction.transaction_manager import TransactionManager
        
        # Create manager and replace web3 with mock
        manager = TransactionManager()
        manager.web3 = mock_web3
        return manager
    
    @pytest.mark.asyncio
    async def test_resolve_token_symbol_cl8y(
        self, 
        transaction_manager: Any, 
        mock_find_token: AsyncMock,
        mock_token_manager: MagicMock
    ) -> None:
        """Test resolving CL8Y token symbol to address."""
        # Patch where the imports are used in transaction_manager module
        with patch('services.transaction.transaction_manager.find_token', mock_find_token, create=True), \
             patch('services.transaction.transaction_manager.token_manager', mock_token_manager, create=True):
            # Also patch at the utils.token level since that's where it's imported from
            with patch('utils.token.find_token', mock_find_token):
                result = await transaction_manager._resolve_token_symbol("CL8Y")
            
                assert result is not None
                assert result == "0x1234567890123456789012345678901234567890"
    
    @pytest.mark.asyncio
    async def test_resolve_token_symbol_czusd(
        self, 
        transaction_manager: Any, 
        mock_find_token: AsyncMock,
        mock_token_manager: MagicMock
    ) -> None:
        """Test resolving CZUSD token symbol to address."""
        with patch('utils.token.find_token', mock_find_token):
            result = await transaction_manager._resolve_token_symbol("CZUSD")
            
            assert result is not None
            assert result == "0xABCDEF1234567890ABCDEF1234567890ABCDEF12"
    
    @pytest.mark.asyncio
    async def test_resolve_token_symbol_case_insensitive(
        self, 
        transaction_manager: Any, 
        mock_find_token: AsyncMock,
        mock_token_manager: MagicMock
    ) -> None:
        """Test that symbol resolution is case-insensitive."""
        with patch('utils.token.find_token', mock_find_token):
            # Test lowercase
            result_lower = await transaction_manager._resolve_token_symbol("cl8y")
            assert result_lower is not None
            
            # Test mixed case
            result_mixed = await transaction_manager._resolve_token_symbol("Cl8Y")
            assert result_mixed is not None
    
    @pytest.mark.asyncio
    async def test_resolve_unknown_symbol_returns_none(
        self, 
        transaction_manager: Any, 
        mock_find_token: AsyncMock,
        mock_token_manager: MagicMock
    ) -> None:
        """Test that unknown symbols return None."""
        with patch('utils.token.find_token', mock_find_token), \
             patch('services.tokens.token_manager', mock_token_manager):
            
            result = await transaction_manager._resolve_token_symbol("UNKNOWN_TOKEN_XYZ")
            
            assert result is None
    
    @pytest.mark.asyncio
    async def test_resolve_symbols_in_path_all_symbols(
        self, 
        transaction_manager: Any, 
        mock_find_token: AsyncMock,
        mock_token_manager: MagicMock
    ) -> None:
        """Test resolving a path with all symbols like ["CL8Y", "CZUSD"]."""
        with patch('utils.token.find_token', mock_find_token), \
             patch('services.tokens.token_manager', mock_token_manager):
            
            path = ["CL8Y", "CZUSD"]
            resolved = await transaction_manager._resolve_token_symbols_in_path(path)
            
            assert len(resolved) == 2
            assert resolved[0] == "0x1234567890123456789012345678901234567890"
            assert resolved[1] == "0xABCDEF1234567890ABCDEF1234567890ABCDEF12"
    
    @pytest.mark.asyncio
    async def test_resolve_symbols_in_path_mixed(
        self, 
        transaction_manager: Any, 
        mock_find_token: AsyncMock,
        mock_token_manager: MagicMock
    ) -> None:
        """Test resolving a path with mixed addresses and symbols."""
        with patch('utils.token.find_token', mock_find_token), \
             patch('services.tokens.token_manager', mock_token_manager):
            
            # Mix of address and symbol
            path = ["0x1234567890123456789012345678901234567890", "CZUSD"]
            resolved = await transaction_manager._resolve_token_symbols_in_path(path)
            
            assert len(resolved) == 2
            # First should be preserved as address
            assert resolved[0] == "0x1234567890123456789012345678901234567890"
            # Second should be resolved from symbol
            assert resolved[1] == "0xABCDEF1234567890ABCDEF1234567890ABCDEF12"
    
    @pytest.mark.asyncio
    async def test_resolve_symbols_in_path_with_bnb(
        self, 
        transaction_manager: Any, 
        mock_find_token: AsyncMock,
        mock_token_manager: MagicMock
    ) -> None:
        """Test that BNB is preserved in the path without resolution."""
        with patch('utils.token.find_token', mock_find_token), \
             patch('services.tokens.token_manager', mock_token_manager):
            
            path = ["BNB", "CZUSD"]
            resolved = await transaction_manager._resolve_token_symbols_in_path(path)
            
            assert len(resolved) == 2
            assert resolved[0] == "BNB"  # BNB should be preserved
            assert resolved[1] == "0xABCDEF1234567890ABCDEF1234567890ABCDEF12"
    
    @pytest.mark.asyncio
    async def test_resolve_symbols_in_path_unknown_raises_error(
        self, 
        transaction_manager: Any, 
        mock_find_token: AsyncMock,
        mock_token_manager: MagicMock
    ) -> None:
        """Test that unknown symbols raise ValueError with helpful message."""
        with patch('utils.token.find_token', mock_find_token), \
             patch('services.tokens.token_manager', mock_token_manager):
            
            path = ["UNKNOWN_TOKEN", "CZUSD"]
            
            with pytest.raises(ValueError) as exc_info:
                await transaction_manager._resolve_token_symbols_in_path(path)
            
            assert "UNKNOWN_TOKEN" in str(exc_info.value)
            assert "Could not resolve" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_resolve_symbols_in_path_all_addresses(
        self, 
        transaction_manager: Any
    ) -> None:
        """Test that paths with all valid addresses pass through unchanged."""
        path = [
            "0x1234567890123456789012345678901234567890",
            "0xABCDEF1234567890ABCDEF1234567890ABCDEF12"
        ]
        resolved = await transaction_manager._resolve_token_symbols_in_path(path)
        
        assert len(resolved) == 2
        assert resolved[0] == "0x1234567890123456789012345678901234567890"
        assert resolved[1] == "0xABCDEF1234567890ABCDEF1234567890ABCDEF12"


class TestProcessParametersWithSymbolResolution:
    """Test process_parameters with token symbol resolution."""
    
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
                "view": [
                    {
                        "name": "getAmountsOut",
                        "description": "Get expected output amounts for a swap path",
                        "inputs": ["amountIn", "path"],
                        "contract": "router"
                    }
                ]
            },
            "parameter_processing": {
                "amountIn": {
                    "type": "token_amount",
                    "convert_from_human": True,
                    "get_decimals_from": "path[0]"
                },
                "path": {
                    "type": "array"
                }
            }
        }
    
    @pytest.mark.asyncio
    async def test_process_parameters_resolves_path_symbols(
        self,
        transaction_manager: Any,
        mock_find_token: AsyncMock,
        mock_token_manager: MagicMock,
        swap_app_config: Dict[str, Any]
    ) -> None:
        """Test that process_parameters resolves token symbols in path."""
        method_config = {
            "name": "getAmountsOut",
            "inputs": ["amountIn", "path"]
        }
        
        raw_params = {
            "amountIn": "1",  # 1 CL8Y
            "path": ["CL8Y", "CZUSD"]
        }
        
        with patch('utils.token.find_token', mock_find_token), \
             patch('services.tokens.token_manager', mock_token_manager):
            
            processed = await transaction_manager.process_parameters(
                method_config, raw_params, swap_app_config
            )
            
            # Path should be resolved to addresses
            assert "path" in processed
            assert processed["path"][0] == "0x1234567890123456789012345678901234567890"
            assert processed["path"][1] == "0xABCDEF1234567890ABCDEF1234567890ABCDEF12"
    
    @pytest.mark.asyncio
    async def test_process_parameters_uses_resolved_path_for_decimals(
        self,
        transaction_manager: Any,
        mock_find_token: AsyncMock,
        mock_token_manager: MagicMock,
        swap_app_config: Dict[str, Any]
    ) -> None:
        """Test that decimals lookup uses the resolved address, not symbol."""
        method_config = {
            "name": "getAmountsOut",
            "inputs": ["amountIn", "path"]
        }
        
        raw_params = {
            "amountIn": "1.5",
            "path": ["CL8Y", "CZUSD"]
        }
        
        with patch('utils.token.find_token', mock_find_token), \
             patch('services.tokens.token_manager', mock_token_manager):
            
            processed = await transaction_manager.process_parameters(
                method_config, raw_params, swap_app_config
            )
            
            # amountIn should be converted using decimals from resolved CL8Y address
            # 1.5 tokens with 18 decimals = 1.5 * 10^18
            expected_amount = int(1.5 * 10**18)
            assert processed["amountIn"] == expected_amount


class TestEdgeCases:
    """Test edge cases for token symbol resolution."""
    
    @pytest.fixture
    def mock_web3(self) -> MagicMock:
        """Create a mock Web3 instance."""
        return create_mock_web3()
    
    @pytest.fixture
    def transaction_manager(self, mock_web3: MagicMock) -> Any:
        """Create a TransactionManager with mocked dependencies."""
        from services.transaction.transaction_manager import TransactionManager
        manager = TransactionManager()
        manager.web3 = mock_web3
        return manager
    
    @pytest.mark.asyncio
    async def test_empty_path(self, transaction_manager: Any) -> None:
        """Test that empty path returns empty list."""
        resolved = await transaction_manager._resolve_token_symbols_in_path([])
        assert resolved == []
    
    @pytest.mark.asyncio
    async def test_eth_preserved_in_path(
        self, 
        transaction_manager: Any,
        mock_web3: MagicMock
    ) -> None:
        """Test that ETH is preserved in path just like BNB."""
        mock_find_token = AsyncMock(return_value={
            "address": "0xABCDEF1234567890ABCDEF1234567890ABCDEF12",
            "symbol": "CZUSD",
            "name": "CZ USD", 
            "decimals": 18
        })
        
        mock_token_manager = MagicMock()
        mock_token_manager.default_tokens = TEST_TOKENS
        
        with patch('utils.token.find_token', mock_find_token), \
             patch('services.tokens.token_manager', mock_token_manager):
            
            path = ["ETH", "CZUSD"]
            resolved = await transaction_manager._resolve_token_symbols_in_path(path)
            
            assert resolved[0] == "ETH"
    
    @pytest.mark.asyncio
    async def test_three_hop_path(
        self, 
        transaction_manager: Any
    ) -> None:
        """Test resolving a three-hop swap path."""
        mock_find_token = AsyncMock(side_effect=lambda symbol=None, address=None: {
            "CL8Y": {"address": "0x1234567890123456789012345678901234567890", "symbol": "CL8Y", "name": "Clay", "decimals": 18},
            "BUSD": {"address": "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56", "symbol": "BUSD", "name": "Binance USD", "decimals": 18},
            "CAKE": {"address": "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82", "symbol": "CAKE", "name": "PancakeSwap", "decimals": 18},
        }.get(symbol.upper() if symbol else None))
        
        mock_token_manager = MagicMock()
        mock_token_manager.default_tokens = TEST_TOKENS
        
        with patch('utils.token.find_token', mock_find_token), \
             patch('services.tokens.token_manager', mock_token_manager):
            
            path = ["CL8Y", "BUSD", "CAKE"]
            resolved = await transaction_manager._resolve_token_symbols_in_path(path)
            
            assert len(resolved) == 3
            assert resolved[0] == "0x1234567890123456789012345678901234567890"
            assert resolved[1] == "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56"
            assert resolved[2] == "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82"


class TestIntegrationScenario:
    """Integration-style tests simulating the actual error scenario."""
    
    @pytest.fixture
    def mock_web3(self) -> MagicMock:
        """Create a mock Web3 instance."""
        return create_mock_web3()
    
    @pytest.fixture
    def transaction_manager(self, mock_web3: MagicMock) -> Any:
        """Create a TransactionManager with mocked dependencies."""
        from services.transaction.transaction_manager import TransactionManager
        manager = TransactionManager()
        manager.web3 = mock_web3
        return manager
    
    @pytest.mark.asyncio
    async def test_whats_the_price_of_cl8y_in_czusd_scenario(
        self,
        transaction_manager: Any
    ) -> None:
        """
        Test the exact scenario that caused the original error:
        User asks: "Whats the price of CL8Y in CZUSD?"
        LLM returns path: ["CL8Y", "CZUSD"]
        
        Before fix: ENS name: 'CL8Y' is invalid error
        After fix: Path should be resolved to addresses
        """
        mock_find_token = AsyncMock(side_effect=lambda symbol=None, address=None: {
            "CL8Y": {
                "address": "0x1234567890123456789012345678901234567890",
                "symbol": "CL8Y",
                "name": "Clay Token",
                "decimals": 18
            },
            "CZUSD": {
                "address": "0xABCDEF1234567890ABCDEF1234567890ABCDEF12",
                "symbol": "CZUSD", 
                "name": "CZ USD",
                "decimals": 18
            }
        }.get(symbol.upper() if symbol else None))
        
        mock_token_manager = MagicMock()
        mock_token_manager.default_tokens = TEST_TOKENS
        
        with patch('utils.token.find_token', mock_find_token), \
             patch('services.tokens.token_manager', mock_token_manager):
            
            # This is what the LLM returns
            llm_path = ["CL8Y", "CZUSD"]
            
            # This is what we need for the contract call
            resolved_path = await transaction_manager._resolve_token_symbols_in_path(llm_path)
            
            # Verify both are valid addresses now
            assert transaction_manager.web3.is_address(resolved_path[0])
            assert transaction_manager.web3.is_address(resolved_path[1])
            
            # Verify they're the correct addresses
            assert resolved_path[0] == "0x1234567890123456789012345678901234567890"
            assert resolved_path[1] == "0xABCDEF1234567890ABCDEF1234567890ABCDEF12"
    
    @pytest.mark.asyncio  
    async def test_symbol_not_address_causes_clear_error(
        self,
        transaction_manager: Any
    ) -> None:
        """Test that passing a symbol directly to Web3 address conversion fails."""
        # Verify that "CL8Y" is not recognized as an address
        assert not transaction_manager.web3.is_address("CL8Y")
        
        # Verify that trying to convert it raises an error
        with pytest.raises(ValueError):
            transaction_manager.web3.to_checksum_address("CL8Y")

