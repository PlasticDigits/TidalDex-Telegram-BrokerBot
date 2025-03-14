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
        logger.debug(f"Using provided PIN for encryption/decryption for user {user_id}")
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