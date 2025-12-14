#!/usr/bin/env python3
"""
Unit tests for USTC Preregister view result formatting.

These tests validate `commands.llm_app.format_view_result` output for the
`ustc_preregister` LLM app without requiring RPC or database access.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

# Add parent directory to path for imports (keeps consistency with other tests)
sys.path.insert(0, str(Path(__file__).parent.parent))

from commands.llm_app import format_view_result


@pytest.mark.unit
class TestUSTCPreregisterViewFormatting:
    """Unit tests for USTC preregister view formatting."""

    @pytest.mark.asyncio
    async def test_get_total_deposits_formats_with_decimals(self) -> None:
        """getTotalDeposits should format as human USTC-cb with token decimals."""
        session = Mock()
        session.llm_app_name = "ustc_preregister"

        with patch(
            "services.tokens.token_manager.get_token_info",
            new_callable=AsyncMock,
            return_value={"decimals": 6},
        ):
            # 1.234567 USTC-cb with 6 decimals
            result = await format_view_result("getTotalDeposits", 1_234_567, session)

        assert "Total Deposits" in result
        assert "1.234567" in result
        assert "USTC-cb" in result

    @pytest.mark.asyncio
    async def test_get_user_count_formats_with_commas(self) -> None:
        """getUserCount should format as an integer with commas."""
        session = Mock()
        session.llm_app_name = "ustc_preregister"

        result = await format_view_result("getUserCount", 1234567, session)
        assert result == "**Total Users:** 1,234,567"

    @pytest.mark.asyncio
    async def test_get_user_deposit_formats_with_decimals(self) -> None:
        """getUserDeposit should format as human USTC-cb with token decimals."""
        session = Mock()
        session.llm_app_name = "ustc_preregister"

        with patch(
            "services.tokens.token_manager.get_token_info",
            new_callable=AsyncMock,
            return_value={"decimals": 18},
        ):
            # 0.5 USTC-cb with 18 decimals
            result = await format_view_result(
                "getUserDeposit", 500_000_000_000_000_000, session
            )

        assert "Your Deposit" in result
        assert "0.500000" in result
        assert "USTC-cb" in result


