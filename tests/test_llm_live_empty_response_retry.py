#!/usr/bin/env python3
"""
Live (real) OpenAI API regression test for the "empty response" bug.

This test intentionally sets an extremely low output token budget to provoke
finish_reason="length" and potentially empty / invalid JSON output, then asserts
that LLMInterface retries and returns a valid, non-empty parsed response.

To run:
  RUN_LIVE_OPENAI_TESTS=1 OPENAI_API_KEY=... pytest -m api -k live_empty_response_retry
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


class _DummySession:
    """Minimal session stub compatible with LLMInterface.process_user_message."""

    def __init__(self, llm_app_name: str, llm_app_config: Dict[str, Any], context: Dict[str, Any]):
        self.llm_app_name = llm_app_name
        self.llm_app_config = llm_app_config
        self.context = context
        self.conversation_history: List[Dict[str, str]] = []

    def add_message(self, role: str, content: str) -> None:
        self.conversation_history.append({"role": role, "content": content})


@pytest.mark.api
@pytest.mark.asyncio
async def test_live_empty_response_retry() -> None:
    """Regression: do not surface 'empty response' when finish_reason=length."""
    if os.getenv("RUN_LIVE_OPENAI_TESTS") != "1":
        pytest.skip("Set RUN_LIVE_OPENAI_TESTS=1 to run live OpenAI tests")
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")

    from app.base.llm_interface import LLMInterface

    project_root = Path(__file__).parent.parent
    swap_config_path = project_root / "app" / "llm_apps" / "swap" / "config.json"
    llm_app_config = json.loads(swap_config_path.read_text())

    session = _DummySession(
        llm_app_name="swap",
        llm_app_config=llm_app_config,
        context={
            "wallet_address": "0x0000000000000000000000000000000000000000",
            "token_balances": [
                {"symbol": "CAKE", "name": "PancakeSwap", "balance": "1.2345", "address": "0xCAKE"},
                {"symbol": "BUSD", "name": "Binance USD", "balance": "12.34", "address": "0xBUSD"},
            ],
            "available_methods": llm_app_config.get("available_methods", {}),
        },
    )

    llm = LLMInterface()

    # Force the first call to be truncated/empty. The retry logic should bump tokens enough
    # to produce a complete JSON response.
    llm.max_tokens = 1

    result = await llm.process_user_message(session, "What's my current balances? Reply briefly.")

    assert isinstance(result, dict)
    assert result.get("error") is None, f"Unexpected error: {result.get('error')}"
    assert result.get("message"), "Expected a non-empty message"
    assert result.get("message") != (
        "The AI service returned an empty response. Please try again. "
        "If this keeps happening, the service may be refusing or failing upstream."
    )


