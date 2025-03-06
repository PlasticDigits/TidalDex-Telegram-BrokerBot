"""
Gas estimation utilities for BSC transactions.
"""
from utils.web3_connection import w3
from utils.token_operations import get_token_contract, convert_to_raw_amount

def estimate_bnb_transfer_gas(from_address, to_address, amount_bnb, status_callback=None):
    """
    Estimate gas for a BNB transfer.
    
    Args:
        from_address (str): Sender address
        to_address (str): Recipient address
        amount_bnb (float): Amount of BNB to send
        status_callback (callable, optional): Function to call with status updates
        
    Returns:
        dict: Gas estimation info
            {
                'gas_wei': int,       # Gas cost in wei
                'gas_bnb': float,     # Gas cost in BNB
                'gas_estimate': int,  # Gas units needed
                'gas_price': int      # Current gas price in wei
            }
    """
    if status_callback:
        status_callback("Estimating gas fees for transaction...")
    
    # Convert to checksum addresses
    from_checksum = w3.to_checksum_address(from_address)
    to_checksum = w3.to_checksum_address(to_address)
    
    # Convert amount to wei
    amount_wei = w3.to_wei(amount_bnb, 'ether')
    
    # Get current gas price
    gas_price = w3.eth.gas_price
    
    # Estimate gas for the transaction
    try:
        gas_estimate = w3.eth.estimate_gas({
            'to': to_checksum,
            'from': from_checksum,
            'value': amount_wei
        })
        
        # Calculate total gas cost in wei and BNB
        gas_cost_wei = gas_price * gas_estimate
        gas_cost_bnb = w3.from_wei(gas_cost_wei, 'ether')
        
        if status_callback:
            status_callback(f"Estimated gas cost: {gas_cost_bnb} BNB")
        
        return {
            'gas_wei': gas_cost_wei,
            'gas_bnb': gas_cost_bnb,
            'gas_estimate': gas_estimate,
            'gas_price': gas_price
        }
    except Exception as e:
        if status_callback:
            status_callback(f"Error estimating gas: {str(e)}")
        raise

def estimate_token_transfer_gas(from_address, to_address, token_address, amount, decimals, status_callback=None):
    """
    Estimate gas for a token transfer.
    
    Args:
        from_address (str): Sender address
        to_address (str): Recipient address
        token_address (str): Token contract address
        amount (float): Amount of tokens to send
        decimals (int): Token decimals
        status_callback (callable, optional): Function to call with status updates
        
    Returns:
        dict: Gas estimation info
            {
                'gas_wei': int,       # Gas cost in wei
                'gas_bnb': float,     # Gas cost in BNB
                'gas_estimate': int,  # Gas units needed
                'gas_price': int      # Current gas price in wei
            }
    """
    if status_callback:
        status_callback("Estimating gas fees for token transaction...")
    
    # Convert to checksum addresses
    from_checksum = w3.to_checksum_address(from_address)
    to_checksum = w3.to_checksum_address(to_address)
    token_checksum = w3.to_checksum_address(token_address)
    
    # Get token contract
    token_contract = get_token_contract(token_checksum, status_callback)
    
    # Convert amount to token units
    token_amount = convert_to_raw_amount(amount, decimals)
    
    # Get current gas price
    gas_price = w3.eth.gas_price
    
    # Prepare the transfer function to estimate gas
    transfer_function = token_contract.functions.transfer(
        to_checksum,
        token_amount
    )
    
    # Estimate gas
    try:
        gas_estimate = transfer_function.estimate_gas({
            'from': from_checksum
        })
        
        # Calculate total gas cost in wei and BNB
        gas_cost_wei = gas_price * gas_estimate
        gas_cost_bnb = w3.from_wei(gas_cost_wei, 'ether')
        
        if status_callback:
            status_callback(f"Estimated gas cost: {gas_cost_bnb} BNB")
        
        return {
            'gas_wei': gas_cost_wei,
            'gas_bnb': gas_cost_bnb,
            'gas_estimate': gas_estimate,
            'gas_price': gas_price
        }
    except Exception as e:
        if status_callback:
            status_callback(f"Error estimating token transfer gas: {str(e)}")
        # Provide a default gas estimate for token transfers
        return {
            'gas_wei': w3.to_wei(0.002, 'ether'),
            'gas_bnb': 0.002,  # Default value
            'gas_estimate': 100000,  # Conservative default
            'gas_price': gas_price
        }

def estimate_max_bnb_transfer(from_address, to_address, balance, status_callback=None):
    """
    Estimate the maximum amount of BNB that can be sent after accounting for gas fees.
    
    Args:
        from_address (str): Sender address
        to_address (str): Recipient address
        balance (float): Current BNB balance
        status_callback (callable, optional): Function to call with status updates
        
    Returns:
        float: Maximum amount of BNB that can be sent
    """
    if status_callback:
        status_callback("Calculating maximum sendable BNB amount...")
    
    # Use 90% of balance for estimation to ensure it's not over the actual balance
    dummy_amount = balance * 0.9
    
    # Estimate gas using a dummy amount
    gas_info = estimate_bnb_transfer_gas(
        from_address, 
        to_address, 
        dummy_amount, 
        status_callback
    )
    
    gas_cost_bnb = gas_info['gas_bnb']
    
    # Calculate the actual amount to send (entire balance minus gas cost)
    max_amount = balance - gas_cost_bnb
    
    if max_amount <= 0:
        if status_callback:
            status_callback(f"❌ Insufficient balance. Your balance of {balance} BNB is not enough to cover gas costs of {gas_cost_bnb} BNB.")
        raise ValueError(f"Insufficient balance for gas. Balance: {balance} BNB, Gas cost: {gas_cost_bnb} BNB")
    
    if status_callback:
        status_callback(f"Maximum sendable amount: {max_amount} BNB")
    
    return max_amount 