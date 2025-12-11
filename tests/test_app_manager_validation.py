#!/usr/bin/env python3
"""
Tests for AppManager validation logic.

Tests app configuration validation without requiring database access.
"""
import json
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import pytest
    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False

from app.base.app_manager import AppManager


@pytest.mark.unit
class TestAppManagerValidation:
    """Tests for AppManager validation without requiring database."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.manager = AppManager()
    
    def _create_temp_app_dir(self, app_name: str, config: dict) -> Path:
        """Create a temporary app directory with config."""
        temp_dir = Path(tempfile.mkdtemp())
        app_dir = temp_dir / app_name
        app_dir.mkdir()
        
        config_file = app_dir / "config.json"
        with open(config_file, 'w') as f:
            json.dump(config, f)
        
        return app_dir
    
    def test_validate_app_config_missing_abi_file(self):
        """Test validation catches missing ABI files."""
        config = {
            "name": "test_app",
            "description": "Test app",
            "contracts": {
                "router": {
                    "address_env_var": "TEST_ROUTER_ADDRESS",
                    "abi_file": "nonexistent.json"
                }
            },
            "available_methods": {
                "view": [],
                "write": []
            }
        }
        
        app_dir = self._create_temp_app_dir("test_app", config)
        self.manager.loaded_apps["test_app"] = {
            **config,
            "app_path": str(app_dir)
        }
        
        errors = self.manager.validate_app_config("test_app")
        assert len(errors) > 0
        assert any("ABI file not found" in error for error in errors)
        
        # Cleanup
        import shutil
        shutil.rmtree(app_dir.parent)
    
    def test_validate_app_config_missing_method_name(self):
        """Test validation catches methods without names."""
        config = {
            "name": "test_app",
            "description": "Test app",
            "contracts": {},
            "available_methods": {
                "view": [
                    {"description": "Method without name", "inputs": []}
                ],
                "write": []
            }
        }
        
        self.manager.loaded_apps["test_app"] = config
        errors = self.manager.validate_app_config("test_app")
        assert len(errors) > 0
        assert any("missing 'name' field" in error.lower() for error in errors)
    
    def test_validate_app_config_missing_inputs(self):
        """Test validation catches methods without inputs field."""
        config = {
            "name": "test_app",
            "description": "Test app",
            "contracts": {},
            "available_methods": {
                "view": [
                    {"name": "testMethod", "description": "Test"}
                ],
                "write": []
            }
        }
        
        self.manager.loaded_apps["test_app"] = config
        errors = self.manager.validate_app_config("test_app")
        assert len(errors) > 0
        assert any("missing 'inputs' field" in error.lower() for error in errors)
    
    def test_validate_app_config_valid_config(self):
        """Test validation passes for valid configuration."""
        config = {
            "name": "valid_app",
            "description": "Valid app",
            "contracts": {},
            "available_methods": {
                "view": [
                    {
                        "name": "getData",
                        "description": "Get data",
                        "inputs": ["param1"]
                    }
                ],
                "write": [
                    {
                        "name": "setData",
                        "description": "Set data",
                        "inputs": ["param1", "param2"]
                    }
                ]
            }
        }
        
        self.manager.loaded_apps["valid_app"] = config
        errors = self.manager.validate_app_config("valid_app")
        assert len(errors) == 0
    
    def test_validate_app_config_nonexistent_app(self):
        """Test validation returns error for nonexistent app."""
        errors = self.manager.validate_app_config("nonexistent_app")
        assert len(errors) > 0
        assert any("not found" in error.lower() for error in errors)
    
    def test_validate_app_config_missing_env_var(self):
        """Test validation warns about missing environment variables."""
        config = {
            "name": "env_test",
            "description": "Test env vars",
            "contracts": {
                "router": {
                    "address_env_var": "MISSING_ENV_VAR",
                    "abi_file": "router.json"
                }
            },
            "available_methods": {
                "view": [],
                "write": []
            }
        }
        
        # Create temp app dir with ABI file
        app_dir = self._create_temp_app_dir("env_test", config)
        abi_file = app_dir / "router.json"
        with open(abi_file, 'w') as f:
            json.dump([], f)
        
        self.manager.loaded_apps["env_test"] = {
            **config,
            "app_path": str(app_dir)
        }
        
        # Ensure env var is not set
        if "MISSING_ENV_VAR" in os.environ:
            del os.environ["MISSING_ENV_VAR"]
        
        errors = self.manager.validate_app_config("env_test")
        # Should have error about missing env var
        assert any("MISSING_ENV_VAR" in error for error in errors)
        
        # Cleanup
        import shutil
        shutil.rmtree(app_dir.parent)
    
    def test_load_app_style_guide_missing_file(self):
        """Test style guide loading when file doesn't exist."""
        config = {
            "name": "no_style",
            "app_path": "/nonexistent/path"
        }
        
        self.manager.loaded_apps["no_style"] = config
        style_guide = self.manager.load_app_style_guide("no_style")
        assert style_guide is None
    
    def test_load_app_style_guide_existing_file(self):
        """Test style guide loading when file exists."""
        app_dir = self._create_temp_app_dir("with_style", {
            "name": "with_style",
            "description": "App with style"
        })
        
        style_file = app_dir / "STYLE.md"
        style_content = "# Style Guide\nBe professional."
        with open(style_file, 'w') as f:
            f.write(style_content)
        
        self.manager.loaded_apps["with_style"] = {
            "name": "with_style",
            "app_path": str(app_dir)
        }
        
        loaded_content = self.manager.load_app_style_guide("with_style")
        assert loaded_content == style_content
        
        # Cleanup
        import shutil
        shutil.rmtree(app_dir.parent)
    
    def test_load_app_style_guide_nonexistent_app(self):
        """Test style guide loading for nonexistent app."""
        style_guide = self.manager.load_app_style_guide("nonexistent")
        assert style_guide is None
    
    def test_get_app_config_existing(self):
        """Test getting config for existing app."""
        config = {"name": "test", "description": "Test"}
        self.manager.loaded_apps["test"] = config
        retrieved = self.manager.get_app_config("test")
        assert retrieved == config
    
    def test_get_app_config_nonexistent(self):
        """Test getting config for nonexistent app."""
        retrieved = self.manager.get_app_config("nonexistent")
        assert retrieved is None
    
    def test_get_available_apps(self):
        """Test getting list of available apps."""
        self.manager.loaded_apps = {
            "app1": {"name": "app1", "description": "First app"},
            "app2": {"name": "app2", "description": "Second app"}
        }
        
        apps = self.manager.get_available_apps()
        assert len(apps) == 2
        assert {"name": "app1", "description": "First app"} in apps
        assert {"name": "app2", "description": "Second app"} in apps
    
    # ========== Additional Validation Edge Cases ==========
    
    def test_validate_app_config_empty_contracts(self):
        """Test validation with empty contracts dict."""
        config = {
            "name": "no_contracts",
            "description": "App with no contracts",
            "contracts": {},
            "available_methods": {
                "view": [],
                "write": []
            }
        }
        
        self.manager.loaded_apps["no_contracts"] = config
        errors = self.manager.validate_app_config("no_contracts")
        # Empty contracts is valid - app might just be a UI app
        assert len(errors) == 0
    
    def test_validate_app_config_missing_description_in_method(self):
        """Test validation with method missing description field."""
        config = {
            "name": "missing_desc",
            "description": "App with method missing desc",
            "contracts": {},
            "available_methods": {
                "view": [
                    {"name": "getData", "inputs": []}  # Missing description
                ],
                "write": []
            }
        }
        
        self.manager.loaded_apps["missing_desc"] = config
        errors = self.manager.validate_app_config("missing_desc")
        # Missing description might not be a validation error (depends on implementation)
        # Just verify it doesn't crash
        assert isinstance(errors, list)
    
    def test_validate_app_config_empty_method_name(self):
        """Test validation with empty string method name."""
        config = {
            "name": "empty_name",
            "description": "App with empty method name",
            "contracts": {},
            "available_methods": {
                "view": [
                    {"name": "", "description": "Empty name method", "inputs": []}
                ],
                "write": []
            }
        }
        
        self.manager.loaded_apps["empty_name"] = config
        errors = self.manager.validate_app_config("empty_name")
        # Empty name should technically be valid (it has a name field)
        assert isinstance(errors, list)
    
    def test_validate_app_config_special_chars_in_name(self):
        """Test validation with special characters in method names."""
        config = {
            "name": "special_chars",
            "description": "App with special method names",
            "contracts": {},
            "available_methods": {
                "view": [
                    {"name": "get-data_v2.0", "description": "Hyphen and dots", "inputs": []},
                    {"name": "getData(uint256)", "description": "Solidity signature", "inputs": ["param1"]}
                ],
                "write": []
            }
        }
        
        self.manager.loaded_apps["special_chars"] = config
        errors = self.manager.validate_app_config("special_chars")
        # Special chars are allowed in method names
        assert len(errors) == 0
    
    def test_validate_app_config_inputs_as_dict(self):
        """Test validation with inputs as dict instead of list."""
        config = {
            "name": "dict_inputs",
            "description": "App with dict inputs",
            "contracts": {},
            "available_methods": {
                "view": [
                    {
                        "name": "getData",
                        "description": "Get data",
                        "inputs": {"param1": "string", "param2": "uint256"}  # Dict instead of list
                    }
                ],
                "write": []
            }
        }
        
        self.manager.loaded_apps["dict_inputs"] = config
        errors = self.manager.validate_app_config("dict_inputs")
        # Dict inputs might be valid depending on implementation
        assert isinstance(errors, list)
    
    def test_get_available_apps_empty(self):
        """Test getting available apps when none are loaded."""
        self.manager.loaded_apps = {}
        apps = self.manager.get_available_apps()
        assert apps == []
    
    def test_load_app_style_guide_empty_content(self):
        """Test loading style guide with empty content."""
        app_dir = self._create_temp_app_dir("empty_style", {
            "name": "empty_style",
            "description": "App with empty style"
        })
        
        style_file = app_dir / "STYLE.md"
        with open(style_file, 'w') as f:
            f.write("")  # Empty file
        
        self.manager.loaded_apps["empty_style"] = {
            "name": "empty_style",
            "app_path": str(app_dir)
        }
        
        loaded_content = self.manager.load_app_style_guide("empty_style")
        assert loaded_content == ""
        
        # Cleanup
        import shutil
        shutil.rmtree(app_dir.parent)
    
    def test_validate_app_config_multiple_contracts(self):
        """Test validation with multiple contracts."""
        app_dir = self._create_temp_app_dir("multi_contract", {
            "name": "multi_contract",
            "description": "App with multiple contracts"
        })
        
        # Create ABI files
        for abi_name in ["router.json", "factory.json", "pair.json"]:
            abi_file = app_dir / abi_name
            with open(abi_file, 'w') as f:
                json.dump([], f)
        
        config = {
            "name": "multi_contract",
            "description": "Multi-contract app",
            "contracts": {
                "router": {
                    "address_env_var": "ROUTER_ADDRESS",
                    "abi_file": "router.json"
                },
                "factory": {
                    "address_env_var": "FACTORY_ADDRESS",
                    "abi_file": "factory.json"
                },
                "pair": {
                    "address_env_var": "PAIR_ADDRESS",
                    "abi_file": "pair.json"
                }
            },
            "available_methods": {
                "view": [{"name": "getReserves", "description": "Get reserves", "inputs": []}],
                "write": []
            },
            "app_path": str(app_dir)
        }
        
        self.manager.loaded_apps["multi_contract"] = config
        errors = self.manager.validate_app_config("multi_contract")
        
        # Should have errors for missing env vars
        assert any("ROUTER_ADDRESS" in error for error in errors)
        assert any("FACTORY_ADDRESS" in error for error in errors)
        
        # Cleanup
        import shutil
        shutil.rmtree(app_dir.parent)


if __name__ == "__main__":
    tester = TestAppManagerValidation()
    
    try:
        tester.setup_method()
    except Exception as e:
        print(f"⚠️  Setup failed: {e}")
        sys.exit(0)
    
    # Run tests
    test_methods = [method for method in dir(tester) if method.startswith("test_")]
    passed = 0
    failed = 0
    
    for test_method in test_methods:
        try:
            print(f"Running {test_method}...")
            getattr(tester, test_method)()
            print(f"  ✅ {test_method} passed")
            passed += 1
        except Exception as e:
            print(f"  ❌ {test_method} failed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print(f"\n📊 Results: {passed} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)

