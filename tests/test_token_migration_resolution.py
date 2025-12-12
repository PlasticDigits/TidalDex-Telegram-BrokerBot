#!/usr/bin/env python3
"""Test for token migration resolution - ensuring default token list is authoritative.

This test verifies that when a user has an old/migrated token tracked (e.g., old CL8Y contract),
the system correctly resolves to the new address from the default token list instead of
using the stale tracked token.

Scenario:
- User has old CL8Y tracked at 0x999311589cc1Ed0065AD9eD9702cB593FFc62ddF (old contract)
- Default token list has CL8Y at 0x8F452a1fdd388A45e1080992eFF051b4dd9048d2 (new contract)
- System should use the default token list address (authoritative)
"""
import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from services.transaction.transaction_manager import TransactionManager


class TestTokenMigrationResolution:
    """Test cases for token migration scenarios."""

    @pytest.fixture
    def transaction_manager(self) -> TransactionManager:
        """Create a TransactionManager instance."""
        return TransactionManager()

    @pytest.fixture
    def old_cl8y_address(self) -> str:
        """Old CL8Y contract address (stale/migrated)."""
        return "0x999311589cc1Ed0065AD9eD9702cB593FFc62ddF"

    @pytest.fixture
    def new_cl8y_address(self) -> str:
        """New CL8Y contract address (current/correct)."""
        return "0x8F452a1fdd388A45e1080992eFF051b4dd9048d2"

    @pytest.mark.asyncio
    async def test_default_list_preferred_over_tracked_token(
        self,
        transaction_manager: TransactionManager,
        old_cl8y_address: str,
        new_cl8y_address: str,
    ) -> None:
        """Verify default token list is used even when user has stale tracked token with balance."""
        user_id = "test_user_123"
        wallet_address = "0x1234567890123456789012345678901234567890"

        # Mock tracked tokens - user has old CL8Y with balance
        mock_tracked_tokens = [
            {
                "token_address": old_cl8y_address,
                "symbol": "CL8Y",
                "name": "Ceramic Liberty",
                "decimals": 18,
            }
        ]

        # Mock default token list - has new CL8Y address
        mock_default_token_info = {
            "symbol": "CL8Y",
            "name": "Ceramic Liberty",
            "address": new_cl8y_address,
            "decimals": 18,
        }

        # Mock token_manager
        mock_token_manager = MagicMock()
        mock_token_manager.get_tracked_tokens = AsyncMock(return_value=mock_tracked_tokens)
        mock_token_manager.get_token_balance = AsyncMock(return_value=10**18)

        with patch("utils.token.find_token", new=AsyncMock(return_value=mock_default_token_info)), \
             patch("services.transaction.transaction_manager.token_manager", mock_token_manager, create=True):

            result = await transaction_manager._resolve_token_symbol(
                symbol="CL8Y",
                user_id=user_id,
                wallet_address=wallet_address,
            )

        # Should return the NEW address from default list, not the old tracked one
        # Note: TransactionManager.web3.to_checksum_address will be called
        assert result.lower() == new_cl8y_address.lower(), (
            f"Expected new CL8Y address {new_cl8y_address}, "
            f"got {result}. Default token list should be authoritative."
        )

    @pytest.mark.asyncio
    async def test_tracked_token_used_when_not_in_default_list(
        self,
        transaction_manager: TransactionManager,
    ) -> None:
        """Verify tracked tokens are used as fallback when token not in default list."""
        user_id = "test_user_123"
        wallet_address = "0x1234567890123456789012345678901234567890"
        custom_token_address = "0xC0570FFACE1234567890123456789012345678AB"  # Valid hex address

        # Mock tracked tokens - user has a custom token not in default list
        mock_tracked_tokens = [
            {
                "token_address": custom_token_address,
                "symbol": "CUSTOM",
                "name": "Custom Token",
                "decimals": 18,
            }
        ]

        # Mock token_manager with empty default_tokens
        mock_token_manager = MagicMock()
        mock_token_manager.get_tracked_tokens = AsyncMock(return_value=mock_tracked_tokens)
        mock_token_manager.default_tokens = {}
        mock_token_manager._parse_default_token_list = AsyncMock()

        with patch("utils.token.find_token", new=AsyncMock(return_value=None)), \
             patch("services.tokens.token_manager", mock_token_manager):

            result = await transaction_manager._resolve_token_symbol(
                symbol="CUSTOM",
                user_id=user_id,
                wallet_address=wallet_address,
            )

        # Should return the tracked token address since it's not in default list
        assert result is not None, "Expected tracked token to be resolved"
        assert result.lower() == custom_token_address.lower(), (
            f"Expected tracked token address {custom_token_address}, got {result}. "
            f"Tracked tokens should be used when not in default list."
        )

    @pytest.mark.asyncio
    async def test_stale_tracked_token_is_auto_purged(
        self,
        transaction_manager: TransactionManager,
        old_cl8y_address: str,
        new_cl8y_address: str,
    ) -> None:
        """Verify stale tracked token is automatically purged when found."""
        user_id = "test_user_123"

        # Mock tracked tokens - user has old CL8Y
        mock_tracked_tokens = [
            {
                "token_address": old_cl8y_address,
                "symbol": "CL8Y",
                "name": "Ceramic Liberty",
                "decimals": 18,
            }
        ]

        # Mock default token list - has new CL8Y address
        mock_default_token_info = {
            "symbol": "CL8Y",
            "name": "Ceramic Liberty",
            "address": new_cl8y_address,
            "decimals": 18,
        }

        # Mock token_manager
        mock_token_manager = MagicMock()
        mock_token_manager.get_tracked_tokens = AsyncMock(return_value=mock_tracked_tokens)
        mock_token_manager.untrack = AsyncMock(return_value=True)

        with patch("utils.token.find_token", new=AsyncMock(return_value=mock_default_token_info)), \
             patch("services.tokens.token_manager", mock_token_manager):

            result = await transaction_manager._resolve_token_symbol(
                symbol="CL8Y",
                user_id=user_id,
            )

        # Verify correct address is returned
        assert result.lower() == new_cl8y_address.lower(), (
            f"Expected new address {new_cl8y_address}, got {result}"
        )
        
        # Verify untrack was called for the stale token
        mock_token_manager.untrack.assert_called_once_with(user_id, old_cl8y_address)

    @pytest.mark.asyncio
    async def test_no_purge_when_tracked_matches_default(
        self,
        transaction_manager: TransactionManager,
        new_cl8y_address: str,
    ) -> None:
        """Verify no purge when tracked token address matches default list."""
        user_id = "test_user_123"

        # Mock tracked tokens - user has correct CL8Y (matches default)
        mock_tracked_tokens = [
            {
                "token_address": new_cl8y_address,
                "symbol": "CL8Y",
                "name": "Ceramic Liberty",
                "decimals": 18,
            }
        ]

        # Mock default token list - has same CL8Y address
        mock_default_token_info = {
            "symbol": "CL8Y",
            "name": "Ceramic Liberty",
            "address": new_cl8y_address,
            "decimals": 18,
        }

        # Mock token_manager
        mock_token_manager = MagicMock()
        mock_token_manager.get_tracked_tokens = AsyncMock(return_value=mock_tracked_tokens)
        mock_token_manager.untrack = AsyncMock(return_value=True)

        with patch("utils.token.find_token", new=AsyncMock(return_value=mock_default_token_info)), \
             patch("services.tokens.token_manager", mock_token_manager):

            await transaction_manager._resolve_token_symbol(
                symbol="CL8Y",
                user_id=user_id,
            )

        # Verify untrack was NOT called since addresses match
        mock_token_manager.untrack.assert_not_called()

    @pytest.mark.asyncio
    async def test_case_insensitive_symbol_resolution(
        self,
        transaction_manager: TransactionManager,
        new_cl8y_address: str,
    ) -> None:
        """Verify symbol resolution is case-insensitive."""
        # Mock default token list
        mock_default_token_info = {
            "symbol": "CL8Y",
            "name": "Ceramic Liberty",
            "address": new_cl8y_address,
            "decimals": 18,
        }

        with patch("utils.token.find_token", new=AsyncMock(return_value=mock_default_token_info)):
            # Test lowercase
            result_lower = await transaction_manager._resolve_token_symbol("cl8y")
            # Test mixed case
            result_mixed = await transaction_manager._resolve_token_symbol("Cl8Y")
            # Test uppercase
            result_upper = await transaction_manager._resolve_token_symbol("CL8Y")

        assert result_lower.lower() == new_cl8y_address.lower()
        assert result_mixed.lower() == new_cl8y_address.lower()
        assert result_upper.lower() == new_cl8y_address.lower()


class TestTokenMigrationIntegration:
    """Integration tests for token migration scenarios with route selection."""

    @pytest.fixture
    def llm_app_config(self) -> Dict[str, Any]:
        """Load swap LLM app config."""
        import json
        config_path = Path(__file__).parent.parent / "app" / "llm_apps" / "swap" / "config.json"
        with open(config_path, "r") as f:
            return json.load(f)

    @pytest.mark.asyncio
    async def test_swap_route_uses_correct_token_address(
        self,
        llm_app_config: Dict[str, Any],
    ) -> None:
        """Verify swap routes use the correct token address from default list.
        
        This is a regression test for the CL8Y/CZB swap issue where the old
        CL8Y contract address was being used instead of the new one.
        """
        from app.base.llm_app_session import LLMAppSession

        session = LLMAppSession(user_id="123", llm_app_name="swap", llm_app_config=llm_app_config)

        # The correct addresses
        new_cl8y = "0x8F452a1fdd388A45e1080992eFF051b4dd9048d2"
        czb = "0xD963b2236D227a0302E19F2f9595F424950dc186"
        czusd = "0xE68b79e51bf826534Ff37AA9CeE71a3842ee9c70"

        call_paths: List[List[str]] = []

        async def fake_call_view_method(_contract: str, _abi: List[Dict[str, Any]], method: str, args: List[Any], status_callback=None):
            assert method == "getAmountsOut"
            amount, path = args
            call_paths.append([addr.lower() for addr in path])  # Store lowercase for comparison
            
            # Simulate successful quote for correct address
            if new_cl8y.lower() in [addr.lower() for addr in path]:
                return [amount, amount * 100]  # Success
            
            # Fail for any path using old address
            raise ValueError("INSUFFICIENT_LIQUIDITY")

        # Mock to return the new CL8Y address from default list
        mock_default_token_info = {
            "symbol": "CL8Y",
            "address": new_cl8y,
        }

        with patch("app.base.llm_app_session.transaction_manager._resolve_token_symbol",
                   new=AsyncMock(side_effect=lambda s, **kw: 
                       czusd if s.upper() == "CZUSD" else 
                       czb if s.upper() == "CZB" else 
                       new_cl8y if s.upper() == "CL8Y" else None)), \
             patch("app.base.llm_app_session.transaction_manager.call_view_method",
                   new=AsyncMock(side_effect=fake_call_view_method)):
            
            from app.base.llm_app_session import transaction_manager as tm
            
            best_path, best_result = await session._select_best_swap_route(
                contract_address="0xrouter",
                abi=[],
                quote_method="getAmountsOut",
                amount=10**18,
                token_in=tm.web3.to_checksum_address(new_cl8y),  # Use new address
                token_out=tm.web3.to_checksum_address(czb),
            )

        # Verify the correct CL8Y address was used in routes
        assert len(call_paths) > 0, "At least one route should have been tried"
        for path in call_paths:
            assert new_cl8y.lower() in path, (
                f"Route should use new CL8Y address {new_cl8y}, got path: {path}"
            )
