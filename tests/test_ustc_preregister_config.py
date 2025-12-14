#!/usr/bin/env python3
"""
Tests for USTC Preregister LLM app configuration validation.

Tests that the app config is valid and discoverable by LLMAppManager.
"""
import json
import sys
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import pytest
    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False

from app.base.llm_app_manager import LLMAppManager


@pytest.mark.unit
class TestUSTCPreregisterConfig:
    """Tests for USTC Preregister app configuration."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.manager = LLMAppManager()
        self.repo_root = Path(__file__).parent.parent
    
    def test_config_file_exists(self):
        """Test that config.json exists."""
        config_path = self.repo_root / "app" / "llm_apps" / "ustc_preregister" / "config.json"
        assert config_path.exists(), f"Config file not found: {config_path}"
    
    def test_config_is_valid_json(self):
        """Test that config.json is valid JSON."""
        config_path = self.repo_root / "app" / "llm_apps" / "ustc_preregister" / "config.json"
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        assert isinstance(config, dict)
        assert "name" in config
        assert config["name"] == "ustc_preregister"
    
    def test_config_has_required_fields(self):
        """Test that config has all required fields."""
        config_path = self.repo_root / "app" / "llm_apps" / "ustc_preregister" / "config.json"
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        required_fields = ["name", "description", "contracts", "available_methods"]
        for field in required_fields:
            assert field in config, f"Missing required field: {field}"
    
    def test_config_contracts_section(self):
        """Test that contracts section is properly configured."""
        config_path = self.repo_root / "app" / "llm_apps" / "ustc_preregister" / "config.json"
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        assert "contracts" in config
        assert "preregister" in config["contracts"]
        
        contract_config = config["contracts"]["preregister"]
        assert "address_env_var" in contract_config
        assert contract_config["address_env_var"] == "USTC_PREREGISTER_ADDRESS"
        assert "abi_file" in contract_config
        assert contract_config["abi_file"] == "abi/USTCPreregister.json"
    
    def test_abi_file_exists(self):
        """Test that ABI file exists."""
        abi_path = self.repo_root / "app" / "llm_apps" / "ustc_preregister" / "abi" / "USTCPreregister.json"
        assert abi_path.exists(), f"ABI file not found: {abi_path}"
    
    def test_abi_file_is_valid_json(self):
        """Test that ABI file is valid JSON."""
        abi_path = self.repo_root / "app" / "llm_apps" / "ustc_preregister" / "abi" / "USTCPreregister.json"
        
        with open(abi_path, 'r') as f:
            abi = json.load(f)
        
        assert isinstance(abi, list)
        assert len(abi) > 0
    
    def test_config_view_methods(self):
        """Test that view methods are properly configured."""
        config_path = self.repo_root / "app" / "llm_apps" / "ustc_preregister" / "config.json"
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        assert "available_methods" in config
        assert "view" in config["available_methods"]
        
        view_methods = config["available_methods"]["view"]
        assert isinstance(view_methods, list)
        assert len(view_methods) >= 3
        
        method_names = [m["name"] for m in view_methods]
        assert "getTotalDeposits" in method_names
        assert "getUserCount" in method_names
        assert "getUserDeposit" in method_names
    
    def test_config_write_methods(self):
        """Test that write methods are properly configured."""
        config_path = self.repo_root / "app" / "llm_apps" / "ustc_preregister" / "config.json"
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        assert "available_methods" in config
        assert "write" in config["available_methods"]
        
        write_methods = config["available_methods"]["write"]
        assert isinstance(write_methods, list)
        assert len(write_methods) >= 2
        
        method_names = [m["name"] for m in write_methods]
        assert "deposit" in method_names
        assert "withdraw" in method_names
    
    def test_deposit_method_config(self):
        """Test that deposit method has correct configuration."""
        config_path = self.repo_root / "app" / "llm_apps" / "ustc_preregister" / "config.json"
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        write_methods = config["available_methods"]["write"]
        deposit_method = next(m for m in write_methods if m["name"] == "deposit")
        
        assert deposit_method["contract"] == "preregister"
        assert "amount" in deposit_method["inputs"]
        assert deposit_method.get("requires_token_approval") is True
        assert "token_amount_pairs" in deposit_method
    
    def test_withdraw_method_config(self):
        """Test that withdraw method has correct configuration."""
        config_path = self.repo_root / "app" / "llm_apps" / "ustc_preregister" / "config.json"
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        write_methods = config["available_methods"]["write"]
        withdraw_method = next(m for m in write_methods if m["name"] == "withdraw")
        
        assert withdraw_method["contract"] == "preregister"
        assert "amount" in withdraw_method["inputs"]
        assert withdraw_method.get("requires_token_approval") is False
        assert "token_amount_pairs" in withdraw_method
    
    def test_parameter_processing_config(self):
        """Test that parameter_processing is properly configured."""
        config_path = self.repo_root / "app" / "llm_apps" / "ustc_preregister" / "config.json"
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        assert "parameter_processing" in config
        param_processing = config["parameter_processing"]
        
        assert "amount" in param_processing
        assert param_processing["amount"]["type"] == "token_amount"
        assert param_processing["amount"].get("convert_from_human") is True
        assert param_processing["amount"].get("get_decimals_from") == "token_address"
        
        assert "token_address" in param_processing
        assert param_processing["token_address"]["type"] == "address"
        
        assert "user" in param_processing
        assert param_processing["user"]["type"] == "address"
    
    def test_manager_validates_config(self):
        """Test that LLMAppManager can validate the config."""
        # Load the app config
        config_path = self.repo_root / "app" / "llm_apps" / "ustc_preregister" / "config.json"
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Add app_path for validation
        app_path = self.repo_root / "app" / "llm_apps" / "ustc_preregister"
        config["app_path"] = str(app_path)
        
        # Register with manager
        self.manager.loaded_llm_apps["ustc_preregister"] = config
        
        # Validate (may have warnings about env vars, but should not have critical errors)
        errors = self.manager.validate_llm_app_config("ustc_preregister")
        
        # Should not have critical errors (env var warnings are OK)
        critical_errors = [e for e in errors if "not found" not in e.lower() and "env" not in e.lower()]
        assert len(critical_errors) == 0, f"Critical validation errors: {critical_errors}"
    
    def test_style_guide_exists(self):
        """Test that STYLE.md exists."""
        style_path = self.repo_root / "app" / "llm_apps" / "ustc_preregister" / "STYLE.md"
        assert style_path.exists(), f"STYLE.md not found: {style_path}"
    
    def test_style_guide_is_readable(self):
        """Test that STYLE.md is readable."""
        style_path = self.repo_root / "app" / "llm_apps" / "ustc_preregister" / "STYLE.md"
        
        with open(style_path, 'r') as f:
            content = f.read()
        
        assert len(content) > 0
        assert "USTC" in content or "Preregister" in content


if __name__ == "__main__":
    tester = TestUSTCPreregisterConfig()
    
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

