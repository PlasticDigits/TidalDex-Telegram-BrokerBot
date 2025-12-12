"""
Generic transaction manager for arbitrary contract interactions.
Handles both view (read-only) and write (state-changing) contract calls.
"""
import logging
import json
import os
import re
import time
from typing import Dict, List, Any, Optional, Union, Iterable, Tuple
import difflib
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

    @classmethod
    def _canonicalize_token_ref(cls, token_ref: str) -> str:
        """Canonicalize a user-provided token reference (symbol or name).

        - Uppercases
        - Strips non-alphanumeric characters (spaces, hyphens, etc.)

        This intentionally does NOT hardcode aliases; instead we resolve robustly
        by matching against known token symbols *and* token names.
        """
        return re.sub(r"[^A-Za-z0-9]", "", token_ref).upper()

    @classmethod
    def _token_details_match_ref(cls, token_ref_clean: str, token_details: Dict[str, Any]) -> bool:
        """Return True if token_details matches a cleaned token reference."""
        sym = cls._canonicalize_token_ref(str(token_details.get("symbol", "")))
        name = cls._canonicalize_token_ref(str(token_details.get("name", "")))
        return token_ref_clean in (sym, name)

    @classmethod
    def _token_details_best_match_score(cls, token_ref_clean: str, token_details: Dict[str, Any]) -> float:
        """Compute similarity score (0..1) for a token ref against token details."""
        sym = cls._canonicalize_token_ref(str(token_details.get("symbol", "")))
        name = cls._canonicalize_token_ref(str(token_details.get("name", "")))
        if not token_ref_clean:
            return 0.0
        # Exact matches should have been handled earlier, but keep them highest anyway.
        if token_ref_clean in (sym, name):
            return 1.0
        return max(
            difflib.SequenceMatcher(a=token_ref_clean, b=sym).ratio() if sym else 0.0,
            difflib.SequenceMatcher(a=token_ref_clean, b=name).ratio() if name else 0.0,
        )

    @staticmethod
    def _format_token_suggestion(symbol: str, name: str, address: str) -> str:
        """Human-friendly suggestion string."""
        sym = symbol.strip() or "?"
        nm = name.strip() or "?"
        addr = address
        return f"{sym} ({nm}) {addr}"

    async def _suggest_tokens(
        self,
        *,
        token_ref: str,
        user_id: Optional[str],
        wallet_address: Optional[str],
        limit: int = 5,
    ) -> List[str]:
        """Suggest likely tokens for a misspelled/unknown token reference.

        Suggestions are based on fuzzy similarity against known symbols and names.
        We search:
        - user's tracked tokens (if available)
        - TokenManager default tokens list (cached)
        """
        try:
            from services.tokens import token_manager

            token_ref_clean = self._canonicalize_token_ref(token_ref)
            if not token_ref_clean:
                return []

            # Ensure default token cache is populated.
            if not token_manager.default_tokens:
                await token_manager._parse_default_token_list()

            # Build candidate pool (address -> details), prefer richer details.
            candidates_by_addr: Dict[str, Dict[str, Any]] = {}

            if user_id:
                try:
                    tracked = await token_manager.get_tracked_tokens(user_id)
                    for t in tracked:
                        addr = str(t.get("token_address") or "")
                        if not addr:
                            continue
                        candidates_by_addr[addr] = {
                            "symbol": str(t.get("symbol") or ""),
                            "name": str(t.get("name") or ""),
                            "address": addr,
                        }
                except Exception:
                    # Suggestions are best-effort; ignore failures.
                    pass

            for addr, details in token_manager.default_tokens.items():
                addr_str = str(addr)
                # Keep tracked-token details if present, otherwise use default list details.
                candidates_by_addr.setdefault(
                    addr_str,
                    {
                        "symbol": str(details.get("symbol") or ""),
                        "name": str(details.get("name") or ""),
                        "address": addr_str,
                    },
                )

            scored: List[Tuple[float, str]] = []
            for addr, details in candidates_by_addr.items():
                score = self._token_details_best_match_score(token_ref_clean, details)
                if score <= 0:
                    continue
                scored.append((score, addr))

            if not scored:
                return []

            # Sort by similarity desc; compute balances only for the top few.
            scored.sort(key=lambda x: x[0], reverse=True)
            top_addrs = [addr for _score, addr in scored[: max(limit * 2, 10)]]

            balances_by_addr: Dict[str, int] = {}
            if wallet_address:
                for addr in top_addrs:
                    try:
                        bal = await token_manager.get_token_balance(wallet_address, addr)
                        balances_by_addr[addr] = int(bal)
                    except Exception:
                        balances_by_addr[addr] = 0

            # Final ordering: similarity desc, then balance desc (if available).
            top_ranked = sorted(
                scored[: max(limit * 2, 10)],
                key=lambda x: (x[0], balances_by_addr.get(x[1], 0)),
                reverse=True,
            )[:limit]

            suggestions: List[str] = []
            for _score, addr in top_ranked:
                det = candidates_by_addr[addr]
                suggestions.append(
                    self._format_token_suggestion(
                        symbol=str(det.get("symbol") or ""),
                        name=str(det.get("name") or ""),
                        address=str(det.get("address") or addr),
                    )
                )
            return suggestions
        except Exception:
            return []
        
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
            # Extract readable error message from ContractLogicError
            # ContractLogicError stores error as tuple: (message, data)
            # The message may contain hex-encoded error data that we want to remove
            readable_error = None
            
            # Try to get message from e.args[0] (first element is the message string)
            if hasattr(e, 'args') and e.args and len(e.args) > 0:
                error_message = str(e.args[0])
                
                # Extract readable part - remove hex-encoded error data
                if "execution reverted:" in error_message:
                    # Find the start of "execution reverted:"
                    revert_start = error_message.find("execution reverted:")
                    # Extract everything after "execution reverted:"
                    after_revert = error_message[revert_start + len("execution reverted:"):].strip()
                    
                    # Remove hex-encoded error data (long hex strings starting with 0x)
                    # The hex data appears after a colon or space
                    # Look for patterns like ": 0x..." or " 0x..." where hex is >50 chars
                    parts = after_revert.split()
                    readable_parts = []
                    for part in parts:
                        # Check if this part is a long hex string (error data encoding)
                        if part.startswith("0x") and len(part) > 50:
                            break  # Stop at first long hex string
                        # Also check if part contains ":0x" (colon followed by hex)
                        if ":0x" in part:
                            # Split at colon and take only the part before hex
                            colon_idx = part.find(":0x")
                            if colon_idx > 0:
                                readable_parts.append(part[:colon_idx])
                            break
                        readable_parts.append(part)
                    
                    readable_error = f"execution reverted: {' '.join(readable_parts).strip()}"
                else:
                    # No "execution reverted:" prefix, just truncate if too long
                    readable_error = error_message[:500] if len(error_message) > 500 else error_message
            
            # Fallback: try e.message attribute
            if not readable_error and hasattr(e, 'message') and e.message:
                msg_str = str(e.message)
                readable_error = msg_str[:500] if len(msg_str) > 500 else msg_str
            
            # Final fallback: use string representation but truncate
            if not readable_error:
                error_str = str(e)
                readable_error = error_str[:500] if len(error_str) > 500 else error_str
            
            error_msg = f"Contract logic error in {method_name}: {readable_error}"
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
        app_config: Dict[str, Any],
        user_id: Optional[str] = None,
        wallet_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Convert human-readable params to blockchain format.
        
        Args:
            method_config: Configuration for the specific method
            raw_params: Raw parameters from user input
            app_config: Full app configuration
            user_id: Optional user ID for context-aware token resolution
            wallet_address: Optional wallet address used for disambiguating tokens by balance
            
        Returns:
            Dict: Processed parameters ready for contract call
        """
        try:
            processed = {}
            parameter_processing = app_config.get("parameter_processing", {})
            
            # First, resolve token symbols in path if present
            if "path" in raw_params:
                processed["path"] = await self._resolve_token_symbols_in_path(
                    raw_params["path"],
                    user_id=user_id,
                    wallet_address=wallet_address,
                )
            
            # Process parameters from raw_params
            for param_name, value in raw_params.items():
                # Skip path as it's already processed above
                if param_name == "path":
                    continue
                    
                param_rules = parameter_processing.get(param_name, {})
                param_type = param_rules.get("type", "string")
                
                if param_type == "token_amount" and param_rules.get("convert_from_human"):
                    # Get token address to determine decimals
                    decimals_from = param_rules.get("get_decimals_from")
                    if decimals_from:
                        # Use processed params (with resolved path) for token address lookup
                        token_address = self._resolve_parameter_reference(decimals_from, processed)
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
                    # Only regenerate if value is the default string, otherwise preserve explicit value
                    if value == "current_time + 5_minutes":
                        # Generate deadline timestamp (current time + 5 minutes)
                        processed[param_name] = int(time.time() + 300)
                    else:
                        # Preserve explicit timestamp value
                        processed[param_name] = value
                else:
                    # No special processing needed
                    processed[param_name] = value
            
            # Apply default values for required parameters not in raw_params
            required_inputs = method_config.get("inputs", [])
            for param_name in required_inputs:
                if param_name not in processed:
                    param_rules = parameter_processing.get(param_name, {})
                    default_value = param_rules.get("default")
                    
                    if default_value:
                        if default_value == "user_wallet_address":
                            # This will be resolved later in llm_app_session
                            processed[param_name] = "user_wallet_address"
                        elif param_rules.get("type") == "timestamp" and default_value == "current_time + 5_minutes":
                            # Generate deadline timestamp (current time + 5 minutes)
                            processed[param_name] = int(time.time() + 300)
                        else:
                            # Use the default value as-is
                            processed[param_name] = default_value
            
            return processed
            
        except Exception as e:
            logger.error(f"Parameter processing failed: {str(e)}")
            raise
    
    def _resolve_parameter_reference(self, param_ref: str, params: Dict[str, Any]) -> str:
        """Resolve parameter reference like 'path[0]' to actual value.
        
        Args:
            param_ref: Parameter reference string
            params: Parameters dictionary (processed or raw)
            
        Returns:
            str: Resolved value
        """
        try:
            if param_ref == "BNB":
                return "BNB"
            elif param_ref.startswith("path["):
                path = params.get("path", [])
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
                return params.get(param_ref, "")
            
            return ""
            
        except Exception as e:
            logger.error(f"Failed to resolve parameter reference '{param_ref}': {str(e)}")
            return ""
    
    async def _resolve_token_symbols_in_path(
        self,
        path: List[str],
        user_id: Optional[str] = None,
        wallet_address: Optional[str] = None,
    ) -> List[str]:
        """Resolve token symbols to addresses in a swap path.
        
        When the LLM returns a path with token symbols like ["CL8Y", "CZUSD"],
        this method resolves those symbols to their actual contract addresses.
        
        Note:
            This method intentionally does NOT enforce swap routing rules.
            Routing is app-specific logic (e.g., TidalDex swap can try multiple
            intermediate routes) and is handled at the app/session layer.
        
        Args:
            path: List of token symbols or addresses
            user_id: Optional user ID for context-aware token resolution
            wallet_address: Optional wallet address used for disambiguating tokens by balance
            
        Returns:
            List[str]: Path with all symbols resolved to checksum addresses
        """
        resolved_path: List[str] = []
        
        for token_ref in path:
            # Check if it's already a valid address
            if self.web3.is_address(token_ref):
                resolved_path.append(self.web3.to_checksum_address(token_ref))
            elif token_ref in ["BNB", "ETH"]:
                # Native token - keep as is, will be handled by swap manager
                resolved_path.append(token_ref)
            else:
                # Try to resolve as symbol
                token_address = await self._resolve_token_symbol(
                    token_ref,
                    user_id=user_id,
                    wallet_address=wallet_address,
                )
                if token_address:
                    resolved_path.append(token_address)
                else:
                    suggestions = await self._suggest_tokens(
                        token_ref=token_ref,
                        user_id=user_id,
                        wallet_address=wallet_address,
                        limit=5,
                    )
                    did_you_mean = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
                    # If can't resolve, raise an error with a helpful message
                    raise ValueError(
                        f"Could not resolve token reference '{token_ref}' to an address.{did_you_mean} "
                        f"Please ensure the token is in the default token list or use the token address instead."
                    )
        
        return resolved_path
    
    async def _resolve_token_symbol(
        self,
        symbol: str,
        user_id: Optional[str] = None,
        wallet_address: Optional[str] = None,
    ) -> Optional[str]:
        """Resolve a token reference (symbol or name) to its contract address.
        
        The default token list is authoritative. Tracked tokens are only used
        when the token is not in the default list.

        Resolution priority:
        1. Default token list (authoritative - prevents using stale/migrated tokens)
        2. TokenManager default_tokens by symbol OR name
        3. Tracked tokens (fallback only if not in any default list)
        
        Args:
            symbol: Token reference to resolve (symbol or name; e.g., "CL8Y", "CZUSD", "CeramicLiberty.com")
            user_id: Optional user ID for context-aware resolution (checks tracked tokens as fallback)
            wallet_address: Optional wallet address (currently unused, kept for API compatibility)
            
        Returns:
            Optional[str]: Token checksum address if found, None otherwise
        """
        try:
            from utils.token import find_token
            from services.tokens import token_manager
            
            token_ref_clean = self._canonicalize_token_ref(symbol)
            
            # 1) Default token list is authoritative - always check first
            # This prevents using stale/migrated token addresses from tracked tokens
            token_info = await find_token(symbol=token_ref_clean)
            if token_info and token_info.get('address'):
                address = self.web3.to_checksum_address(token_info['address'])
                
                # Auto-purge any stale tracked tokens with same symbol but different address
                if user_id:
                    await self._purge_stale_tracked_tokens(
                        user_id, token_ref_clean, address, token_manager
                    )
                
                logger.debug(f"Resolved '{symbol}' to default token list: {address}")
                return address
            
            # 2) Try TokenManager's parsed default list
            if not token_manager.default_tokens:
                await token_manager._parse_default_token_list()
            
            # Search in default_tokens by symbol OR name (case/punctuation-insensitive)
            matching_default_addrs: List[str] = []
            for address, details in token_manager.default_tokens.items():
                if self._token_details_match_ref(token_ref_clean, details):
                    matching_default_addrs.append(str(address))

            if matching_default_addrs:
                if len(matching_default_addrs) > 1:
                    logger.warning(
                        "Token reference '%s' matched multiple default tokens (%d); selecting first.",
                        symbol,
                        len(matching_default_addrs),
                    )
                address = self.web3.to_checksum_address(matching_default_addrs[0])
                
                # Auto-purge any stale tracked tokens with same symbol but different address
                if user_id:
                    await self._purge_stale_tracked_tokens(
                        user_id, token_ref_clean, address, token_manager
                    )
                
                logger.debug(f"Resolved '{symbol}' to default_tokens: {address}")
                return address

            # 3) Fallback: use user's tracked tokens (only if not in any default list)
            if user_id:
                try:
                    tracked_tokens = await token_manager.get_tracked_tokens(user_id)
                    matching_tracked = [
                        token for token in tracked_tokens
                        if self._token_details_match_ref(token_ref_clean, token)
                    ]

                    if matching_tracked:
                        if len(matching_tracked) > 1 and wallet_address:
                            balances_with_tokens = []
                            for token in matching_tracked:
                                try:
                                    balance = await token_manager.get_token_balance(
                                        wallet_address,
                                        token['token_address'],
                                    )
                                    balances_with_tokens.append((balance, token))
                                except Exception:
                                    balances_with_tokens.append((0, token))

                            balances_with_tokens.sort(key=lambda x: x[0], reverse=True)
                            best_token = balances_with_tokens[0][1]
                            logger.info(
                                f"Default list missing '{symbol}'; multiple tracked tokens found, "
                                f"selecting highest balance: {best_token['token_address']}"
                            )
                            return self.web3.to_checksum_address(best_token['token_address'])

                        selected_token = matching_tracked[0]
                        logger.debug(
                            f"Default list missing '{symbol}'; resolved to tracked token: {selected_token['token_address']}"
                        )
                        return self.web3.to_checksum_address(selected_token['token_address'])
                except Exception as e:
                    logger.warning(f"Failed to check tracked tokens for symbol '{symbol}': {str(e)}")
            
            logger.warning(f"Token reference '{symbol}' not found in default token list or tracked tokens")
            return None
            
        except Exception as e:
            logger.error(f"Failed to resolve token symbol '{symbol}': {str(e)}")
            return None

    async def _purge_stale_tracked_tokens(
        self,
        user_id: str,
        token_ref_clean: str,
        authoritative_address: str,
        token_manager: Any,
    ) -> None:
        """Auto-purge stale tracked tokens when default list has a different address.
        
        When a token migrates to a new contract (e.g., CL8Y), users may still have
        the old address tracked. This method automatically removes those stale entries
        to prevent using outdated contract addresses.
        
        Args:
            user_id: User ID to check tracked tokens for
            token_ref_clean: Canonicalized token reference (symbol/name)
            authoritative_address: The correct address from default token list
            token_manager: TokenManager instance
        """
        try:
            tracked_tokens = await token_manager.get_tracked_tokens(user_id)
            conflicting_tokens = [
                token for token in tracked_tokens
                if self._token_details_match_ref(token_ref_clean, token)
                and self.web3.to_checksum_address(token['token_address']) != authoritative_address
            ]
            
            for token in conflicting_tokens:
                stale_address = token['token_address']
                token_symbol = token.get('symbol', token_ref_clean)
                
                logger.info(
                    "Auto-purging stale tracked token '%s' at %s for user %s "
                    "(migrated to %s)",
                    token_symbol,
                    stale_address,
                    user_id[:16] + "..." if len(user_id) > 16 else user_id,
                    authoritative_address,
                )
                
                try:
                    # Untrack the stale token
                    await token_manager.untrack(user_id, stale_address)
                    logger.info(
                        "Successfully purged stale token %s (%s) for user %s",
                        token_symbol,
                        stale_address,
                        user_id[:16] + "..." if len(user_id) > 16 else user_id,
                    )
                except Exception as untrack_error:
                    logger.warning(
                        "Failed to purge stale token %s (%s) for user %s: %s",
                        token_symbol,
                        stale_address,
                        user_id[:16] + "..." if len(user_id) > 16 else user_id,
                        str(untrack_error),
                    )
        except Exception as e:
            # Don't fail resolution if purge check fails
            logger.debug(f"Could not check for stale tracked tokens: {e}")
    
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
        wallet_address: str,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Prepare human-readable transaction preview.
        
        Args:
            method_config: Configuration for the specific method
            raw_params: Raw parameters for the transaction
            app_config: Full app configuration
            wallet_address: User's wallet address for gas estimation
            user_id: Optional user ID for context-aware token resolution
            
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
            abi_path = f"app/llm_apps/{app_config['name']}/{contract_config['abi_file']}"
            abi = load_abi_from_file(abi_path)
            
            # Estimate gas
            processed_params = await self.process_parameters(
                method_config,
                raw_params,
                app_config,
                user_id=user_id,
                wallet_address=wallet_address,
            )
            
            # Resolve "user_wallet_address" to actual wallet address if needed
            if "to" in processed_params and processed_params["to"] == "user_wallet_address":
                processed_params["to"] = wallet_address
            
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