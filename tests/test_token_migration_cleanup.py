"""
Unit tests for token migration cleanup functionality.

Tests the cleanup of old token addresses when tokens migrate
to new addresses and appear in the default token list.
"""
import pytest
import sys
from unittest.mock import MagicMock, patch, call, AsyncMock
from typing import Dict, Any, List

# Valid test addresses
NEW_CL8Y_ADDRESS = "0x0000000000000000000000000000000000000001"
OLD_CL8Y_ADDRESS = "0x0000000000000000000000000000000000000002"
SAME_CL8Y_ADDRESS = "0x0000000000000000000000000000000000000003"


class TestTokenMigrationCleanup:
    """Test token migration cleanup logic."""
    
    @pytest.mark.asyncio
    async def test_cleanup_untracks_old_token_when_symbol_in_default_list(self) -> None:
        """
        Test that cleanup untracks old token addresses when symbol appears in default list.
        """
        from services.tokens.TokenManager import TokenManager
        
        # Get the actual module object
        tm_module = sys.modules['services.tokens.TokenManager']
        
        # Setup: Default token list has CL8Y at new address
        default_tokens = {
            NEW_CL8Y_ADDRESS: {
                "symbol": "CL8Y",
                "name": "CeramicLiberty.com",
                "decimals": 18
            }
        }
        
        # User has tracked old CL8Y address
        mock_tracked_tokens = [
            {
                "user_id": "hashed_user_123",
                "token_address": OLD_CL8Y_ADDRESS,
                "symbol": "CL8Y",
                "chain_id": 56
            }
        ]
        
        token_manager = TokenManager()
        token_manager._untrack_by_hashed_user_id = MagicMock(return_value=True)
        
        # Patch the db function at the module level
        original_func = tm_module.get_all_tracked_tokens_by_symbol
        tm_module.get_all_tracked_tokens_by_symbol = MagicMock(return_value=mock_tracked_tokens)
        
        try:
            await token_manager._cleanup_token_migrations(default_tokens)
            
            # Should have called untrack for the old address
            token_manager._untrack_by_hashed_user_id.assert_called_once()
            call_args = token_manager._untrack_by_hashed_user_id.call_args
            assert call_args[0][0] == "hashed_user_123"
            assert call_args[0][1].lower() == OLD_CL8Y_ADDRESS.lower()
            assert call_args[0][2] == 56
        finally:
            tm_module.get_all_tracked_tokens_by_symbol = original_func
    
    @pytest.mark.asyncio
    async def test_cleanup_does_not_untrack_same_address(self) -> None:
        """
        Test that cleanup does not untrack tokens with the same address as default list.
        """
        from services.tokens.TokenManager import TokenManager
        
        tm_module = sys.modules['services.tokens.TokenManager']
        
        # Setup: Default token list and tracked token have same address
        default_tokens = {
            SAME_CL8Y_ADDRESS: {
                "symbol": "CL8Y",
                "name": "CeramicLiberty.com",
                "decimals": 18
            }
        }
        
        mock_tracked_tokens = [
            {
                "user_id": "hashed_user_123",
                "token_address": SAME_CL8Y_ADDRESS,  # Same address
                "symbol": "CL8Y",
                "chain_id": 56
            }
        ]
        
        token_manager = TokenManager()
        token_manager._untrack_by_hashed_user_id = MagicMock(return_value=True)
        
        original_func = tm_module.get_all_tracked_tokens_by_symbol
        tm_module.get_all_tracked_tokens_by_symbol = MagicMock(return_value=mock_tracked_tokens)
        
        try:
            await token_manager._cleanup_token_migrations(default_tokens)
            
            # Should not have called untrack since addresses match
            token_manager._untrack_by_hashed_user_id.assert_not_called()
        finally:
            tm_module.get_all_tracked_tokens_by_symbol = original_func
    
    @pytest.mark.asyncio
    async def test_cleanup_handles_multiple_users_with_same_old_token(self) -> None:
        """
        Test that cleanup handles multiple users tracking the same old token.
        """
        from services.tokens.TokenManager import TokenManager
        
        tm_module = sys.modules['services.tokens.TokenManager']
        
        default_tokens = {
            NEW_CL8Y_ADDRESS: {
                "symbol": "CL8Y",
                "name": "CeramicLiberty.com",
                "decimals": 18
            }
        }
        
        # Multiple users have tracked old address
        mock_tracked_tokens = [
            {
                "user_id": "hashed_user_1",
                "token_address": OLD_CL8Y_ADDRESS,
                "symbol": "CL8Y",
                "chain_id": 56
            },
            {
                "user_id": "hashed_user_2",
                "token_address": OLD_CL8Y_ADDRESS,
                "symbol": "CL8Y",
                "chain_id": 56
            }
        ]
        
        token_manager = TokenManager()
        token_manager._untrack_by_hashed_user_id = MagicMock(return_value=True)
        
        original_func = tm_module.get_all_tracked_tokens_by_symbol
        tm_module.get_all_tracked_tokens_by_symbol = MagicMock(return_value=mock_tracked_tokens)
        
        try:
            await token_manager._cleanup_token_migrations(default_tokens)
            
            # Should untrack for both users
            assert token_manager._untrack_by_hashed_user_id.call_count == 2
        finally:
            tm_module.get_all_tracked_tokens_by_symbol = original_func
    
    @pytest.mark.asyncio
    async def test_cleanup_handles_errors_gracefully(self) -> None:
        """
        Test that cleanup handles errors gracefully and doesn't crash.
        """
        from services.tokens.TokenManager import TokenManager
        
        tm_module = sys.modules['services.tokens.TokenManager']
        
        default_tokens = {
            NEW_CL8Y_ADDRESS: {
                "symbol": "CL8Y",
                "name": "CeramicLiberty.com",
                "decimals": 18
            }
        }
        
        mock_tracked_tokens = [
            {
                "user_id": "hashed_user_123",
                "token_address": OLD_CL8Y_ADDRESS,
                "symbol": "CL8Y",
                "chain_id": 56
            }
        ]
        
        token_manager = TokenManager()
        token_manager._untrack_by_hashed_user_id = MagicMock(side_effect=Exception("Database error"))
        
        original_func = tm_module.get_all_tracked_tokens_by_symbol
        tm_module.get_all_tracked_tokens_by_symbol = MagicMock(return_value=mock_tracked_tokens)
        
        try:
            # Should not raise exception
            await token_manager._cleanup_token_migrations(default_tokens)
            
            # Should have attempted untrack despite error
            token_manager._untrack_by_hashed_user_id.assert_called_once()
        finally:
            tm_module.get_all_tracked_tokens_by_symbol = original_func


class TestCleanupMigratedTokensPublicAPI:
    """Test the public cleanup_migrated_tokens API."""
    
    @pytest.mark.asyncio
    async def test_cleanup_migrated_tokens_parses_token_list_if_empty(self) -> None:
        """
        Test that cleanup_migrated_tokens parses token list if not already parsed.
        """
        from services.tokens.TokenManager import TokenManager
        
        token_manager = TokenManager()
        token_manager.default_tokens = {}  # Empty
        
        # Mock the private methods
        async def mock_parse() -> dict:
            token_manager.default_tokens = {
                "0x0000000000000000000000000000000000000001": {
                    "symbol": "TEST", 
                    "name": "Test", 
                    "decimals": 18
                }
            }
            return token_manager.default_tokens
        
        token_manager._parse_default_token_list = mock_parse
        token_manager._cleanup_token_migrations = AsyncMock()
        
        await token_manager.cleanup_migrated_tokens()
        
        # Should have called cleanup with the parsed tokens
        token_manager._cleanup_token_migrations.assert_called_once()
