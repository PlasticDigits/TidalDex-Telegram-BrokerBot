"""
Shared Web3 connection utility for BSC.
"""
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
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
    
    w3 = Web3(Web3.HTTPProvider(BSC_RPC_URL))
    
    # Inject the PoA middleware at layer 0 (innermost layer)
    # This is required for BNB Chain (Binance Smart Chain) which is a PoA chain
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    
    return w3

# Singleton connection instance
w3: Web3 = get_web3_connection() 