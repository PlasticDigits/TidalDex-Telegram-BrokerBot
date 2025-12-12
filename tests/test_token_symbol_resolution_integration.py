"""
Integration tests for token symbol resolution with user context.

These tests verify the end-to-end behavior of token symbol resolution
when user context is available, including interaction with the database
and token manager.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List, Optional
import os


@pytest.mark.integration
class TestTokenSymbolResolutionIntegration:
    """Integration tests for token symbol resolution."""
    
    @pytest.fixture
    def mock_web3(self) -> MagicMock:
        """Create a mock Web3 instance."""
        mock = MagicMock()
        
        def is_address(value: str) -> bool:
            return isinstance(value, str) and value.startswith("0x") and len(value) == 42
        
        def to_checksum_address(address: str) -> str:
            return address
        
        mock.is_address = is_address
        mock.to_checksum_address = to_checksum_address
        return mock
    
    @pytest.fixture
    def setup_user_tokens(self) -> Dict[str, Any]:
        """Setup test data for user tokens."""
        return {
            "user_id": "test_user_12345",
            "wallet_address": "0x1234567890123456789012345678901234567890",
            "tracked_tokens": [
                {
                    "token_address": "0xTRACKED_CL8Y",
                    "symbol": "CL8Y",
                    "name": "CeramicLiberty.com",
                    "decimals": 18,
                    "balance": 13_552_103_200_785_384  # 13.55 CL8Y
                },
                {
                    "token_address": "0xTRACKED_CAKE",
                    "symbol": "CAKE",
                    "name": "PancakeSwap Token",
                    "decimals": 18,
                    "balance": 100_000_000_000_000_000  # 0.1 CAKE
                }
            ]
        }
    
    @pytest.mark.asyncio
    async def test_resolve_symbol_uses_tracked_token_with_balance(
        self,
        mock_web3: MagicMock,
        setup_user_tokens: Dict[str, Any]
    ) -> None:
        """
        Integration test: Resolve symbol should use tracked token that user holds.
        """
        from services.transaction.transaction_manager import TransactionManager
        
        user_id = setup_user_tokens["user_id"]
        wallet_address = setup_user_tokens["wallet_address"]
        
        # Mock token_manager
        token_manager = MagicMock()
        
        async def get_tracked_tokens(uid: str) -> List[Dict[str, Any]]:
            if uid == user_id:
                return [
                    {
                        "token_address": token["token_address"],
                        "symbol": token["symbol"],
                        "name": token["name"],
                        "decimals": token["decimals"]
                    }
                    for token in setup_user_tokens["tracked_tokens"]
                ]
            return []
        
        async def get_token_balance(w_addr: str, t_addr: str) -> int:
            for token in setup_user_tokens["tracked_tokens"]:
                if t_addr.lower() == token["token_address"].lower():
                    return token["balance"]
            return 0
        
        token_manager.get_tracked_tokens = AsyncMock(side_effect=get_tracked_tokens)
        token_manager.get_token_balance = AsyncMock(side_effect=get_token_balance)
        token_manager._get_user_pin = MagicMock(return_value="test_pin")
        token_manager.default_tokens = {}
        
        # Mock wallet_manager
        wallet_manager = MagicMock()
        wallet_manager.get_active_wallet_name = MagicMock(return_value="test_wallet")
        wallet_manager.get_wallet_by_name = MagicMock(return_value={
            "address": wallet_address,
            "private_key": "0x" + "1" * 64
        })
        
        # Mock find_token to return different CL8Y (simulating default list)
        async def find_token(symbol: Optional[str] = None, address: Optional[str] = None) -> Optional[Dict[str, Any]]:
            if symbol == "CL8Y":
                return {
                    "address": "0xDEFAULT_CL8Y",  # Different from tracked
                    "symbol": "CL8Y",
                    "name": "CeramicLiberty.com",
                    "decimals": 18
                }
            return None
        
        transaction_manager = TransactionManager()
        transaction_manager.web3 = mock_web3
        
        with patch('utils.token.find_token', AsyncMock(side_effect=find_token)), \
             patch('services.tokens.token_manager', token_manager), \
             patch('services.wallet.wallet_manager', wallet_manager):
            
            result = await transaction_manager._resolve_token_symbol("CL8Y", user_id=user_id)
            
            # Default list should win
            assert result is not None
            assert result.lower() == "0xdefault_cl8y"
    
    @pytest.mark.asyncio
    async def test_resolve_path_integration(
        self,
        mock_web3: MagicMock,
        setup_user_tokens: Dict[str, Any]
    ) -> None:
        """
        Integration test: Path resolution should use user context for all symbols.
        """
        from services.transaction.transaction_manager import TransactionManager
        
        user_id = setup_user_tokens["user_id"]
        wallet_address = setup_user_tokens["wallet_address"]
        
        token_manager = MagicMock()
        
        async def get_tracked_tokens(uid: str) -> List[Dict[str, Any]]:
            if uid == user_id:
                return [
                    {
                        "token_address": token["token_address"],
                        "symbol": token["symbol"],
                        "name": token["name"],
                        "decimals": token["decimals"]
                    }
                    for token in setup_user_tokens["tracked_tokens"]
                ]
            return []
        
        token_manager.get_tracked_tokens = AsyncMock(side_effect=get_tracked_tokens)
        token_manager.get_token_balance = AsyncMock(return_value=0)
        token_manager._get_user_pin = MagicMock(return_value="test_pin")
        token_manager.default_tokens = {}
        token_manager._parse_default_token_list = AsyncMock(return_value={})
        
        wallet_manager = MagicMock()
        wallet_manager.get_active_wallet_name = MagicMock(return_value="test_wallet")
        wallet_manager.get_wallet_by_name = MagicMock(return_value={
            "address": wallet_address,
            "private_key": "0x" + "1" * 64
        })
        
        transaction_manager = TransactionManager()
        transaction_manager.web3 = mock_web3
        
        with patch('utils.token.find_token', AsyncMock(return_value=None)), \
             patch('services.tokens.token_manager', token_manager), \
             patch('services.wallet.wallet_manager', wallet_manager):
            
            path = ["CL8Y", "CAKE"]
            resolved = await transaction_manager._resolve_token_symbols_in_path(path, user_id=user_id)
            
            # With default list unavailable, both should resolve to tracked tokens
            assert len(resolved) == 2
            assert resolved[0].lower() == "0xtracked_cl8y"
            assert resolved[1].lower() == "0xtracked_cake"
    
    @pytest.mark.asyncio
    async def test_process_parameters_integration_with_user_context(
        self,
        mock_web3: MagicMock,
        setup_user_tokens: Dict[str, Any]
    ) -> None:
        """
        Integration test: process_parameters should use user context for path resolution.
        """
        from services.transaction.transaction_manager import TransactionManager
        
        user_id = setup_user_tokens["user_id"]
        wallet_address = setup_user_tokens["wallet_address"]
        
        token_manager = MagicMock()
        
        async def get_tracked_tokens(uid: str) -> List[Dict[str, Any]]:
            if uid == user_id:
                return [
                    {
                        "token_address": token["token_address"],
                        "symbol": token["symbol"],
                        "name": token["name"],
                        "decimals": token["decimals"]
                    }
                    for token in setup_user_tokens["tracked_tokens"]
                ]
            return []
        
        async def get_token_info(t_addr: str) -> Optional[Dict[str, Any]]:
            for token in setup_user_tokens["tracked_tokens"]:
                if t_addr.lower() == token["token_address"].lower():
                    return {
                        "token_address": token["token_address"],
                        "symbol": token["symbol"],
                        "name": token["name"],
                        "decimals": token["decimals"],
                        "chain_id": 56
                    }
            return None
        
        token_manager.get_tracked_tokens = AsyncMock(side_effect=get_tracked_tokens)
        token_manager.get_token_balance = AsyncMock(return_value=0)
        token_manager.get_token_info = AsyncMock(side_effect=get_token_info)
        token_manager._get_user_pin = MagicMock(return_value="test_pin")
        token_manager.default_tokens = {}
        token_manager._parse_default_token_list = AsyncMock(return_value={})
        
        wallet_manager = MagicMock()
        wallet_manager.get_active_wallet_name = MagicMock(return_value="test_wallet")
        wallet_manager.get_wallet_by_name = MagicMock(return_value={
            "address": wallet_address,
            "private_key": "0x" + "1" * 64
        })
        
        method_config = {
            "name": "swapExactTokensForTokens",
            "inputs": ["amountIn", "amountOutMin", "path", "to", "deadline"]
        }
        
        raw_params = {
            "amountIn": "1.5",
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
        
        transaction_manager = TransactionManager()
        transaction_manager.web3 = mock_web3
        
        with patch('utils.token.find_token', AsyncMock(return_value=None)), \
             patch('services.tokens.token_manager', token_manager), \
             patch('services.wallet.wallet_manager', wallet_manager):
            
            processed = await transaction_manager.process_parameters(
                method_config, raw_params, app_config, user_id=user_id
            )
            
            # Path should be resolved to tracked tokens
            assert "path" in processed
            assert len(processed["path"]) == 2
            assert processed["path"][0].lower() == "0xtracked_cl8y"
            assert processed["path"][1].lower() == "0xtracked_cake"
            
            # amountIn should be converted using decimals from tracked CL8Y (18 decimals)
            assert processed["amountIn"] == int(1.5 * 10**18)
