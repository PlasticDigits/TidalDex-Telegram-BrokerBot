"""
LLM app session management for tracking conversation state and handling transactions.
"""
import logging
import json
import os
from typing import Dict, List, Any, Optional, AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from services.wallet import wallet_manager
from services.pin import pin_manager
from services.tokens import token_manager
from services.transaction import transaction_manager, transaction_formatter
from db.utils import hash_user_id

logger = logging.getLogger(__name__)

class SessionState(Enum):
    """Possible states of an LLM app session."""
    ACTIVE = "active"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    AWAITING_PIN = "awaiting_pin"
    COMPLETED = "completed"
    ERROR = "error"

@dataclass
class PendingTransaction:
    """Information about a transaction awaiting confirmation."""
    method_config: Dict[str, Any]
    processed_params: Dict[str, Any]
    app_config: Dict[str, Any]
    preview: Dict[str, Any]
    raw_params: Dict[str, Any] = field(default_factory=dict)

class LLMAppSession:
    """Manages the state and execution of an LLM app conversation session."""
    
    def __init__(self, user_id: str, llm_app_name: str, llm_app_config: Dict[str, Any]):
        """Initialize an LLM app session.
        
        Args:
            user_id: Telegram user ID as string
            llm_app_name: Name of the LLM app being used
            llm_app_config: Full LLM app configuration
        """
        self.user_id = user_id
        self.llm_app_name = llm_app_name
        self.llm_app_config = llm_app_config
        self.state = SessionState.ACTIVE
        self.conversation_history: List[Dict[str, str]] = []
        self.context: Dict[str, Any] = {}
        self.pending_transaction: Optional[PendingTransaction] = None
        
        # Initialize wallet and token context
        self.wallet_info: Optional[Dict[str, Any]] = None
        self.tracked_tokens: List[Dict[str, Any]] = []
        self.token_balances: Dict[str, Any] = {}
        
    async def initialize_context(self) -> bool:
        """Initialize session context with user's wallet and token information.
        
        Returns:
            bool: True if context was successfully initialized
        """
        try:
            # Get active wallet
            wallet_name = wallet_manager.get_active_wallet_name(self.user_id)
            if not wallet_name:
                logger.warning(f"No active wallet for user {hash_user_id(self.user_id)}")
                return False
            
            # Get user's PIN if needed
            user_id_int = int(self.user_id)
            pin = pin_manager.get_pin(user_id_int) if pin_manager.needs_pin(user_id_int) else None
            
            # Get wallet info
            self.wallet_info = wallet_manager.get_wallet_by_name(self.user_id, wallet_name, pin)
            if not self.wallet_info:
                logger.error(f"Failed to get wallet {wallet_name} for user {hash_user_id(self.user_id)}")
                return False
            
            # Get tracked tokens
            self.tracked_tokens = await token_manager.get_tracked_tokens(self.user_id)
            
            # Get token balances
            self.token_balances = await token_manager.balances(self.user_id)
            
            # Build context for LLM
            self.context = await self._build_llm_context()
            
            logger.info(f"Initialized context for user {hash_user_id(self.user_id)} in LLM app {self.llm_app_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize context for user {hash_user_id(self.user_id)}: {str(e)}")
            return False
    
    async def _build_llm_context(self) -> Dict[str, Any]:
        """Build context dictionary for LLM system prompt.
        
        Returns:
            Dict containing all relevant context for the LLM
        """
        wallet_address = self.wallet_info['address'] if self.wallet_info else None
        
        # Format token balances for LLM context
        balance_info = []
        for token_address, balance_data in self.token_balances.items():
            balance_info.append({
                "symbol": balance_data["symbol"],
                "name": balance_data["name"],
                "balance": balance_data["balance"],
                "address": token_address
            })
        
        return {
            "app_name": self.llm_app_name,
            "app_description": self.llm_app_config["description"],
            "wallet_address": wallet_address,
            "tracked_tokens": self.tracked_tokens,
            "token_balances": balance_info,
            "available_methods": self.llm_app_config["available_methods"]
        }
    
    def add_message(self, role: str, content: str) -> None:
        """Add a message to the conversation history.
        
        Args:
            role: "user" or "assistant"
            content: Message content
        """
        self.conversation_history.append({
            "role": role,
            "content": content
        })

    def _to_router_path_token(self, token_ref: str) -> str:
        """Convert a token reference to a router-compatible token address.

        The swap LLM app may carry native tokens as strings ("BNB"/"ETH") in the path.
        Router methods expect address[]; for native tokens we must use WETH/WBNB.
        """
        if token_ref in ("BNB", "ETH"):
            weth = os.getenv("WETH")
            if not weth:
                raise ValueError("WETH environment variable is required to route native token swaps")
            return transaction_manager.web3.to_checksum_address(weth)

        # token_ref should already be a checksum address (from parameter processing)
        if transaction_manager.web3.is_address(token_ref):
            return transaction_manager.web3.to_checksum_address(token_ref)

        raise ValueError(f"Invalid token reference in path: {token_ref!r}")

    @staticmethod
    def _normalize_path(path: List[str]) -> List[str]:
        """Normalize a path by removing consecutive duplicates."""
        if not path:
            return []
        normalized: List[str] = [path[0]]
        for item in path[1:]:
            if item != normalized[-1]:
                normalized.append(item)
        return normalized

    async def _select_best_swap_route(
        self,
        *,
        contract_address: str,
        abi: List[Dict[str, Any]],
        quote_method: str,
        amount: int,
        token_in: str,
        token_out: str,
        status_callback: Optional[Any] = None,
    ) -> tuple[List[str], Any]:
        """Try 4 possible TidalDex routes and pick the best non-reverting one.

        Supported route patterns (after resolving token symbols):
        - token_in -> CZUSD -> token_out
        - token_in -> CZB   -> token_out
        - token_in -> CZUSD -> CZB -> token_out
        - token_in -> CZB   -> CZUSD -> token_out

        Selection:
        - getAmountsOut: choose route with maximum output (last element).
        - getAmountsIn:  choose route with minimum required input (first element).
        """
        if quote_method not in ("getAmountsOut", "getAmountsIn"):
            raise ValueError(f"Unsupported quote method for route selection: {quote_method}")

        if amount <= 0:
            raise ValueError("Amount must be positive for route selection")

        czusd = await transaction_manager._resolve_token_symbol("CZUSD")
        czb = await transaction_manager._resolve_token_symbol("CZB")
        if not czusd or not czb:
            raise ValueError("Could not resolve CZUSD/CZB token addresses from token list")

        czusd_addr = transaction_manager.web3.to_checksum_address(czusd)
        czb_addr = transaction_manager.web3.to_checksum_address(czb)

        token_in_addr = self._to_router_path_token(token_in)
        token_out_addr = self._to_router_path_token(token_out)

        raw_candidates: List[List[str]] = [
            [token_in_addr, czusd_addr, token_out_addr],
            [token_in_addr, czb_addr, token_out_addr],
            [token_in_addr, czusd_addr, czb_addr, token_out_addr],
            [token_in_addr, czb_addr, czusd_addr, token_out_addr],
        ]

        candidates: List[List[str]] = []
        seen: set[tuple[str, ...]] = set()
        for cand in raw_candidates:
            normalized = self._normalize_path(cand)
            if len(normalized) < 2:
                continue
            key = tuple(normalized)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(normalized)

        best_path: Optional[List[str]] = None
        best_result: Any = None
        best_score: Optional[int] = None
        errors: List[str] = []

        for idx, cand in enumerate(candidates, start=1):
            if status_callback:
                await status_callback(f"Trying route {idx}/{len(candidates)}...")
            try:
                result = await transaction_manager.call_view_method(
                    contract_address,
                    abi,
                    quote_method,
                    [amount, cand],
                    status_callback=None,
                )
                if not isinstance(result, list) or not result:
                    raise ValueError(f"Unexpected {quote_method} result type: {type(result)}")

                score = int(result[-1]) if quote_method == "getAmountsOut" else int(result[0])
                if best_score is None:
                    best_score = score
                    best_path = cand
                    best_result = result
                else:
                    if quote_method == "getAmountsOut" and score > best_score:
                        best_score = score
                        best_path = cand
                        best_result = result
                    if quote_method == "getAmountsIn" and score < best_score:
                        best_score = score
                        best_path = cand
                        best_result = result
            except Exception as e:
                errors.append(f"route={cand}: {e}")

        if best_path is None:
            err_preview = "; ".join(errors[:4]) + (" ..." if len(errors) > 4 else "")
            raise ValueError(f"All swap routes failed for {quote_method}. Errors: {err_preview}")

        logger.info(
            "Selected best swap route for %s user=%s path=%s score=%s",
            quote_method,
            hash_user_id(self.user_id),
            best_path,
            best_score,
        )
        return best_path, best_result
    
    async def handle_view_call(
        self,
        method_name: str,
        parameters: Dict[str, Any],
        status_callback: Optional[Any] = None
    ) -> Any:
        """Handle a view (read-only) contract call.
        
        Args:
            method_name: Name of the contract method to call
            parameters: Method parameters
            status_callback: Optional callback for status updates
            
        Returns:
            Result of the contract call
        """
        try:
            # Find method config
            method_config = self._find_method_config(method_name, "view")
            if not method_config:
                raise ValueError(f"View method {method_name} not found in LLM app configuration")
            
            # Get contract info
            contract_name = method_config.get("contract", list(self.llm_app_config["contracts"].keys())[0])
            contract_config = self.llm_app_config["contracts"][contract_name]
            contract_address = os.getenv(contract_config["address_env_var"])
            
            if not contract_address:
                raise ValueError(f"Contract address not found: {contract_config['address_env_var']}")
            
            # Load ABI
            abi_path = f"app/llm_apps/{self.llm_app_name}/{contract_config['abi_file']}"
            abi = self._load_abi(abi_path)
            
            # Process parameters
            processed_params = await transaction_manager.process_parameters(
                method_config, parameters, self.llm_app_config
            )
            
            # TidalDex swap routing: probe multiple routes and pick best
            if (
                self.llm_app_name == "swap"
                and method_name in ("getAmountsOut", "getAmountsIn")
                and isinstance(processed_params.get("path"), list)
                and len(processed_params["path"]) >= 2
            ):
                amount_key = "amountIn" if method_name == "getAmountsOut" else "amountOut"
                amount_val = processed_params.get(amount_key)
                if amount_val is None:
                    raise ValueError(f"Missing required parameter '{amount_key}' for {method_name}")

                token_in = processed_params["path"][0]
                token_out = processed_params["path"][-1]
                best_path, best_result = await self._select_best_swap_route(
                    contract_address=contract_address,
                    abi=abi,
                    quote_method=method_name,
                    amount=int(amount_val),
                    token_in=str(token_in),
                    token_out=str(token_out),
                    status_callback=status_callback,
                )
                logger.info(
                    "Using routed path for %s user=%s original=%s selected=%s",
                    method_name,
                    hash_user_id(self.user_id),
                    processed_params.get("path"),
                    best_path,
                )
                return best_result

            # Generic path: Prepare arguments in correct order and execute
            args = [processed_params.get(param) for param in method_config["inputs"]]
            result = await transaction_manager.call_view_method(
                contract_address,
                abi,
                method_name,
                args,
                status_callback,
            )
            
            logger.info(f"View call {method_name} executed successfully for user {hash_user_id(self.user_id)}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to handle view call {method_name}: {str(e)}")
            raise
    
    async def prepare_write_call(
        self,
        method_name: str,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Prepare a write (state-changing) contract call for confirmation.
        
        Args:
            method_name: Name of the contract method to call
            parameters: Method parameters
            
        Returns:
            Dict containing transaction preview information
        """
        try:
            # Find method config
            method_config = self._find_method_config(method_name, "write")
            if not method_config:
                raise ValueError(f"Write method {method_name} not found in LLM app configuration")
            
            # Prepare transaction preview (this will process parameters internally)
            preview = await transaction_manager.prepare_transaction_preview(
                method_config,
                parameters,
                self.llm_app_config,
                self.wallet_info["address"]
            )
            
            # Use processed_params from preview (already has defaults resolved)
            processed_params = preview["processed_params"]

            # For swap write calls, select a viable/best routed path before confirmation.
            if (
                self.llm_app_name == "swap"
                and isinstance(processed_params.get("path"), list)
                and len(processed_params["path"]) >= 2
                and "path" in method_config.get("inputs", [])
            ):
                # Load router ABI/address for quote calls
                contract_name = method_config.get("contract", list(self.llm_app_config["contracts"].keys())[0])
                contract_config = self.llm_app_config["contracts"][contract_name]
                contract_address = os.getenv(contract_config["address_env_var"])
                if not contract_address:
                    raise ValueError(f"Contract address not found: {contract_config['address_env_var']}")
                abi_path = f"app/llm_apps/{self.llm_app_name}/{contract_config['abi_file']}"
                abi = self._load_abi(abi_path)

                amount_for_quote = processed_params.get("amountIn")
                if amount_for_quote is None:
                    amount_for_quote = processed_params.get("value_wei")

                if amount_for_quote is not None and int(amount_for_quote) > 0:
                    token_in = processed_params["path"][0]
                    token_out = processed_params["path"][-1]
                    best_path, _best_amounts = await self._select_best_swap_route(
                        contract_address=contract_address,
                        abi=abi,
                        quote_method="getAmountsOut",
                        amount=int(amount_for_quote),
                        token_in=str(token_in),
                        token_out=str(token_out),
                        status_callback=None,
                    )
                    processed_params["path"] = best_path
                    preview["processed_params"] = processed_params
            
            # Store pending transaction
            self.pending_transaction = PendingTransaction(
                method_config=method_config,
                processed_params=processed_params,
                app_config=self.llm_app_config,
                preview=preview,
                raw_params=parameters
            )
            
            self.state = SessionState.AWAITING_CONFIRMATION
            
            logger.info(f"Prepared write call {method_name} for user {hash_user_id(self.user_id)}")
            return preview
            
        except Exception as e:
            logger.error(f"Failed to prepare write call {method_name}: {str(e)}")
            self.state = SessionState.ERROR
            raise
    
    async def execute_pending_transaction(
        self,
        status_callback: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Execute the pending transaction after confirmation.
        
        Args:
            status_callback: Optional callback for status updates
            
        Returns:
            Dict containing transaction result
        """
        try:
            if not self.pending_transaction:
                raise ValueError("No pending transaction to execute")
            
            if self.state != SessionState.AWAITING_CONFIRMATION:
                raise ValueError(f"Invalid state for execution: {self.state}")
            
            # Check PIN requirements
            user_id_int = int(self.user_id)
            if pin_manager.needs_pin(user_id_int):
                pin = pin_manager.get_pin(user_id_int)
                if not pin:
                    self.state = SessionState.AWAITING_PIN
                    raise ValueError("PIN required but not available")
            
            # Get contract info
            contract_name = self.pending_transaction.method_config.get(
                "contract", 
                list(self.llm_app_config["contracts"].keys())[0]
            )
            contract_config = self.llm_app_config["contracts"][contract_name]
            contract_address = os.getenv(contract_config["address_env_var"])
            
            # Load ABI
            abi_path = f"app/llm_apps/{self.llm_app_name}/{contract_config['abi_file']}"
            abi = self._load_abi(abi_path)
            
            # Prepare arguments
            method_config = self.pending_transaction.method_config
            processed_params = self.pending_transaction.processed_params
            raw_params = self.pending_transaction.raw_params
            args = [processed_params.get(param) for param in method_config["inputs"]]
            value_wei = processed_params.get("value_wei", 0)
            
            # Execute the transaction
            result = await transaction_manager.call_write_method(
                self.wallet_info,
                contract_address,
                abi,
                method_config["name"],
                args,
                value_wei,
                status_callback,
                method_config=method_config,
                processed_params=processed_params,
                raw_params=raw_params
            )
            
            self.state = SessionState.COMPLETED
            self.pending_transaction = None
            
            logger.info(f"Executed transaction {method_config['name']} for user {hash_user_id(self.user_id)}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to execute pending transaction: {str(e)}")
            self.state = SessionState.ERROR
            raise
    
    def cancel_pending_transaction(self) -> None:
        """Cancel the pending transaction and return to active state."""
        self.pending_transaction = None
        self.state = SessionState.ACTIVE
        logger.info(f"Cancelled pending transaction for user {hash_user_id(self.user_id)}")
    
    def _find_method_config(self, method_name: str, method_type: str) -> Optional[Dict[str, Any]]:
        """Find method configuration by name and type.
        
        Args:
            method_name: Name of the method to find
            method_type: "view" or "write"
            
        Returns:
            Method configuration dict or None if not found
        """
        methods = self.llm_app_config["available_methods"].get(method_type, [])
        for method in methods:
            if method["name"] == method_name:
                return method
        return None
    
    def _load_abi(self, abi_path: str) -> List[Dict]:
        """Load ABI from JSON file.
        
        Args:
            abi_path: Path to the ABI JSON file
            
        Returns:
            List[Dict]: Contract ABI
        """
        try:
            with open(abi_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load ABI from {abi_path}: {str(e)}")
            raise ValueError(f"Could not load ABI file: {abi_path}")
    
    async def format_confirmation_message(self) -> str:
        """Format the confirmation message for pending transaction.
        
        Returns:
            str: Formatted confirmation message
        """
        if not self.pending_transaction:
            return "No pending transaction"
        
        preview = self.pending_transaction.preview
        
        return (
            f"🔄 **Transaction Preview**\n\n"
            f"{preview['summary']}\n\n"
            f"⚙️ **Method:** {preview['method_name']}\n"
            f"🏦 **Contract:** {preview.get('contract_name', 'Unknown')}\n"
            f"⛽ **Estimated Gas:** {preview['gas_estimate'].get('total_cost_bnb', 'Unknown')} BNB\n\n"
            f"Please verify these details carefully before confirming."
        )
    
    def get_confirmation_keyboard(self) -> InlineKeyboardMarkup:
        """Get the inline keyboard for transaction confirmation.
        
        Returns:
            InlineKeyboardMarkup: Keyboard with confirm/cancel buttons
        """
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Confirm Transaction", callback_data=f"llm_app_confirm_{self.llm_app_name}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"llm_app_cancel_{self.llm_app_name}")
            ]
        ])