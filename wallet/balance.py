"""
Balance checking module for BNB and BEP20 tokens.
"""
from utils.web3_connection import w3
from utils.token_operations import get_token_contract, get_token_details

async def get_bnb_balance(address, status_callback=None):
    """
    Get BNB balance for an address.
    
    Args:
        address (str): The wallet address to check
        status_callback (callable, optional): Function to call with status updates
        
    Returns:
        float: The BNB balance in ether
    """
    if status_callback:
        await status_callback("Converting address to checksum format...")
    
    # Convert to checksum address
    checksum_address = w3.to_checksum_address(address)
    
    if status_callback:
        await status_callback("Connecting to BSC network...")
    
    if status_callback:
        await status_callback("Fetching BNB balance...")
    
    balance_wei = w3.eth.get_balance(checksum_address)
    balance_bnb = w3.from_wei(balance_wei, 'ether')
    
    if status_callback:
        await status_callback(f"Balance retrieved: {balance_bnb} BNB")
    
    return balance_bnb

async def get_token_balance(token_address, wallet_address, status_callback=None):
    """
    Get BEP20 token balance.
    
    Args:
        token_address (str): The token contract address
        wallet_address (str): The wallet address to check
        status_callback (callable, optional): Function to call with status updates
        
    Returns:
        dict: Token balance information
            {
                'balance': float,  # Human-readable balance
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
    balance = raw_balance / (10 ** decimals)
    
    if status_callback:
        await status_callback(f"Balance retrieved: {balance} {symbol}")
    
    return {
        'balance': balance,
        'symbol': symbol,
        'raw_balance': raw_balance,
        'decimals': decimals
    } 