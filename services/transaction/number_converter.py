"""
Number conversion utilities for blockchain transactions.
Handles conversion between human-readable and raw token amounts.
"""
import logging
import re
from decimal import Decimal
from typing import Union, Dict, Any
from utils.number_display import number_display_with_sigfig
from utils.token_operations import convert_to_raw_amount

logger = logging.getLogger(__name__)

class NumberConverter:
    """Utility class for converting between human-readable and raw token amounts."""
    
    @staticmethod
    def to_human_readable(raw_amount: int, decimals: int, sig_figs: int = 6) -> str:
        """Convert raw token amount to human-readable format.
        
        Args:
            raw_amount: Raw token amount (in wei-like units)
            decimals: Number of decimals for the token
            sig_figs: Number of significant figures to display
            
        Returns:
            str: Human-readable amount (e.g., "1.5", "2.352m")
        """
        try:
            if raw_amount == 0:
                return "0"
                
            human_amount = raw_amount / (10 ** decimals)
            return number_display_with_sigfig(human_amount, sig_figs)
            
        except Exception as e:
            logger.error(f"Failed to convert {raw_amount} to human readable: {str(e)}")
            return str(raw_amount)
    
    @staticmethod
    def to_raw_amount(human_input: str, decimals: int) -> int:
        """Convert human-readable input to raw token amount.
        
        Args:
            human_input: Human-readable amount (e.g., "1.5", "2.5m", "1000k")
            decimals: Number of decimals for the token
            
        Returns:
            int: Raw token amount
        """
        try:
            # Parse human input with suffixes
            parsed_amount = NumberConverter._parse_human_input(human_input)
            return convert_to_raw_amount(parsed_amount, decimals)
            
        except Exception as e:
            logger.error(f"Failed to convert '{human_input}' to raw amount: {str(e)}")
            raise ValueError(f"Invalid amount format: {human_input}")
    
    @staticmethod
    def _parse_human_input(human_input: str) -> float:
        """Parse human input with optional suffixes (k, m, b, t).
        
        Args:
            human_input: Input string like "1.5", "2.5m", "1000k"
            
        Returns:
            float: Parsed numeric value
        """
        human_input = human_input.strip().lower()
        
        # Define multipliers for suffixes
        multipliers = {
            'k': 1_000,
            'm': 1_000_000, 
            'b': 1_000_000_000,
            't': 1_000_000_000_000,
            'q': 1_000_000_000_000_000
        }
        
        # Check for suffix
        if human_input[-1] in multipliers:
            suffix = human_input[-1]
            number_part = human_input[:-1]
            multiplier = multipliers[suffix]
        else:
            number_part = human_input
            multiplier = 1
        
        # Parse the numeric part
        try:
            number = float(number_part)
            return number * multiplier
        except ValueError:
            raise ValueError(f"Invalid numeric format: {number_part}")
    
    @staticmethod
    def format_gas_estimate(gas_wei: int, gas_price_wei: int) -> Dict[str, str]:
        """Format gas estimate for human display.
        
        Args:
            gas_wei: Gas amount in wei
            gas_price_wei: Gas price in wei
            
        Returns:
            Dict containing formatted gas information
        """
        try:
            # Convert to BNB (18 decimals)
            total_cost_bnb = (gas_wei * gas_price_wei) / (10 ** 18)
            
            return {
                "gas_limit": f"{gas_wei:,}",
                "gas_price_gwei": f"{gas_price_wei / (10 ** 9):.1f}",
                "total_cost_bnb": number_display_with_sigfig(total_cost_bnb, 4),
                "total_cost_usd": ""  # Could add USD conversion later
            }
            
        except Exception as e:
            logger.error(f"Failed to format gas estimate: {str(e)}")
            return {
                "gas_limit": "Unknown",
                "gas_price_gwei": "Unknown", 
                "total_cost_bnb": "Unknown",
                "total_cost_usd": ""
            }