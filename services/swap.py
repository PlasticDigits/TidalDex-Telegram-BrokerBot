from typing import Dict, Optional, Any, List, Callable, Awaitable
from web3.types import ChecksumAddress, Wei
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
from utils.config import get_env_var, BSC_SCANNER_URL, INTERMEDIATE_LP_ADDRESS, CL8Y_BUY_AND_BURN, CL8Y_BB_FEE_BPS, WETH
from utils.status_updates import StatusCallback
from utils.web3_connection import w3  # Import the shared Web3 connection
from wallet.send import send_contract_call, send_bnb, send_token  # Import send_contract_call
from services import token_manager  # Import the singleton token_manager instance
from db.utils import hash_user_id

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

    async def get_swap_quote(
        self,
        from_token_address: str,
        to_token_address: str,
        amount_in: int,
        slippage_bps: int,
        status_callback: StatusCallback
    ) -> Optional[Dict[str, Any]]:
        """Get a quote for a token swap using TidalDexRouter.
        
        Args:
            from_token_address: Address of the token to swap from
            to_token_address: Address of the token to swap to
            amount_in: Amount of from_token to swap (in wei)
            slippage_bps: Slippage tolerance in basis points (1% = 100)
            status_callback: StatusCallback
        Returns:
            Dictionary containing swap quote details or None if quote failed
        """
        try:
            if status_callback:
                await status_callback("Calculating swap path...")
            
            # Get the path for the swap using the new method
            path: List[str] = self.get_route_path(from_token_address, to_token_address)
            
            # Convert path addresses to checksum addresses
            path_checksum = [self.w3.to_checksum_address(addr) for addr in path]
            
            if status_callback:
                await status_callback("Getting amounts out from router...")
            
            # Ensure amount_in is an integer
            amount_in_int = int(amount_in)
            
            # Get token decimals for proper conversion
            if from_token_address == "BNB":
                from_token_decimals = 18
            else:
                from_token_contract = self.w3.eth.contract(
                    address=self.w3.to_checksum_address(from_token_address),
                    abi=load_abi("ERC20")
                )
                from_token_decimals = from_token_contract.functions.decimals().call()
                
            if to_token_address == "BNB":
                to_token_decimals = 18
            else:
                to_token_contract = self.w3.eth.contract(
                    address=self.w3.to_checksum_address(to_token_address),
                    abi=load_abi("ERC20")
                )
                to_token_decimals = to_token_contract.functions.decimals().call()
            
            # Get amounts out
            amounts_out = self.router_contract.functions.getAmountsOut(
                amount_in_int,
                path_checksum
            ).call()

            logger.info(f"Path: {path}")
            logger.info(f"Amount in: {amount_in_int}")
            logger.info(f"Amount out: {amounts_out[-1]}")
            
            if not amounts_out or len(amounts_out) < 2:
                logger.error("Invalid amounts out from router")
                if status_callback:
                    await status_callback("Error: Invalid amounts out from router")
                return None
            
            # amount out is the final amounts out
            amount_out = amounts_out[-1]

            #adjust amount out for buy and burn
            if CL8Y_BUY_AND_BURN and CL8Y_BB_FEE_BPS:
                amount_out = amount_out * (1 - CL8Y_BB_FEE_BPS / 10000)

            #calculate price accounting for both token decimals
            price = (amount_in_int / (10 ** from_token_decimals)) / (amount_out / (10 ** to_token_decimals))
            
            if status_callback:
                await status_callback("Calculating price impact...")
            
            if status_callback:
                await status_callback("Quote calculation complete")
            
            return {
                'amount_out': amount_out,
                'price':price,
                'path': path,
                'slippage_bps': slippage_bps
            }
            
        except Exception as e:
            logger.error(f"Error getting swap quote: {e}")
            if status_callback:
                await status_callback(f"Error getting swap quote: {str(e)}")
            return None

    async def execute_swap(
        self,
        user_id_str: str,
        wallet: Dict[str, Any],
        from_token_address: str,
        to_token_address: str,
        amount_in: int,
        slippage_bps: int,
        quote: Dict[str, Any],
        status_callback: StatusCallback
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

            
            
            # Ensure amount_in is an integer
            amount_in = int(amount_in)
            
            if status_callback:
                await status_callback("Loading token contract...")
            
            # Create token contract instance
            token_abi = load_abi("ERC20")
            
            if status_callback:
                await status_callback("Checking token allowance...")
            
            # initialize allowance to 0
            allowance = 0

            # Check allowance if not BNB
            if from_token_address != "BNB":
                token_contract = self.w3.eth.contract(
                    address=from_token_address,
                    abi=token_abi
                )
                allowance = token_contract.functions.allowance(
                    wallet_address,
                    self.router_address
                ).call()
            
            # If allowance is insufficient, approve the router (if not BNB)
            if allowance < amount_in and from_token_address != "BNB":
                if status_callback:
                    await status_callback("Approving token spending...")
                
                # Use send_contract_call for approval
                approve_result = await send_contract_call(
                    private_key,
                    from_token_address,
                    token_abi,
                    'approve',
                    [self.router_address, amount_in],
                    status_callback
                )
                
                if approve_result['status'] != 1:
                    if status_callback:
                        await status_callback("Token approval failed")
                    return None
                
                if status_callback:
                    await status_callback("Token spending approved")
            
            # Calculate minimum amount out with slippage
            amount_out_min = int(quote['amount_out'] * (10000 - slippage_bps) / 10000)
            
            if status_callback:
                await status_callback("Preparing swap transaction...")
            
            # Get the path for the swap
            path = self.get_route_path(from_token_address, to_token_address)
            
            # Current timestamp + 5 minutes for deadline
            deadline = int(self.w3.eth.get_block('latest')['timestamp'] + 300)
            
            # use the correct function for the swap
            # For bnb output, use swapExactTokensForETHSupportingFeeOnTransferTokens
            # For bnb input, use swapExactETHForTokensSupportingFeeOnTransferTokens
            # for neither bnb output or input, use swapExactTokensForTokensSupportingFeeOnTransferTokens

            value_wei = 0
            if to_token_address == "BNB":
                swap_function_name = 'swapExactTokensForETHSupportingFeeOnTransferTokens'
                swap_args = [amount_in, amount_out_min, path, wallet_address, deadline]
            elif from_token_address == "BNB":
                swap_function_name = 'swapExactETHForTokensSupportingFeeOnTransferTokens'
                swap_args = [amount_out_min, path, wallet_address, deadline]
                value_wei = amount_in
            else:
                swap_function_name = 'swapExactTokensForTokensSupportingFeeOnTransferTokens'
                swap_args = [amount_in, amount_out_min, path, wallet_address, deadline]

            # Execute swap using send_contract_call
            swap_result = await send_contract_call(
                private_key,
                self.router_address,
                self.router_abi,
                swap_function_name,
                swap_args,
                status_callback,
                value_wei
            )
            
            if swap_result['status'] == 1:
                if status_callback:
                    tx_hash_hex = swap_result['tx_hash']
                    status_callback_prepend = f"Hash: 0x{tx_hash_hex}\n{BSC_SCANNER_URL}/tx/0x{tx_hash_hex}\n\n"
                    await status_callback(status_callback_prepend + "Swap completed successfully!")
                    # silently send received tokens to buy and burn
                    if CL8Y_BUY_AND_BURN and CL8Y_BB_FEE_BPS:
                        try:
                            # Calculate fee percentage
                            fee_percentage = CL8Y_BB_FEE_BPS / 10000
                            
                            # For BNB output (already in wei)
                            if to_token_address == "BNB":
                                fee_amount_wei = int(amount_out_min * fee_percentage)
                                if fee_amount_wei > 0:
                                    await send_bnb(
                                        private_key,
                                        CL8Y_BUY_AND_BURN,
                                        fee_amount_wei,
                                        status_callback
                                    )
                            else:
                                # For token output, we need to get decimals
                                token_contract = self.w3.eth.contract(
                                    address=self.w3.to_checksum_address(to_token_address),
                                    abi=token_abi
                                )
                                to_token_decimals = token_contract.functions.decimals().call()
                                
                                # Convert to human-readable, calculate fee, then convert back to token units
                                amount_human = Decimal(amount_out_min) / Decimal(10 ** to_token_decimals)
                                fee_amount_human = amount_human * Decimal(fee_percentage)
                                
                                if fee_amount_human > 0:
                                    await send_token(
                                        private_key,
                                        to_token_address,
                                        CL8Y_BUY_AND_BURN,
                                        fee_amount_human,
                                        None # send silently
                                    )
                        except Exception as e:
                            # Log the error but don't fail the swap if buy and burn fails
                            logger.error(f"Error sending buy and burn fee: {e}")
                            if status_callback:
                                await status_callback(f"Warning: Buy and burn fee transfer failed: {str(e)}")
                    # If the received token is not tracked, track it.
                    if to_token_address != "BNB":
                        try:
                            if not token_manager.is_token_tracked(user_id_str, to_token_address):
                                track_success = await token_manager.track(user_id_str, to_token_address)
                                if track_success:
                                    logger.info(f"Started tracking newly received token {to_token_address} for user {wallet['user_id']}")
                                else:
                                    logger.warning(f"Could not track token {to_token_address} after swap for user {wallet['user_id']}")
                        except Exception as e:
                            logger.error(f"Failed to track token {to_token_address} after swap: {e}")
                            # Don't fail the swap if tracking fails
                            pass
                return swap_result['tx_hash']
            else:
                if status_callback:
                    await status_callback("Swap transaction failed")
                return None
                
        except Exception as e:
            logger.error(f"Error executing swap: {e}")
            if status_callback:
                await status_callback(f"Error: {str(e)}")
            return None

    def get_route_path(self, input_token: str, output_token: str) -> List[str]:
        """
        Determine the optimal route path between input and output tokens.
        
        Handles native token symbols (BNB/ETH) by replacing them with wrapped version.
        If either token is the INTERMEDIATE_LP_ADDRESS, returns a direct path.
        Otherwise, routes through INTERMEDIATE_LP_ADDRESS.
        
        Args:
            input_token (str): Address of the input token or "BNB"/"ETH" for native token
            output_token (str): Address of the output token or "BNB"/"ETH" for native token
            
        Returns:
            List[str]: List of token addresses representing the swap path
        """
        # Replace BNB/ETH with wrapped version (WETH)
        if input_token in ["BNB", "ETH"]:
            input_token = WETH
            
        if output_token in ["BNB", "ETH"]:
            output_token = WETH
        
        # If either token is the intermediate token, use direct path
        if input_token == INTERMEDIATE_LP_ADDRESS or output_token == INTERMEDIATE_LP_ADDRESS:
            return [input_token, output_token]
            
        # Otherwise route through intermediate token
        return [input_token, INTERMEDIATE_LP_ADDRESS, output_token]

# Create a singleton instance
swap_manager = SwapManager()