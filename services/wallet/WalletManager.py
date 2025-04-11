"""
WalletManager - Centralized service for managing wallet-related operations.

This service provides a clean, simple API for:
- Getting wallet information
- Creating wallets
- Importing wallets
- Managing wallet names
- Retrieving wallet balances
- Handling wallet encryption/decryption

All wallet-related operations should go through this service to maintain
consistency and avoid duplication of logic across the codebase.
"""
import logging
import threading
import traceback
from typing import Dict, List, Optional, Any, Tuple, Union, TypedDict, cast, Callable
from db.wallet import WalletData
from utils.load_abi import ERC20_ABI
from mnemonic import Mnemonic
import time
from db.wallet import (
    get_user_wallet as db_get_user_wallet,
    get_user_wallets as db_get_user_wallets,
    save_user_wallet as db_save_user_wallet,
    delete_user_wallet as db_delete_user_wallet,
    set_active_wallet as db_set_active_wallet,
    get_active_wallet_name as db_get_active_wallet_name,
    get_wallet_by_name as db_get_wallet_by_name,
    get_wallet_by_address as db_get_wallet_by_address,
    get_user_wallets_with_keys as db_get_user_wallets_with_keys,
    has_user_wallet as db_has_user_wallet,
)
from db.mnemonic import get_user_mnemonic, save_user_mnemonic, get_user_mnemonic_index, increment_user_mnemonic_index
from wallet.mnemonic import derive_wallet_from_mnemonic
from wallet.send import send_bnb, send_token
from wallet.balance import get_bnb_balance, get_token_balance
from web3 import Web3
from utils.config import BSC_RPC_URL
from decimal import Decimal
from db.utils import hash_user_id

logger = logging.getLogger(__name__)

class WalletManager:
    """
    Singleton service for centralized wallet management.
    
    This class is responsible for all wallet-related operations, including
    wallet creation, retrieval, and management.
    """
    _instance: Optional['WalletManager'] = None
    _lock: threading.Lock = threading.Lock()
    
    def __new__(cls) -> 'WalletManager':
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(WalletManager, cls).__new__(cls)
                cls._instance._initialize()
            return cls._instance
    
    def _initialize(self) -> None:
        """Initialize the wallet manager."""
        self.w3 = Web3(Web3.HTTPProvider(BSC_RPC_URL))
        logger.info("WalletManager initialized")

    async def send_bnb(self, user_id: str, recipient: str, amount_wei: int, pin: Optional[str] = None, status_callback: Optional[Callable[[str, str], None]] = None) -> Dict[str, Any]:
        """
        Send BNB from a user's wallet to a recipient.
        """
        wallet_name: Optional[str] = self.get_active_wallet_name(user_id)
        if not wallet_name:
            logger.error(f"No active wallet found for user {hash_user_id(user_id)}")
            return {'status': 'error', 'message': 'No active wallet found'}
        wallet_data: Optional[WalletData] = self.get_wallet_by_name(user_id, wallet_name, pin)
        if not wallet_data:
            logger.error(f"Wallet {wallet_name} not found for user {hash_user_id(user_id)}")
            return {'status': 'error', 'message': f'Wallet {wallet_name} not found'}
        
        # Wrap the status_callback to match the expected signature
        async def callback_wrapper(status: str) -> None:
            if status_callback:
                status_callback(status, recipient)
        
        return await send_bnb(str(wallet_data['private_key']), recipient, amount_wei, status_callback=callback_wrapper)

    async def send_token(self, user_id: str, recipient: str, amount: int, token_address: str, pin: Optional[str] = None, status_callback: Optional[Callable[[str, str], None]] = None) -> Dict[str, Any]:
        """
        Send a token from a user's wallet to a recipient.
        """
        wallet_name: Optional[str] = self.get_active_wallet_name(user_id)
        if not wallet_name:
            logger.error(f"No active wallet found for user {hash_user_id(user_id)}")
            return {'status': 'error', 'message': 'No active wallet found'}
        wallet_data: Optional[WalletData] = self.get_wallet_by_name(user_id, wallet_name, pin)
        if not wallet_data:
            logger.error(f"Wallet {wallet_name} not found for user {hash_user_id(user_id)}")
            return {'status': 'error', 'message': f'Wallet {wallet_name} not found'}
        
        # Wrap the status_callback to match the expected signature
        async def callback_wrapper(status: str) -> None:
            if status_callback:
                status_callback(status, recipient)
        
        # Convert amount to string as expected by send_token
        amount_str = str(amount)
        
        return await send_token(str(wallet_data['private_key']), token_address, recipient, amount_str, status_callback=callback_wrapper)
    
    async def get_token_balance(self, token_address: str, user_address: str) -> Dict[str, Union[float, str, int, Decimal]]:
        """
        Get token balance.
        
        Args:
            token_address (str): The token contract address
            user_address (str): The wallet address to check
            
        Returns:
            Dict[str, Union[float, str, int, Decimal]]: Token balance information
                {
                    'balance': Decimal,  # Human-readable balance
                    'symbol': str,     # Token symbol
                    'raw_balance': int, # Raw balance in smallest unit
                    'decimals': int    # Token decimals
                }
        """
        return await get_token_balance(token_address, user_address)

    async def get_bnb_balance(self, user_address: str) -> Dict[str, Union[float, str, int, Decimal]]:
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
        return await get_bnb_balance(user_address)
    
    def get_active_wallet_name(self, user_id: str) -> Optional[str]:
        """
        Get the name of the active wallet for a user.
        
        Args:
            user_id (str): The user ID
            
        Returns:
            str: The name of the active wallet, or None if no active wallet
        """
        return db_get_active_wallet_name(user_id)
    
    def get_wallet_by_name(self, user_id: str, wallet_name: str, pin: Optional[str] = None) -> Optional[WalletData]:
        """
        Get a wallet by its name.
        
        Args:
            user_id (str): The user ID
            wallet_name (str): The wallet name
            pin (str, optional): PIN for decrypting private key
            
        Returns:
            WalletData: The wallet information, or None if not found
        """
        return db_get_wallet_by_name(user_id, wallet_name, pin)
    
    def get_wallet_by_address(self, user_id: str, address: str, pin: Optional[str] = None) -> Optional[WalletData]:
        """
        Get a wallet by its address.
        
        Args:
            user_id (str): The user ID
            address (str): The wallet address
            pin (str, optional): PIN for decrypting private key
            
        Returns:
            WalletData: The wallet information, or None if not found
        """
        return db_get_wallet_by_address(user_id, address, pin)
    

    def has_user_wallet(self, user_id: str, pin: Optional[str] = None) -> bool:
        """
        Check if a user has any wallets.
        
        Args:
            user_id: The user ID to check
            pin (str, optional): Not used, included for API consistency
            
        Returns:
            bool: True if the user has at least one wallet, False otherwise
        """
        return db_has_user_wallet(user_id, pin)
    
    def has_user_mnemonic(self, user_id: str, pin: Optional[str] = None) -> bool:
        """
        Check if a user has a mnemonic.
        
        Args:
            user_id: The user ID to check
            pin (str, optional): PIN for decryption if necessary
            
        Returns:
            bool: True if the user has a mnemonic, False otherwise
        """
        return get_user_mnemonic(user_id, pin) is not None
    
    def get_user_mnemonic(self, user_id: str, pin: Optional[str] = None) -> Optional[str]:
        """
        Get a user's mnemonic.
        
        Args:
            user_id: The user ID to get the mnemonic for
            pin (str, optional): PIN for decryption
            
        Returns:
            str: The user's mnemonic, or None if not found
        """
        return get_user_mnemonic(user_id, pin)
    
    def save_user_wallet(self, user_id: str, wallet_data: WalletData, wallet_name: str, pin: Optional[str] = None) -> bool:
        """
        Save a wallet for a specific user.
        
        Args:
            user_id (str): The user ID to save the wallet for
            wallet_data (WalletData): The wallet data to save
            wallet_name (str): The name of the wallet
            pin (str, optional): PIN for encryption
            
        Returns:
            bool: True if the wallet was saved successfully
        """
        return db_save_user_wallet(user_id, dict(wallet_data), wallet_name, pin)
    
    def get_user_wallet(self, user_id: str, wallet_name: Optional[str] = None, pin: Optional[str] = None) -> Optional[WalletData]:
        """
        Get a user's wallet.
        
        Args:
            user_id (str): The user ID
            wallet_name (str, optional): The wallet name (uses active wallet if None)
            pin (str, optional): PIN for decrypting private key
            
        Returns:
            WalletData: The wallet information, or None if not found
        """
        return db_get_user_wallet(user_id, wallet_name, pin)
    
    def get_user_wallets(self, user_id: str, include_private_keys: bool = False, pin: Optional[str] = None) -> Dict[str, WalletData]:
        """
        Get all wallets for a user.
        
        Args:
            user_id (str): The user ID
            include_private_keys (bool): Whether to include private keys
            pin (str, optional): PIN for decrypting private keys
            
        Returns:
            Dict[str, WalletData]: Dictionary of wallet name to wallet data
        """
        if include_private_keys:
            return db_get_user_wallets_with_keys(user_id, pin)
        return db_get_user_wallets(user_id)
    

    def save_user_mnemonic(self, user_id: str, mnemonic: str, pin: Optional[str] = None) -> bool:
        """
        Save a user's mnemonic.
        
        Args:
            user_id: The user ID to save the mnemonic for
            mnemonic: The mnemonic to save
            pin (str, optional): PIN for encryption
            
        Returns:
            bool: True if the mnemonic was saved successfully
        """
        return save_user_mnemonic(user_id, mnemonic, pin)
    
    def create_mnemonic(self, user_id: str, pin: Optional[str] = None) -> Optional[str]:
        """
        Create a new mnemonic for a user.
        
        Args:
            user_id: The user ID to create a mnemonic for
            pin (str, optional): PIN for encryption
            
        Returns:
            str: The created mnemonic, or None if creation failed
        """
        # first, check if the user has a mnmoenic
        # if so, throw an error
        if self.has_user_mnemonic(user_id):
            logger.error(f"User {hash_user_id(user_id)} already has a mnemonic")
            return None
        
        # create a new mnemonic using bip39
        mnemo = Mnemonic("english")
        mnemonic: str = mnemo.generate(strength=128)  # 12 words
        
        # save the mnemonic to the database
        save_user_mnemonic(user_id, mnemonic, pin)
        
        return mnemonic
    
    def create_wallet(self, user_id: str, wallet_name: str, pin: Optional[str] = None) -> Optional[WalletData]:
        """
        Create a new wallet for a user from their mnemonic.
        Increments the mnemonic index for the user.
        
        Args:
            user_id: The user ID to create the wallet for
            wallet_name: The name for the new wallet
            pin: PIN for encryption/decryption
            
        Returns:
            WalletData: The wallet information, or None if creation failed
        """
        try:
            # Check if the wallet already exists
            existing_wallet: Optional[WalletData] = self.get_wallet_by_name(user_id, wallet_name, pin)
            if existing_wallet:
                logger.error(f"Wallet with name '{wallet_name}' already exists for user {hash_user_id(user_id)}")
                return None
            
            # Get the user's mnemonic
            mnemonic: Optional[str] = self.get_user_mnemonic(user_id, pin)
            if not mnemonic:
                logger.error(f"No mnemonic found for user {hash_user_id(user_id)}")
                return None
            
            # Get all current wallets to determine the next derivation path
            wallets_all: Dict[str, WalletData] = db_get_user_wallets_with_keys(user_id, pin)
            
            # Determine the next derivation path index
            next_index: Union[int, None] = get_user_mnemonic_index(user_id)
            if next_index is None:
                logger.error(f"No mnemonic index found for user {hash_user_id(user_id)}")
                return None
            
            wallet_derivation_path: str = f"m/44'/60'/0'/0/{next_index}"
            
            # Derive the wallet from the mnemonic
            wallet_dict: Dict[str, str] = derive_wallet_from_mnemonic(mnemonic, next_index)
            
            # Add the name and derivation path to the wallet data
            new_wallet_data: WalletData = {
                'name': wallet_name,
                'address': wallet_dict.get('address', ''),
                'private_key': wallet_dict.get('private_key', ''),
                'derivation_path': wallet_derivation_path,
                'is_active': False,
                'is_imported': False,
                'created_at': time.time()
            }
            
            # Save the wallet
            success: bool = self.save_user_wallet(user_id, new_wallet_data, wallet_name, pin)
            if not success:
                logger.error(f"Failed to save wallet '{wallet_name}' for user {hash_user_id(user_id)}")
                return None

            # If this is the first wallet, set it as active
            if len(wallets_all) == 0:
                self.set_active_wallet(user_id, wallet_name)
            
            # Return the wallet data (without the private key)
            public_wallet_data: WalletData = {
                'name': wallet_name,
                'address': new_wallet_data['address'],
                'derivation_path': new_wallet_data['derivation_path']
            }
            
            # Increment the mnemonic index only on success
            increment_user_mnemonic_index(user_id)
            
            return public_wallet_data
        except Exception as e:
            logger.error(f"Error creating wallet for user {hash_user_id(user_id)}: {e}")
            logger.error(traceback.format_exc())
            return None
    
    def import_wallet(self, user_id: str, private_key: str, wallet_name: str, pin: Optional[str] = None) -> Optional[WalletData]:
        """
        Import a wallet from a private key.
        
        Args:
            user_id: The user ID to import the wallet for
            private_key: The private key to import
            wallet_name: The name for the imported wallet
            pin: PIN for encryption
            
        Returns:
            WalletData: The wallet information, or None if import failed
        """
        try:
            # Check if the wallet already exists
            existing_wallet: Optional[WalletData] = self.get_wallet_by_name(user_id, wallet_name, pin)
            if existing_wallet:
                logger.error(f"Wallet with name '{wallet_name}' already exists for user {hash_user_id(user_id)}")
                return None
            
            # Convert the private key to a checksum address
            # Strip '0x' prefix if present
            if private_key.startswith('0x'):
                private_key = private_key[2:]
            
            try:
                # Create an account from the private key
                account = self.w3.eth.account.from_key(private_key)
                address: str = account.address
            except Exception as e:
                logger.error(f"Invalid private key: {e}")
                return None
            
            # Check if a wallet with this address already exists for the user
            existing_wallet_by_address: Optional[WalletData] = self.get_wallet_by_address(user_id, address, pin)
            if existing_wallet_by_address:
                logger.error(f"Wallet with address '{address}' already exists for user {hash_user_id(user_id)}")
                return None
            
            # Create the wallet data
            wallet_data: WalletData = {
                'name': wallet_name,
                'address': address,
                'private_key': private_key,
                'is_imported': True
            }
            
            # Save the wallet
            success: bool = self.save_user_wallet(user_id, wallet_data, wallet_name, pin)
            if not success:
                logger.error(f"Failed to save wallet '{wallet_name}' for user {hash_user_id(user_id)}")
                return None
            
            # Get all current wallets to check if this is the first one
            wallets_all: Dict[str, WalletData] = db_get_user_wallets_with_keys(user_id, pin)
            
            # If this is the first wallet, set it as active
            if len(wallets_all) == 1:
                self.set_active_wallet(user_id, wallet_name)
            
            # Return the wallet data (without the private key)
            public_wallet_data: WalletData = {
                'name': wallet_name,
                'address': address,
                'is_imported': True
            }
            
            return public_wallet_data
        except Exception as e:
            logger.error(f"Error importing wallet for user {hash_user_id(user_id)}: {e}")
            logger.error(traceback.format_exc())
            return None
    
    def rename_wallet(self, user_id: str, old_name: str, new_name: str, pin: Optional[str] = None) -> bool:
        """
        Rename a wallet.
        
        Args:
            user_id: The user ID of the wallet owner
            old_name: The current name of the wallet
            new_name: The new name for the wallet
            pin: PIN for encryption/decryption if needed
            
        Returns:
            bool: True if the wallet was renamed successfully, False otherwise
        """
        try:
            # Get the wallet data
            wallet_data: Optional[WalletData] = self.get_wallet_by_name(user_id, old_name, pin)
            if not wallet_data:
                logger.error(f"Wallet '{old_name}' not found for user {hash_user_id(user_id)}")
                return False
            
            # Check if a wallet with the new name already exists
            existing_wallet: Optional[WalletData] = self.get_wallet_by_name(user_id, new_name)
            if existing_wallet:
                logger.error(f"Wallet with name '{new_name}' already exists for user {hash_user_id(user_id)}")
                return False
            
            # Update the wallet name in the data
            wallet_data['name'] = new_name
            
            # Save the wallet with the new name
            success: bool = self.save_user_wallet(user_id, wallet_data, new_name, pin)
            if not success:
                logger.error(f"Failed to save wallet with new name '{new_name}' for user {hash_user_id(user_id)}")
                return False
            
            # Delete the old wallet
            success = db_delete_user_wallet(user_id, old_name)
            if not success:
                logger.error(f"Failed to delete wallet with old name '{old_name}' for user {hash_user_id(user_id)}")
                # Don't return False here, since the wallet was saved with the new name
            
            # Check if the renamed wallet was the active wallet
            active_wallet_name: Optional[str] = self.get_active_wallet_name(user_id)
            if active_wallet_name == old_name:
                # Update the active wallet name
                self.set_active_wallet(user_id, new_name)
            
            return True
        except Exception as e:
            logger.error(f"Error renaming wallet for user {hash_user_id(user_id)}: {e}")
            logger.error(traceback.format_exc())
            return False
    
    def delete_wallet(self, user_id: str, wallet_name: str) -> bool:
        """
        Delete a wallet.
        
        Args:
            user_id: The user ID of the wallet owner
            wallet_name: The name of the wallet to delete
            
        Returns:
            bool: True if the wallet was deleted successfully, False otherwise
        """
        try:
            # Check if the wallet exists
            wallet: Optional[WalletData] = self.get_wallet_by_name(user_id, wallet_name)
            if not wallet:
                logger.error(f"Wallet '{wallet_name}' not found for user {hash_user_id(user_id)}")
                return False
            
            # Delete the wallet
            success: bool = db_delete_user_wallet(user_id, wallet_name)
            if not success:
                logger.error(f"Failed to delete wallet '{wallet_name}' for user {hash_user_id(user_id)}")
                return False
            
            # If the deleted wallet was the active wallet, set a new active wallet
            active_wallet_name: Optional[str] = self.get_active_wallet_name(user_id)
            if active_wallet_name == wallet_name:
                # Get all remaining wallets
                wallets: Dict[str, WalletData] = db_get_user_wallets(user_id)
                
                if wallets:
                    # Set the first available wallet as active
                    new_active_wallet: str = next(iter(wallets))
                    self.set_active_wallet(user_id, new_active_wallet)
                    logger.info(f"Set new active wallet '{new_active_wallet}' for user {hash_user_id(user_id)}")
                else:
                    # No wallets left, clear the active wallet
                    logger.info(f"No wallets left for user {hash_user_id(user_id)}, clearing active wallet")
            
            return True
        except Exception as e:
            logger.error(f"Error deleting wallet for user {hash_user_id(user_id)}: {e}")
            logger.error(traceback.format_exc())
            return False
        
    def delete_wallets_all(self, user_id: str, pin: Optional[str] = None) -> bool:
        """
        Delete all wallets for a user.
        
        Args:
            user_id (str): The user ID to delete wallets for
            pin (Optional[str], optional): PIN for decryption
            
        Returns:
            bool: True if all wallets were deleted successfully, False otherwise
        """
        try:
            from db.wallet import delete_user_wallet, get_user_wallets
            from db.mnemonic import delete_user_mnemonic
            
            # Get all user wallets
            wallets = get_user_wallets(user_id)
            
            # Delete each wallet individually
            success_wallets = True
            for wallet_name, wallet_data in wallets.items():
                if not delete_user_wallet(user_id, wallet_name):
                    logger.error(f"Failed to delete wallet {wallet_name} for user {hash_user_id(user_id)}")
                    success_wallets = False
            
            if not success_wallets:
                logger.error(f"Failed to delete all wallets for user {hash_user_id(user_id)}")
                return False
            
            # Delete the mnemonic
            success_mnemonic: bool = delete_user_mnemonic(user_id)
            if not success_mnemonic:
                logger.error(f"Failed to delete mnemonic for user {hash_user_id(user_id)}")
                return False
            
            return True
        except Exception as e:
            logger.error(f"Error deleting all wallets for user {hash_user_id(user_id)}: {e}")
            logger.error(traceback.format_exc())
            return False
    
    def set_active_wallet(self, user_id: str, wallet_name: str) -> bool:
        """
        Set a wallet as the active wallet.
        
        Args:
            user_id (str): The user ID
            wallet_name (str): The wallet name
            
        Returns:
            bool: True if successful, False otherwise
        """
        return db_set_active_wallet(user_id, wallet_name)
    
    async def get_wallet_balance(self, wallet_address: str, token_address: Optional[str] = None) -> int:
        """
        Get the balance of a wallet.
        
        Args:
            wallet_address (str): The wallet address to get the balance for
            token_address (Optional[str], optional): The token address to get the balance for,
                if None, will get the BNB balance
                
        Returns:
            int: The balance of the wallet in the smallest unit (wei for BNB, token units for tokens)
        """
        try:
            if token_address is None or token_address == 'BNB':
                # Get native BNB balance
                # Convert the string to checksummed address format expected by web3
                checksum_address = self.w3.to_checksum_address(wallet_address)
                native_balance: int = self.w3.eth.get_balance(checksum_address)
                return native_balance
            else:
                # Get token balance
                if not self.w3.is_address(token_address):
                    logger.error(f"Invalid token address: {token_address}")
                    return 0
                    
                token_address = self.w3.to_checksum_address(token_address)
                checksum_wallet_address = self.w3.to_checksum_address(wallet_address)
                
                # Get token contract
                token_contract = self.w3.eth.contract(address=token_address, abi=ERC20_ABI)
                
                # Get token balance
                token_balance: int = token_contract.functions.balanceOf(checksum_wallet_address).call()
                return token_balance
        except Exception as e:
            logger.error(f"Error getting wallet balance for {wallet_address}: {e}")
            logger.error(traceback.format_exc())
            return 0

# Create a singleton instance
wallet_manager: WalletManager = WalletManager() 