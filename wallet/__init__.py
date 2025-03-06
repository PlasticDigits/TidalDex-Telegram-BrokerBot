"""
Wallet module for the Telegram trading bot.
Provides functionality for creating wallets, checking balances, and sending transactions on BSC.
"""

from wallet.create import create_wallet
from wallet.balance import get_bnb_balance, get_token_balance
from wallet.send import send_bnb, send_token
from wallet.utils import validate_address

# Export all functions
__all__ = [
    'create_wallet',
    'get_bnb_balance',
    'get_token_balance',
    'send_bnb',
    'send_token',
    'validate_address'
] 