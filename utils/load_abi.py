import os
import json
from typing import List, Dict, Any, cast


def load_abi(abi_name: str) -> List[Dict[str, Any]]:
    """
    Load an ABI from the ABI directory
    
    Args:
        abi_name (str): Name of the ABI file without extension (e.g., "ERC20")
        
    Returns:
        List[Dict[str, Any]]: The ABI as a list of objects
        
    Raises:
        FileNotFoundError: If the ABI file doesn't exist
        json.JSONDecodeError: If the ABI file isn't valid JSON
        TypeError: If the loaded ABI is not a list of dictionaries
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
    
    # Load the ABI
    with open(abi_file_path, 'r') as f:
        abi_data = json.load(f)
    
    # Validate that the loaded data is a list of dictionaries
    if not isinstance(abi_data, list) or not all(isinstance(item, dict) for item in abi_data):
        raise TypeError(f"ABI file for {abi_name} does not contain a list of objects")
    
    # Return the validated ABI
    return cast(List[Dict[str, Any]], abi_data)

ERC20_ABI: List[Dict[str, Any]] = load_abi("ERC20")