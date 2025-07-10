"""
Simple File Organizer

Basic file organization for backward compatibility.
"""

import logging
import shutil
from pathlib import Path
from typing import Dict, Optional


class SimpleFileOrganizer:
    """Simple file organizer with basic folder structure."""
    
    def __init__(self, target_root: str, dry_run: bool = False):
        self.target_root = Path(target_root)
        self.dry_run = dry_run
        self.logger = logging.getLogger(__name__)
    
    def organize_file(self, file_path: Path, metadata: Dict, quality_score: float) -> Optional[Path]:
        """
        Organize a file into target structure.
        
        Args:
            file_path: Source file path
            metadata: File metadata
            quality_score: Quality score (0-100)
            
        Returns:
            Destination path if successful, None otherwise
        """
        try:
            # Determine destination folder based on metadata
            artist = metadata.get('artist', 'Unknown Artist')
            album = metadata.get('album', 'Unknown Album')
            
            # Clean up folder names
            artist = self._clean_folder_name(artist)
            album = self._clean_folder_name(album)
            
            # Create destination path
            dest_folder = self.target_root / artist / album
            dest_file = dest_folder / file_path.name
            
            # Handle name conflicts
            counter = 1
            while dest_file.exists():
                stem = file_path.stem
                suffix = file_path.suffix
                dest_file = dest_folder / f"{stem}_{counter}{suffix}"
                counter += 1
            
            # Create destination folder
            if not self.dry_run:
                dest_folder.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, dest_file)
            else:
                self.logger.info(f"[DRY RUN] Would copy: {file_path} → {dest_file}")
            
            return dest_file
            
        except Exception as e:
            self.logger.error(f"Error organizing {file_path}: {e}")
            return None
    
    def _clean_folder_name(self, name: str) -> str:
        """Clean folder name by removing invalid characters."""
        if not name:
            return "Unknown"
        
        # Remove invalid characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, '_')
        
        # Limit length
        return name[:100].strip()