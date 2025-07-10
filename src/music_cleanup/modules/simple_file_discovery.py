"""
Simple File Discovery Module

Basic file discovery implementation for backward compatibility.
"""

import logging
from pathlib import Path
from typing import Generator, List

from ..core.constants import SUPPORTED_AUDIO_FORMATS


class SimpleFileDiscovery:
    """Simple file discovery for audio files."""
    
    def __init__(self, streaming_config):
        self.streaming_config = streaming_config
        self.logger = logging.getLogger(__name__)
        self.supported_extensions = set(SUPPORTED_AUDIO_FORMATS.keys())
    
    def discover_files_streaming(self, source_folders: List[str]) -> Generator[str, None, None]:
        """
        Discover audio files in source folders.
        
        Args:
            source_folders: List of directories to search
            
        Yields:
            Audio file paths
        """
        for folder in source_folders:
            folder_path = Path(folder)
            if not folder_path.exists():
                self.logger.warning(f"Source folder does not exist: {folder}")
                continue
            
            # Recursive search for audio files
            for file_path in folder_path.rglob('*'):
                if file_path.is_file() and file_path.suffix.lower() in self.supported_extensions:
                    yield str(file_path)