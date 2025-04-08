"""
Initialize and export shared service instances.
"""
from utils.web3_connection import w3
from services.tokens import TokenManager

# Initialize shared service instances
token_manager = TokenManager() 