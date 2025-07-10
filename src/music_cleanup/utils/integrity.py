"""
File Integrity Checking System for DJ Music Cleanup Tool
Advanced integrity verification and corruption detection
"""
import os
import sys
import hashlib
import time
import json
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set, Any, Generator
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import logging
import concurrent.futures

try:
    from mutagen import File as MutagenFile
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False


class IntegrityLevel(Enum):
    """Levels of integrity checking"""
    BASIC = "basic"          # File existence and size
    CHECKSUM = "checksum"    # MD5/SHA256 checksums
    METADATA = "metadata"    # Audio metadata validation
    DEEP = "deep"           # Comprehensive validation
    PARANOID = "paranoid"   # Maximum security checks


class IntegrityStatus(Enum):
    """File integrity status"""
    HEALTHY = "healthy"
    MODIFIED = "modified"
    CORRUPTED = "corrupted"
    MISSING = "missing"
    INACCESSIBLE = "inaccessible"
    UNKNOWN = "unknown"


@dataclass
class IntegrityCheck:
    """Single integrity check result"""
    file_path: str
    status: IntegrityStatus
    check_level: IntegrityLevel
    checked_at: str
    file_size: int
    checksum_md5: Optional[str] = None
    checksum_sha256: Optional[str] = None
    metadata_valid: Optional[bool] = None
    audio_playable: Optional[bool] = None
    issues: List[str] = None
    repair_suggestions: List[str] = None
    
    def __post_init__(self):
        if self.issues is None:
            self.issues = []
        if self.repair_suggestions is None:
            self.repair_suggestions = []


@dataclass
class IntegrityReport:
    """Comprehensive integrity report"""
    report_id: str
    created_at: str
    check_level: IntegrityLevel
    total_files: int
    healthy_files: int
    modified_files: int
    corrupted_files: int
    missing_files: int
    inaccessible_files: int
    integrity_score: float
    check_duration: float
    file_checks: List[IntegrityCheck]
    summary: Dict[str, Any]


class IntegrityError(Exception):
    """Exception for integrity checking errors"""
    pass


class FileIntegrityChecker:
    """
    Advanced file integrity checker for music libraries.
    Provides comprehensive integrity verification with multiple levels.
    """
    
    def __init__(self, workspace_dir: str = None, enable_caching: bool = True):
        """Initialize integrity checker"""
        self.logger = logging.getLogger(__name__)
        
        # Setup workspace
        if workspace_dir:
            self.workspace_dir = Path(workspace_dir)
        else:
            self.workspace_dir = Path.cwd() / ".integrity_cache"
        
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        
        # Cache directories
        self.checksums_cache_dir = self.workspace_dir / "checksums"
        self.metadata_cache_dir = self.workspace_dir / "metadata"
        self.reports_dir = self.workspace_dir / "reports"
        
        for directory in [self.checksums_cache_dir, self.metadata_cache_dir, self.reports_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        # Configuration
        self.enable_caching = enable_caching
        self.checksum_cache_max_age = 7 * 24 * 3600  # 7 days
        self.max_workers = min(4, os.cpu_count() or 1)
        self.chunk_size = 64 * 1024  # 64KB chunks for reading
        
        # Supported audio formats
        self.audio_formats = {
            '.mp3', '.flac', '.wav', '.m4a', '.aac', '.ogg', 
            '.opus', '.wma', '.mp4', '.m4p'
        }
        
        # Cache for checksums and metadata
        self.checksum_cache: Dict[str, Dict[str, Any]] = {}
        self.metadata_cache: Dict[str, Dict[str, Any]] = {}
        
        # Load existing caches
        if enable_caching:
            self._load_caches()
        
        self.logger.info(f"FileIntegrityChecker initialized with workspace: {self.workspace_dir}")
    
    def _load_caches(self):
        """Load existing caches from storage"""
        try:
            # Load checksum cache
            checksum_cache_file = self.checksums_cache_dir / "checksums.json"
            if checksum_cache_file.exists():
                with open(checksum_cache_file, 'r') as f:
                    self.checksum_cache = json.load(f)
                self.logger.debug(f"Loaded {len(self.checksum_cache)} checksum entries")
            
            # Load metadata cache
            metadata_cache_file = self.metadata_cache_dir / "metadata.json"
            if metadata_cache_file.exists():
                with open(metadata_cache_file, 'r') as f:
                    self.metadata_cache = json.load(f)
                self.logger.debug(f"Loaded {len(self.metadata_cache)} metadata entries")
        
        except Exception as e:
            self.logger.error(f"Error loading caches: {e}")
    
    def _save_caches(self):
        """Save caches to storage"""
        if not self.enable_caching:
            return
        
        try:
            # Save checksum cache
            checksum_cache_file = self.checksums_cache_dir / "checksums.json"
            with open(checksum_cache_file, 'w') as f:
                json.dump(self.checksum_cache, f, indent=2)
            
            # Save metadata cache
            metadata_cache_file = self.metadata_cache_dir / "metadata.json"
            with open(metadata_cache_file, 'w') as f:
                json.dump(self.metadata_cache, f, indent=2)
        
        except Exception as e:
            self.logger.error(f"Error saving caches: {e}")
    
    def _get_file_checksum(self, file_path: str, algorithm: str = 'md5') -> str:
        """Calculate file checksum with caching"""
        file_path = os.path.abspath(file_path)
        
        # Check cache first
        if self.enable_caching and file_path in self.checksum_cache:
            cache_entry = self.checksum_cache[file_path]
            file_stat = os.stat(file_path)
            
            # Check if cache is still valid
            if (cache_entry.get('mtime') == file_stat.st_mtime and
                cache_entry.get('size') == file_stat.st_size and
                time.time() - cache_entry.get('cached_at', 0) < self.checksum_cache_max_age):
                
                if algorithm in cache_entry:
                    return cache_entry[algorithm]
        
        # Calculate checksum
        try:
            if algorithm == 'md5':
                hasher = hashlib.md5()
            elif algorithm == 'sha256':
                hasher = hashlib.sha256()
            else:
                raise ValueError(f"Unsupported algorithm: {algorithm}")
            
            with open(file_path, 'rb') as f:
                while chunk := f.read(self.chunk_size):
                    hasher.update(chunk)
            
            checksum = hasher.hexdigest()
            
            # Update cache
            if self.enable_caching:
                file_stat = os.stat(file_path)
                if file_path not in self.checksum_cache:
                    self.checksum_cache[file_path] = {}
                
                self.checksum_cache[file_path].update({
                    algorithm: checksum,
                    'mtime': file_stat.st_mtime,
                    'size': file_stat.st_size,
                    'cached_at': time.time()
                })
            
            return checksum
        
        except Exception as e:
            self.logger.error(f"Error calculating {algorithm} for {file_path}: {e}")
            return None
    
    def _validate_audio_metadata(self, file_path: str) -> Tuple[bool, List[str]]:
        """Validate audio file metadata"""
        if not MUTAGEN_AVAILABLE:
            return True, ["Mutagen not available for metadata validation"]
        
        issues = []
        
        try:
            audio_file = MutagenFile(file_path)
            
            if audio_file is None:
                issues.append("File not recognized as audio")
                return False, issues
            
            # Check basic audio info
            if not hasattr(audio_file, 'info') or audio_file.info is None:
                issues.append("No audio info available")
                return False, issues
            
            # Validate duration
            duration = getattr(audio_file.info, 'length', 0)
            if duration <= 0:
                issues.append("Invalid or zero duration")
            elif duration < 1:
                issues.append("Suspiciously short duration")
            elif duration > 3600:  # 1 hour
                issues.append("Suspiciously long duration")
            
            # Validate bitrate
            bitrate = getattr(audio_file.info, 'bitrate', 0)
            if bitrate <= 0:
                issues.append("Invalid or zero bitrate")
            elif bitrate < 64:
                issues.append("Very low bitrate")
            elif bitrate > 2000:
                issues.append("Suspiciously high bitrate")
            
            # Validate sample rate
            sample_rate = getattr(audio_file.info, 'sample_rate', 0)
            if sample_rate <= 0:
                issues.append("Invalid or zero sample rate")
            elif sample_rate < 8000:
                issues.append("Very low sample rate")
            elif sample_rate > 192000:
                issues.append("Suspiciously high sample rate")
            
            # Validate channels
            channels = getattr(audio_file.info, 'channels', 0)
            if channels <= 0:
                issues.append("Invalid channel count")
            elif channels > 8:
                issues.append("Suspiciously high channel count")
            
            return len(issues) == 0, issues
        
        except Exception as e:
            issues.append(f"Metadata validation error: {str(e)}")
            return False, issues
    
    def _test_audio_playability(self, file_path: str) -> Tuple[bool, List[str]]:
        """Test if audio file is playable (basic check)"""
        issues = []
        
        try:
            # Basic file structure check
            file_size = os.path.getsize(file_path)
            if file_size == 0:
                issues.append("File is empty")
                return False, issues
            elif file_size < 1024:  # Less than 1KB
                issues.append("File suspiciously small")
            
            # Check file extension vs content
            extension = Path(file_path).suffix.lower()
            
            if extension == '.mp3':
                # Check for MP3 header
                with open(file_path, 'rb') as f:
                    header = f.read(3)
                    if header != b'ID3' and header[:2] != b'\xff\xfb':
                        issues.append("Invalid MP3 header")
            
            elif extension == '.flac':
                # Check for FLAC header
                with open(file_path, 'rb') as f:
                    header = f.read(4)
                    if header != b'fLaC':
                        issues.append("Invalid FLAC header")
            
            elif extension == '.wav':
                # Check for WAV header
                with open(file_path, 'rb') as f:
                    header = f.read(12)
                    if header[:4] != b'RIFF' or header[8:12] != b'WAVE':
                        issues.append("Invalid WAV header")
            
            # More format checks could be added here
            
            return len(issues) == 0, issues
        
        except Exception as e:
            issues.append(f"Playability test error: {str(e)}")
            return False, issues
    
    def check_file_integrity(self, file_path: str, 
                           level: IntegrityLevel = IntegrityLevel.CHECKSUM,
                           reference_checksums: Dict[str, str] = None) -> IntegrityCheck:
        """Check integrity of a single file"""
        file_path = os.path.abspath(file_path)
        start_time = time.time()
        
        try:
            # Basic existence and accessibility check
            if not os.path.exists(file_path):
                return IntegrityCheck(
                    file_path=file_path,
                    status=IntegrityStatus.MISSING,
                    check_level=level,
                    checked_at=datetime.now().isoformat(),
                    file_size=0,
                    issues=["File does not exist"]
                )
            
            if not os.access(file_path, os.R_OK):
                return IntegrityCheck(
                    file_path=file_path,
                    status=IntegrityStatus.INACCESSIBLE,
                    check_level=level,
                    checked_at=datetime.now().isoformat(),
                    file_size=0,
                    issues=["File is not readable"]
                )
            
            # Get file size
            file_size = os.path.getsize(file_path)
            
            # Initialize result
            result = IntegrityCheck(
                file_path=file_path,
                status=IntegrityStatus.HEALTHY,
                check_level=level,
                checked_at=datetime.now().isoformat(),
                file_size=file_size
            )
            
            # Level: BASIC - just existence and size
            if level == IntegrityLevel.BASIC:
                if file_size == 0:
                    result.status = IntegrityStatus.CORRUPTED
                    result.issues.append("File is empty")
                return result
            
            # Level: CHECKSUM and above
            if level.value in ['checksum', 'metadata', 'deep', 'paranoid']:
                # Calculate checksums
                result.checksum_md5 = self._get_file_checksum(file_path, 'md5')
                
                if level.value in ['deep', 'paranoid']:
                    result.checksum_sha256 = self._get_file_checksum(file_path, 'sha256')
                
                # Compare with reference checksums if provided
                if reference_checksums:
                    if 'md5' in reference_checksums and result.checksum_md5:
                        if result.checksum_md5 != reference_checksums['md5']:
                            result.status = IntegrityStatus.MODIFIED
                            result.issues.append("MD5 checksum mismatch")
                    
                    if 'sha256' in reference_checksums and result.checksum_sha256:
                        if result.checksum_sha256 != reference_checksums['sha256']:
                            result.status = IntegrityStatus.MODIFIED
                            result.issues.append("SHA256 checksum mismatch")
            
            # Level: METADATA and above
            if level.value in ['metadata', 'deep', 'paranoid']:
                # Check if it's an audio file
                if Path(file_path).suffix.lower() in self.audio_formats:
                    metadata_valid, metadata_issues = self._validate_audio_metadata(file_path)
                    result.metadata_valid = metadata_valid
                    
                    if not metadata_valid:
                        if result.status == IntegrityStatus.HEALTHY:
                            result.status = IntegrityStatus.CORRUPTED
                        result.issues.extend(metadata_issues)
            
            # Level: DEEP and above
            if level.value in ['deep', 'paranoid']:
                # Test audio playability
                if Path(file_path).suffix.lower() in self.audio_formats:
                    playable, playability_issues = self._test_audio_playability(file_path)
                    result.audio_playable = playable
                    
                    if not playable:
                        if result.status == IntegrityStatus.HEALTHY:
                            result.status = IntegrityStatus.CORRUPTED
                        result.issues.extend(playability_issues)
            
            # Level: PARANOID
            if level == IntegrityLevel.PARANOID:
                # Additional paranoid checks
                
                # Check for suspicious file patterns
                try:
                    with open(file_path, 'rb') as f:
                        # Read first and last 1KB
                        first_kb = f.read(1024)
                        f.seek(-1024, 2)
                        last_kb = f.read(1024)
                        
                        # Check for all zeros (suspicious)
                        if first_kb == b'\x00' * len(first_kb):
                            result.issues.append("File starts with all zeros")
                        
                        if last_kb == b'\x00' * len(last_kb):
                            result.issues.append("File ends with all zeros")
                
                except Exception as e:
                    result.issues.append(f"Paranoid check error: {str(e)}")
            
            # Generate repair suggestions
            if result.status != IntegrityStatus.HEALTHY:
                result.repair_suggestions = self._generate_repair_suggestions(result)
            
            return result
        
        except Exception as e:
            self.logger.error(f"Error checking integrity of {file_path}: {e}")
            return IntegrityCheck(
                file_path=file_path,
                status=IntegrityStatus.UNKNOWN,
                check_level=level,
                checked_at=datetime.now().isoformat(),
                file_size=0,
                issues=[f"Integrity check error: {str(e)}"]
            )
    
    def _generate_repair_suggestions(self, check: IntegrityCheck) -> List[str]:
        """Generate repair suggestions based on integrity check results"""
        suggestions = []
        
        if check.status == IntegrityStatus.MISSING:
            suggestions.extend([
                "Restore file from backup",
                "Check if file was moved to another location",
                "Verify file path is correct"
            ])
        
        elif check.status == IntegrityStatus.INACCESSIBLE:
            suggestions.extend([
                "Check file permissions",
                "Verify file is not locked by another process",
                "Run as administrator if necessary"
            ])
        
        elif check.status == IntegrityStatus.CORRUPTED:
            suggestions.extend([
                "Restore file from backup",
                "Re-download or re-rip the audio file"
            ])
            
            if "checksum mismatch" in " ".join(check.issues):
                suggestions.append("File may have been modified or corrupted")
            
            if check.metadata_valid is False:
                suggestions.append("Try to repair metadata with audio tools")
            
            if check.audio_playable is False:
                suggestions.extend([
                    "File may be truncated or corrupted",
                    "Try transcoding to repair format issues"
                ])
        
        elif check.status == IntegrityStatus.MODIFIED:
            suggestions.extend([
                "Verify if modification was intentional",
                "Compare with original version",
                "Update reference checksums if modification is valid"
            ])
        
        return suggestions
    
    def check_directory_integrity(self, directory: str, 
                                level: IntegrityLevel = IntegrityLevel.CHECKSUM,
                                recursive: bool = True,
                                file_pattern: str = None,
                                reference_database: str = None) -> IntegrityReport:
        """Check integrity of all files in a directory"""
        start_time = time.time()
        report_id = f"integrity_{int(time.time())}"
        
        self.logger.info(f"Starting integrity check: {directory} (level: {level.value})")
        
        # Find files to check
        files_to_check = []
        directory_path = Path(directory)
        
        if recursive:
            pattern = "**/*" if file_pattern is None else f"**/{file_pattern}"
            files_to_check = list(directory_path.rglob("*"))
        else:
            pattern = "*" if file_pattern is None else file_pattern
            files_to_check = list(directory_path.glob(pattern))
        
        # Filter to actual files
        files_to_check = [f for f in files_to_check if f.is_file()]
        
        # Load reference checksums if provided
        reference_checksums = {}
        if reference_database and os.path.exists(reference_database):
            try:
                with open(reference_database, 'r') as f:
                    reference_checksums = json.load(f)
            except Exception as e:
                self.logger.error(f"Error loading reference database: {e}")
        
        # Initialize counters
        total_files = len(files_to_check)
        counters = {
            'healthy': 0,
            'modified': 0,
            'corrupted': 0,
            'missing': 0,
            'inaccessible': 0,
            'unknown': 0
        }
        
        file_checks = []
        
        # Process files
        if total_files > 100 and self.max_workers > 1:
            # Use parallel processing for large datasets
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # Submit all tasks
                future_to_file = {
                    executor.submit(
                        self.check_file_integrity,
                        str(file_path),
                        level,
                        reference_checksums.get(str(file_path))
                    ): file_path
                    for file_path in files_to_check
                }
                
                # Collect results
                for future in concurrent.futures.as_completed(future_to_file):
                    try:
                        check_result = future.result()
                        file_checks.append(check_result)
                        counters[check_result.status.value] += 1
                        
                        # Progress logging
                        if len(file_checks) % 1000 == 0:
                            self.logger.info(f"Checked {len(file_checks)}/{total_files} files")
                    
                    except Exception as e:
                        file_path = future_to_file[future]
                        self.logger.error(f"Error checking {file_path}: {e}")
                        counters['unknown'] += 1
        else:
            # Sequential processing for small datasets
            for i, file_path in enumerate(files_to_check):
                try:
                    file_ref_checksums = reference_checksums.get(str(file_path))
                    check_result = self.check_file_integrity(str(file_path), level, file_ref_checksums)
                    file_checks.append(check_result)
                    counters[check_result.status.value] += 1
                    
                    # Progress logging
                    if (i + 1) % 100 == 0:
                        self.logger.info(f"Checked {i + 1}/{total_files} files")
                
                except Exception as e:
                    self.logger.error(f"Error checking {file_path}: {e}")
                    counters['unknown'] += 1
        
        # Calculate integrity score
        if total_files > 0:
            integrity_score = counters['healthy'] / total_files
        else:
            integrity_score = 1.0
        
        # Calculate duration
        check_duration = time.time() - start_time
        
        # Create summary
        summary = {
            'directory': str(directory),
            'check_level': level.value,
            'total_size_bytes': sum(check.file_size for check in file_checks),
            'avg_file_size_bytes': sum(check.file_size for check in file_checks) / max(total_files, 1),
            'issues_found': sum(len(check.issues) for check in file_checks),
            'files_with_issues': len([check for check in file_checks if check.issues]),
            'repair_suggestions_total': sum(len(check.repair_suggestions) for check in file_checks),
            'check_duration_per_file': check_duration / max(total_files, 1)
        }
        
        # Add format-specific statistics
        format_stats = {}
        for check in file_checks:
            ext = Path(check.file_path).suffix.lower()
            if ext not in format_stats:
                format_stats[ext] = {'total': 0, 'healthy': 0, 'issues': 0}
            
            format_stats[ext]['total'] += 1
            if check.status == IntegrityStatus.HEALTHY:
                format_stats[ext]['healthy'] += 1
            if check.issues:
                format_stats[ext]['issues'] += 1
        
        summary['format_statistics'] = format_stats
        
        # Create report
        report = IntegrityReport(
            report_id=report_id,
            created_at=datetime.now().isoformat(),
            check_level=level,
            total_files=total_files,
            healthy_files=counters['healthy'],
            modified_files=counters['modified'],
            corrupted_files=counters['corrupted'],
            missing_files=counters['missing'],
            inaccessible_files=counters['inaccessible'],
            integrity_score=integrity_score,
            check_duration=check_duration,
            file_checks=file_checks,
            summary=summary
        )
        
        # Save report
        self._save_report(report)
        
        # Save updated caches
        self._save_caches()
        
        self.logger.info(f"Integrity check completed: {total_files} files, "
                        f"{integrity_score:.2%} healthy, {check_duration:.1f}s")
        
        return report
    
    def _save_report(self, report: IntegrityReport):
        """Save integrity report to file"""
        try:
            report_file = self.reports_dir / f"{report.report_id}.json"
            
            # Convert to serializable format
            report_data = {
                'report_id': report.report_id,
                'created_at': report.created_at,
                'check_level': report.check_level.value,
                'total_files': report.total_files,
                'healthy_files': report.healthy_files,
                'modified_files': report.modified_files,
                'corrupted_files': report.corrupted_files,
                'missing_files': report.missing_files,
                'inaccessible_files': report.inaccessible_files,
                'integrity_score': report.integrity_score,
                'check_duration': report.check_duration,
                'summary': report.summary,
                'file_checks': [
                    {
                        'file_path': check.file_path,
                        'status': check.status.value,
                        'check_level': check.check_level.value,
                        'checked_at': check.checked_at,
                        'file_size': check.file_size,
                        'checksum_md5': check.checksum_md5,
                        'checksum_sha256': check.checksum_sha256,
                        'metadata_valid': check.metadata_valid,
                        'audio_playable': check.audio_playable,
                        'issues': check.issues,
                        'repair_suggestions': check.repair_suggestions
                    }
                    for check in report.file_checks
                ]
            }
            
            with open(report_file, 'w') as f:
                json.dump(report_data, f, indent=2)
            
            self.logger.info(f"Saved integrity report: {report_file}")
        
        except Exception as e:
            self.logger.error(f"Error saving integrity report: {e}")
    
    def create_checksum_database(self, directory: str, output_file: str = None) -> str:
        """Create a checksum database for future integrity checks"""
        if output_file is None:
            output_file = f"checksums_{int(time.time())}.json"
        
        self.logger.info(f"Creating checksum database for: {directory}")
        
        # Run integrity check with checksum level
        report = self.check_directory_integrity(directory, IntegrityLevel.CHECKSUM)
        
        # Create checksum database
        checksum_db = {}
        for check in report.file_checks:
            if check.status in [IntegrityStatus.HEALTHY, IntegrityStatus.MODIFIED]:
                checksum_db[check.file_path] = {
                    'md5': check.checksum_md5,
                    'size': check.file_size,
                    'checked_at': check.checked_at
                }
        
        # Save database
        with open(output_file, 'w') as f:
            json.dump(checksum_db, f, indent=2)
        
        self.logger.info(f"Created checksum database: {output_file} ({len(checksum_db)} files)")
        return output_file
    
    def get_integrity_statistics(self) -> Dict[str, Any]:
        """Get integrity checking statistics"""
        stats = {
            'workspace_path': str(self.workspace_dir),
            'caching_enabled': self.enable_caching,
            'checksum_cache_size': len(self.checksum_cache),
            'metadata_cache_size': len(self.metadata_cache),
            'max_workers': self.max_workers,
            'supported_formats': list(self.audio_formats),
            'mutagen_available': MUTAGEN_AVAILABLE
        }
        
        # Count reports
        report_files = list(self.reports_dir.glob("*.json"))
        stats['total_reports'] = len(report_files)
        
        # Cache statistics
        if self.checksum_cache:
            cache_ages = []
            for entry in self.checksum_cache.values():
                if 'cached_at' in entry:
                    age = time.time() - entry['cached_at']
                    cache_ages.append(age)
            
            if cache_ages:
                stats['cache_stats'] = {
                    'avg_age_hours': sum(cache_ages) / len(cache_ages) / 3600,
                    'oldest_entry_hours': max(cache_ages) / 3600,
                    'newest_entry_hours': min(cache_ages) / 3600
                }
        
        return stats
    
    def cleanup_old_caches(self, max_age_days: int = 30):
        """Clean up old cache entries"""
        if not self.enable_caching:
            return
        
        cutoff_time = time.time() - (max_age_days * 24 * 3600)
        cleaned_count = 0
        
        # Clean checksum cache
        files_to_remove = []
        for file_path, entry in self.checksum_cache.items():
            if entry.get('cached_at', 0) < cutoff_time:
                files_to_remove.append(file_path)
        
        for file_path in files_to_remove:
            del self.checksum_cache[file_path]
            cleaned_count += 1
        
        # Save updated cache
        self._save_caches()
        
        self.logger.info(f"Cleaned up {cleaned_count} old cache entries")
        return cleaned_count