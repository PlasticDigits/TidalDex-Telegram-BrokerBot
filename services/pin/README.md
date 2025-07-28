# PIN Management Service

This service provides centralized PIN management for the TidalDex Telegram Bot.

## Overview

The PINManager handles all PIN-related operations including verification, storage, retrieval, and expiration management. It's designed as a singleton service to ensure consistency across the application.

## Key Features

- **Centralized PIN Storage**: All PIN operations go through a single service
- **Automatic Expiration**: PINs expire after a configurable time (default: 1 hour)
- **Thread-Safe Operations**: Safe for concurrent access
- **Memory-Based Storage**: PINs are stored in memory for security
- **Background Cleanup**: Expired PINs are automatically cleaned up
- **Data Re-encryption**: Automatically re-encrypts all sensitive data when PIN is set/changed

## Usage

```python
from services.pin.PINManager import pin_manager

# Check if user needs PIN
if pin_manager.needs_pin(user_id):
    # Get cached PIN if available
    pin = pin_manager.get_pin(user_id)

    if not pin:
        # PIN verification needed
        if pin_manager.verify_pin(user_id, user_input_pin):
            pin = pin_manager.get_pin(user_id)  # Now available
```

## PIN Setting and Data Re-encryption

When a user sets a PIN using `pin_manager.set_pin(user_id, pin)`, the service automatically:

1. **Retrieves existing data** with the old PIN (if any)
2. **Sets the new PIN** in the database
3. **Re-encrypts all sensitive data** with the new PIN:
   - User mnemonic phrases
   - Wallet private keys
   - **X account connection data** (access tokens, refresh tokens)
4. **Stores the PIN** in memory for immediate use

This ensures all encrypted data remains accessible and secure with the new PIN.

## Integration with X Account Management

The X account connection system uses PINManager to:

1. Retrieve verified PINs for decryption
2. Handle PIN-protected account data
3. Maintain consistent PIN state across navigation
4. **Re-encrypt X account data when PIN changes**

This ensures that users don't lose their connection status when navigating through the X account management interface.

## Recent Fix

Fixed issue where users would appear disconnected after successful X account connection when navigating back to the main menu. The fix involved:

1. **Enhanced `has_x_account_connection()`**: Now accepts optional PIN parameter
2. **PINManager Integration**: Uses centralized PIN management instead of manual context handling
3. **Consistent PIN Retrieval**: All X account functions now use PINManager for PIN operations
4. **X Account Re-encryption**: Added X account data re-encryption to PIN setting process

This ensures that PIN-protected X account data can be properly validated throughout the user experience and remains accessible when PINs are changed.
