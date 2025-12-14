# USTC+ Preregister LLM App Implementation Plan (Updated)

## Overview

This document updates the original plan for the `ustc_preregister` conversational `/llm_app` after significant refactors in the LLM app framework.

The goal is still the same: let users interact with the USTC Preregister smart contract to:

- View global stats
- View their deposit for the active wallet
- Deposit / withdraw USTC-cb, including `"ALL"` shorthand

## What changed in the codebase (critical)

The current LLM app system is centered around these modules:

- `app/base/llm_app_manager.py`: discovers `app/llm_apps/*/config.json` and creates `LLMAppSession`.
- `app/base/llm_app_session.py`: owns wallet context, performs view calls, prepares write calls, stores a `PendingTransaction`.
- `services/transaction/transaction_manager.py`: converts parameters, builds previews, validates token pairs, runs approvals, executes view/write calls.
- `commands/llm_app.py`: Telegram conversation flow, welcome messages, and `format_view_result()`.
- `app/base/llm_interface.py`: system prompt building + OpenAI response parsing (JSON schema is `app/schemas/app_json_schema.json`).

Important behavioral details that affect this app design:

1. **Defaults are now applied**: `TransactionManager.process_parameters()` applies `parameter_processing.*.default` *for missing required inputs* (i.e., those listed in the method’s `inputs` array).
2. **Token validation + approvals read from `raw_params`**:
   - `TransactionFormatter.validate_token_amount_pairs()` resolves token refs from `raw_params`.
   - `TransactionManager._ensure_token_approval()` resolves token refs from `raw_params`.
   - Therefore **`token_address` must be present in `raw_params`** for deposit/withdraw previews and execution.
3. **`process_parameters()` order sensitivity**:
   - When converting a `token_amount` with `get_decimals_from: "token_address"`, `token_address` must already be present in the in-progress processed dict.
   - If the LLM returns `{ "amount": "10", "token_address": "0x..." }` in that order, conversion may see a missing `token_address`.
   - We should make this robust in code by **normalizing parameter dict order** and/or **using raw integer amounts when resolving `"ALL"`** (ints bypass human conversion in `process_parameters()`).

## App requirements

### 1) Global stats (view calls)

- `getTotalDeposits() -> uint256`: total deposited amount (raw units)
- `getUserCount() -> uint256`: number of users

### 2) Wallet stats (view call)

- `getUserDeposit(address user) -> uint256`: deposit for active wallet

### 3) Deposit / withdraw (write calls)

- `deposit(uint256 amount)`
  - `"ALL"` means “deposit my entire USTC-cb wallet balance”
- `withdraw(uint256 amount)`
  - `"ALL"` means “withdraw my entire deposited amount”

## Constants / configuration

- **USTC-cb token address (constant enforced in code)**: `0xA4224f910102490Dc02AAbcBc6cb3c59Ff390055`
- **Contract address env var**: `USTC_PREREGISTER_ADDRESS`

## Implementation steps (updated for current repo)

### Step 1: Create app directory structure

```
app/llm_apps/ustc_preregister/
├── abi/
│   └── USTCPreregister.json
├── config.json
├── STYLE.md
└── IMPLEMENTATION.md
```

### Step 2: Copy ABI file

Copy:

- Source: `ABI/USTCPreregister.json`
- Destination: `app/llm_apps/ustc_preregister/abi/USTCPreregister.json`

### Step 3: Create `config.json` (compatible with TransactionManager)

Key points for this repo:

- Keep contract function `inputs` aligned to the actual ABI.
- Include a `token_amount_pairs` entry for deposit so approvals can be computed.
- Include `token_address` in `raw_params` (injected by session) even though the contract method doesn’t take it as an input.

Recommended config (shape mirrors `app/llm_apps/swap/config.json`):

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
        "description": "Get total deposits across all users (raw uint256)",
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
        "description": "Get the deposited amount for a wallet address (raw uint256)",
        "inputs": ["user"],
        "contract": "preregister"
      }
    ],
    "write": [
      {
        "name": "deposit",
        "description": "Deposit USTC-cb into the preregister contract",
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
        "description": "Withdraw USTC-cb from the preregister contract",
        "inputs": ["amount"],
        "contract": "preregister",
        "requires_token_approval": false,
        "gas_estimate": "medium",
        "token_amount_pairs": [
          {
            "token_param": "token_address",
            "amount_param": "amount",
            "direction": "output",
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

Notes:

- `direction: "payment"` is important because approvals look for `direction` in `["input", "payment", "stake"]`.
- For withdraw, the direction is informational only (approval is disabled).
- `token_address` is not a contract input. It exists to enable:
  - token pair validation (`validate_token_amount_pairs()`)
  - token approvals (`_ensure_token_approval()`)
  - decimals conversion (`get_decimals_from: "token_address"`)

### Step 4: Create `STYLE.md`

Keep the existing style guide intent, but update the “requirements” wording:

- The LLM **should** include `token_address` and `"ALL"` when relevant.
- The system will also **enforce and inject** `token_address` for safety.

### Step 5: Update `LLMAppSession` to normalize parameters and resolve `"ALL"`

File: `app/base/llm_app_session.py`

Add a small app-specific normalization step that runs **before** calling:

- `transaction_manager.prepare_transaction_preview()` (write calls)
- `transaction_manager.process_parameters()` (view calls, for `getUserDeposit`)

Required behaviors:

- **Enforce token**:
  - For `deposit`/`withdraw`, always set `token_address` to the USTC-cb constant.
  - If the LLM supplies a different token address, reject with a clear error (security).
- **Fix order sensitivity**:
  - Rebuild the dict so `token_address` is inserted first (helps `get_decimals_from`).
- **Resolve `"ALL"` robustly**:
  - For `deposit` with `"ALL"`:
    - call `wallet_manager.get_token_balance(USTC_CB_ADDRESS, wallet_address)`
    - set `parameters["amount"] = <raw_balance int>` (not a string), so `process_parameters()` won’t re-convert it.
  - For `withdraw` with `"ALL"`:
    - call `self.handle_view_call("getUserDeposit", {"user": wallet_address})`
    - set `parameters["amount"] = <deposit_raw int>`
  - Handle zero amounts with user-friendly errors.
- **Optionally inject `user`**:
  - For `getUserDeposit` view calls, if `user` is missing, set it to the active wallet address (this improves robustness when the model forgets).

Why this belongs in session code (not config):

- `validate_token_amount_pairs()` and `_ensure_token_approval()` both require `token_address` in **raw params**.
- `"ALL"` requires live wallet/contract queries, which must be done in Python, not by config defaults.

### Step 6: Update Telegram UX: welcome message + view formatting

File: `commands/llm_app.py`

1) **Welcome message**

Update `get_llm_app_welcome_message()` to include `ustc_preregister` examples similar to `swap`.

2) **View formatting**

Update `format_view_result()` to handle the three view methods for this app:

- `getTotalDeposits`: display as human USTC-cb using token decimals
- `getUserCount`: format as integer with commas
- `getUserDeposit`: display as “Your Deposit” in human USTC-cb using token decimals

Implementation notes:

- Use `token_manager.get_token_info(USTC_CB_ADDRESS)` to get decimals.
- Treat contract results as raw `uint256`.
- Be defensive: if token info lookup fails, fall back to 18 decimals.

### Step 7 (optional but recommended): Add app-specific instructions to the system prompt

File: `app/base/llm_interface.py`

In `_build_system_prompt()`, add a small `if session.llm_app_name == "ustc_preregister": ...` block with explicit guidance:

- For deposit/withdraw, include `"amount"` and (optionally) `"token_address"` (even though code injects it)
- When user says “ALL”, set `"amount": "ALL"` exactly
- For `getUserDeposit`, include `"user"` as the active wallet address

This reduces normalization work and improves model consistency, but **the session-layer enforcement is still required** for correctness and security.

## Environment setup

Add to `.env`:

```
USTC_PREREGISTER_ADDRESS=<deployed_contract_address>
```

Also ensure existing required env vars are configured (e.g., RPC endpoints, token list URL, etc.) so token metadata calls are reliable.

## Robust testing plan (automated)

This app touches both config-driven execution and app-specific normalization logic. The test strategy should cover:

### A) Config validation tests (unit)

Goal: ensure the app is discoverable and passes manager validation.

- Add a new unit test (pattern matches `tests/test_app_manager_validation.py`) that:
  - loads/validates the real `ustc_preregister/config.json`
  - asserts `validate_llm_app_config("ustc_preregister")` returns no errors *when env vars are set in the test environment*
  - asserts ABI file exists at `app/llm_apps/ustc_preregister/abi/USTCPreregister.json`

### B) Session normalization + `"ALL"` resolution (unit, async)

Goal: prove `LLMAppSession.prepare_write_call()` is robust regardless of LLM parameter ordering.

Test cases (mock external calls):

- **Deposit ALL**
  - Input: `{"amount": "ALL"}` (no `token_address`)
  - Mock `wallet_manager.get_token_balance()` to return a non-zero raw balance.
  - Expect:
    - preview succeeds
    - `pending_transaction.raw_params["token_address"]` exists and matches the constant
    - `pending_transaction.raw_params["amount"]` is an `int` raw amount
- **Withdraw ALL**
  - Input: `{"amount": "ALL"}` (no `token_address`)
  - Mock `session.handle_view_call("getUserDeposit", ...)` to return non-zero int
  - Expect raw int amount and injected token address in pending transaction
- **Deposit ALL with zero balance**
  - Mock balance raw = 0
  - Expect a user-friendly exception
- **Withdraw ALL with zero deposit**
  - Mock deposit raw = 0
  - Expect a user-friendly exception
- **Wrong token address supplied**
  - Input includes `token_address` != USTC constant
  - Expect rejection (security)
- **Ordering stress**
  - Input: `{"amount": "1.5", "token_address": "<USTC>"}` and reverse order
  - Ensure normalization makes conversion deterministic.

### C) View result formatting (unit, async)

Goal: confirm user-facing output is correct and stable.

- Patch `token_manager.get_token_info()` to return various decimals
- Validate formatted strings for:
  - `getTotalDeposits` (decimals conversion)
  - `getUserCount` (commas)
  - `getUserDeposit` (decimals conversion)

### D) TransactionManager integration surface (fast integration tests)

Goal: ensure config and parameter_processing produce correct `processed_params`.

- Patch `transaction_manager.web3` to `tests.mocks.mock_web3.MockWeb3` or MagicMock (see token resolution tests).
- Patch ABI loading / contract calls so no RPC is required.
- Verify:
  - `prepare_transaction_preview()` produces `processed_params["amount"]` as int
  - preview includes a valid `summary` and gas estimate object

### E) Manual / staging checklist (non-automated)

Do a quick end-to-end on a test wallet and the real contract:

- Start: `/llm_app ustc_preregister`
- View:
  - “show global stats”
  - “how much have I deposited?”
- Deposit:
  - “deposit 1” (verify preview, approval, tx)
  - “deposit ALL” (verify wallet balance resolution)
- Withdraw:
  - “withdraw 1”
  - “withdraw ALL” (verify contract deposit resolution)
- Error UX:
  - try deposit with no balance
  - try withdraw with no deposit

## Summary of files to create/modify

### Create

- `app/llm_apps/ustc_preregister/abi/USTCPreregister.json`
- `app/llm_apps/ustc_preregister/config.json`
- `app/llm_apps/ustc_preregister/STYLE.md`

### Modify

- `app/base/llm_app_session.py`: app-specific normalization + `"ALL"` resolution + safety checks
- `commands/llm_app.py`: welcome text + `format_view_result()` formatting
- `app/base/llm_interface.py`: optional app-specific system prompt guidance

### Add tests

- New `tests/test_ustc_preregister_*.py` files covering:
  - config validation
  - session `"ALL"` normalization
  - view formatting
