"""
Database connection management.
Provides functions to create, test, and manage database connections.

This module is a wrapper around the actual database connection implementation.
It imports all functions from the selected database driver (sqlite3 or postgresql).
"""

# Import all functions from the new connection module
from db.connections.connection import (
    create_connection,
    get_connection,
    close_connection,
    get_db_connection,
    execute_query,
    test_connection,
    init_db,
    DB_TYPE,
    retry_on_db_lock,
    retry_on_db_error
)

# For backward compatibility
if DB_TYPE == 'sqlite3' and retry_on_db_lock is not None:
    retry_decorator = retry_on_db_lock
elif DB_TYPE == 'postgresql' and retry_on_db_error is not None:
    retry_decorator = retry_on_db_error
else:
    # Fallback decorator if neither is available
    from functools import wraps
    def retry_decorator(max_attempts=5, initial_wait=0.1):
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            return wrapper
        return decorator 