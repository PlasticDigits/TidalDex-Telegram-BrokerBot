"""
Utility functions for database operations, including encryption and decryption.
"""
import base64
import hashlib
import logging
import os
import traceback
from typing import Optional, Union, Any, Dict, List, Tuple, cast
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from utils.config import ENCRYPTION_KEY

# Configure module logger
logger = logging.getLogger(__name__)

def get_encryption_key(salt: bytes, user_id: Union[int, str], pin: Optional[str] = None) -> bytes:
    """
    Generate a Fernet encryption key based on user_id, optional PIN, and salt.
    Uses PIN if provided or if user has one set.
    
    Args:
        salt: Salt for key derivation
        user_id: User identifier (additional entropy)
        pin: User's PIN for additional security
        
    Returns:
        A Fernet-compatible 32-byte key
    """
    # Convert user_id to string and encode to bytes
    user_id_bytes: bytes = str(user_id).encode() if user_id else b"default_user"
    
    # Ensure ENCRYPTION_KEY is in bytes format
    encryption_key_bytes: bytes = ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY
    
    # Default combined input with encryption key and user ID
    combined_input: bytes = encryption_key_bytes + b":" + user_id_bytes
    
    # If a PIN is provided directly, use it
    if pin:
        # Log that we're using a provided PIN
        logger.debug(f"Using provided PIN for encryption/decryption for user {hash_user_id(user_id)}")
        # Combine user_id and PIN for better security
        pin_bytes: bytes = str(pin).encode()
        combined_input = user_id_bytes + b":" + pin_bytes

    password: bytes = hashlib.sha256(combined_input).digest()
    
    # Use PBKDF2 to derive a secure key
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,  # 32 bytes = 256 bits
        salt=salt,
        iterations=100000,  # Recommended minimum by OWASP
    )
    
    key: bytes = base64.urlsafe_b64encode(kdf.derive(password))
    return key

def encrypt_data(data: str, user_id: Union[int, str], pin: Optional[str] = None) -> Optional[str]:
    """
    Encrypt data using Fernet symmetric encryption.
    
    Args:
        data: The data to encrypt
        user_id: User identifier for key derivation
        pin: User's PIN for additional security
        
    Returns:
        Base64-encoded encrypted data with salt, or None if encryption fails
    """
    if not data:
        return None
    
    try:
        # Generate a random salt for this encryption
        salt: bytes = os.urandom(16)
        
        # Get encryption key
        key: bytes = get_encryption_key(salt, user_id, pin)
        
        # Create a Fernet cipher and encrypt
        f = Fernet(key)
        encrypted_data: bytes = f.encrypt(data.encode())
        
        # Combine salt and encrypted data, then encode to base64
        combined: bytes = salt + encrypted_data
        return base64.b64encode(combined).decode('utf-8')
    except Exception as e:
        logger.error(f"Encryption error: {e}")
        logger.error(traceback.format_exc())
        return None

def decrypt_data(encrypted_data: str, user_id: Union[int, str], pin: Optional[str] = None) -> Optional[str]:
    """
    Decrypt Fernet-encrypted data.
    
    Args:
        encrypted_data: Base64-encoded encrypted data with salt
        user_id: User identifier for key derivation
        pin: User's PIN for additional security
        
    Returns:
        Decrypted data as string or None if decryption fails
    """
    if not encrypted_data:
        logger.warning(f"No encrypted data provided for user {hash_user_id(user_id)}")
        return None
    
    try:
        # Decode from base64
        decoded: bytes = base64.b64decode(encrypted_data)
        
        # Extract salt (first 16 bytes) and ciphertext
        salt: bytes = decoded[:16]
        ciphertext: bytes = decoded[16:]
        
        # Get encryption key
        key: bytes = get_encryption_key(salt, user_id, pin)
        
        # Create a Fernet cipher and decrypt
        f = Fernet(key)
        
        try:
            decrypted_data: str = f.decrypt(ciphertext).decode('utf-8')
            logger.debug(f"Successfully decrypted data for user {hash_user_id(user_id)}")
            return decrypted_data
        except Exception as e:
            logger.error(f"Decryption failed for user {hash_user_id(user_id)}: {e}")
            return None
    except Exception as e:
        logger.error(f"Error in decrypt_data for user {hash_user_id(user_id)}: {e}")
        logger.error(traceback.format_exc())
        return None

def is_data_encrypted(data: str) -> bool:
    """
    Check if data appears to be encrypted (base64-encoded with salt).
    
    Args:
        data: The data to check
        
    Returns:
        True if data appears encrypted, False otherwise
    """
    if not data:
        return False
    
    try:
        # Encrypted data should be base64-encoded
        decoded = base64.b64decode(data)
        # Should have at least 16 bytes for salt + some encrypted content
        return len(decoded) > 16
    except Exception:
        # If base64 decoding fails, it's likely plain text
        return False

def encrypt_address(address: str, user_id: Union[int, str], pin: Optional[str] = None) -> Optional[str]:
    """
    Encrypt a wallet address using the same encryption as other sensitive data.
    
    Args:
        address: The wallet address to encrypt
        user_id: User identifier for key derivation
        pin: User's PIN for additional security
        
    Returns:
        Encrypted address or None if encryption fails
    """
    if not address:
        return None
    
    # Use the same encryption as private keys
    return encrypt_data(address, user_id, pin)

def decrypt_address(encrypted_address: str, user_id: Union[int, str], pin: Optional[str] = None) -> Optional[str]:
    """
    Decrypt a wallet address.
    
    Args:
        encrypted_address: The encrypted address
        user_id: User identifier for key derivation
        pin: User's PIN for additional security
        
    Returns:
        Decrypted address or None if decryption fails
    """
    if not encrypted_address:
        return None
    
    # Use the same decryption as private keys
    return decrypt_data(encrypted_address, user_id, pin)

def get_address_for_storage_and_retrieval(address: str, user_id: Union[int, str], pin: Optional[str] = None) -> Tuple[Optional[str], bool]:
    """
    Handle address encryption for storage, with backwards compatibility support.
    Also handles migration scenarios where addresses may be encrypted with or without PIN.
    
    Args:
        address: The address (could be plain text or encrypted)
        user_id: User identifier
        pin: User's PIN
        
    Returns:
        Tuple of (processed_address, was_encrypted)
    """
    if not address:
        return None, False
    
    # Check if address is already encrypted
    if is_data_encrypted(address):
        # Try to decrypt to validate it's a valid encrypted address
        # First try with PIN (normal case)
        if pin:
            decrypted = decrypt_address(address, user_id, pin)
            if decrypted:
                # Valid encrypted address with PIN, return as-is
                return address, True
        
        # Try without PIN (migration case)
        decrypted_no_pin = decrypt_address(address, user_id, None)
        if decrypted_no_pin:
            # Valid encrypted address without PIN, return as-is
            return address, True
        
        # If we can't decrypt it with either method, it may be corrupted
        logger.warning(f"Found encrypted address that cannot be decrypted for user {hash_user_id(user_id)}")
        return address, True  # Still treat as encrypted, but may be problematic
    
    # Plain text address, encrypt it
    encrypted = encrypt_address(address, user_id, pin)
    return encrypted, False

def get_address_for_display(stored_address: str, user_id: Union[int, str], pin: Optional[str] = None) -> Optional[str]:
    """
    Get address for display, handling both encrypted and plain text addresses.
    Also handles addresses encrypted during migration (without PIN) vs normal operation (with PIN).
    
    Args:
        stored_address: The address as stored in database
        user_id: User identifier
        pin: User's PIN
        
    Returns:
        Plain text address for display
    """
    if not stored_address:
        return None
    
    # Check if address is encrypted
    if is_data_encrypted(stored_address):
        # Try to decrypt with PIN first (normal case)
        if pin:
            decrypted = decrypt_address(stored_address, user_id, pin)
            if decrypted:
                return decrypted
        
        # If PIN decryption failed or no PIN, try without PIN (migration case)
        decrypted_no_pin = decrypt_address(stored_address, user_id, None)
        if decrypted_no_pin:
            logger.debug(f"Successfully decrypted address without PIN for user {hash_user_id(user_id)} (migration case)")
            return decrypted_no_pin
        
        # If both attempts failed, log the error
        logger.error(f"Failed to decrypt address for user {hash_user_id(user_id)} with both PIN and without PIN")
        return None
    else:
        # Plain text, return as-is (backwards compatibility)
        return stored_address

def hash_user_id(user_id: Union[int, str]) -> str:
    """
    Create an irreversible hash of a user ID for database storage.
    
    Args:
        user_id: User identifier (int or str)
        
    Returns:
        Hexadecimal SHA-256 hash of the user ID
    """
    
    # Convert to string and encode to bytes
    user_id_str: bytes = str(user_id).encode('utf-8')
    
    # Create SHA-256 hash
    hashed: str = hashlib.sha256(user_id_str).hexdigest()
    
    return hashed 

def hash_pin(pin: str) -> str:
    """
    Create an irreversible hash of a PIN for database storage.
    
    Args:
        PIN: pin (str)
        
    Returns:
        Hexadecimal SHA-256 hash of the PIN
    """
    # Convert to string and encode to bytes
    pin_str: bytes = str(pin).encode('utf-8')
    
    # Create SHA-256 hash
    hashed: str = hashlib.sha256(pin_str).hexdigest()
    
    return hashed

def migrate_wallet_addresses() -> Tuple[bool, str]:
    """
    Migrate existing plain-text wallet addresses to encrypted format.
    
    This function handles backwards compatibility by:
    1. Finding all wallets with plain-text addresses
    2. Encrypting them with the user's PIN (if available)
    3. Updating the database with encrypted addresses
    
    Returns:
        Tuple of (success, message)
    """
    try:
        from db.connection import execute_query
        from db.pin import has_pin
        from services.pin.PINManager import pin_manager
        
        logger.info("Starting wallet address migration...")
        
        # Get all wallets
        all_wallets = execute_query(
            "SELECT id, user_id, address, name FROM wallets",
            fetch='all'
        )
        
        if not all_wallets or not isinstance(all_wallets, list):
            return True, "No wallets found to migrate"
        
        migrated_count = 0
        skipped_count = 0
        error_count = 0
        
        for wallet in all_wallets:
            if not isinstance(wallet, dict):
                continue
                
            wallet_id = wallet.get('id')
            user_id_str = wallet.get('user_id')
            stored_address = wallet.get('address')
            wallet_name = wallet.get('name', 'Unknown')
            
            if not wallet_id or not user_id_str or not stored_address:
                continue
            
            # Check if address is already encrypted
            if is_data_encrypted(stored_address):
                skipped_count += 1
                logger.debug(f"Skipping already encrypted address for wallet {wallet_name}")
                continue
            
            try:
                # Try to get the original user ID from the hash (not possible, so we'll work with hashed ID)
                # We need to determine if the user has a PIN
                pin = None
                
                # Check if user has a PIN in the database
                if has_pin(user_id_str):
                    # Try to get PIN from PINManager if user is currently active
                    # Note: This migration should ideally be run when users are not active
                    # or we should prompt for PIN during migration
                    logger.warning(f"User {user_id_str[:10]}... has PIN but migration cannot access it. Address will be encrypted without PIN.")
                
                # Encrypt the address
                encrypted_address = encrypt_address(stored_address, user_id_str, pin)
                
                if encrypted_address:
                    # Update the database
                    execute_query(
                        "UPDATE wallets SET address = ? WHERE id = ?",
                        (encrypted_address, wallet_id)
                    )
                    migrated_count += 1
                    logger.debug(f"Migrated address for wallet {wallet_name} (user {user_id_str[:10]}...)")
                else:
                    logger.error(f"Failed to encrypt address for wallet {wallet_name}")
                    error_count += 1
                    
            except Exception as e:
                logger.error(f"Error migrating wallet {wallet_name}: {e}")
                error_count += 1
        
        message = f"Migration completed: {migrated_count} addresses encrypted, {skipped_count} already encrypted, {error_count} errors"
        logger.info(message)
        
        return error_count == 0, message
        
    except Exception as e:
        error_msg = f"Migration failed with error: {e}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        return False, error_msg

def migrate_user_wallet_addresses(user_id: Union[int, str], pin: Optional[str] = None) -> Tuple[bool, str]:
    """
    Migrate wallet addresses for a specific user.
    
    This is useful for migrating addresses when a user logs in and provides their PIN.
    
    Args:
        user_id: The user ID (will be hashed for database lookup)
        pin: The user's PIN for encryption
        
    Returns:
        Tuple of (success, message)
    """
    try:
        from db.connection import execute_query
        
        user_id_str = hash_user_id(user_id)
        logger.info(f"Starting wallet address migration for user {user_id_str[:10]}...")
        
        # Get all wallets for this user
        user_wallets = execute_query(
            "SELECT id, address, name FROM wallets WHERE user_id = ?",
            (user_id_str,),
            fetch='all'
        )
        
        if not user_wallets or not isinstance(user_wallets, list):
            return True, "No wallets found for user"
        
        migrated_count = 0
        skipped_count = 0
        error_count = 0
        
        for wallet in user_wallets:
            if not isinstance(wallet, dict):
                continue
                
            wallet_id = wallet.get('id')
            stored_address = wallet.get('address')
            wallet_name = wallet.get('name', 'Unknown')
            
            if not wallet_id or not stored_address:
                continue
            
            # Check if address is already encrypted
            if is_data_encrypted(stored_address):
                skipped_count += 1
                logger.debug(f"Skipping already encrypted address for wallet {wallet_name}")
                continue
            
            try:
                # Encrypt the address with the user's PIN
                encrypted_address = encrypt_address(stored_address, user_id, pin)
                
                if encrypted_address:
                    # Update the database
                    execute_query(
                        "UPDATE wallets SET address = ? WHERE id = ?",
                        (encrypted_address, wallet_id)
                    )
                    migrated_count += 1
                    logger.debug(f"Migrated address for wallet {wallet_name}")
                else:
                    logger.error(f"Failed to encrypt address for wallet {wallet_name}")
                    error_count += 1
                    
            except Exception as e:
                logger.error(f"Error migrating wallet {wallet_name}: {e}")
                error_count += 1
        
        message = f"User migration completed: {migrated_count} addresses encrypted, {skipped_count} already encrypted, {error_count} errors"
        logger.info(message)
        
        return error_count == 0, message
        
    except Exception as e:
        error_msg = f"User migration failed with error: {e}"
        logger.error(error_msg)
        logger.error(traceback.format_exc())
        return False, error_msg 