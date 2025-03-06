import json
import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from utils.config import ENCRYPTION_KEY

# Simple file-based storage for user wallets
DB_FILE = 'wallets.json'
# File for storing user salts
SALTS_FILE = '.salts.json'

def load_salts():
    """Load salts from file"""
    if os.path.exists(SALTS_FILE):
        with open(SALTS_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                # Return empty dict if file is corrupted
                return {}
    return {}

def save_salts(salts_data):
    """Save salts to file"""
    with open(SALTS_FILE, 'w') as f:
        json.dump(salts_data, f)

def get_encryption_key(user_id):
    """Generate or load a key for encryption/decryption specific to a user"""
    # Use an environment variable for additional security if available
    secret_key = ENCRYPTION_KEY
    
    if not secret_key:
        # Don't use a default key - raise error instead
        raise ValueError("ENCRYPTION_KEY not set in environment variables. Run `openssl rand -hex 32` to generate a secure key and add it to your .env file.")
    
    # Load salts
    salts = load_salts()
    user_id_str = str(user_id)
    
    # Create or load salt for this user
    if user_id_str in salts:
        # Decode stored salt from base64
        salt = base64.b64decode(salts[user_id_str])
    else:
        # Generate new salt if not exists
        salt = os.urandom(16)
        # Store salt as base64 string
        salts[user_id_str] = base64.b64encode(salt).decode('utf-8')
        save_salts(salts)
    
    # Derive a key from the secret and user-specific salt
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(secret_key.encode()))
    return key

def encrypt_private_key(private_key, user_id):
    """Encrypt a private key using user-specific salt"""
    if not private_key:
        return None
    
    # Initialize Fernet cipher with the user-specific encryption key
    cipher = Fernet(get_encryption_key(user_id))
    
    # Encrypt the private key
    encrypted_key = cipher.encrypt(private_key.encode())
    
    # Return the encrypted key as a base64 string
    return base64.b64encode(encrypted_key).decode('utf-8')

def decrypt_private_key(encrypted_key, user_id):
    """Decrypt a private key using user-specific salt"""
    if not encrypted_key:
        return None
    
    try:
        # Decode from base64 string
        encrypted_bytes = base64.b64decode(encrypted_key)
        
        # Initialize Fernet cipher with the user-specific encryption key
        cipher = Fernet(get_encryption_key(user_id))
        
        # Decrypt the private key
        decrypted_key = cipher.decrypt(encrypted_bytes)
        
        # Return as a string
        return decrypted_key.decode('utf-8')
    except Exception as e:
        print(f"Error decrypting private key: {e}")
        return None

def load_db():
    """Load wallet database from file"""
    if os.path.exists(DB_FILE):
        with open(DB_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_db(data):
    """Save wallet database to file"""
    with open(DB_FILE, 'w') as f:
        json.dump(data, f)

def get_user_wallet(user_id):
    """Get wallet for a specific user"""
    db = load_db()
    wallet_data = db.get(str(user_id))
    
    if wallet_data and 'private_key' in wallet_data:
        # Decrypt the private key before returning
        encrypted_key = wallet_data['private_key']
        wallet_data['private_key'] = decrypt_private_key(encrypted_key, user_id)
    
    return wallet_data

def save_user_wallet(user_id, wallet_data):
    """Save wallet for a specific user with encrypted private key"""
    if wallet_data and 'private_key' in wallet_data:
        # Make a copy to avoid modifying the original
        wallet_copy = wallet_data.copy()
        
        # Encrypt the private key
        private_key = wallet_copy['private_key']
        wallet_copy['private_key'] = encrypt_private_key(private_key, user_id)
        
        # Save to database
        db = load_db()
        db[str(user_id)] = wallet_copy
        save_db(db)
    else:
        # Save as is if no private key
        db = load_db()
        db[str(user_id)] = wallet_data
        save_db(db)

def delete_user_wallet(user_id):
    """Delete wallet for a specific user"""
    user_id_str = str(user_id)
    
    # Delete from wallet DB
    db = load_db()
    if user_id_str in db:
        del db[user_id_str]
        save_db(db)
        
        # Also delete user's salt if it exists
        salts = load_salts()
        if user_id_str in salts:
            del salts[user_id_str]
            save_salts(salts)
        
        return True
    return False 