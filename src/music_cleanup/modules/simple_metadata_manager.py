"""
Simple Metadata Manager

Basic metadata extraction for backward compatibility.
"""

import logging
from pathlib import Path
from typing import Dict, Optional, Any

try:
    import mutagen
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False


class SimpleMetadataManager:
    """Simple metadata extraction manager."""
    
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        if not MUTAGEN_AVAILABLE:
            self.logger.warning("Mutagen not available - metadata extraction limited")
    
    def extract_metadata(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Extract basic metadata from audio file.
        
        Args:
            file_path: Path to audio file
            
        Returns:
            Dictionary with metadata or None if extraction fails
        """
        if not MUTAGEN_AVAILABLE:
            return self._extract_basic_metadata(file_path)
        
        try:
            audio_file = mutagen.File(file_path)
            if not audio_file:
                return None
            
            metadata = {}
            
            # Extract basic info
            if hasattr(audio_file, 'info'):
                metadata['duration'] = getattr(audio_file.info, 'length', 0)
                metadata['bitrate'] = getattr(audio_file.info, 'bitrate', 0)
            
            # Extract tags
            if hasattr(audio_file, 'tags') and audio_file.tags:
                metadata['title'] = self._get_tag_value(audio_file.tags, ['TIT2', 'TITLE'])
                metadata['artist'] = self._get_tag_value(audio_file.tags, ['TPE1', 'ARTIST'])
                metadata['album'] = self._get_tag_value(audio_file.tags, ['TALB', 'ALBUM'])
                metadata['genre'] = self._get_tag_value(audio_file.tags, ['TCON', 'GENRE'])
                metadata['year'] = self._get_tag_value(audio_file.tags, ['TDRC', 'DATE', 'YEAR'])
            
            return metadata
            
        except Exception as e:
            self.logger.error(f"Error extracting metadata from {file_path}: {e}")
            return None
    
    def _extract_basic_metadata(self, file_path: str) -> Dict:
        """Extract basic file information without mutagen."""
        file_path_obj = Path(file_path)
        return {
            'title': file_path_obj.stem,
            'duration': 0,
            'bitrate': 0,
            'format': file_path_obj.suffix
        }
    
    def _get_tag_value(self, tags, tag_names):
        """Get tag value from multiple possible tag names."""
        for tag_name in tag_names:
            if tag_name in tags:
                value = tags[tag_name]
                if isinstance(value, list) and value:
                    return str(value[0])
                elif value:
                    return str(value)
        return None