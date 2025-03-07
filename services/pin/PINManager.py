"""
PINManager - Centralized service for managing PIN-related operations.

This service provides a clean, simple API for:
- Verifying PINs
- Storing verified PINs
- Retrieving stored PINs 
- Managing PIN expiration
- Checking if a user has a PIN

All PIN-related operations should go through this service to maintain
consistency and avoid duplication of logic across the codebase.
"""
import logging
import time
import threading
import traceback
from db.pin import has_pin, verify_pin as db_verify_pin, save_user_pin
from db.mnemonic import get_user_mnemonic, save_user_mnemonic
from db.wallet import get_user_wallets_with_keys, save_user_wallet
from db.utils import hash_user_id

logger = logging.getLogger(__name__)

class PINManager:
    """
    Singleton service for centralized PIN management.
    
    This class is responsible for all PIN-related operations, including
    verification, storage, retrieval, and expiration. It provides a clean
    API for other parts of the codebase to interact with.
    """
    _instance = None
    _lock = threading.RLock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                logger.info("Creating PINManager singleton instance")
                cls._instance = super(PINManager, cls).__new__(cls)
                cls._instance._initialize()
            return cls._instance
    
    def _initialize(self):
        """Initialize the PINManager instance."""
        self._pin_store = {}  # {user_id: {"pin": str, "timestamp": float}}
        self._expiration_time = 30 * 60  # 30 minutes by default
        self._start_cleanup_thread()
        logger.debug("PINManager initialized")
    
    def _start_cleanup_thread(self):
        """Start a background thread to periodically clean up expired PINs."""
        def cleanup_thread():
            logger.info("Starting PIN cleanup background thread")
            while True:
                try:
                    # Sleep for 5 minutes
                    time.sleep(5 * 60)
                    self.clear_expired_pins()
                except Exception as e:
                    logger.error(f"Error in PIN cleanup thread: {e}")
                    logger.error(traceback.format_exc())
        
        thread = threading.Thread(target=cleanup_thread, daemon=True)
        thread.start()
    
    def needs_pin(self, user_id):
        """
        Check if a user has a PIN set and therefore needs PIN verification.
        
        Args:
            user_id: The user ID to check
            
        Returns:
            bool: True if the user has a PIN set, False otherwise
        """
        return has_pin(user_id)
    
    def verify_pin(self, user_id, pin):
        """
        Verify if a PIN is correct for a user.
        If the PIN is valid, it will also be stored for future use.
        
        Args:
            user_id: The user ID to verify the PIN for
            pin: The PIN to verify
            
        Returns:
            bool: True if the PIN is valid, False otherwise
        """
        user_id_str = hash_user_id(user_id)
        logger.debug(f"Verifying PIN for user {user_id_str}")
        
        # Don't verify if user doesn't have a PIN
        if not self.needs_pin(user_id):
            logger.debug(f"No PIN set for user {user_id_str}, skipping verification")
            return True
        
        # Verify the PIN using the database function
        valid = db_verify_pin(user_id, pin)
        
        if valid:
            logger.info(f"PIN verified successfully for user {user_id_str}")
            # Store the verified PIN
            self.store_pin(user_id, pin)
            return True
        else:
            logger.warning(f"Invalid PIN provided for user {user_id_str}")
            return False
    
    def store_pin(self, user_id, pin, expiration_time=None):
        """
        Store a verified PIN for future use.
        
        Args:
            user_id: The user ID to store the PIN for
            pin: The PIN to store
            expiration_time: Custom expiration time in seconds (optional)
            
        Returns:
            bool: True if the PIN was stored successfully
        """
        if expiration_time is None:
            expiration_time = self._expiration_time
            
        user_id_str = hash_user_id(user_id)
        logger.debug(f"Storing PIN for user {user_id_str}")
        
        with self._lock:
            self._pin_store[user_id] = {
                "pin": pin,
                "timestamp": time.time(),
                "expiration": expiration_time
            }
        
        return True
    
    def set_pin(self, user_id, pin):
        """
        Set a PIN for a user.
        """
        try:
            # Must reencrypt mnemonic and private keys
            old_pin = None
            if self.has_pin(user_id):
                old_pin = self.get_pin(user_id)
            mnemonic = get_user_mnemonic(user_id, old_pin)
            wallets_all = get_user_wallets_with_keys(user_id, old_pin)
            
            # Save the PIN first
            save_user_pin(user_id, pin)
            
            # Save the mnemonic with the new PIN
            if mnemonic:
                save_user_mnemonic(user_id, mnemonic, pin)
            
            # Save each wallet with the new PIN
            for wallet in wallets_all:
                wallet_name = wallet.get('name', 'Default')
                save_user_wallet(user_id, wallet, wallet_name, pin)
            
            # Store the PIN in the PIN manager
            self.store_pin(user_id, pin)
            
            return True, None
        except Exception as e:
            logger.error(f"Error setting PIN for user {hash_user_id(user_id)}: {e}")
            logger.error(traceback.format_exc())
            return False, str(e)
    
    def get_pin(self, user_id):
        """
        Get a stored PIN if it exists and hasn't expired.
        
        Args:
            user_id: The user ID to get the PIN for
            
        Returns:
            str: The stored PIN, or None if not found or expired
        """
        user_id_str = hash_user_id(user_id)
        
        with self._lock:
            if user_id in self._pin_store:
                pin_data = self._pin_store[user_id]
                current_time = time.time()
                
                # Check if the PIN has expired
                if current_time - pin_data["timestamp"] < pin_data.get("expiration", self._expiration_time):
                    logger.debug(f"Retrieved valid PIN for user {user_id_str}")
                    return pin_data["pin"]
                else:
                    # PIN has expired, remove it
                    logger.debug(f"PIN for user {user_id_str} has expired, removing")
                    del self._pin_store[user_id]
        
        logger.debug(f"No valid PIN found for user {user_id_str}")
        return None
    
    def clear_pin(self, user_id):
        """
        Clear a stored PIN for a user.
        
        Args:
            user_id: The user ID to clear the PIN for
            
        Returns:
            bool: True if the PIN was cleared, False if no PIN was found
        """
        user_id_str = hash_user_id(user_id)
        logger.debug(f"Clearing PIN for user {user_id_str}")
        
        with self._lock:
            if user_id in self._pin_store:
                del self._pin_store[user_id]
                logger.debug(f"PIN cleared for user {user_id_str}")
                return True
        
        return False
    
    def clear_expired_pins(self):
        """
        Clear all expired PINs from storage.
        
        Returns:
            int: The number of expired PINs that were cleared
        """
        cleared_count = 0
        current_time = time.time()
        
        with self._lock:
            user_ids_to_remove = []
            
            # Identify expired PINs
            for user_id, pin_data in self._pin_store.items():
                expiration = pin_data.get("expiration", self._expiration_time)
                if current_time - pin_data["timestamp"] >= expiration:
                    user_ids_to_remove.append(user_id)
            
            # Remove expired PINs
            for user_id in user_ids_to_remove:
                del self._pin_store[user_id]
                cleared_count += 1
                user_id_str = hash_user_id(user_id)
                logger.debug(f"Cleared expired PIN for user {user_id_str}")
        
        if cleared_count > 0:
            logger.info(f"Cleared {cleared_count} expired PINs")
        
        return cleared_count
    
    def get_pin_count(self):
        """
        Get the number of currently stored PINs.
        
        Returns:
            int: The number of stored PINs
        """
        with self._lock:
            return len(self._pin_store)\
    
    def has_pin(self, user_id):
        """
        Check if a user has a PIN set.
        """
        return self.needs_pin(user_id)

# Create and export singleton instance
pin_manager = PINManager() 