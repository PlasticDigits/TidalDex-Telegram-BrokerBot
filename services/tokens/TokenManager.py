"""
Token management service for tracking and monitoring ERC20 tokens.
"""
import logging
import os
import json
import httpx
from typing import Dict, List, Optional, Any, TypedDict, cast, Union, Awaitable
from web3 import Web3
from web3.contract import Contract
from web3.exceptions import ContractLogicError
from web3.types import Address, ChecksumAddress, ENS # type: ignore[attr-defined]
from db.tokens import (
    track_token,
    untrack_token,
    get_tracked_tokens as db_get_tracked_tokens,
    is_token_tracked,
    get_token_by_address
)
from db.track import get_token_balance_history as db_get_token_balance_history
from services.wallet import wallet_manager
from services.pin import pin_manager

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
    
    def __init__(self, web3: Web3) -> None:
        """Initialize the TokenManager.
        
        Args:
            web3: Web3 instance for blockchain interaction
        """
        self.web3 = web3
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
            logger.error(f"Failed to get PIN for user {user_id}: {str(e)}")
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
            logger.error(f"Failed to get tracked tokens for user {user_id}: {str(e)}")
            return []

    async def _parse_default_token_list(self) -> Dict[ChecksumAddress, TokenDetails]:
        """Fetch and parse the DEFAULT_TOKEN_LIST from a remote URL.
        
        Expected format: JSON file with tokens array containing token objects
        Each token object should have: address, symbol, name, decimals
        
        Returns:
            Dict[ChecksumAddress, TokenDetails]: Dictionary mapping token addresses to their details
        """
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
                    address = Web3.to_checksum_address(token['address'])
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
            
        return default_tokens

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
            token_address = Web3.to_checksum_address(token_address)
            
            if await is_token_tracked(user_id, token_address, chain_id):
                logger.info(f"Token {token_address} is already being tracked for user {user_id}")
                return True

            # Check if token is in DEFAULT_TOKEN_LIST
            if token_address in self.default_tokens:
                token_details = self.default_tokens[token_address]
                symbol = token_details["symbol"]
                name = token_details["name"]
                decimals = token_details["decimals"]
            else:
                # Get token details from contract if not in DEFAULT_TOKEN_LIST
                contract = self.web3.eth.contract(address=token_address, abi=self.erc20_abi)
                symbol = await contract.functions.symbol().call()
                name = await contract.functions.name().call()
                decimals = await contract.functions.decimals().call()
            
            await track_token(user_id, token_address, chain_id, symbol, name, decimals)
            logger.info(f"Successfully started tracking token {symbol} ({token_address}) for user {user_id}")
            return True
            
        except (ContractLogicError, ValueError) as e:
            logger.error(f"Failed to track token {token_address} for user {user_id}: {str(e)}")
            return False

    async def untrack(self, user_id: str, token_address: str, chain_id: int = 56) -> bool:
        """Stop tracking an ERC20 token for a specific user.
        
        Args:
            user_id: ID of the user to untrack the token for
            token_address: Address of the ERC20 token to untrack
            chain_id: Chain ID where the token exists (default: 56 for BSC)
            
        Returns:
            bool: True if token was successfully untracked, False otherwise
        """
        try:
            token_address = Web3.to_checksum_address(token_address)
            await untrack_token(user_id, token_address, chain_id)
            logger.info(f"Stopped tracking token {token_address} for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to untrack token {token_address} for user {user_id}: {str(e)}")
            return False

    async def scan(self, user_id: str, chain_id: int = 56) -> List[ChecksumAddress]:
        """Scan default token list and track tokens with non-zero balance for a specific user.
        
        Args:
            user_id: ID of the user to scan tokens for
            chain_id: Chain ID to scan tokens on (default: 56 for BSC)
            
        Returns:
            List[ChecksumAddress]: List of token addresses that were newly tracked
        """
        newly_tracked: List[ChecksumAddress] = []
        
        # Get active wallet for user
        wallet_name = wallet_manager.get_active_wallet_name(user_id)
        if not wallet_name:
            logger.error(f"No active wallet found for user {user_id}")
            return newly_tracked
            
        # Get user's PIN
        pin = self._get_user_pin(user_id)
        if not pin and pin_manager.needs_pin(int(user_id)):
            logger.error(f"PIN required but not available for user {user_id}")
            return newly_tracked
            
        wallet = wallet_manager.get_wallet_by_name(user_id, wallet_name, pin)
        if not wallet:
            logger.error(f"Wallet {wallet_name} not found for user {user_id}")
            return newly_tracked
            
        wallet_address = wallet['address']
        
        for token_address in self.default_tokens:
            try:
                if await is_token_tracked(user_id, str(token_address), chain_id):
                    continue
                    
                contract = self.web3.eth.contract(address=token_address, abi=self.erc20_abi)
                balance = await contract.functions.balanceOf(wallet_address).call()
                
                if balance > 0:
                    if await self.track(user_id, str(token_address), chain_id):
                        newly_tracked.append(token_address)
                        
            except Exception as e:
                logger.error(f"Failed to scan token {token_address} for user {user_id}: {str(e)}")
                continue
                
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
            logger.error(f"No active wallet found for user {user_id}")
            return {}
            
        # Get user's PIN
        pin = self._get_user_pin(user_id)
        if not pin and pin_manager.needs_pin(int(user_id)):
            logger.error(f"PIN required but not available for user {user_id}")
            return {}
            
        wallet = wallet_manager.get_wallet_by_name(user_id, wallet_name, pin)
        if not wallet:
            logger.error(f"Wallet {wallet_name} not found for user {user_id}")
            return {}
            
        wallet_address = wallet['address']
        
        tokens = db_get_tracked_tokens(user_id)
        balances: Dict[ChecksumAddress, TokenBalance] = {}
        
        for token in tokens:
            try:
                # Convert token address to checksum address
                token_address = Web3.to_checksum_address(token["token_address"])
                
                # Create contract instance
                contract = self.web3.eth.contract(
                    address=token_address,
                    abi=self.erc20_abi
                )
                
                # Get balance using the contract's balanceOf function
                raw_balance = await contract.functions.balanceOf(wallet_address).call()
                
                # Get token decimals
                decimals = token.get("decimals", 18)
                if decimals is None:
                    decimals = 18
                
                # Calculate human-readable balance
                balance = raw_balance / (10 ** decimals)
                
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
                    decimals=decimals
                )
                
            except Exception as e:
                logger.error(f"Failed to get balance for token {token['token_address']} for user {user_id}: {str(e)}")
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
            logger.error(f"Failed to get balance history for token {token_address} for user {user_id}: {str(e)}")
            return []

    async def is_token_tracked(self, user_id: str, token_address: str, chain_id: int = 56) -> bool:
        """Check if a user is tracking a specific token.
        
        Args:
            user_id: ID of the user to check
            token_address: Address of the token to check
            chain_id: Chain ID where the token exists (default: 56 for BSC)
            
        Returns:
            bool: True if the token is being tracked, False otherwise
        """
        try:
            token_address = Web3.to_checksum_address(token_address)
            return is_token_tracked(user_id, token_address, chain_id)
        except Exception as e:
            logger.error(f"Failed to check if token {token_address} is tracked for user {user_id}: {str(e)}")
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
            token_address = Web3.to_checksum_address(token_address)
            
            # First try to get token info from database
            token = get_token_by_address(token_address)
            if token:
                return TokenInfo(
                    token_address=token_address,
                    symbol=token['token_symbol'],
                    name=token['token_name'],
                    decimals=token['token_decimals'],
                    chain_id=token['chain_id']
                )
            
            # If not in database, try to get from blockchain
            contract = self.web3.eth.contract(address=token_address, abi=self.erc20_abi)
            
            try:
                symbol = await contract.functions.symbol().call()
                name = await contract.functions.name().call()
                decimals = await contract.functions.decimals().call()
                
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