#!/usr/bin/env python3
"""Tests for swap route probing (CZUSD/CZB).

Why this exists:
- The swap LLM app can receive an under-specified path like ["CL8Y", "CZB"].
- On TidalDex, multiple intermediate routes may exist/behave differently:
  1) token1 -> CZUSD -> token2
  2) token1 -> CZB   -> token2
  3) token1 -> CZUSD -> CZB -> token2
  4) token1 -> CZB   -> CZUSD -> token2

The app must try all 4 (and pick the best non-reverting quote) instead of hardcoding
one route.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, patch

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from app.base.llm_app_session import LLMAppSession


@pytest.mark.integration
class TestSwapRouteProbing:
    @pytest.fixture
    def llm_app_config(self) -> Dict[str, Any]:
        config_path = Path(__file__).parent.parent / "app" / "llm_apps" / "swap" / "config.json"
        with open(config_path, "r") as f:
            return json.load(f)

    @pytest.mark.asyncio
    async def test_select_best_route_getamountsout_prefers_max_output(self, llm_app_config: Dict[str, Any]) -> None:
        """If multiple routes succeed, choose the one with maximum output."""
        session = LLMAppSession(user_id="123", llm_app_name="swap", llm_app_config=llm_app_config)

        # Use checksum addresses because the session normalizes via Web3.
        from app.base.llm_app_session import transaction_manager as tm
        czusd = tm.web3.to_checksum_address("0x00000000000000000000000000000000000000A1")
        czb = tm.web3.to_checksum_address("0x00000000000000000000000000000000000000B2")
        token_in = tm.web3.to_checksum_address("0x00000000000000000000000000000000000000C3")
        token_out = tm.web3.to_checksum_address("0x00000000000000000000000000000000000000D4")

        # Route outputs:
        # 1) token_in->czusd->token_out : output 100
        # 2) token_in->czb->token_out   : revert
        # 3) token_in->czusd->czb->token_out : output 150  (best)
        # 4) token_in->czb->czusd->token_out : output 120
        async def fake_call_view_method(_contract: str, _abi: List[Dict[str, Any]], method: str, args: List[Any], status_callback=None):
            assert method == "getAmountsOut"
            amount, path = args
            assert amount == 1
            if path == [token_in, czusd, token_out]:
                return [1, 100]
            if path == [token_in, czb, token_out]:
                raise ValueError("execution reverted")
            if path == [token_in, czusd, czb, token_out]:
                return [1, 10, 20, 150]
            if path == [token_in, czb, czusd, token_out]:
                return [1, 10, 120]
            raise AssertionError(f"Unexpected path: {path}")

        with patch("app.base.llm_app_session.transaction_manager._resolve_token_symbol", new=AsyncMock(side_effect=lambda s: czusd if s == "CZUSD" else czb)), \
             patch("app.base.llm_app_session.transaction_manager.call_view_method", new=AsyncMock(side_effect=fake_call_view_method)):
            best_path, best_result = await session._select_best_swap_route(
                contract_address="0xrouter",
                abi=[],
                quote_method="getAmountsOut",
                amount=1,
                token_in=token_in,
                token_out=token_out,
            )

        assert best_path == [token_in, czusd, czb, token_out]
        assert best_result[-1] == 150

    @pytest.mark.asyncio
    async def test_select_best_route_getamountsin_prefers_min_input(self, llm_app_config: Dict[str, Any]) -> None:
        """For getAmountsIn, choose the route with minimum required input."""
        session = LLMAppSession(user_id="123", llm_app_name="swap", llm_app_config=llm_app_config)

        from app.base.llm_app_session import transaction_manager as tm
        czusd = tm.web3.to_checksum_address("0x00000000000000000000000000000000000000A1")
        czb = tm.web3.to_checksum_address("0x00000000000000000000000000000000000000B2")
        token_in = tm.web3.to_checksum_address("0x00000000000000000000000000000000000000C3")
        token_out = tm.web3.to_checksum_address("0x00000000000000000000000000000000000000D4")

        async def fake_call_view_method(_contract: str, _abi: List[Dict[str, Any]], method: str, args: List[Any], status_callback=None):
            assert method == "getAmountsIn"
            amount_out, path = args
            assert amount_out == 100
            if path == [token_in, czusd, token_out]:
                return [12, 100]
            if path == [token_in, czb, token_out]:
                return [10, 100]  # best (min input)
            if path == [token_in, czusd, czb, token_out]:
                return [11, 50, 80, 100]
            if path == [token_in, czb, czusd, token_out]:
                raise ValueError("execution reverted")
            raise AssertionError(f"Unexpected path: {path}")

        with patch("app.base.llm_app_session.transaction_manager._resolve_token_symbol", new=AsyncMock(side_effect=lambda s: czusd if s == "CZUSD" else czb)), \
             patch("app.base.llm_app_session.transaction_manager.call_view_method", new=AsyncMock(side_effect=fake_call_view_method)):
            best_path, best_result = await session._select_best_swap_route(
                contract_address="0xrouter",
                abi=[],
                quote_method="getAmountsIn",
                amount=100,
                token_in=token_in,
                token_out=token_out,
            )

        assert best_path == [token_in, czb, token_out]
        assert best_result[0] == 10


@pytest.mark.integration
@pytest.mark.live
@pytest.mark.asyncio
async def test_getamountsout_route_probing_live() -> None:
    """Live route-probing smoke test against real BSC RPC.

    Requires:
    - RUN_LIVE_TESTS=true
    - DEX_ROUTER_ADDRESS set
    - WETH set
    - OPENAI_API_KEY is NOT required for this test

    This is intentionally a smoke test: it only asserts we can quote without revert.
    """
    if os.getenv("RUN_LIVE_TESTS", "").lower() != "true":
        pytest.skip("Skipping live test (set RUN_LIVE_TESTS=true to run)")

    # Import inside test to avoid import-time env coupling
    from services.transaction import transaction_manager

    router = os.getenv("DEX_ROUTER_ADDRESS")
    if not router:
        pytest.skip("DEX_ROUTER_ADDRESS not set")

    # Load swap config & create session
    repo_root = Path(__file__).parent.parent
    with open(repo_root / "app" / "llm_apps" / "swap" / "config.json", "r") as f:
        swap_cfg = json.load(f)

    session = LLMAppSession(user_id="live", llm_app_name="swap", llm_app_config=swap_cfg)

    # This uses the LLM-app parameter processing (symbol->address) + 4-route probing.
    # Use a small amount in wei directly to avoid decimals ambiguity.
    params = {"amountIn": str(10**15), "path": ["CL8Y", "CZB"]}

    result = await session.handle_view_call("getAmountsOut", params)

    assert isinstance(result, list)
    assert len(result) >= 2
    assert int(result[-1]) > 0
