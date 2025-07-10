"""
Directory Manager for DJ Music Cleanup Tool

Handles creation and management of standard output directories.
Provides consistent directory structure across the application.
"""

import logging
import os
from pathlib import Path
from typing import Dict, Optional, Tuple
from dataclasses import dataclass

from ..utils.decorators import handle_errors, validate_path


@dataclass
class DirectoryPaths:
    """Standard directory paths for the cleanup tool."""
    
    # Main directories
    organized_dir: Path
    rejected_dir: Path
    
    # Rejected subdirectories
    duplicates_dir: Path
    low_quality_dir: Path
    corrupted_dir: Path
    
    # Optional directories
    workspace_dir: Optional[Path] = None
    backup_dir: Optional[Path] = None
    
    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary with string paths."""
        return {
            'organized_dir': str(self.organized_dir),
            'rejected_dir': str(self.rejected_dir),
            'duplicates_dir': str(self.duplicates_dir),
            'low_quality_dir': str(self.low_quality_dir),
            'corrupted_dir': str(self.corrupted_dir),
            'workspace_dir': str(self.workspace_dir) if self.workspace_dir else None,
            'backup_dir': str(self.backup_dir) if self.backup_dir else None,
        }


class DirectoryManager:
    """
    Manages directory structure for DJ Music Cleanup Tool.
    
    Features:
    - Creates standard directory structure
    - Validates directory permissions
    - Provides path resolution
    - Handles directory cleanup
    """
    
    def __init__(self, 
                 base_path: Optional[str] = None,
                 auto_create: bool = True):
        """
        Initialize directory manager.
        
        Args:
            base_path: Base directory for all operations (defaults to current dir)
            auto_create: Whether to automatically create directories
        """
        self.base_path = Path(base_path or os.getcwd())
        self.auto_create = auto_create
        self.logger = logging.getLogger(__name__)
        
        # Standard directory structure
        self._paths: Optional[DirectoryPaths] = None
        
        self.logger.info(f"DirectoryManager initialized with base: {self.base_path}")
    
    @handle_errors(return_on_error=None)
    def setup_directories(self, config: Dict) -> Optional[DirectoryPaths]:
        """
        Setup standard directory structure from configuration.
        
        Args:
            config: Configuration dictionary with output_directories section
            
        Returns:
            DirectoryPaths object with all paths, or None on error
        """
        output_config = config.get('output_directories', {})
        
        # Resolve paths relative to base directory
        organized_dir = self._resolve_path(
            output_config.get('organized_dir', './organized')
        )
        rejected_dir = self._resolve_path(
            output_config.get('rejected_dir', './rejected')
        )
        
        # Create DirectoryPaths object
        paths = DirectoryPaths(
            organized_dir=organized_dir,
            rejected_dir=rejected_dir,
            duplicates_dir=rejected_dir / 'duplicates',
            low_quality_dir=rejected_dir / 'low_quality',
            corrupted_dir=rejected_dir / 'corrupted'
        )
        
        # Add optional directories
        if workspace_dir := config.get('workspace_directory'):
            paths.workspace_dir = self._resolve_path(workspace_dir)
        
        # Create directories if requested
        if output_config.get('auto_create_dirs', True) and self.auto_create:
            self._create_directory_structure(paths)
        
        # Validate directories
        if not self._validate_directories(paths):
            return None
        
        self._paths = paths
        self.logger.info("Directory structure setup completed")
        return paths
    
    def get_paths(self) -> Optional[DirectoryPaths]:
        """Get current directory paths."""
        return self._paths
    
    @handle_errors(log_level="warning")
    def ensure_directory_exists(self, directory: Path) -> bool:
        """
        Ensure a directory exists, creating it if necessary.
        
        Args:
            directory: Path to directory
            
        Returns:
            True if directory exists or was created, False otherwise
        """
        if directory.exists():
            if not directory.is_dir():
                self.logger.error(f"Path exists but is not a directory: {directory}")
                return False
            return True
        
        if self.auto_create:
            try:
                directory.mkdir(parents=True, exist_ok=True)
                self.logger.info(f"Created directory: {directory}")
                return True
            except PermissionError:
                self.logger.error(f"Permission denied creating directory: {directory}")
                return False
            except OSError as e:
                self.logger.error(f"Failed to create directory {directory}: {e}")
                return False
        else:
            self.logger.warning(f"Directory does not exist: {directory}")
            return False
    
    def get_categorized_path(self, category: str) -> Optional[Path]:
        """
        Get path for a specific file category.
        
        Args:
            category: File category ('organized', 'duplicates', 'low_quality', 'corrupted')
            
        Returns:
            Path for the category, or None if invalid category
        """
        if not self._paths:
            self.logger.error("Directory paths not initialized")
            return None
        
        category_map = {
            'organized': self._paths.organized_dir,
            'duplicates': self._paths.duplicates_dir,
            'low_quality': self._paths.low_quality_dir,
            'corrupted': self._paths.corrupted_dir,
        }
        
        return category_map.get(category)
    
    def create_genre_structure(self, genre: str, decade: Optional[str] = None) -> Path:
        """
        Create genre-based directory structure in organized folder.
        
        Args:
            genre: Music genre name
            decade: Optional decade (e.g., '2020s')
            
        Returns:
            Path to the created directory
        """
        if not self._paths:
            raise ValueError("Directory paths not initialized")
        
        # Sanitize genre name
        safe_genre = self._sanitize_name(genre)
        genre_path = self._paths.organized_dir / safe_genre
        
        if decade:
            safe_decade = self._sanitize_name(decade)
            target_path = genre_path / safe_decade
        else:
            target_path = genre_path
        
        self.ensure_directory_exists(target_path)
        return target_path
    
    def get_directory_stats(self) -> Dict[str, Dict[str, int]]:
        """
        Get statistics about directory contents.
        
        Returns:
            Dictionary with file counts and sizes per directory
        """
        if not self._paths:
            return {}
        
        stats = {}
        
        for name, path_attr in [
            ('organized', 'organized_dir'),
            ('duplicates', 'duplicates_dir'),
            ('low_quality', 'low_quality_dir'),
            ('corrupted', 'corrupted_dir')
        ]:
            directory = getattr(self._paths, path_attr)
            if directory.exists():
                file_count = sum(1 for f in directory.rglob('*') if f.is_file())
                total_size = sum(f.stat().st_size for f in directory.rglob('*') if f.is_file())
                stats[name] = {
                    'file_count': file_count,
                    'total_size_bytes': total_size,
                    'total_size_mb': total_size / (1024 * 1024)
                }
            else:
                stats[name] = {
                    'file_count': 0,
                    'total_size_bytes': 0,
                    'total_size_mb': 0.0
                }
        
        return stats
    
    def cleanup_empty_directories(self) -> int:
        """
        Remove empty directories from the organized structure.
        
        Returns:
            Number of directories removed
        """
        if not self._paths:
            return 0
        
        removed_count = 0
        
        # Only clean up in organized directory to preserve structure
        for directory in self._paths.organized_dir.rglob('*'):
            if directory.is_dir() and not any(directory.iterdir()):
                try:
                    directory.rmdir()
                    removed_count += 1
                    self.logger.debug(f"Removed empty directory: {directory}")
                except OSError:
                    # Directory might not be empty or have permission issues
                    pass
        
        self.logger.info(f"Cleaned up {removed_count} empty directories")
        return removed_count
    
    def _resolve_path(self, path_str: str) -> Path:
        """Resolve path relative to base directory."""
        path = Path(path_str)
        if path.is_absolute():
            return path
        return self.base_path / path
    
    def _create_directory_structure(self, paths: DirectoryPaths) -> None:
        """Create all directories in the structure."""
        directories_to_create = [
            paths.organized_dir,
            paths.rejected_dir,
            paths.duplicates_dir,
            paths.low_quality_dir,
            paths.corrupted_dir
        ]
        
        if paths.workspace_dir:
            directories_to_create.append(paths.workspace_dir)
        
        if paths.backup_dir:
            directories_to_create.append(paths.backup_dir)
        
        for directory in directories_to_create:
            self.ensure_directory_exists(directory)
    
    def _validate_directories(self, paths: DirectoryPaths) -> bool:
        """Validate that all required directories are accessible."""
        required_dirs = [
            paths.organized_dir,
            paths.rejected_dir,
            paths.duplicates_dir,
            paths.low_quality_dir,
            paths.corrupted_dir
        ]
        
        for directory in required_dirs:
            if not directory.exists():
                self.logger.error(f"Required directory does not exist: {directory}")
                return False
            
            if not os.access(directory, os.R_OK | os.W_OK):
                self.logger.error(f"Insufficient permissions for directory: {directory}")
                return False
        
        return True
    
    def _sanitize_name(self, name: str) -> str:
        """Sanitize name for use as directory name."""
        # Remove or replace invalid characters
        invalid_chars = '<>:"/\\|?*'
        sanitized = ''.join(c if c not in invalid_chars else '_' for c in name)
        
        # Remove leading/trailing whitespace and dots
        sanitized = sanitized.strip(' .')
        
        # Ensure not empty
        if not sanitized:
            sanitized = 'Unknown'
        
        return sanitized