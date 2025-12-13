"""
Token management service for tracking and monitoring ERC20 tokens.
"""
import logging
import os
import json
import httpx
import asyncio
from typing import Dict, List, Optional, Any, TypedDict, cast, Union, Awaitable, Callable
from web3.contract import Contract
from web3.exceptions import ContractLogicError
from web3.types import Address, ChecksumAddress, ENS # type: ignore[attr-defined]
from db.tokens import (
    track_token,
    untrack_token,
    get_tracked_tokens as db_get_tracked_tokens,
    is_token_tracked,
    get_token_by_address,
    get_all_tracked_tokens_by_symbol
)
from db.connection import execute_query
from db.track import get_token_balance_history as db_get_token_balance_history
from services.wallet import wallet_manager
from services.pin import pin_manager
from db.utils import hash_user_id
from utils.token_utils import (
    TokenBalanceFetchError,
    format_token_balance,
    get_token_balance_with_options,
    get_token_info,
)
from utils.web3_connection import w3

logger = logging.getLogger(__name__)

class TokenDetails(TypedDict):
    """Type definition for token details."""
    symbol: str
    name: str
    decimals: int

class TokenBalance(TypedDict):
    """Type definition for token balance information."""
    symbol: str
    name: str
    balance: float
    raw_balance: int
    decimals: int
    error: Optional[str]

class TokenBalanceHistory(TypedDict):
    """Type definition for token balance history entry."""
    balance: str
    balance_usd: Optional[float]
    timestamp: int

class TokenInfo(TypedDict):
    """Type definition for token information."""
    token_address: str
    symbol: str
    name: str
    decimals: int
    chain_id: int

class TokenManager:
    """Service for managing ERC20 token tracking and balance monitoring."""
    
    # BLACKLISTED TOKENS - Add deprecated/problematic token addresses here
    # Format: ["0xTokenAddress1", "0xTokenAddress2", ...]
    BLACKLISTED_TOKENS = [
        # Deprecated CL8Y token (security incident at p2b exchange)
        "0x999311589cc1ed0065ad9ed9702cb593ffc62ddf",
    ]
    
    def __init__(self) -> None:
        """Initialize the TokenManager.
        """
            
        self.web3 = w3
        self.default_tokens: Dict[ChecksumAddress, TokenDetails] = {}
        
        # Load ERC20 ABI from file
        try:
            with open('ABI/ERC20.json', 'r') as f:
                self.erc20_abi = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load ERC20 ABI: {str(e)}")
            raise RuntimeError("Failed to load ERC20 ABI") from e

    def _get_user_pin(self, user_id: str) -> Optional[str]:
        """Get the PIN for a user if they have one set.
        
        Args:
            user_id: The user ID to get the PIN for
            
        Returns:
            Optional[str]: The user's PIN if they have one set, None otherwise
        """
        try:
            # Convert user_id to int for pin_manager
            user_id_int = int(user_id)
            return pin_manager.get_pin(user_id_int)
        except (ValueError, TypeError) as e:
            logger.error(f"Failed to get PIN for user {hash_user_id(user_id)}: {str(e)}")
            return None

    async def get_tracked_tokens(self, user_id: str, chain_id: int = 56) -> List[TokenInfo]:
        """Get all tracked tokens for a specific user.
        
        Args:
            user_id: ID of the user to get tracked tokens for
            chain_id: Chain ID to filter tokens by (default: 56 for BSC)
            
        Returns:
            List[TokenInfo]: List of tracked token information
        """
        try:
            tokens = db_get_tracked_tokens(user_id)
            return [
                TokenInfo(
                    token_address=token["token_address"],
                    symbol=token["symbol"] or "UNKNOWN",
                    name=token["name"] or "Unknown Token",
                    decimals=token["decimals"] or 18,
                    chain_id=chain_id
                )
                for token in tokens
            ]
        except Exception as e:
            logger.error(f"Failed to get tracked tokens for user {hash_user_id(user_id)}: {str(e)}")
            return []

    async def _parse_default_token_list(self) -> Dict[ChecksumAddress, TokenDetails]:
        """Fetch and parse the DEFAULT_TOKEN_LIST from a remote URL.
        
        Expected format: JSON file with tokens array containing token objects
        Each token object should have: address, symbol, name, decimals
        
        Returns:
            Dict[ChecksumAddress, TokenDetails]: Dictionary mapping token addresses to their details
        """
        logger.info("Parsing default token list")
        default_tokens: Dict[ChecksumAddress, TokenDetails] = {}
        token_list_url = os.getenv("DEFAULT_TOKEN_LIST", "")
        
        if not token_list_url:
            logger.warning("DEFAULT_TOKEN_LIST environment variable not set")
            return default_tokens
            
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(token_list_url)
                response.raise_for_status()
                token_list = response.json()
            if not isinstance(token_list, dict) or 'tokens' not in token_list:
                logger.error("Invalid token list format: missing 'tokens' array")
                return default_tokens
                
            for token in token_list['tokens']:
                try:
                    address = w3.to_checksum_address(token['address'])
                    default_tokens[address] = TokenDetails(
                        symbol=token['symbol'],
                        name=token['name'],
                        decimals=int(token['decimals'])
                    )
                except (KeyError, ValueError) as e:
                    logger.warning(f"Invalid token format in token list: {token}. Error: {str(e)}")
                    continue
                    
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            logger.error(f"Failed to fetch or parse token list from {token_list_url}: {str(e)}")
            
        logger.info(f"Successfully parsed {len(default_tokens)} tokens from default token list")
        self.default_tokens = default_tokens
        
        return default_tokens
    
    async def cleanup_migrated_tokens(self) -> None:
        """Explicitly clean up migrated tokens for all users.
        
        This should be called explicitly when token migrations are known to have occurred,
        not automatically on every token list parse. The cleanup untracks old token addresses
        when a symbol appears in the default token list at a different address.
        
        Warning: This affects ALL users who have tracked tokens with symbols that appear
        in the default token list. Only call this when you know tokens have migrated.
        """
        if not self.default_tokens:
            await self._parse_default_token_list()
        await self._cleanup_token_migrations(self.default_tokens)
    
    async def _cleanup_token_migrations(self, default_tokens: Dict[ChecksumAddress, TokenDetails]) -> None:
        """Clean up token migrations: untrack old tokens when symbol appears in default list.
        
        When tokens migrate to new addresses (e.g., CL8Y), users may have tracked the old address.
        If the symbol appears in the default token list, we assume that's the "current" token and
        should untrack any user-tracked tokens with the same symbol but different addresses.
        
        Args:
            default_tokens: Dictionary of tokens from default token list
        """
        try:
            # Build a map of symbol -> address from default token list
            default_symbol_to_address: Dict[str, ChecksumAddress] = {}
            for address, details in default_tokens.items():
                symbol_upper = details['symbol'].upper()
                # If multiple tokens with same symbol in default list, keep the first one
                # (this shouldn't happen often, but handle it gracefully)
                if symbol_upper not in default_symbol_to_address:
                    default_symbol_to_address[symbol_upper] = address
            
            # For each symbol in default list, check for tracked tokens with different addresses
            for symbol_upper, default_address in default_symbol_to_address.items():
                # Get all tracked tokens with this symbol (across all users)
                tracked_tokens = get_all_tracked_tokens_by_symbol(symbol_upper)
                
                for tracked_token in tracked_tokens:
                    tracked_address = w3.to_checksum_address(tracked_token['token_address'])
                    
                    # If tracked address is different from default address, untrack it
                    if tracked_address.lower() != default_address.lower():
                        hashed_user_id = tracked_token.get('user_id')
                        if hashed_user_id:
                            # user_id from database is already hashed, use internal sync method
                            logger.info(
                                f"Token migration detected: symbol '{symbol_upper}' has migrated. "
                                f"Untracking old address {tracked_address} for user {hashed_user_id[:16]}.... "
                                f"New address: {default_address}"
                            )
                            try:
                                self._untrack_by_hashed_user_id(
                                    hashed_user_id, 
                                    tracked_address, 
                                    tracked_token.get('chain_id', 56)
                                )
                            except Exception as e:
                                logger.error(
                                    f"Failed to untrack migrated token {tracked_address} "
                                    f"for user {hashed_user_id[:16]}...: {str(e)}"
                                )
        except Exception as e:
            logger.error(f"Failed to cleanup token migrations: {str(e)}")
            # Don't raise - this is a cleanup operation, shouldn't block other functionality

    async def track(self, user_id: str, token_address: str, chain_id: int = 56) -> bool:
        """Track a new ERC20 token for a specific user.
        
        Args:
            user_id: ID of the user to track the token for
            token_address: Address of the ERC20 token to track
            chain_id: Chain ID where the token exists (default: 56 for BSC)
            
        Returns:
            bool: True if token was successfully tracked, False otherwise
        """
        try:
            token_address = w3.to_checksum_address(token_address)
            
            # Check if token is blacklisted
            if str(token_address).lower() in [addr.lower() for addr in self.BLACKLISTED_TOKENS]:
                logger.warning(f"Attempted to track blacklisted token {token_address} for user {hash_user_id(user_id)}")
                return False
            
            if is_token_tracked(user_id, token_address, chain_id):
                logger.info(f"Token {token_address} is already being tracked for user {hash_user_id(user_id)}")
                return True

            logger.info(f"checking if token is in DEFAULT_TOKEN_LIST")
            if token_address in self.default_tokens:
                token_details = self.default_tokens[token_address]
                symbol = token_details["symbol"]
                name = token_details["name"]
                decimals = token_details["decimals"]
            else:
                logger.info(f"Token {token_address} is not in DEFAULT_TOKEN_LIST")
                # Get token details from contract if not in DEFAULT_TOKEN_LIST
                token_info = await get_token_info(token_address)
                if token_info:
                    symbol = token_info["symbol"]
                    name = token_info["name"]
                    decimals = token_info["decimals"]
                else:
                    logger.error(f"Failed to get token info for {token_address}")
                    return False
            
            track_token(user_id, token_address, chain_id, symbol, name, decimals)
            logger.info(f"Successfully started tracking token {symbol} ({token_address}) for user {hash_user_id(user_id)}")
            return True
            
        except (ContractLogicError, ValueError) as e:
            logger.error(f"Failed to track token {token_address} for user {hash_user_id(user_id)}: {str(e)}")
            return False

    async def untrack(self, user_id: str, token_address: str, chain_id: int = 56) -> bool:
        """Stop tracking an ERC20 token for a specific user.
        
        Args:
            user_id: ID of the user to untrack the token for (will be hashed)
            token_address: Address of the ERC20 token to untrack
            chain_id: Chain ID where the token exists (default: 56 for BSC)
            
        Returns:
            bool: True if token was successfully untracked, False otherwise
        """
        try:
            token_address = w3.to_checksum_address(token_address)
            # untrack_token is a sync function
            untrack_token(user_id, token_address, chain_id)
            logger.info(f"Stopped tracking token {token_address} for user {hash_user_id(user_id)}")
            return True
        except Exception as e:
            logger.error(f"Failed to untrack token {token_address} for user {hash_user_id(user_id)}: {str(e)}")
            return False
    
    def _untrack_by_hashed_user_id(self, hashed_user_id: str, token_address: str, chain_id: int = 56) -> bool:
        """Stop tracking an ERC20 token for a user identified by hashed user_id.
        
        Internal method for cleanup operations where we already have the hashed user_id
        from database queries. This is a sync method since it uses sync database operations.
        
        Args:
            hashed_user_id: Already-hashed user ID from database
            token_address: Address of the ERC20 token to untrack
            chain_id: Chain ID where the token exists (default: 56 for BSC)
            
        Returns:
            bool: True if token was successfully untracked, False otherwise
        """
        try:
            token_address = w3.to_checksum_address(token_address)
            # Get the token_id
            get_token_id_query = "SELECT id FROM tokens WHERE token_address = %s AND chain_id = %s"
            token_result = execute_query(get_token_id_query, (token_address, chain_id), fetch='one')
            if not token_result:
                logger.warning(f"Token {token_address} not found, cannot untrack")
                return False
            token_id = token_result['id']
            
            # Remove from user_tracked_tokens using hashed user_id directly
            untrack_query = "DELETE FROM user_tracked_tokens WHERE user_id = %s AND token_id = %s"
            execute_query(untrack_query, (hashed_user_id, token_id))
            logger.info(f"Stopped tracking token {token_address} for hashed user {hashed_user_id[:16]}...")
            return True
        except Exception as e:
            logger.error(f"Failed to untrack token {token_address} for hashed user {hashed_user_id[:16]}...: {str(e)}")
            return False

    async def scan(self, user_id: str, chain_id: int = 56, status_callback: Optional[Callable[[str], Awaitable[None]]] = None) -> List[ChecksumAddress]:
        """Scan default token list and track tokens with non-zero balance for a specific user.
        
        Args:
            user_id: ID of the user to scan tokens for
            chain_id: Chain ID to scan tokens on (default: 56 for BSC)
            status_callback: Optional async callback function to report scanning progress
            
        Returns:
            List[ChecksumAddress]: List of token addresses that were newly tracked
        """
        newly_tracked: List[ChecksumAddress] = []
        
        # Get active wallet for user
        wallet_name = wallet_manager.get_active_wallet_name(user_id)
        if not wallet_name:
            logger.error(f"No active wallet found for user {hash_user_id(user_id)}")
            return newly_tracked
            
        # Get user's PIN
        pin = self._get_user_pin(user_id)
        if not pin and pin_manager.needs_pin(int(user_id)):
            logger.error(f"PIN required but not available for user {hash_user_id(user_id)}")
            return newly_tracked
            
        wallet = wallet_manager.get_wallet_by_name(user_id, wallet_name, pin)
        if not wallet:
            logger.error(f"Wallet {wallet_name} not found for user {hash_user_id(user_id)}")
            return newly_tracked
        
        wallet_address = wallet['address']

        # update the default token list
        await self._parse_default_token_list()
        
        logger.info(f"Starting to scan {len(self.default_tokens)} tokens from default list")
        
        for token_address in self.default_tokens:
            # Skip blacklisted tokens
            if str(token_address).lower() in [addr.lower() for addr in self.BLACKLISTED_TOKENS]:
                logger.info(f"Skipping blacklisted token {token_address}")
                continue
                
            isTokenTracked: bool = is_token_tracked(user_id, str(token_address), chain_id)
            try:
                if isTokenTracked:
                    continue
                    
                # Get token details for status updates
                token_info = await self.get_token_info(str(token_address))
                if not token_info:
                    logger.warning(f"Could not get token info for {token_address}")
                    continue
                    
                # Run balance check and status update concurrently
                if status_callback:
                    balance, _ = await asyncio.gather(
                        get_token_balance(wallet_address, token_address),
                        status_callback(f"Scanning {token_info['symbol']}...")
                    )
                else:
                    balance = await get_token_balance(wallet_address, token_address)
                
                # Calculate human-readable balance
                decimals = token_info['decimals']
                human_balance = balance / (10 ** decimals)
                
                if balance > 0:
                    if status_callback:
                        # Run tracking and status update concurrently
                        tracking_success, _ = await asyncio.gather(
                            self.track(user_id, str(token_address), chain_id),
                            status_callback(f"{token_info['symbol']} Balance: {human_balance}\nTracking...")
                        )
                        if tracking_success:
                            newly_tracked.append(token_address)
                        else:
                            logger.error(f"Failed to track token {token_address} for user {hash_user_id(user_id)}")
                    else:
                        if await self.track(user_id, str(token_address), chain_id):
                            newly_tracked.append(token_address)
                        else:
                            logger.error(f"Failed to track token {token_address} for user {hash_user_id(user_id)}")
                        
            except Exception as e:
                logger.error(f"Failed to scan token {token_address} for user {hash_user_id(user_id)}: {str(e)}")
                continue
        
        logger.info(f"Scan completed: processed {len(self.default_tokens)} tokens, newly tracked: {len(newly_tracked)}")
        return newly_tracked

    async def balances(self, user_id: str) -> Dict[ChecksumAddress, TokenBalance]:
        """Get balances for all tracked tokens for a specific user.
        
        Args:
            user_id: ID of the user to get balances for
            
        Returns:
            Dict[ChecksumAddress, TokenBalance]: Dictionary of token addresses to their balance info
        """
        # Get active wallet for user
        wallet_name = wallet_manager.get_active_wallet_name(user_id)
        if not wallet_name:
            logger.error(f"No active wallet found for user {hash_user_id(user_id)}")
            return {}
            
        # Get user's PIN
        pin = self._get_user_pin(user_id)
        if not pin and pin_manager.needs_pin(int(user_id)):
            logger.error(f"PIN required but not available for user {hash_user_id(user_id)}")
            return {}
            
        wallet = wallet_manager.get_wallet_by_name(user_id, wallet_name, pin)
        if not wallet:
            logger.error(f"Wallet {wallet_name} not found for user {hash_user_id(user_id)}")
            return {}
            
        wallet_address = wallet['address']
        
        tokens = db_get_tracked_tokens(user_id)
        balances: Dict[ChecksumAddress, TokenBalance] = {}
        
        for token in tokens:
            try:
                # Convert token address to checksum address
                token_address = w3.to_checksum_address(token["token_address"])
                
                raw_balance: int = 0
                balance_error: Optional[str] = None
                try:
                    # Get balance using the contract's balanceOf function.
                    # Use retries and surface "unavailable" instead of silently treating RPC errors as 0.
                    raw_balance = await get_token_balance_with_options(
                        wallet_address,
                        str(token_address),
                        raise_on_error=True,
                        retries=2,
                        retry_delay_s=0.4,
                    )
                except TokenBalanceFetchError as e:
                    balance_error = "unavailable"
                    logger.warning(
                        "Token balance unavailable for %s (%s) user %s: %s",
                        token.get("symbol"),
                        token_address,
                        hash_user_id(user_id),
                        str(e),
                    )
                
                # Get token decimals
                decimals = token.get("decimals", 18)
                if decimals is None:
                    decimals = 18
                
                # Calculate human-readable balance
                balance = raw_balance / (10 ** decimals) if balance_error is None else 0.0
                
                # Skip if required fields are missing
                if token["symbol"] is None or token["name"] is None:
                    logger.warning(f"Skipping token {token['token_address']} due to missing required fields")
                    continue
                
                # Add to balances dictionary
                balances[token_address] = TokenBalance(
                    symbol=token["symbol"],
                    name=token["name"],
                    balance=balance,
                    raw_balance=raw_balance,
                    decimals=decimals,
                    error=balance_error,
                )
                
            except Exception as e:
                logger.error(f"Failed to get balance for token {token['token_address']} for user {hash_user_id(user_id)}: {str(e)}")
                continue
                
        return balances

    async def get_token_balance_history(self, user_id: str, token_address: str, limit: int = 30) -> List[TokenBalanceHistory]:
        """Get the balance history for a specific token.
        
        Args:
            user_id: ID of the user to get balance history for
            token_address: Address of the token to get history for
            limit: Maximum number of history entries to return (default: 30)
            
        Returns:
            List[TokenBalanceHistory]: List of balance history entries with timestamps
        """
        try:
            # Get token ID from address
            token = get_token_by_address(token_address)
            if not token:
                logger.error(f"Token {token_address} not found in database")
                return []
                
            token_id = token['id']
            
            # Get balance history from database
            history = db_get_token_balance_history(user_id, token_id, limit)
            
            if not history:
                return []
                
            return [
                TokenBalanceHistory(
                    balance=entry['balance'],
                    balance_usd=entry.get('balance_usd'),
                    timestamp=entry['timestamp']
                )
                for entry in history
            ]
            
        except Exception as e:
            logger.error(f"Failed to get balance history for token {token_address} for user {hash_user_id(user_id)}: {str(e)}")
            return []
        
    async def get_token_balance(self, wallet_address: str, token_address: str) -> int:
        """Get the balance of a specific token for a wallet.
        
        Args:
            wallet_address: Address of the wallet to get balance for
            token_address: Address of the token to get balance for
            
        Returns:
            int: Raw Balance of the token for the wallet
        """
        try:
            token_address = w3.to_checksum_address(token_address)
            return await get_token_balance(wallet_address, token_address)
        except Exception as e:
            logger.error(f"Failed to get token balance for {token_address} for wallet {wallet_address}: {str(e)}")
            return 0

    def is_token_tracked(self, user_id: str, token_address: str, chain_id: int = 56) -> bool:
        """Check if a user is tracking a specific token.
        
        Args:
            user_id: ID of the user to check
            token_address: Address of the token to check
            chain_id: Chain ID where the token exists (default: 56 for BSC)
            
        Returns:
            bool: True if the token is being tracked, False otherwise
        """
        try:
            token_address = w3.to_checksum_address(token_address)
            return is_token_tracked(user_id, token_address, chain_id)
        except Exception as e:
            logger.error(f"Failed to check if token {token_address} is tracked for user {hash_user_id(user_id)}: {str(e)}")
            return False

    async def get_token_info(self, token_address: str, chain_id: int = 56) -> Optional[TokenInfo]:
        """Get information about a specific token.
        
        Args:
            token_address: Address of the token to get info for
            chain_id: Chain ID where the token exists (default: 56 for BSC)
            
        Returns:
            Optional[TokenInfo]: Token information if found, None otherwise
        """
        try:
            token_address = w3.to_checksum_address(token_address)
            
            # First try to get token info from database
            token = get_token_by_address(token_address)
            if token:
                return TokenInfo(
                    token_address=token_address,
                    symbol=token.get('symbol') or token.get('token_symbol', ''),
                    name=token.get('name') or token.get('token_name', ''),
                    decimals=token.get('decimals') or token.get('token_decimals', 18),
                    chain_id=token.get('chain_id', chain_id)
                )
            
            # If not in database, try to get from blockchain
            contract = self.web3.eth.contract(address=token_address, abi=self.erc20_abi)
            
            try:
                # Get token info concurrently
                symbol, name, decimals = await asyncio.gather(
                    asyncio.to_thread(contract.functions.symbol().call),
                    asyncio.to_thread(contract.functions.name().call),
                    asyncio.to_thread(contract.functions.decimals().call)
                )
                
                # Some tokens return bytes for symbol/name, so we need to decode
                if isinstance(symbol, bytes):
                    symbol = symbol.decode('utf-8', errors='ignore').strip('\x00')
                if isinstance(name, bytes):
                    name = name.decode('utf-8', errors='ignore').strip('\x00')
                
                return TokenInfo(
                    token_address=token_address,
                    symbol=symbol,
                    name=name,
                    decimals=decimals,
                    chain_id=chain_id
                )
            except Exception as e:
                logger.error(f"Failed to get token info from blockchain for {token_address}: {str(e)}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to get token info for {token_address}: {str(e)}")
            return None


# Create singleton instance
token_manager: TokenManager = TokenManager() 