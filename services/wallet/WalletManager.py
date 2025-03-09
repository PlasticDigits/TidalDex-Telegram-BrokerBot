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
from typing import Dict, List, Optional, Any, Tuple
from utils.load_abi import ERC20_ABI
from mnemonic import Mnemonic

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
from db.mnemonic import get_user_mnemonic, save_user_mnemonic
from wallet.mnemonic import derive_wallet_from_mnemonic
from web3 import Web3
from utils.config import BSC_RPC_URL

logger = logging.getLogger(__name__)

class WalletManager:
    """
    Singleton service for centralized wallet management.
    
    This class is responsible for all wallet-related operations, including
    wallet creation, retrieval, and management.
    """
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(WalletManager, cls).__new__(cls)
                cls._instance._initialize()
            return cls._instance
    
    def _initialize(self):
        """Initialize the wallet manager."""
        self.w3 = Web3(Web3.HTTPProvider(BSC_RPC_URL))
        logger.info("WalletManager initialized")
    
    def get_active_wallet_name(self, user_id: str) -> Optional[str]:
        """
        Get the name of the active wallet for a user.
        
        Args:
            user_id (str): The user ID
            
        Returns:
            str: The name of the active wallet, or None if no active wallet
        """
        return db_get_active_wallet_name(user_id)
    
    def get_wallet_by_name(self, user_id: str, wallet_name: str, pin: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get a wallet by its name.
        
        Args:
            user_id (str): The user ID
            wallet_name (str): The wallet name
            pin (str, optional): PIN for decrypting private key
            
        Returns:
            dict: The wallet information, or None if not found
        """
        return db_get_wallet_by_name(user_id, wallet_name, pin)
    
    def get_wallet_by_address(self, user_id: str, address: str, pin: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get a wallet by its address.
        
        Args:
            user_id (str): The user ID
            address (str): The wallet address
            pin (str, optional): PIN for decrypting private key
            
        Returns:
            dict: The wallet information, or None if not found
        """
        return db_get_wallet_by_address(user_id, address, pin)
    

    def has_user_wallet(self, user_id, pin=None):
        """
        Check if a user has any wallets.
        
        Args:
            user_id: The user ID to check
            pin (str, optional): Not used, included for API consistency
            
        Returns:
            bool: True if the user has at least one wallet, False otherwise
        """
        return db_has_user_wallet(user_id, pin)
    
    def has_user_mnemonic(self, user_id):
        """
        Check if a user has a mnemonic.
        """
        return get_user_mnemonic(user_id) is not None
    
    def get_user_wallet(self, user_id: str, wallet_name: Optional[str] = None, pin: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get a user's wallet.
        
        Args:
            user_id (str): The user ID
            wallet_name (str, optional): The wallet name (uses active wallet if None)
            pin (str, optional): PIN for decrypting private key
            
        Returns:
            dict: The wallet information, or None if not found
        """
        return db_get_user_wallet(user_id, wallet_name, pin)
    
    def get_user_wallets(self, user_id: str, include_private_keys: bool = False, pin: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all wallets for a user.
        
        Args:
            user_id (str): The user ID
            include_private_keys (bool): Whether to include private keys
            pin (str, optional): PIN for decrypting private keys
            
        Returns:
            list: List of wallet information
        """
        if include_private_keys:
            return db_get_user_wallets_with_keys(user_id, pin)
        return db_get_user_wallets(user_id)
    
    def create_mnemonic(self, user_id: str, pin: Optional[str] = None) -> Optional[str]:
        """
        Create a new mnemonic for a user.
        """
        # first, check if the user has a mnmoenic
        # if so, throw an error
        if self.has_user_mnemonic(user_id):
            logger.error(f"User {user_id} already has a mnemonic")
            return None
        
        # create a new mnemonic using bip39
        mnemo = Mnemonic("english")
        mnemonic = mnemo.generate(strength=128)  # 12 words
        
        # save the mnemonic to the database
        save_user_mnemonic(user_id, mnemonic, pin)
        
        return mnemonic
    
    def create_wallet(self, user_id: str, wallet_name: str, pin: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Create a new wallet for a user.
        
        Args:
            user_id (str): The user ID
            wallet_name (str): The wallet name
            pin (str, optional): PIN for encrypting private key
            
        Returns:
            dict: The created wallet information, or None if creation failed
        """
        try:
            # Get or create mnemonic
            mnemonic = get_user_mnemonic(user_id, pin)
            if not mnemonic:
                mnemonic = self.create_mnemonic(user_id, pin)
            
            # Get existing wallets to determine the next index
            wallets = db_get_user_wallets(user_id)
            index = len(wallets)
            
            # Derive wallet from mnemonic
            wallet = derive_wallet_from_mnemonic(mnemonic, index)
            if not wallet:
                logger.error(f"Failed to derive wallet for user {user_id}")
                return None
            
            # Save wallet
            wallet_data = {
                'address': wallet['address'],
                'private_key': wallet['private_key'],
                'path': wallet['path']
            }
            
            success = db_save_user_wallet(user_id, wallet_data, wallet_name, pin)
            if not success:
                logger.error(f"Failed to save wallet for user {user_id}")
                return None
            
            # Set as active wallet if it's the first one
            if len(wallets) == 0:
                db_set_active_wallet(user_id, wallet_name)
            
            return wallet_data
        except Exception as e:
            logger.error(f"Error creating wallet for user {user_id}: {e}")
            logger.error(traceback.format_exc())
            return None
    
    def import_wallet(self, user_id: str, private_key: str, wallet_name: str, pin: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Import a wallet using a private key.
        
        Args:
            user_id (str): The user ID
            private_key (str): The private key
            wallet_name (str): The wallet name
            pin (str, optional): PIN for encrypting private key
            
        Returns:
            dict: The imported wallet information, or None if import failed
        """
        try:
            # Create account from private key
            if private_key.startswith('0x'):
                private_key = private_key[2:]
                
            account = self.w3.eth.account.from_key(private_key)
            address = account.address
            
            # Check if wallet with this address already exists
            existing_wallet = db_get_wallet_by_address(user_id, address)
            if existing_wallet:
                logger.warning(f"Wallet with address {address} already exists for user {user_id}")
                return None
            
            # Save wallet
            wallet_data = {
                'address': address,
                'private_key': private_key,
                'path': None,  # Imported wallets don't have a derivation path
                'name': wallet_name
            }
            
            success = db_save_user_wallet(user_id, wallet_data, wallet_name, pin)
            if not success:
                logger.error(f"Failed to save imported wallet for user {user_id}")
                return None
            
            # Set as active wallet if it's the first one
            wallets = db_get_user_wallets(user_id)
            if len(wallets) == 1:
                db_set_active_wallet(user_id, wallet_name)
            
            return wallet_data
        except Exception as e:
            logger.error(f"Error importing wallet for user {user_id}: {e}")
            logger.error(traceback.format_exc())
            return None
    
    def rename_wallet(self, user_id: str, old_name: str, new_name: str, pin: Optional[str] = None) -> bool:
        """
        Rename a wallet.
        
        Args:
            user_id (str): The user ID
            old_name (str): The current wallet name
            new_name (str): The new wallet name
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Get the wallet
            wallet = db_get_wallet_by_name(user_id, old_name)
            if not wallet:
                logger.error(f"Wallet {old_name} not found for user {user_id}")
                return False
            
            # Update the name
            wallet['name'] = new_name
            
            # Save the wallet
            success = db_save_user_wallet(user_id, wallet, new_name, pin)
            if not success:
                logger.error(f"Failed to save renamed wallet for user {user_id}")
                return False
            
            # Update active wallet if needed
            active_wallet_name = db_get_active_wallet_name(user_id)
            if active_wallet_name == old_name:
                db_set_active_wallet(user_id, new_name)
            
            return True
        except Exception as e:
            logger.error(f"Error renaming wallet for user {user_id}: {e}")
            logger.error(traceback.format_exc())
            return False
    
    def delete_wallet(self, user_id: str, wallet_name: str) -> bool:
        """
        Delete a wallet.
        
        Args:
            user_id (str): The user ID
            wallet_name (str): The wallet name
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Delete the wallet
            success = db_delete_user_wallet(user_id, wallet_name)
            if not success:
                logger.error(f"Failed to delete wallet {wallet_name} for user {user_id}")
                return False
            
            # If this was the active wallet, set another one as active
            active_wallet_name = db_get_active_wallet_name(user_id)
            if active_wallet_name == wallet_name:
                wallets = db_get_user_wallets(user_id)
                if wallets:
                    db_set_active_wallet(user_id, wallets[0]['name'])
            
            return True
        except Exception as e:
            logger.error(f"Error deleting wallet for user {user_id}: {e}")
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
            wallet_address (str): The wallet address
            token_address (str, optional): The token address (None for native BNB)
            
        Returns:
            int: The wallet balance
        """
        try:
            if not self.w3.is_address(wallet_address):
                logger.error(f"Invalid wallet address: {wallet_address}")
                return 0
                
            wallet_address = self.w3.to_checksum_address(wallet_address)
            
            if token_address is None:
                # Get native BNB balance
                balance = self.w3.eth.get_balance(wallet_address)
                return balance
            else:
                # Get token balance
                if not self.w3.is_address(token_address):
                    logger.error(f"Invalid token address: {token_address}")
                    return 0
                    
                token_address = self.w3.to_checksum_address(token_address)
                
                # Create contract instance
                contract = self.w3.eth.contract(address=token_address, abi=ERC20_ABI)
                
                # Call balanceOf function
                balance = contract.functions.balanceOf(wallet_address).call()
                return balance
        except Exception as e:
            logger.error(f"Error getting wallet balance for {wallet_address}: {e}")
            logger.error(traceback.format_exc())
            return 0

# Create a singleton instance
wallet_manager = WalletManager() 