"""
Initialize and export shared service instances.
"""
from utils.web3_connection import w3
from services.tokens import token_manager  # Import singleton from tokens module
from services.version import version_manager

# Export version manager
__all__ = ['token_manager', 'version_manager'] 