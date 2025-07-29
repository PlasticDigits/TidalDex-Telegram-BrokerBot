"""
Initialize and export shared service instances.
"""
from utils.web3_connection import w3
from services.tokens import TokenManager
from services.version import version_manager

# Initialize shared service instances  
token_manager = TokenManager()

# Export version manager
__all__ = ['token_manager', 'version_manager'] 