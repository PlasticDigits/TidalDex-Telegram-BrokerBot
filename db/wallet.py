"""
Database operations for wallets.
"""
import logging
import traceback
from typing import Optional, Union, Dict, Any, List, Tuple, TypedDict, cast
from db.connections.connection import QueryResult
from db.connection import execute_query
from db.utils import encrypt_data, decrypt_data, hash_user_id
from db.pin import has_pin
from db.mnemonic import get_user_mnemonic
from wallet.mnemonic import derive_wallet_from_mnemonic
import time

# Configure module logger
logger = logging.getLogger(__name__)

# Define TypedDict for wallet data
class WalletData(TypedDict, total=False):
    """TypedDict for wallet data"""
    name: str
    address: str
    private_key: Optional[str]
    derivation_path: Optional[str]
    path: Optional[str]  # Database field before conversion to derivation_path
    is_active: bool
    imported: bool
    created_at: Optional[float]
    id: Optional[int]  # Database ID for the wallet

def get_user_wallet(user_id: Union[int, str], wallet_name: Optional[str] = None, pin: Optional[str] = None) -> Optional[WalletData]:
    """
    Get the active wallet for a specific user.
    
    Args:
        user_id: The user ID to get the wallet for
        wallet_name: Optional wallet name to retrieve a specific wallet
        pin: The PIN to use for decryption
        
    Returns:
        The wallet data or None if not found
    """
    # Hash the user ID for database lookup
    user_id_str: str = hash_user_id(user_id)
    result: QueryResult

    try:
        # If wallet_name is provided, get that specific wallet
        if wallet_name:
            logger.debug(f"Querying specific wallet {wallet_name} for user: {user_id_str}")
            result = execute_query(
                "SELECT * FROM wallets WHERE user_id = ? AND name = ?",
                (user_id_str, wallet_name),
                fetch='one'
            )
        else:
            # Get the active wallet using active_wallet_id from the users table
            logger.debug(f"Querying active wallet for user: {user_id_str}")
            result = execute_query(
                """
                SELECT w.* FROM wallets w
                JOIN users u ON w.id = u.active_wallet_id AND w.user_id = u.user_id
                WHERE u.user_id = ?
                """,
                (user_id_str,),
                fetch='one'
            )
        
        if not result or not isinstance(result, dict):
            if wallet_name:
                logger.debug(f"No wallet with ID {wallet_name} found for user: {user_id_str}")
            else:
                logger.debug(f"No active wallet found for user: {user_id_str}")
            return None
        
        # Decrypt private key if present
        wallet_data: WalletData = cast(WalletData, dict(result))
        if wallet_data.get('private_key'):
            logger.debug(f"Attempting to decrypt private key for wallet {wallet_name} for user {user_id_str}")
            try:
                if wallet_data['private_key'] is not None:
                    private_key: Optional[str] = decrypt_data(wallet_data['private_key'], user_id, pin)
                    if private_key:
                        wallet_data['private_key'] = private_key
                        logger.debug(f"Successfully decrypted private key for wallet {wallet_name} for user {user_id_str}")
                    else:
                        logger.error(f"Failed to decrypt private key for wallet {wallet_name} for user {user_id_str}")
                else:
                    logger.error(f"Private key is None for wallet {wallet_name} for user {user_id_str}")
            except Exception as e:
                logger.error(f"Error decrypting private key for wallet {wallet_name} for user {user_id_str}: {e}")
                logger.error(traceback.format_exc())
                wallet_data['private_key'] = None
        elif wallet_data.get('derivation_path'):
            logger.debug(f"Wallet {wallet_name} has no private key, but has a path. It is a mnemonic wallet.")
            try:
                mnemonic: Optional[str] = get_user_mnemonic(user_id, pin)
                if mnemonic:
                    derived_wallet: Dict[str, str] = derive_wallet_from_mnemonic(
                        mnemonic, 
                        int(wallet_data['derivation_path']) if wallet_data.get('derivation_path') and isinstance(wallet_data['derivation_path'], str) and wallet_data['derivation_path'].isdigit() else 0
                    )
                    private_key_derived: Optional[str] = derived_wallet.get('private_key')
                    if private_key_derived is not None:
                        # Ensure private_key is a string
                        wallet_data['private_key'] = str(private_key_derived)
                    else:
                        wallet_data['private_key'] = None
                    logger.debug(f"Successfully derived private key for wallet {wallet_name} for user {user_id_str}")
                else:
                    logger.error(f"Failed to retrieve mnemonic for user {user_id_str}")
            except Exception as e:
                logger.error(f"Error deriving private key from mnemonic for wallet {wallet_name} for user {user_id_str}: {e}")
                logger.error(traceback.format_exc())
                wallet_data['private_key'] = None
                    
        return wallet_data
    except Exception as e:
        logger.error(f"Error retrieving wallet for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        return None

def save_user_wallet(user_id: Union[int, str], wallet_data: Dict[str, Any], wallet_name: str = "Default", pin: Optional[str] = None) -> bool:
    """
    Save a wallet for a specific user.
    
    Args:
        user_id: The user ID to save the wallet for
        wallet_data: The wallet data to save
        wallet_name: The name of the wallet
        pin: PIN to use for encryption
        
    Returns:
        True if successful, False otherwise
    """
    # Hash the user ID for database storage
    user_id_str: str = hash_user_id(user_id)
    
    try:
        # Make a copy of the wallet data to avoid modifying the original
        wallet_copy: Dict[str, Any] = dict(wallet_data)
        
        # Ensure required fields exist
        if not wallet_copy.get('address'):
            logger.error(f"Cannot save wallet without an address for user {user_id_str}")
            return False
        
        # Encrypt the private key if present
        if wallet_copy.get('private_key'):
            logger.debug(f"Encrypting private key for wallet {wallet_name} for user {user_id_str}")
            encrypted_key: Optional[str] = encrypt_data(wallet_copy['private_key'], user_id, pin)
            if not encrypted_key:
                logger.error(f"Failed to encrypt private key for wallet {wallet_name} for user {user_id_str}")
                return False
            wallet_copy['private_key'] = encrypted_key
        
        # First, create user record if it doesn't exist
        logger.debug(f"Ensuring user {user_id_str} exists in users table")
        execute_query(
            "INSERT OR IGNORE INTO users (user_id, active_wallet_id) VALUES (?, NULL)",
            (user_id_str,)
        )
        
        # Check if wallet with this name exists for user
        existing_wallet: QueryResult = execute_query(
            "SELECT id FROM wallets WHERE user_id = ? AND name = ?",
            (user_id_str, wallet_name),
            fetch='one'
        )
        
        if existing_wallet and isinstance(existing_wallet, dict):
            # Update existing wallet
            logger.debug(f"Updating existing wallet {wallet_name} for user {user_id_str}")
            
            # Update fields, dynamically building query
            fields: List[str] = []
            values: List[Any] = []
            
            if 'address' in wallet_copy:
                fields.append("address = ?")
                values.append(wallet_copy['address'])
            
            if 'private_key' in wallet_copy:
                fields.append("private_key = ?")
                values.append(wallet_copy['private_key'])
            
            if 'derivation_path' in wallet_copy:
                fields.append("path = ?")
                values.append(wallet_copy['derivation_path'])
                
            if 'imported' in wallet_copy:
                fields.append("imported = ?")
                values.append(1 if wallet_copy['imported'] else 0)
            
            if 'is_active' in wallet_copy:
                fields.append("is_active = ?")
                values.append(1 if wallet_copy['is_active'] else 0)
            
            # If there are fields to update
            if fields:
                # Add the user_id and wallet_name to values
                values.append(user_id_str)
                values.append(wallet_name)
                
                # Execute update query
                query: str = f"UPDATE wallets SET {', '.join(fields)} WHERE user_id = ? AND name = ?"
                execute_query(query, tuple(values))
            
            logger.debug(f"Wallet {wallet_name} updated for user {user_id_str}")
        else:
            # Insert new wallet
            logger.debug(f"Creating new wallet {wallet_name} for user {user_id_str}")
            
            # Prepare data for insertion
            now: float = time.time()
            address: str = wallet_copy.get('address', '')
            private_key: Optional[str] = wallet_copy.get('private_key')
            derivation_path: Optional[str] = wallet_copy.get('derivation_path')
            imported: bool = bool(wallet_copy.get('imported', False))
            
            # Insert new wallet
            execute_query(
                """
                INSERT INTO wallets 
                (user_id, name, address, private_key, path, imported, created_at) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id_str, wallet_name, address, private_key, derivation_path, 1 if imported else 0, now)
            )
            
            logger.debug(f"New wallet {wallet_name} created for user {user_id_str}")
        
        # Newly created wallets always set to active.
        set_active_wallet(user_id, wallet_name)
        
        return True
    except Exception as e:
        logger.error(f"Error saving wallet {wallet_name} for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        return False

def delete_user_wallet(user_id: Union[int, str], wallet_name: Optional[str] = None) -> bool:
    """
    Delete a wallet for a specific user.
    
    Args:
        user_id: The user ID to delete the wallet for
        wallet_name: Optional wallet name to delete a specific wallet (deletes active wallet if None)
        
    Returns:
        True if successful, False otherwise
    """
    # Hash the user ID for database operations
    user_id_str: str = hash_user_id(user_id)
    
    try:
        # If wallet_name is provided, delete that specific wallet
        if wallet_name:
            logger.debug(f"Deleting specific wallet {wallet_name} for user: {user_id_str}")
            
            # Check if this is the active wallet
            active_wallet_id: Optional[int] = get_active_wallet_id(user_id)
            
            # Get the wallet ID for the wallet being deleted
            wallet_info: QueryResult = execute_query(
                "SELECT id FROM wallets WHERE user_id = ? AND name = ?",
                (user_id_str, wallet_name),
                fetch='one'
            )
            
            if not wallet_info or not isinstance(wallet_info, dict):
                logger.error(f"Wallet {wallet_name} not found for user {user_id_str}")
                return False
                
            was_active = active_wallet_id == wallet_info.get('id')
            
            # Delete the wallet
            execute_query(
                "DELETE FROM wallets WHERE user_id = ? AND name = ?",
                (user_id_str, wallet_name)
            )
            
            # If this was the active wallet, set another wallet as active if possible
            if was_active:
                # There are other wallets, set the first one as active
                new_active: QueryResult = execute_query(
                    "SELECT id, name FROM wallets WHERE user_id = ? LIMIT 1",
                    (user_id_str,),
                    fetch='one'
                )
                
                if new_active and isinstance(new_active, dict):
                    logger.debug(f"Setting wallet {new_active['name']} as active for user: {user_id_str}")
                    execute_query(
                        "UPDATE users SET active_wallet_id = ? WHERE user_id = ?",
                        (new_active['id'], user_id_str)
                    )
        else:
            # Delete the active wallet
            logger.debug(f"Deleting active wallet for user: {user_id_str}")
            active_wallet: QueryResult = execute_query(
                """
                SELECT w.name 
                FROM wallets w
                JOIN users u ON w.id = u.active_wallet_id AND w.user_id = u.user_id
                WHERE u.user_id = ?
                """,
                (user_id_str,),
                fetch='one'
            )
            
            if active_wallet and isinstance(active_wallet, dict):
                execute_query(
                    "DELETE FROM wallets WHERE user_id = ? AND name = ?",
                    (user_id_str, active_wallet['name'])
                )
                
                # Set another wallet as active if possible
                another_active: QueryResult = execute_query(
                    "SELECT id, name FROM wallets WHERE user_id = ? LIMIT 1",
                    (user_id_str,),
                    fetch='one'
                )
                
                if another_active and isinstance(another_active, dict):
                    logger.debug(f"Setting wallet {another_active['name']} as active for user: {user_id_str}")
                    execute_query(
                        "UPDATE users SET active_wallet_id = ? WHERE user_id = ?",
                        (another_active['id'], user_id_str)
                    )
            else:
                logger.debug(f"No active wallet found for user: {user_id_str}")
                return False
        
        logger.debug(f"Wallet deleted successfully for user {user_id_str}")
        return True
    except Exception as e:
        logger.error(f"Error deleting wallet for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        return False
    
def get_active_wallet_id(user_id: Union[int, str]) -> Optional[int]:
    """
    Get the ID of the active wallet for a user.
    
    Args:
        user_id: The user ID to get the active wallet for
        
    Returns:
        The ID of the active wallet or None if no active wallet is found
    """
    # Hash the user ID for database lookup
    user_id_str: str = hash_user_id(user_id)
    
    try:
        result: QueryResult = execute_query(
            "SELECT active_wallet_id FROM users WHERE user_id = ?",
            (user_id_str,),
            fetch='one'
        )

        if result and isinstance(result, dict) and 'active_wallet_id' in result:
            return cast(Optional[int], result['active_wallet_id'])
        else:
            return None
    except Exception as e:
        logger.error(f"Error getting active wallet ID for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        return None
    

def has_user_wallet(user_id: Union[int, str], pin: Optional[str] = None) -> bool:
    """
    Check if a user has any wallets.
    
    Args:
        user_id: The user ID to check
        pin: Not used, included for API consistency
        
    Returns:
        True if the user has at least one wallet, False otherwise
    """
    # Hash the user ID for database lookup
    user_id_str: str = hash_user_id(user_id)
    
    try:
        result: QueryResult = execute_query(
            "SELECT COUNT(*) as count FROM wallets WHERE user_id = ?",
            (user_id_str,),
            fetch='one'
        )
        
        return result is not None and isinstance(result, dict) and result['count'] > 0
    except Exception as e:
        logger.error(f"Error checking if user {user_id_str} has wallets: {e}")
        logger.error(traceback.format_exc())
        return False

def get_user_wallets(user_id: Union[int, str], pin: Optional[str] = None) -> Dict[str, WalletData]:
    """
    Get all wallets for a specific user.
    
    Args:
        user_id: The user ID to get wallets for
        pin: Not used, included for API consistency
        
    Returns:
        Dict of wallet names to wallet data without private keys
    """
    # Hash the user ID for database lookup
    user_id_str: str = hash_user_id(user_id)
    
    try:
        logger.debug(f"Querying all wallets for user: {user_id_str}")
        
        # First get the active wallet ID from the users table
        active_wallet_id: Optional[int] = get_active_wallet_id(user_id)

        if active_wallet_id is None:
            active_wallet_id = 0
        
        # Now get all wallets
        results: QueryResult = execute_query(
            "SELECT id, name, address, path, imported, created_at FROM wallets WHERE user_id = ?",
            (user_id_str,),
            fetch='all'
        )
        
        if not results:
            logger.debug(f"No wallets found for user: {user_id_str}")
            return {}
        
        # Process each wallet to remove private keys and mark active wallet
        wallets: Dict[str, WalletData] = {}
        if isinstance(results, list):
            for result in results:
                if not isinstance(result, dict):
                    logger.error(f"Unexpected result type: {type(result)}")
                    continue
                wallet: WalletData = cast(WalletData, dict(result))
                if 'path' in wallet:
                    wallet['derivation_path'] = wallet.pop('path')
                
                # Mark as active if this wallet's id matches the active_wallet_id
                wallet_id = wallet.pop('id', None)  # Remove id from the result
                wallet['is_active'] = (wallet_id == active_wallet_id)
                
                if 'name' in wallet:
                    wallet_name = wallet['name']
                    wallets[wallet_name] = wallet
                else:
                    logger.error(f"Wallet missing name field: {wallet}")
        else:
            logger.error(f"Expected list of results but got {type(results)}")
        
        logger.debug(f"Found {len(wallets)} wallets for user {user_id_str}")
        return wallets
    except Exception as e:
        logger.error(f"Error retrieving wallets for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        return {}

def set_active_wallet(user_id: Union[int, str], wallet_name: str) -> bool:
    """
    Set a specific wallet as the active wallet for a user.
    
    Args:
        user_id: The user ID
        wallet_name: The name of the wallet to set as active
        
    Returns:
        True if successful, False otherwise
    """
    # Hash the user ID for database operations
    user_id_str: str = hash_user_id(user_id)
    
    try:
        # Check if the wallet exists and get its ID
        wallet_info: QueryResult = execute_query(
            "SELECT id FROM wallets WHERE user_id = ? AND name = ?",
            (user_id_str, wallet_name),
            fetch='one'
        )
        
        if not wallet_info or not isinstance(wallet_info, dict) or 'id' not in wallet_info:
            logger.error(f"Cannot set non-existent wallet '{wallet_name}' as active for user {user_id_str}")
            return False
        
        # Update the active_wallet_id in the users table
        execute_query(
            "UPDATE users SET active_wallet_id = ? WHERE user_id = ?",
            (wallet_info['id'], user_id_str)
        )
        
        logger.debug(f"Wallet '{wallet_name}' set as active for user {user_id_str}")
        return True
    except Exception as e:
        logger.error(f"Error setting active wallet for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        return False

def rename_wallet(user_id: Union[int, str], new_name: str) -> Tuple[bool, str]:
    """
    Rename the currently active wallet for a user.
    
    Args:
        user_id: The user ID
        new_name: The new name for the wallet
        
    Returns:
        A tuple containing:
            - bool: True if successful, False otherwise
            - str: The old name of the wallet or error message if False
    """
    # Hash the user ID for database operations
    user_id_str = hash_user_id(user_id)
    logger.debug(f"Renaming active wallet for hashed user_id: {user_id_str}")
    
    # Basic length validation
    if not new_name:
        return False, "Invalid wallet name. Name cannot be empty."
    
    if len(new_name) > 32:
        return False, "Invalid wallet name. Name must not exceed 32 characters."
    
    if len(new_name) < 3:
        return False, "Invalid wallet name. Name must be at least 3 characters long."
    
    # Check for leading/trailing whitespace
    if new_name != new_name.strip():
        return False, "Wallet name cannot have leading or trailing spaces."
        
    # Check for dangerous characters (SQL injection, command execution)
    import re
    if re.search(r'[\'";`<>]', new_name):
        return False, "Wallet name contains invalid characters. Avoid using: ' \" ; ` < >"
    
    # Check against reserved names
    reserved_names = ["default", "wallet", "main", "primary", "backup", "test", "admin", "system"]
    if new_name.lower() in reserved_names:
        return False, f"'{new_name}' is a reserved name and cannot be used."
    
    try:
        # Check if wallet with new name already exists
        existing_wallet: QueryResult = execute_query(
            "SELECT id FROM wallets WHERE user_id = ? AND name = ?", 
            (user_id_str, new_name),
            fetch='one'
        )
        
        if existing_wallet and isinstance(existing_wallet, dict) and existing_wallet.get('id'):
            return False, f"Wallet with name '{new_name}' already exists."
        
        # Get active wallet
        active_wallet: QueryResult = execute_query(
            """
            SELECT w.id, w.name 
            FROM wallets w
            JOIN users u ON w.id = u.active_wallet_id AND w.user_id = u.user_id
            WHERE u.user_id = ?
            """, 
            (user_id_str,),
            fetch='one'
        )
        
        if not active_wallet or not isinstance(active_wallet, dict):
            return False, "No active wallet found."
        
        old_name = active_wallet.get('name', '')
        wallet_id = active_wallet.get('id')
        
        if not old_name or not wallet_id:
            return False, "Invalid wallet data retrieved."
        
        # Update the wallet name
        execute_query(
            "UPDATE wallets SET name = ? WHERE id = ?",
            (new_name, wallet_id)
        )
        
        # Enhanced logging for security audit
        logger.info(f"Wallet renamed from '{old_name}' to '{new_name}' for user ID hash: {user_id_str[:10]}...")
        return True, old_name
    except Exception as e:
        logger.error(f"Error renaming wallet for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        return False, str(e)

def get_user_wallets_with_keys(user_id: Union[int, str], pin: Optional[str] = None) -> Dict[str, WalletData]:
    """
    Get all wallets for a specific user, including private keys.
    
    Args:
        user_id: The user ID to get wallets for
        pin: The PIN to use for decryption
        
    Returns:
        A dictionary of wallet names to wallet data including private keys
    """
    # Hash the user ID for database lookup
    user_id_str: str = hash_user_id(user_id)
    
    try:
        logger.debug(f"Querying all wallets with keys for user: {user_id_str}")
        results: QueryResult = execute_query(
            "SELECT * FROM wallets WHERE user_id = ?",
            (user_id_str,),
            fetch='all'
        )
        
        if not results:
            logger.debug(f"No wallets found for user: {user_id_str}")
            return {}
        
        # Process each wallet to decrypt keys
        wallets_with_keys: Dict[str, WalletData] = {}
        if isinstance(results, list):
            for result in results:
                if not isinstance(result, dict):
                    logger.error(f"Unexpected result type: {type(result)}")
                    continue
                wallet_dict: Dict[str, Any] = dict(result)
                name: str = wallet_dict.pop('name')
                
                # Rename path to derivation_path for clarity
                if 'path' in wallet_dict:
                    wallet_dict['derivation_path'] = wallet_dict.pop('path')
                
                # Decrypt private key if present
                if wallet_dict.get('private_key'):
                    try:
                        if wallet_dict['private_key'] is not None:
                            decrypted_key: Optional[str] = decrypt_data(wallet_dict['private_key'], user_id, pin)
                            if decrypted_key:
                                wallet_dict['private_key'] = decrypted_key
                                logger.debug(f"Successfully decrypted private key for wallet {name}")
                            else:
                                logger.error(f"Failed to decrypt private key for wallet {name}")
                                wallet_dict['private_key'] = None
                        else:
                            logger.error(f"Private key is None for wallet {name}")
                            wallet_dict['private_key'] = None
                    except Exception as e:
                        logger.error(f"Error decrypting private key for wallet {name}: {e}")
                        logger.error(traceback.format_exc())
                        wallet_dict['private_key'] = None
                # Derive private key from mnemonic if path is present
                elif wallet_dict.get('derivation_path'):
                    try:
                        mnemonic: Optional[str] = get_user_mnemonic(user_id, pin)
                        if mnemonic:
                            derived_wallet: Dict[str, str] = derive_wallet_from_mnemonic(
                                mnemonic, 
                                int(wallet_dict['derivation_path']) if wallet_dict.get('derivation_path') and isinstance(wallet_dict['derivation_path'], str) and wallet_dict['derivation_path'].isdigit() else 0
                            )
                            private_key_derived: Optional[str] = derived_wallet.get('private_key')
                            if private_key_derived is not None:
                                # Ensure private_key is a string
                                wallet_dict['private_key'] = str(private_key_derived)
                            else:
                                wallet_dict['private_key'] = None
                            logger.debug(f"Successfully derived private key for wallet {name}")
                        else:
                            logger.error(f"Failed to retrieve mnemonic for user {user_id_str}")
                    except Exception as e:
                        logger.error(f"Error deriving private key from mnemonic for wallet {name}: {e}")
                        logger.error(traceback.format_exc())
                        wallet_dict['private_key'] = None
                
                wallets_with_keys[name] = cast(WalletData, wallet_dict)
        
        logger.debug(f"Found {len(wallets_with_keys)} wallets with keys for user {user_id_str}")
        return wallets_with_keys
    except Exception as e:
        logger.error(f"Error retrieving wallets with keys for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        return {}

def get_active_wallet_name(user_id: Union[int, str]) -> Optional[str]:
    """
    Get the name of the active wallet for a user.
    
    Args:
        user_id: The user ID
        
    Returns:
        The name of the active wallet, or None if no active wallet is set
    """
    # Hash the user ID for database lookup
    user_id_str: str = hash_user_id(user_id)
    
    try:
        logger.debug(f"Querying active wallet name for user: {user_id_str}")
        result: QueryResult = execute_query(
            """
            SELECT w.name 
            FROM wallets w
            JOIN users u ON w.id = u.active_wallet_id AND w.user_id = u.user_id
            WHERE u.user_id = ?
            """,
            (user_id_str,),
            fetch='one'
        )
        
        if result and isinstance(result, dict):
            return result.get('name')
        logger.debug(f"No active wallet found for user: {user_id_str}")
        return None
    except Exception as e:
        logger.error(f"Error retrieving active wallet name for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        return None

def get_wallet_by_name(user_id: Union[int, str], wallet_name: str, pin: Optional[str] = None) -> Optional[WalletData]:
    """
    Get a wallet by its name.
    
    Args:
        user_id: The user ID
        wallet_name: The wallet name
        pin: The PIN to use for decryption
        
    Returns:
        The wallet data, or None if not found
    """
    # Hash the user ID for database lookup
    user_id_str: str = hash_user_id(user_id)
    
    try:
        logger.debug(f"Querying wallet by name {wallet_name} for user: {user_id_str}")
        query_result = execute_query(
            "SELECT * FROM wallets WHERE user_id = ? AND name = ?",
            (user_id_str, wallet_name),
            fetch='one'
        )
        
        result: Optional[Dict[str, Any]] = None
        if isinstance(query_result, dict):
            result = query_result
        
        if not result:
            logger.debug(f"No wallet with name {wallet_name} found for user: {user_id_str}")
            return None
        
        # Process wallet data
        wallet_dict: Dict[str, Any] = dict(result)
        
        # Rename path to derivation_path for clarity
        if 'path' in wallet_dict:
            wallet_dict['derivation_path'] = wallet_dict.pop('path')
        
        # Decrypt private key if present
        if wallet_dict.get('private_key'):
            try:
                if wallet_dict['private_key'] is not None:
                    decrypted_key: Optional[str] = decrypt_data(wallet_dict['private_key'], user_id, pin)
                    if decrypted_key:
                        wallet_dict['private_key'] = decrypted_key
                        logger.debug(f"Successfully decrypted private key for wallet {wallet_name}")
                    else:
                        logger.error(f"Failed to decrypt private key for wallet {wallet_name}")
                        wallet_dict['private_key'] = None
                else:
                    logger.error(f"Private key is None for wallet {wallet_name}")
                    wallet_dict['private_key'] = None
            except Exception as e:
                logger.error(f"Error decrypting private key for wallet {wallet_name}: {e}")
                logger.error(traceback.format_exc())
                wallet_dict['private_key'] = None
        # Derive private key from mnemonic if path is present
        elif wallet_dict.get('derivation_path'):
            try:
                mnemonic: Optional[str] = get_user_mnemonic(user_id, pin)
                if mnemonic:
                    derived_wallet: Dict[str, str] = derive_wallet_from_mnemonic(
                        mnemonic, 
                        int(wallet_dict['derivation_path']) if wallet_dict.get('derivation_path') and isinstance(wallet_dict['derivation_path'], str) and wallet_dict['derivation_path'].isdigit() else 0
                    )
                    private_key: Optional[str] = derived_wallet.get('private_key')
                    if private_key is not None:
                        # Ensure private_key is a string
                        wallet_dict['private_key'] = str(private_key)
                    else:
                        wallet_dict['private_key'] = None
                    logger.debug(f"Successfully derived private key for wallet {wallet_name}")
                else:
                    logger.error(f"Failed to retrieve mnemonic for user {user_id_str}")
            except Exception as e:
                logger.error(f"Error deriving private key from mnemonic for wallet {wallet_name}: {e}")
                logger.error(traceback.format_exc())
                wallet_dict['private_key'] = None
        
        return cast(WalletData, wallet_dict)
    except Exception as e:
        logger.error(f"Error retrieving wallet {wallet_name} for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        return None

def get_wallet_by_address(user_id: Union[int, str], address: str, pin: Optional[str] = None) -> Optional[WalletData]:
    """
    Get a wallet by its address.
    
    Args:
        user_id: The user ID
        address: The wallet address
        pin: The PIN to use for decryption
        
    Returns:
        The wallet data, or None if not found
    """
    # Hash the user ID for database lookup
    user_id_str: str = hash_user_id(user_id)
    
    try:
        logger.debug(f"Querying wallet by address {address} for user: {user_id_str}")
        query_result = execute_query(
            "SELECT * FROM wallets WHERE user_id = ? AND address = ?",
            (user_id_str, address),
            fetch='one'
        )
        
        result: Optional[Dict[str, Any]] = None
        if isinstance(query_result, dict):
            result = query_result
        
        if not result:
            logger.debug(f"No wallet with address {address} found for user: {user_id_str}")
            return None
        
        # Process wallet data
        wallet_dict: Dict[str, Any] = dict(result)
        
        # Rename path to derivation_path for clarity
        if 'path' in wallet_dict:
            wallet_dict['derivation_path'] = wallet_dict.pop('path')
        
        # Decrypt private key if present
        if wallet_dict.get('private_key'):
            try:
                if wallet_dict['private_key'] is not None:
                    decrypted_key: Optional[str] = decrypt_data(wallet_dict['private_key'], user_id, pin)
                    if decrypted_key:
                        wallet_dict['private_key'] = decrypted_key
                        logger.debug(f"Successfully decrypted private key for wallet with address {address}")
                    else:
                        logger.error(f"Failed to decrypt private key for wallet with address {address}")
                        wallet_dict['private_key'] = None
                else:
                    logger.error(f"Private key is None for wallet with address {address}")
                    wallet_dict['private_key'] = None
            except Exception as e:
                logger.error(f"Error decrypting private key for wallet with address {address}: {e}")
                logger.error(traceback.format_exc())
                wallet_dict['private_key'] = None
        # Derive private key from mnemonic if path is present
        elif wallet_dict.get('derivation_path'):
            try:
                mnemonic: Optional[str] = get_user_mnemonic(user_id, pin)
                if mnemonic:
                    derived_wallet: Dict[str, str] = derive_wallet_from_mnemonic(
                        mnemonic, 
                        int(wallet_dict['derivation_path']) if wallet_dict.get('derivation_path') and isinstance(wallet_dict['derivation_path'], str) and wallet_dict['derivation_path'].isdigit() else 0
                    )
                    private_key: Optional[str] = derived_wallet.get('private_key')
                    if private_key is not None:
                        # Ensure private_key is a string
                        wallet_dict['private_key'] = str(private_key)
                    else:
                        wallet_dict['private_key'] = None
                    logger.debug(f"Successfully derived private key for wallet with address {address}")
                else:
                    logger.error(f"Failed to retrieve mnemonic for user {user_id_str}")
            except Exception as e:
                logger.error(f"Error deriving private key from mnemonic for wallet with address {address}: {e}")
                logger.error(traceback.format_exc())
                wallet_dict['private_key'] = None
        
        return cast(WalletData, wallet_dict)
    except Exception as e:
        logger.error(f"Error retrieving wallet with address {address} for user {user_id_str}: {e}")
        logger.error(traceback.format_exc())
        return None 