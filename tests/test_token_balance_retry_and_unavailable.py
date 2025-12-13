"""
Regression tests for token balance fetching behavior.

We must not silently treat transient RPC/contract failures as a real 0 balance.
Instead:
- Retry a few times
- If still failing, surface "unavailable" to formatting / LLM context (not 0)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest


@pytest.mark.asyncio
async def test_get_token_balance_with_options_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the contract call fails once, we retry and return the correct balance."""
    from utils import token_utils

    # Mock w3 address validation/checksum
    w3 = MagicMock()
    w3.is_address.return_value = True
    w3.to_checksum_address.side_effect = lambda x: x

    # Mock contract.balanceOf(...).call() to fail once then succeed
    contract = MagicMock()
    contract.functions.balanceOf.return_value.call.side_effect = [Exception("rpc glitch"), 123]
    w3.eth.contract.return_value = contract

    monkeypatch.setattr(token_utils, "w3", w3)

    bal = await token_utils.get_token_balance_with_options(
        "0x1234567890123456789012345678901234567890",
        "0xABCDEF1234567890ABCDEF1234567890ABCDEF12",
        raise_on_error=True,
        retries=2,
        retry_delay_s=0,
    )
    assert bal == 123


def test_balance_formatter_shows_unavailable_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """commands.balance._format_token_balances should show 'unavailable' when error is set."""
    # Ensure format_token_balance would produce a non-zero string if called
    from utils import token_utils

    monkeypatch.setattr(token_utils, "format_token_balance", lambda raw, dec: "999")

    from commands.balance import _format_token_balances

    token_balances: dict[str, Any] = {
        "0x1234567890123456789012345678901234567890": {
            "symbol": "CZB",
            "name": "CZBlue",
            "raw_balance": 12300000000000000000000,
            "decimals": 18,
            "error": "unavailable",
        }
    }

    lines = _format_token_balances(token_balances)
    assert len(lines) == 1
    assert "CZB" in lines[0]
    assert "unavailable" in lines[0].lower()


@pytest.mark.asyncio
async def test_llm_context_uses_unavailable_on_error() -> None:
    """LLMAppSession context should carry 'unavailable' instead of a fake 0."""
    from app.base.llm_app_session import LLMAppSession

    session = LLMAppSession(
        user_id="123",
        llm_app_name="swap",
        llm_app_config={
            "name": "swap",
            "description": "Test swap app",
            "available_methods": {"view": [], "write": []},
        },
    )

    # Inject a token balance with an error (simulating failed RPC fetch)
    session.wallet_info = {"address": "0x1234567890123456789012345678901234567890"}
    session.active_wallet_name = "Old"
    session.tracked_tokens = []
    session.token_balances = {
        "0xABCDEF1234567890ABCDEF1234567890ABCDEF12": {
            "symbol": "CZB",
            "name": "CZBlue",
            "balance": 0.0,
            "raw_balance": 0,
            "decimals": 18,
            "error": "unavailable",
        }
    }

    ctx = await session._build_llm_context()
    assert ctx["token_balances"][0]["symbol"] == "CZB"
    assert str(ctx["token_balances"][0]["balance"]).lower() == "unavailable"


