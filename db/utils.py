"""
Utility functions for database operations, including encryption and decryption.
"""
import base64
import hashlib
import logging
import os
import traceback
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from utils.config import ENCRYPTION_KEY

# Configure module logger
logger = logging.getLogger(__name__)

def get_encryption_key(salt, user_id=None, pin=None):
    """
    Generate a Fernet encryption key based on user_id, optional PIN, and salt.
    Uses PIN if provided or if user has one set.
    
    Args:
        salt (bytes): Salt for key derivation
        user_id: User identifier (additional entropy)
        pin (str, optional): User's PIN for additional security
        
    Returns:
        bytes: A Fernet-compatible 32-byte key
    """
    # Convert user_id to string and encode to bytes
    user_id_bytes = str(user_id).encode() if user_id else b"default_user"
    
    # If a PIN is provided directly, use it
    if pin:
        # Combine user_id and PIN for better security
        pin_bytes = str(pin).encode()
        combined_input = user_id_bytes + b":" + pin_bytes
        password = hashlib.sha256(combined_input).digest()
    else:
        # Move the import inside the function to break circular dependency
        from db.pin import get_user_pin_hash
        
        # If no PIN provided, check if user has a PIN hash stored
        pin_hash = get_user_pin_hash(user_id) if user_id else None
        
        if pin_hash:
            # If user has a PIN hash, incorporate it
            pin_hash_bytes = pin_hash.encode()
            combined_input = user_id_bytes + b":" + pin_hash_bytes
            password = hashlib.sha256(combined_input).digest()
        else:
            # Fallback to just user_id if no PIN
            password = hashlib.sha256(user_id_bytes).digest()
    
    # Use PBKDF2 to derive a secure key
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,  # 32 bytes = 256 bits
        salt=salt,
        iterations=100000,  # Recommended minimum by OWASP
    )
    
    key = base64.urlsafe_b64encode(kdf.derive(password))
    return key

def encrypt_data(data, user_id=None, pin=None):
    """
    Encrypt data using Fernet symmetric encryption.
    
    Args:
        data (str): The data to encrypt
        user_id: User identifier for key derivation
        pin (str, optional): User's PIN for additional security
        
    Returns:
        str: Base64-encoded encrypted data with salt
    """
    if not data:
        return None
    
    try:
        # Generate a random salt for this encryption
        salt = os.urandom(16)
        
        # Get encryption key
        key = get_encryption_key(salt, user_id, pin)
        
        # Create a Fernet cipher and encrypt
        f = Fernet(key)
        encrypted_data = f.encrypt(data.encode())
        
        # Combine salt and encrypted data, then encode to base64
        combined = salt + encrypted_data
        return base64.b64encode(combined).decode('utf-8')
    except Exception as e:
        logger.error(f"Encryption error: {e}")
        logger.error(traceback.format_exc())
        return None

def decrypt_data(encrypted_data, user_id=None, pin=None):
    """
    Decrypt Fernet-encrypted data.
    
    Args:
        encrypted_data (str): Base64-encoded encrypted data with salt
        user_id: User identifier for key derivation
        pin (str, optional): User's PIN for additional security
        
    Returns:
        str: Decrypted data as string or None if decryption fails
    """
    if not encrypted_data:
        return None
    
    try:
        # Decode from base64
        decoded = base64.b64decode(encrypted_data)
        
        # Extract salt (first 16 bytes) and ciphertext
        salt = decoded[:16]
        ciphertext = decoded[16:]
        
        # Get encryption key
        key = get_encryption_key(salt, user_id, pin)
        
        # Create a Fernet cipher and decrypt
        f = Fernet(key)
        decrypted_data = f.decrypt(ciphertext).decode('utf-8')
        
        return decrypted_data
    except Exception as e:
        logger.error(f"Decryption error: {e}")
        logger.error(traceback.format_exc())
        return None

def hash_user_id(user_id):
    """
    Create an irreversible hash of a user ID for database storage.
    
    Args:
        user_id: User identifier (int or str)
        
    Returns:
        str: Hexadecimal SHA-256 hash of the user ID
    """
    # Convert to string and encode to bytes
    user_id_str = str(user_id).encode('utf-8')
    
    # Create SHA-256 hash
    hashed = hashlib.sha256(user_id_str).hexdigest()
    
    return hashed 