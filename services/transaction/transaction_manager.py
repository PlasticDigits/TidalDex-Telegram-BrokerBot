"""
Generic transaction manager for arbitrary contract interactions.
Handles both view (read-only) and write (state-changing) contract calls.
"""
import logging
import json
import os
import re
from typing import Dict, List, Any, Optional, Union
from web3.exceptions import ContractLogicError
from wallet.send import send_contract_call
from utils.web3_connection import w3
from utils.load_abi import load_abi
# ABI loading handled internally
from utils.gas_estimation import estimate_contract_call_gas
from utils.status_updates import StatusCallback
from services.transaction.transaction_formatter import TransactionFormatter
from services.transaction.number_converter import NumberConverter

logger = logging.getLogger(__name__)

class TransactionManager:
    """Generic contract interaction manager for any blockchain application."""
    
    def __init__(self):
        """Initialize the TransactionManager."""
        self.web3 = w3
        self.formatter = TransactionFormatter()
        self.number_converter = NumberConverter()
        
    async def call_view_method(
        self,
        contract_address: str,
        abi: List[Dict],
        method_name: str,
        args: List[Any],
        status_callback: Optional[StatusCallback] = None
    ) -> Any:
        """Execute read-only contract calls.
        
        Args:
            contract_address: Address of the contract to call
            abi: Contract ABI
            method_name: Name of the method to call
            args: Arguments for the method
            status_callback: Optional callback for status updates
            
        Returns:
            Any: Result of the contract call
        """
        try:
            if status_callback:
                await status_callback(f"Calling {method_name}...")
            
            # Create contract instance
            checksum_address = self.web3.to_checksum_address(contract_address)
            contract = self.web3.eth.contract(address=checksum_address, abi=abi)
            
            # Execute the call
            result = contract.functions[method_name](*args).call()
            
            if status_callback:
                await status_callback(f"Call completed successfully")
            
            logger.info(f"View call {method_name} executed successfully")
            return result
            
        except ContractLogicError as e:
            error_msg = f"Contract logic error in {method_name}: {str(e)}"
            logger.error(error_msg)
            if status_callback:
                await status_callback(f"Error: {error_msg}")
            raise ValueError(error_msg)
        except Exception as e:
            error_msg = f"Failed to call {method_name}: {str(e)}"
            logger.error(error_msg)
            if status_callback:
                await status_callback(f"Error: {error_msg}")
            raise
    
    async def call_write_method(
        self,
        user_wallet: Dict[str, Any],
        contract_address: str,
        abi: List[Dict],
        method_name: str,
        args: List[Any],
        value_wei: int = 0,
        status_callback: Optional[StatusCallback] = None,
        method_config: Optional[Dict[str, Any]] = None,
        processed_params: Optional[Dict[str, Any]] = None,
        raw_params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Union[str, int]]:
        """Execute state-changing contract calls using existing send_contract_call.
        
        Args:
            user_wallet: User's wallet information with private_key and address
            contract_address: Address of the contract to call
            abi: Contract ABI
            method_name: Name of the method to call
            args: Arguments for the method
            value_wei: Amount of native token to send (in wei)
            status_callback: Optional callback for status updates
            method_config: Optional method configuration (needed for token approval)
            processed_params: Optional processed parameters (needed for token approval)
            raw_params: Optional raw parameters (needed for token approval)
            
        Returns:
            Dict containing transaction hash, status, and block number
        """
        try:
            if status_callback:
                await status_callback(f"Preparing to execute {method_name}...")
            
            # Handle token approval if required
            if method_config and method_config.get("requires_token_approval", False):
                if not processed_params or not raw_params:
                    logger.warning(f"requires_token_approval is True but missing processed_params or raw_params for {method_name}")
                else:
                    await self._ensure_token_approval(
                        user_wallet,
                        contract_address,
                        method_config,
                        processed_params,
                        raw_params,
                        status_callback
                    )
            
            # Use existing send_contract_call infrastructure
            result = await send_contract_call(
                user_wallet['private_key'],
                contract_address,
                abi,
                method_name,
                args,
                status_callback,
                value_wei
            )
            
            logger.info(f"Write call {method_name} executed with tx hash: {result.get('tx_hash')}")
            return result
            
        except Exception as e:
            error_msg = f"Failed to execute {method_name}: {str(e)}"
            logger.error(error_msg)
            if status_callback:
                await status_callback(f"Error: {error_msg}")
            raise
    
    async def estimate_gas(
        self,
        wallet_address: str,
        contract_address: str,
        abi: List[Dict],
        method_name: str,
        args: List[Any],
        value_wei: int = 0
    ) -> Dict[str, Union[int, float]]:
        """Estimate gas for contract calls.
        
        Args:
            wallet_address: Address of the wallet making the call
            contract_address: Address of the contract to call
            abi: Contract ABI
            method_name: Name of the method to call
            args: Arguments for the method
            value_wei: Amount of native token to send (in wei)
            
        Returns:
            Dict containing gas estimates
        """
        try:
            return await estimate_contract_call_gas(
                wallet_address,
                contract_address,
                abi,
                method_name,
                args,
                None,  # No status callback for estimation
                value_wei
            )
        except Exception as e:
            logger.error(f"Failed to estimate gas for {method_name}: {str(e)}")
            # Return default estimates if gas estimation fails
            return {
                "gas_estimate": 250000,  # Default gas limit
                "gas_price": 5000000000,  # 5 gwei default
                "gas_wei": 1250000000000000,  # 0.00125 BNB
                "gas_bnb": 0.00125
            }
    
    async def validate_method_args(
        self,
        abi: List[Dict],
        method_name: str,
        args: List[Any]
    ) -> bool:
        """Validate arguments against ABI specification.
        
        Args:
            abi: Contract ABI
            method_name: Name of the method to validate
            args: Arguments to validate
            
        Returns:
            bool: True if arguments are valid
            
        Raises:
            ValueError: If validation fails
        """
        try:
            # Find the method in the ABI
            method_abi = None
            for item in abi:
                if item.get("type") == "function" and item.get("name") == method_name:
                    method_abi = item
                    break
            
            if not method_abi:
                raise ValueError(f"Method {method_name} not found in ABI")
            
            # Check argument count
            inputs = method_abi.get("inputs", [])
            if len(args) != len(inputs):
                raise ValueError(
                    f"Method {method_name} expects {len(inputs)} arguments, got {len(args)}"
                )
            
            # TODO: Add more detailed type validation if needed
            return True
            
        except Exception as e:
            logger.error(f"Argument validation failed: {str(e)}")
            raise
    
    async def process_parameters(
        self,
        method_config: Dict[str, Any],
        raw_params: Dict[str, Any],
        app_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Convert human-readable params to blockchain format.
        
        Args:
            method_config: Configuration for the specific method
            raw_params: Raw parameters from user input
            app_config: Full app configuration
            
        Returns:
            Dict: Processed parameters ready for contract call
        """
        try:
            processed = {}
            parameter_processing = app_config.get("parameter_processing", {})
            
            for param_name, value in raw_params.items():
                param_rules = parameter_processing.get(param_name, {})
                param_type = param_rules.get("type", "string")
                
                if param_type == "token_amount" and param_rules.get("convert_from_human"):
                    # Get token address to determine decimals
                    decimals_from = param_rules.get("get_decimals_from")
                    if decimals_from:
                        token_address = self._resolve_parameter_reference(decimals_from, raw_params)
                        if token_address == "BNB":
                            decimals = 18
                        else:
                            from services.tokens import token_manager
                            token_info = await token_manager.get_token_info(token_address)
                            decimals = token_info['decimals'] if token_info else 18
                        
                        # Convert human amount to raw amount
                        processed[param_name] = self.number_converter.to_raw_amount(str(value), decimals)
                    else:
                        processed[param_name] = value
                elif param_type == "timestamp" and param_rules.get("default") == "current_time + 5_minutes":
                    # Generate deadline timestamp (current time + 5 minutes)
                    import time
                    processed[param_name] = int(time.time() + 300)
                else:
                    # No special processing needed
                    processed[param_name] = value
            
            return processed
            
        except Exception as e:
            logger.error(f"Parameter processing failed: {str(e)}")
            raise
    
    def _resolve_parameter_reference(self, param_ref: str, raw_params: Dict[str, Any]) -> str:
        """Resolve parameter reference like 'path[0]' to actual value.
        
        Args:
            param_ref: Parameter reference string
            raw_params: Raw parameters dictionary
            
        Returns:
            str: Resolved value
        """
        try:
            if param_ref == "BNB":
                return "BNB"
            elif param_ref.startswith("path["):
                path = raw_params.get("path", [])
                if not path:
                    return ""
                
                if param_ref == "path[0]":
                    return path[0] if len(path) > 0 else ""
                elif param_ref == "path[-1]":
                    return path[-1] if len(path) > 0 else ""
                else:
                    # Handle path[1], path[2], etc.
                    match = re.match(r"path\[(\d+)\]", param_ref)
                    if match:
                        index = int(match.group(1))
                        return path[index] if 0 <= index < len(path) else ""
            else:
                # Direct parameter reference
                return raw_params.get(param_ref, "")
            
            return ""
            
        except Exception as e:
            logger.error(f"Failed to resolve parameter reference '{param_ref}': {str(e)}")
            return ""
    
    async def _ensure_token_approval(
        self,
        user_wallet: Dict[str, Any],
        spender_address: str,
        method_config: Dict[str, Any],
        processed_params: Dict[str, Any],
        raw_params: Dict[str, Any],
        status_callback: Optional[StatusCallback] = None
    ) -> None:
        """Ensure token approval is granted before executing a transaction.
        
        Args:
            user_wallet: User's wallet information with private_key and address
            spender_address: Address of the contract that needs approval (spender)
            method_config: Method configuration containing token_amount_pairs
            processed_params: Processed parameters containing amounts
            raw_params: Raw parameters containing token addresses
            status_callback: Optional callback for status updates
            
        Raises:
            ValueError: If token approval fails
        """
        try:
            # Find the input token from token_amount_pairs
            token_amount_pairs = method_config.get("token_amount_pairs", [])
            input_pair = None
            
            for pair in token_amount_pairs:
                if pair.get("direction") in ["input", "payment", "stake"]:
                    input_pair = pair
                    break
            
            if not input_pair:
                logger.warning("No input token found in token_amount_pairs for approval")
                return
            
            # Resolve token address
            token_param = input_pair.get("token_param", "")
            token_address = self._resolve_parameter_reference(token_param, raw_params)
            
            # Skip approval for native token (BNB)
            if not token_address or token_address == "BNB":
                logger.info("Skipping approval for native token")
                return
            
            # Resolve amount
            amount_param = input_pair.get("amount_param", "")
            amount = processed_params.get(amount_param, 0)
            
            if amount <= 0:
                logger.warning(f"Invalid amount {amount} for token approval")
                return
            
            wallet_address = self.web3.to_checksum_address(user_wallet['address'])
            checksum_token_address = self.web3.to_checksum_address(token_address)
            checksum_spender_address = self.web3.to_checksum_address(spender_address)
            
            if status_callback:
                await status_callback("Checking token allowance...")
            
            # Load ERC20 ABI
            token_abi = load_abi("ERC20")
            
            # Check current allowance
            token_contract = self.web3.eth.contract(
                address=checksum_token_address,
                abi=token_abi
            )
            
            allowance = token_contract.functions.allowance(
                wallet_address,
                checksum_spender_address
            ).call()
            
            # Approve if allowance is insufficient
            if allowance < amount:
                if status_callback:
                    await status_callback("Approving token spending...")
                
                # Use send_contract_call for approval
                approve_result = await send_contract_call(
                    user_wallet['private_key'],
                    checksum_token_address,
                    token_abi,
                    'approve',
                    [checksum_spender_address, amount],
                    status_callback
                )
                
                if approve_result.get('status') != 1:
                    error_msg = "Token approval failed"
                    logger.error(error_msg)
                    if status_callback:
                        await status_callback(f"Error: {error_msg}")
                    raise ValueError(error_msg)
                
                if status_callback:
                    await status_callback("Token spending approved")
                
                logger.info(f"Approved {amount} tokens for {checksum_spender_address}")
            else:
                if status_callback:
                    await status_callback("Token allowance sufficient")
                logger.info(f"Token allowance sufficient: {allowance} >= {amount}")
            
        except Exception as e:
            error_msg = f"Failed to ensure token approval: {str(e)}"
            logger.error(error_msg)
            if status_callback:
                await status_callback(f"Error: {error_msg}")
            raise ValueError(error_msg)
    
    async def prepare_transaction_preview(
        self,
        method_config: Dict[str, Any],
        raw_params: Dict[str, Any],
        app_config: Dict[str, Any],
        wallet_address: str
    ) -> Dict[str, Any]:
        """Prepare human-readable transaction preview.
        
        Args:
            method_config: Configuration for the specific method
            raw_params: Raw parameters for the transaction
            app_config: Full app configuration
            wallet_address: User's wallet address for gas estimation
            
        Returns:
            Dict containing transaction preview information
        """
        try:
            # Validate token/amount pairs
            await self.formatter.validate_token_amount_pairs(method_config, raw_params)
            
            # Generate human summary
            summary = await self.formatter.format_transaction_summary(
                method_config,
                raw_params,
                app_config
            )
            
            # Get contract info
            contract_name = method_config.get("contract", list(app_config["contracts"].keys())[0])
            contract_config = app_config["contracts"][contract_name]
            contract_address = os.getenv(contract_config["address_env_var"])
            
            if not contract_address:
                raise ValueError(f"Contract address not found in environment: {contract_config['address_env_var']}")
            
            # Load ABI
            abi_path = f"app/apps/{app_config['name']}/{contract_config['abi_file']}"
            abi = load_abi_from_file(abi_path)
            
            # Estimate gas
            processed_params = await self.process_parameters(method_config, raw_params, app_config)
            args = [processed_params[param] for param in method_config["inputs"]]
            value_wei = processed_params.get("value_wei", 0)
            
            gas_estimate = await self.estimate_gas(
                wallet_address,
                contract_address,
                abi,
                method_config["name"],
                args,
                value_wei
            )
            
            gas_formatted = self.number_converter.format_gas_estimate(
                gas_estimate.get("gas_wei", 0),
                1  # We already have total cost
            )
            
            return {
                "summary": summary,
                "method_name": method_config["name"],
                "contract_name": contract_name,
                "contract_address": contract_address,
                "gas_estimate": gas_formatted,
                "processed_params": processed_params,
                "raw_params": raw_params
            }
            
        except Exception as e:
            logger.error(f"Failed to prepare transaction preview: {str(e)}")
            raise

def load_abi_from_file(file_path: str) -> List[Dict]:
    """Load ABI from JSON file.
    
    Args:
        file_path: Path to the ABI JSON file
        
    Returns:
        List[Dict]: Contract ABI
    """
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load ABI from {file_path}: {str(e)}")
        raise ValueError(f"Could not load ABI file: {file_path}")