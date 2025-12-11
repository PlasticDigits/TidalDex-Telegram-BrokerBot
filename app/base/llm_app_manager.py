"""
LLM app manager for loading and managing LLM-powered blockchain apps.
Handles LLM app discovery, configuration loading, and session management.
"""
import logging
import json
import os
from typing import Dict, List, Optional, Any
from pathlib import Path
from app.base.llm_app_session import LLMAppSession
from db.utils import hash_user_id

logger = logging.getLogger(__name__)

class LLMAppManager:
    """Manages the lifecycle of LLM-powered blockchain apps and their sessions."""
    
    def __init__(self):
        """Initialize the LLMAppManager."""
        self.llm_apps_dir = Path("app/llm_apps")
        self.loaded_llm_apps: Dict[str, Dict[str, Any]] = {}
        self.active_sessions: Dict[str, LLMAppSession] = {}  # user_id -> session
        
    async def initialize(self) -> None:
        """Initialize the LLM app manager by loading all available LLM apps."""
        try:
            await self._discover_and_load_llm_apps()
            logger.info(f"LLMAppManager initialized with {len(self.loaded_llm_apps)} LLM apps")
        except Exception as e:
            logger.error(f"Failed to initialize LLMAppManager: {str(e)}")
            raise
    
    async def _discover_and_load_llm_apps(self) -> None:
        """Discover and load all LLM apps from the llm_apps directory."""
        if not self.llm_apps_dir.exists():
            logger.warning(f"LLM apps directory not found: {self.llm_apps_dir}")
            return
        
        for llm_app_path in self.llm_apps_dir.iterdir():
            if llm_app_path.is_dir() and not llm_app_path.name.startswith('.'):
                try:
                    llm_app_config = await self._load_llm_app_config(llm_app_path)
                    if llm_app_config:
                        self.loaded_llm_apps[llm_app_config["name"]] = llm_app_config
                        logger.info(f"Loaded LLM app: {llm_app_config['name']}")
                except Exception as e:
                    logger.error(f"Failed to load LLM app from {llm_app_path}: {str(e)}")
    
    async def _load_llm_app_config(self, llm_app_path: Path) -> Optional[Dict[str, Any]]:
        """Load LLM app configuration from config.json file.
        
        Args:
            llm_app_path: Path to the LLM app directory
            
        Returns:
            Dict containing LLM app configuration or None if loading fails
        """
        config_file = llm_app_path / "config.json"
        if not config_file.exists():
            logger.warning(f"No config.json found in {llm_app_path}")
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
            
            # Add LLM app directory path for loading ABIs and style guide
            config["app_path"] = str(llm_app_path)
            
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
    
    def get_available_llm_apps(self) -> List[Dict[str, str]]:
        """Get list of available LLM apps with basic info.
        
        Returns:
            List of dicts containing LLM app name and description
        """
        return [
            {
                "name": llm_app_config["name"],
                "description": llm_app_config["description"]
            }
            for llm_app_config in self.loaded_llm_apps.values()
        ]
    
    def get_llm_app_config(self, llm_app_name: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific LLM app.
        
        Args:
            llm_app_name: Name of the LLM app
            
        Returns:
            LLM app configuration dict or None if not found
        """
        return self.loaded_llm_apps.get(llm_app_name)
    
    async def start_llm_app_session(self, user_id: str, llm_app_name: str) -> Optional[LLMAppSession]:
        """Start a new LLM app session for a user.
        
        Args:
            user_id: Telegram user ID as string
            llm_app_name: Name of the LLM app to start
            
        Returns:
            LLMAppSession instance or None if LLM app not found
        """
        try:
            # Check if LLM app exists
            llm_app_config = self.get_llm_app_config(llm_app_name)
            if not llm_app_config:
                logger.error(f"LLM app {llm_app_name} not found")
                return None
            
            # Close any existing session for this user
            await self.close_session(user_id)
            
            # Create new session
            session = LLMAppSession(user_id, llm_app_name, llm_app_config)
            
            # Initialize session context
            if not await session.initialize_context():
                logger.error(f"Failed to initialize context for user {hash_user_id(user_id)} in LLM app {llm_app_name}")
                return None
            
            # Store session
            self.active_sessions[user_id] = session
            
            logger.info(f"Started LLM app session {llm_app_name} for user {hash_user_id(user_id)}")
            return session
            
        except Exception as e:
            logger.error(f"Failed to start LLM app session {llm_app_name} for user {hash_user_id(user_id)}: {str(e)}")
            return None
    
    def get_session(self, user_id: str) -> Optional[LLMAppSession]:
        """Get the active session for a user.
        
        Args:
            user_id: Telegram user ID as string
            
        Returns:
            LLMAppSession instance or None if no active session
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
            logger.info(f"Closed LLM app session for user {hash_user_id(user_id)}")
    
    def load_llm_app_style_guide(self, llm_app_name: str) -> Optional[str]:
        """Load the style guide for an LLM app.
        
        Args:
            llm_app_name: Name of the LLM app
            
        Returns:
            Style guide content as string or None if not found
        """
        try:
            llm_app_config = self.get_llm_app_config(llm_app_name)
            if not llm_app_config:
                return None
            
            style_file = Path(llm_app_config["app_path"]) / "STYLE.md"
            if not style_file.exists():
                logger.warning(f"No STYLE.md found for LLM app {llm_app_name}")
                return None
            
            with open(style_file, 'r') as f:
                return f.read()
                
        except Exception as e:
            logger.error(f"Failed to load style guide for LLM app {llm_app_name}: {str(e)}")
            return None
    
    def validate_llm_app_config(self, llm_app_name: str) -> List[str]:
        """Validate an LLM app's configuration.
        
        Args:
            llm_app_name: Name of the LLM app to validate
            
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        llm_app_config = self.get_llm_app_config(llm_app_name)
        if not llm_app_config:
            errors.append(f"LLM app {llm_app_name} not found")
            return errors
        
        # Check contract addresses
        for contract_name, contract_config in llm_app_config["contracts"].items():
            env_var = contract_config["address_env_var"]
            if not os.getenv(env_var):
                errors.append(f"Environment variable {env_var} not set for contract {contract_name}")
            
            # Check ABI file exists
            abi_path = Path(llm_app_config["app_path"]) / contract_config["abi_file"]
            if not abi_path.exists():
                errors.append(f"ABI file not found: {abi_path}")
        
        # Validate method configurations
        for method_type in ["view", "write"]:
            methods = llm_app_config["available_methods"].get(method_type, [])
            for method in methods:
                if "name" not in method:
                    errors.append(f"Method missing 'name' field in {method_type} methods")
                if "inputs" not in method:
                    errors.append(f"Method {method.get('name', 'unknown')} missing 'inputs' field")
        
        return errors
    
    async def refresh_apps(self) -> None:
        """Refresh the LLM app configurations by reloading from disk."""
        try:
            self.loaded_llm_apps.clear()
            await self._discover_and_load_llm_apps()
            logger.info(f"Refreshed LLM apps: {len(self.loaded_llm_apps)} LLM apps loaded")
        except Exception as e:
            logger.error(f"Failed to refresh LLM apps: {str(e)}")
            raise

# Create singleton instance
llm_app_manager = LLMAppManager()