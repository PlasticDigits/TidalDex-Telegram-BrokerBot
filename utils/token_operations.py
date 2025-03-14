"""
Utility module for token operations.
"""
from utils.web3_connection import w3
from utils.load_abi import ERC20_ABI
from utils.token import find_token
from web3.contract import Contract
from typing import Dict, Any, Optional, Callable, Union, Awaitable
from decimal import Decimal
import logging

# Configure module logger
logger = logging.getLogger(__name__)

# No need to load the ABI again since we're importing it directly
# ERC20_ABI = load_abi("ERC20")

def get_token_contract(token_address: str) -> Contract:
    """
    Create a token contract instance from a token address.
    
    Args:
        token_address (str): The token contract address
        status_callback (callable, optional): Function to call with status updates
        
    Returns:
        Contract: The web3 contract instance
    """
    
    # Convert to checksum address
    checksum_token_address = w3.to_checksum_address(token_address)
    
    # Create contract instance using the full ERC20 ABI
    return w3.eth.contract(address=checksum_token_address, abi=ERC20_ABI)

async def get_token_details(token_contract: Contract, status_callback: Optional[Callable[[str], Awaitable[None]]] = None) -> Dict[str, Any]:
    """
    Get token symbol and decimals from a token contract.
    
    Args:
        token_contract: The web3 token contract instance
        status_callback (callable, optional): Function to call with status updates
        
    Returns:
        dict: Token details with symbol and decimals
            {
                'symbol': str,     # Token symbol
                'decimals': int     # Token decimals
            }
    """
    if status_callback:
        await status_callback("Fetching token details...")
    
    # First, check if the token exists in our default token list for faster access
    token_address: str = token_contract.address.lower()
    token_info: Optional[Dict[str, Any]] = await find_token(address=token_address)

    if token_info is None:
        # If not in our list, proceed with blockchain calls
        
        # Get token symbol
        try:
            symbol = token_contract.functions.symbol().call()
            if status_callback:
                await status_callback(f"Retrieved token symbol: {symbol}")
        except Exception as e:
            if status_callback:
                await status_callback(f"Error fetching token symbol: {str(e)}")
            symbol = "UNKNOWN"
        
        # Get token decimals
        try:
            decimals = token_contract.functions.decimals().call()
            if status_callback:
                await status_callback(f"Retrieved token decimals: {decimals}")
        except Exception as e:
            if status_callback:
                await status_callback(f"Error fetching token decimals: {str(e)}")
            decimals = 18  # Default to 18 decimals if we can't fetch
        
        return {
            'symbol': symbol,
            'decimals': decimals
        }
    else:
        return {
            'symbol': token_info['symbol'],
            'decimals': token_info.get('decimals', 18)
        }
    

def convert_to_raw_amount(amount: Union[int, float, str, Decimal], decimals: int) -> int:
    """
    Convert a human-readable token amount to raw token units.
    
    Args:
        amount (Union[int, float, str, Decimal]): The human-readable amount
        decimals (int): The token decimals
        
    Returns:
        int: The raw token amount
    """
    # Convert string to float if needed
    if isinstance(amount, str):
        amount = float(amount)
    # Convert Decimal to float if needed
    elif isinstance(amount, Decimal):
        amount = float(amount)
        
    return int(amount * (10 ** decimals)) 