"""
Wallet creation module.
"""
from typing import Dict
import secrets
from eth_account import Account

def create_wallet() -> Dict[str, str]:
    """
    Generate a new wallet with private key and address.
    
    Returns:
        Dict[str, str]: A dictionary containing the wallet address and private key
            {
                'address': '0x...',
                'private_key': '0x...'
            }
    """
    private_key = "0x" + secrets.token_hex(32)
    account = Account.from_key(private_key)
    return {
        'address': account.address,
        'private_key': private_key
    } 