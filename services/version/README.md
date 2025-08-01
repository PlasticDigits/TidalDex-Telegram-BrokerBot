# Version Management Service

This service provides centralized version management for the TidalDex Telegram Bot to prevent multiple instances from running simultaneously.

## Overview

The VersionManager uses a database-driven versioning system to ensure only one instance of the Telegram bot can run at a time. This prevents conflicts and polling issues that occur when multiple bot instances attempt to receive updates from Telegram.

## How It Works

### Startup Process

1. **Database Connection**: The service connects to the database on startup
2. **Table Creation**: Creates an `application` table if it doesn't exist
3. **Version Check**: Checks for existing version in the database
4. **Version Increment**: If version exists, increments it; otherwise sets to 1
5. **Version Storage**: Stores the new version and remembers it for this instance

### Runtime Monitoring

- When Telegram polling fails (especially with "Conflict" errors), the service checks if the current instance's version is still the latest in the database
- If another instance has started and incremented the version, this instance gracefully shuts down
- This prevents multiple instances from fighting over Telegram updates

### Database Schema

```sql
-- Application table for version management and instance control
CREATE TABLE IF NOT EXISTS application (
    id INTEGER PRIMARY KEY,
    version INTEGER NOT NULL,
    updated_at INTEGER DEFAULT (current timestamp)
);
```

## Usage

```python
from services.version import version_manager

# Initialize version on startup
if not version_manager.initialize_version():
    logger.error("Failed to initialize version")
    sys.exit(1)

# Check if current version is still valid
if not version_manager.is_version_current():
    logger.warning("Another instance has started, shutting down")
    graceful_shutdown()

# Get current version
version = version_manager.get_current_version()
```

## Integration with Main Application

The version manager is integrated into `main.py`:

1. **Startup**: Version is initialized after database initialization
2. **Error Handling**: Version is checked when polling fails
3. **Shutdown**: Version cleanup is performed during graceful shutdown

## Key Features

- **Singleton Pattern**: Ensures consistent version state across the application
- **Thread-Safe**: Safe for concurrent access with locks
- **Automatic Cleanup**: Handles cleanup on application shutdown
- **PostgreSQL Support**: Works with PostgreSQL database
- **Graceful Handling**: Provides clean shutdown when version conflicts are detected

## Benefits

1. **Prevents Conflicts**: Eliminates Telegram polling conflicts between instances
2. **Clean Deployment**: Enables clean deployment strategies without manual intervention
3. **Automatic Detection**: Automatically detects and resolves multiple instance scenarios
4. **Logging**: Provides clear logging for troubleshooting and monitoring
5. **Fail-Safe**: Fails safely by shutting down rather than causing conflicts

## Monitoring

The service provides comprehensive logging:

- Version initialization and increments
- Version mismatch detection
- Graceful shutdown triggers
- Error conditions and recovery

This makes it easy to monitor deployment and instance management in production environments.
