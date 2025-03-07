"""
Transaction sending module for BNB and BEP20 tokens.
"""
from utils.web3_connection import w3
from eth_account import Account
from utils.token_operations import get_token_contract, get_token_details, convert_to_raw_amount
import time

def send_bnb(from_private_key, to_address, amount_bnb, status_callback=None):
    """
    Send BNB from one address to another.
    
    Args:
        from_private_key (str): Private key of the sender
        to_address (str): Address of the recipient
        amount_bnb (float): Amount of BNB to send
        status_callback (callable, optional): Function to call with status updates
        
    Returns:
        dict: Transaction result
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
    
    # Convert to checksum address
    checksum_to_address = w3.to_checksum_address(to_address)
    checksum_from_address = w3.to_checksum_address(from_address)
    
    if status_callback:
        status_callback(f"Preparing to send {amount_bnb} BNB from {checksum_from_address[:6]}...{checksum_from_address[-4:]} to {checksum_to_address[:6]}...{checksum_to_address[-4:]}...")
    
    # Convert BNB to Wei
    amount_wei = w3.to_wei(amount_bnb, 'ether')
    
    if status_callback:
        status_callback("Fetching current gas price...")
    
    gas_price = w3.eth.gas_price
    
    if status_callback:
        status_callback(f"Current gas price: {w3.from_wei(gas_price, 'gwei')} Gwei")
    
    if status_callback:
        status_callback("Getting nonce for transaction...")
    
    # Get nonce for the sending address
    nonce = w3.eth.get_transaction_count(checksum_from_address)
    
    if status_callback:
        status_callback("Building transaction...")
    
    # Prepare transaction
    tx = {
        'nonce': nonce,
        'to': checksum_to_address,
        'value': amount_wei,
        'gas': 21000,  # Standard gas limit for simple transfers
        'gasPrice': gas_price,
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
        status_callback(f"Transaction sent! Hash: {tx_hash_hex}")
        status_callback("Waiting for transaction confirmation...")
    
    # Wait for transaction receipt
    start_time = time.time()
    update_interval = 5  # seconds
    next_update = start_time + update_interval
    
    while True:
        try:
            receipt = w3.eth.get_transaction_receipt(tx_hash)
            break
        except Exception:
            # Transaction not yet mined
            current_time = time.time()
            if current_time >= next_update:
                elapsed = int(current_time - start_time)
                if status_callback:
                    status_callback(f"Still waiting for confirmation... ({elapsed}s)")
                next_update = current_time + update_interval
            time.sleep(1)
    
    if status_callback:
        if receipt['status'] == 1:
            status_callback(f"Transaction confirmed in block {receipt['blockNumber']}! ✅")
        else:
            status_callback(f"Transaction failed in block {receipt['blockNumber']}! ❌")
    
    return {
        'tx_hash': tx_hash_hex,
        'status': receipt['status'],
        'block_number': receipt['blockNumber']
    }

def send_token(from_private_key, token_address, to_address, amount, status_callback=None):
    """
    Send BEP20 tokens from one address to another.
    
    Args:
        from_private_key (str): Private key of the sender
        token_address (str): Address of the token contract
        to_address (str): Address of the recipient
        amount (float): Amount of tokens to send (in human-readable form)
        status_callback (callable, optional): Function to call with status updates
        
    Returns:
        dict: Transaction result
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
    
    # Get token contract
    token_contract = get_token_contract(token_address, status_callback)
    
    # Get token details
    token_details = get_token_details(token_contract, status_callback)
    symbol = token_details['symbol']
    decimals = token_details['decimals']
    
    # Convert token amount to raw amount considering decimals
    raw_amount = convert_to_raw_amount(amount, decimals)
    
    if status_callback:
        status_callback(f"Preparing to send {amount} {symbol} ({raw_amount} raw units) to {checksum_to_address[:6]}...{checksum_to_address[-4:]}...")
    
    if status_callback:
        status_callback("Fetching current gas price...")
    
    gas_price = w3.eth.gas_price
    
    if status_callback:
        status_callback(f"Current gas price: {w3.from_wei(gas_price, 'gwei')} Gwei")
    
    if status_callback:
        status_callback("Getting nonce for transaction...")
    
    # Get nonce
    nonce = w3.eth.get_transaction_count(checksum_from_address)
    
    if status_callback:
        status_callback("Building transaction...")
    
    # Build transaction for token transfer
    tx = token_contract.functions.transfer(
        checksum_to_address, 
        raw_amount
    ).build_transaction({
        'chainId': 56,
        'gas': 100000,  # Higher gas limit for token transfers
        'gasPrice': gas_price,
        'nonce': nonce,
    })
    
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
        status_callback(f"Transaction sent! Hash: {tx_hash_hex}")
        status_callback("Waiting for transaction confirmation...")
    
    # Wait for transaction receipt
    start_time = time.time()
    update_interval = 5  # seconds
    next_update = start_time + update_interval
    
    while True:
        try:
            receipt = w3.eth.get_transaction_receipt(tx_hash)
            break
        except Exception:
            # Transaction not yet mined
            current_time = time.time()
            if current_time >= next_update:
                elapsed = int(current_time - start_time)
                if status_callback:
                    status_callback(f"Still waiting for confirmation... ({elapsed}s)")
                next_update = current_time + update_interval
            time.sleep(1)
    
    if status_callback:
        if receipt['status'] == 1:
            status_callback(f"Transaction confirmed in block {receipt['blockNumber']}! ✅")
        else:
            status_callback(f"Transaction failed in block {receipt['blockNumber']}! ❌")
    
    return {
        'tx_hash': tx_hash_hex,
        'status': receipt['status'],
        'block_number': receipt['blockNumber']
    } 