"""
Utility functions for converting between different analysis result formats.

This module provides converters between the new unified FileAnalysisResult
and legacy analysis formats used by various components.
"""

from typing import Dict, Any, Optional, List
from dataclasses import asdict

from ..core.file_analyzer import FileAnalysisResult
from ..audio.quality_scoring import UnifiedQualityScore
from ..audio.advanced_quality_analyzer import AudioQualityReport


def convert_to_file_info_dict(result: FileAnalysisResult) -> Dict[str, Any]:
    """
    Convert FileAnalysisResult to legacy file_info dictionary format.
    
    Args:
        result: FileAnalysisResult from unified analyzer
        
    Returns:
        Dictionary in legacy file_info format
    """
    file_info = {
        'file_path': result.file_path,
        'file_size': result.file_size,
        'file_mtime': result.file_mtime,
        'fingerprint': result.fingerprint,
        'metadata': result.metadata or {},
        'health_score': result.quality_score or 50,
        'is_healthy': result.is_healthy,
        'duration': result.duration or 0,
        'bitrate': result.bitrate,
        'format': result.format,
        'sample_rate': result.sample_rate,
        'channels': result.channels,
        'checksum': result.checksum
    }
    
    # Add optional fields
    if result.fingerprint_algorithm:
        file_info['algorithm'] = result.fingerprint_algorithm
    
    if result.health_issues:
        file_info['defects'] = result.health_issues
        file_info['metadata_accessible'] = result.has_metadata
    
    if result.corruption_level:
        file_info['corruption_level'] = result.corruption_level
    
    if result.duplicate_of:
        file_info['duplicate_of'] = result.duplicate_of
        file_info['is_duplicate'] = result.is_duplicate
    
    return file_info


def convert_from_file_info_dict(file_info: Dict[str, Any]) -> FileAnalysisResult:
    """
    Convert legacy file_info dictionary to FileAnalysisResult.
    
    Args:
        file_info: Legacy file_info dictionary
        
    Returns:
        FileAnalysisResult object
    """
    result = FileAnalysisResult(
        file_path=file_info.get('file_path', ''),
        file_size=file_info.get('file_size', 0),
        file_mtime=file_info.get('file_mtime', 0),
        format=file_info.get('format'),
        duration=file_info.get('duration'),
        metadata=file_info.get('metadata', {}),
        has_metadata=bool(file_info.get('metadata')),
        bitrate=file_info.get('bitrate'),
        sample_rate=file_info.get('sample_rate'),
        channels=file_info.get('channels'),
        quality_score=file_info.get('health_score', 50),
        is_healthy=file_info.get('is_healthy', True),
        health_issues=file_info.get('defects', []),
        corruption_level=file_info.get('corruption_level'),
        fingerprint=file_info.get('fingerprint'),
        fingerprint_algorithm=file_info.get('algorithm'),
        checksum=file_info.get('checksum'),
        is_duplicate=file_info.get('is_duplicate', False),
        duplicate_of=file_info.get('duplicate_of'),
        processed_successfully=True
    )
    
    return result


def merge_quality_reports(
    basic: Dict[str, Any],
    advanced: Optional[AudioQualityReport] = None,
    unified: Optional[UnifiedQualityScore] = None
) -> Dict[str, Any]:
    """
    Merge different quality report formats into a single dictionary.
    
    Args:
        basic: Basic quality data (from SimpleQualityAnalyzer)
        advanced: Advanced quality report (from AdvancedQualityAnalyzer)
        unified: Unified quality score (from QualityScoringSystem)
        
    Returns:
        Merged quality data dictionary
    """
    merged = basic.copy()
    
    # Merge advanced quality data
    if advanced:
        merged.update({
            'spectral_centroid': advanced.spectral_centroid,
            'zero_crossing_rate': advanced.zero_crossing_rate,
            'spectral_rolloff': advanced.spectral_rolloff,
            'dynamic_range': advanced.dynamic_range,
            'peak_amplitude': advanced.peak_amplitude,
            'rms_energy': advanced.rms_energy,
            'silence_ratio': advanced.silence_ratio,
            'clipping_rate': advanced.clipping_rate,
            'noise_floor': advanced.noise_floor,
            'snr': advanced.snr,
            'thd': advanced.thd,
            'advanced_score': advanced.overall_score
        })
    
    # Merge unified scoring data
    if unified:
        merged.update({
            'technical_score': unified.technical_score,
            'perceptual_score': unified.perceptual_score,
            'defect_penalty': unified.defect_penalty,
            'bonus_points': unified.bonus_points,
            'final_score': unified.final_score,
            'quality_grade': unified.quality_grade,
            'quality_tier': unified.quality_tier,
            'confidence': unified.confidence
        })
    
    # Calculate overall score
    scores = []
    if 'quality_score' in basic:
        scores.append(basic['quality_score'])
    if advanced and hasattr(advanced, 'overall_score'):
        scores.append(advanced.overall_score)
    if unified and hasattr(unified, 'final_score'):
        scores.append(unified.final_score)
    
    if scores:
        merged['overall_quality_score'] = sum(scores) / len(scores)
    
    return merged


def create_batch_analysis_summary(results: List[FileAnalysisResult]) -> Dict[str, Any]:
    """
    Create a summary of batch analysis results.
    
    Args:
        results: List of FileAnalysisResult objects
        
    Returns:
        Dictionary with batch analysis summary
    """
    total_files = len(results)
    healthy_files = sum(1 for r in results if r.is_healthy)
    corrupted_files = sum(1 for r in results if r.corruption_level)
    duplicates = sum(1 for r in results if r.is_duplicate)
    
    total_size = sum(r.file_size for r in results)
    total_duration = sum(r.duration or 0 for r in results)
    avg_quality = sum(r.quality_score or 0 for r in results) / total_files if total_files > 0 else 0
    
    formats = {}
    for r in results:
        if r.format:
            formats[r.format] = formats.get(r.format, 0) + 1
    
    health_issues_summary = {}
    for r in results:
        for issue in r.health_issues:
            health_issues_summary[issue] = health_issues_summary.get(issue, 0) + 1
    
    return {
        'total_files': total_files,
        'healthy_files': healthy_files,
        'corrupted_files': corrupted_files,
        'duplicate_files': duplicates,
        'total_size_bytes': total_size,
        'total_duration_seconds': total_duration,
        'average_quality_score': avg_quality,
        'format_distribution': formats,
        'health_issues': health_issues_summary,
        'processing_stats': {
            'successful': sum(1 for r in results if r.processed_successfully),
            'failed': sum(1 for r in results if not r.processed_successfully),
            'skipped': sum(1 for r in results if r.skip_reason)
        }
    }