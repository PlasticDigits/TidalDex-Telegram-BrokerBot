from typing import Dict, Optional, Any, List, Callable, Awaitable
from web3 import Web3
from web3.types import ChecksumAddress
import logging
from decimal import Decimal
import json
import os
from pathlib import Path
from utils.gas_estimation import (
    estimate_token_transfer_gas,
    estimate_contract_call_gas
)
from utils.load_abi import load_abi
from utils.config import get_env_var, BSC_SCANNER_URL, INTERMEDIATE_LP_ADDRESS
from utils.status_updates import with_status_updates, create_status_callback
from utils.web3_connection import w3  # Import the shared Web3 connection

logger = logging.getLogger(__name__)

class SwapManager:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SwapManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.w3 = w3  # Use the shared Web3 connection
            
            # Load router ABI
            self.router_abi = load_abi("TidalDexRouter")
            
            # Get router address from environment
            self.router_address = get_env_var('DEX_ROUTER_ADDRESS')
            if not self.router_address:
                raise ValueError("DEX_ROUTER_ADDRESS environment variable not set")
            
            # Create router contract instance
            self.router_contract = self.w3.eth.contract(
                address=self.router_address,
                abi=self.router_abi
            )
            
            self._initialized = True

    @with_status_updates("Swap Quote")
    async def get_swap_quote(
        self,
        from_token_address: str,
        to_token_address: str,
        amount_in: int,
        slippage_bps: int,
        status_callback: Optional[Callable[[str], Awaitable[None]]] = None
    ) -> Optional[Dict[str, Any]]:
        """Get a quote for a token swap using TidalDexRouter.
        
        Args:
            from_token_address: Address of the token to swap from
            to_token_address: Address of the token to swap to
            amount_in: Amount of from_token to swap (in wei)
            slippage_bps: Slippage tolerance in basis points (1% = 100)
            
        Returns:
            Dictionary containing swap quote details or None if quote failed
        """
        try:
            if status_callback:
                await status_callback("Calculating swap path...")
            
            # Get the path for the swap using the new method
            path: List[str] = self.get_route_path(from_token_address, to_token_address)
            
            if status_callback:
                await status_callback("Getting amounts out from router...")
            
            # Get amounts out
            amounts_out = self.router_contract.functions.getAmountsOut(
                amount_in,
                path
            ).call()
            
            if not amounts_out or len(amounts_out) < 2:
                logger.error("Invalid amounts out from router")
                if status_callback:
                    await status_callback("Error: Invalid amounts out from router")
                return None
            
            amount_out = amounts_out[1]
            
            if status_callback:
                await status_callback("Calculating price impact...")
            
            # Calculate price impact
            # TODO: Implement proper price impact calculation
            # For now, using a placeholder value
            price_impact = 0.1  # Placeholder
            
            if status_callback:
                await status_callback("Quote calculation complete")
            
            return {
                'amount_out': amount_out,
                'price_impact': price_impact,
                'path': path,
                'slippage_bps': slippage_bps
            }
            
        except Exception as e:
            logger.error(f"Error getting swap quote: {e}")
            if status_callback:
                await status_callback(f"Error getting swap quote: {str(e)}")
            return None

    @with_status_updates("Token Swap")
    async def execute_swap(
        self,
        wallet: Dict[str, Any],
        from_token_address: str,
        to_token_address: str,
        amount_in: int,
        slippage_bps: int,
        quote: Dict[str, Any],
        status_callback: Optional[Callable[[str], Awaitable[None]]] = None
    ) -> Optional[str]:
        """Execute a token swap using TidalDexRouter.
        
        Args:
            wallet: User's wallet information
            from_token_address: Address of the token to swap from
            to_token_address: Address of the token to swap to
            amount_in: Amount of from_token to swap (in wei)
            slippage_bps: Slippage tolerance in basis points (1% = 100)
            quote: Swap quote from get_swap_quote
            status_callback: Optional callback for status updates
            
        Returns:
            Transaction hash if successful, None otherwise
        """
        try:
            # Get wallet address and private key
            wallet_address = wallet['address']
            private_key = wallet['private_key']
            
            if status_callback:
                await status_callback("Loading token contract...")
            
            # Create token contract instance
            token_abi = load_abi("ERC20")
            token_contract = self.w3.eth.contract(
                address=from_token_address,
                abi=token_abi
            )
            
            if status_callback:
                await status_callback("Checking token allowance...")
            
            # Check allowance
            allowance = token_contract.functions.allowance(
                wallet_address,
                self.router_address
            ).call()
            
            # If allowance is insufficient, approve the router
            if allowance < amount_in:
                if status_callback:
                    await status_callback("Approving token spending...")
                
                # Estimate gas for approval
                gas_info = await estimate_contract_call_gas(
                    wallet_address,
                    from_token_address,
                    token_abi,
                    'approve',
                    [self.router_address, amount_in],
                    status_callback
                )
                
                approve_tx = token_contract.functions.approve(
                    self.router_address,
                    amount_in
                ).build_transaction({
                    'from': wallet_address,
                    'nonce': self.w3.eth.get_transaction_count(wallet_address),
                    'gas': gas_info['gas_estimate'],
                    'gasPrice': gas_info['gas_price']
                })
                
                if status_callback:
                    await status_callback("Signing approval transaction...")
                
                signed_approve_tx = self.w3.eth.account.sign_transaction(
                    approve_tx,
                    private_key
                )
                
                if status_callback:
                    await status_callback("Sending approval transaction...")
                
                approve_tx_hash = self.w3.eth.send_raw_transaction(
                    signed_approve_tx.rawTransaction
                )
                
                if status_callback:
                    await status_callback("Waiting for approval transaction...")
                
                # Wait for approval transaction to be mined
                self.w3.eth.wait_for_transaction_receipt(approve_tx_hash)
                
                if status_callback:
                    await status_callback("Token spending approved")
            
            # Calculate minimum amount out with slippage
            amount_out_min = int(quote['amount_out'] * (10000 - slippage_bps) / 10000)
            
            if status_callback:
                await status_callback("Estimating gas for swap...")
            
            # Get the path for the swap using the new method
            path = self.get_route_path(from_token_address, to_token_address)
            
            # Estimate gas for swap
            gas_info = await estimate_contract_call_gas(
                wallet_address,
                self.router_address,
                self.router_abi,
                'swapExactTokensForTokens',
                [
                    amount_in,
                    amount_out_min,
                    path,
                    wallet_address,
                    int(self.w3.eth.get_block('latest')['timestamp'] + 300)
                ],
                status_callback
            )
            
            if status_callback:
                await status_callback("Building swap transaction...")
            
            # Build swap transaction
            swap_tx = self.router_contract.functions.swapExactTokensForTokens(
                amount_in,  # amountIn
                amount_out_min,  # amountOutMin
                path,  # path
                wallet_address,  # to
                int(self.w3.eth.get_block('latest')['timestamp'] + 300)  # deadline (5 minutes)
            ).build_transaction({
                'from': wallet_address,
                'nonce': self.w3.eth.get_transaction_count(wallet_address),
                'gas': gas_info['gas_estimate'],
                'gasPrice': gas_info['gas_price']
            })
            
            if status_callback:
                await status_callback("Signing swap transaction...")
            
            # Sign and send transaction
            signed_swap_tx = self.w3.eth.account.sign_transaction(
                swap_tx,
                private_key
            )
            
            if status_callback:
                await status_callback("Sending swap transaction...")
            
            tx_hash = self.w3.eth.send_raw_transaction(
                signed_swap_tx.rawTransaction
            )
            tx_hash_hex = tx_hash.hex()
            
            # status_callback prepend
            status_callback_prepend = f"Hash: {tx_hash_hex}\n{BSC_SCANNER_URL}/tx/{tx_hash_hex}\n\n"
            
            if status_callback:
                await status_callback(status_callback_prepend + "Transaction sent!")
                await status_callback(status_callback_prepend + "Waiting for confirmation...")
            
            # Wait for transaction to be mined
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            
            if receipt.status == 1:
                if status_callback:
                    await status_callback(status_callback_prepend + "Swap completed successfully!")
                return tx_hash_hex
            else:
                logger.error("Swap transaction failed")
                if status_callback:
                    await status_callback(status_callback_prepend + "Swap transaction failed")
                return None
                
        except Exception as e:
            logger.error(f"Error executing swap: {e}")
            if status_callback:
                await status_callback(f"Error: {str(e)}")
            return None

    def get_route_path(self, input_token: str, output_token: str) -> List[str]:
        """
        Determine the optimal route path between input and output tokens.
        
        If either token is the INTERMEDIATE_LP_ADDRESS, returns a direct path.
        Otherwise, routes through INTERMEDIATE_LP_ADDRESS.
        
        Args:
            input_token (str): Address of the input token
            output_token (str): Address of the output token
            
        Returns:
            List[str]: List of token addresses representing the swap path
        """
        # If either token is the intermediate token, use direct path
        if input_token == INTERMEDIATE_LP_ADDRESS or output_token == INTERMEDIATE_LP_ADDRESS:
            return [input_token, output_token]
            
        # Otherwise route through intermediate token
        return [input_token, INTERMEDIATE_LP_ADDRESS, output_token]

# Create a singleton instance
swap_manager = SwapManager() 