#!/usr/bin/env python3
"""
Live RPC test for CL8Y/CZB swap routes on BSC TidalDex.

This script queries the TidalDex router directly to verify which routes
have liquidity for CL8Y <-> CZB swaps.
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()

from utils.web3_connection import w3

# Token addresses
# NOTE: Old CL8Y was 0x999311589cc1Ed0065AD9eD9702cB593FFc62ddF (migrated/stale)
CL8Y = w3.to_checksum_address("0x8F452a1fdd388A45e1080992eFF051b4dd9048d2")  # Correct address
CZB = w3.to_checksum_address("0xD963b2236D227a0302E19F2f9595F424950dc186")
CZUSD = w3.to_checksum_address("0xE68b79e51bf826534Ff37AA9CeE71a3842ee9c70")

# Router address
ROUTER = w3.to_checksum_address(os.getenv("DEX_ROUTER_ADDRESS", "0x71aB950a0C349103967e711b931c460E9580c631"))

# Minimal ABI for getAmountsOut
ROUTER_ABI = [
    {
        "type": "function",
        "name": "getAmountsOut",
        "inputs": [
            {"name": "amountIn", "type": "uint256"},
            {"name": "path", "type": "address[]"}
        ],
        "outputs": [
            {"name": "amounts", "type": "uint256[]"}
        ],
        "stateMutability": "view"
    }
]


def test_route(amount_in: int, path: List[str]) -> Tuple[bool, Optional[List[int]], Optional[str]]:
    """Test a swap route via getAmountsOut.
    
    Returns:
        Tuple of (success, amounts_out, error_message)
    """
    try:
        router = w3.eth.contract(address=ROUTER, abi=ROUTER_ABI)
        amounts = router.functions.getAmountsOut(amount_in, path).call()
        return True, amounts, None
    except Exception as e:
        error_str = str(e)
        # Extract readable part
        if "INSUFFICIENT_LIQUIDITY" in error_str:
            return False, None, "INSUFFICIENT_LIQUIDITY"
        if "execution reverted" in error_str:
            return False, None, f"Reverted: {error_str[:200]}"
        return False, None, str(e)[:200]


def format_amount(amount: int, symbol: str, decimals: int = 18) -> str:
    """Format amount as human-readable."""
    human = amount / (10 ** decimals)
    return f"{human:.6f} {symbol}"


def get_path_description(path: List[str]) -> str:
    """Get human-readable path description."""
    symbol_map = {
        CL8Y: "CL8Y",
        CZB: "CZB",
        CZUSD: "CZUSD"
    }
    symbols = [symbol_map.get(addr, addr[:10] + "...") for addr in path]
    return " -> ".join(symbols)


def main():
    print("=" * 70)
    print("Live RPC Test: CL8Y <-> CZB Swap Routes on TidalDex (BSC)")
    print("=" * 70)
    
    print(f"\nRouter: {ROUTER}")
    print(f"CL8Y:   {CL8Y}")
    print(f"CZB:    {CZB}")
    print(f"CZUSD:  {CZUSD}")
    
    # Test amounts
    test_amounts = [
        (10 ** 18, "1 CL8Y"),        # 1 token
        (10 ** 17, "0.1 CL8Y"),      # 0.1 token
        (10 ** 16, "0.01 CL8Y"),     # 0.01 token
        (10 ** 15, "0.001 CL8Y"),    # 0.001 token
    ]
    
    # Test routes for CL8Y -> CZB
    routes = [
        [CL8Y, CZB],           # Direct
        [CL8Y, CZUSD, CZB],    # Via CZUSD
    ]
    
    print("\n" + "=" * 70)
    print("Testing CL8Y -> CZB routes:")
    print("=" * 70)
    
    for amount, amount_desc in test_amounts:
        print(f"\nAmount in: {amount_desc}")
        print("-" * 50)
        
        for path in routes:
            path_desc = get_path_description(path)
            success, amounts, error = test_route(amount, path)
            
            if success:
                out_amount = amounts[-1]
                out_human = format_amount(out_amount, "CZB")
                print(f"  ✓ {path_desc}: {out_human}")
            else:
                print(f"  ✗ {path_desc}: {error}")
    
    # Also test reverse routes (CZB -> CL8Y)
    print("\n" + "=" * 70)
    print("Testing CZB -> CL8Y routes:")
    print("=" * 70)
    
    reverse_amounts = [
        (10 ** 18, "1 CZB"),
        (10 ** 17, "0.1 CZB"),
    ]
    
    reverse_routes = [
        [CZB, CL8Y],           # Direct
        [CZB, CZUSD, CL8Y],    # Via CZUSD
    ]
    
    for amount, amount_desc in reverse_amounts:
        print(f"\nAmount in: {amount_desc}")
        print("-" * 50)
        
        for path in reverse_routes:
            path_desc = get_path_description(path)
            success, amounts, error = test_route(amount, path)
            
            if success:
                out_amount = amounts[-1]
                out_human = format_amount(out_amount, "CL8Y")
                print(f"  ✓ {path_desc}: {out_human}")
            else:
                print(f"  ✗ {path_desc}: {error}")
    
    # Test individual pair liquidity
    print("\n" + "=" * 70)
    print("Testing individual pair liquidity:")
    print("=" * 70)
    
    pair_tests = [
        ([CL8Y, CZUSD], "CL8Y/CZUSD", 10 ** 17),
        ([CZUSD, CL8Y], "CZUSD/CL8Y", 10 ** 17),
        ([CZUSD, CZB], "CZUSD/CZB", 10 ** 17),
        ([CZB, CZUSD], "CZB/CZUSD", 10 ** 17),
        ([CL8Y, CZB], "CL8Y/CZB", 10 ** 17),
        ([CZB, CL8Y], "CZB/CL8Y", 10 ** 17),
    ]
    
    for path, pair_name, amount in pair_tests:
        success, amounts, error = test_route(amount, path)
        if success:
            print(f"  ✓ {pair_name}: Liquidity exists")
        else:
            print(f"  ✗ {pair_name}: {error}")
    
    print("\n" + "=" * 70)
    print("Test complete!")
    print("=" * 70)


if __name__ == "__main__":
    main()
