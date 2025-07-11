"""
Unit tests for ConfigManager.

Tests the hierarchical configuration loading system and dataclass-based config.
"""

import pytest
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.music_cleanup.core.config_manager import (
    ConfigManager,
    MusicCleanupConfig,
    AudioConfig,
    ProcessingConfig,
    OutputDirectoriesConfig,
    OrganizationConfig,
    UIConfig,
    get_config_manager,
    get_config
)


class TestConfigDataclasses:
    """Test configuration dataclasses."""
    
    def test_audio_config_defaults(self):
        """Test AudioConfig default values."""
        config = AudioConfig()
        assert config.fingerprint_algorithm == "chromaprint"
        assert config.fingerprint_length == 120
        assert config.duplicate_action == "move"
        assert config.duplicate_similarity == 0.95
        assert config.min_health_score == 50.0
        assert config.silence_threshold == 0.001
        assert config.defect_sample_duration == 30.0
        assert '.mp3' in config.supported_formats
        assert '.flac' in config.supported_formats
    
    def test_processing_config_defaults(self):
        """Test ProcessingConfig default values."""
        config = ProcessingConfig()
        assert config.batch_size == 50
        assert config.max_workers == 4
        assert config.memory_limit_mb == 1024
        assert config.enable_recovery == True
        assert config.checkpoint_interval == 300
        assert config.integrity_level == "checksum"
    
    def test_output_directories_config_defaults(self):
        """Test OutputDirectoriesConfig default values."""
        config = OutputDirectoriesConfig()
        assert config.organized_dir == "./organized"
        assert config.rejected_dir == "./rejected"
        assert config.duplicates_dir == "./rejected/duplicates"
        assert config.low_quality_dir == "./rejected/low_quality"
        assert config.corrupted_dir == "./rejected/corrupted"
        assert config.auto_create_dirs == True
    
    def test_organization_config_defaults(self):
        """Test OrganizationConfig default values."""
        config = OrganizationConfig()
        assert config.structure_template == "{genre}/{artist}/{artist} - {title}"
        assert config.quality_indicators == True
        assert config.handle_duplicates == True
        assert config.quarantine_defective == True
        assert config.create_backups == False
    
    def test_ui_config_defaults(self):
        """Test UIConfig default values."""
        config = UIConfig()
        assert config.progress_mode == "simple"
        assert config.log_level == "INFO"
        assert config.color_output == True
        assert config.verbose_errors == False
    
    def test_music_cleanup_config_initialization(self):
        """Test MusicCleanupConfig initialization."""
        config = MusicCleanupConfig()
        assert isinstance(config.audio, AudioConfig)
        assert isinstance(config.processing, ProcessingConfig)
        assert isinstance(config.output_directories, OutputDirectoriesConfig)
        assert isinstance(config.organization, OrganizationConfig)
        assert isinstance(config.ui, UIConfig)
        assert config.dry_run == False
        assert config.workspace_directory == "./workspace"


class TestConfigManager:
    """Test ConfigManager functionality."""
    
    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories for testing."""
        project_root = tempfile.mkdtemp()
        config_dir = Path(project_root) / "config"
        config_dir.mkdir()
        user_dir = tempfile.mkdtemp()
        
        yield project_root, config_dir, user_dir
        
        shutil.rmtree(project_root, ignore_errors=True)
        shutil.rmtree(user_dir, ignore_errors=True)
    
    @pytest.fixture
    def config_manager(self, temp_dirs):
        """Create ConfigManager with temp directories."""
        project_root, _, user_dir = temp_dirs
        
        with patch.object(ConfigManager, '_get_user_config_dir', return_value=Path(user_dir)):
            manager = ConfigManager(project_root=Path(project_root))
        
        return manager
    
    def test_config_manager_initialization(self, config_manager, temp_dirs):
        """Test ConfigManager initialization."""
        project_root, _, _ = temp_dirs
        assert config_manager.project_root == Path(project_root)
        assert config_manager.config_dir == Path(project_root) / "config"
        assert config_manager.user_config_dir.exists()
    
    def test_load_default_config(self, config_manager):
        """Test loading default configuration."""
        config = config_manager.load_config()
        
        assert isinstance(config, MusicCleanupConfig)
        assert config.audio.fingerprint_algorithm == "chromaprint"
        assert config.processing.batch_size == 50
        assert config.dry_run == False
    
    def test_load_project_config(self, config_manager, temp_dirs):
        """Test loading project-specific configuration."""
        _, config_dir, _ = temp_dirs
        
        # Create project config
        project_config = {
            "audio": {
                "fingerprint_algorithm": "acoustid",
                "min_health_score": 60.0
            },
            "processing": {
                "batch_size": 100
            }
        }
        
        config_file = config_dir / "test.json"
        config_file.write_text(json.dumps(project_config))
        
        # Load config
        config = config_manager.load_config(project_config="test.json")
        
        assert config.audio.fingerprint_algorithm == "acoustid"
        assert config.audio.min_health_score == 60.0
        assert config.processing.batch_size == 100
        # Other values should be defaults
        assert config.audio.duplicate_similarity == 0.95
    
    def test_load_user_config(self, config_manager, temp_dirs):
        """Test loading user configuration."""
        _, _, user_dir = temp_dirs
        
        # Create user config
        user_config = {
            "ui": {
                "log_level": "DEBUG",
                "color_output": False
            }
        }
        
        user_file = Path(user_dir) / "settings.json"
        user_file.write_text(json.dumps(user_config))
        
        # Load config
        config = config_manager.load_config()
        
        assert config.ui.log_level == "DEBUG"
        assert config.ui.color_output == False
    
    def test_cli_overrides(self, config_manager):
        """Test CLI argument overrides."""
        cli_overrides = {
            "dry_run": True,
            "audio": {
                "min_health_score": 70.0
            },
            "processing": {
                "max_workers": 8
            }
        }
        
        config = config_manager.load_config(cli_overrides=cli_overrides)
        
        assert config.dry_run == True
        assert config.audio.min_health_score == 70.0
        assert config.processing.max_workers == 8
    
    def test_config_precedence(self, config_manager, temp_dirs):
        """Test configuration loading precedence."""
        _, config_dir, user_dir = temp_dirs
        
        # Create project config
        project_config = {
            "audio": {"min_health_score": 55.0},
            "processing": {"batch_size": 75}
        }
        (config_dir / "test.json").write_text(json.dumps(project_config))
        
        # Create user config
        user_config = {
            "audio": {"min_health_score": 65.0},
            "ui": {"log_level": "WARNING"}
        }
        (Path(user_dir) / "settings.json").write_text(json.dumps(user_config))
        
        # CLI overrides
        cli_overrides = {
            "audio": {"min_health_score": 75.0}
        }
        
        # Load with all sources
        config = config_manager.load_config(
            project_config="test.json",
            cli_overrides=cli_overrides
        )
        
        # CLI should override all
        assert config.audio.min_health_score == 75.0
        # User config should override project
        assert config.ui.log_level == "WARNING"
        # Project config should be used when no override
        assert config.processing.batch_size == 75
    
    def test_save_user_settings(self, config_manager, temp_dirs):
        """Test saving user settings."""
        _, _, user_dir = temp_dirs
        
        settings = {
            "ui": {"log_level": "ERROR"},
            "audio": {"duplicate_action": "quarantine"}
        }
        
        config_manager.save_user_settings(settings)
        
        # Verify saved file
        saved_file = Path(user_dir) / "settings.json"
        assert saved_file.exists()
        
        saved_data = json.loads(saved_file.read_text())
        assert saved_data["ui"]["log_level"] == "ERROR"
        assert saved_data["audio"]["duplicate_action"] == "quarantine"
    
    def test_validate_config(self, config_manager):
        """Test configuration validation."""
        # Valid config
        config = config_manager.load_config()
        errors = config_manager.validate_config(config)
        assert len(errors) == 0
        
        # Invalid batch size
        config.processing.batch_size = 0
        errors = config_manager.validate_config(config)
        assert any("batch_size" in error for error in errors)
        
        # Invalid integrity level
        config.processing.integrity_level = "invalid"
        errors = config_manager.validate_config(config)
        assert any("integrity_level" in error for error in errors)
    
    def test_export_config(self, config_manager, temp_dirs):
        """Test configuration export."""
        config = config_manager.load_config()
        config.audio.min_health_score = 65.0
        
        export_path = Path(temp_dirs[0]) / "exported_config.json"
        config_manager.export_config(config, export_path)
        
        assert export_path.exists()
        
        # Verify exported data
        exported = json.loads(export_path.read_text())
        assert exported["audio"]["min_health_score"] == 65.0
    
    @patch('platform.system')
    def test_user_config_dir_windows(self, mock_system):
        """Test Windows user config directory."""
        mock_system.return_value = "Windows"
        
        with patch.dict('os.environ', {'APPDATA': 'C:\\Users\\Test\\AppData\\Roaming'}):
            manager = ConfigManager()
            expected = Path("C:\\Users\\Test\\AppData\\Roaming\\dj-music-cleanup")
            assert str(manager._get_user_config_dir()) == str(expected)
    
    @patch('platform.system')
    def test_user_config_dir_macos(self, mock_system):
        """Test macOS user config directory."""
        mock_system.return_value = "Darwin"
        
        manager = ConfigManager()
        assert "Library/Application Support/dj-music-cleanup" in str(manager._get_user_config_dir())
    
    @patch('platform.system')
    def test_user_config_dir_linux(self, mock_system):
        """Test Linux user config directory."""
        mock_system.return_value = "Linux"
        
        with patch.dict('os.environ', {'XDG_CONFIG_HOME': '/home/test/.config'}):
            manager = ConfigManager()
            expected = Path("/home/test/.config/dj-music-cleanup")
            assert str(manager._get_user_config_dir()) == str(expected)
    
    def test_merge_configs(self, config_manager):
        """Test configuration merging logic."""
        base = {
            "audio": {"min_health_score": 50.0, "fingerprint_algorithm": "chromaprint"},
            "ui": {"log_level": "INFO"}
        }
        
        override = {
            "audio": {"min_health_score": 60.0},
            "processing": {"batch_size": 100}
        }
        
        merged = config_manager._merge_configs(base, override)
        
        assert merged["audio"]["min_health_score"] == 60.0  # Overridden
        assert merged["audio"]["fingerprint_algorithm"] == "chromaprint"  # Preserved
        assert merged["ui"]["log_level"] == "INFO"  # Preserved
        assert merged["processing"]["batch_size"] == 100  # New
    
    def test_get_config_singleton(self):
        """Test get_config_manager singleton pattern."""
        manager1 = get_config_manager()
        manager2 = get_config_manager()
        
        assert manager1 is manager2
    
    def test_get_config_convenience(self):
        """Test get_config convenience function."""
        config = get_config()
        assert isinstance(config, MusicCleanupConfig)
        
        # With overrides
        config = get_config(dry_run=True, batch_size=200)
        assert config.dry_run == True
        # Note: batch_size override handling would need to be implemented
    
    def test_invalid_json_handling(self, config_manager, temp_dirs):
        """Test handling of invalid JSON in config files."""
        _, config_dir, _ = temp_dirs
        
        # Create invalid JSON
        invalid_file = config_dir / "invalid.json"
        invalid_file.write_text("{ invalid json }")
        
        # Should fall back to defaults
        config = config_manager.load_config(project_config="invalid.json")
        assert isinstance(config, MusicCleanupConfig)
        assert config.audio.fingerprint_algorithm == "chromaprint"  # Default
    
    def test_missing_config_file(self, config_manager):
        """Test handling of missing config files."""
        # Should fall back to defaults
        config = config_manager.load_config(project_config="nonexistent.json")
        assert isinstance(config, MusicCleanupConfig)
        assert config.audio.fingerprint_algorithm == "chromaprint"  # Default