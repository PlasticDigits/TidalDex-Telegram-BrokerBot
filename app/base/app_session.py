"""
App session management for tracking conversation state and handling transactions.
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
    """Possible states of an app session."""
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

class AppSession:
    """Manages the state and execution of an app conversation session."""
    
    def __init__(self, user_id: str, app_name: str, app_config: Dict[str, Any]):
        """Initialize an app session.
        
        Args:
            user_id: Telegram user ID as string
            app_name: Name of the app being used
            app_config: Full app configuration
        """
        self.user_id = user_id
        self.app_name = app_name
        self.app_config = app_config
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
            
            logger.info(f"Initialized context for user {hash_user_id(self.user_id)} in app {self.app_name}")
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
            "app_name": self.app_name,
            "app_description": self.app_config["description"],
            "wallet_address": wallet_address,
            "tracked_tokens": self.tracked_tokens,
            "token_balances": balance_info,
            "available_methods": self.app_config["available_methods"]
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
                raise ValueError(f"View method {method_name} not found in app configuration")
            
            # Get contract info
            contract_name = method_config.get("contract", list(self.app_config["contracts"].keys())[0])
            contract_config = self.app_config["contracts"][contract_name]
            contract_address = os.getenv(contract_config["address_env_var"])
            
            if not contract_address:
                raise ValueError(f"Contract address not found: {contract_config['address_env_var']}")
            
            # Load ABI
            abi_path = f"app/apps/{self.app_name}/{contract_config['abi_file']}"
            abi = self._load_abi(abi_path)
            
            # Process parameters
            processed_params = await transaction_manager.process_parameters(
                method_config, parameters, self.app_config
            )
            
            # Prepare arguments in correct order
            args = [processed_params.get(param) for param in method_config["inputs"]]
            
            # Execute the call
            result = await transaction_manager.call_view_method(
                contract_address,
                abi,
                method_name,
                args,
                status_callback
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
                raise ValueError(f"Write method {method_name} not found in app configuration")
            
            # Process parameters
            processed_params = await transaction_manager.process_parameters(
                method_config, parameters, self.app_config
            )
            
            # Set default values
            if "to" in processed_params and processed_params["to"] == "user_wallet_address":
                processed_params["to"] = self.wallet_info["address"]
            
            # Prepare transaction preview
            preview = await transaction_manager.prepare_transaction_preview(
                method_config,
                processed_params,
                self.app_config,
                self.wallet_info["address"]
            )
            
            # Store pending transaction
            self.pending_transaction = PendingTransaction(
                method_config=method_config,
                processed_params=processed_params,
                app_config=self.app_config,
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
                list(self.app_config["contracts"].keys())[0]
            )
            contract_config = self.app_config["contracts"][contract_name]
            contract_address = os.getenv(contract_config["address_env_var"])
            
            # Load ABI
            abi_path = f"app/apps/{self.app_name}/{contract_config['abi_file']}"
            abi = self._load_abi(abi_path)
            
            # Prepare arguments
            method_config = self.pending_transaction.method_config
            processed_params = self.pending_transaction.processed_params
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
                status_callback
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
        methods = self.app_config["available_methods"].get(method_type, [])
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
                InlineKeyboardButton("✅ Confirm Transaction", callback_data=f"app_confirm_{self.app_name}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"app_cancel_{self.app_name}")
            ]
        ])