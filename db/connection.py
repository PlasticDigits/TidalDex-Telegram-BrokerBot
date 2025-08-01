"""
Database connection management for PostgreSQL.
Provides functions to create, test, and manage PostgreSQL database connections.

This module is a wrapper around the PostgreSQL database connection implementation.
"""
from typing import Any, Dict, List, Optional, Union, Callable, TypeVar, cast
from functools import wraps

# Define F type variable for better type checking with decorators
F = TypeVar('F', bound=Callable[..., Any])

# Import all functions from the PostgreSQL connection module
from db.connections.connection import (
    create_connection,
    get_connection,
    close_connection,
    get_db_connection,
    execute_query,
    test_connection,
    init_db,
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
    'retry_decorator'
]

# Use PostgreSQL retry decorator
if retry_on_db_error is not None:
    retry_decorator = retry_on_db_error
else:
    # Fallback decorator if retry_on_db_error is not available
    def retry_decorator(max_attempts: int = 5, initial_wait: float = 0.1) -> Callable[[F], F]:
        def decorator(func: F) -> F:
            @wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                return func(*args, **kwargs)
            return cast(F, wrapper)
        return decorator 