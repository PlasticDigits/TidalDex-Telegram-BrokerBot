# Database Module

This directory contains the database abstraction layer for the TidalDEX Telegram Trading bot.

## Structure

The database module is structured as follows:

- `__init__.py`: Exports public functions and initializes the database
- `connection.py`: Database connection handling and core functionality
- `wallet.py`: Wallet-related database operations
- `mnemonic.py`: Mnemonic seed phrase database operations
- `utils.py`: Utility functions for encryption/decryption

## Database Schema

The database uses SQLite with the following tables:

### Users Table

```sql
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    account_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    settings TEXT
);
```

### Mnemonics Table

```sql
CREATE TABLE IF NOT EXISTS mnemonics (
    user_id TEXT PRIMARY KEY,
    mnemonic TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);
```

### Wallets Table

```sql
CREATE TABLE IF NOT EXISTS wallets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    address TEXT NOT NULL,
    private_key TEXT,
    path TEXT,
    name TEXT DEFAULT 'Default',
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    UNIQUE(user_id, name)
);
```

## Security

All sensitive data (private keys and mnemonics) are encrypted before storage using Fernet symmetric encryption with a user-specific key. The encryption uses a random salt for each encryption operation and PBKDF2 key derivation.

### User ID Protection

For enhanced security, all user IDs are irreversibly hashed using SHA-256 before being stored in the database. This means:

1. Actual Telegram user IDs are never stored in the database
2. Even with database access, it's computationally infeasible to determine the original user IDs
3. Data lookup is performed using the same hashing algorithm, ensuring consistent access

This approach provides an additional layer of security and privacy for users.

## Usage

```python
import db

# Initialize the database
db.init_db()

# Get a user's wallet
wallet = db.get_user_wallet(user_id)

# Save a wallet
db.save_user_wallet(user_id, wallet_data, wallet_name="Default", pin=None)

# Save a mnemonic
db.save_user_mnemonic(user_id, mnemonic, pin=None)

# Close connection when done
db.close_connection()
```
