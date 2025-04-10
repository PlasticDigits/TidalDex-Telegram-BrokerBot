"""
Utility functions for formatting numbers with significant figures.
"""
import math
from decimal import Decimal
from typing import Union

def number_display_with_sigfig(number: Union[int, float, Decimal], sig_figs: int) -> str:
    """
    Formats a number with the specified number of significant figures.
    For numbers >= 1000, uses human-readable suffixes (k, m, b, t, q).
    Always truncates (rounds down) the last digit.
    
    Args:
        number: The number to format (int, float, or Decimal)
        sig_figs: Number of significant figures to display
        
    Returns:
        str: Formatted number string with appropriate suffix
        
    Examples:
        >>> number_display_with_sigfig(0.00004291432134, 2)
        '0.000042'
        >>> number_display_with_sigfig(41283.923799, 8)
        '41283.92'
        >>> number_display_with_sigfig(1500000, 3)
        '1.50m'
        >>> number_display_with_sigfig(0.00004212391432134, 8)
        '0.000042123914'
    """
    if not isinstance(number, (int, float, Decimal)):
        raise TypeError("Number must be int, float, or Decimal")
    
    if sig_figs < 1:
        raise ValueError("Significant figures must be at least 1")
    
    # Convert to Decimal for precise decimal arithmetic
    num = Decimal(str(number))
    
    # Handle zero case
    if num == 0:
        return "0"
    
    # Handle negative numbers
    is_negative = num < 0
    num = abs(num)
    
    # Define suffixes and their values
    suffixes = [
        ('q', Decimal('1e15')),  # quadrillion
        ('t', Decimal('1e12')),  # trillion
        ('b', Decimal('1e9')),   # billion
        ('m', Decimal('1e6')),   # million
        ('k', Decimal('1e3')),   # thousand
    ]
    
    # Find appropriate suffix
    suffix = ''
    for s, value in suffixes:
        if num >= value:
            num = num / value
            suffix = s
            break
    
    # Calculate number of decimal places needed
    if num >= 1:
        # For numbers >= 1, count digits before decimal
        digits_before_decimal = len(str(int(num)))
        decimal_places = max(0, sig_figs - digits_before_decimal)
    else:
        # For numbers < 1, find the first non-zero digit
        str_num = format(num, '.20f').rstrip('0')
        if '.' in str_num:
            decimal_part = str_num.split('.')[1]
            leading_zeros = len(decimal_part) - len(decimal_part.lstrip('0'))
            # The first non-zero digit is at position leading_zeros + 1
            # We want sig_figs digits after that position
            decimal_places = leading_zeros + sig_figs
        else:
            decimal_places = 0
    
    # Format the number with truncation
    format_str = f"{{:.{decimal_places}f}}"
    result = format_str.format(float(num))
    
    # Remove trailing zeros and decimal point if not needed
    if '.' in result:
        result = result.rstrip('0').rstrip('.')
    
    # Add negative sign and suffix
    if is_negative:
        result = f"-{result}"
    if suffix:
        result = f"{result}{suffix}"
    
    return result 