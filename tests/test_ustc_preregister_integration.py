#!/usr/bin/env python3
"""
Integration tests for USTC Preregister LLM app with live RPC and OpenAI API.

These tests make real API calls to:
- BSC RPC (for contract view calls)
- OpenAI API (for LLM processing)

Environment variables are loaded from .env file in the project root.
You can also set them via environment variables:
  RUN_LIVE_TESTS=true RUN_LIVE_OPENAI_TESTS=1 pytest tests/test_ustc_preregister_integration.py -v -s
"""
import json
import os
import sys
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables from .env file in project root
project_root = Path(__file__).parent.parent
env_path = project_root / ".env"
load_dotenv(dotenv_path=env_path)

try:
    import pytest
    import pytest_asyncio
    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False


@pytest.mark.integration
@pytest.mark.live
@pytest.mark.asyncio
class TestUSTCPreregisterLiveRPC:
    """Live RPC integration tests for USTC Preregister app."""
    
    @pytest_asyncio.fixture
    async def session(self):
        """Create a test LLM app session with real config."""
        # Ensure dotenv is loaded (in case called directly)
        load_dotenv(dotenv_path=project_root / ".env")
        
        if os.getenv("RUN_LIVE_TESTS", "").lower() != "true":
            pytest.skip("Set RUN_LIVE_TESTS=true in .env file or environment to run live RPC tests")
        
        repo_root = Path(__file__).parent.parent
        config_path = repo_root / "app" / "llm_apps" / "ustc_preregister" / "config.json"
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        from app.base.llm_app_session import LLMAppSession
        
        session = LLMAppSession(
            user_id="live_test",
            llm_app_name="ustc_preregister",
            llm_app_config=config
        )
        
        # Use a test wallet address (doesn't need to be real)
        session.wallet_info = {
            "address": "0x1234567890123456789012345678901234567890"
        }
        
        return session
    
    @pytest.mark.asyncio
    async def test_get_total_deposits_live(self, session):
        """Test getTotalDeposits view call against live RPC."""
        result = await session.handle_view_call("getTotalDeposits", {})
        
        assert isinstance(result, (int, str))
        # Convert to int if needed
        total = int(result) if isinstance(result, str) else result
        assert total >= 0
    
    @pytest.mark.asyncio
    async def test_get_user_count_live(self, session):
        """Test getUserCount view call against live RPC."""
        result = await session.handle_view_call("getUserCount", {})
        
        assert isinstance(result, (int, str))
        count = int(result) if isinstance(result, str) else result
        assert count >= 0
    
    @pytest.mark.asyncio
    async def test_get_user_deposit_live(self, session):
        """Test getUserDeposit view call against live RPC."""
        # Use a known address (could be zero address or any address)
        test_address = "0x0000000000000000000000000000000000000000"
        result = await session.handle_view_call("getUserDeposit", {"user": test_address})
        
        assert isinstance(result, (int, str))
        deposit = int(result) if isinstance(result, str) else result
        assert deposit >= 0
    
    @pytest.mark.asyncio
    async def test_get_user_deposit_auto_inject_user(self, session):
        """Test getUserDeposit auto-injects user address."""
        # Don't provide user - should auto-inject
        result = await session.handle_view_call("getUserDeposit", {})
        
        assert isinstance(result, (int, str))
        deposit = int(result) if isinstance(result, str) else result
        assert deposit >= 0
    
    @pytest.mark.asyncio
    async def test_normalize_deposit_all_live(self, session):
        """Test deposit ALL normalization with live RPC."""
        from utils.config import USTC_CB_TOKEN_ADDRESS
        
        # This will call live RPC to get balance
        params = {"amount": "ALL"}
        normalized = await session._normalize_ustc_preregister_params("deposit", params)
        
        assert normalized["token_address"] == USTC_CB_TOKEN_ADDRESS
        assert "amount" in normalized
        # Amount should be an int (raw balance)
        assert isinstance(normalized["amount"], int)
        assert normalized["amount"] >= 0
    
    @pytest.mark.asyncio
    async def test_normalize_withdraw_all_live(self, session):
        """Test withdraw ALL normalization with live RPC."""
        from utils.config import USTC_CB_TOKEN_ADDRESS
        
        # This will call live RPC to get deposit
        params = {"amount": "ALL"}
        try:
            normalized = await session._normalize_ustc_preregister_params("withdraw", params)
            
            assert normalized["token_address"] == USTC_CB_TOKEN_ADDRESS
            assert "amount" in normalized
            # Amount should be an int (raw deposit)
            assert isinstance(normalized["amount"], int)
            assert normalized["amount"] >= 0
        except ValueError as e:
            # If user has zero deposit, that's expected
            if "haven't deposited" in str(e):
                pytest.skip(f"Test wallet has zero deposit: {e}")
            raise


@pytest.mark.integration
@pytest.mark.api
@pytest.mark.live
@pytest.mark.asyncio
class TestUSTCPreregisterLiveLLM:
    """Live OpenAI API integration tests for USTC Preregister app."""
    
    @pytest_asyncio.fixture
    async def session(self):
        """Create a test LLM app session."""
        # Ensure dotenv is loaded (in case called directly)
        load_dotenv(dotenv_path=project_root / ".env")
        
        if os.getenv("RUN_LIVE_OPENAI_TESTS") != "1":
            pytest.skip("Set RUN_LIVE_OPENAI_TESTS=1 in .env file or environment to run live OpenAI tests")
        
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set in .env file or environment")
        
        repo_root = Path(__file__).parent.parent
        config_path = repo_root / "app" / "llm_apps" / "ustc_preregister" / "config.json"
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        from app.base.llm_app_session import LLMAppSession
        
        session = LLMAppSession(
            user_id="live_test",
            llm_app_name="ustc_preregister",
            llm_app_config=config
        )
        
        # Initialize context
        session.wallet_info = {
            "address": "0x1234567890123456789012345678901234567890"
        }
        session.active_wallet_name = "test_wallet"
        session.context = {
            "app_name": "ustc_preregister",
            "app_description": config["description"],
            "wallet_name": "test_wallet",
            "wallet_address": session.wallet_info["address"],
            "token_balances": [
                {
                    "symbol": "USTC-cb",
                    "name": "USTC-cb",
                    "balance": "10.5",
                    "address": "0xA4224f910102490Dc02AAbcBc6cb3c59Ff390055"
                }
            ],
            "available_methods": config["available_methods"]
        }
        session.conversation_history = []
        
        return session
    
    @pytest.mark.asyncio
    async def test_llm_chat_response(self, session):
        """Test LLM responds to general chat."""
        from app.base.llm_interface import get_llm_interface
        
        llm = get_llm_interface()
        result = await llm.process_user_message(session, "Hello, what can you help me with?")
        
        assert result["response_type"] in ["chat", "view_call", "write_call"]
        assert "message" in result
        assert len(result["message"]) > 0
    
    @pytest.mark.asyncio
    async def test_llm_view_call_global_stats(self, session):
        """Test LLM generates view_call for global stats request."""
        from app.base.llm_interface import get_llm_interface
        
        llm = get_llm_interface()
        result = await llm.process_user_message(
            session,
            "Show me the global stats. How many users have deposited?"
        )
        
        assert result["response_type"] == "view_call"
        assert "contract_call" in result
        assert result["contract_call"]["method"] in ["getTotalDeposits", "getUserCount"]
        assert "parameters" in result["contract_call"]
    
    @pytest.mark.asyncio
    async def test_llm_view_call_user_deposit(self, session):
        """Test LLM generates view_call for user deposit query."""
        from app.base.llm_interface import get_llm_interface
        
        llm = get_llm_interface()
        result = await llm.process_user_message(
            session,
            "How much USTC-cb have I deposited?"
        )
        
        assert result["response_type"] == "view_call"
        assert "contract_call" in result
        assert result["contract_call"]["method"] == "getUserDeposit"
        assert "parameters" in result["contract_call"]
    
    @pytest.mark.asyncio
    async def test_llm_write_call_deposit(self, session):
        """Test LLM generates write_call for deposit request."""
        from app.base.llm_interface import get_llm_interface
        
        llm = get_llm_interface()
        result = await llm.process_user_message(
            session,
            "I want to deposit 1.5 USTC-cb"
        )
        
        assert result["response_type"] == "write_call"
        assert "contract_call" in result
        assert result["contract_call"]["method"] == "deposit"
        assert "parameters" in result["contract_call"]
        assert "amount" in result["contract_call"]["parameters"]
    
    @pytest.mark.asyncio
    async def test_llm_write_call_deposit_all(self, session):
        """Test LLM generates write_call for deposit ALL request."""
        from app.base.llm_interface import get_llm_interface
        
        llm = get_llm_interface()
        result = await llm.process_user_message(
            session,
            "Deposit all my USTC-cb"
        )
        
        assert result["response_type"] == "write_call"
        assert "contract_call" in result
        assert result["contract_call"]["method"] == "deposit"
        assert "parameters" in result["contract_call"]
        # LLM should include "ALL" or the system will normalize it
        amount = result["contract_call"]["parameters"].get("amount")
        assert amount is not None
    
    @pytest.mark.asyncio
    async def test_llm_write_call_withdraw(self, session):
        """Test LLM generates write_call for withdraw request."""
        from app.base.llm_interface import get_llm_interface
        
        llm = get_llm_interface()
        result = await llm.process_user_message(
            session,
            "Withdraw 0.5 USTC-cb from my deposit"
        )
        
        assert result["response_type"] == "write_call"
        assert "contract_call" in result
        assert result["contract_call"]["method"] == "withdraw"
        assert "parameters" in result["contract_call"]
        assert "amount" in result["contract_call"]["parameters"]


@pytest.mark.integration
@pytest.mark.live
@pytest.mark.asyncio
class TestUSTCPreregisterEndToEnd:
    """End-to-end integration tests combining RPC and LLM."""
    
    @pytest.mark.asyncio
    async def test_full_view_call_flow(self):
        """Test full flow: LLM request -> view call -> formatted result."""
        # Ensure dotenv is loaded (in case called directly)
        load_dotenv(dotenv_path=project_root / ".env")
        
        if os.getenv("RUN_LIVE_TESTS", "").lower() != "true":
            pytest.skip("Set RUN_LIVE_TESTS=true in .env file or environment to run live tests")
        
        if os.getenv("RUN_LIVE_OPENAI_TESTS") != "1":
            pytest.skip("Set RUN_LIVE_OPENAI_TESTS=1 in .env file or environment to run live OpenAI tests")
        
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set in .env file or environment")
        
        repo_root = Path(__file__).parent.parent
        config_path = repo_root / "app" / "llm_apps" / "ustc_preregister" / "config.json"
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        from app.base.llm_app_session import LLMAppSession
        from app.base.llm_interface import get_llm_interface
        from commands.llm_app import format_view_result
        
        session = LLMAppSession(
            user_id="e2e_test",
            llm_app_name="ustc_preregister",
            llm_app_config=config
        )
        
        session.wallet_info = {
            "address": "0x1234567890123456789012345678901234567890"
        }
        session.active_wallet_name = "test_wallet"
        session.context = {
            "app_name": "ustc_preregister",
            "wallet_address": session.wallet_info["address"],
            "token_balances": [],
            "available_methods": config["available_methods"]
        }
        
        # Step 1: LLM processes request
        llm = get_llm_interface()
        llm_result = await llm.process_user_message(
            session,
            "What is the total amount deposited?"
        )
        
        # Step 2: Execute view call if LLM returned one
        if llm_result["response_type"] == "view_call":
            method = llm_result["contract_call"]["method"]
            params = llm_result["contract_call"]["parameters"]
            
            # Step 3: Execute view call
            result = await session.handle_view_call(method, params)
            
            # Step 4: Format result
            formatted = await format_view_result(method, result, session)
            
            assert len(formatted) > 0
            assert "Total Deposits" in formatted or "USTC-cb" in formatted


if __name__ == "__main__":
    if not HAS_PYTEST:
        print("⚠️  pytest not available. Install with: pip install pytest pytest-asyncio")
        sys.exit(1)
    
    print("Running USTC Preregister integration tests...")
    print("Note: These tests require:")
    print("  - RUN_LIVE_TESTS=true for RPC tests")
    print("  - RUN_LIVE_OPENAI_TESTS=1 and OPENAI_API_KEY for LLM tests")
    sys.exit(0)

