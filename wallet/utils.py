"""
Utility functions for the wallet module.
"""
from utils.web3_connection import w3

def validate_address(address):
    """
    Validate an Ethereum address and convert it to checksum format.
    
    Args:
        address (str): Any Ethereum address format
        
    Returns:
        str: The address converted to checksum format
        
    Raises:
        ValueError: If the address is not a valid Ethereum address
    """
    # Basic validation first
    if not address or not isinstance(address, str):
        raise ValueError("Address must be a non-empty string")
    
    # Remove 0x prefix if it exists and check length
    clean_address = address.lower().replace('0x', '')
    if len(clean_address) != 40:
        raise ValueError(f"Invalid address length: {address}")
    
    # Check if the address contains only valid hex characters
    try:
        int(clean_address, 16)
    except ValueError:
        raise ValueError(f"Address contains invalid characters: {address}")
    
    # Convert to checksum address
    try:
        return w3.to_checksum_address(address)
    except ValueError as e:
        raise ValueError(f"Invalid Ethereum address: {address}") from e 