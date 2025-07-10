"""
Simple Fingerprinter

Basic fingerprinting implementation for backward compatibility.
"""

import hashlib
import logging
from pathlib import Path


class SimpleFingerprinter:
    """Simple hash-based fingerprinter."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def generate_fingerprint(self, file_path: str) -> str:
        """
        Generate simple hash-based fingerprint.
        
        Args:
            file_path: Path to audio file
            
        Returns:
            Hash-based fingerprint string
        """
        try:
            # Read first 64KB for basic fingerprinting
            with open(file_path, 'rb') as f:
                data = f.read(65536)  # 64KB
            
            # Create MD5 hash
            fingerprint = hashlib.md5(data).hexdigest()
            return fingerprint
            
        except Exception as e:
            self.logger.error(f"Error generating fingerprint for {file_path}: {e}")
            return None