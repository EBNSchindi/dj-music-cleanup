"""
Unit tests for MusicCleanupOrchestrator.

Tests the central orchestrator functionality including module coordination,
streaming pipeline, and error handling.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from collections import defaultdict

from src.music_cleanup.core.orchestrator import MusicCleanupOrchestrator
from src.music_cleanup.core.config import Config
from src.music_cleanup.core.streaming import StreamingConfig


class TestMusicCleanupOrchestrator:
    """Test suite for MusicCleanupOrchestrator."""
    
    @pytest.fixture
    def temp_workspace(self):
        """Create temporary workspace directory."""
        workspace = tempfile.mkdtemp()
        yield workspace
        shutil.rmtree(workspace, ignore_errors=True)
    
    @pytest.fixture
    def mock_config(self):
        """Create mock configuration."""
        return {
            'output_directory': '/test/output',
            'audio_formats': ['.mp3', '.flac', '.wav'],
            'quality_threshold': 192,
            'enable_fingerprinting': False,
            'skip_duplicates': False,
            'integrity_level': 'checksum',
            'protected_paths': []
        }
    
    @pytest.fixture
    def streaming_config(self):
        """Create streaming configuration."""
        return StreamingConfig(
            file_discovery_batch_size=10,
            max_workers=2,
            max_memory_usage_mb=100
        )
    
    @pytest.fixture
    def orchestrator(self, mock_config, streaming_config, temp_workspace):
        """Create orchestrator instance for testing."""
        with patch('src.music_cleanup.core.orchestrator.get_database_manager'):
            return MusicCleanupOrchestrator(
                config=mock_config,
                streaming_config=streaming_config,
                workspace_dir=temp_workspace,
                enable_recovery=False,  # Disable for unit tests
                dry_run=True
            )
    
    def test_orchestrator_initialization(self, orchestrator, temp_workspace):
        """Test orchestrator initialization."""
        assert orchestrator.config is not None
        assert orchestrator.streaming_config is not None
        assert orchestrator.workspace_dir == Path(temp_workspace)
        assert orchestrator.dry_run is True
        assert orchestrator.session_id is not None
        assert orchestrator.operation_group is not None
    
    def test_lazy_loading_modules(self, orchestrator):
        """Test that modules are lazy-loaded."""
        # Initially, modules should be None
        assert orchestrator._fingerprinter is None
        assert orchestrator._metadata_manager is None
        assert orchestrator._quality_analyzer is None
        assert orchestrator._organizer is None
        assert orchestrator._integrity_checker is None
        
        # Accessing properties should initialize modules
        with patch('src.music_cleanup.core.orchestrator.AudioFingerprinter'):
            fingerprinter = orchestrator.fingerprinter
            assert fingerprinter is not None
            assert orchestrator._fingerprinter is not None
    
    @patch('src.music_cleanup.core.orchestrator.FileDiscoveryStream')
    @patch('src.music_cleanup.core.orchestrator.StreamingProgressTracker')
    def test_analyze_library_basic(self, mock_progress, mock_discovery, orchestrator):
        """Test basic library analysis functionality."""
        # Mock file discovery
        mock_discovery.return_value.stream_files.return_value = [
            '/test/file1.mp3',
            '/test/file2.flac'
        ]
        
        # Mock progress tracker
        mock_progress.return_value.__enter__.return_value = Mock()
        
        # Mock file analysis
        with patch.object(orchestrator, '_analyze_single_file') as mock_analyze:
            mock_analyze.return_value = {
                'size': 5000000,
                'format': '.mp3',
                'quality_category': 'high',
                'genre': 'Electronic',
                'decade': '2020s',
                'metadata_issues': [],
                'integrity_status': 'healthy'
            }
            
            # Mock duplicate detection
            with patch.object(orchestrator, '_detect_duplicates_streaming') as mock_duplicates:
                mock_duplicates.return_value = []
                
                # Run analysis
                results = orchestrator.analyze_library(['/test/music'])
                
                # Verify results structure
                assert 'total_files' in results
                assert 'audio_formats' in results
                assert 'quality_distribution' in results
                assert 'duplicate_groups' in results
                assert 'metadata_issues' in results
                assert 'integrity_issues' in results
                assert 'analysis_duration' in results
                
                # Verify file counting
                assert results['total_files'] == 2
                assert results['total_size_bytes'] == 10000000  # 2 files * 5MB each
    
    def test_analyze_single_file(self, orchestrator):
        """Test single file analysis."""
        test_file = '/test/sample.mp3'
        
        # Mock file size
        with patch('os.path.getsize', return_value=3000000):
            # Mock integrity checker
            mock_integrity_result = Mock()
            mock_integrity_result.status.value = 'healthy'
            mock_integrity_result.issues = []
            
            with patch.object(orchestrator, 'integrity_checker') as mock_checker:
                mock_checker.check_file_integrity.return_value = mock_integrity_result
                
                # Mock metadata extraction
                with patch.object(orchestrator, 'metadata_manager') as mock_metadata:
                    mock_metadata.extract_metadata_streaming.return_value = {
                        'artist': 'Test Artist',
                        'title': 'Test Song',
                        'genre': 'Electronic',
                        'year': 2023,
                        'bitrate': 320,
                        'duration': 180
                    }
                    
                    # Mock quality analysis
                    with patch.object(orchestrator, 'quality_analyzer') as mock_quality:
                        mock_quality.analyze_file.return_value = {
                            'overall_score': 0.85
                        }
                        
                        result = orchestrator._analyze_single_file(test_file)
                        
                        # Verify result structure
                        assert result['path'] == test_file
                        assert result['size'] == 3000000
                        assert result['format'] == '.mp3'
                        assert result['artist'] == 'Test Artist'
                        assert result['title'] == 'Test Song'
                        assert result['quality_category'] == 'lossless'  # 320kbps
                        assert result['decade'] == '2020s'
                        assert result['integrity_status'] == 'healthy'
    
    @patch('src.music_cleanup.core.orchestrator.ParallelStreamProcessor')
    @patch('src.music_cleanup.core.orchestrator.FileDiscoveryStream')
    @patch('src.music_cleanup.core.orchestrator.StreamingProgressTracker')
    def test_organize_library_basic(self, mock_progress, mock_discovery, mock_processor, orchestrator):
        """Test basic library organization functionality."""
        # Mock file discovery
        mock_discovery.return_value.stream_files.return_value = [
            '/test/file1.mp3',
            '/test/file2.flac'
        ]
        
        # Mock progress tracker
        mock_progress.return_value.__enter__.return_value = Mock()
        
        # Mock processor results
        mock_processor.return_value.process_stream.return_value = [
            [
                {'success': True, 'destination': '/output/Electronic/2020s/Artist - Song.mp3'},
                {'success': True, 'destination': '/output/Rock/2010s/Band - Track.flac'}
            ]
        ]
        
        # Mock organizer
        with patch.object(orchestrator, 'organizer') as mock_organizer:
            mock_organizer.begin_organization_session.return_value = None
            mock_organizer.finalize.return_value = None
            
            results = orchestrator.organize_library(
                source_folders=['/test/music'],
                output_directory='/test/output'
            )
            
            # Verify results
            assert results['files_processed'] == 2
            assert results['files_organized'] == 2
            assert results['files_skipped'] == 0
            assert results['errors'] == 0
            assert 'organization_duration' in results
    
    def test_process_file_for_organization(self, orchestrator):
        """Test processing single file for organization."""
        test_file = '/test/sample.mp3'
        
        # Mock should_skip_file
        with patch.object(orchestrator, '_should_skip_file', return_value=False):
            # Mock metadata extraction
            with patch.object(orchestrator, 'metadata_manager') as mock_metadata:
                mock_metadata.extract_metadata_streaming.return_value = {
                    'artist': 'Test Artist',
                    'title': 'Test Song',
                    'genre': 'Electronic',
                    'year': 2023
                }
                
                # Mock organizer
                with patch.object(orchestrator, 'organizer') as mock_organizer:
                    mock_target_dir = Path('/output/Electronic/2020s')
                    mock_organizer.create_target_structure_atomic.return_value = mock_target_dir
                    
                    result = orchestrator._process_file_for_organization(test_file)
                    
                    # Verify result in dry run mode
                    assert result['file'] == test_file
                    assert result['success'] is True
                    assert result['skipped'] is False
                    assert 'Test Artist - Test Song.mp3' in result['destination']
    
    def test_detect_duplicates_streaming_metadata(self, orchestrator):
        """Test metadata-based duplicate detection."""
        source_folders = ['/test/music']
        
        # Mock file discovery
        with patch('src.music_cleanup.core.orchestrator.FileDiscoveryStream') as mock_discovery:
            mock_discovery.return_value.stream_files.return_value = [
                '/test/song1.mp3',
                '/test/song2.mp3',
                '/test/song1_copy.mp3'  # Duplicate
            ]
            
            # Mock metadata extraction
            metadata_responses = [
                {'artist': 'Artist A', 'title': 'Song 1', 'duration': 180},
                {'artist': 'Artist B', 'title': 'Song 2', 'duration': 200},
                {'artist': 'Artist A', 'title': 'Song 1', 'duration': 180}  # Duplicate
            ]
            
            with patch.object(orchestrator, 'metadata_manager') as mock_metadata:
                mock_metadata.extract_metadata_streaming.side_effect = metadata_responses
                
                # Mock file sizes
                with patch('os.path.getsize', side_effect=[5000000, 6000000, 5000000]):
                    # Mock quality analysis
                    with patch.object(orchestrator, 'quality_analyzer') as mock_quality:
                        mock_quality.analyze_file.return_value = {'overall_score': 0.8}
                        
                        duplicate_groups = orchestrator._detect_duplicates_streaming(source_folders)
                        
                        # Should find one duplicate group with 2 files
                        assert len(duplicate_groups) == 1
                        assert len(duplicate_groups[0]) == 2
    
    def test_select_best_duplicate(self, orchestrator):
        """Test selecting the best file from duplicate group."""
        duplicate_group = [
            {
                'file_path': '/test/song_low.mp3',
                'quality_score': 0.6,
                'size': 3000000
            },
            {
                'file_path': '/test/song_high.mp3',
                'quality_score': 0.9,
                'size': 5000000
            },
            {
                'file_path': '/test/song_medium.mp3',
                'quality_score': 0.7,
                'size': 4000000
            }
        ]
        
        keep_file, remove_files = orchestrator._select_best_duplicate(duplicate_group)
        
        # Should keep the highest quality file
        assert keep_file == '/test/song_high.mp3'
        assert len(remove_files) == 2
        assert '/test/song_low.mp3' in remove_files
        assert '/test/song_medium.mp3' in remove_files
    
    def test_should_skip_file(self, orchestrator):
        """Test file skipping logic."""
        # Test protected path
        orchestrator.config['protected_paths'] = ['/protected']
        assert orchestrator._should_skip_file('/protected/file.mp3') is True
        assert orchestrator._should_skip_file('/normal/file.mp3') is False
        
        # Test file extension filtering
        orchestrator.config['protected_paths'] = []
        orchestrator.config['audio_formats'] = ['.mp3', '.flac']
        assert orchestrator._should_skip_file('/test/file.txt') is True
        assert orchestrator._should_skip_file('/test/file.mp3') is False
    
    def test_create_metadata_signature(self, orchestrator):
        """Test metadata signature creation."""
        # Valid metadata
        metadata = {
            'artist': 'Test Artist',
            'title': 'Test Song',
            'duration': 180
        }
        signature = orchestrator._create_metadata_signature(metadata)
        assert signature == 'test artist|test song|180'
        
        # Missing essential data
        metadata_incomplete = {'artist': '', 'title': 'Song'}
        signature = orchestrator._create_metadata_signature(metadata_incomplete)
        assert signature is None
    
    def test_get_decade(self, orchestrator):
        """Test decade extraction from year."""
        assert orchestrator._get_decade(2023) == '2020s'
        assert orchestrator._get_decade(1995) == '1990s'
        assert orchestrator._get_decade(None) == 'Unknown'
        assert orchestrator._get_decade('invalid') == 'Unknown'
    
    def test_categorize_quality(self, orchestrator):
        """Test audio quality categorization."""
        assert orchestrator._categorize_quality(320) == 'lossless'
        assert orchestrator._categorize_quality(256) == 'high'
        assert orchestrator._categorize_quality(192) == 'good'
        assert orchestrator._categorize_quality(128) == 'acceptable'
        assert orchestrator._categorize_quality(96) == 'low'
    
    def test_get_statistics(self, orchestrator):
        """Test statistics retrieval."""
        orchestrator.start_time = 1000.0
        orchestrator.stats['files_processed'] = 100
        
        with patch('time.time', return_value=1060.0):  # 60 seconds later
            stats = orchestrator.get_statistics()
            
            assert stats['session_id'] == orchestrator.session_id
            assert stats['operation_group'] == orchestrator.operation_group
            assert stats['statistics']['files_processed'] == 100
            assert stats['duration_seconds'] == 60.0
            assert stats['dry_run'] is True
    
    def test_cleanup_resources(self, orchestrator):
        """Test resource cleanup."""
        # Mock modules for cleanup
        orchestrator._fingerprinter = Mock()
        orchestrator.atomic_ops = Mock()
        
        orchestrator.cleanup()
        
        # Verify cleanup calls
        orchestrator._fingerprinter.cleanup.assert_called_once()
        orchestrator.atomic_ops.cleanup_old_backups.assert_called_once()
    
    @patch('src.music_cleanup.core.orchestrator.StreamingProgressTracker')
    def test_memory_monitoring(self, mock_progress, orchestrator):
        """Test memory monitoring during processing."""
        # Mock memory monitor
        orchestrator.memory_monitor.check_memory_usage = Mock()
        
        # Mock progress tracker
        mock_progress.return_value.__enter__.return_value = Mock()
        
        # Mock file analysis that triggers memory check
        with patch.object(orchestrator, '_analyze_single_file') as mock_analyze:
            mock_analyze.return_value = {
                'size': 1000000,
                'format': '.mp3',
                'quality_category': 'high',
                'metadata_issues': [],
                'integrity_status': 'healthy'
            }
            
            with patch.object(orchestrator, '_detect_duplicates_streaming') as mock_duplicates:
                mock_duplicates.return_value = []
                
                with patch('src.music_cleanup.core.orchestrator.FileDiscoveryStream') as mock_discovery:
                    mock_discovery.return_value.stream_files.return_value = ['/test/file.mp3']
                    
                    orchestrator.analyze_library(['/test'])
                    
                    # Verify memory monitoring was called
                    orchestrator.memory_monitor.check_memory_usage.assert_called()
    
    def test_error_handling_in_analysis(self, orchestrator):
        """Test error handling during file analysis."""
        with patch('src.music_cleanup.core.orchestrator.FileDiscoveryStream') as mock_discovery:
            mock_discovery.return_value.stream_files.return_value = ['/test/corrupt.mp3']
            
            with patch('src.music_cleanup.core.orchestrator.StreamingProgressTracker') as mock_progress:
                mock_progress_tracker = Mock()
                mock_progress.return_value.__enter__.return_value = mock_progress_tracker
                
                # Mock file analysis that raises exception
                with patch.object(orchestrator, '_analyze_single_file', side_effect=Exception("Corrupt file")):
                    with patch.object(orchestrator, '_detect_duplicates_streaming', return_value=[]):
                        results = orchestrator.analyze_library(['/test'])
                        
                        # Should handle error gracefully
                        assert results['total_files'] == 0
                        assert orchestrator.stats['analysis_errors'] == 1
                        
                        # Progress should be updated with error
                        mock_progress_tracker.update.assert_called_with(1, has_error=True)


class TestOrchestratorIntegration:
    """Integration tests for orchestrator with real components."""
    
    @pytest.fixture
    def temp_test_files(self):
        """Create temporary test music files."""
        workspace = tempfile.mkdtemp()
        test_dir = Path(workspace) / 'test_music'
        test_dir.mkdir()
        
        # Create fake audio files
        (test_dir / 'song1.mp3').write_text('fake mp3 content')
        (test_dir / 'song2.flac').write_text('fake flac content')
        
        yield test_dir
        shutil.rmtree(workspace, ignore_errors=True)
    
    def test_orchestrator_with_real_files(self, temp_test_files):
        """Test orchestrator with real file system."""
        config = {
            'output_directory': str(temp_test_files.parent / 'output'),
            'audio_formats': ['.mp3', '.flac'],
            'skip_duplicates': True,  # Skip for faster test
            'integrity_level': 'basic'
        }
        
        streaming_config = StreamingConfig(batch_size=5, max_workers=1)
        
        with patch('src.music_cleanup.core.orchestrator.get_database_manager'):
            orchestrator = MusicCleanupOrchestrator(
                config=config,
                streaming_config=streaming_config,
                workspace_dir=str(temp_test_files.parent / 'workspace'),
                enable_recovery=False,
                dry_run=True
            )
            
            # Test analysis mode
            results = orchestrator.analyze_library([str(temp_test_files)])
            
            assert results['total_files'] == 2
            assert '.mp3' in results['audio_formats']
            assert '.flac' in results['audio_formats']
            
            orchestrator.cleanup()


if __name__ == '__main__':
    pytest.main([__file__])