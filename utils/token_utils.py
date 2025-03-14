"""
Utility functions for working with tokens on the blockchain.
"""
import logging
import json
import os
from web3 import Web3
from web3.exceptions import BadFunctionCallOutput, ContractLogicError
import httpx
from utils.config import BSC_RPC_URL, DEFAULT_TOKEN_LIST
from utils.load_abi import ERC20_ABI
from typing import Dict, Union, Any, Optional

# Configure module logger
logger = logging.getLogger(__name__)

# Initialize Web3 connection
w3 = Web3(Web3.HTTPProvider(BSC_RPC_URL))

# Token cache for faster lookups
_token_cache: Dict[str, Dict[str, Union[str, int]]] = {}



async def validate_token_address(token_address: str) -> bool:
    """
    Validates if a given address is a valid ERC-20 token.
    
    Args:
        token_address (str): The token contract address
        
    Returns:
        bool: True if valid token, False otherwise
    """
    if not Web3.is_address(token_address):
        return False
        
    # Convert to checksum address
    token_address = Web3.to_checksum_address(token_address)
    
    try:
        # Create contract instance
        contract = w3.eth.contract(address=token_address, abi=ERC20_ABI)
        
        # Try to call basic ERC-20 functions
        contract.functions.symbol().call()
        contract.functions.decimals().call()
        
        return True
    except (BadFunctionCallOutput, ContractLogicError) as e:
        logger.warning(f"Contract {token_address} is not a valid ERC-20 token: {e}")
        return False
    except Exception as e:
        logger.error(f"Error validating token {token_address}: {e}")
        return False

async def get_token_info(token_address: str) -> Optional[Dict[str, Any]]:
    """
    Gets token information like symbol, name and decimals.
    
    Args:
        token_address (str): The token contract address
        
    Returns:
        dict: Token information with keys 'symbol', 'name', 'decimals'
        None: If token information cannot be retrieved
    """
    if not Web3.is_address(token_address):
        return None
        
    # Convert to checksum address
    token_address = Web3.to_checksum_address(token_address)

    httpxClient = httpx.AsyncClient()
    
    # Check cache first
    if token_address in _token_cache:
        return _token_cache[token_address]
    
    try:
        # Create contract instance
        contract = w3.eth.contract(address=token_address, abi=ERC20_ABI)
        
        # Get token information
        symbol = contract.functions.symbol().call()
        name = contract.functions.name().call()
        decimals = contract.functions.decimals().call()
        
        # Some tokens return bytes for symbol/name, so we need to decode
        if isinstance(symbol, bytes):
            symbol = symbol.decode('utf-8', errors='ignore').strip('\x00')
        if isinstance(name, bytes):
            name = name.decode('utf-8', errors='ignore').strip('\x00')
        
        token_info = {
            'address': token_address,
            'symbol': symbol,
            'name': name,
            'decimals': decimals
        }
        
        # Cache for future use
        _token_cache[token_address] = token_info
        
        return token_info
    except Exception as e:
        logger.error(f"Error getting token info for {token_address}: {e}")
        
        # Try getting info from default token list
        try:
            token_list_response = await httpxClient.get(DEFAULT_TOKEN_LIST)
            if token_list_response.status_code == 200:
                token_list = token_list_response.json()
                
                for token in token_list.get('tokens', []):
                    if token.get('address', '').lower() == token_address.lower():
                        token_info = {
                            'address': token_address,
                            'symbol': token.get('symbol'),
                            'name': token.get('name'),
                            'decimals': token.get('decimals', 18)
                        }
                        
                        # Cache for future use
                        _token_cache[token_address] = token_info
                        
                        return token_info
        except Exception as e:
            logger.error(f"Error fetching token from token list: {e}")
        
        return None

async def get_token_balance(wallet_address: str, token_address: str) -> int:
    """
    Gets the balance of a specific token for a wallet.
    
    Args:
        wallet_address (str): The wallet address
        token_address (str): The token contract address
        
    Returns:
        int: Raw token balance (without decimal adjustment)
    """
    if not Web3.is_address(wallet_address) or not Web3.is_address(token_address):
        return 0
        
    # Convert to checksum addresses
    wallet_address = Web3.to_checksum_address(wallet_address)
    token_address = Web3.to_checksum_address(token_address)
    
    try:
        # Create contract instance
        contract = w3.eth.contract(address=token_address, abi=ERC20_ABI)
        
        # Get token balance
        balance = int(contract.functions.balanceOf(wallet_address).call())
        
        return balance
    except Exception as e:
        logger.error(f"Error getting token balance for {wallet_address} ({token_address}): {e}")
        return 0

def format_token_balance(balance: int, decimals: int = 18) -> str:
    """
    Formats a raw token balance with proper decimal places.
    
    Args:
        balance (int): Raw token balance
        decimals (int): Number of decimals for the token
        
    Returns:
        str: Formatted balance with proper decimal places
    """
    if balance == 0:
        return "0"
        
    # Convert to decimal representation
    return str(balance / (10 ** decimals)) 