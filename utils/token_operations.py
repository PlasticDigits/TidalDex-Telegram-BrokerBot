"""
Utility module for token operations.
"""
from utils.web3_connection import w3
from utils import load_abi

# Cache the ABI to avoid loading it multiple times
ERC20_ABI = load_abi("ERC20")

def get_token_contract(token_address, status_callback=None):
    """
    Create a token contract instance from a token address.
    
    Args:
        token_address (str): The token contract address
        status_callback (callable, optional): Function to call with status updates
        
    Returns:
        Contract: The web3 contract instance
    """
    if status_callback:
        status_callback("Converting token address to checksum format...")
    
    # Convert to checksum address
    checksum_token_address = w3.to_checksum_address(token_address)
    
    if status_callback:
        status_callback("Creating token contract instance...")
    
    # Create contract instance using the full ERC20 ABI
    return w3.eth.contract(address=checksum_token_address, abi=ERC20_ABI)

def get_token_details(token_contract, status_callback=None):
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
        status_callback("Fetching token details (symbol, decimals)...")
    
    # Get token symbol
    try:
        symbol = token_contract.functions.symbol().call()
        if status_callback:
            status_callback(f"Retrieved token symbol: {symbol}")
    except Exception as e:
        if status_callback:
            status_callback(f"Error fetching token symbol: {str(e)}")
        symbol = "UNKNOWN"
    
    # Get token decimals
    try:
        decimals = token_contract.functions.decimals().call()
        if status_callback:
            status_callback(f"Retrieved token decimals: {decimals}")
    except Exception as e:
        if status_callback:
            status_callback(f"Error fetching token decimals: {str(e)}")
        decimals = 18  # Default to 18 decimals if we can't fetch
    
    return {
        'symbol': symbol,
        'decimals': decimals
    }

def convert_to_raw_amount(amount, decimals):
    """
    Convert a human-readable token amount to raw token units.
    
    Args:
        amount (float): The human-readable amount
        decimals (int): The token decimals
        
    Returns:
        int: The raw token amount
    """
    return int(amount * (10 ** decimals)) 