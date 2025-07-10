"""
Centralized Configuration Management

Manages all configuration sources:
- Default settings
- Project configs (config/*.json)
- User settings (~/.config/dj-music-cleanup/)
- CLI overrides
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional, Union
from dataclasses import dataclass, asdict
import platform


@dataclass
class AudioConfig:
    """Audio processing configuration"""
    fingerprint_algorithm: str = "chromaprint"
    fingerprint_length: int = 120
    duplicate_action: str = "move"
    duplicate_similarity: float = 0.95
    min_health_score: float = 50.0
    silence_threshold: float = 0.001
    defect_sample_duration: float = 30.0
    supported_formats: list = None
    
    def __post_init__(self):
        if self.supported_formats is None:
            self.supported_formats = ['.mp3', '.flac', '.wav', '.m4a', '.aac', '.ogg', '.wma']


@dataclass 
class ProcessingConfig:
    """Processing pipeline configuration"""
    batch_size: int = 50
    max_workers: int = 4
    memory_limit_mb: int = 1024
    enable_recovery: bool = True
    checkpoint_interval: int = 300
    integrity_level: str = "checksum"


@dataclass
class OutputDirectoriesConfig:
    """Output directories configuration"""
    organized_dir: str = "./organized"
    rejected_dir: str = "./rejected"
    duplicates_dir: str = "./rejected/duplicates"
    low_quality_dir: str = "./rejected/low_quality"
    corrupted_dir: str = "./rejected/corrupted"
    auto_create_dirs: bool = True


@dataclass
class OrganizationConfig:
    """File organization configuration"""
    structure_template: str = "{genre}/{artist}/{artist} - {title}"
    quality_indicators: bool = True
    handle_duplicates: bool = True
    quarantine_defective: bool = True
    create_backups: bool = False


@dataclass
class UIConfig:
    """User interface configuration"""
    progress_mode: str = "simple"
    log_level: str = "INFO"
    color_output: bool = True
    verbose_errors: bool = False


@dataclass
class MusicCleanupConfig:
    """Complete configuration for DJ Music Cleanup Tool"""
    audio: AudioConfig = None
    processing: ProcessingConfig = None
    output_directories: OutputDirectoriesConfig = None
    organization: OrganizationConfig = None
    ui: UIConfig = None
    
    # Runtime settings
    output_directory: str = ""  # Deprecated: use output_directories.organized_dir
    workspace_directory: str = "./workspace"
    dry_run: bool = False
    
    def __post_init__(self):
        if self.audio is None:
            self.audio = AudioConfig()
        if self.processing is None:
            self.processing = ProcessingConfig()
        if self.output_directories is None:
            self.output_directories = OutputDirectoriesConfig()
        if self.organization is None:
            self.organization = OrganizationConfig()
        if self.ui is None:
            self.ui = UIConfig()


class ConfigManager:
    """
    Centralized configuration manager with hierarchical loading:
    1. Default settings
    2. Project configs (config/*.json)
    3. User settings (~/.config/dj-music-cleanup/)
    4. CLI arguments
    """
    
    def __init__(self, project_root: Optional[Path] = None):
        self.logger = logging.getLogger(__name__)
        
        # Determine project root
        if project_root is None:
            # Try to find project root by looking for setup.py or pyproject.toml
            current = Path(__file__).parent
            while current != current.parent:
                if (current / "setup.py").exists() or (current / "pyproject.toml").exists():
                    project_root = current
                    break
                current = current.parent
            else:
                project_root = Path(__file__).parent.parent.parent
        
        self.project_root = project_root
        self.config_dir = project_root / "config"
        self.user_config_dir = self._get_user_config_dir()
        
        # Ensure directories exist
        self.user_config_dir.mkdir(parents=True, exist_ok=True)
        
        self._config: Optional[MusicCleanupConfig] = None
        
        self.logger.info(f"ConfigManager initialized")
        self.logger.info(f"  Project root: {self.project_root}")
        self.logger.info(f"  User config: {self.user_config_dir}")
    
    def _get_user_config_dir(self) -> Path:
        """Get platform-appropriate user config directory"""
        system = platform.system()
        
        if system == "Windows":
            base = Path(os.environ.get("APPDATA", "~"))
        elif system == "Darwin":  # macOS
            base = Path("~/Library/Application Support")
        else:  # Linux and others
            base = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config"))
        
        return (base / "dj-music-cleanup").expanduser()
    
    def load_config(self, 
                   project_config: Optional[str] = None,
                   user_overrides: Optional[Dict] = None,
                   cli_overrides: Optional[Dict] = None) -> MusicCleanupConfig:
        """
        Load configuration from all sources with proper precedence.
        
        Args:
            project_config: Specific project config file name (e.g., "production.json")
            user_overrides: User-specific settings
            cli_overrides: Command-line argument overrides
            
        Returns:
            Complete configuration object
        """
        self.logger.info("Loading configuration from all sources...")
        
        # 1. Start with defaults
        config = MusicCleanupConfig()
        config_dict = asdict(config)
        
        # 2. Load project config
        if project_config:
            project_config_path = self.config_dir / project_config
        else:
            project_config_path = self.config_dir / "default.json"
        
        if project_config_path.exists():
            project_settings = self._load_json_config(project_config_path)
            config_dict = self._merge_configs(config_dict, project_settings)
            self.logger.info(f"Loaded project config: {project_config_path}")
        
        # 3. Load user settings
        user_config_path = self.user_config_dir / "settings.json"
        if user_config_path.exists():
            user_settings = self._load_json_config(user_config_path)
            config_dict = self._merge_configs(config_dict, user_settings)
            self.logger.info(f"Loaded user config: {user_config_path}")
        
        # 4. Apply user overrides
        if user_overrides:
            config_dict = self._merge_configs(config_dict, user_overrides)
            self.logger.debug("Applied user overrides")
        
        # 5. Apply CLI overrides
        if cli_overrides:
            config_dict = self._merge_configs(config_dict, cli_overrides)
            self.logger.debug("Applied CLI overrides")
        
        # Convert back to dataclass
        self._config = self._dict_to_config(config_dict)
        
        self.logger.info("Configuration loaded successfully")
        return self._config
    
    def _load_json_config(self, config_path: Path) -> Dict[str, Any]:
        """Load JSON configuration file"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load config {config_path}: {e}")
            return {}
    
    def _merge_configs(self, base: Dict, override: Dict) -> Dict:
        """Deep merge configuration dictionaries"""
        result = base.copy()
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def _dict_to_config(self, config_dict: Dict) -> MusicCleanupConfig:
        """Convert dictionary to config dataclass"""
        try:
            # Extract nested configs
            audio_dict = config_dict.get('audio', {})
            processing_dict = config_dict.get('processing', {})
            organization_dict = config_dict.get('organization', {})
            ui_dict = config_dict.get('ui', {})
            
            # Create nested dataclasses
            audio_config = AudioConfig(**audio_dict)
            processing_config = ProcessingConfig(**processing_dict)
            organization_config = OrganizationConfig(**organization_dict)
            ui_config = UIConfig(**ui_dict)
            
            # Create main config
            main_config = MusicCleanupConfig(
                audio=audio_config,
                processing=processing_config,
                organization=organization_config,
                ui=ui_config
            )
            
            # Set top-level attributes
            for key, value in config_dict.items():
                if key not in ['audio', 'processing', 'organization', 'ui']:
                    if hasattr(main_config, key):
                        setattr(main_config, key, value)
            
            return main_config
            
        except Exception as e:
            self.logger.error(f"Failed to convert config dict: {e}")
            return MusicCleanupConfig()
    
    def save_user_settings(self, settings: Dict[str, Any]) -> bool:
        """Save user-specific settings"""
        try:
            user_config_path = self.user_config_dir / "settings.json"
            
            # Load existing settings
            existing = {}
            if user_config_path.exists():
                existing = self._load_json_config(user_config_path)
            
            # Merge with new settings
            merged = self._merge_configs(existing, settings)
            
            # Save to file
            with open(user_config_path, 'w', encoding='utf-8') as f:
                json.dump(merged, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"User settings saved to {user_config_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save user settings: {e}")
            return False
    
    def get_config(self) -> MusicCleanupConfig:
        """Get current configuration (load if not already loaded)"""
        if self._config is None:
            self._config = self.load_config()
        return self._config
    
    def validate_config(self, config: MusicCleanupConfig) -> list:
        """Validate configuration and return list of issues"""
        issues = []
        
        # Validate audio config
        if config.audio.duplicate_similarity < 0.5 or config.audio.duplicate_similarity > 1.0:
            issues.append("duplicate_similarity must be between 0.5 and 1.0")
        
        if config.audio.min_health_score < 0 or config.audio.min_health_score > 100:
            issues.append("min_health_score must be between 0 and 100")
        
        # Validate processing config
        if config.processing.batch_size < 1:
            issues.append("batch_size must be at least 1")
        
        if config.processing.max_workers < 1:
            issues.append("max_workers must be at least 1")
        
        # Validate paths
        if config.output_directory and not Path(config.output_directory).parent.exists():
            issues.append(f"Output directory parent does not exist: {config.output_directory}")
        
        return issues
    
    def create_default_user_config(self) -> bool:
        """Create default user configuration file"""
        try:
            default_settings = {
                "audio": {
                    "fingerprint_algorithm": "chromaprint",
                    "duplicate_action": "move"
                },
                "ui": {
                    "progress_mode": "simple",
                    "log_level": "INFO"
                }
            }
            
            return self.save_user_settings(default_settings)
            
        except Exception as e:
            self.logger.error(f"Failed to create default user config: {e}")
            return False


# Global config manager instance
_config_manager: Optional[ConfigManager] = None

def get_config_manager() -> ConfigManager:
    """Get global config manager instance"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager

def get_config(project_config: Optional[str] = None, **overrides) -> MusicCleanupConfig:
    """Convenience function to get configuration"""
    manager = get_config_manager()
    return manager.load_config(project_config=project_config, cli_overrides=overrides)