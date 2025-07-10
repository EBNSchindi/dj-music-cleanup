"""
Core configuration module for DJ Music Library Cleanup Tool
"""
import os
from pathlib import Path
from typing import List, Dict, Any
import json
from datetime import datetime


class Config:
    """Central configuration management"""
    
    # Default configuration
    DEFAULT_CONFIG = {
        'protected_folders': [],  # Folders that should never be modified
        'source_folders': [],     # Folders to scan for music
        'target_folder': 'D:\\Bereinigt',
        'quality_priority': ['flac', 'wav', 'mp3_320', 'mp3_256', 'mp3_192', 'mp3_128', 'mp3_vbr', 'other'],
        'genre_mapping': 'auto',
        'decade_fallback': '2020s',
        'batch_size': 1000,
        'enable_musicbrainz': True,
        'create_backup_list': True,
        'multiprocessing_workers': 4,
        'fingerprint_cache_db': 'fingerprints.db',
        'log_level': 'INFO',
        'dry_run': False,
        'resume_enabled': True,
        'min_file_size_mb': 0.5,  # Ignore files smaller than this
        'max_file_size_mb': 50,   # Ignore files larger than this
        'supported_formats': ['.mp3', '.flac', '.wav', '.m4a', '.ogg', '.wma', '.aac'],
        'genre_categories': {
            'House': ['house', 'deep house', 'tech house', 'progressive house', 'electro house', 'future house'],
            'Techno': ['techno', 'minimal techno', 'detroit techno', 'acid techno'],
            'Hip-Hop': ['hip hop', 'hip-hop', 'rap', 'trap', 'boom bap'],
            'Pop': ['pop', 'dance pop', 'electropop', 'synthpop'],
            'Electronic': ['electronic', 'edm', 'electronica', 'ambient', 'experimental'],
            'Trance': ['trance', 'uplifting trance', 'progressive trance', 'psytrance'],
            'Drum & Bass': ['drum and bass', 'drum & bass', 'dnb', 'jungle'],
            'Dubstep': ['dubstep', 'brostep', 'future garage'],
            'Reggae': ['reggae', 'dub', 'dancehall'],
            'Rock': ['rock', 'alternative rock', 'indie rock', 'punk rock'],
            'Unknown': []
        }
    }
    
    def __init__(self, config_file: str = None):
        """Initialize configuration"""
        self.config_file = config_file or 'music_cleanup_config.json'
        self.config = self.DEFAULT_CONFIG.copy()
        self.load_config()
        
    def load_config(self):
        """Load configuration from file if exists"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                    self.config.update(user_config)
                print(f"Configuration loaded from {self.config_file}")
            except Exception as e:
                print(f"Error loading config file: {e}")
                print("Using default configuration")
    
    def save_config(self):
        """Save current configuration to file"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4)
            print(f"Configuration saved to {self.config_file}")
        except Exception as e:
            print(f"Error saving config file: {e}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any):
        """Set configuration value"""
        self.config[key] = value
    
    def update(self, updates: Dict[str, Any]):
        """Update multiple configuration values"""
        self.config.update(updates)
    
    def validate(self) -> List[str]:
        """Validate configuration and return list of errors"""
        errors = []
        
        # Check target folder
        if not self.config.get('target_folder'):
            errors.append("Target folder not specified")
            
        # Check source folders
        if not self.config.get('source_folders'):
            errors.append("No source folders specified")
        else:
            for folder in self.config['source_folders']:
                if not os.path.exists(folder):
                    errors.append(f"Source folder does not exist: {folder}")
        
        # Check protected folders
        for folder in self.config.get('protected_folders', []):
            if not os.path.exists(folder):
                errors.append(f"Protected folder does not exist: {folder}")
        
        # Validate batch size
        if self.config.get('batch_size', 0) < 1:
            errors.append("Batch size must be at least 1")
        
        # Validate workers
        if self.config.get('multiprocessing_workers', 0) < 1:
            errors.append("Number of workers must be at least 1")
            
        return errors
    
    def get_genre_category(self, genre: str) -> str:
        """Map a genre string to a category"""
        if not genre:
            return 'Unknown'
            
        genre_lower = genre.lower()
        
        for category, keywords in self.config['genre_categories'].items():
            for keyword in keywords:
                if keyword in genre_lower:
                    return category
        
        return 'Unknown'
    
    def get_decade_from_year(self, year: Any) -> str:
        """Convert year to decade string"""
        try:
            year_int = int(year)
            if year_int < 1950:
                return 'Pre-1950s'
            elif year_int >= 2020:
                return '2020s'
            else:
                decade = (year_int // 10) * 10
                return f'{decade}s'
        except:
            return self.config.get('decade_fallback', '2020s')
    
    def is_protected_path(self, path: str) -> bool:
        """Check if a path is within a protected folder"""
        path = Path(path).resolve()
        for protected in self.config.get('protected_folders', []):
            protected_path = Path(protected).resolve()
            try:
                path.relative_to(protected_path)
                return True
            except ValueError:
                continue
        return False
    
    def get_quality_score(self, format_info: Dict[str, Any]) -> int:
        """Get quality score for a file format"""
        format_type = format_info.get('format', '').lower()
        bitrate = format_info.get('bitrate', 0)
        
        # Map formats to quality tiers
        if format_type in ['flac', 'wav']:
            return 1000
        elif format_type == 'mp3':
            if bitrate >= 320000:
                return 900
            elif bitrate >= 256000:
                return 800
            elif bitrate >= 192000:
                return 700
            elif bitrate >= 128000:
                return 600
            else:
                return 500
        elif format_type in ['m4a', 'aac']:
            return 650
        elif format_type == 'ogg':
            return 640
        else:
            return 400
    
    def create_example_config(self, filename: str = 'example_config.json'):
        """Create an example configuration file"""
        example_config = {
            'protected_folders': [
                'D:\\Core-Library',
                'D:\\Master-Collection',
                'D:\\DJ-Sets'
            ],
            'source_folders': [
                'D:\\Music',
                'D:\\Downloads\\Music',
                'E:\\Backup\\Music'
            ],
            'target_folder': 'D:\\Bereinigt',
            'quality_priority': ['flac', 'wav', 'mp3_320', 'mp3_256', 'mp3_192', 'mp3_128'],
            'batch_size': 1000,
            'multiprocessing_workers': 4,
            'enable_musicbrainz': True,
            'dry_run': True,
            'log_level': 'INFO'
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(example_config, f, indent=4)
        
        print(f"Example configuration created: {filename}")


# Singleton instance
_config_instance = None

def get_config(config_file: str = None) -> Config:
    """Get configuration singleton instance"""
    global _config_instance
    if _config_instance is None:
        _config_instance = Config(config_file)
    return _config_instance