"""
Unit tests for FileAnalyzer.

Tests the unified file analyzer functionality including metadata extraction,
quality analysis, defect detection, and fingerprinting.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from src.music_cleanup.core.file_analyzer import FileAnalyzer, FileAnalysisResult
from src.music_cleanup.utils.integrity import IntegrityLevel


class TestFileAnalyzer:
    """Test suite for FileAnalyzer."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for test files."""
        temp = tempfile.mkdtemp()
        yield temp
        shutil.rmtree(temp, ignore_errors=True)
    
    @pytest.fixture
    def test_audio_file(self, temp_dir):
        """Create a test audio file."""
        file_path = Path(temp_dir) / "test_song.mp3"
        # Create dummy file with some content
        file_path.write_bytes(b"MP3" + b"\x00" * 1000)
        return str(file_path)
    
    @pytest.fixture
    def analyzer(self):
        """Create FileAnalyzer instance."""
        return FileAnalyzer(
            enable_fingerprinting=True,
            enable_defect_detection=True,
            integrity_level=IntegrityLevel.CHECKSUM,
            fingerprint_algorithm="chromaprint",
            min_health_score=50.0
        )
    
    def test_analyzer_initialization(self):
        """Test FileAnalyzer initialization with different configurations."""
        # Default initialization
        analyzer = FileAnalyzer()
        assert not analyzer.enable_fingerprinting
        assert analyzer.enable_defect_detection
        assert analyzer.integrity_level == IntegrityLevel.CHECKSUM
        assert analyzer.min_health_score == 50.0
        
        # Custom initialization
        analyzer = FileAnalyzer(
            enable_fingerprinting=True,
            enable_defect_detection=False,
            integrity_level=IntegrityLevel.DEEP,
            min_health_score=70.0
        )
        assert analyzer.enable_fingerprinting
        assert not analyzer.enable_defect_detection
        assert analyzer.integrity_level == IntegrityLevel.DEEP
        assert analyzer.min_health_score == 70.0
    
    @patch('src.music_cleanup.modules.simple_metadata_manager.SimpleMetadataManager.extract_metadata')
    @patch('src.music_cleanup.modules.simple_quality_analyzer.SimpleQualityAnalyzer.analyze_quality')
    @patch('src.music_cleanup.utils.integrity.IntegrityChecker.check_integrity')
    def test_analyze_file_success(self, mock_integrity, mock_quality, mock_metadata, analyzer, test_audio_file):
        """Test successful file analysis."""
        # Mock responses
        mock_metadata.return_value = {
            'title': 'Test Song',
            'artist': 'Test Artist',
            'duration': 180.0,
            'bitrate': 320000,
            'sample_rate': 44100,
            'channels': 2
        }
        
        mock_quality.return_value = {
            'bitrate': 320000,
            'sample_rate': 44100,
            'channels': 2,
            'quality_score': 0.85
        }
        
        mock_integrity.return_value = (True, "abc123def456")
        
        # Analyze file
        result = analyzer.analyze_file(test_audio_file)
        
        # Verify result
        assert result is not None
        assert isinstance(result, FileAnalysisResult)
        assert result.file_path == test_audio_file
        assert result.file_size > 0
        assert result.format == ".mp3"
        assert result.has_metadata
        assert result.metadata['title'] == 'Test Song'
        assert result.duration == 180.0
        assert result.bitrate == 320000
        assert result.quality_score == 85.0  # Converted from 0.85
        assert result.is_healthy
        assert result.integrity_verified
        assert result.checksum == "abc123def456"
        assert result.processed_successfully
    
    def test_analyze_file_invalid_format(self, analyzer, temp_dir):
        """Test analysis of unsupported file format."""
        file_path = Path(temp_dir) / "test.txt"
        file_path.write_text("Not an audio file")
        
        result = analyzer.analyze_file(str(file_path))
        
        assert result is not None
        assert not result.is_healthy
        assert result.skip_reason == "Unsupported format: .txt"
        assert not result.processed_successfully
    
    def test_analyze_file_too_small(self, analyzer, temp_dir):
        """Test analysis of file that's too small."""
        file_path = Path(temp_dir) / "tiny.mp3"
        file_path.write_bytes(b"MP3")  # Only 3 bytes
        
        with patch('src.music_cleanup.core.constants.MIN_FILE_SIZE', 100):
            result = analyzer.analyze_file(str(file_path))
        
        assert result is not None
        assert not result.is_healthy
        assert "File too small" in result.skip_reason
    
    @patch('src.music_cleanup.modules.simple_metadata_manager.SimpleMetadataManager.extract_metadata')
    def test_analyze_file_metadata_failure(self, mock_metadata, analyzer, test_audio_file):
        """Test handling of metadata extraction failure."""
        mock_metadata.return_value = None
        
        result = analyzer.analyze_file(test_audio_file)
        
        assert result is not None
        assert not result.has_metadata
        assert "Failed to extract metadata" in result.health_issues
        assert not result.is_healthy
    
    @patch('src.music_cleanup.modules.simple_metadata_manager.SimpleMetadataManager.extract_metadata')
    @patch('src.music_cleanup.modules.simple_quality_analyzer.SimpleQualityAnalyzer.analyze_quality')
    def test_analyze_file_low_quality(self, mock_quality, mock_metadata, analyzer, test_audio_file):
        """Test detection of low quality files."""
        mock_metadata.return_value = {'duration': 180.0}
        mock_quality.return_value = {
            'quality_score': 0.3,  # Low quality
            'bitrate': 96000
        }
        
        result = analyzer.analyze_file(test_audio_file)
        
        assert result is not None
        assert result.quality_score == 30.0
        assert not result.is_healthy
        assert any("Low quality score" in issue for issue in result.health_issues)
    
    @patch('src.music_cleanup.modules.simple_metadata_manager.SimpleMetadataManager.extract_metadata')
    @patch('src.music_cleanup.utils.integrity.IntegrityChecker.check_integrity')
    def test_analyze_file_integrity_failure(self, mock_integrity, mock_metadata, analyzer, test_audio_file):
        """Test handling of integrity check failure."""
        mock_metadata.return_value = {'duration': 180.0}
        mock_integrity.return_value = (False, None)
        
        result = analyzer.analyze_file(test_audio_file)
        
        assert result is not None
        assert not result.integrity_verified
        assert not result.is_healthy
        assert "Integrity check failed" in result.health_issues
        assert result.corruption_level == "high"
    
    @patch('src.music_cleanup.modules.simple_metadata_manager.SimpleMetadataManager.extract_metadata')
    @patch('src.music_cleanup.modules.simple_fingerprinter.SimpleFingerprinter.generate_fingerprint')
    def test_analyze_file_with_fingerprint(self, mock_fingerprint, mock_metadata, analyzer, test_audio_file):
        """Test fingerprint generation."""
        mock_metadata.return_value = {'duration': 180.0}
        mock_fingerprint.return_value = "fingerprint123"
        
        result = analyzer.analyze_file(test_audio_file)
        
        assert result is not None
        assert result.fingerprint == "fingerprint123"
        assert result.fingerprint_algorithm == "chromaprint"
    
    def test_analyze_batch(self, analyzer, temp_dir):
        """Test batch file analysis."""
        # Create test files
        files = []
        for i in range(3):
            file_path = Path(temp_dir) / f"song_{i}.mp3"
            file_path.write_bytes(b"MP3" + b"\x00" * 1000)
            files.append(str(file_path))
        
        # Mock successful analysis
        with patch.object(analyzer, 'analyze_file') as mock_analyze:
            mock_analyze.side_effect = [
                FileAnalysisResult(
                    file_path=files[i],
                    file_size=1003,
                    file_mtime=0,
                    processed_successfully=True,
                    quality_score=70 + i * 10
                ) for i in range(3)
            ]
            
            # Analyze batch
            results = analyzer.analyze_batch(files)
            
            assert len(results) == 3
            assert all(r.processed_successfully for r in results)
            assert results[0].quality_score == 70
            assert results[1].quality_score == 80
            assert results[2].quality_score == 90
    
    def test_analyze_batch_with_progress(self, analyzer, temp_dir):
        """Test batch analysis with progress callback."""
        files = [str(Path(temp_dir) / f"song_{i}.mp3") for i in range(3)]
        for file in files:
            Path(file).write_bytes(b"MP3" + b"\x00" * 1000)
        
        progress_updates = []
        
        def progress_callback(info):
            progress_updates.append(info)
        
        with patch.object(analyzer, 'analyze_file') as mock_analyze:
            mock_analyze.return_value = FileAnalysisResult(
                file_path="",
                file_size=1003,
                file_mtime=0,
                processed_successfully=True
            )
            
            analyzer.analyze_batch(files, progress_callback)
            
            assert len(progress_updates) == 3
            assert progress_updates[0]['current'] == 1
            assert progress_updates[0]['total'] == 3
            assert progress_updates[2]['current'] == 3
    
    def test_performance_summary(self, analyzer):
        """Test performance metrics tracking."""
        # No metrics initially
        summary = analyzer.get_performance_summary()
        assert len(summary) == 0
        
        # TODO: Test performance tracking after implementing decorator
        # This would require actually calling methods with @track_performance
    
    def test_file_validation(self, analyzer, temp_dir):
        """Test various file validation scenarios."""
        # Test non-existent file
        result = analyzer.analyze_file("/path/that/does/not/exist.mp3")
        assert result is None  # Should be caught by @validate_path
        
        # Test directory instead of file
        result = analyzer.analyze_file(temp_dir)
        assert result is None
    
    @patch('src.music_cleanup.audio.defect_detection.DefectDetector.analyze_audio_health')
    @patch('src.music_cleanup.modules.simple_metadata_manager.SimpleMetadataManager.extract_metadata')
    def test_defect_detection(self, mock_metadata, mock_defects, analyzer, test_audio_file):
        """Test audio defect detection integration."""
        from src.music_cleanup.audio.defect_detection import AudioHealthReport, AudioDefect, DefectType
        
        mock_metadata.return_value = {'duration': 180.0}
        
        # Mock defect detection
        mock_defects.return_value = AudioHealthReport(
            file_path=test_audio_file,
            is_healthy=False,
            health_score=40.0,
            defects=[
                AudioDefect(
                    defect_type=DefectType.CLIPPING,
                    severity="critical",
                    timestamp=10.5,
                    duration=0.5,
                    description="Severe clipping detected"
                )
            ],
            metadata_accessible=True
        )
        
        result = analyzer.analyze_file(test_audio_file)
        
        assert result is not None
        assert not result.is_healthy
        assert "CLIPPING: Severe clipping detected" in result.health_issues
        assert result.corruption_level == "critical"
    
    def test_error_handling(self, analyzer):
        """Test error handling in file analysis."""
        # Test with None path
        result = analyzer.analyze_file(None)
        assert result is None
        
        # Test with empty string
        result = analyzer.analyze_file("")
        assert result is None
    
    def test_concurrent_analysis(self, analyzer, temp_dir):
        """Test thread safety of FileAnalyzer."""
        import threading
        
        files = []
        for i in range(5):
            file_path = Path(temp_dir) / f"concurrent_{i}.mp3"
            file_path.write_bytes(b"MP3" + b"\x00" * 1000)
            files.append(str(file_path))
        
        results = []
        lock = threading.Lock()
        
        def analyze_file(file_path):
            result = analyzer.analyze_file(file_path)
            with lock:
                results.append(result)
        
        # Create threads
        threads = []
        for file_path in files:
            thread = threading.Thread(target=analyze_file, args=(file_path,))
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Verify results
        assert len(results) == 5
        assert all(r is not None for r in results)