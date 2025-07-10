"""
Professional Audio Analysis Module

Provides advanced audio fingerprinting, duplicate detection, and defect analysis
for professional music library management.
"""

from .fingerprinting import (
    AudioFingerprinter,
    AudioFingerprint,
    FingerprintCache,
    fingerprint_file,
    find_duplicate_files
)

from .duplicate_detection import (
    DuplicateDetector,
    DuplicateGroup,
    DuplicateAction,
    AudioQuality
)

from .defect_detection import (
    AudioDefectDetector,
    AudioHealthReport,
    AudioDefect,
    DefectType
)

from .advanced_quality_analyzer import (
    AdvancedQualityAnalyzer,
    AudioQualityReport,
    QualityIssue,
    QualityIssueType
)

from .reference_quality_checker import (
    ReferenceQualityChecker,
    ReferenceComparisonResult,
    ReferenceVersion,
    ReferenceQuality
)

from .quality_scoring import (
    QualityScoringSystem,
    QualityFileManager,
    UnifiedQualityScore,
    QualityScoreComponents,
    ScoringProfile
)

from .integrated_quality_manager import (
    IntegratedQualityManager,
    QualityProcessingOptions,
    QualityProcessingResult
)

__all__ = [
    # Fingerprinting
    'AudioFingerprinter',
    'AudioFingerprint', 
    'FingerprintCache',
    'fingerprint_file',
    'find_duplicate_files',
    
    # Duplicate Detection
    'DuplicateDetector',
    'DuplicateGroup',
    'DuplicateAction',
    'AudioQuality',
    
    # Defect Detection
    'AudioDefectDetector',
    'AudioHealthReport',
    'AudioDefect',
    'DefectType',
    
    # Advanced Quality Analysis
    'AdvancedQualityAnalyzer',
    'AudioQualityReport',
    'QualityIssue',
    'QualityIssueType',
    
    # Reference Quality Checking
    'ReferenceQualityChecker',
    'ReferenceComparisonResult',
    'ReferenceVersion',
    'ReferenceQuality',
    
    # Quality Scoring
    'QualityScoringSystem',
    'QualityFileManager',
    'UnifiedQualityScore',
    'QualityScoreComponents',
    'ScoringProfile',
    
    # Integrated Quality Management
    'IntegratedQualityManager',
    'QualityProcessingOptions',
    'QualityProcessingResult'
]