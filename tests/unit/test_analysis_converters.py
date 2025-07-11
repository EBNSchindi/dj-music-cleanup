"""
Unit tests for analysis result converters.

Tests conversion between FileAnalysisResult and legacy formats.
"""

import pytest
from datetime import datetime

from src.music_cleanup.core.file_analyzer import FileAnalysisResult
from src.music_cleanup.utils.analysis_converters import (
    convert_to_file_info_dict,
    convert_from_file_info_dict,
    merge_quality_reports,
    create_batch_analysis_summary
)
from src.music_cleanup.audio.quality_scoring import UnifiedQualityScore
from src.music_cleanup.audio.advanced_quality_analyzer import AudioQualityReport


class TestAnalysisConverters:
    """Test suite for analysis converters."""
    
    def test_convert_to_file_info_dict_basic(self):
        """Test basic conversion from FileAnalysisResult to dict."""
        result = FileAnalysisResult(
            file_path="/path/to/song.mp3",
            file_size=5242880,
            file_mtime=1234567890.0,
            format=".mp3",
            duration=180.0,
            metadata={'title': 'Test Song', 'artist': 'Test Artist'},
            has_metadata=True,
            bitrate=320000,
            sample_rate=44100,
            channels=2,
            quality_score=85.0,
            is_healthy=True,
            fingerprint="abc123",
            fingerprint_algorithm="chromaprint",
            checksum="def456"
        )
        
        file_info = convert_to_file_info_dict(result)
        
        assert file_info['file_path'] == "/path/to/song.mp3"
        assert file_info['file_size'] == 5242880
        assert file_info['file_mtime'] == 1234567890.0
        assert file_info['format'] == ".mp3"
        assert file_info['duration'] == 180.0
        assert file_info['metadata']['title'] == 'Test Song'
        assert file_info['bitrate'] == 320000
        assert file_info['sample_rate'] == 44100
        assert file_info['channels'] == 2
        assert file_info['health_score'] == 85.0
        assert file_info['is_healthy'] == True
        assert file_info['fingerprint'] == "abc123"
        assert file_info['algorithm'] == "chromaprint"
        assert file_info['checksum'] == "def456"
    
    def test_convert_to_file_info_dict_with_issues(self):
        """Test conversion with health issues and defects."""
        result = FileAnalysisResult(
            file_path="/path/to/bad.mp3",
            file_size=1000000,
            file_mtime=0,
            is_healthy=False,
            health_issues=["Clipping detected", "Low bitrate"],
            corruption_level="moderate",
            has_metadata=False,
            quality_score=30.0
        )
        
        file_info = convert_to_file_info_dict(result)
        
        assert not file_info['is_healthy']
        assert file_info['health_score'] == 30.0
        assert file_info['defects'] == ["Clipping detected", "Low bitrate"]
        assert file_info['metadata_accessible'] == False
        assert file_info['corruption_level'] == "moderate"
    
    def test_convert_to_file_info_dict_with_duplicates(self):
        """Test conversion with duplicate information."""
        result = FileAnalysisResult(
            file_path="/path/to/duplicate.mp3",
            file_size=5000000,
            file_mtime=0,
            is_duplicate=True,
            duplicate_of="/path/to/original.mp3"
        )
        
        file_info = convert_to_file_info_dict(result)
        
        assert file_info['is_duplicate'] == True
        assert file_info['duplicate_of'] == "/path/to/original.mp3"
    
    def test_convert_from_file_info_dict_basic(self):
        """Test conversion from legacy dict to FileAnalysisResult."""
        file_info = {
            'file_path': '/path/to/song.mp3',
            'file_size': 5242880,
            'file_mtime': 1234567890.0,
            'format': '.mp3',
            'duration': 180.0,
            'metadata': {'title': 'Test Song'},
            'bitrate': 320000,
            'sample_rate': 44100,
            'channels': 2,
            'health_score': 85.0,
            'is_healthy': True,
            'fingerprint': 'abc123',
            'algorithm': 'chromaprint',
            'checksum': 'def456'
        }
        
        result = convert_from_file_info_dict(file_info)
        
        assert isinstance(result, FileAnalysisResult)
        assert result.file_path == '/path/to/song.mp3'
        assert result.file_size == 5242880
        assert result.format == '.mp3'
        assert result.duration == 180.0
        assert result.metadata['title'] == 'Test Song'
        assert result.has_metadata == True
        assert result.bitrate == 320000
        assert result.sample_rate == 44100
        assert result.quality_score == 85.0
        assert result.is_healthy == True
        assert result.fingerprint == 'abc123'
        assert result.fingerprint_algorithm == 'chromaprint'
    
    def test_convert_from_file_info_dict_minimal(self):
        """Test conversion with minimal file_info."""
        file_info = {
            'file_path': '/path/to/song.mp3',
            'file_size': 1000000
        }
        
        result = convert_from_file_info_dict(file_info)
        
        assert result.file_path == '/path/to/song.mp3'
        assert result.file_size == 1000000
        assert result.file_mtime == 0  # Default
        assert result.quality_score == 50  # Default from 'health_score'
        assert result.is_healthy == True  # Default
        assert result.processed_successfully == True
    
    def test_bidirectional_conversion(self):
        """Test that conversion is bidirectional."""
        original = FileAnalysisResult(
            file_path="/test/song.mp3",
            file_size=3000000,
            file_mtime=1234567890,
            format=".mp3",
            duration=200.0,
            metadata={'artist': 'Test', 'album': 'Album'},
            has_metadata=True,
            bitrate=256000,
            quality_score=75.0,
            is_healthy=True,
            health_issues=[],
            fingerprint="xyz789",
            fingerprint_algorithm="acoustid"
        )
        
        # Convert to dict and back
        file_info = convert_to_file_info_dict(original)
        reconstructed = convert_from_file_info_dict(file_info)
        
        assert reconstructed.file_path == original.file_path
        assert reconstructed.file_size == original.file_size
        assert reconstructed.format == original.format
        assert reconstructed.duration == original.duration
        assert reconstructed.bitrate == original.bitrate
        assert reconstructed.quality_score == original.quality_score
        assert reconstructed.fingerprint == original.fingerprint
    
    def test_merge_quality_reports_basic_only(self):
        """Test merging with only basic quality data."""
        basic = {
            'quality_score': 0.7,
            'bitrate': 192000,
            'format': 'mp3'
        }
        
        merged = merge_quality_reports(basic)
        
        assert merged['quality_score'] == 0.7
        assert merged['bitrate'] == 192000
        assert merged['format'] == 'mp3'
        assert merged['overall_quality_score'] == 0.7
    
    def test_merge_quality_reports_with_advanced(self):
        """Test merging with advanced quality report."""
        basic = {'quality_score': 0.7}
        
        advanced = AudioQualityReport(
            file_path="/test.mp3",
            format="mp3",
            duration=180.0,
            bitrate=320000,
            sample_rate=44100,
            channels=2,
            bit_depth=16,
            spectral_centroid=2500.0,
            zero_crossing_rate=0.05,
            spectral_rolloff=5000.0,
            dynamic_range=20.0,
            peak_amplitude=0.95,
            rms_energy=0.3,
            silence_ratio=0.01,
            clipping_rate=0.001,
            noise_floor=-60.0,
            snr=55.0,
            thd=0.02,
            overall_score=85.0
        )
        
        merged = merge_quality_reports(basic, advanced=advanced)
        
        assert merged['quality_score'] == 0.7
        assert merged['spectral_centroid'] == 2500.0
        assert merged['dynamic_range'] == 20.0
        assert merged['snr'] == 55.0
        assert merged['advanced_score'] == 85.0
        assert merged['overall_quality_score'] == pytest.approx((0.7 + 85.0) / 2)
    
    def test_merge_quality_reports_with_unified(self):
        """Test merging with unified quality score."""
        basic = {'quality_score': 0.7}
        
        unified = UnifiedQualityScore(
            technical_score=80.0,
            perceptual_score=75.0,
            defect_penalty=5.0,
            bonus_points=2.0,
            final_score=72.0,
            quality_grade='B',
            quality_tier='good',
            confidence=0.9
        )
        
        merged = merge_quality_reports(basic, unified=unified)
        
        assert merged['technical_score'] == 80.0
        assert merged['perceptual_score'] == 75.0
        assert merged['final_score'] == 72.0
        assert merged['quality_grade'] == 'B'
        assert merged['overall_quality_score'] == pytest.approx((0.7 + 72.0) / 2)
    
    def test_merge_quality_reports_all_sources(self):
        """Test merging with all quality data sources."""
        basic = {'quality_score': 0.7}
        
        advanced = AudioQualityReport(
            file_path="/test.mp3",
            format="mp3",
            duration=180.0,
            bitrate=320000,
            sample_rate=44100,
            channels=2,
            bit_depth=16,
            spectral_centroid=2500.0,
            zero_crossing_rate=0.05,
            spectral_rolloff=5000.0,
            dynamic_range=20.0,
            peak_amplitude=0.95,
            rms_energy=0.3,
            silence_ratio=0.01,
            clipping_rate=0.001,
            noise_floor=-60.0,
            snr=55.0,
            thd=0.02,
            overall_score=85.0
        )
        
        unified = UnifiedQualityScore(
            technical_score=80.0,
            perceptual_score=75.0,
            defect_penalty=5.0,
            bonus_points=2.0,
            final_score=72.0,
            quality_grade='B',
            quality_tier='good',
            confidence=0.9
        )
        
        merged = merge_quality_reports(basic, advanced=advanced, unified=unified)
        
        # Check all scores are present
        assert merged['quality_score'] == 0.7
        assert merged['advanced_score'] == 85.0
        assert merged['final_score'] == 72.0
        
        # Overall should be average of all three
        expected_overall = (0.7 + 85.0 + 72.0) / 3
        assert merged['overall_quality_score'] == pytest.approx(expected_overall)
    
    def test_create_batch_analysis_summary_empty(self):
        """Test summary creation with empty results."""
        summary = create_batch_analysis_summary([])
        
        assert summary['total_files'] == 0
        assert summary['healthy_files'] == 0
        assert summary['corrupted_files'] == 0
        assert summary['duplicate_files'] == 0
        assert summary['total_size_bytes'] == 0
        assert summary['total_duration_seconds'] == 0
        assert summary['average_quality_score'] == 0
        assert summary['format_distribution'] == {}
        assert summary['health_issues'] == {}
    
    def test_create_batch_analysis_summary_mixed(self):
        """Test summary creation with mixed results."""
        results = [
            FileAnalysisResult(
                file_path="/song1.mp3",
                file_size=5000000,
                file_mtime=0,
                format=".mp3",
                duration=180.0,
                quality_score=85.0,
                is_healthy=True,
                processed_successfully=True
            ),
            FileAnalysisResult(
                file_path="/song2.flac",
                file_size=30000000,
                file_mtime=0,
                format=".flac",
                duration=200.0,
                quality_score=95.0,
                is_healthy=True,
                corruption_level=None,
                processed_successfully=True
            ),
            FileAnalysisResult(
                file_path="/song3.mp3",
                file_size=4000000,
                file_mtime=0,
                format=".mp3",
                duration=150.0,
                quality_score=40.0,
                is_healthy=False,
                corruption_level="high",
                health_issues=["Clipping detected", "Low bitrate"],
                processed_successfully=True
            ),
            FileAnalysisResult(
                file_path="/song4.mp3",
                file_size=5000000,
                file_mtime=0,
                format=".mp3",
                is_duplicate=True,
                duplicate_of="/song1.mp3",
                processed_successfully=True
            ),
            FileAnalysisResult(
                file_path="/song5.wav",
                file_size=1000000,
                file_mtime=0,
                format=".wav",
                skip_reason="File too small",
                processed_successfully=False
            )
        ]
        
        summary = create_batch_analysis_summary(results)
        
        assert summary['total_files'] == 5
        assert summary['healthy_files'] == 2
        assert summary['corrupted_files'] == 1
        assert summary['duplicate_files'] == 1
        assert summary['total_size_bytes'] == 45000000
        assert summary['total_duration_seconds'] == 530.0
        assert summary['average_quality_score'] == pytest.approx((85 + 95 + 40 + 0 + 0) / 5)
        
        assert summary['format_distribution']['.mp3'] == 3
        assert summary['format_distribution']['.flac'] == 1
        assert summary['format_distribution']['.wav'] == 1
        
        assert summary['health_issues']['Clipping detected'] == 1
        assert summary['health_issues']['Low bitrate'] == 1
        
        assert summary['processing_stats']['successful'] == 4
        assert summary['processing_stats']['failed'] == 1
        assert summary['processing_stats']['skipped'] == 1
    
    def test_create_batch_analysis_summary_all_healthy(self):
        """Test summary with all healthy files."""
        results = [
            FileAnalysisResult(
                file_path=f"/song{i}.mp3",
                file_size=5000000,
                file_mtime=0,
                format=".mp3",
                duration=180.0,
                quality_score=80.0 + i,
                is_healthy=True,
                processed_successfully=True
            )
            for i in range(5)
        ]
        
        summary = create_batch_analysis_summary(results)
        
        assert summary['total_files'] == 5
        assert summary['healthy_files'] == 5
        assert summary['corrupted_files'] == 0
        assert summary['duplicate_files'] == 0
        assert summary['average_quality_score'] == 82.0  # (80+81+82+83+84)/5