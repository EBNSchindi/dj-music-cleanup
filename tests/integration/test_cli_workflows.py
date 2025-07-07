"""
Integration tests for CLI end-to-end workflows.

Tests the complete CLI functionality including all operational modes
and their integration with the orchestrator and underlying modules.
"""

import pytest
import tempfile
import shutil
import subprocess
import sys
import json
from pathlib import Path
from unittest.mock import patch, Mock

from src.music_cleanup.cli.main import (
    main, run_analysis_mode, run_organize_mode, 
    run_cleanup_mode, run_recovery_mode
)


class TestCLIWorkflows:
    """Integration tests for CLI workflows."""
    
    @pytest.fixture
    def temp_workspace(self):
        """Create temporary workspace with test files."""
        workspace = tempfile.mkdtemp()
        test_dir = Path(workspace)
        
        # Create test music directory structure
        music_dir = test_dir / 'music'
        music_dir.mkdir()
        
        # Create fake audio files with different formats
        (music_dir / 'song1.mp3').write_text('fake mp3 content - artist1 - title1')
        (music_dir / 'song2.flac').write_text('fake flac content - artist2 - title2')
        (music_dir / 'song3.wav').write_text('fake wav content - artist1 - title3')
        (music_dir / 'duplicate.mp3').write_text('fake mp3 content - artist1 - title1')  # Duplicate
        
        # Create subdirectories
        subdir = music_dir / 'Electronic'
        subdir.mkdir()
        (subdir / 'electronic1.mp3').write_text('fake electronic mp3')
        
        # Create output directory
        output_dir = test_dir / 'output'
        output_dir.mkdir()
        
        # Create workspace for temp files
        work_dir = test_dir / 'workspace'
        work_dir.mkdir()
        
        yield {
            'base': test_dir,
            'music': music_dir,
            'output': output_dir,
            'workspace': work_dir
        }
        
        shutil.rmtree(workspace, ignore_errors=True)
    
    @pytest.fixture
    def mock_args_base(self, temp_workspace):
        """Base mock arguments for CLI functions."""
        class MockArgs:
            def __init__(self):
                self.source_folders = [str(temp_workspace['music'])]
                self.output = str(temp_workspace['output'])
                self.workspace = str(temp_workspace['workspace'])
                self.config = None
                self.dry_run = True
                self.enable_recovery = False
                self.enable_fingerprinting = False
                self.skip_duplicates = True  # Speed up tests
                self.integrity_level = 'basic'
                self.batch_size = 5
                self.max_workers = 1
                self.memory_limit = 512
                self.progress = 'none'
                self.report = None
                self.recovery_id = None
                self.checkpoint_interval = 300
                self.log_level = 'WARNING'
                self.log_file = None
        
        return MockArgs()


class TestAnalysisMode:
    """Test analysis mode functionality."""
    
    def test_run_analysis_mode_basic(self, temp_workspace, mock_args_base):
        """Test basic analysis mode execution."""
        args = mock_args_base
        args.report = str(temp_workspace['base'] / 'analysis_report.html')
        
        # Mock the orchestrator components to avoid dependencies
        with patch('src.music_cleanup.cli.main.get_config') as mock_config:
            mock_config.return_value = {
                'audio_formats': ['.mp3', '.flac', '.wav'],
                'skip_duplicates': True
            }
            
            with patch('src.music_cleanup.cli.main.MusicCleanupOrchestrator') as mock_orchestrator_class:
                mock_orchestrator = Mock()
                mock_orchestrator_class.return_value = mock_orchestrator
                
                # Mock analysis results
                mock_orchestrator.analyze_library.return_value = {
                    'total_files': 5,
                    'total_size_bytes': 25000000,
                    'audio_formats': {'.mp3': 3, '.flac': 1, '.wav': 1},
                    'duplicate_groups': [['file1.mp3', 'file1_copy.mp3']],
                    'metadata_issues': [],
                    'integrity_issues': [],
                    'analysis_duration': 2.5
                }
                
                # Run analysis mode
                result = run_analysis_mode(args)
                
                # Verify successful execution
                assert result == 0
                
                # Verify orchestrator was called correctly
                mock_orchestrator_class.assert_called_once()
                mock_orchestrator.analyze_library.assert_called_once_with(
                    source_folders=args.source_folders,
                    report_path=args.report,
                    progress_callback=None
                )
                mock_orchestrator.cleanup.assert_called_once()
    
    def test_analysis_mode_with_progress_callback(self, temp_workspace, mock_args_base):
        """Test analysis mode with detailed progress."""
        args = mock_args_base
        args.progress = 'detailed'
        
        with patch('src.music_cleanup.cli.main.get_config') as mock_config:
            mock_config.return_value = {'skip_duplicates': True}
            
            with patch('src.music_cleanup.cli.main.MusicCleanupOrchestrator') as mock_orchestrator_class:
                mock_orchestrator = Mock()
                mock_orchestrator_class.return_value = mock_orchestrator
                
                mock_orchestrator.analyze_library.return_value = {
                    'total_files': 2,
                    'total_size_bytes': 10000000,
                    'audio_formats': {'.mp3': 2},
                    'duplicate_groups': [],
                    'metadata_issues': [],
                    'integrity_issues': [],
                    'analysis_duration': 1.0
                }
                
                result = run_analysis_mode(args)
                
                assert result == 0
                
                # Verify progress callback was provided
                call_args = mock_orchestrator.analyze_library.call_args
                assert call_args[1]['progress_callback'] is not None


class TestOrganizeMode:
    """Test organize mode functionality."""
    
    def test_run_organize_mode_basic(self, temp_workspace, mock_args_base):
        """Test basic organize mode execution."""
        args = mock_args_base
        
        with patch('src.music_cleanup.cli.main.get_config') as mock_config:
            mock_config.return_value = {
                'output_directory': args.output,
                'enable_fingerprinting': False,
                'skip_duplicates': True,
                'integrity_level': 'basic'
            }
            
            with patch('src.music_cleanup.cli.main.MusicCleanupOrchestrator') as mock_orchestrator_class:
                mock_orchestrator = Mock()
                mock_orchestrator_class.return_value = mock_orchestrator
                
                # Mock organization results
                mock_orchestrator.organize_library.return_value = {
                    'files_processed': 5,
                    'files_organized': 4,
                    'files_skipped': 1,
                    'errors': 0,
                    'duplicates_handled': 1,
                    'space_saved': 5000000,
                    'organization_duration': 10.5
                }
                
                result = run_organize_mode(args)
                
                assert result == 0
                
                # Verify orchestrator was configured correctly
                mock_orchestrator_class.assert_called_once()
                init_args = mock_orchestrator_class.call_args
                assert init_args[1]['dry_run'] is True
                assert init_args[1]['enable_recovery'] is False
                
                # Verify organize_library was called
                mock_orchestrator.organize_library.assert_called_once()
                organize_args = mock_orchestrator.organize_library.call_args
                assert organize_args[1]['source_folders'] == args.source_folders
                assert organize_args[1]['output_directory'] == args.output
                assert organize_args[1]['enable_fingerprinting'] is False
    
    def test_organize_mode_with_fingerprinting(self, temp_workspace, mock_args_base):
        """Test organize mode with fingerprinting enabled."""
        args = mock_args_base
        args.enable_fingerprinting = True
        args.skip_duplicates = False
        
        with patch('src.music_cleanup.cli.main.get_config') as mock_config:
            mock_config.return_value = {}
            
            with patch('src.music_cleanup.cli.main.MusicCleanupOrchestrator') as mock_orchestrator_class:
                mock_orchestrator = Mock()
                mock_orchestrator_class.return_value = mock_orchestrator
                
                mock_orchestrator.organize_library.return_value = {
                    'files_processed': 5,
                    'files_organized': 4,
                    'files_skipped': 0,
                    'errors': 1,
                    'duplicates_handled': 2,
                    'space_saved': 10000000,
                    'organization_duration': 25.0
                }
                
                result = run_organize_mode(args)
                
                assert result == 0
                
                # Verify fingerprinting was enabled
                organize_args = mock_orchestrator.organize_library.call_args
                assert organize_args[1]['enable_fingerprinting'] is True
    
    def test_organize_mode_with_report_generation(self, temp_workspace, mock_args_base):
        """Test organize mode with report generation."""
        args = mock_args_base
        args.report = str(temp_workspace['base'] / 'organize_report.html')
        
        with patch('src.music_cleanup.cli.main.get_config') as mock_config:
            mock_config.return_value = {}
            
            with patch('src.music_cleanup.cli.main.MusicCleanupOrchestrator') as mock_orchestrator_class:
                mock_orchestrator = Mock()
                mock_orchestrator_class.return_value = mock_orchestrator
                
                mock_orchestrator.organize_library.return_value = {
                    'files_processed': 3,
                    'files_organized': 3,
                    'files_skipped': 0,
                    'errors': 0,
                    'duplicates_handled': 0,
                    'space_saved': 0,
                    'organization_duration': 5.0
                }
                
                with patch('src.music_cleanup.cli.main._generate_organization_report') as mock_report:
                    result = run_organize_mode(args)
                    
                    assert result == 0
                    mock_report.assert_called_once()


class TestCleanupMode:
    """Test cleanup mode functionality."""
    
    def test_run_cleanup_mode_basic(self, temp_workspace, mock_args_base):
        """Test basic cleanup mode execution."""
        args = mock_args_base
        args.enable_fingerprinting = True
        
        with patch('src.music_cleanup.cli.main.get_config') as mock_config:
            mock_config.return_value = {
                'enable_fingerprinting': True,
                'skip_duplicates': False,
                'integrity_level': 'basic'
            }
            
            with patch('src.music_cleanup.cli.main.MusicCleanupOrchestrator') as mock_orchestrator_class:
                mock_orchestrator = Mock()
                mock_orchestrator_class.return_value = mock_orchestrator
                
                # Mock cleanup results
                mock_orchestrator.cleanup_library.return_value = {
                    'files_scanned': 10,
                    'duplicates_found': 3,
                    'duplicates_removed': 2,
                    'space_reclaimed': 15000000,
                    'errors': 1,
                    'cleanup_duration': 8.5
                }
                
                result = run_cleanup_mode(args)
                
                assert result == 0
                
                # Verify cleanup_library was called correctly
                mock_orchestrator.cleanup_library.assert_called_once()
                cleanup_args = mock_orchestrator.cleanup_library.call_args
                assert cleanup_args[1]['source_folders'] == args.source_folders
                assert cleanup_args[1]['enable_fingerprinting'] is True
    
    def test_cleanup_mode_with_detailed_progress(self, temp_workspace, mock_args_base):
        """Test cleanup mode with detailed progress reporting."""
        args = mock_args_base
        args.progress = 'detailed'
        
        with patch('src.music_cleanup.cli.main.get_config') as mock_config:
            mock_config.return_value = {}
            
            with patch('src.music_cleanup.cli.main.MusicCleanupOrchestrator') as mock_orchestrator_class:
                mock_orchestrator = Mock()
                mock_orchestrator_class.return_value = mock_orchestrator
                
                mock_orchestrator.cleanup_library.return_value = {
                    'files_scanned': 5,
                    'duplicates_found': 1,
                    'duplicates_removed': 1,
                    'space_reclaimed': 5000000,
                    'errors': 0,
                    'cleanup_duration': 3.0
                }
                
                result = run_cleanup_mode(args)
                
                assert result == 0
                
                # Verify progress callback was provided
                cleanup_args = mock_orchestrator.cleanup_library.call_args
                assert cleanup_args[1]['progress_callback'] is not None


class TestRecoveryMode:
    """Test recovery mode functionality."""
    
    def test_run_recovery_mode_basic(self, temp_workspace, mock_args_base):
        """Test basic recovery mode execution."""
        args = mock_args_base
        args.enable_recovery = True  # Must be enabled for recovery mode
        args.recovery_id = 'session_test_123'
        
        with patch('src.music_cleanup.cli.main.get_config') as mock_config:
            mock_config.return_value = {}
            
            with patch('src.music_cleanup.cli.main.MusicCleanupOrchestrator') as mock_orchestrator_class:
                mock_orchestrator = Mock()
                mock_orchestrator_class.return_value = mock_orchestrator
                
                # Mock successful recovery
                mock_orchestrator.recover_from_crash.return_value = {
                    'recovery_successful': True,
                    'checkpoint_used': 'checkpoint_123',
                    'files_recovered': 15,
                    'operations_rolled_back': 3,
                    'duration': 5.2
                }
                
                result = run_recovery_mode(args)
                
                assert result == 0
                
                # Verify recovery was called correctly
                mock_orchestrator.recover_from_crash.assert_called_once()
                recovery_args = mock_orchestrator.recover_from_crash.call_args
                assert recovery_args[1]['recovery_id'] == 'session_test_123'
    
    def test_recovery_mode_auto_detect(self, temp_workspace, mock_args_base):
        """Test recovery mode with auto-detection."""
        args = mock_args_base
        args.enable_recovery = True
        args.recovery_id = None  # Auto-detect
        
        with patch('src.music_cleanup.cli.main.get_config') as mock_config:
            mock_config.return_value = {}
            
            with patch('src.music_cleanup.cli.main.MusicCleanupOrchestrator') as mock_orchestrator_class:
                mock_orchestrator = Mock()
                mock_orchestrator_class.return_value = mock_orchestrator
                
                mock_orchestrator.recover_from_crash.return_value = {
                    'recovery_successful': True,
                    'checkpoint_used': 'auto-detected',
                    'files_recovered': 8,
                    'operations_rolled_back': 1,
                    'duration': 2.1
                }
                
                result = run_recovery_mode(args)
                
                assert result == 0
                
                # Verify auto-detection was used
                recovery_args = mock_orchestrator.recover_from_crash.call_args
                assert recovery_args[1]['recovery_id'] is None
    
    def test_recovery_mode_failed_recovery(self, temp_workspace, mock_args_base):
        """Test recovery mode with failed recovery."""
        args = mock_args_base
        args.enable_recovery = True
        
        with patch('src.music_cleanup.cli.main.get_config') as mock_config:
            mock_config.return_value = {}
            
            with patch('src.music_cleanup.cli.main.MusicCleanupOrchestrator') as mock_orchestrator_class:
                mock_orchestrator = Mock()
                mock_orchestrator_class.return_value = mock_orchestrator
                
                # Mock failed recovery
                mock_orchestrator.recover_from_crash.return_value = {
                    'recovery_successful': False,
                    'checkpoint_used': 'checkpoint_456',
                    'files_recovered': 0,
                    'operations_rolled_back': 0,
                    'error': 'Checkpoint corrupted',
                    'duration': 1.5
                }
                
                result = run_recovery_mode(args)
                
                assert result == 1  # Should return error code


class TestCLIHelperFunctions:
    """Test CLI helper functions."""
    
    def test_create_streaming_config(self, mock_args_base):
        """Test streaming configuration creation."""
        from src.music_cleanup.cli.main import _create_streaming_config
        
        args = mock_args_base
        args.batch_size = 100
        args.max_workers = 8
        args.memory_limit = 2048
        
        config = _create_streaming_config(args)
        
        assert config.batch_size == 100
        assert config.max_workers == 8
        assert config.memory_limit_mb == 2048
    
    def test_get_enabled_features(self, mock_args_base):
        """Test feature enumeration."""
        from src.music_cleanup.cli.main import _get_enabled_features
        
        args = mock_args_base
        args.enable_recovery = True
        args.enable_fingerprinting = True
        args.skip_duplicates = False
        args.integrity_level = 'deep'
        
        features = _get_enabled_features(args)
        
        assert 'Recovery' in features
        assert 'Fingerprinting' in features
        assert 'Duplicate Detection' in features
        assert 'Integrity: deep' in features


class TestCLIIntegration:
    """Full CLI integration tests."""
    
    def test_cli_help_command(self):
        """Test CLI help functionality."""
        # Test that help doesn't crash
        with patch('sys.argv', ['music-cleanup', '--help']):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
    
    def test_cli_version_command(self):
        """Test CLI version functionality."""
        with patch('sys.argv', ['music-cleanup', '--version']):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0
    
    def test_cli_missing_arguments(self):
        """Test CLI with missing required arguments."""
        with patch('sys.argv', ['music-cleanup']):
            result = main()
            assert result == 1  # Should fail due to missing arguments
    
    def test_cli_invalid_source_folder(self):
        """Test CLI with invalid source folder."""
        with patch('sys.argv', ['music-cleanup', '/nonexistent', '-o', '/tmp/output']):
            result = main()
            assert result == 1  # Should fail validation
    
    def test_cli_full_workflow_dry_run(self, temp_workspace):
        """Test complete CLI workflow in dry run mode."""
        source = str(temp_workspace['music'])
        output = str(temp_workspace['output'])
        
        # Mock sys.argv for main() function
        test_args = [
            'music-cleanup',
            source,
            '-o', output,
            '--dry-run',
            '--mode', 'organize',
            '--progress', 'none',
            '--log-level', 'ERROR'  # Suppress output
        ]
        
        with patch('sys.argv', test_args):
            with patch('src.music_cleanup.cli.main.get_config') as mock_config:
                mock_config.return_value = {
                    'audio_formats': ['.mp3', '.flac', '.wav'],
                    'skip_duplicates': True
                }
                
                with patch('src.music_cleanup.cli.main.MusicCleanupOrchestrator') as mock_orchestrator_class:
                    mock_orchestrator = Mock()
                    mock_orchestrator_class.return_value = mock_orchestrator
                    
                    mock_orchestrator.organize_library.return_value = {
                        'files_processed': 5,
                        'files_organized': 5,
                        'files_skipped': 0,
                        'errors': 0,
                        'duplicates_handled': 0,
                        'space_saved': 0,
                        'organization_duration': 2.0
                    }
                    
                    result = main()
                    
                    assert result == 0
                    mock_orchestrator.organize_library.assert_called_once()


class TestErrorHandling:
    """Test error handling in CLI workflows."""
    
    def test_keyboard_interrupt_handling(self, temp_workspace, mock_args_base):
        """Test graceful handling of keyboard interrupts."""
        args = mock_args_base
        
        with patch('src.music_cleanup.cli.main.get_config') as mock_config:
            mock_config.return_value = {}
            
            with patch('src.music_cleanup.cli.main.MusicCleanupOrchestrator') as mock_orchestrator_class:
                mock_orchestrator = Mock()
                mock_orchestrator_class.return_value = mock_orchestrator
                
                # Simulate keyboard interrupt
                mock_orchestrator.analyze_library.side_effect = KeyboardInterrupt()
                
                result = run_analysis_mode(args)
                
                assert result == 130  # Standard interrupt exit code
    
    def test_exception_handling(self, temp_workspace, mock_args_base):
        """Test handling of unexpected exceptions."""
        args = mock_args_base
        
        with patch('src.music_cleanup.cli.main.get_config') as mock_config:
            mock_config.return_value = {}
            
            with patch('src.music_cleanup.cli.main.MusicCleanupOrchestrator') as mock_orchestrator_class:
                mock_orchestrator = Mock()
                mock_orchestrator_class.return_value = mock_orchestrator
                
                # Simulate unexpected error
                mock_orchestrator.organize_library.side_effect = RuntimeError("Unexpected error")
                
                result = run_organize_mode(args)
                
                assert result == 1  # Error exit code
    
    def test_configuration_error_handling(self, temp_workspace, mock_args_base):
        """Test handling of configuration errors."""
        args = mock_args_base
        args.config = '/nonexistent/config.json'
        
        # This should be caught by validate_arguments
        from src.music_cleanup.cli.main import validate_arguments
        
        result = validate_arguments(args)
        assert result is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])