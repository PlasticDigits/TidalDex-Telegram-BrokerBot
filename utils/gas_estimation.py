"""
Gas estimation utilities for BSC transactions.
"""
from typing import Dict, Any, Optional, Callable, Union, List, Awaitable
from decimal import Decimal
from utils.web3_connection import w3
from utils.token_operations import get_token_contract, convert_to_raw_amount

async def estimate_bnb_transfer_gas(
    from_address: str, 
    to_address: str, 
    amount_bnb: Union[float, str, Decimal], 
    status_callback: Optional[Callable[[str], Awaitable[None]]] = None
) -> Dict[str, Union[int, float]]:
    """
    Estimate gas for a BNB transfer.
    
    Args:
        from_address (str): Sender address
        to_address (str): Recipient address
        amount_bnb (Union[float, str, Decimal]): Amount of BNB to send
        status_callback (Optional[Callable[[str], Awaitable[None]]]): Function to call with status updates
        
    Returns:
        Dict[str, Union[int, float]]: Gas estimation info
            {
                'gas_wei': int,       # Gas cost in wei
                'gas_bnb': float,     # Gas cost in BNB
                'gas_estimate': int,  # Gas units needed
                'gas_price': int      # Current gas price in wei
            }
    """
    if status_callback:
        await status_callback("Estimating gas fees for transaction...")
    
    # Convert to checksum addresses
    from_checksum = w3.to_checksum_address(from_address)
    to_checksum = w3.to_checksum_address(to_address)
    
    # Convert BNB amount to wei
    amount_wei = w3.to_wei(amount_bnb, 'ether')
    
    # Create transaction dictionary
    tx = {
        'from': from_checksum,
        'to': to_checksum,
        'value': amount_wei,
        'nonce': w3.eth.get_transaction_count(from_checksum),
    }
    
    try:
        # Properly annotate tx as TxParams
        from web3.types import TxParams
        tx_params: TxParams = tx  # type: ignore
        
        # Estimate gas
        gas_estimate = w3.eth.estimate_gas(tx_params)
        
        # Get gas price
        gas_price = w3.eth.gas_price
        
        # Calculate total gas cost in wei
        gas_cost_wei = gas_estimate * gas_price
        
        # Convert gas cost to BNB
        gas_cost_bnb = w3.from_wei(gas_cost_wei, 'ether')
        
        if status_callback:
            await status_callback(f"Gas estimate: {gas_estimate} units")
            await status_callback(f"Gas price: {w3.from_wei(gas_price, 'gwei')} Gwei")
            await status_callback(f"Total gas cost: {gas_cost_bnb} BNB")
        
        return {
            'gas_wei': gas_cost_wei,
            'gas_bnb': float(gas_cost_bnb),
            'gas_estimate': gas_estimate,
            'gas_price': gas_price
        }
    except Exception as e:
        if status_callback:
            await status_callback(f"Error estimating gas: {str(e)}")
        raise

async def estimate_token_transfer_gas(
    from_address: str, 
    to_address: str, 
    token_address: str, 
    amount: Union[float, str, Decimal], 
    decimals: int, 
    status_callback: Optional[Callable[[str], Awaitable[None]]] = None
) -> Dict[str, Union[int, float]]:
    """
    Estimate gas for a token transfer.
    
    Args:
        from_address (str): Sender address
        to_address (str): Recipient address
        token_address (str): Token contract address
        amount (Union[float, str, Decimal]): Amount of tokens to send
        decimals (int): Token decimals
        status_callback (Optional[Callable[[str], Awaitable[None]]]): Function to call with status updates
        
    Returns:
        Dict[str, Union[int, float]]: Gas estimation info
            {
                'gas_wei': int,       # Gas cost in wei
                'gas_bnb': float,     # Gas cost in BNB
                'gas_estimate': int,  # Gas units needed
                'gas_price': int      # Current gas price in wei
            }
    """
    if status_callback:
        await status_callback("Estimating gas fees for token transfer...")
    
    # Convert to checksum addresses
    from_checksum = w3.to_checksum_address(from_address)
    to_checksum = w3.to_checksum_address(to_address)
    token_checksum = w3.to_checksum_address(token_address)
    
    # Get token contract
    token_contract = get_token_contract(token_checksum)
    
    # Convert token amount to raw amount
    amount_raw = convert_to_raw_amount(amount, decimals)
    
    try:
        # Estimate gas for transfer
        gas_estimate = token_contract.functions.transfer(
            to_checksum, amount_raw
        ).estimate_gas({'from': from_checksum})
        
        # Get gas price
        gas_price = w3.eth.gas_price
        
        # Calculate total gas cost in wei
        gas_cost_wei = gas_estimate * gas_price
        
        # Convert gas cost to BNB
        gas_cost_bnb = w3.from_wei(gas_cost_wei, 'ether')
        
        if status_callback:
            await status_callback(f"Gas estimate: {gas_estimate} units")
            await status_callback(f"Gas price: {w3.from_wei(gas_price, 'gwei')} Gwei")
            await status_callback(f"Total gas cost: {gas_cost_bnb} BNB")
        
        return {
            'gas_wei': gas_cost_wei,
            'gas_bnb': float(gas_cost_bnb),
            'gas_estimate': gas_estimate,
            'gas_price': gas_price
        }
    except Exception as e:
        if status_callback:
            await status_callback(f"Error estimating gas for token transfer: {str(e)}")
        raise

async def estimate_contract_call_gas(
    from_address: str,
    to_contract_address: str,
    contract_abi: List[Dict[str, Any]],
    function_name: str,
    function_args: List[Any],
    status_callback: Optional[Callable[[str], Awaitable[None]]] = None,
    value_wei: int = 0
) -> Dict[str, Union[int, float]]:
    """
    Estimate gas for a contract call.
    """
    if status_callback:
        await status_callback("Estimating gas fees for contract call...")
    
    # Convert to checksum addresses
    from_checksum = w3.to_checksum_address(from_address)
    to_checksum = w3.to_checksum_address(to_contract_address)
    
    # Get contract
    contract = w3.eth.contract(address=to_checksum, abi=contract_abi)   
    
    # Build function call
    function_call = contract.functions[function_name](*function_args)
    
    # Estimate gas
    gas_estimate = function_call.estimate_gas({'from': from_checksum, 'value': value_wei})
    
    # Get gas price
    gas_price = w3.eth.gas_price
    
    # Calculate total gas cost in wei
    gas_cost_wei = gas_estimate * gas_price
    
    # Convert gas cost to BNB
    gas_cost_bnb = w3.from_wei(gas_cost_wei, 'ether')
    
    if status_callback:
        await status_callback(f"Total gas cost: {gas_cost_bnb} BNB\nGas price: {w3.from_wei(gas_price, 'gwei')} Gwei")
        
    return {
        'gas_wei': gas_cost_wei,
        'gas_bnb': float(gas_cost_bnb),
        'gas_estimate': gas_estimate,
        'gas_price': gas_price
    }

async def estimate_max_bnb_transfer(
    from_address: str, 
    to_address: str, 
    balance: Union[float, str, int, Decimal], 
    status_callback: Optional[Callable[[str], Awaitable[None]]] = None
) -> Dict[str, Union[int, float, str]]:
    """
    Estimate the maximum amount of BNB that can be transferred after accounting for gas fees.
    
    Args:
        from_address (str): Sender address
        to_address (str): Recipient address
        balance (Union[float, str, Decimal]): Current BNB balance
        status_callback (Optional[Callable[[str], Awaitable[None]]]): Function to call with status updates
        
    Returns:
        Dict[str, Union[int, float, str]]: Max transfer info
            {
                'max_amount': float,      # Maximum amount that can be sent in BNB
                'max_amount_wei': int,    # Maximum amount in wei
                'gas_wei': int,           # Gas cost in wei
                'gas_bnb': float,         # Gas cost in BNB
                'error': str (optional)   # Error message if any
            }
    """
    if status_callback:
        await status_callback("Calculating maximum transferable amount...")
    
    # First, get the gas estimate for a sample transfer of a small amount
    try:
        # Convert balance to float for calculations
        balance_float = float(balance)
        
        # Try with 70% of the balance first to ensure we have enough for gas
        test_amount = balance_float * 0.7
        
        # Get gas estimate
        gas_info = await estimate_bnb_transfer_gas(
            from_address, to_address, test_amount, status_callback
        )
        
        # Calculate max amount
        gas_cost_bnb = gas_info['gas_bnb']
        max_amount = balance_float - gas_cost_bnb
        
        # Guard against negative amounts due to high gas costs
        if max_amount <= 0:
            return {
                'max_amount': 0,
                'max_amount_wei': 0,
                'gas_wei': gas_info['gas_wei'],
                'gas_bnb': gas_cost_bnb,
                'error': "Gas cost exceeds balance"
            }
        
        # Convert to wei for precision
        max_amount_wei = w3.to_wei(max_amount, 'ether')
        
        if status_callback:
            await status_callback(f"Maximum transferable amount: {max_amount} BNB")
            await status_callback(f"Gas cost: {gas_cost_bnb} BNB")
        
        return {
            'max_amount': max_amount,
            'max_amount_wei': max_amount_wei,
            'gas_wei': gas_info['gas_wei'],
            'gas_bnb': gas_cost_bnb
        }
    except Exception as e:
        if status_callback:
            await status_callback(f"Error calculating maximum amount: {str(e)}")
        return {
            'max_amount': 0,
            'max_amount_wei': 0,
            'gas_wei': 0,
            'gas_bnb': 0,
            'error': str(e)
        } 