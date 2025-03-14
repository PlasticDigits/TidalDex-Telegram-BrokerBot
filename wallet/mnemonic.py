"""
Mnemonic wallet functionality for generating and using seed phrases.
"""
import secrets
from typing import Dict, List, Any, Optional, Union
from eth_account import Account
from mnemonic import Mnemonic
import binascii
from utils.config import DEFAULT_DERIVATION_PATH, ACCOUNT_PATH_TEMPLATE

# Import BIP functionality
Account.enable_unaudited_hdwallet_features()

def create_mnemonic(strength: int = 128) -> str:
    """
    Generate a new mnemonic phrase (seed phrase).
    
    Args:
        strength (int): Bit strength of the mnemonic (128, 160, 192, 224, 256)
                        128 bits = 12 words, 256 bits = 24 words
    
    Returns:
        str: A space-separated mnemonic phrase
    """
    # Generate random entropy
    entropy = secrets.token_bytes(strength // 8)
    
    # Convert entropy to mnemonic
    mnemo = Mnemonic("english")
    mnemonic = mnemo.to_mnemonic(entropy)
    
    return mnemonic

def create_mnemonic_wallet(mnemonic: str, account_path: Optional[str] = None) -> Dict[str, str]:
    """
    Create a wallet from a mnemonic phrase.
    
    Args:
        mnemonic (str): Space-separated mnemonic phrase
        account_path (Optional[str]): Derivation path (if None, uses DEFAULT_DERIVATION_PATH)
    
    Returns:
        Dict[str, str]: A dictionary containing the wallet address and private key
            {
                'address': '0x...',
                'private_key': '0x...',
                'mnemonic': 'word1 word2 ... word12',
                'path': 'm/44\'/60\'/0\'/0/0'
            }
    """
    # Use default path if none provided
    if account_path is None:
        account_path = DEFAULT_DERIVATION_PATH
        
    try:
        # Validate mnemonic
        mnemo = Mnemonic("english")
        if not mnemo.check(mnemonic):
            raise ValueError("Invalid mnemonic phrase")
        
        # Derive account from mnemonic
        account = Account.from_mnemonic(
            mnemonic=mnemonic,
            account_path=account_path
        )
        
        # Return wallet details
        return {
            'address': account.address,
            'private_key': account.key.hex(),  # Convert private key to hex
            'mnemonic': mnemonic,
            'path': account_path
        }
    except ValueError as e:
        raise ValueError(f"Invalid mnemonic: {str(e)}")
    except binascii.Error:
        raise ValueError("Invalid mnemonic format")
    except Exception as e:
        raise ValueError(f"Error creating wallet from mnemonic: {str(e)}")

def derive_wallet_from_mnemonic(
    mnemonic: str, 
    index: int = 0, 
    account_path_template: Optional[str] = None
) -> Dict[str, str]:
    """
    Derive a wallet at a specific index from a mnemonic phrase.
    
    Args:
        mnemonic (str): Space-separated mnemonic phrase
        index (int): Index of the wallet to derive (default: 0)
        account_path_template (Optional[str]): Template for derivation path with {} placeholder for index
    
    Returns:
        Dict[str, str]: A dictionary containing the wallet address and private key
            {
                'address': '0x...',
                'private_key': '0x...',
                'index': '0',
                'path': 'm/44\'/60\'/0\'/0/0'
            }
    """
    # Use default template if none provided
    if account_path_template is None:
        account_path_template = ACCOUNT_PATH_TEMPLATE
        
    # Construct the account path using the template and index
    account_path = account_path_template.format(index)
    
    # Derive the wallet
    wallet_data = create_mnemonic_wallet(mnemonic, account_path)
    
    # Add index information
    wallet_data['index'] = str(index)
    
    return wallet_data

def derive_multiple_wallets(
    mnemonic: str, 
    count: int = 5, 
    start_index: int = 0, 
    account_path_template: Optional[str] = None
) -> List[Dict[str, str]]:
    """
    Derive multiple wallets from a single mnemonic phrase.
    
    Args:
        mnemonic (str): Space-separated mnemonic phrase
        count (int): Number of wallets to derive
        start_index (int): Starting index for derivation
        account_path_template (Optional[str]): Template for derivation path
    
    Returns:
        List[Dict[str, str]]: List of wallet dictionaries
    """
    # Use default template if none provided
    if account_path_template is None:
        account_path_template = ACCOUNT_PATH_TEMPLATE
        
    wallets = []
    
    for i in range(start_index, start_index + count):
        wallet = derive_wallet_from_mnemonic(
            mnemonic, 
            index=i, 
            account_path_template=account_path_template
        )
        wallets.append(wallet)
    
    return wallets 