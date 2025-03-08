"""
Wallet management services.

This package provides services for managing wallets, including:
- Creating wallets
- Importing wallets
- Managing wallet names
- Retrieving wallet balances
"""
from services.wallet.WalletManager import wallet_manager

# Export the wallet manager functions directly
get_active_wallet_name = wallet_manager.get_active_wallet_name
get_wallet_by_name = wallet_manager.get_wallet_by_name
get_wallet_by_address = wallet_manager.get_wallet_by_address
get_user_wallet = wallet_manager.get_user_wallet
get_user_wallets = wallet_manager.get_user_wallets
create_wallet = wallet_manager.create_wallet
import_wallet = wallet_manager.import_wallet
rename_wallet = wallet_manager.rename_wallet
delete_wallet = wallet_manager.delete_wallet
set_active_wallet = wallet_manager.set_active_wallet
get_wallet_balance = wallet_manager.get_wallet_balance
has_user_wallet = wallet_manager.has_user_wallet
create_mnemonic = wallet_manager.create_mnemonic
has_user_mnemonic = wallet_manager.has_user_mnemonic

# Export the wallet manager instance
__all__ = [
    'wallet_manager',
    'get_active_wallet_name',
    'get_wallet_by_name',
    'get_wallet_by_address',
    'get_user_wallet',
    'get_user_wallets',
    'create_wallet',
    'import_wallet',
    'rename_wallet',
    'delete_wallet',
    'set_active_wallet',
    'get_wallet_balance',
    'has_user_wallet',
    'create_mnemonic',
    'has_user_mnemonic'
] 