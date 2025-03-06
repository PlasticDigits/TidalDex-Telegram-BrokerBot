"""
PIN operations utility module.
Handles PIN hashing and verification.
"""
import hashlib
import logging
from db.pin import get_user_pin_hash, save_user_pin as db_save_user_pin
import traceback

# Configure module logger
logger = logging.getLogger(__name__)

def hash_pin(pin):
    """
    Create an irreversible hash of a PIN for secure storage.
    
    Args:
        pin (str): The PIN to hash
        
    Returns:
        str: Hexadecimal SHA-256 hash of the PIN
    """
    if not pin:
        return None
        
    # Convert to string and encode to bytes
    pin_bytes = str(pin).encode('utf-8')
    
    # Create SHA-256 hash
    hashed = hashlib.sha256(pin_bytes).hexdigest()
    
    return hashed

def save_user_pin(user_id, pin):
    """
    Hash and save a user's PIN to the database.
    
    Args:
        user_id: The user ID
        pin (str): The PIN to save
        
    Returns:
        bool: True if successful, False otherwise
    """
    # Hash the PIN before storing
    pin_hash = hash_pin(pin)
    if not pin_hash:
        logger.warning(f"Invalid PIN provided for user {user_id}")
        return False
    
    # Save the hashed PIN to the database
    return db_save_user_pin(user_id, pin_hash)

def verify_pin(user_id, pin):
    """
    Verify if the provided PIN matches the stored PIN for the user.
    
    Args:
        user_id: The user ID
        pin (str): The PIN to verify
        
    Returns:
        bool: True if PIN matches, False otherwise
    """
    # Get the stored PIN hash
    stored_pin_hash = get_user_pin_hash(user_id)
    
    # If no PIN is set, return False
    if not stored_pin_hash:
        return False
        
    # Hash the provided PIN
    provided_pin_hash = hash_pin(pin)
    
    # Compare the hashes
    return stored_pin_hash == provided_pin_hash

def has_pin(user_id):
    """
    Check if the user has set a PIN.
    
    Args:
        user_id: The user ID
        
    Returns:
        bool: True if the user has a PIN, False otherwise
    """
    return get_user_pin_hash(user_id) is not None

def update_user_pin(user_id, old_pin, new_pin):
    """
    Update a user's PIN and re-encrypt all sensitive data with the new PIN.
    
    Args:
        user_id: The user ID
        old_pin (str): The user's current PIN
        new_pin (str): The new PIN to set
        
    Returns:
        bool: True if successful, False otherwise
    """
    # Verify the old PIN is correct first
    if not verify_pin(user_id, old_pin):
        logger.warning(f"Old PIN verification failed for user {user_id}")
        return False
    
    try:
        # Move imports inside the function to avoid circular dependencies
        # 1. Retrieve the mnemonic with the old PIN
        from db.mnemonic import get_user_mnemonic, save_user_mnemonic
        mnemonic = get_user_mnemonic(user_id)
        
        # 2. Retrieve wallet data with the old PIN
        from db.wallet import get_user_wallets, save_user_wallet
        wallets = get_user_wallets(user_id)
        
        # 3. Save the new PIN
        new_pin_hash = hash_pin(new_pin)
        if not db_save_user_pin(user_id, new_pin_hash):
            logger.error(f"Failed to save new PIN for user {user_id}")
            return False
            
        # 4. Re-encrypt and save the mnemonic with the new PIN
        if mnemonic:
            if not save_user_mnemonic(user_id, mnemonic):
                logger.error(f"Failed to re-encrypt mnemonic for user {user_id}")
                # Rollback to old PIN if this fails
                db_save_user_pin(user_id, hash_pin(old_pin))
                return False
        
        # 5. Re-encrypt and save each wallet with the new PIN
        if wallets:
            for wallet in wallets:
                wallet_data = wallet.get('data', {})
                wallet_name = wallet.get('name', 'Default')
                if wallet_data and not save_user_wallet(user_id, wallet_data, wallet_name):
                    logger.error(f"Failed to re-encrypt wallet {wallet_name} for user {user_id}")
                    # Rollback to old PIN if this fails
                    db_save_user_pin(user_id, hash_pin(old_pin))
                    return False
        
        logger.info(f"Successfully updated PIN and re-encrypted data for user {user_id}")
        return True
        
    except Exception as e:
        logger.error(f"Error updating PIN for user {user_id}: {e}")
        logger.error(traceback.format_exc())
        # Try to rollback to old PIN
        db_save_user_pin(user_id, hash_pin(old_pin))
        return False 