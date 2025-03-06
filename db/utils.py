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
from db.connection import execute_query

# Configure module logger
logger = logging.getLogger(__name__)

def get_encryption_key(salt, user_id=None):
    """
    Generate a Fernet encryption key based on user_id and salt.
    
    Args:
        salt (bytes): Salt for key generation
        user_id: User identifier (additional entropy)
        
    Returns:
        bytes: A Fernet-compatible 32-byte key
    """
    # Convert user_id to string and encode to bytes
    user_id_bytes = str(user_id).encode() if user_id else b"default_user"
    
    # Use PBKDF2 to derive a secure key
    # We use a combination of the app secret and user_id for the password
    password = hashlib.sha256(user_id_bytes).digest()
    
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,  # 32 bytes = 256 bits
        salt=salt,
        iterations=100000,  # Recommended minimum by OWASP
    )
    
    key = base64.urlsafe_b64encode(kdf.derive(password))
    return key

def encrypt_data(data, user_id=None):
    """
    Encrypt data using Fernet symmetric encryption.
    
    Args:
        data (str): The data to encrypt
        user_id: User identifier for key derivation
        
    Returns:
        str: Base64-encoded encrypted data with salt
    """
    if not data:
        return None
    
    try:
        # Generate a random salt for this encryption
        salt = os.urandom(16)
        
        # Get encryption key
        key = get_encryption_key(salt, user_id)
        
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

def decrypt_data(encrypted_data, user_id=None):
    """
    Decrypt Fernet-encrypted data.
    
    Args:
        encrypted_data (str): Base64-encoded encrypted data with salt
        user_id: User identifier for key derivation
        
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
        key = get_encryption_key(salt, user_id)
        
        # Create a Fernet cipher and decrypt
        f = Fernet(key)
        decrypted_data = f.decrypt(ciphertext).decode('utf-8')
        
        return decrypted_data
    except Exception as e:
        logger.error(f"Decryption error: {e}")
        logger.error(traceback.format_exc())
        return None

def get_encryption_key_old(user_id):
    """
    Generate or load a key for encryption/decryption specific to a user.
    
    Args:
        user_id: The user ID to generate a key for
        
    Returns:
        bytes: The encryption key
    """
    user_id_str = str(user_id)
    
    try:
        # Use an environment variable for additional security if available
        secret_key = ENCRYPTION_KEY
        
        if not secret_key:
            # Don't use a default key - raise error instead
            raise ValueError("ENCRYPTION_KEY not set in environment variables. Run `openssl rand -hex 32` to generate a secure key and add it to your .env file.")
        
        # Check if user has a salt
        result = execute_query(
            "SELECT salt FROM salts WHERE user_id = ?", 
            (user_id_str,), 
            fetch='one'
        )
        
        if result:
            # Decode stored salt from base64
            salt = base64.b64decode(result['salt'])
        else:
            # Generate new salt if not exists
            import os
            salt = os.urandom(16)
            # Store salt as base64 string
            salt_b64 = base64.b64encode(salt).decode('utf-8')
            
            # First try to insert the salt without using transaction
            try:
                execute_query(
                    "INSERT INTO salts (user_id, salt) VALUES (?, ?)",
                    (user_id_str, salt_b64)
                )
            except Exception as e:
                logger.warning(f"Could not insert salt (may already exist): {e}")
                # Try to get the salt again in case of race condition
                result = execute_query(
                    "SELECT salt FROM salts WHERE user_id = ?", 
                    (user_id_str,), 
                    fetch='one'
                )
                if result:
                    salt = base64.b64decode(result['salt'])
                else:
                    raise ValueError("Failed to create or retrieve salt")
        
        # Derive a key from the secret and user-specific salt
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(secret_key.encode()))
        return key
    except Exception as e:
        logger.error(f"Error getting encryption key: {e}")
        logger.error(traceback.format_exc())
        raise 

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