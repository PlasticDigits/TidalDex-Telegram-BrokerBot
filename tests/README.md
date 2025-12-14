# Tests

Test suite for TidalDex Telegram Broker Bot.

## Running Tests

### With pytest (recommended)

Run all unit tests (no database/wallet/API required):

```bash
python3 -m pytest tests/ -v --ignore=tests/test_llm_schema.py
```

Run only API tests (requires OPENAI_API_KEY):

```bash
python3 -m pytest tests/test_llm_schema.py -v
```

### Individual Test Files

Each test file can also be run directly:

```bash
python3 tests/test_llm_response_parsing.py
python3 tests/test_app_manager_validation.py
python3 tests/test_llm_edge_cases.py
python3 tests/test_llm_system_prompt.py
python3 tests/test_ustc_preregister_config.py
python3 tests/test_ustc_preregister_normalization.py
python3 tests/test_ustc_preregister_view_formatting.py
```

### USTC Preregister Integration Tests

Run unit tests (no external dependencies):
```bash
python3 -m pytest tests/test_ustc_preregister_config.py tests/test_ustc_preregister_normalization.py tests/test_ustc_preregister_view_formatting.py -v
```

Run live RPC tests (requires BSC RPC):
```bash
# Option 1: Set in .env file (recommended)
# Add RUN_LIVE_TESTS=true to .env
python3 -m pytest tests/test_ustc_preregister_integration.py::TestUSTCPreregisterLiveRPC -v

# Option 2: Set via environment variable
RUN_LIVE_TESTS=true python3 -m pytest tests/test_ustc_preregister_integration.py::TestUSTCPreregisterLiveRPC -v
```

Run live OpenAI API tests (requires OpenAI API key):
```bash
# Option 1: Set in .env file (recommended)
# Add RUN_LIVE_OPENAI_TESTS=1 and OPENAI_API_KEY=sk-... to .env
python3 -m pytest tests/test_ustc_preregister_integration.py::TestUSTCPreregisterLiveLLM -v

# Option 2: Set via environment variables
RUN_LIVE_OPENAI_TESTS=1 OPENAI_API_KEY=sk-... python3 -m pytest tests/test_ustc_preregister_integration.py::TestUSTCPreregisterLiveLLM -v
```

Run all integration tests:
```bash
# Option 1: Set in .env file (recommended)
# Add RUN_LIVE_TESTS=true, RUN_LIVE_OPENAI_TESTS=1, and OPENAI_API_KEY=sk-... to .env
python3 -m pytest tests/test_ustc_preregister_integration.py -v

# Option 2: Set via environment variables
RUN_LIVE_TESTS=true RUN_LIVE_OPENAI_TESTS=1 OPENAI_API_KEY=sk-... python3 -m pytest tests/test_ustc_preregister_integration.py -v
```

**Note:** Integration tests automatically load environment variables from `.env` file in the project root using `dotenv`. You can set variables in `.env` or override them via environment variables.

## Test Categories

### Unit Tests (No External Dependencies)

These tests run without database, wallet, or external API access:

| File | Tests | Description |
|------|-------|-------------|
| `test_llm_response_parsing.py` | 12 | LLM response parsing and validation |
| `test_app_manager_validation.py` | 20 | LLM app configuration validation |
| `test_llm_edge_cases.py` | 27 | Edge cases for LLM interface |
| `test_llm_system_prompt.py` | 12 | System prompt building |
| `test_ustc_preregister_config.py` | 15 | USTC Preregister app config validation |
| `test_ustc_preregister_normalization.py` | 10 | USTC Preregister parameter normalization (mocked) |
| `test_ustc_preregister_view_formatting.py` | 3 | USTC Preregister view result formatting |

### API Tests (Requires External API)

| File | Tests | Description |
|------|-------|-------------|
| `test_llm_schema.py` | 2 | OpenAI API integration and schema validation |

**Requirements:**
- `OPENAI_API_KEY` must be set in your `.env` file
- Internet connection for API calls

### Integration Tests (Requires Live Services)

| File | Tests | Description |
|------|-------|-------------|
| `test_ustc_preregister_integration.py` | 15+ | USTC Preregister live RPC and OpenAI API tests |

**Requirements:**
- `RUN_LIVE_TESTS=true` for RPC tests
- `RUN_LIVE_OPENAI_TESTS=1` and `OPENAI_API_KEY` for LLM tests
- `USTC_PREREGISTER_ADDRESS` env var (or uses default)
- Internet connection for BSC RPC and OpenAI API calls

## Test Coverage

### LLM Response Parsing (`test_llm_response_parsing.py`)

- ✅ Chat response parsing
- ✅ View call response with contract_call
- ✅ Write call response with contract_call
- ✅ Missing contract_call validation
- ✅ Missing required fields in contract_call
- ✅ Missing response_type and message validation
- ✅ Invalid JSON handling
- ✅ Swap-specific response formats

### LLM App Manager Validation (`test_app_manager_validation.py`)

- ✅ Missing ABI file detection
- ✅ Missing method name/inputs validation
- ✅ Valid configuration passing
- ✅ Nonexistent app handling
- ✅ Missing environment variables
- ✅ Style guide loading (existing, missing, empty)

### USTC Preregister Tests

**Config Validation (`test_ustc_preregister_config.py`):**
- ✅ Config file existence and JSON validity
- ✅ Required fields validation
- ✅ Contracts section configuration
- ✅ ABI file existence and validity
- ✅ View and write methods configuration
- ✅ Parameter processing rules
- ✅ Manager validation integration

**Normalization (`test_ustc_preregister_normalization.py`):**
- ✅ Token address enforcement
- ✅ Invalid token rejection
- ✅ "ALL" amount resolution for deposits
- ✅ "ALL" amount resolution for withdrawals
- ✅ Zero balance/deposit error handling
- ✅ User address auto-injection
- ✅ Parameter order normalization

**Integration (`test_ustc_preregister_integration.py`):**
- ✅ Live RPC view calls (getTotalDeposits, getUserCount, getUserDeposit)
- ✅ Live RPC normalization (deposit/withdraw ALL)
- ✅ Live OpenAI API chat responses
- ✅ Live OpenAI API view call generation
- ✅ Live OpenAI API write call generation
- ✅ End-to-end flow (LLM -> RPC -> formatting)
- ✅ Multiple contracts validation
- ✅ Empty contracts/methods handling
- ✅ Special characters in method names

### LLM Edge Cases (`test_llm_edge_cases.py`)

- ✅ Schema loading (missing file, invalid JSON, unwrapped schema)
- ✅ Fallback schema format
- ✅ Empty/whitespace messages
- ✅ Unicode and emoji handling
- ✅ Extra fields in responses
- ✅ Very long messages
- ✅ Null values in contract_call
- ✅ Unknown response types
- ✅ Nested parameters
- ✅ Empty choices array
- ✅ Missing message/content fields
- ✅ Multiple choices (uses first)
- ✅ OpenAI refusal responses
- ✅ Numeric and scientific notation values
- ✅ Boolean/wrong type response_type
- ✅ Escaped quotes in content

### LLM System Prompt (`test_llm_system_prompt.py`)

- ✅ No token balances
- ✅ No view/write methods
- ✅ Style guide inclusion
- ✅ Token balance formatting
- ✅ Multiple methods
- ✅ Missing wallet address
- ✅ Method input parameters
- ✅ Special characters in descriptions
- ✅ Many token balances
- ✅ Long style guides

## Compatibility

These tests verify that:

1. ✅ Schema loads correctly with wrapper structure (`name`, `strict`, `schema`)
2. ✅ Valid responses parse correctly
3. ✅ Invalid responses are caught and handled gracefully
4. ✅ Swap-related responses (view_call/write_call) work correctly
5. ✅ The validation logic correctly enforces `contract_call` requirement
6. ✅ App configuration validation is comprehensive
7. ✅ Edge cases are handled gracefully without crashing
