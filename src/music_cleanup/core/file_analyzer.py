"""
Unified File Analyzer for DJ Music Cleanup Tool

Consolidates all file analysis logic into a single, reusable component.
Replaces duplicate analysis code across orchestrator, batch processor, and quality manager.
"""

import logging
from pathlib import Path
from typing import Dict, Optional, Any, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from ..utils.decorators import handle_errors, track_performance, validate_path
from ..utils.integrity import FileIntegrityChecker as IntegrityChecker, IntegrityLevel
from ..modules.simple_metadata_manager import SimpleMetadataManager
from ..modules.simple_quality_analyzer import SimpleQualityAnalyzer
from ..modules.simple_fingerprinter import SimpleFingerprinter
from ..audio.defect_detection import AudioDefectDetector as DefectDetector
from ..audio.duplicate_detection import DuplicateDetector
from ..core.constants import (
    SUPPORTED_AUDIO_FORMATS,
    MIN_AUDIO_FILE_SIZE as MIN_FILE_SIZE,
    MAX_AUDIO_FILE_SIZE as MAX_FILE_SIZE
)


@dataclass
class FileAnalysisResult:
    """Complete analysis result for a single file"""
    file_path: str
    file_size: int
    file_mtime: float
    
    # Basic info
    format: Optional[str] = None
    duration: Optional[float] = None
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    has_metadata: bool = False
    
    # Quality metrics
    bitrate: Optional[int] = None
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    quality_score: Optional[float] = None
    
    # Health status
    is_healthy: bool = True
    health_issues: List[str] = field(default_factory=list)
    corruption_level: Optional[str] = None
    
    # Fingerprint
    fingerprint: Optional[str] = None
    fingerprint_algorithm: Optional[str] = None
    
    # Processing status
    processed_successfully: bool = False
    error_message: Optional[str] = None
    processing_time_ms: Optional[float] = None
    
    # Integrity
    checksum: Optional[str] = None
    integrity_verified: bool = False
    
    # Additional flags
    is_duplicate: bool = False
    duplicate_of: Optional[str] = None
    needs_organization: bool = True
    skip_reason: Optional[str] = None


class FileAnalyzer:
    """
    Unified file analyzer that consolidates all analysis operations.
    
    Features:
    - Metadata extraction
    - Quality analysis
    - Health/defect detection
    - Fingerprinting
    - Integrity checking
    - Duplicate detection
    """
    
    def __init__(
        self,
        enable_fingerprinting: bool = False,
        enable_defect_detection: bool = True,
        integrity_level: IntegrityLevel = IntegrityLevel.CHECKSUM,
        fingerprint_algorithm: str = "chromaprint",
        min_health_score: float = 50.0
    ):
        """
        Initialize the file analyzer.
        
        Args:
            enable_fingerprinting: Whether to generate audio fingerprints
            enable_defect_detection: Whether to analyze for audio defects
            integrity_level: Level of integrity checking
            fingerprint_algorithm: Algorithm for fingerprinting
            min_health_score: Minimum score for file to be considered healthy
        """
        self.enable_fingerprinting = enable_fingerprinting
        self.enable_defect_detection = enable_defect_detection
        self.integrity_level = integrity_level
        self.fingerprint_algorithm = fingerprint_algorithm
        self.min_health_score = min_health_score
        self.logger = logging.getLogger(__name__)
        
        # Initialize components
        self._metadata_manager = SimpleMetadataManager({})
        self._quality_analyzer = SimpleQualityAnalyzer({})
        self._integrity_checker = IntegrityChecker()
        
        # Optional components
        self._fingerprinter = SimpleFingerprinter() if enable_fingerprinting else None
        self._defect_detector = DefectDetector() if enable_defect_detection else None
        
        # Performance tracking
        self._performance_metrics: Dict[str, List[float]] = {}
        
        self.logger.info(
            f"FileAnalyzer initialized (fingerprinting: {enable_fingerprinting}, "
            f"defects: {enable_defect_detection}, integrity: {integrity_level.value})"
        )
    
    @handle_errors(return_on_error=None)
    @track_performance(threshold_ms=1000)
    @validate_path(must_exist=True)
    def analyze_file(self, file_path: str) -> Optional[FileAnalysisResult]:
        """
        Perform complete analysis of an audio file.
        
        Args:
            file_path: Path to the audio file
            
        Returns:
            FileAnalysisResult with all analysis data, or None on error
        """
        start_time = datetime.now()
        path = Path(file_path)
        
        # Initialize result
        result = FileAnalysisResult(
            file_path=str(path),
            file_size=path.stat().st_size,
            file_mtime=path.stat().st_mtime
        )
        
        # Validate file
        if not self._validate_file(path, result):
            return result
        
        # Step 1: Extract metadata
        self._analyze_metadata(path, result)
        
        # Step 2: Analyze quality
        self._analyze_quality(path, result)
        
        # Step 3: Check integrity
        self._check_integrity(path, result)
        
        # Step 4: Detect defects (if enabled)
        if self.enable_defect_detection and result.has_metadata:
            self._detect_defects(path, result)
        
        # Step 5: Generate fingerprint (if enabled and file is healthy)
        if self.enable_fingerprinting and result.is_healthy:
            self._generate_fingerprint(path, result)
        
        # Calculate processing time
        result.processing_time_ms = (datetime.now() - start_time).total_seconds() * 1000
        result.processed_successfully = result.is_healthy and not result.error_message
        
        self.logger.debug(
            f"Analysis complete for {path.name}: "
            f"healthy={result.is_healthy}, "
            f"quality={result.quality_score}, "
            f"time={result.processing_time_ms:.0f}ms"
        )
        
        return result
    
    def _validate_file(self, path: Path, result: FileAnalysisResult) -> bool:
        """Validate file before analysis"""
        # Check file size
        if result.file_size < MIN_FILE_SIZE:
            result.skip_reason = f"File too small ({result.file_size} bytes)"
            result.is_healthy = False
            return False
        
        if result.file_size > MAX_FILE_SIZE:
            result.skip_reason = f"File too large ({result.file_size / (1024**3):.1f} GB)"
            result.is_healthy = False
            return False
        
        # Check format
        if path.suffix.lower() not in SUPPORTED_AUDIO_FORMATS:
            result.skip_reason = f"Unsupported format: {path.suffix}"
            result.is_healthy = False
            return False
        
        result.format = path.suffix.lower()
        return True
    
    @handle_errors(log_level="warning")
    def _analyze_metadata(self, path: Path, result: FileAnalysisResult) -> None:
        """Extract and analyze metadata"""
        metadata = self._metadata_manager.extract_metadata(str(path))
        
        if metadata:
            result.metadata = metadata
            result.has_metadata = True
            result.duration = metadata.get('duration')
        else:
            result.health_issues.append("Failed to extract metadata")
            result.is_healthy = False
    
    @handle_errors(log_level="warning")
    def _analyze_quality(self, path: Path, result: FileAnalysisResult) -> None:
        """Analyze audio quality"""
        quality_data = self._quality_analyzer.analyze_quality(str(path))
        
        if quality_data:
            result.bitrate = quality_data.get('bitrate')
            result.sample_rate = quality_data.get('sample_rate', 44100)
            result.channels = quality_data.get('channels')
            result.quality_score = quality_data.get('quality_score', 0.0)
            
            # Check if quality meets minimum threshold
            if result.quality_score < self.min_health_score:
                result.health_issues.append(
                    f"Low quality score: {result.quality_score:.1f} < {self.min_health_score}"
                )
                result.is_healthy = False
        else:
            result.health_issues.append("Failed to analyze quality")
    
    @handle_errors(log_level="warning")
    def _check_integrity(self, path: Path, result: FileAnalysisResult) -> None:
        """Check file integrity"""
        is_valid, checksum = self._integrity_checker.check_integrity(
            str(path),
            level=self.integrity_level
        )
        
        result.integrity_verified = is_valid
        result.checksum = checksum
        
        if not is_valid:
            result.health_issues.append("Integrity check failed")
            result.is_healthy = False
            result.corruption_level = "high"
    
    @handle_errors(log_level="warning")
    def _detect_defects(self, path: Path, result: FileAnalysisResult) -> None:
        """Detect audio defects"""
        if not self._defect_detector:
            return
        
        health_report = self._defect_detector.analyze_audio_health(str(path))
        
        if health_report and not health_report.is_healthy:
            result.is_healthy = False
            result.health_issues.extend([
                f"{defect.defect_type}: {defect.description}"
                for defect in health_report.defects
            ])
            
            # Determine corruption level
            critical_defects = [d for d in health_report.defects if d.severity == "critical"]
            if critical_defects:
                result.corruption_level = "critical"
            elif health_report.defects:
                result.corruption_level = "moderate"
    
    @handle_errors(log_level="warning")
    def _generate_fingerprint(self, path: Path, result: FileAnalysisResult) -> None:
        """Generate audio fingerprint"""
        if not self._fingerprinter:
            return
        
        fingerprint = self._fingerprinter.generate_fingerprint(
            str(path),
            algorithm=self.fingerprint_algorithm
        )
        
        if fingerprint:
            result.fingerprint = fingerprint
            result.fingerprint_algorithm = self.fingerprint_algorithm
        else:
            self.logger.warning(f"Failed to generate fingerprint for {path.name}")
    
    def analyze_batch(
        self,
        file_paths: List[str],
        progress_callback: Optional[callable] = None
    ) -> List[FileAnalysisResult]:
        """
        Analyze multiple files in a batch.
        
        Args:
            file_paths: List of file paths to analyze
            progress_callback: Optional callback for progress updates
            
        Returns:
            List of analysis results
        """
        results = []
        total_files = len(file_paths)
        
        for i, file_path in enumerate(file_paths):
            if progress_callback:
                progress_callback({
                    'current': i + 1,
                    'total': total_files,
                    'file': Path(file_path).name
                })
            
            result = self.analyze_file(file_path)
            if result:
                results.append(result)
        
        return results
    
    def get_performance_summary(self) -> Dict[str, Dict[str, float]]:
        """
        Get performance metrics summary.
        
        Returns:
            Dictionary with performance statistics per method
        """
        summary = {}
        
        for method, times in self._performance_metrics.items():
            if times:
                summary[method] = {
                    'count': len(times),
                    'total_ms': sum(times),
                    'average_ms': sum(times) / len(times),
                    'min_ms': min(times),
                    'max_ms': max(times)
                }
        
        return summary