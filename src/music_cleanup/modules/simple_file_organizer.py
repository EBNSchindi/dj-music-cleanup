"""
Simple File Organizer

Basic file organization for backward compatibility.
"""

import logging
import re
import shutil
from pathlib import Path
from typing import Dict, Optional


class SimpleFileOrganizer:
    """Simple file organizer with basic folder structure."""
    
    def __init__(self, target_root: str, dry_run: bool = False, structure: str = "genre/decade", 
                 naming_pattern: str = "{year} - {artist} - {title} [QS{score}%]"):
        self.target_root = Path(target_root)
        self.dry_run = dry_run
        self.structure = structure
        self.naming_pattern = naming_pattern
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
            # Determine destination folder based on structure configuration
            if self.structure == "genre/decade":
                # Get genre and decade
                genre = metadata.get('genre', 'Unknown')
                year = metadata.get('year') or metadata.get('date', '')
                
                # Extract decade from year
                decade = self._get_decade(year)
                
                # Clean up folder names
                genre = self._clean_folder_name(genre)
                decade_folder = f"{decade}s" if decade != "Unknown" else "Unknown"
                
                # Create destination path: Genre/Decade/
                dest_folder = self.target_root / genre / decade_folder
            else:
                # Fallback to artist/album structure
                artist = metadata.get('artist', 'Unknown Artist')
                album = metadata.get('album', 'Unknown Album')
                
                # Clean up folder names
                artist = self._clean_folder_name(artist)
                album = self._clean_folder_name(album)
                
                # Create destination path
                dest_folder = self.target_root / artist / album
            
            # Generate new filename based on naming pattern
            new_filename = self._generate_filename(metadata, quality_score, file_path.suffix)
            dest_file = dest_folder / new_filename
            
            # Handle name conflicts
            counter = 1
            original_dest = dest_file
            while dest_file.exists():
                stem = original_dest.stem
                suffix = original_dest.suffix
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
    
    def _get_decade(self, year) -> str:
        """Extract decade from year."""
        if not year:
            return "Unknown"
        
        # Convert to string and extract year
        year_str = str(year)
        
        # Try to extract 4-digit year
        import re
        year_match = re.search(r'(19\d{2}|20\d{2})', year_str)
        
        if year_match:
            year_int = int(year_match.group(1))
            decade = (year_int // 10) * 10
            return str(decade)
        
        return "Unknown"
    
    def _generate_filename(self, metadata: Dict, quality_score: float, extension: str) -> str:
        """Generate filename based on naming pattern."""
        # Extract metadata
        artist = metadata.get('artist', 'Unknown Artist')
        title = metadata.get('title', 'Unknown Title')
        album = metadata.get('album', 'Unknown Album')
        year = metadata.get('year', metadata.get('date', ''))
        genre = metadata.get('genre', 'Unknown')
        
        # Clean values for filename
        artist = self._clean_filename_part(artist)
        title = self._clean_filename_part(title)
        album = self._clean_filename_part(album)
        genre = self._clean_filename_part(genre)
        
        # Extract year properly
        year_str = ''
        if year:
            year_str = str(year)
            # Try to extract 4-digit year
            year_match = re.search(r'(19\d{2}|20\d{2})', year_str)
            if year_match:
                year_str = year_match.group(1)
            else:
                year_str = ''
        
        # Format the filename using the pattern
        filename = self.naming_pattern
        filename = filename.replace('{artist}', artist)
        filename = filename.replace('{title}', title)
        filename = filename.replace('{album}', album)
        filename = filename.replace('{year}', year_str)
        filename = filename.replace('{genre}', genre)
        filename = filename.replace('{score}', f"{int(quality_score)}")
        
        # Clean up the filename
        # Remove empty year placeholder and extra hyphens
        filename = re.sub(r'^[\s-]+', '', filename)  # Remove leading spaces/hyphens
        filename = re.sub(r'\s*-\s*-\s*', ' - ', filename)  # Fix double hyphens
        filename = re.sub(r'\s*\[\s*\]', '', filename)  # Remove empty brackets
        filename = re.sub(r'\s+', ' ', filename).strip()  # Fix multiple spaces
        
        return filename + extension
    
    def _clean_filename_part(self, text: str) -> str:
        """Clean a text part for use in filename."""
        if not text:
            return ""
        
        # Remove invalid filename characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            text = text.replace(char, '_')
        
        # Remove multiple spaces
        text = ' '.join(text.split())
        
        # Limit length
        return text[:50].strip()