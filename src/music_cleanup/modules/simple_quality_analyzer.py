"""
Simple Quality Analyzer

Basic quality analysis for backward compatibility.
"""

import logging
import os
from pathlib import Path


class SimpleQualityAnalyzer:
    """Simple file-based quality analyzer."""
    
    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    def analyze_quality(self, file_path: str) -> float:
        """
        Analyze basic file quality.
        
        Args:
            file_path: Path to audio file
            
        Returns:
            Quality score (0.0 to 1.0)
        """
        try:
            file_path_obj = Path(file_path)
            
            # Basic checks
            if not file_path_obj.exists():
                return 0.0
            
            file_size = file_path_obj.stat().st_size
            
            # Size-based quality assessment
            if file_size < 100 * 1024:  # Less than 100KB
                return 0.1
            elif file_size < 1024 * 1024:  # Less than 1MB
                return 0.5
            else:
                return 0.8
                
        except Exception as e:
            self.logger.error(f"Error analyzing quality of {file_path}: {e}")
            return 0.0