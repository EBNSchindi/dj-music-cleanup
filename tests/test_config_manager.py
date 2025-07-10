"""
Unit tests for ConfigManager
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from music_cleanup.core.config_manager import (
    ConfigManager, MusicCleanupConfig, AudioConfig, 
    ProcessingConfig, OrganizationConfig, UIConfig
)


class TestConfigManager(unittest.TestCase):
    
    def setUp(self):
        """Set up test environment"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        
        # Create project structure
        self.project_root = self.temp_path / "project"
        self.config_dir = self.project_root / "config"
        self.config_dir.mkdir(parents=True)
        
        # Create test config file
        self.test_config = {
            "audio": {
                "fingerprint_algorithm": "chromaprint",
                "min_health_score": 75.0
            },
            "ui": {
                "log_level": "DEBUG"
            }
        }
        
        config_file = self.config_dir / "test.json"
        with open(config_file, 'w') as f:
            json.dump(self.test_config, f)
    
    def tearDown(self):
        """Clean up test environment"""
        self.temp_dir.cleanup()
    
    def test_config_manager_initialization(self):
        """Test ConfigManager initialization"""
        manager = ConfigManager(self.project_root)
        
        self.assertEqual(manager.project_root, self.project_root)
        self.assertEqual(manager.config_dir, self.config_dir)
        self.assertTrue(manager.user_config_dir.exists())
    
    def test_load_default_config(self):
        """Test loading default configuration"""
        manager = ConfigManager(self.project_root)
        config = manager.load_config()
        
        self.assertIsInstance(config, MusicCleanupConfig)
        self.assertIsInstance(config.audio, AudioConfig)
        self.assertIsInstance(config.processing, ProcessingConfig)
        self.assertIsInstance(config.organization, OrganizationConfig)
        self.assertIsInstance(config.ui, UIConfig)
        
        # Check default values
        self.assertEqual(config.audio.fingerprint_algorithm, "chromaprint")
        self.assertEqual(config.audio.min_health_score, 50.0)
        self.assertEqual(config.processing.batch_size, 50)
        self.assertEqual(config.ui.log_level, "INFO")
    
    def test_load_project_config(self):
        """Test loading project-specific configuration"""
        manager = ConfigManager(self.project_root)
        config = manager.load_config(project_config="test.json")
        
        # Check that project config overrides defaults
        self.assertEqual(config.audio.min_health_score, 75.0)  # From test config
        self.assertEqual(config.ui.log_level, "DEBUG")  # From test config
        self.assertEqual(config.processing.batch_size, 50)  # Default value
    
    def test_cli_overrides(self):
        """Test CLI argument overrides"""
        manager = ConfigManager(self.project_root)
        
        cli_overrides = {
            "audio": {
                "duplicate_action": "delete"
            },
            "processing": {
                "max_workers": 8
            },
            "dry_run": True
        }
        
        config = manager.load_config(cli_overrides=cli_overrides)
        
        self.assertEqual(config.audio.duplicate_action, "delete")
        self.assertEqual(config.processing.max_workers, 8)
        self.assertTrue(config.dry_run)
    
    def test_config_validation(self):
        """Test configuration validation"""
        manager = ConfigManager(self.project_root)
        config = MusicCleanupConfig()
        
        # Valid config should pass
        issues = manager.validate_config(config)
        self.assertEqual(len(issues), 0)
        
        # Invalid config should fail
        config.audio.duplicate_similarity = 1.5  # Invalid value
        config.audio.min_health_score = -10  # Invalid value
        config.processing.batch_size = 0  # Invalid value
        
        issues = manager.validate_config(config)
        self.assertGreater(len(issues), 0)
        self.assertTrue(any("duplicate_similarity" in issue for issue in issues))
        self.assertTrue(any("min_health_score" in issue for issue in issues))
        self.assertTrue(any("batch_size" in issue for issue in issues))
    
    def test_save_user_settings(self):
        """Test saving user settings"""
        manager = ConfigManager(self.project_root)
        
        user_settings = {
            "audio": {
                "fingerprint_algorithm": "md5"
            },
            "ui": {
                "progress_mode": "detailed"
            }
        }
        
        result = manager.save_user_settings(user_settings)
        self.assertTrue(result)
        
        # Verify settings were saved
        user_config_path = manager.user_config_dir / "settings.json"
        self.assertTrue(user_config_path.exists())
        
        with open(user_config_path) as f:
            saved_settings = json.load(f)
        
        self.assertEqual(saved_settings["audio"]["fingerprint_algorithm"], "md5")
        self.assertEqual(saved_settings["ui"]["progress_mode"], "detailed")
    
    def test_config_merge(self):
        """Test configuration merging"""
        manager = ConfigManager(self.project_root)
        
        base = {
            "audio": {
                "fingerprint_algorithm": "chromaprint",
                "min_health_score": 50.0
            },
            "processing": {
                "batch_size": 50
            }
        }
        
        override = {
            "audio": {
                "min_health_score": 75.0  # Override existing
            },
            "ui": {
                "log_level": "DEBUG"  # Add new section
            }
        }
        
        result = manager._merge_configs(base, override)
        
        # Check merged values
        self.assertEqual(result["audio"]["fingerprint_algorithm"], "chromaprint")  # Preserved
        self.assertEqual(result["audio"]["min_health_score"], 75.0)  # Overridden
        self.assertEqual(result["processing"]["batch_size"], 50)  # Preserved
        self.assertEqual(result["ui"]["log_level"], "DEBUG")  # Added
    
    @patch('platform.system')
    def test_user_config_dir_windows(self, mock_system):
        """Test user config directory on Windows"""
        mock_system.return_value = "Windows"
        
        with patch.dict('os.environ', {'APPDATA': str(self.temp_path)}):
            manager = ConfigManager(self.project_root)
            expected = self.temp_path / "dj-music-cleanup"
            self.assertEqual(manager.user_config_dir, expected)
    
    @patch('platform.system')
    def test_user_config_dir_macos(self, mock_system):
        """Test user config directory on macOS"""
        mock_system.return_value = "Darwin"
        
        manager = ConfigManager(self.project_root)
        expected_path = Path("~/Library/Application Support/dj-music-cleanup").expanduser()
        self.assertEqual(manager.user_config_dir, expected_path)
    
    @patch('platform.system')
    def test_user_config_dir_linux(self, mock_system):
        """Test user config directory on Linux"""
        mock_system.return_value = "Linux"
        
        with patch.dict('os.environ', {'XDG_CONFIG_HOME': str(self.temp_path)}):
            manager = ConfigManager(self.project_root)
            expected = self.temp_path / "dj-music-cleanup"
            self.assertEqual(manager.user_config_dir, expected)


if __name__ == '__main__':
    unittest.main()