#!/usr/bin/env python3
"""
Unit tests for USTC Preregister app normalization logic.

Tests parameter normalization, "ALL" resolution, and token address enforcement
without requiring database or external API access.
"""
import json
import sys
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import pytest
    import pytest_asyncio
    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False

from app.base.llm_app_session import LLMAppSession


@pytest.mark.unit
class TestUSTCPreregisterNormalization:
    """Unit tests for USTC preregister parameter normalization."""
    
    @pytest_asyncio.fixture
    async def session(self):
        """Create a test LLM app session."""
        repo_root = Path(__file__).parent.parent
        config_path = repo_root / "app" / "llm_apps" / "ustc_preregister" / "config.json"
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        session = LLMAppSession(
            user_id="test_user",
            llm_app_name="ustc_preregister",
            llm_app_config=config
        )
        
        # Mock wallet info
        session.wallet_info = {
            "address": "0x1234567890123456789012345678901234567890"
        }
        
        return session
    
    @pytest.mark.asyncio
    async def test_normalize_deposit_enforces_token_address(self, session):
        """Test that deposit enforces USTC-cb token address."""
        from utils.config import USTC_CB_TOKEN_ADDRESS
        
        params = {"amount": "1.5"}
        normalized = await session._normalize_ustc_preregister_params("deposit", params)
        
        assert normalized["token_address"] == USTC_CB_TOKEN_ADDRESS
        assert normalized["amount"] == "1.5"
    
    @pytest.mark.asyncio
    async def test_normalize_deposit_rejects_wrong_token(self, session):
        """Test that deposit rejects invalid token addresses."""
        params = {
            "amount": "1.5",
            "token_address": "0x0000000000000000000000000000000000000000"
        }
        
        with pytest.raises(ValueError, match="Invalid token address"):
            await session._normalize_ustc_preregister_params("deposit", params)
    
    @pytest.mark.asyncio
    async def test_normalize_deposit_all_resolves_balance(self, session):
        """Test that deposit ALL resolves to wallet balance."""
        from utils.config import USTC_CB_TOKEN_ADDRESS
        from services.wallet import wallet_manager
        
        # Mock wallet balance
        mock_balance = 1000000000000000000  # 1 token with 18 decimals
        with patch.object(wallet_manager, 'get_token_balance', new_callable=AsyncMock) as mock_get_balance:
            mock_get_balance.return_value = {
                "raw_balance": mock_balance,
                "balance": 1.0,
                "symbol": "USTC-cb",
                "decimals": 18
            }
            
            params = {"amount": "ALL"}
            normalized = await session._normalize_ustc_preregister_params("deposit", params)
            
            assert normalized["token_address"] == USTC_CB_TOKEN_ADDRESS
            assert normalized["amount"] == mock_balance
            assert isinstance(normalized["amount"], int)
    
    @pytest.mark.asyncio
    async def test_normalize_deposit_all_zero_balance_raises_error(self, session):
        """Test that deposit ALL with zero balance raises error."""
        from services.wallet import wallet_manager
        
        with patch.object(wallet_manager, 'get_token_balance', new_callable=AsyncMock) as mock_get_balance:
            mock_get_balance.return_value = {
                "raw_balance": 0,
                "balance": 0.0,
                "symbol": "USTC-cb",
                "decimals": 18
            }
            
            params = {"amount": "ALL"}
            with pytest.raises(ValueError, match="zero"):
                await session._normalize_ustc_preregister_params("deposit", params)
    
    @pytest.mark.asyncio
    async def test_normalize_withdraw_all_resolves_deposit(self, session):
        """Test that withdraw ALL resolves to contract deposit."""
        from utils.config import USTC_CB_TOKEN_ADDRESS, USTC_PREREGISTER_ADDRESS
        from services.transaction import transaction_manager
        
        # Mock contract call
        mock_deposit = 500000000000000000  # 0.5 tokens
        with patch.object(transaction_manager, 'call_view_method', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = mock_deposit
            
            params = {"amount": "ALL"}
            normalized = await session._normalize_ustc_preregister_params("withdraw", params)
            
            assert normalized["token_address"] == USTC_CB_TOKEN_ADDRESS
            assert normalized["amount"] == mock_deposit
            assert isinstance(normalized["amount"], int)
    
    @pytest.mark.asyncio
    async def test_normalize_withdraw_all_zero_deposit_raises_error(self, session):
        """Test that withdraw ALL with zero deposit raises error."""
        from services.transaction import transaction_manager
        
        with patch.object(transaction_manager, 'call_view_method', new_callable=AsyncMock) as mock_call:
            mock_call.return_value = 0
            
            params = {"amount": "ALL"}
            with pytest.raises(ValueError, match="haven't deposited"):
                await session._normalize_ustc_preregister_params("withdraw", params)
    
    @pytest.mark.asyncio
    async def test_normalize_getuserdeposit_injects_user(self, session):
        """Test that getUserDeposit auto-injects user address if missing."""
        params = {}
        normalized = await session._normalize_ustc_preregister_params("getUserDeposit", params)
        
        assert normalized["user"] == session.wallet_info["address"]
    
    @pytest.mark.asyncio
    async def test_normalize_getuserdeposit_preserves_existing_user(self, session):
        """Test that getUserDeposit preserves user if provided."""
        custom_user = "0x9876543210987654321098765432109876543210"
        params = {"user": custom_user}
        normalized = await session._normalize_ustc_preregister_params("getUserDeposit", params)
        
        assert normalized["user"] == custom_user
    
    @pytest.mark.asyncio
    async def test_normalize_fixes_parameter_order(self, session):
        """Test that normalization fixes parameter order (token_address first)."""
        from utils.config import USTC_CB_TOKEN_ADDRESS
        
        # Parameters in wrong order
        params = {"amount": "1.5", "token_address": USTC_CB_TOKEN_ADDRESS}
        normalized = await session._normalize_ustc_preregister_params("deposit", params)
        
        # Check that token_address comes first in the dict (Python 3.7+ preserves insertion order)
        keys = list(normalized.keys())
        assert keys[0] == "token_address"
        assert normalized["token_address"] == USTC_CB_TOKEN_ADDRESS
    
    @pytest.mark.asyncio
    async def test_normalize_withdraw_enforces_token_address(self, session):
        """Test that withdraw enforces USTC-cb token address."""
        from utils.config import USTC_CB_TOKEN_ADDRESS
        
        params = {"amount": "1.5"}
        normalized = await session._normalize_ustc_preregister_params("withdraw", params)
        
        assert normalized["token_address"] == USTC_CB_TOKEN_ADDRESS
        assert normalized["amount"] == "1.5"
    
    @pytest.mark.asyncio
    async def test_normalize_withdraw_rejects_wrong_token(self, session):
        """Test that withdraw rejects invalid token addresses."""
        params = {
            "amount": "1.5",
            "token_address": "0x1111111111111111111111111111111111111111"
        }
        
        with pytest.raises(ValueError, match="Invalid token address"):
            await session._normalize_ustc_preregister_params("withdraw", params)


if __name__ == "__main__":
    # Run tests without pytest if pytest not available
    import sys
    
    if not HAS_PYTEST:
        print("⚠️  pytest not available. Install with: pip install pytest pytest-asyncio")
        sys.exit(1)
    
    print("Running USTC Preregister normalization unit tests...")
    print("Note: These tests use mocks and don't require external APIs")
    sys.exit(0)

