"""
App manager for loading and managing blockchain apps.
Handles app discovery, configuration loading, and session management.
"""
import logging
import json
import os
from typing import Dict, List, Optional, Any
from pathlib import Path
from app.base.app_session import AppSession
from db.utils import hash_user_id

logger = logging.getLogger(__name__)

class AppManager:
    """Manages the lifecycle of blockchain apps and their sessions."""
    
    def __init__(self):
        """Initialize the AppManager."""
        self.apps_dir = Path("app/apps")
        self.loaded_apps: Dict[str, Dict[str, Any]] = {}
        self.active_sessions: Dict[str, AppSession] = {}  # user_id -> session
        
    async def initialize(self) -> None:
        """Initialize the app manager by loading all available apps."""
        try:
            await self._discover_and_load_apps()
            logger.info(f"AppManager initialized with {len(self.loaded_apps)} apps")
        except Exception as e:
            logger.error(f"Failed to initialize AppManager: {str(e)}")
            raise
    
    async def _discover_and_load_apps(self) -> None:
        """Discover and load all apps from the apps directory."""
        if not self.apps_dir.exists():
            logger.warning(f"Apps directory not found: {self.apps_dir}")
            return
        
        for app_path in self.apps_dir.iterdir():
            if app_path.is_dir() and not app_path.name.startswith('.'):
                try:
                    app_config = await self._load_app_config(app_path)
                    if app_config:
                        self.loaded_apps[app_config["name"]] = app_config
                        logger.info(f"Loaded app: {app_config['name']}")
                except Exception as e:
                    logger.error(f"Failed to load app from {app_path}: {str(e)}")
    
    async def _load_app_config(self, app_path: Path) -> Optional[Dict[str, Any]]:
        """Load app configuration from config.json file.
        
        Args:
            app_path: Path to the app directory
            
        Returns:
            Dict containing app configuration or None if loading fails
        """
        config_file = app_path / "config.json"
        if not config_file.exists():
            logger.warning(f"No config.json found in {app_path}")
            return None
        
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
            
            # Validate required fields
            required_fields = ["name", "description", "contracts", "available_methods"]
            for field in required_fields:
                if field not in config:
                    logger.error(f"Missing required field '{field}' in {config_file}")
                    return None
            
            # Add app directory path for loading ABIs and style guide
            config["app_path"] = str(app_path)
            
            # Validate contract addresses exist in environment
            for contract_name, contract_config in config["contracts"].items():
                env_var = contract_config["address_env_var"]
                if not os.getenv(env_var):
                    logger.warning(f"Environment variable {env_var} not set for contract {contract_name}")
            
            return config
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {config_file}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Failed to load config from {config_file}: {str(e)}")
            return None
    
    def get_available_apps(self) -> List[Dict[str, str]]:
        """Get list of available apps with basic info.
        
        Returns:
            List of dicts containing app name and description
        """
        return [
            {
                "name": app_config["name"],
                "description": app_config["description"]
            }
            for app_config in self.loaded_apps.values()
        ]
    
    def get_app_config(self, app_name: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific app.
        
        Args:
            app_name: Name of the app
            
        Returns:
            App configuration dict or None if not found
        """
        return self.loaded_apps.get(app_name)
    
    async def start_app_session(self, user_id: str, app_name: str) -> Optional[AppSession]:
        """Start a new app session for a user.
        
        Args:
            user_id: Telegram user ID as string
            app_name: Name of the app to start
            
        Returns:
            AppSession instance or None if app not found
        """
        try:
            # Check if app exists
            app_config = self.get_app_config(app_name)
            if not app_config:
                logger.error(f"App {app_name} not found")
                return None
            
            # Close any existing session for this user
            await self.close_session(user_id)
            
            # Create new session
            session = AppSession(user_id, app_name, app_config)
            
            # Initialize session context
            if not await session.initialize_context():
                logger.error(f"Failed to initialize context for user {hash_user_id(user_id)} in app {app_name}")
                return None
            
            # Store session
            self.active_sessions[user_id] = session
            
            logger.info(f"Started app session {app_name} for user {hash_user_id(user_id)}")
            return session
            
        except Exception as e:
            logger.error(f"Failed to start app session {app_name} for user {hash_user_id(user_id)}: {str(e)}")
            return None
    
    def get_session(self, user_id: str) -> Optional[AppSession]:
        """Get the active session for a user.
        
        Args:
            user_id: Telegram user ID as string
            
        Returns:
            AppSession instance or None if no active session
        """
        return self.active_sessions.get(user_id)
    
    async def close_session(self, user_id: str) -> None:
        """Close the active session for a user.
        
        Args:
            user_id: Telegram user ID as string
        """
        if user_id in self.active_sessions:
            session = self.active_sessions[user_id]
            session.cancel_pending_transaction()  # Clean up any pending transactions
            del self.active_sessions[user_id]
            logger.info(f"Closed app session for user {hash_user_id(user_id)}")
    
    def load_app_style_guide(self, app_name: str) -> Optional[str]:
        """Load the style guide for an app.
        
        Args:
            app_name: Name of the app
            
        Returns:
            Style guide content as string or None if not found
        """
        try:
            app_config = self.get_app_config(app_name)
            if not app_config:
                return None
            
            style_file = Path(app_config["app_path"]) / "STYLE.md"
            if not style_file.exists():
                logger.warning(f"No STYLE.md found for app {app_name}")
                return None
            
            with open(style_file, 'r') as f:
                return f.read()
                
        except Exception as e:
            logger.error(f"Failed to load style guide for app {app_name}: {str(e)}")
            return None
    
    def validate_app_config(self, app_name: str) -> List[str]:
        """Validate an app's configuration.
        
        Args:
            app_name: Name of the app to validate
            
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        app_config = self.get_app_config(app_name)
        if not app_config:
            errors.append(f"App {app_name} not found")
            return errors
        
        # Check contract addresses
        for contract_name, contract_config in app_config["contracts"].items():
            env_var = contract_config["address_env_var"]
            if not os.getenv(env_var):
                errors.append(f"Environment variable {env_var} not set for contract {contract_name}")
            
            # Check ABI file exists
            abi_path = Path(app_config["app_path"]) / contract_config["abi_file"]
            if not abi_path.exists():
                errors.append(f"ABI file not found: {abi_path}")
        
        # Validate method configurations
        for method_type in ["view", "write"]:
            methods = app_config["available_methods"].get(method_type, [])
            for method in methods:
                if "name" not in method:
                    errors.append(f"Method missing 'name' field in {method_type} methods")
                if "inputs" not in method:
                    errors.append(f"Method {method.get('name', 'unknown')} missing 'inputs' field")
        
        return errors
    
    async def refresh_apps(self) -> None:
        """Refresh the app configurations by reloading from disk."""
        try:
            self.loaded_apps.clear()
            await self._discover_and_load_apps()
            logger.info(f"Refreshed apps: {len(self.loaded_apps)} apps loaded")
        except Exception as e:
            logger.error(f"Failed to refresh apps: {str(e)}")
            raise

# Create singleton instance
app_manager = AppManager()