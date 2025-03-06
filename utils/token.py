import requests
from utils.config import get_env_var

def get_token_list():
    """Fetch token list from the provided URL"""
    token_list_url = get_env_var('DEFAULT_TOKEN_LIST', 'https://tokens.pancakeswap.finance/pancakeswap-extended.json')
    response = requests.get(token_list_url)
    if response.status_code == 200:
        return response.json().get('tokens', [])
    return []

def find_token(symbol=None, address=None):
    """Find token by symbol or address"""
    tokens = get_token_list()
    
    if symbol:
        symbol = symbol.upper()
        matching_tokens = [t for t in tokens if t.get('symbol', '').upper() == symbol]
        return matching_tokens[0] if matching_tokens else None
        
    if address:
        address = address.lower()
        matching_tokens = [t for t in tokens if t.get('address', '').lower() == address]
        return matching_tokens[0] if matching_tokens else None
    
    return None 