"""
Audio Fingerprint Processor for DJ Music Cleanup Tool

Handles Chromaprint fingerprint generation and caching.
CRITICAL: This is ALWAYS the first step in metadata processing.
"""

import logging
import time
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any
import hashlib

from ..utils.decorators import handle_errors, track_performance, retry
from ..core.unified_database import UnifiedDatabase


class FingerprintProcessor:
    """
    Chromaprint fingerprint processor with caching.
    
    Features:
    - Chromaprint fingerprint generation
    - Database caching with TTL
    - Error handling and retries
    - Performance tracking
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize fingerprint processor.
        
        Args:
            config: Metadata configuration
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Settings
        self.cache_ttl_days = config.get('cache_ttl_days', 30)
        self.fingerprint_length = config.get('fingerprint_length', 120)
        
        # Database for caching
        self.db = UnifiedDatabase()
        
        # Check for fpcalc tool
        self.fpcalc_available = self._check_fpcalc()
        
        self.logger.info(f"FingerprintProcessor initialized (fpcalc: {self.fpcalc_available})")
    
    def _check_fpcalc(self) -> bool:
        """Check if fpcalc (Chromaprint) is available"""
        try:
            result = subprocess.run(['fpcalc', '-version'], 
                                  capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            self.logger.warning("fpcalc not found - fingerprinting disabled")
            return False
    
    @handle_errors(return_on_error=None)
    @track_performance(threshold_ms=10000)
    @retry(max_attempts=3, delay=1.0)
    def generate_fingerprint(self, file_path: str) -> Optional[str]:
        """
        Generate Chromaprint fingerprint for audio file.
        
        Args:
            file_path: Path to audio file
            
        Returns:
            Fingerprint string or None on failure
        """
        if not self.fpcalc_available:
            return None
        
        try:
            # Run fpcalc to get fingerprint
            cmd = [
                'fpcalc',
                '-length', str(self.fingerprint_length),
                '-raw',
                file_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                check=True
            )
            
            # Parse output
            for line in result.stdout.strip().split('\\n'):
                if line.startswith('FINGERPRINT='):
                    fingerprint = line.replace('FINGERPRINT=', '')
                    self.logger.debug(f"Generated fingerprint for {Path(file_path).name}")
                    return fingerprint
            
            self.logger.warning(f"No fingerprint in fpcalc output for: {file_path}")
            return None
            
        except subprocess.TimeoutExpired:
            self.logger.error(f"Fingerprint generation timeout for: {file_path}")
            return None
        except subprocess.CalledProcessError as e:
            self.logger.error(f"fpcalc failed for {file_path}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Fingerprint generation error for {file_path}: {e}")
            return None
    
    @handle_errors(return_on_error=None)
    def check_cache(self, fingerprint: str) -> Optional['MetadataResult']:
        """
        Check if fingerprint is cached in database.
        
        Args:
            fingerprint: Chromaprint fingerprint
            
        Returns:
            Cached MetadataResult or None
        """
        try:
            from .metadata_manager import MetadataResult
            
            # Check database cache
            cached_data = self.db.get_fingerprint_metadata(fingerprint)
            if not cached_data:
                return None
            
            # Check TTL
            cache_age_days = (time.time() - cached_data.get('cached_at', 0)) / 86400
            if cache_age_days > self.cache_ttl_days:
                self.logger.debug(f"Cache expired for fingerprint (age: {cache_age_days:.1f} days)")
                return None
            
            # Reconstruct MetadataResult
            result = MetadataResult(
                artist=cached_data.get('artist', 'Unknown'),
                title=cached_data.get('title', 'Unknown'),
                year=cached_data.get('year', '0000'),
                genre=cached_data.get('genre', 'Unknown Genre'),
                album=cached_data.get('album'),
                source='acoustid_cached',
                confidence=cached_data.get('confidence', 0.0),
                fingerprint=fingerprint
            )
            
            self.logger.debug(f"Cache hit: {result.artist} - {result.title}")
            return result
            
        except Exception as e:
            self.logger.error(f"Cache check error: {e}")
            return None
    
    @handle_errors(log_level="warning")
    def cache_result(self, fingerprint: str, metadata_result: 'MetadataResult') -> None:
        """
        Cache successful fingerprint lookup result.
        
        Args:
            fingerprint: Chromaprint fingerprint
            metadata_result: MetadataResult to cache
        """
        try:
            cache_data = {
                'fingerprint': fingerprint,
                'artist': metadata_result.artist,
                'title': metadata_result.title,
                'year': metadata_result.year,
                'genre': metadata_result.genre,
                'album': metadata_result.album,
                'confidence': metadata_result.confidence,
                'source': metadata_result.source,
                'cached_at': time.time()
            }
            
            self.db.cache_fingerprint_metadata(fingerprint, cache_data)
            self.logger.debug(f"Cached result: {metadata_result.artist} - {metadata_result.title}")
            
        except Exception as e:
            self.logger.error(f"Cache storage error: {e}")
    
    def get_fingerprint_hash(self, fingerprint: str) -> str:
        """
        Generate hash for fingerprint (for shorter database keys).
        
        Args:
            fingerprint: Chromaprint fingerprint
            
        Returns:
            SHA256 hash of fingerprint
        """
        return hashlib.sha256(fingerprint.encode()).hexdigest()
    
    def clear_cache(self, older_than_days: Optional[int] = None) -> int:
        """
        Clear fingerprint cache.
        
        Args:
            older_than_days: Only clear entries older than this many days
            
        Returns:
            Number of entries cleared
        """
        try:
            cutoff_time = None
            if older_than_days:
                cutoff_time = time.time() - (older_than_days * 86400)
            
            cleared = self.db.clear_fingerprint_cache(cutoff_time)
            self.logger.info(f"Cleared {cleared} fingerprint cache entries")
            return cleared
            
        except Exception as e:
            self.logger.error(f"Cache clearing error: {e}")
            return 0
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get fingerprint cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        try:
            stats = self.db.get_fingerprint_cache_stats()
            return {
                'total_entries': stats.get('total_entries', 0),
                'cache_hit_rate': stats.get('hit_rate', 0.0),
                'oldest_entry_days': stats.get('oldest_entry_days', 0),
                'cache_size_mb': stats.get('cache_size_mb', 0.0)
            }
        except Exception as e:
            self.logger.error(f"Cache stats error: {e}")
            return {}