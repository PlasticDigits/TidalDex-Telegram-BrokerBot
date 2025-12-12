#!/usr/bin/env python3
"""Test for CL8Y/CZB direct route scenario.

This test verifies that when direct liquidity exists for CL8Y/CZB pair,
the direct route is tried first and succeeds, avoiding unnecessary intermediate hops.
"""
import json
import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from app.base.llm_app_session import LLMAppSession


@pytest.mark.integration
class TestCL8YCZBDirectRoute:
    """Test cases for CL8Y/CZB direct route scenario."""

    @pytest.fixture
    def llm_app_config(self) -> Dict[str, Any]:
        config_path = Path(__file__).parent.parent / "app" / "llm_apps" / "swap" / "config.json"
        with open(config_path, "r") as f:
            return json.load(f)

    @pytest.mark.asyncio
    async def test_direct_route_tried_first_and_succeeds(self, llm_app_config: Dict[str, Any]) -> None:
        """Verify direct CL8Y->CZB route is tried first and succeeds when liquidity exists."""
        session = LLMAppSession(user_id="123", llm_app_name="swap", llm_app_config=llm_app_config)

        from app.base.llm_app_session import transaction_manager as tm
        
        # Use realistic addresses (checksummed)
        cl8y_addr = tm.web3.to_checksum_address("0x999311589cc1Ed0065AD9eD9702cB593FFc62ddF")
        czb_addr = tm.web3.to_checksum_address("0xD963b2236D227a0302E19F2f9595F424950dc186")
        czusd_addr = tm.web3.to_checksum_address("0xE68b79e51bf826534Ff37AA9CeE71a3842ee9c70")

        call_order = []  # Track the order routes are tried

        async def fake_call_view_method(_contract: str, _abi: List[Dict[str, Any]], method: str, args: List[Any], status_callback=None):
            assert method == "getAmountsOut"
            amount, path = args
            call_order.append(path.copy())  # Store a copy to avoid mutation
            
            # Direct route succeeds with good output (simulating sufficient liquidity)
            if path == [cl8y_addr, czb_addr]:
                return [amount, amount * 100]  # Good output for direct route
            
            # All intermediate routes fail with INSUFFICIENT_LIQUIDITY
            if path == [cl8y_addr, czusd_addr, czb_addr]:
                raise ValueError("execution reverted: AmmLibrary: INSUFFICIENT_LIQUIDITY")
            
            raise AssertionError(f"Unexpected path: {path}")

        with patch("app.base.llm_app_session.transaction_manager._resolve_token_symbol", 
                   new=AsyncMock(side_effect=lambda s: czusd_addr if s == "CZUSD" else czb_addr if s == "CZB" else None)), \
             patch("app.base.llm_app_session.transaction_manager.call_view_method", 
                   new=AsyncMock(side_effect=fake_call_view_method)):
            best_path, best_result = await session._select_best_swap_route(
                contract_address="0xrouter",
                abi=[],
                quote_method="getAmountsOut",
                amount=10**18,  # 1 token (assuming 18 decimals)
                token_in=cl8y_addr,
                token_out=czb_addr,
            )

        # Direct route should be selected
        assert best_path == [cl8y_addr, czb_addr], f"Expected direct route, got: {best_path}"
        assert best_result[-1] == 10**18 * 100, f"Expected good output, got: {best_result}"
        
        # Direct route should be tried first
        assert call_order[0] == [cl8y_addr, czb_addr], \
            f"Expected direct route first, got order: {call_order}"

    @pytest.mark.asyncio
    async def test_direct_route_fails_falls_back_to_intermediate(self, llm_app_config: Dict[str, Any]) -> None:
        """Verify that when direct route fails, intermediate routes are tried."""
        session = LLMAppSession(user_id="123", llm_app_name="swap", llm_app_config=llm_app_config)

        from app.base.llm_app_session import transaction_manager as tm
        
        cl8y_addr = tm.web3.to_checksum_address("0x999311589cc1Ed0065AD9eD9702cB593FFc62ddF")
        czb_addr = tm.web3.to_checksum_address("0xD963b2236D227a0302E19F2f9595F424950dc186")
        czusd_addr = tm.web3.to_checksum_address("0xE68b79e51bf826534Ff37AA9CeE71a3842ee9c70")

        call_order = []

        async def fake_call_view_method(_contract: str, _abi: List[Dict[str, Any]], method: str, args: List[Any], status_callback=None):
            assert method == "getAmountsOut"
            amount, path = args
            call_order.append(path.copy())
            
            # Direct route fails (no direct liquidity)
            if path == [cl8y_addr, czb_addr]:
                raise ValueError("execution reverted: AmmLibrary: INSUFFICIENT_LIQUIDITY")
            
            # Intermediate route succeeds
            if path == [cl8y_addr, czusd_addr, czb_addr]:
                return [amount, amount * 50, amount * 50]
            
            raise AssertionError(f"Unexpected path: {path}")

        with patch("app.base.llm_app_session.transaction_manager._resolve_token_symbol", 
                   new=AsyncMock(side_effect=lambda s: czusd_addr if s == "CZUSD" else czb_addr if s == "CZB" else None)), \
             patch("app.base.llm_app_session.transaction_manager.call_view_method", 
                   new=AsyncMock(side_effect=fake_call_view_method)):
            best_path, best_result = await session._select_best_swap_route(
                contract_address="0xrouter",
                abi=[],
                quote_method="getAmountsOut",
                amount=10**18,
                token_in=cl8y_addr,
                token_out=czb_addr,
            )

        # Should fall back to intermediate route
        assert best_path == [cl8y_addr, czusd_addr, czb_addr]
        # Direct route should still be tried first
        assert call_order[0] == [cl8y_addr, czb_addr], \
            f"Expected direct route tried first, got: {call_order}"
