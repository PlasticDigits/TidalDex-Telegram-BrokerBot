"""
Transaction sending module for BNB and BEP20 tokens.
"""
from typing import Dict, Any, Optional, Callable, Union, List, Awaitable
from decimal import Decimal
from utils.web3_connection import w3
from eth_account import Account
from utils.token_operations import get_token_contract, get_token_details, convert_to_raw_amount
from utils.gas_estimation import estimate_bnb_transfer_gas, estimate_token_transfer_gas, estimate_contract_call_gas
from web3.types import Wei
import time

def send_bnb(
    from_private_key: str, 
    to_address: str, 
    amount_bnb: Union[float, Decimal, str], 
    status_callback: Optional[Callable[[str], None]] = None
) -> Dict[str, Union[str, int]]:
    """
    Send BNB from one address to another.
    
    Args:
        from_private_key (str): Private key of the sender
        to_address (str): Address of the recipient
        amount_bnb (Union[float, Decimal, str]): Amount of BNB to send
        status_callback (Optional[Callable[[str], None]]): Function to call with status updates
        
    Returns:
        Dict[str, Union[str, int]]: Transaction result
            {
                'tx_hash': str,     # Transaction hash
                'status': int,      # Transaction status (1 = success)
                'block_number': int # Block where transaction was included
            }
    """
    if status_callback:
        status_callback("Deriving sender address from private key...")
    
    account = Account.from_key(from_private_key)
    from_address = account.address
    
    if status_callback:
        status_callback("Converting addresses to checksum format...")
    
    # Convert to checksum addresses
    checksum_from_address = w3.to_checksum_address(from_address)
    checksum_to_address = w3.to_checksum_address(to_address)
    
    if status_callback:
        status_callback("Checking BNB balance...")
    
    # Check if sender has enough balance
    balance_wei = w3.eth.get_balance(checksum_from_address)
    balance_bnb = w3.from_wei(balance_wei, 'ether')
    
    # Convert amount to wei
    amount_wei = w3.to_wei(amount_bnb, 'ether')

    gas_estimate = estimate_bnb_transfer_gas(checksum_from_address, checksum_to_address, amount_bnb, status_callback)

    amount_bnb_with_gas = Decimal(str(amount_bnb)) + Decimal(str(gas_estimate['gas_bnb']))
    amount_wei_with_gas = amount_wei + gas_estimate['gas_wei']
    
    if status_callback:
        status_callback(f"Your balance: {balance_bnb} BNB")
        status_callback(f"Sending: {amount_bnb} BNB")
    
    if amount_wei_with_gas > balance_wei:
        error_msg = f"Insufficient balance. You have {balance_bnb} BNB but trying to send {amount_bnb_with_gas} BNB (including gas fees)."
        if status_callback:
            status_callback(f"Error: {error_msg}")
        raise ValueError(error_msg)
    
    if status_callback:
        status_callback("Building transaction...")
    
    if status_callback:
        status_callback(f"Estimated gas cost: {gas_estimate['gas_bnb']} BNB")
    
    nonce = w3.eth.get_transaction_count(checksum_from_address)

    # Prepare transaction
    tx = {
        'nonce': nonce,
        'to': checksum_to_address,
        'value': amount_wei_with_gas,
        'gas': gas_estimate['gas_estimate'],
        'gasPrice': gas_estimate['gas_price'],
        'chainId': 56  # BSC mainnet
    }
    
    if status_callback:
        status_callback("Signing transaction...")
    
    # Sign transaction
    signed_tx = w3.eth.account.sign_transaction(tx, from_private_key)
    
    if status_callback:
        status_callback("Sending transaction to network...")
    
    # Send transaction
    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    tx_hash_hex = tx_hash.hex()
    
    if status_callback:
        status_callback(f"Transaction sent with hash: {tx_hash_hex}")
        status_callback("Waiting for transaction confirmation...")
    
    # Wait for transaction receipt
    max_attempts = 20
    attempts = 0
    
    while attempts < max_attempts:
        try:
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
            
            if status_callback:
                status_callback(f"Transaction confirmed in block {receipt['blockNumber']}")
                status_callback(f"Status: {'Success' if receipt['status'] == 1 else 'Failed'}")
            
            return {
                'tx_hash': tx_hash_hex,
                'status': receipt['status'],
                'block_number': receipt['blockNumber']
            }
        except Exception as e:
            attempts += 1
            if status_callback:
                status_callback(f"Waiting for confirmation... ({attempts}/{max_attempts})")
            time.sleep(5)  # Wait 5 seconds before checking again
    
    # If we get here, the transaction didn't confirm in time
    if status_callback:
        status_callback("Timed out waiting for transaction confirmation.")
        status_callback("The transaction may still confirm later.")
    
    return {
        'tx_hash': tx_hash_hex,
        'status': 0,
        'block_number': 0
    }

async def send_token(
    from_private_key: str, 
    token_address: str, 
    to_address: str, 
    amount: Union[float, Decimal, str], 
    status_callback: Optional[Callable[[str], Awaitable[None]]] = None
) -> Dict[str, Union[str, int]]:
    """
    Send BEP20 tokens from one address to another.
    
    Args:
        from_private_key (str): Private key of the sender
        token_address (str): Address of the token contract
        to_address (str): Address of the recipient
        amount (Union[float, Decimal, str]): Amount of tokens to send (in human-readable form)
        status_callback (Optional[Callable[[str], Awaitable[None]]]): Function to call with status updates
        
    Returns:
        Dict[str, Union[str, int]]: Transaction result
            {
                'tx_hash': str,     # Transaction hash
                'status': int,      # Transaction status (1 = success)
                'block_number': int # Block where transaction was included
            }
    """
    if status_callback:
        status_callback("Deriving sender address from private key...")
    
    account = Account.from_key(from_private_key)
    from_address = account.address
    
    if status_callback:
        status_callback("Converting addresses to checksum format...")
    
    # Convert to checksum addresses
    checksum_to_address = w3.to_checksum_address(to_address)
    checksum_from_address = w3.to_checksum_address(from_address)
    checksum_token_address = w3.to_checksum_address(token_address)
    
    if status_callback:
        status_callback("Loading token contract...")
    
    # Get the token contract
    token_contract = get_token_contract(checksum_token_address)
    
    # Get token details
    if status_callback:
        await status_callback("Getting token details...")
        
    token_details = await get_token_details(token_contract, status_callback)
    symbol = token_details.get('symbol', 'Unknown')
    decimals = token_details.get('decimals', 18)
    
    if status_callback:
        await status_callback(f"Token: {symbol}, Decimals: {decimals}")
    
    # Check token balance
    if status_callback:
        status_callback(f"Checking {symbol} balance...")
    
    token_balance_raw = token_contract.functions.balanceOf(checksum_from_address).call()
    token_balance = token_balance_raw / (10 ** decimals)
    
    if status_callback:
        status_callback(f"Your balance: {token_balance} {symbol}")
        status_callback(f"Sending: {amount} {symbol}")
    
    # Convert to token units
    amount_raw = convert_to_raw_amount(amount, decimals)
    
    # Check if sufficient balance
    if amount_raw > token_balance_raw:
        error_msg = f"Insufficient {symbol} balance. You have {token_balance} but trying to send {amount}."
        if status_callback:
            status_callback(f"Error: {error_msg}")
        raise ValueError(error_msg)
    
    # Get the nonce for the sender address
    nonce = w3.eth.get_transaction_count(checksum_from_address)
    
    # Prepare the transfer function call
    transfer_function = token_contract.functions.transfer(checksum_to_address, amount_raw)
    
    # Estimate gas for the transfer
    if status_callback:
        status_callback("Estimating gas cost...")
    
    try:
        gas_estimate = estimate_token_transfer_gas(checksum_from_address, checksum_to_address, checksum_token_address, amount, decimals, status_callback)
        
        if status_callback:
            status_callback(f"Estimated gas cost: {gas_estimate['gas_bnb']} BNB")
        
        # Check BNB balance for gas
        bnb_balance_wei = w3.eth.get_balance(checksum_from_address)
        bnb_balance = w3.from_wei(bnb_balance_wei, 'ether')
        
        if gas_estimate['gas_wei'] > bnb_balance_wei:
            error_msg = f"Insufficient BNB for gas. You need {gas_estimate['gas_bnb']} BNB but have {bnb_balance} BNB."
            if status_callback:
                status_callback(f"Error: {error_msg}")
            raise ValueError(error_msg)
        
        # Build the transaction
        if status_callback:
            status_callback("Building transaction...")
        
        tx = transfer_function.build_transaction({
            'from': checksum_from_address,
            'nonce': nonce,
            'gas': int(gas_estimate['gas_estimate']),
            'gasPrice': Wei(int(gas_estimate['gas_price'])),
            'chainId': 56  # BSC mainnet
        })
        
        # Sign the transaction
        if status_callback:
            status_callback("Signing transaction...")
            
        signed_tx = w3.eth.account.sign_transaction(tx, from_private_key)
        
        # Send the transaction
        if status_callback:
            status_callback("Sending transaction to network...")
            
        tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
        tx_hash_hex = tx_hash.hex()
        
        if status_callback:
            status_callback(f"Transaction sent with hash: {tx_hash_hex}")
            status_callback("Waiting for transaction confirmation...")
        
        # Wait for transaction receipt
        max_attempts = 20
        attempts = 0
        
        while attempts < max_attempts:
            try:
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
                
                if status_callback:
                    status_callback(f"Transaction confirmed in block {receipt['blockNumber']}")
                    status_callback(f"Status: {'Success' if receipt['status'] == 1 else 'Failed'}")
                
                return {
                    'tx_hash': tx_hash_hex,
                    'status': receipt['status'],
                    'block_number': receipt['blockNumber']
                }
            except Exception as e:
                attempts += 1
                if status_callback:
                    status_callback(f"Waiting for confirmation... ({attempts}/{max_attempts})")
                time.sleep(5)  # Wait 5 seconds before checking again
        
        # If we get here, the transaction didn't confirm in time
        if status_callback:
            status_callback("Timed out waiting for transaction confirmation.")
            status_callback("The transaction may still confirm later.")
        
        return {
            'tx_hash': tx_hash_hex,
            'status': 0,
            'block_number': 0
        }
    except Exception as e:
        if status_callback:
            status_callback(f"Error: {str(e)}")
        raise 

def send_contract_call(
    from_private_key: str,
    to_contract_address: str,
    contract_abi: List[Dict[str, Any]],
    function_name: str,
    function_args: List[Any],
    status_callback: Optional[Callable[[str], None]] = None
) -> Dict[str, Union[str, int]]:
    """
    Call a contract address with a function name and arguments.
    """
    if status_callback:
        status_callback("Deriving sender address from private key...")
    
    account = Account.from_key(from_private_key)
    from_address = account.address
    
    if status_callback:
        status_callback("Converting addresses to checksum format...")
    
    checksum_from_address = w3.to_checksum_address(from_address)
    checksum_to_contract_address = w3.to_checksum_address(to_contract_address)
    
    if status_callback:
        status_callback("Loading contract...")
    
    contract = w3.eth.contract(address=checksum_to_contract_address, abi=contract_abi)
    
    if status_callback:
        status_callback("Building transaction...")

    function_call = contract.functions[function_name](*function_args)
    
    if status_callback:
        status_callback("Estimating gas cost...")
    
    gas_estimate = estimate_contract_call_gas(checksum_from_address, checksum_to_contract_address, contract_abi, function_name, function_args, status_callback)

    bnb_balance_wei = w3.eth.get_balance(checksum_from_address)
    bnb_balance = w3.from_wei(bnb_balance_wei, 'ether')

    if gas_estimate['gas_wei'] > bnb_balance_wei:
        error_msg = f"Insufficient BNB for gas. You need {gas_estimate['gas_bnb']} BNB but have {bnb_balance} BNB."
        if status_callback:
            status_callback(f"Error: {error_msg}")
        raise ValueError(error_msg)

    if status_callback:
        status_callback(f"Estimated gas cost: {gas_estimate['gas_bnb']} BNB")
    
    nonce = w3.eth.get_transaction_count(checksum_from_address)
    
    tx = function_call.build_transaction({
        'from': checksum_from_address,
        'nonce': nonce,
        'gas': int(gas_estimate['gas_estimate']),
        'gasPrice': Wei(int(gas_estimate['gas_price'])),
        'chainId': 56  # BSC mainnet
    })

    if status_callback:
        status_callback("Signing transaction...")
    
    signed_tx = w3.eth.account.sign_transaction(tx, from_private_key)

    if status_callback:
        status_callback("Sending transaction to network...")
    
    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    tx_hash_hex = tx_hash.hex()
    
    if status_callback:
        status_callback(f"Transaction sent with hash: {tx_hash_hex}")
        status_callback("Waiting for transaction confirmation...")
    
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    
    if status_callback:
        status_callback(f"Transaction confirmed in block {receipt['blockNumber']}")
        status_callback(f"Status: {'Success' if receipt['status'] == 1 else 'Failed'}")
    
    return {
        'tx_hash': tx_hash_hex,
        'status': receipt['status'],
        'block_number': receipt['blockNumber']
    }