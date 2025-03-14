"""
Balance checking module for BNB and BEP20 tokens.
"""
from typing import Dict, Any, Optional, Callable, Union, Awaitable
from decimal import Decimal
from utils.web3_connection import w3
from utils.token_operations import get_token_contract, get_token_details

async def get_bnb_balance(
    address: str,
    status_callback: Optional[Callable[[str], Awaitable[None]]] = None
) -> Dict[str, Union[float, str, int, Decimal]]:
    """
    Get BNB balance.
    
    Args:
        address (str): The wallet address to check
        status_callback (Optional[Callable[[str], Awaitable[None]]]): Function to call with status updates
        
    Returns:
        Dict[str, Union[float, str, int, Decimal]]: Token balance information
            {
                'balance': Decimal,  # Human-readable balance
                'symbol': str,     # Token symbol
                'raw_balance': int, # Raw balance in smallest unit
                'decimals': int    # Token decimals
            }
    """
    if status_callback:
        await status_callback("Converting address to checksum format...")
    
    # Convert to checksum address
    checksum_address = w3.to_checksum_address(address)
    
    if status_callback:
        await status_callback("Connecting to BSC network...")
    
    if status_callback:
        await status_callback("Fetching BNB balance...")
    
    raw_balance = w3.eth.get_balance(checksum_address)
    balance = w3.from_wei(raw_balance, 'ether')
    decimals = 18
    symbol = 'BNB'
    
    if status_callback:
        await status_callback(f"Balance retrieved: {balance} BNB")
    
    # Ensure we always return a Decimal
    return {
        'balance': balance,
        'symbol': symbol,
        'raw_balance': raw_balance,
        'decimals': decimals
    }

async def get_token_balance(
    token_address: str,
    wallet_address: str,
    status_callback: Optional[Callable[[str], Awaitable[None]]] = None
) -> Dict[str, Union[float, str, int, Decimal]]:
    """
    Get BEP20 token balance.
    
    Args:
        token_address (str): The token contract address
        wallet_address (str): The wallet address to check
        status_callback (Optional[Callable[[str], Awaitable[None]]]): Function to call with status updates
        
    Returns:
        Dict[str, Union[float, str, int, Decimal]]: Token balance information
            {
                'balance': Decimal,  # Human-readable balance
                'symbol': str,     # Token symbol
                'raw_balance': int, # Raw balance in smallest unit
                'decimals': int    # Token decimals
            }
    """
    if status_callback:
        await status_callback("Converting wallet address to checksum format...")
    
    # Convert wallet address to checksum
    checksum_wallet_address = w3.to_checksum_address(wallet_address)
    
    # Get token contract
    token_contract = get_token_contract(token_address)
    
    # Get token details
    token_details = await get_token_details(token_contract, status_callback)
    symbol = token_details['symbol']
    decimals = token_details['decimals']
    
    if status_callback:
        await status_callback(f"Fetching {symbol} balance...")
    
    # Get balance
    raw_balance = token_contract.functions.balanceOf(checksum_wallet_address).call()
    balance = Decimal(raw_balance) / Decimal(10 ** decimals)
    
    if status_callback:
        await status_callback(f"Balance retrieved: {balance} {symbol}")
    
    return {
        'balance': balance,
        'symbol': symbol,
        'raw_balance': raw_balance,
        'decimals': decimals
    } 