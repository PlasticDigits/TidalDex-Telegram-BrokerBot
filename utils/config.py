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

# PIN security settings
PIN_EXPIRATION_TIME: int = int(get_env_var('PIN_EXPIRATION_TIME', 1800))  # Default: 30 minutes (in seconds)

# API Server settings (for render.com deployment)
API_HOST: str = get_env_var('API_HOST', '0.0.0.0')  # Default: bind to all interfaces
API_PORT: int = int(get_env_var('API_PORT', 10000))  # Default: render.com expected port

# Wallet derivation path settings
DEFAULT_DERIVATION_PATH: str = "m/44'/60'/0'/0/0"  # Default path for first Ethereum account
ACCOUNT_PATH_TEMPLATE: str = "m/44'/60'/0'/0/{}"   # Template for deriving multiple accounts

# Database settings
DB_TYPE: str = get_env_var('DB_TYPE', 'sqlite3').lower()  # Database type: sqlite3 or postgresql
DB_NAME: str = get_env_var('DB_NAME', 'tidaldex.db')  # Database name or path for SQLite
DB_HOST: str = get_env_var('DB_HOST', 'localhost')  # Database host for PostgreSQL
DB_PORT: int = int(get_env_var('DB_PORT', '5432'))  # Database port for PostgreSQL
DB_USER: str = get_env_var('DB_USER', 'postgres')  # Database user for PostgreSQL
DB_PASSWORD: str = get_env_var('DB_PASSWORD', 'postgres')  # Database password for PostgreSQL

# For backward compatibility
DATABASE_PATH: str = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', DB_NAME)
DATABASE_RETRY_MAX_ATTEMPTS: int = 5  # Maximum number of retries for database operations
DATABASE_RETRY_INITIAL_WAIT: float = 0.1  # Initial wait between retries in seconds (doubles with each retry)
DATABASE_CONNECTION_TIMEOUT: float = 30.0  # Connection timeout in seconds

# SQLite PRAGMA settings
DB_PRAGMAS: Dict[str, Union[str, int]] = {
    "journal_mode": "MEMORY",  # In-memory journal for speed
    "cache_size": 10000,       # Larger cache for better performance
    "temp_store": "MEMORY",    # Store temp tables in memory
} 