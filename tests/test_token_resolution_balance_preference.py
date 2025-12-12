"""
Unit tests for token symbol resolution preferring tokens with non-zero balances.

Tests the fix for the issue where users have multiple tokens with the same symbol
(e.g., CL8Y old and new addresses) and the system should prefer the token with
the highest balance when resolving symbols.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List, Optional

# Test addresses
CL8Y_OLD = "0x999311589cc1ed0065ad9ed9702cb593ffc62ddf"  # Old CL8Y with 0 balance
CL8Y_NEW = "0x1234567890123456789012345678901234567890"  # New CL8Y with balance
CL8Y_DEFAULT = "0xABCDEF1234567890ABCDEF1234567890ABCDEF12"  # CL8Y in default list with 0 balance

WALLET_ADDRESS = "0x3fC4D8a13207A2cbcb09758eaa8c22C62857DfAF"
USER_ID = "test_user_123"


class TestTokenResolutionBalancePreference:
    """Test that token resolution prefers tokens with non-zero balances."""
    
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
    def mock_token_manager(self) -> MagicMock:
        """Create a mock token_manager."""
        token_manager = MagicMock()
        
        # Default token list has CL8Y at CL8Y_DEFAULT (with 0 balance)
        token_manager.default_tokens = {
            CL8Y_DEFAULT: {
                "symbol": "CL8Y",
                "name": "CeramicLiberty.com",
                "decimals": 18
            }
        }
        
        # User has tracked both old and new CL8Y tokens
        async def get_tracked_tokens(user_id: str) -> List[Dict[str, Any]]:
            return [
                {
                    "token_address": CL8Y_OLD,
                    "symbol": "CL8Y",
                    "name": "CeramicLiberty.com (Old)",
                    "decimals": 18,
                    "chain_id": 56
                },
                {
                    "token_address": CL8Y_NEW,
                    "symbol": "CL8Y",
                    "name": "CeramicLiberty.com (New)",
                    "decimals": 18,
                    "chain_id": 56
                }
            ]
        
        async def get_token_balance(wallet_address: str, token_address: str) -> int:
            # CL8Y_NEW has balance, others have 0
            if token_address.lower() == CL8Y_NEW.lower():
                return 13_552_103_200_785_384  # ~13.55 CL8Y
            elif token_address.lower() == CL8Y_OLD.lower():
                return 0
            elif token_address.lower() == CL8Y_DEFAULT.lower():
                return 0
            return 0
        
        async def _parse_default_token_list() -> Dict[str, Any]:
            return token_manager.default_tokens
        
        token_manager.get_tracked_tokens = AsyncMock(side_effect=get_tracked_tokens)
        token_manager.get_token_balance = AsyncMock(side_effect=get_token_balance)
        token_manager._parse_default_token_list = AsyncMock(side_effect=_parse_default_token_list)
        
        return token_manager
    
    @pytest.mark.asyncio
    async def test_resolves_to_token_with_balance_when_wallet_provided(
        self, mock_web3, mock_token_manager
    ) -> None:
        """
        Test that when wallet_address is provided, resolution prefers tracked tokens
        with non-zero balance over default token list tokens with zero balance.
        """
        from services.transaction.transaction_manager import TransactionManager
        
        with patch('utils.token.find_token', new_callable=AsyncMock) as mock_find_token, \
             patch('services.tokens.token_manager', mock_token_manager):
            
            # find_token returns None (not in default list via utils.token)
            mock_find_token.return_value = None
            
            manager = TransactionManager()
            manager.web3 = mock_web3
            
            # Resolve CL8Y with wallet address provided
            result = await manager._resolve_token_symbol(
                "CL8Y",
                user_id=USER_ID,
                wallet_address=WALLET_ADDRESS
            )
            
            # Should resolve to CL8Y_NEW (the one with balance)
            assert result is not None
            assert result.lower() == CL8Y_NEW.lower()
            
            # Verify it checked balances
            assert mock_token_manager.get_token_balance.called
    
    @pytest.mark.asyncio
    async def test_resolves_to_default_when_no_wallet_provided(
        self, mock_web3, mock_token_manager
    ) -> None:
        """
        Test that when wallet_address is not provided, resolution uses default token list.
        """
        from services.transaction.transaction_manager import TransactionManager
        
        with patch('utils.token.find_token', new_callable=AsyncMock) as mock_find_token, \
             patch('services.tokens.token_manager', mock_token_manager):
            
            # find_token returns default token
            mock_find_token.return_value = {
                'address': CL8Y_DEFAULT,
                'symbol': 'CL8Y',
                'name': 'CeramicLiberty.com',
                'decimals': 18
            }
            
            manager = TransactionManager()
            manager.web3 = mock_web3
            
            # Resolve CL8Y without wallet address
            result = await manager._resolve_token_symbol(
                "CL8Y",
                user_id=USER_ID,
                wallet_address=None
            )
            
            # Should resolve to default token list address
            assert result is not None
            assert result.lower() == CL8Y_DEFAULT.lower()
    
    @pytest.mark.asyncio
    async def test_prefers_highest_balance_when_multiple_tracked_tokens(
        self, mock_web3, mock_token_manager
    ) -> None:
        """
        Test that when multiple tracked tokens share the same symbol,
        resolution prefers the one with the highest balance.
        """
        from services.transaction.transaction_manager import TransactionManager
        
        # Modify mock to have both tokens with balances (CL8Y_NEW has more)
        async def get_token_balance(wallet_address: str, token_address: str) -> int:
            if token_address.lower() == CL8Y_NEW.lower():
                return 13_552_103_200_785_384  # ~13.55 CL8Y
            elif token_address.lower() == CL8Y_OLD.lower():
                return 12_689_072_202_450_769  # ~12.69 CL8Y (less)
            return 0
        
        mock_token_manager.get_token_balance = AsyncMock(side_effect=get_token_balance)
        
        with patch('utils.token.find_token', new_callable=AsyncMock) as mock_find_token, \
             patch('services.tokens.token_manager', mock_token_manager):
            
            mock_find_token.return_value = None
            
            manager = TransactionManager()
            manager.web3 = mock_web3
            
            # Resolve CL8Y
            result = await manager._resolve_token_symbol(
                "CL8Y",
                user_id=USER_ID,
                wallet_address=WALLET_ADDRESS
            )
            
            # Should resolve to CL8Y_NEW (highest balance)
            assert result is not None
            assert result.lower() == CL8Y_NEW.lower()
            
            # Verify it checked balances for both tokens
            assert mock_token_manager.get_token_balance.call_count >= 2
    
    @pytest.mark.asyncio
    async def test_uses_first_tracked_token_when_all_have_zero_balance(
        self, mock_web3, mock_token_manager
    ) -> None:
        """
        Test that when all tracked tokens have zero balance, resolution still uses
        the first tracked token (user may want to swap to get balance).
        Only falls back to default if no tracked tokens exist.
        """
        from services.transaction.transaction_manager import TransactionManager
        
        # Modify mock so all tracked tokens have zero balance
        async def get_token_balance(wallet_address: str, token_address: str) -> int:
            return 0  # All have zero balance
        
        mock_token_manager.get_token_balance = AsyncMock(side_effect=get_token_balance)
        
        with patch('utils.token.find_token', new_callable=AsyncMock) as mock_find_token, \
             patch('services.tokens.token_manager', mock_token_manager):
            
            # find_token returns None (not in default list via utils.token)
            mock_find_token.return_value = None
            
            manager = TransactionManager()
            manager.web3 = mock_web3
            
            # Resolve CL8Y
            result = await manager._resolve_token_symbol(
                "CL8Y",
                user_id=USER_ID,
                wallet_address=WALLET_ADDRESS
            )
            
            # Should use first tracked token (CL8Y_OLD) even though it has zero balance
            # This is correct behavior - user may want to swap to get balance
            assert result is not None
            assert result.lower() == CL8Y_OLD.lower()
    
    @pytest.mark.asyncio
    async def test_exact_bug_scenario_tracked_tokens_with_balance_vs_default_with_zero(
        self, mock_web3, mock_token_manager
    ) -> None:
        """
        Regression test for the exact bug from chat logs:
        
        Scenario:
        - User has TWO tracked CL8Y tokens with non-zero balances (13.55 and 12.69)
        - Default token list has CL8Y at a DIFFERENT address with 0 balance
        - When swap requested with wallet_address, should pick tracked token with highest balance
        - NOT the default list address with 0 balance
        
        Chat log evidence:
        - /balance shows: CL8Y: 13.552103200785384 and CL8Y: 12.689072202450769
        - Swap command: "Swap 1 CL8Y for CZB"
        - Bug response: "You have 0.0 CL8Y" (picked wrong address)
        """
        from services.transaction.transaction_manager import TransactionManager
        
        # User has TWO tracked CL8Y tokens with balances (matching chat log)
        two_tracked_cl8y = [
            {
                "token_address": CL8Y_NEW,
                "symbol": "CL8Y",
                "name": "CeramicLiberty.com",
                "decimals": 18,
                "chain_id": 56
            },
            {
                "token_address": CL8Y_OLD,
                "symbol": "CL8Y",
                "name": "CeramicLiberty.com",
                "decimals": 18,
                "chain_id": 56
            }
        ]
        
        async def get_tracked_tokens(user_id: str) -> List[Dict[str, Any]]:
            return two_tracked_cl8y
        
        async def get_token_balance(wallet_address: str, token_address: str) -> int:
            # Both tracked tokens have balances (matching chat log)
            if token_address.lower() == CL8Y_NEW.lower():
                return 13_552_103_200_785_384  # ~13.55 CL8Y
            elif token_address.lower() == CL8Y_OLD.lower():
                return 12_689_072_202_450_769  # ~12.69 CL8Y
            elif token_address.lower() == CL8Y_DEFAULT.lower():
                return 0  # User doesn't hold default list CL8Y
            return 0
        
        mock_token_manager.get_tracked_tokens = AsyncMock(side_effect=get_tracked_tokens)
        mock_token_manager.get_token_balance = AsyncMock(side_effect=get_token_balance)
        
        with patch('utils.token.find_token', new_callable=AsyncMock) as mock_find_token, \
             patch('services.tokens.token_manager', mock_token_manager):
            
            # Default token list returns CL8Y_DEFAULT (different address)
            mock_find_token.return_value = {
                'address': CL8Y_DEFAULT,
                'symbol': 'CL8Y',
                'name': 'CeramicLiberty.com',
                'decimals': 18
            }
            
            manager = TransactionManager()
            manager.web3 = mock_web3
            
            # Resolve CL8Y with wallet_address provided (swap scenario)
            result = await manager._resolve_token_symbol(
                "CL8Y",
                user_id=USER_ID,
                wallet_address=WALLET_ADDRESS
            )
            
            # Should resolve to CL8Y_NEW (highest balance among tracked tokens)
            # NOT CL8Y_DEFAULT (default list with 0 balance)
            assert result is not None
            assert result.lower() == CL8Y_NEW.lower()
            
            # Verify balance checks were made for tracked tokens
            balance_calls = mock_token_manager.get_token_balance.call_args_list
            checked_addresses = [call[0][1].lower() for call in balance_calls]
            assert CL8Y_NEW.lower() in checked_addresses or CL8Y_OLD.lower() in checked_addresses
