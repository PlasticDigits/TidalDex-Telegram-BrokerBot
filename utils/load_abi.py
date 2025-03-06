import os
import json

def load_abi(abi_name):
    """
    Load an ABI from the ABI directory
    
    Args:
        abi_name (str): Name of the ABI file without extension (e.g., "ERC20")
        
    Returns:
        list: The ABI as a list of objects
        
    Raises:
        FileNotFoundError: If the ABI file doesn't exist
        json.JSONDecodeError: If the ABI file isn't valid JSON
    """
    # Get the root directory of the project (one level up from utils)
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Construct the path to the ABI file
    abi_file_path = os.path.join(root_dir, 'ABI', f'{abi_name}.json')
    
    # Check if file exists
    if not os.path.exists(abi_file_path):
        # Try with "I" prefix
        abi_file_path = os.path.join(root_dir, 'ABI', f'I{abi_name}.json')
        
        # If it still doesn't exist, raise an error
        if not os.path.exists(abi_file_path):
            raise FileNotFoundError(f"ABI file for {abi_name} not found")
    
    # Load and return the ABI
    with open(abi_file_path, 'r') as f:
        return json.load(f) 