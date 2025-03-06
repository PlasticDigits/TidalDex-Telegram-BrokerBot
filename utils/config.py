"""
Configuration module to handle environment variables.
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def get_env_var(name, default=None):
    """
    Get an environment variable or return a default value if not found.
    
    Args:
        name (str): The name of the environment variable
        default: The default value to return if the variable is not found
        
    Returns:
        The value of the environment variable or the default value
    """
    value = os.getenv(name, default)
    if value is None:
        raise ValueError(f"Environment variable {name} not found and no default provided")
    return value

# Commonly used configuration variables
BSC_RPC_URL = get_env_var('BSC_RPC_URL')
TELEGRAM_BOT_TOKEN = get_env_var('TELEGRAM_BOT_TOKEN')
ENCRYPTION_KEY = get_env_var('ENCRYPTION_KEY') 