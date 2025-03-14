from typing import List, Dict, Any, Optional, cast
import httpx
from utils.config import get_env_var

async def get_token_list() -> List[Dict[str, Any]]:
    """
    Fetch token list from the provided URL
    
    Returns:
        List[Dict[str, Any]]: List of token dictionaries
    """    
    httpxClient = httpx.AsyncClient()
    try:
        token_list_url = get_env_var('DEFAULT_TOKEN_LIST', 'https://tokens.pancakeswap.finance/pancakeswap-extended.json')
        response = await httpxClient.get(token_list_url)
        if response.status_code == 200:
            return cast(List[Dict[str, Any]], response.json().get('tokens', []))
        return []
    finally:
        await httpxClient.aclose()

async def find_token(symbol: Optional[str] = None, address: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Find token by symbol or address
    
    Args:
        symbol (Optional[str]): Token symbol to search for
        address (Optional[str]): Token address to search for
        
    Returns:
        Optional[Dict[str, Any]]: Token info dictionary if found, None otherwise
    """
    tokens = await get_token_list()
    
    if symbol:
        symbol = symbol.upper()
        matching_tokens = [t for t in tokens if t.get('symbol', '').upper() == symbol]
        return matching_tokens[0] if matching_tokens else None
        
    if address:
        address = address.lower()
        matching_tokens = [t for t in tokens if t.get('address', '').lower() == address]
        return matching_tokens[0] if matching_tokens else None
    
    return None 