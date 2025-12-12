"""
Regression test for token symbol resolution with user context.

Tests the fix for the issue where the LLM thought the wallet had 0 CL8Y
because token symbol resolution was using the default token list instead of
the user's tracked tokens.

Issue: When a user has multiple tokens with the same symbol (e.g., CL8Y),
or when the default token list has a different CL8Y address than what the
user holds, the system should prefer the user's tracked tokens, especially
the one with the highest balance.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List, Optional


# Test token data - simulating multiple CL8Y tokens
CL8Y_OLD = "0x999311589cc1ed0065ad9ed9702cb593ffc62ddf"  # Old/deprecated CL8Y
CL8Y_NEW_TRACKED = "0x1234567890123456789012345678901234567890"  # User's tracked CL8Y
CL8Y_DEFAULT_LIST = "0xABCDEF1234567890ABCDEF1234567890ABCDEF12"  # CL8Y in default token list

TEST_TOKENS = {
    CL8Y_NEW_TRACKED: {
        "symbol": "CL8Y",
        "name": "CeramicLiberty.com",
        "decimals": 18
    },
    CL8Y_DEFAULT_LIST: {
        "symbol": "CL8Y",
        "name": "CeramicLiberty.com",
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

# User's tracked tokens (has CL8Y_NEW_TRACKED with balance)
USER_TRACKED_TOKENS = [
    {
        "token_address": CL8Y_NEW_TRACKED,
        "symbol": "CL8Y",
        "name": "CeramicLiberty.com",
        "decimals": 18,
        "chain_id": 56
    },
    {
        "token_address": "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82",
        "symbol": "CAKE",
        "name": "PancakeSwap Token",
        "decimals": 18,
        "chain_id": 56
    }
]


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
        return address
    
    mock.is_address = is_address
    mock.to_checksum_address = to_checksum_address
    
    return mock


class TestTokenSymbolResolutionUserContext:
    """Test token symbol resolution with user context (tracked tokens)."""
    
    @pytest.fixture
    def mock_web3(self) -> MagicMock:
        """Create a mock Web3 instance."""
        return create_mock_web3()
    
    @pytest.fixture
    def mock_token_manager(self) -> MagicMock:
        """Create a mock token_manager with user's tracked tokens."""
        token_manager = MagicMock()
        token_manager.default_tokens = {
            CL8Y_DEFAULT_LIST: TEST_TOKENS[CL8Y_DEFAULT_LIST],
            "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82": TEST_TOKENS["0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82"]
        }
        
        async def get_tracked_tokens(user_id: str) -> List[Dict[str, Any]]:
            return USER_TRACKED_TOKENS
        
        async def get_token_balance(wallet_address: str, token_address: str) -> int:
            # CL8Y_NEW_TRACKED has balance, CL8Y_DEFAULT_LIST has 0
            if token_address.lower() == CL8Y_NEW_TRACKED.lower():
                return 13_552_103_200_785_384  # 13.55 CL8Y (with decimals)
            elif token_address.lower() == CL8Y_DEFAULT_LIST.lower():
                return 0  # User doesn't hold this CL8Y
            return 0
        
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
        
        token_manager.get_tracked_tokens = AsyncMock(side_effect=get_tracked_tokens)
        token_manager.get_token_balance = AsyncMock(side_effect=get_token_balance)
        token_manager.get_token_info = AsyncMock(side_effect=get_token_info)
        token_manager._get_user_pin = MagicMock(return_value="test_pin")
        
        return token_manager
    
    @pytest.fixture
    def mock_wallet_manager(self) -> MagicMock:
        """Create a mock wallet_manager."""
        wallet_manager = MagicMock()
        
        def get_active_wallet_name(user_id: str) -> str:
            return "test_wallet"
        
        def get_wallet_by_name(user_id: str, wallet_name: str, pin: Optional[str]) -> Dict[str, Any]:
            return {
                "address": "0x1234567890123456789012345678901234567890",
                "private_key": "0x" + "1" * 64
            }
        
        wallet_manager.get_active_wallet_name = get_active_wallet_name
        wallet_manager.get_wallet_by_name = get_wallet_by_name
        
        return wallet_manager
    
    @pytest.fixture
    def mock_find_token(self) -> AsyncMock:
        """Create a mock find_token that returns CL8Y_DEFAULT_LIST."""
        async def _find_token(
            symbol: Optional[str] = None, 
            address: Optional[str] = None
        ) -> Optional[Dict[str, Any]]:
            if symbol and symbol.upper() == "CL8Y":
                # Default token list has CL8Y_DEFAULT_LIST
                return {
                    "address": CL8Y_DEFAULT_LIST,
                    "symbol": "CL8Y",
                    "name": "CeramicLiberty.com",
                    "decimals": 18
                }
            return None
        
        return AsyncMock(side_effect=_find_token)
    
    @pytest.fixture
    def transaction_manager(self, mock_web3: MagicMock) -> Any:
        """Create a TransactionManager with mocked dependencies."""
        from services.transaction.transaction_manager import TransactionManager
        
        manager = TransactionManager()
        manager.web3 = mock_web3
        return manager
    
    @pytest.mark.asyncio
    async def test_resolve_cl8y_prefers_default_list_over_tracked_tokens(
        self,
        transaction_manager: Any,
        mock_find_token: AsyncMock,
        mock_token_manager: MagicMock,
        mock_wallet_manager: MagicMock
    ) -> None:
        """
        Test that CL8Y resolution prefers the default token list over user's tracked tokens.
        
        Scenario:
        - User has tracked CL8Y_NEW_TRACKED with balance 13.55
        - Default token list has CL8Y_DEFAULT_LIST (user doesn't hold this)
        - Resolution should return CL8Y_DEFAULT_LIST (default list is authoritative)
        """
        user_id = "test_user_123"
        
        with patch('utils.token.find_token', mock_find_token), \
             patch('services.tokens.token_manager', mock_token_manager), \
             patch('services.wallet.wallet_manager', mock_wallet_manager):
            
            result = await transaction_manager._resolve_token_symbol("CL8Y", user_id=user_id)
            
            # Default list should win
            assert result is not None
            assert result.lower() == CL8Y_DEFAULT_LIST.lower()
    
    @pytest.mark.asyncio
    async def test_resolve_cl8y_without_user_id_uses_default_list(
        self,
        transaction_manager: Any,
        mock_find_token: AsyncMock,
        mock_token_manager: MagicMock
    ) -> None:
        """
        Test that without user_id, resolution falls back to default token list.
        """
        with patch('utils.token.find_token', mock_find_token), \
             patch('services.tokens.token_manager', mock_token_manager):
            
            result = await transaction_manager._resolve_token_symbol("CL8Y")
            
            # Without user_id, should use default list
            assert result is not None
            assert result.lower() == CL8Y_DEFAULT_LIST.lower()
    
    @pytest.mark.asyncio
    async def test_resolve_multiple_tracked_tokens_prefers_highest_balance_when_default_missing(
        self,
        transaction_manager: Any,
        mock_token_manager: MagicMock,
        mock_wallet_manager: MagicMock
    ) -> None:
        """
        Test that when user has multiple tracked tokens with same symbol,
        resolution prefers the one with highest balance when default list is missing.
        """
        user_id = "test_user_123"
        wallet_address = "0x1234567890123456789012345678901234567890"
        
        # Mock multiple CL8Y tokens tracked by user
        multiple_cl8y_tracked = [
            {
                "token_address": CL8Y_NEW_TRACKED,
                "symbol": "CL8Y",
                "name": "CeramicLiberty.com",
                "decimals": 18,
                "chain_id": 56
            },
            {
                "token_address": "0x1111111111111111111111111111111111111111",
                "symbol": "CL8Y",
                "name": "CeramicLiberty.com",
                "decimals": 18,
                "chain_id": 56
            }
        ]
        
        async def get_tracked_tokens(user_id: str) -> List[Dict[str, Any]]:
            return multiple_cl8y_tracked
        
        async def get_token_balance(wallet_address: str, token_address: str) -> int:
            if token_address.lower() == CL8Y_NEW_TRACKED.lower():
                return 13_552_103_200_785_384  # Higher balance
            elif token_address.lower() == "0x1111111111111111111111111111111111111111".lower():
                return 1_000_000_000_000_000  # Lower balance
            return 0
        
        mock_token_manager.get_tracked_tokens = AsyncMock(side_effect=get_tracked_tokens)
        mock_token_manager.get_token_balance = AsyncMock(side_effect=get_token_balance)
        mock_token_manager.default_tokens = {}
        mock_token_manager._parse_default_token_list = AsyncMock(return_value={})
        
        with patch('utils.token.find_token', AsyncMock(return_value=None)), \
             patch('services.tokens.token_manager', mock_token_manager), \
             patch('services.wallet.wallet_manager', mock_wallet_manager):
            
            # Default list missing -> tracked fallback should pick highest balance
            result = await transaction_manager._resolve_token_symbol(
                "CL8Y",
                user_id=user_id,
                wallet_address=wallet_address,
            )
            
            # Should prefer the one with highest balance
            assert result is not None
            assert result.lower() == CL8Y_NEW_TRACKED.lower()
    
    @pytest.mark.asyncio
    async def test_resolve_path_with_user_context(
        self,
        transaction_manager: Any,
        mock_find_token: AsyncMock,
        mock_token_manager: MagicMock,
        mock_wallet_manager: MagicMock
    ) -> None:
        """
        Test that path resolution uses default list resolution when available.
        """
        user_id = "test_user_123"
        
        with patch('utils.token.find_token', mock_find_token), \
             patch('services.tokens.token_manager', mock_token_manager), \
             patch('services.wallet.wallet_manager', mock_wallet_manager):
            
            path = ["CL8Y", "CAKE"]
            resolved = await transaction_manager._resolve_token_symbols_in_path(path, user_id=user_id)
            
            # CL8Y should resolve to default list token
            assert len(resolved) == 2
            assert resolved[0].lower() == CL8Y_DEFAULT_LIST.lower()
            assert resolved[1].lower() == "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82".lower()
    
    @pytest.mark.asyncio
    async def test_process_parameters_passes_user_id(
        self,
        transaction_manager: Any,
        mock_find_token: AsyncMock,
        mock_token_manager: MagicMock,
        mock_wallet_manager: MagicMock
    ) -> None:
        """
        Test that process_parameters passes user_id to path resolution.
        """
        user_id = "test_user_123"
        
        method_config = {
            "name": "swapExactTokensForTokens",
            "inputs": ["amountIn", "amountOutMin", "path", "to", "deadline"]
        }
        
        raw_params = {
            "amountIn": "1",
            "path": ["CL8Y", "CAKE"]
        }
        
        app_config = {
            "name": "swap",
            "parameter_processing": {
                "amountIn": {
                    "type": "token_amount",
                    "convert_from_human": True,
                    "get_decimals_from": "path[0]"
                }
            }
        }
        
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
        
        mock_token_manager.get_token_info = AsyncMock(side_effect=get_token_info)
        
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
        
        mock_token_manager.get_token_info = AsyncMock(side_effect=get_token_info)
        
        with patch('utils.token.find_token', mock_find_token), \
             patch('services.tokens.token_manager', mock_token_manager), \
             patch('services.wallet.wallet_manager', mock_wallet_manager):
            
            processed = await transaction_manager.process_parameters(
                method_config, raw_params, app_config, user_id=user_id
            )
            
            # Path should be resolved using user context
            assert "path" in processed
            assert processed["path"][0].lower() == CL8Y_DEFAULT_LIST.lower()
    
    @pytest.mark.asyncio
    async def test_resolve_symbol_without_tracked_tokens_falls_back(
        self,
        transaction_manager: Any,
        mock_find_token: AsyncMock,
        mock_token_manager: MagicMock
    ) -> None:
        """
        Test that resolution falls back to default list when user has no tracked tokens.
        """
        user_id = "test_user_no_tokens"
        
        # Mock empty tracked tokens
        async def get_tracked_tokens(uid: str) -> List[Dict[str, Any]]:
            return []
        
        mock_token_manager.get_tracked_tokens = AsyncMock(side_effect=get_tracked_tokens)
        
        with patch('utils.token.find_token', mock_find_token), \
             patch('services.tokens.token_manager', mock_token_manager):
            
            result = await transaction_manager._resolve_token_symbol("CL8Y", user_id=user_id)
            
            # Should fall back to default list
            assert result is not None
            assert result.lower() == CL8Y_DEFAULT_LIST.lower()
    
    @pytest.mark.asyncio
    async def test_resolve_symbol_handles_tracked_token_error_gracefully(
        self,
        transaction_manager: Any,
        mock_find_token: AsyncMock,
        mock_token_manager: MagicMock
    ) -> None:
        """
        Test that resolution handles errors when fetching tracked tokens gracefully.
        """
        user_id = "test_user_error"
        
        # Mock error when getting tracked tokens
        async def get_tracked_tokens(uid: str) -> List[Dict[str, Any]]:
            raise Exception("Database error")
        
        mock_token_manager.get_tracked_tokens = AsyncMock(side_effect=get_tracked_tokens)
        
        with patch('utils.token.find_token', mock_find_token), \
             patch('services.tokens.token_manager', mock_token_manager):
            
            # Should not raise, should fall back to default list
            result = await transaction_manager._resolve_token_symbol("CL8Y", user_id=user_id)
            
            assert result is not None
            assert result.lower() == CL8Y_DEFAULT_LIST.lower()

