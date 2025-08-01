"""
Transaction formatting service for creating human-readable transaction summaries.
"""
import logging
from typing import Dict, List, Any, Optional
from services.tokens import token_manager
from services.transaction.number_converter import NumberConverter

logger = logging.getLogger(__name__)

class TransactionFormatter:
    """Format transaction parameters into human-readable confirmations."""
    
    def __init__(self):
        """Initialize the TransactionFormatter."""
        self.token_manager = token_manager
        self.number_converter = NumberConverter()
        
    async def format_transaction_summary(
        self,
        method_config: Dict[str, Any],
        raw_params: Dict[str, Any],
        app_config: Dict[str, Any]
    ) -> str:
        """Generate human-readable transaction summary without LLM.
        
        Args:
            method_config: Configuration for the specific method
            raw_params: Raw parameters for the transaction
            app_config: Full app configuration
            
        Returns:
            str: Human-readable transaction summary
        """
        try:
            token_amount_pairs = method_config.get("token_amount_pairs", [])
            formatted_pairs = []
            
            for pair in token_amount_pairs:
                # Resolve token address
                token_address = self._resolve_token_param(
                    pair["token_param"],
                    raw_params
                )
                
                # Get amount value
                amount_raw = self._resolve_amount_param(
                    pair["amount_param"],
                    raw_params
                )
                
                # Format the pair
                formatted_pair = await self._format_token_amount_pair(
                    token_address,
                    amount_raw,
                    pair["display_as"],
                    raw_params
                )
                formatted_pairs.append(formatted_pair)
            
            # Combine using human_summary template or default
            summary_template = method_config.get(
                "human_summary",
                " ".join([p["display_as"] for p in token_amount_pairs])
            )
            
            # Create context for template replacement
            template_context = {
                "input": formatted_pairs[0] if len(formatted_pairs) > 0 else "",
                "output": formatted_pairs[1] if len(formatted_pairs) > 1 else "",
                "payment": next((p for p in formatted_pairs if "Pay" in p), ""),
                "stake": next((p for p in formatted_pairs if "Stake" in p), ""),
                "withdraw": next((p for p in formatted_pairs if "Withdraw" in p), ""),
            }
            
            return self._apply_template(summary_template, template_context)
            
        except Exception as e:
            logger.error(f"Failed to format transaction summary: {str(e)}")
            return f"Execute {method_config.get('name', 'unknown method')}"
    
    async def _format_token_amount_pair(
        self,
        token_address: str,
        amount_raw: int,
        display_template: str,
        raw_params: Dict[str, Any]
    ) -> str:
        """Format a single token/amount pair.
        
        Args:
            token_address: Token contract address or "BNB" for native
            amount_raw: Raw amount in token's smallest unit
            display_template: Template string for display
            raw_params: All raw parameters for template substitution
            
        Returns:
            str: Formatted token/amount pair string
        """
        try:
            if token_address == "BNB":
                symbol = "BNB"
                decimals = 18
            else:
                # Get token info from TokenManager
                token_info = await self.token_manager.get_token_info(token_address)
                if not token_info:
                    logger.warning(f"Token info not found for {token_address}")
                    return f"Unknown Token ({amount_raw} raw units)"
                
                symbol = token_info['symbol']
                decimals = token_info['decimals']
            
            # Convert to human readable
            formatted_amount = self.number_converter.to_human_readable(amount_raw, decimals)
            
            # Apply template with available substitutions
            template_vars = {
                "amount": formatted_amount,
                "symbol": symbol,
                **raw_params  # Allow access to other params like itemId, poolId, etc.
            }
            
            result = display_template.format(**template_vars)
            return result
            
        except Exception as e:
            logger.error(f"Failed to format token/amount pair: {str(e)}")
            return f"{amount_raw} {token_address}"
    
    def _resolve_token_param(self, token_param: str, raw_params: Dict[str, Any]) -> str:
        """Resolve token address from parameter reference.
        
        Args:
            token_param: Parameter reference (e.g., "path[0]", "tokenAddress", "BNB")
            raw_params: Raw parameters dictionary
            
        Returns:
            str: Resolved token address
        """
        try:
            if token_param == "BNB":
                return "BNB"
            elif token_param.startswith("path["):
                # Handle path[0], path[-1], etc.
                path = raw_params.get("path", [])
                if not path:
                    return ""
                
                if token_param == "path[0]":
                    return path[0] if len(path) > 0 else ""
                elif token_param == "path[-1]":
                    return path[-1] if len(path) > 0 else ""
                else:
                    # Handle path[1], path[2], etc.
                    import re
                    match = re.match(r"path\[(\d+)\]", token_param)
                    if match:
                        index = int(match.group(1))
                        return path[index] if 0 <= index < len(path) else ""
            else:
                # Direct parameter reference
                return raw_params.get(token_param, "")
            
        except Exception as e:
            logger.error(f"Failed to resolve token param '{token_param}': {str(e)}")
            return ""
        
        return ""
    
    def _resolve_amount_param(self, amount_param: str, raw_params: Dict[str, Any]) -> int:
        """Resolve amount value from parameter reference.
        
        Args:
            amount_param: Parameter reference (e.g., "amountIn", "value_wei")
            raw_params: Raw parameters dictionary
            
        Returns:
            int: Resolved amount in raw units
        """
        try:
            if amount_param == "value_wei":
                return raw_params.get("value_wei", 0)
            else:
                return raw_params.get(amount_param, 0)
                
        except Exception as e:
            logger.error(f"Failed to resolve amount param '{amount_param}': {str(e)}")
            return 0
    
    def _apply_template(self, template: str, context: Dict[str, str]) -> str:
        """Apply template substitution.
        
        Args:
            template: Template string with {variable} placeholders
            context: Dictionary of variable substitutions
            
        Returns:
            str: Template with substitutions applied
        """
        try:
            return template.format(**context)
        except KeyError as e:
            logger.warning(f"Template variable not found: {str(e)}")
            return template
        except Exception as e:
            logger.error(f"Failed to apply template: {str(e)}")
            return template
    
    async def validate_token_amount_pairs(
        self,
        method_config: Dict[str, Any],
        raw_params: Dict[str, Any]
    ) -> bool:
        """Validate that all tokens in pairs are tracked by TokenManager.
        
        Args:
            method_config: Configuration for the specific method
            raw_params: Raw parameters for the transaction
            
        Returns:
            bool: True if all tokens are valid
            
        Raises:
            ValueError: If any token is not found in TokenManager
        """
        try:
            token_amount_pairs = method_config.get("token_amount_pairs", [])
            
            for pair in token_amount_pairs:
                token_address = self._resolve_token_param(
                    pair["token_param"],
                    raw_params
                )
                
                if token_address and token_address != "BNB":
                    token_info = await self.token_manager.get_token_info(token_address)
                    if not token_info:
                        raise ValueError(
                            f"Token {token_address} not found. Please track this token first using /track."
                        )
            
            return True
            
        except Exception as e:
            logger.error(f"Token validation failed: {str(e)}")
            raise