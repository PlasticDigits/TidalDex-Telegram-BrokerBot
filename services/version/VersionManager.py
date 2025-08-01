"""
VersionManager - Centralized service for managing application versioning.

This service provides version management to prevent multiple instances
of the Telegram bot from running simultaneously by using database versioning.
"""
import logging
import threading
import time
from typing import Optional
from db.connections.connection import execute_query, test_connection

logger = logging.getLogger(__name__)

class VersionManager:
    """
    Singleton service for centralized application version management.
    
    This class is responsible for managing application version numbers
    to prevent multiple bot instances from running simultaneously.
    """
    _instance: Optional['VersionManager'] = None
    _lock: threading.Lock = threading.Lock()
    _current_version: Optional[int] = None
    _initialized: bool = False
    
    def __new__(cls) -> 'VersionManager':
        with cls._lock:
            if cls._instance is None:
                logger.info("Creating VersionManager singleton instance")
                cls._instance = super(VersionManager, cls).__new__(cls)
            return cls._instance
    
    def _initialize(self) -> None:
        """Initialize the VersionManager instance."""
        if self._initialized:
            return
            
        self._current_version = None
        self._initialized = True
        logger.info("VersionManager initialized")
    
    def initialize_version(self) -> bool:
        """
        Initialize the application version on startup.
        
        This method:
        1. Checks if an application table exists, creates if not
        2. Gets the current version from database
        3. Increments the version and stores it
        4. Sets the current version for this instance
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not self._initialized:
                self._initialize()
            
            logger.info("Initializing application version...")
            
            # Test database connection first
            if not test_connection():
                logger.error("Database connection test failed")
                return False
            
            # Create application table if it doesn't exist
            self._create_application_table()
            
            # Get current version from database
            current_db_version = self._get_database_version()
            
            if current_db_version is None:
                # No version exists, set to 1
                new_version = 1
                logger.info("No existing version found, setting initial version to 1")
            else:
                # Increment existing version
                new_version = current_db_version + 1
                logger.info(f"Found existing version {current_db_version}, incrementing to {new_version}")
            
            # Store the new version in database
            if self._set_database_version(new_version):
                self._current_version = new_version
                logger.info(f"Application version set to {new_version}")
                return True
            else:
                logger.error("Failed to set version in database")
                return False
                
        except Exception as e:
            logger.error(f"Error initializing version: {e}")
            return False
    
    def _create_application_table(self) -> None:
        """Create the application table if it doesn't exist."""
        try:
            create_table_sql = """
                CREATE TABLE IF NOT EXISTS application (
                    id INTEGER PRIMARY KEY,
                    version INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )
            """
            
            result = execute_query(create_table_sql)
            logger.debug("Application table creation completed")
            
        except Exception as e:
            logger.error(f"Error creating application table: {e}")
            raise
    
    def _get_database_version(self) -> Optional[int]:
        """
        Get the current version from the database.
        
        Returns:
            Optional[int]: Current version number or None if not found
        """
        try:
            query = "SELECT version FROM application WHERE id = 1"
            result = execute_query(query, fetch='one')
            
            if result and 'version' in result:
                return int(result['version'])
            return None
            
        except Exception as e:
            logger.error(f"Error getting database version: {e}")
            return None
    
    def _set_database_version(self, version: int) -> bool:
        """
        Set the version in the database.
        
        Args:
            version: Version number to set
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            current_timestamp = int(time.time())
            
            # Check if record exists
            existing = execute_query("SELECT id FROM application WHERE id = 1", fetch='one')
            
            if existing:
                # Update existing record
                query = "UPDATE application SET version = %s, updated_at = %s WHERE id = 1"
                params = (version, current_timestamp)
            else:
                # Insert new record
                query = "INSERT INTO application (id, version, updated_at) VALUES (1, %s, %s)"
                params = (version, current_timestamp)
            
            result = execute_query(query, params)
            return result is not None
            
        except Exception as e:
            logger.error(f"Error setting database version: {e}")
            return False
    
    def get_current_version(self) -> Optional[int]:
        """
        Get the current version for this application instance.
        
        Returns:
            Optional[int]: Current version number or None if not initialized
        """
        return self._current_version
    
    def is_version_current(self) -> bool:
        """
        Check if the current application version is still current in the database.
        
        This is used to detect if another instance has started and incremented
        the version, indicating this instance should shut down.
        
        Returns:
            bool: True if current version matches database, False otherwise
        """
        try:
            if self._current_version is None:
                logger.warning("Current version not set, cannot check if current")
                return False
            
            db_version = self._get_database_version()
            
            if db_version is None:
                logger.warning("Could not get database version")
                return False
            
            is_current = self._current_version >= db_version
            
            if not is_current:
                logger.warning(
                    f"Version mismatch: current={self._current_version}, "
                    f"database={db_version}. Another instance may have started."
                )
            
            return is_current
            
        except Exception as e:
            logger.error(f"Error checking if version is current: {e}")
            return False
    
    def cleanup_version(self) -> None:
        """
        Clean up version on application shutdown.
        
        Note: We don't decrement the version on shutdown as this could
        cause race conditions. The version increment system is designed
        to be monotonically increasing.
        """
        logger.info("Version manager cleanup completed")

# Create and export singleton instance
version_manager: VersionManager = VersionManager() 