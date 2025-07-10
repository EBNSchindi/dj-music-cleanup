"""
Directory Setup Utilities

Provides convenient functions for setting up the standard directory structure
for the DJ Music Cleanup Tool.
"""

import logging
from pathlib import Path
from typing import Dict, Optional, Tuple

from ..core.directory_manager import DirectoryManager, DirectoryPaths
from ..core.config_manager import get_config_manager


def setup_project_directories(
    base_path: Optional[str] = None,
    config_file: Optional[str] = None
) -> Tuple[DirectoryManager, DirectoryPaths]:
    """
    Setup the complete directory structure for the project.
    
    Args:
        base_path: Base directory for the project (defaults to current directory)
        config_file: Optional configuration file path
        
    Returns:
        Tuple of (DirectoryManager instance, DirectoryPaths with all paths)
        
    Raises:
        RuntimeError: If directory setup fails
    """
    logger = logging.getLogger(__name__)
    
    # Initialize directory manager
    dir_manager = DirectoryManager(base_path=base_path, auto_create=True)
    
    # Use simple default configuration for now
    config_dict = {
        'output_directories': {
            'organized_dir': './organized',
            'rejected_dir': './rejected',
            'duplicates_dir': './rejected/duplicates',
            'low_quality_dir': './rejected/low_quality',
            'corrupted_dir': './rejected/corrupted',
            'auto_create_dirs': True,
        },
        'workspace_directory': './workspace'
    }
    
    # Setup directories
    paths = dir_manager.setup_directories(config_dict)
    if not paths:
        raise RuntimeError("Failed to setup directory structure")
    
    logger.info(f"Project directories setup completed in: {dir_manager.base_path}")
    
    return dir_manager, paths


def ensure_standard_structure() -> bool:
    """
    Ensure the standard directory structure exists in the current directory.
    
    Returns:
        True if structure was created/verified, False on error
    """
    try:
        dir_manager, paths = setup_project_directories()
        
        # Create README files if they don't exist
        _create_readme_files(paths)
        
        return True
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to ensure directory structure: {e}")
        return False


def get_directory_info(base_path: Optional[str] = None) -> Dict:
    """
    Get information about the current directory structure.
    
    Args:
        base_path: Base directory to analyze
        
    Returns:
        Dictionary with directory information and statistics
    """
    try:
        dir_manager = DirectoryManager(base_path=base_path, auto_create=False)
        
        # Use simple default configuration
        config_dict = {
            'output_directories': {
                'organized_dir': './organized',
                'rejected_dir': './rejected',
                'duplicates_dir': './rejected/duplicates',
                'low_quality_dir': './rejected/low_quality',
                'corrupted_dir': './rejected/corrupted',
                'auto_create_dirs': False,  # Don't auto-create when just checking
            }
        }
        
        paths = dir_manager.setup_directories(config_dict)
        if not paths:
            return {'status': 'error', 'message': 'Failed to analyze directories'}
        
        # Get statistics
        stats = dir_manager.get_directory_stats()
        
        # Check which directories exist
        existence = {
            'organized': paths.organized_dir.exists(),
            'rejected': paths.rejected_dir.exists(),
            'duplicates': paths.duplicates_dir.exists(),
            'low_quality': paths.low_quality_dir.exists(),
            'corrupted': paths.corrupted_dir.exists(),
        }
        
        return {
            'status': 'success',
            'base_path': str(dir_manager.base_path),
            'paths': paths.to_dict(),
            'existence': existence,
            'statistics': stats,
            'all_directories_exist': all(existence.values())
        }
        
    except Exception as e:
        return {
            'status': 'error',
            'message': str(e)
        }


def clean_empty_directories(base_path: Optional[str] = None) -> int:
    """
    Clean up empty directories in the organized structure.
    
    Args:
        base_path: Base directory to clean
        
    Returns:
        Number of directories removed
    """
    try:
        dir_manager, _ = setup_project_directories(base_path)
        return dir_manager.cleanup_empty_directories()
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to clean empty directories: {e}")
        return 0


def _create_readme_files(paths: DirectoryPaths) -> None:
    """Create README files in directories if they don't exist."""
    
    organized_readme = paths.organized_dir / "README.md"
    if not organized_readme.exists():
        organized_readme.write_text("""# Organized Music Library

This directory contains the **best quality versions** of your music files, organized by genre and decade.

## Directory Structure

Files are organized as: `Genre/Decade/Artist - Title.format`

Example:
```
organized/
├── Electronic/
│   ├── 2020s/
│   ├── 2010s/
│   └── ...
├── House/
└── Rock/
```

## Quality Standards

- ✅ Highest bitrate among duplicates
- ✅ Best audio quality (lossless preferred)
- ✅ Complete metadata
- ✅ Integrity verified
- ✅ Above quality threshold

This is your **production-ready** music library.
""")
    
    rejected_readme = paths.rejected_dir / "README.md"
    if not rejected_readme.exists():
        rejected_readme.write_text("""# Rejected Files

This directory contains files excluded from the main library:

## Subdirectories

- **duplicates/**: Lower quality versions of duplicate files
- **low_quality/**: Files below quality standards
- **corrupted/**: Files with technical issues

⚠️ **Review before deletion** to avoid data loss!
""")


def validate_directory_permissions(base_path: Optional[str] = None) -> Dict[str, bool]:
    """
    Validate that all directories have proper read/write permissions.
    
    Args:
        base_path: Base directory to validate
        
    Returns:
        Dictionary mapping directory names to permission status
    """
    import os
    
    try:
        _, paths = setup_project_directories(base_path)
        
        permissions = {}
        
        for name, directory in [
            ('organized', paths.organized_dir),
            ('rejected', paths.rejected_dir),
            ('duplicates', paths.duplicates_dir),
            ('low_quality', paths.low_quality_dir),
            ('corrupted', paths.corrupted_dir),
        ]:
            if directory.exists():
                permissions[name] = os.access(directory, os.R_OK | os.W_OK)
            else:
                permissions[name] = False
        
        return permissions
        
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to validate permissions: {e}")
        return {}


# Convenience function for CLI usage
def init_project_structure(verbose: bool = False) -> bool:
    """
    Initialize the complete project structure.
    
    Args:
        verbose: Whether to print detailed information
        
    Returns:
        True if successful, False otherwise
    """
    try:
        if verbose:
            print("🏗️  Initializing DJ Music Cleanup directory structure...")
        
        dir_manager, paths = setup_project_directories()
        
        if verbose:
            print(f"✅ Base directory: {dir_manager.base_path}")
            print(f"✅ Organized: {paths.organized_dir}")
            print(f"✅ Rejected: {paths.rejected_dir}")
            print(f"✅ Duplicates: {paths.duplicates_dir}")
            print(f"✅ Low Quality: {paths.low_quality_dir}")
            print(f"✅ Corrupted: {paths.corrupted_dir}")
            
            # Show statistics
            stats = dir_manager.get_directory_stats()
            if any(s['file_count'] > 0 for s in stats.values()):
                print("\\n📊 Current file counts:")
                for category, stat in stats.items():
                    if stat['file_count'] > 0:
                        print(f"   {category}: {stat['file_count']} files "
                              f"({stat['total_size_mb']:.1f} MB)")
            else:
                print("\\n📁 Directory structure ready for first use")
        
        return True
        
    except Exception as e:
        if verbose:
            print(f"❌ Failed to initialize structure: {e}")
        logging.getLogger(__name__).error(f"Structure initialization failed: {e}")
        return False