"""
Shared Web3 connection utility for BSC.
"""
from web3 import Web3
from utils.config import BSC_RPC_URL

# Initialize web3 connection to BSC
def get_web3_connection() -> Web3:
    """
    Get the shared Web3 connection to BSC.
    
    Returns:
        Web3: The Web3 connection instance
    """
    if not BSC_RPC_URL:
        raise ValueError("BSC_RPC_URL not found in environment variables!")
    
    return Web3(Web3.HTTPProvider(BSC_RPC_URL))

# Singleton connection instance
w3: Web3 = get_web3_connection() 