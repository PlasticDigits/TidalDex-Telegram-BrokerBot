"""
Configuration module to handle environment variables.
"""
import os
from typing import Dict, Any, Optional, Union
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def get_env_var(name: str, default: Any = None) -> Any:
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
BSC_RPC_URL: str = get_env_var('BSC_RPC_URL')
TELEGRAM_BOT_TOKEN: str = get_env_var('TELEGRAM_BOT_TOKEN')
ENCRYPTION_KEY: str = get_env_var('ENCRYPTION_KEY')
DEFAULT_TOKEN_LIST: str = get_env_var('DEFAULT_TOKEN_LIST', 'https://raw.githubusercontent.com/chinese-zodiac/tidaldex-fe/refs/heads/main/src/config/constants/tokenLists/tidaldex-default.tokenlist.json')
BSC_SCANNER_URL: str = get_env_var('BSC_SCANNER_URL', 'https://bscscan.com')
INTERMEDIATE_LP_ADDRESS: str = get_env_var('INTERMEDIATE_LP_ADDRESS')
WETH: str = get_env_var('WETH')
CL8Y_BUY_AND_BURN: str = get_env_var('CL8Y_BUY_AND_BURN')
CL8Y_BB_FEE_BPS: int = int(get_env_var('CL8Y_BB_FEE_BPS', 100))

# USTC+ Preregister contract addresses
USTC_CB_TOKEN_ADDRESS: str = get_env_var('USTC_CB_TOKEN_ADDRESS', '0xA4224f910102490Dc02AAbcBc6cb3c59Ff390055')
USTC_PREREGISTER_ADDRESS: str = get_env_var('USTC_PREREGISTER_ADDRESS', '0xe50DaD8c95dd7A43D792a040146EFaA4801d62B8')

# PIN security settings
PIN_EXPIRATION_TIME: int = int(get_env_var('PIN_EXPIRATION_TIME', 1800))  # Default: 30 minutes (in seconds)

# X (Twitter) OAuth 2.0 settings
X_OAUTH_BASE_URL: str = get_env_var('X_OAUTH_BASE_URL')
X_CLIENT_ID: str = get_env_var('X_CLIENT_ID')
X_CLIENT_SECRET: str = get_env_var('X_CLIENT_SECRET')
X_REDIRECT_URI: str = f"{X_OAUTH_BASE_URL}/x-oauth"  # OAuth callback endpoint
X_SCOPES: str = "tweet.read users.read follows.read like.read"  # Scopes for profile, replies, shares, and likes

# API Server settings (for render.com deployment)
API_HOST: str = get_env_var('API_HOST', '0.0.0.0')  # Default: bind to all interfaces
API_PORT: int = int(get_env_var('API_PORT', 10000))  # Default: render.com expected port

# Wallet derivation path settings
DEFAULT_DERIVATION_PATH: str = "m/44'/60'/0'/0/0"  # Default path for first Ethereum account
ACCOUNT_PATH_TEMPLATE: str = "m/44'/60'/0'/0/{}"   # Template for deriving multiple accounts

# Database settings - PostgreSQL only
DB_NAME: str = get_env_var('DB_NAME', 'tidaldex')  # PostgreSQL database name
DB_HOST: str = get_env_var('DB_HOST', 'localhost')  # Database host
DB_PORT: int = int(get_env_var('DB_PORT', '5432'))  # Database port
DB_USER: str = get_env_var('DB_USER', 'postgres')  # Database user
DB_PASSWORD: str = get_env_var('DB_PASSWORD', 'postgres')  # Database password

# Database connection settings
DATABASE_RETRY_MAX_ATTEMPTS: int = 5  # Maximum number of retries for database operations
DATABASE_RETRY_INITIAL_WAIT: float = 0.1  # Initial wait between retries in seconds (doubles with each retry)
DATABASE_CONNECTION_TIMEOUT: float = 30.0  # Connection timeout in seconds 