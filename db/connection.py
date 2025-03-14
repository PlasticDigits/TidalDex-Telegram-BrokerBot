"""
Database connection management.
Provides functions to create, test, and manage database connections.

This module is a wrapper around the actual database connection implementation.
It imports all functions from the selected database driver (sqlite3 or postgresql).
"""
from typing import Any, Dict, List, Optional, Union, Callable, TypeVar, cast
from functools import wraps

# Define F type variable for better type checking with decorators
F = TypeVar('F', bound=Callable[..., Any])

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

# Define exports explicitly
__all__ = [
    'create_connection',
    'get_connection', 
    'close_connection',
    'get_db_connection',
    'execute_query',
    'test_connection',
    'init_db',
    'DB_TYPE',
    'retry_decorator'
]

# For backward compatibility
if DB_TYPE == 'sqlite3' and retry_on_db_lock is not None:
    retry_decorator = retry_on_db_lock
elif DB_TYPE == 'postgresql' and retry_on_db_error is not None:
    retry_decorator = retry_on_db_error
else:
    # Fallback decorator if neither is available
    def retry_decorator(max_attempts: int = 5, initial_wait: float = 0.1) -> Callable[[F], F]:
        def decorator(func: F) -> F:
            @wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                return func(*args, **kwargs)
            return cast(F, wrapper)
        return decorator 