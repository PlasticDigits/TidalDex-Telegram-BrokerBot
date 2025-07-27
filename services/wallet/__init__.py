"""
Wallet management services.

This package provides services for managing wallets, including:
- Creating wallets
- Importing wallets
- Managing wallet names
- Retrieving wallet balances
"""
from typing import Dict, List, Optional, Any, Tuple, Union, Callable, Awaitable
from db.wallet import WalletData

from services.wallet.WalletManager import wallet_manager

# Export the wallet manager functions directly
get_active_wallet_name: Callable[[str], Optional[str]] = wallet_manager.get_active_wallet_name
get_wallet_by_name: Callable[[str, str, Optional[str]], Optional[WalletData]] = wallet_manager.get_wallet_by_name
get_wallet_by_address: Callable[[str, str, Optional[str]], Optional[WalletData]] = wallet_manager.get_wallet_by_address
get_user_wallet: Callable[[str, Optional[str], Optional[str]], Optional[WalletData]] = wallet_manager.get_user_wallet
get_user_wallets: Callable[[str, bool, Optional[str]], Dict[str, WalletData]] = wallet_manager.get_user_wallets
create_wallet: Callable[[str, str, Optional[str]], Optional[WalletData]] = wallet_manager.create_wallet
import_wallet: Callable[[str, str, str, Optional[str]], Optional[WalletData]] = wallet_manager.import_wallet
rename_wallet: Callable[[str, str, str, Optional[str]], bool] = wallet_manager.rename_wallet
delete_wallet: Callable[[str, str], bool] = wallet_manager.delete_wallet
delete_wallets_all: Callable[[str, Optional[str]], bool] = wallet_manager.delete_wallets_all
set_active_wallet: Callable[[str, str], bool] = wallet_manager.set_active_wallet
get_wallet_balance: Callable[[str, Optional[str]], Awaitable[int]] = wallet_manager.get_wallet_balance
has_user_wallet: Callable[[str, Optional[str]], bool] = wallet_manager.has_user_wallet
create_mnemonic: Callable[[str, Optional[str]], Optional[str]] = wallet_manager.create_mnemonic
has_user_mnemonic: Callable[[str, Optional[str]], bool] = wallet_manager.has_user_mnemonic
get_user_mnemonic: Callable[[str, Optional[str]], Optional[str]] = wallet_manager.get_user_mnemonic
save_user_wallet: Callable[[str, WalletData, str, Optional[str]], bool] = wallet_manager.save_user_wallet
save_user_mnemonic: Callable[[str, str, Optional[str]], bool] = wallet_manager.save_user_mnemonic

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
    'delete_wallets_all',
    'set_active_wallet',
    'get_wallet_balance',
    'has_user_wallet',
    'create_mnemonic',
    'has_user_mnemonic',
    'get_user_mnemonic',
    'save_user_wallet',
    'save_user_mnemonic'
] 