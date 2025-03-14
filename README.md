# TidalDex Telegram Broker Bot

A Python Telegram bot for managing crypto wallets and trading on decentralized exchanges (DEX).

## Features

- Create and manage multiple crypto wallets
- Send and receive crypto assets
- Check wallet balances
- Export private keys (with PIN protection)
- Trade on decentralized exchanges
- Backup and recovery options
- PIN protection for sensitive operations

## Installation

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and configure your environment variables
4. Run the bot: `python main.py`

## Usage

Start a conversation with the bot on Telegram and use the following commands:

- `/start` - Begin interaction with the bot
- `/help` - View available commands
- `/wallet` - Manage your wallets
- `/send` - Send crypto to another address
- `/balance` - Check your wallet balance
- `/receive` - Get your wallet address for receiving funds
- `/backup` - Create a backup of your wallet
- `/lock` - Lock your wallet by clearing the stored PIN

## Type checking

Use `mypy main.py --strict` for type checking.

## Database

The TidalDex Telegram Broker Bot supports two database backends:

### Database Options

1. **SQLite** (Default)

   - Lightweight, file-based database
   - Perfect for personal use or small deployments
   - No additional setup required
   - Data stored in `data/tidaldex.db` by default

2. **PostgreSQL**
   - Robust, scalable database for production environments
   - Better performance with many concurrent users
   - Supports advanced features like replication and backups
   - Requires a PostgreSQL server

### Configuration

Database settings are configured in the `.env` file:

```
# Database configuration
DB_TYPE=sqlite3        # Options: sqlite3, postgresql
DB_NAME=tidaldex.db    # Database name or path for SQLite

# PostgreSQL specific configurations (only needed if DB_TYPE=postgresql)
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=postgres
```

### Database Schema

The database includes tables for:

- Users: Stores user information and settings
- Mnemonics: Securely stores encrypted seed phrases
- Wallets: Manages wallet addresses, encrypted private keys, and metadata
- PIN attempts: Tracks PIN verification attempts for security

### Security Features

- All sensitive data (private keys and mnemonics) are encrypted using Fernet symmetric encryption
- User IDs are hashed using SHA-256 before storage for enhanced privacy
- PIN protection with configurable expiration time
- Automatic retry mechanism for handling database locks

## License

This project is licensed under the GNU General Public License v3.0 (GPL-3.0). This means:

- You are free to use, modify, and distribute this software
- If you distribute modified versions, you must release the source code
- All derivatives must also be licensed under GPL-3.0
- There is no warranty for this software

For the full license text, see the [LICENSE](LICENSE) file.

Copyright (C) 2025

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.
