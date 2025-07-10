"""
Professional Audio Fingerprinting Module

Implements acoustic fingerprinting using Chromaprint/fpcalc with fallback
to MD5 hashing. Provides robust duplicate detection and audio analysis.
"""

import hashlib
import json
import logging
import os
import subprocess
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from ..core.unified_database import get_unified_database, FingerprintRecord

try:
    import mutagen
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False


@dataclass
class AudioFingerprint:
    """Represents an audio fingerprint with metadata"""
    file_path: str
    fingerprint: str
    duration: float
    file_size: int
    algorithm: str  # 'chromaprint', 'md5', or 'hybrid'
    bitrate: Optional[int] = None
    format: Optional[str] = None
    file_mtime: float = 0
    generated_at: float = None
    
    def __post_init__(self):
        if self.generated_at is None:
            self.generated_at = time.time()
        if self.file_mtime == 0:
            try:
                self.file_mtime = Path(self.file_path).stat().st_mtime
            except (OSError, FileNotFoundError):
                self.file_mtime = 0


class FingerprintCache:
    """SQLite-based cache for audio fingerprints"""
    
    def __init__(self, cache_file: str = "fingerprint_cache.db"):
        # Use unified database instead of separate cache file
        db_path = cache_file.replace("fingerprint_cache.db", "music_cleanup.db")
        self.db = get_unified_database(db_path)
        self.logger = logging.getLogger(__name__)
        self.logger.info("Using unified database for fingerprint cache")
    
    # Database initialization handled by UnifiedDatabase
    
    def get_fingerprint(self, file_path: str) -> Optional[AudioFingerprint]:
        """Get cached fingerprint if file hasn't changed"""
        try:
            file_stat = os.stat(file_path)
            current_mtime = file_stat.st_mtime
            current_size = file_stat.st_size
            
            with sqlite3.connect(self.cache_file) as conn:
                cursor = conn.execute("""
                    SELECT fingerprint, duration, file_size, algorithm, 
                           bitrate, format, generated_at
                    FROM fingerprints 
                    WHERE file_path = ? AND file_mtime = ? AND file_size = ?
                """, (file_path, current_mtime, current_size))
                
                row = cursor.fetchone()
                if row:
                    return AudioFingerprint(
                        file_path=file_path,
                        fingerprint=row[0],
                        duration=row[1],
                        file_size=row[2],
                        algorithm=row[3],
                        bitrate=row[4],
                        format=row[5],
                        generated_at=row[6]
                    )
        except Exception as e:
            self.logger.warning(f"Error reading cache for {file_path}: {e}")
        
        return None
    
    def store_fingerprint(self, fp: AudioFingerprint):
        """Store fingerprint in cache"""
        try:
            file_stat = os.stat(fp.file_path)
            
            with sqlite3.connect(self.cache_file) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO fingerprints 
                    (file_path, fingerprint, duration, file_size, algorithm,
                     bitrate, format, file_mtime, generated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    fp.file_path, fp.fingerprint, fp.duration, fp.file_size,
                    fp.algorithm, fp.bitrate, fp.format, file_stat.st_mtime,
                    fp.generated_at
                ))
                conn.commit()
                
        except Exception as e:
            self.logger.warning(f"Error storing cache for {fp.file_path}: {e}")
    
    def find_similar_fingerprints(self, fingerprint: str) -> List[Tuple[str, str]]:
        """Find files with identical fingerprints"""
        with sqlite3.connect(self.cache_file) as conn:
            cursor = conn.execute("""
                SELECT file_path, fingerprint 
                FROM fingerprints 
                WHERE fingerprint = ?
            """, (fingerprint,))
            
            return cursor.fetchall()


class AudioFingerprinter:
    """
    Professional audio fingerprinting using Chromaprint with MD5 fallback.
    
    Supports:
    - Chromaprint acoustic fingerprinting via fpcalc
    - MD5 hash fallback when fpcalc unavailable
    - Intelligent caching for performance
    - Duration validation and metadata extraction
    """
    
    def __init__(self, cache_file: str = "fingerprint_cache.db", 
                 fingerprint_length: int = 120):
        """
        Initialize the audio fingerprinter.
        
        Args:
            cache_file: Path to SQLite cache file
            fingerprint_length: Length in seconds to analyze (max 120)
        """
        self.cache = FingerprintCache(cache_file)
        self.fingerprint_length = min(fingerprint_length, 120)
        self.logger = logging.getLogger(__name__)
        
        # Check for fpcalc availability
        self.fpcalc_available = self._check_fpcalc_availability()
        
        if not self.fpcalc_available:
            self.logger.warning("fpcalc not found. Using MD5 fallback for fingerprinting.")
        
        self.stats = {
            'chromaprint_success': 0,
            'chromaprint_failures': 0,
            'md5_fallbacks': 0,
            'cache_hits': 0,
            'total_processed': 0
        }
    
    def _check_fpcalc_availability(self) -> bool:
        """Check if fpcalc is available in PATH"""
        try:
            result = subprocess.run(['fpcalc', '-version'], 
                                  capture_output=True, timeout=5)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
            return False
    
    def generate_fingerprint(self, file_path: str) -> Optional[AudioFingerprint]:
        """
        Generate acoustic fingerprint for audio file.
        
        Args:
            file_path: Path to audio file
            
        Returns:
            AudioFingerprint object or None if failed
        """
        self.stats['total_processed'] += 1
        
        # Check cache first
        cached_fp = self.cache.get_fingerprint(file_path)
        if cached_fp:
            self.stats['cache_hits'] += 1
            self.logger.debug(f"Cache hit for {Path(file_path).name}")
            return cached_fp
        
        # Generate new fingerprint
        if self.fpcalc_available:
            fingerprint = self._generate_chromaprint_fingerprint(file_path)
            if fingerprint:
                self.stats['chromaprint_success'] += 1
                self.cache.store_fingerprint(fingerprint)
                return fingerprint
            else:
                self.stats['chromaprint_failures'] += 1
        
        # Fallback to MD5
        fingerprint = self._generate_md5_fingerprint(file_path)
        if fingerprint:
            self.stats['md5_fallbacks'] += 1
            self.cache.store_fingerprint(fingerprint)
        
        return fingerprint
    
    def _generate_chromaprint_fingerprint(self, file_path: str) -> Optional[AudioFingerprint]:
        """Generate Chromaprint acoustic fingerprint using fpcalc"""
        try:
            # Use fpcalc to generate acoustic fingerprint
            cmd = [
                'fpcalc',
                '-json',
                '-length', str(self.fingerprint_length),
                file_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=30, text=True)
            
            if result.returncode != 0:
                self.logger.debug(f"fpcalc failed for {file_path}: {result.stderr}")
                return None
            
            # Parse JSON output
            data = json.loads(result.stdout)
            fingerprint = data.get('fingerprint')
            duration = data.get('duration', 0)
            
            if not fingerprint:
                return None
            
            # Get additional metadata
            file_size = os.path.getsize(file_path)
            bitrate, format_info = self._extract_audio_metadata(file_path)
            
            return AudioFingerprint(
                file_path=file_path,
                fingerprint=fingerprint,
                duration=duration,
                file_size=file_size,
                algorithm='chromaprint',
                bitrate=bitrate,
                format=format_info
            )
            
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, 
                json.JSONDecodeError, Exception) as e:
            self.logger.debug(f"Chromaprint generation failed for {file_path}: {e}")
            return None
    
    def _generate_md5_fingerprint(self, file_path: str) -> Optional[AudioFingerprint]:
        """Generate MD5 hash as fallback fingerprint"""
        try:
            # Generate MD5 hash of file content
            hash_md5 = hashlib.md5()
            file_size = 0
            
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    hash_md5.update(chunk)
                    file_size += len(chunk)
            
            # Try to get duration from metadata
            duration = 0.0
            bitrate, format_info = self._extract_audio_metadata(file_path)
            
            if MUTAGEN_AVAILABLE:
                try:
                    audio_file = mutagen.File(file_path)
                    if audio_file and hasattr(audio_file, 'info'):
                        duration = getattr(audio_file.info, 'length', 0.0)
                except Exception:
                    pass
            
            return AudioFingerprint(
                file_path=file_path,
                fingerprint=hash_md5.hexdigest(),
                duration=duration,
                file_size=file_size,
                algorithm='md5',
                bitrate=bitrate,
                format=format_info
            )
            
        except Exception as e:
            self.logger.error(f"MD5 generation failed for {file_path}: {e}")
            return None
    
    def _extract_audio_metadata(self, file_path: str) -> Tuple[Optional[int], Optional[str]]:
        """Extract bitrate and format information"""
        bitrate = None
        format_info = Path(file_path).suffix.lower()
        
        if not MUTAGEN_AVAILABLE:
            return bitrate, format_info
        
        try:
            audio_file = mutagen.File(file_path)
            if audio_file and hasattr(audio_file, 'info'):
                info = audio_file.info
                bitrate = getattr(info, 'bitrate', None)
                
                # Get more specific format info
                if hasattr(info, 'mime'):
                    format_info = info.mime[0] if info.mime else format_info
                
        except Exception as e:
            self.logger.debug(f"Metadata extraction failed for {file_path}: {e}")
        
        return bitrate, format_info
    
    def batch_fingerprint(self, file_paths: List[str], 
                         progress_callback: Optional[callable] = None) -> List[AudioFingerprint]:
        """
        Generate fingerprints for multiple files efficiently.
        
        Args:
            file_paths: List of file paths to process
            progress_callback: Optional callback for progress updates
            
        Returns:
            List of AudioFingerprint objects (excludes None results)
        """
        fingerprints = []
        
        for i, file_path in enumerate(file_paths):
            if progress_callback:
                progress_callback(f"Fingerprinting: {Path(file_path).name} ({i+1}/{len(file_paths)})")
            
            fingerprint = self.generate_fingerprint(file_path)
            if fingerprint:
                fingerprints.append(fingerprint)
            
            # Log progress every 100 files
            if (i + 1) % 100 == 0:
                self.logger.info(f"Fingerprinted {i + 1}/{len(file_paths)} files")
        
        return fingerprints
    
    def find_duplicates_by_fingerprint(self, fingerprints: List[AudioFingerprint]) -> List[List[AudioFingerprint]]:
        """
        Group fingerprints by identical fingerprint values.
        
        Args:
            fingerprints: List of AudioFingerprint objects
            
        Returns:
            List of duplicate groups (each group contains 2+ similar files)
        """
        # Group by fingerprint
        fingerprint_groups = {}
        
        for fp in fingerprints:
            if fp.fingerprint not in fingerprint_groups:
                fingerprint_groups[fp.fingerprint] = []
            fingerprint_groups[fp.fingerprint].append(fp)
        
        # Return only groups with duplicates
        duplicate_groups = [
            group for group in fingerprint_groups.values() 
            if len(group) > 1
        ]
        
        return duplicate_groups
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get fingerprinting statistics"""
        total = self.stats['total_processed']
        if total == 0:
            return self.stats
        
        return {
            **self.stats,
            'cache_hit_rate': (self.stats['cache_hits'] / total) * 100,
            'chromaprint_success_rate': (self.stats['chromaprint_success'] / total) * 100,
            'fpcalc_available': self.fpcalc_available,
            'mutagen_available': MUTAGEN_AVAILABLE
        }
    
    def cleanup_cache(self, max_age_days: int = 30):
        """Remove old cache entries"""
        cutoff_time = time.time() - (max_age_days * 24 * 3600)
        
        with sqlite3.connect(self.cache.cache_file) as conn:
            cursor = conn.execute("""
                DELETE FROM fingerprints 
                WHERE generated_at < ?
            """, (cutoff_time,))
            
            deleted = cursor.rowcount
            conn.commit()
            
        self.logger.info(f"Cleaned up {deleted} old cache entries")
        return deleted


# Utility functions for external use

def fingerprint_file(file_path: str, cache_file: str = "fingerprint_cache.db") -> Optional[AudioFingerprint]:
    """
    Convenience function to fingerprint a single file.
    
    Args:
        file_path: Path to audio file
        cache_file: Path to cache database
        
    Returns:
        AudioFingerprint object or None
    """
    fingerprinter = AudioFingerprinter(cache_file)
    return fingerprinter.generate_fingerprint(file_path)


def find_duplicate_files(file_paths: List[str], 
                        cache_file: str = "fingerprint_cache.db") -> List[List[str]]:
    """
    Convenience function to find duplicates in a list of files.
    
    Args:
        file_paths: List of file paths to analyze
        cache_file: Path to cache database
        
    Returns:
        List of duplicate groups (each group contains 2+ file paths)
    """
    fingerprinter = AudioFingerprinter(cache_file)
    fingerprints = fingerprinter.batch_fingerprint(file_paths)
    duplicate_groups = fingerprinter.find_duplicates_by_fingerprint(fingerprints)
    
    # Convert back to file paths
    return [
        [fp.file_path for fp in group]
        for group in duplicate_groups
    ]