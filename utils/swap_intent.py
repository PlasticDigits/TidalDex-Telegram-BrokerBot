"""
Utilities for detecting swap intent and extracting parameters from free-form text.

These helpers are used to improve the swap UX in the LLM app by allowing a single
"Swap X for Y ..." request to immediately produce a transaction confirmation after
quoting, without requiring multiple user re-prompts.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Optional


_SWAP_INTENT_RE = re.compile(r"\b(swap|trade|exchange)\b", flags=re.IGNORECASE)
_SLIPPAGE_RE = re.compile(
    r"(?P<pct>\d+(?:\.\d+)?)\s*%?\s*(?:slippage|slip)\b",
    flags=re.IGNORECASE,
)


def is_swap_intent(text: str) -> bool:
    """Return True if the user message likely intends to execute a swap."""
    return bool(_SWAP_INTENT_RE.search(text or ""))


def parse_slippage_bps(text: str) -> Optional[int]:
    """Parse slippage from text and return it as basis points (bps).

    Examples:
        "1% slippage" -> 100
        "0.5 slippage" -> 50
        "slippage 2" -> 200

    Returns:
        Slippage in bps, or None if not present / invalid.
    """
    if not text:
        return None

    m = _SLIPPAGE_RE.search(text)
    if not m:
        return None

    try:
        pct = Decimal(m.group("pct"))
    except (InvalidOperation, TypeError):
        return None

    if pct < 0:
        return None

    # 1% == 100 bps
    bps = int((pct * Decimal("100")).to_integral_value(rounding="ROUND_HALF_UP"))
    return bps


