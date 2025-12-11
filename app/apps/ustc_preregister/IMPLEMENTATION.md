# USTC+ PREREGISTER App Implementation Plan

## Overview

This document outlines the implementation plan for adding a new "ustc_preregister" app to the TidalDex Telegram Bot. The app allows users to interact with the USTC Preregister smart contract for depositing and withdrawing USTC-cb tokens.

## App Requirements

### 1. View Global Stats
- **Total Deposits**: Display total deposits across all users using `getTotalDeposits()`
- **Total Users**: Display total number of users using `getUserCount()`

### 2. View Wallet Stats
- **Active Wallet Deposit**: Display the deposit amount for the user's currently active wallet using `getUserDeposit(wallet_address)`

### 3. Deposit/Withdraw Operations
- **Deposit**: Call `deposit(amount)` with "ALL" meaning the total active wallet's USTC-cb balance
- **Withdraw**: Call `withdraw(amount)` with "ALL" meaning the active wallet's `getUserDeposit` amount

## Constants

- **USTC-cb Token Address**: `0xA4224f910102490Dc02AAbcBc6cb3c59Ff390055`
- **Environment Variable for Contract**: `USTC_PREREGISTER_ADDRESS`

---

## Implementation Steps

### Step 1: Create App Directory Structure

```
app/apps/ustc_preregister/
├── abi/
│   └── USTCPreregister.json
├── config.json
├── STYLE.md
└── IMPLEMENTATION.md
```

### Step 2: Copy ABI File

Copy the ABI file from `ABI/USTCPreregister.json` to `app/apps/ustc_preregister/abi/USTCPreregister.json`.

### Step 3: Create config.json

```json
{
  "name": "ustc_preregister",
  "description": "USTC+ Preregister - Deposit and withdraw USTC-cb tokens for the preregistration program",
  "contracts": {
    "preregister": {
      "address_env_var": "USTC_PREREGISTER_ADDRESS",
      "abi_file": "abi/USTCPreregister.json"
    }
  },
  "available_methods": {
    "view": [
      {
        "name": "getTotalDeposits",
        "description": "Get total deposits across all users",
        "inputs": [],
        "contract": "preregister"
      },
      {
        "name": "getUserCount",
        "description": "Get total number of users who have deposited",
        "inputs": [],
        "contract": "preregister"
      },
      {
        "name": "getUserDeposit",
        "description": "Get deposit amount for a specific wallet address",
        "inputs": ["user"],
        "contract": "preregister"
      }
    ],
    "write": [
      {
        "name": "deposit",
        "description": "Deposit USTC-cb tokens into the preregister contract",
        "inputs": ["amount"],
        "contract": "preregister",
        "requires_token_approval": true,
        "gas_estimate": "medium",
        "token_amount_pairs": [
          {
            "token_param": "token_address",
            "amount_param": "amount",
            "direction": "payment",
            "display_as": "Deposit {amount} {symbol}"
          }
        ],
        "human_summary": "{input}"
      },
      {
        "name": "withdraw",
        "description": "Withdraw USTC-cb tokens from the preregister contract",
        "inputs": ["amount"],
        "contract": "preregister",
        "requires_token_approval": false,
        "gas_estimate": "medium",
        "token_amount_pairs": [
          {
            "token_param": "token_address",
            "amount_param": "amount",
            "direction": "withdraw",
            "display_as": "Withdraw {amount} {symbol}"
          }
        ],
        "human_summary": "{input}"
      }
    ]
  },
  "parameter_processing": {
    "amount": {
      "type": "token_amount",
      "convert_from_human": true,
      "get_decimals_from": "token_address"
    },
    "token_address": {
      "type": "address"
    },
    "user": {
      "type": "address"
    }
  }
}
```

**Important Notes:**
- The `parameter_processing.*.default` field is NOT automatically applied by the current `process_parameters()` implementation. Defaults must be set explicitly in code or by the LLM.
- The LLM **must** include `token_address` in parameters for deposit/withdraw, or code must inject it.

### Step 4: Create STYLE.md

```markdown
# USTC+ Preregister App Style Guide

## Personality & Tone

- **Professional and informative** - Explain the preregistration program clearly
- **Transparent** - Always show current balances and deposit amounts
- **Safety-focused** - Emphasize verification of amounts before confirming

## Vocabulary & Language

### Preferred Terms

- "deposit" (not "stake" or "lock")
- "withdraw" (not "unstake" or "unlock")
- "preregistration" (official program terminology)
- "USTC-cb" (correct token symbol)

### Avoid These Terms

- "stake/unstake" (this is a deposit/withdraw system)
- "lock/unlock" (tokens are not locked)
- Generic terms like "tokens" when referring to USTC-cb specifically

## Communication Patterns

### For Transaction Confirmations

1. Clear summary of deposit/withdraw action
2. All relevant amounts
3. Gas estimate
4. Simple yes/no confirmation

### When User Says "ALL" for Deposit

Return parameters with amount: "ALL" (exact string). The system resolves this to the user's USTC-cb balance.

### When User Says "ALL" for Withdraw

Return parameters with amount: "ALL" (exact string). The system resolves this to the user's deposit amount.

## Error Handling

### When Insufficient Balance for Deposit

"You don't have enough USTC-cb for this deposit."

### When Zero Balance

"You have 0 USTC-cb balance."

### When Zero Deposit

"You have 0 USTC-cb deposited."

## Parameters Required

For deposit/withdraw operations, the LLM **must** return:
- `amount`: The amount to deposit/withdraw (can be "ALL")
- `token_address`: Must be "0xA4224f910102490Dc02AAbcBc6cb3c59Ff390055"

For getUserDeposit:
- `user`: The wallet address to check (use the user's active wallet address from context)
```

---

## Code Changes Required

### Step 5: Modify `app/base/app_session.py`

The current `prepare_write_call()` does NOT handle:
1. "ALL" amount resolution
2. Default parameter injection

**Add the following logic at the start of `prepare_write_call()` (after line 211):**

```python
async def prepare_write_call(
    self,
    method_name: str,
    parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Prepare a write (state-changing) contract call for confirmation."""
    try:
        # --- BEGIN NEW CODE: USTC Preregister specific handling ---
        if self.app_name == "ustc_preregister":
            USTC_CB_ADDRESS = "0xA4224f910102490Dc02AAbcBc6cb3c59Ff390055"
            
            # Inject token_address if not provided
            if method_name in ["deposit", "withdraw"] and "token_address" not in parameters:
                parameters["token_address"] = USTC_CB_ADDRESS
            
            # Handle "ALL" amount resolution
            amount_value = parameters.get("amount", "")
            if isinstance(amount_value, str) and amount_value.upper() == "ALL":
                if method_name == "deposit":
                    # Get USTC-cb balance (returns human-readable Decimal)
                    balance_info = await wallet_manager.get_token_balance(
                        USTC_CB_ADDRESS,
                        self.wallet_info["address"]
                    )
                    if balance_info["balance"] <= 0:
                        raise ValueError("You have 0 USTC-cb balance. Cannot deposit.")
                    # Convert to string for parameter processing
                    parameters["amount"] = str(balance_info["balance"])
                    
                elif method_name == "withdraw":
                    # Get user deposit from contract (returns raw uint256)
                    deposit_raw = await self.handle_view_call(
                        "getUserDeposit",
                        {"user": self.wallet_info["address"]}
                    )
                    if deposit_raw <= 0:
                        raise ValueError("You have 0 USTC-cb deposited. Cannot withdraw.")
                    
                    # Convert raw to human-readable
                    from services.tokens import token_manager
                    token_info = await token_manager.get_token_info(USTC_CB_ADDRESS)
                    decimals = token_info['decimals'] if token_info else 18
                    human_amount = deposit_raw / (10 ** decimals)
                    parameters["amount"] = str(human_amount)
        # --- END NEW CODE ---
        
        # Find method config (existing code continues...)
        method_config = self._find_method_config(method_name, "write")
        # ... rest of existing code
```

### Step 6: Modify `commands/app.py` - Add View Result Formatting

**Update the `format_view_result()` function (around line 436) to handle USTC Preregister:**

```python
async def format_view_result(method_name: str, result: Any, session: AppSession) -> str:
    """Format the result of a view call for display."""
    
    try:
        # --- BEGIN NEW CODE: USTC Preregister formatting ---
        if session.app_name == "ustc_preregister":
            USTC_CB_ADDRESS = "0xA4224f910102490Dc02AAbcBc6cb3c59Ff390055"
            
            if method_name == "getTotalDeposits":
                from services.tokens import token_manager
                token_info = await token_manager.get_token_info(USTC_CB_ADDRESS)
                decimals = token_info['decimals'] if token_info else 18
                formatted = result / (10 ** decimals)
                return f"📊 **Total Deposits:** {formatted:,.6f} USTC-cb"
                
            elif method_name == "getUserCount":
                return f"👥 **Total Users:** {result:,}"
                
            elif method_name == "getUserDeposit":
                from services.tokens import token_manager
                token_info = await token_manager.get_token_info(USTC_CB_ADDRESS)
                decimals = token_info['decimals'] if token_info else 18
                formatted = result / (10 ** decimals)
                return f"💼 **Your Deposit:** {formatted:,.6f} USTC-cb"
        # --- END NEW CODE ---
        
        # Existing swap formatting...
        if method_name == "getAmountsOut":
            # ... existing code
```

### Step 7: Modify `commands/app.py` - Add Welcome Message

**In `start_specific_app()` (around line 145), add USTC Preregister welcome:**

```python
if app_name == "swap":
    welcome_msg += (
        "I can help you swap tokens on TidalDex! Here are some things you can try:\n\n"
        # ... existing swap content
    )
elif app_name == "ustc_preregister":
    welcome_msg += (
        "I can help you interact with the USTC+ Preregister program! Here are some things you can try:\n\n"
        "• \"show global stats\" - View total deposits and user count\n"
        "• \"how much have I deposited?\" - Check your deposit amount\n"
        "• \"deposit ALL\" - Deposit your entire USTC-cb balance\n"
        "• \"deposit 100\" - Deposit a specific amount\n"
        "• \"withdraw ALL\" - Withdraw your entire deposit\n\n"
        "What would you like to do?"
    )
else:
    welcome_msg += "How can I help you today?"
```

**Also add the same in `start_specific_app_from_callback()` (around line 208).**

### Step 8: Update LLM System Prompt (Optional Enhancement)

**In `app/base/llm_interface.py`, the `_build_system_prompt()` method can be enhanced to add app-specific instructions. Add after line 192:**

```python
# App-specific instructions
if session.app_name == "ustc_preregister":
    system_prompt += """

## USTC Preregister Specific Instructions

- For deposit/withdraw operations, ALWAYS include `token_address: "0xA4224f910102490Dc02AAbcBc6cb3c59Ff390055"` in parameters
- When user says "deposit ALL" or "withdraw ALL", set amount to the string "ALL" exactly
- For getUserDeposit, use the user's wallet address from context as the `user` parameter
"""
```

---

## Parameter Flow Analysis

### Current `process_parameters()` Behavior (transaction_manager.py)

The function iterates over `raw_params.items()`, meaning:
- It only processes parameters that are **already present** in raw_params
- **Default values in config are NOT automatically applied**
- This is why `token_address` must be explicitly set

### Token Resolution in `_resolve_parameter_reference()`

Supports:
- `"BNB"` → returns `"BNB"`
- `"path[0]"`, `"path[-1]"`, `"path[N]"` → indexes into path array
- Direct parameter names → `raw_params.get(param_ref, "")`

Since we use `"token_param": "token_address"`, the token address will be resolved from `raw_params["token_address"]`.

### Token Approval Flow

When `requires_token_approval: true`:
1. `call_write_method()` calls `_ensure_token_approval()`
2. Finds `token_amount_pairs` with direction "input", "payment", or "stake"
3. Resolves token from `token_param` via `_resolve_parameter_reference()`
4. Checks allowance and approves if needed

For deposit, this correctly approves the USTC-cb token for the preregister contract.

---

## Environment Setup

Add to `.env`:
```
USTC_PREREGISTER_ADDRESS=<contract_address>
```

---

## Testing Checklist

- [ ] App loads correctly from config.json
- [ ] View calls work: getTotalDeposits, getUserCount, getUserDeposit
- [ ] View results display with correct formatting and decimals
- [ ] Deposit with specific amount works
- [ ] Deposit with "ALL" resolves to correct balance
- [ ] Withdraw with specific amount works
- [ ] Withdraw with "ALL" resolves to correct deposit
- [ ] Token approval is triggered for deposit
- [ ] Error handling for zero balance/deposit
- [ ] Welcome message displays correctly

---

## Summary of Files to Create/Modify

### Create:
1. `app/apps/ustc_preregister/abi/USTCPreregister.json` - Copy from `ABI/`
2. `app/apps/ustc_preregister/config.json` - App configuration
3. `app/apps/ustc_preregister/STYLE.md` - Style guide for LLM

### Modify:
1. `app/base/app_session.py` - Add "ALL" resolution and token_address injection
2. `commands/app.py` - Add view result formatting and welcome message
3. `app/base/llm_interface.py` (optional) - Add app-specific LLM instructions
