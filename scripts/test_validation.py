#!/usr/bin/env python3
"""
Test validation script to verify the new orchestrator and CLI functionality.

This script performs basic validation of the implemented features without
requiring external test framework dependencies.
"""

import sys
import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

def validate_orchestrator_import():
    """Test that orchestrator can be imported successfully."""
    try:
        from music_cleanup.core.orchestrator import MusicCleanupOrchestrator
        from music_cleanup.core.config import Config
        from music_cleanup.core.streaming import StreamingConfig
        print("✅ Orchestrator import successful")
        return True
    except ImportError as e:
        print(f"❌ Orchestrator import failed: {e}")
        return False

def validate_cli_import():
    """Test that CLI can be imported successfully."""
    try:
        from music_cleanup.cli.main import (
            main, run_analysis_mode, run_organize_mode,
            run_cleanup_mode, run_recovery_mode
        )
        print("✅ CLI import successful")
        return True
    except ImportError as e:
        print(f"❌ CLI import failed: {e}")
        return False

def validate_orchestrator_initialization():
    """Test orchestrator can be initialized."""
    try:
        from music_cleanup.core.orchestrator import MusicCleanupOrchestrator
        from music_cleanup.core.streaming import StreamingConfig
        
        config = {
            'output_directory': '/tmp/test',
            'audio_formats': ['.mp3', '.flac'],
            'skip_duplicates': True
        }
        
        streaming_config = StreamingConfig(batch_size=10, max_workers=2)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('music_cleanup.core.orchestrator.get_database_manager'):
                orchestrator = MusicCleanupOrchestrator(
                    config=config,
                    streaming_config=streaming_config,
                    workspace_dir=temp_dir,
                    enable_recovery=False,
                    dry_run=True
                )
                
                # Test basic properties
                assert orchestrator.config is not None
                assert orchestrator.streaming_config is not None
                assert orchestrator.session_id is not None
                
                print("✅ Orchestrator initialization successful")
                return True
                
    except Exception as e:
        print(f"❌ Orchestrator initialization failed: {e}")
        return False

def validate_cli_functions():
    """Test CLI functions can be called with mock data."""
    try:
        from music_cleanup.cli.main import (
            run_analysis_mode, run_organize_mode,
            run_cleanup_mode, run_recovery_mode,
            _create_streaming_config, _get_enabled_features
        )
        
        # Create mock arguments
        class MockArgs:
            def __init__(self):
                self.source_folders = ['/tmp/test']
                self.output = '/tmp/output'
                self.workspace = '/tmp/workspace'
                self.config = None
                self.dry_run = True
                self.enable_recovery = False
                self.enable_fingerprinting = False
                self.skip_duplicates = True
                self.integrity_level = 'basic'
                self.batch_size = 5
                self.max_workers = 1
                self.memory_limit = 512
                self.progress = 'none'
                self.report = None
                self.recovery_id = None
                
        args = MockArgs()
        
        # Test helper functions
        streaming_config = _create_streaming_config(args)
        assert streaming_config.batch_size == 5
        
        features = _get_enabled_features(args)
        assert isinstance(features, list)
        
        print("✅ CLI helper functions working")
        
        # Test CLI functions with mocking
        with patch('music_cleanup.cli.main.get_config') as mock_config:
            mock_config.return_value = {'skip_duplicates': True}
            
            with patch('music_cleanup.cli.main.MusicCleanupOrchestrator') as mock_orchestrator_class:
                mock_orchestrator = Mock()
                mock_orchestrator_class.return_value = mock_orchestrator
                
                # Mock successful results
                mock_orchestrator.analyze_library.return_value = {
                    'total_files': 5,
                    'total_size_bytes': 25000000,
                    'audio_formats': {'.mp3': 3, '.flac': 2},
                    'duplicate_groups': [],
                    'metadata_issues': [],
                    'integrity_issues': [],
                    'analysis_duration': 2.5
                }
                
                mock_orchestrator.organize_library.return_value = {
                    'files_processed': 5,
                    'files_organized': 4,
                    'files_skipped': 1,
                    'errors': 0,
                    'duplicates_handled': 0,
                    'space_saved': 0,
                    'organization_duration': 10.5
                }
                
                mock_orchestrator.cleanup_library.return_value = {
                    'files_scanned': 10,
                    'duplicates_found': 3,
                    'duplicates_removed': 2,
                    'space_reclaimed': 15000000,
                    'errors': 1,
                    'cleanup_duration': 8.5
                }
                
                mock_orchestrator.recover_from_crash.return_value = {
                    'recovery_successful': True,
                    'checkpoint_used': 'checkpoint_123',
                    'files_recovered': 15,
                    'operations_rolled_back': 3,
                    'duration': 5.2
                }
                
                # Test all mode functions
                result = run_analysis_mode(args)
                assert result == 0
                
                result = run_organize_mode(args)
                assert result == 0
                
                result = run_cleanup_mode(args)
                assert result == 0
                
                args.enable_recovery = True
                result = run_recovery_mode(args)
                assert result == 0
                
                print("✅ All CLI mode functions working")
                return True
                
    except Exception as e:
        print(f"❌ CLI function validation failed: {e}")
        return False

def validate_orchestrator_methods():
    """Test orchestrator key methods."""
    try:
        from music_cleanup.core.orchestrator import MusicCleanupOrchestrator
        from music_cleanup.core.streaming import StreamingConfig
        
        config = {
            'output_directory': '/tmp/test',
            'audio_formats': ['.mp3', '.flac'],
            'skip_duplicates': True,
            'integrity_level': 'basic'
        }
        
        streaming_config = StreamingConfig(batch_size=5, max_workers=1)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('music_cleanup.core.orchestrator.get_database_manager'):
                orchestrator = MusicCleanupOrchestrator(
                    config=config,
                    streaming_config=streaming_config,
                    workspace_dir=temp_dir,
                    enable_recovery=False,
                    dry_run=True
                )
                
                # Test utility methods
                decade = orchestrator._get_decade(2023)
                assert decade == '2020s'
                
                quality = orchestrator._categorize_quality(320)
                assert quality == 'lossless'
                
                signature = orchestrator._create_metadata_signature({
                    'artist': 'Test Artist',
                    'title': 'Test Song',
                    'duration': 180
                })
                assert signature == 'test artist|test song|180'
                
                # Test file skipping logic
                skip = orchestrator._should_skip_file('/test/file.txt')
                assert skip is True  # .txt not in audio_formats
                
                skip = orchestrator._should_skip_file('/test/file.mp3')
                assert skip is False  # .mp3 is in audio_formats
                
                # Test statistics
                stats = orchestrator.get_statistics()
                assert 'session_id' in stats
                assert 'statistics' in stats
                
                print("✅ Orchestrator methods working")
                return True
                
    except Exception as e:
        print(f"❌ Orchestrator method validation failed: {e}")
        return False

def validate_module_integration():
    """Test that modules can be lazy-loaded."""
    try:
        from music_cleanup.core.orchestrator import MusicCleanupOrchestrator
        from music_cleanup.core.streaming import StreamingConfig
        
        config = {'skip_duplicates': True}
        streaming_config = StreamingConfig()
        
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('music_cleanup.core.orchestrator.get_database_manager'):
                orchestrator = MusicCleanupOrchestrator(
                    config=config,
                    streaming_config=streaming_config,
                    workspace_dir=temp_dir,
                    enable_recovery=False,
                    dry_run=True
                )
                
                # Initially modules should be None (lazy loading)
                assert orchestrator._fingerprinter is None
                assert orchestrator._metadata_manager is None
                assert orchestrator._quality_analyzer is None
                assert orchestrator._organizer is None
                assert orchestrator._integrity_checker is None
                
                print("✅ Module lazy loading working")
                return True
                
    except Exception as e:
        print(f"❌ Module integration validation failed: {e}")
        return False

def main():
    """Run all validation tests."""
    print("🔍 Validating DJ Music Cleanup Tool v2.0 Implementation\n")
    
    tests = [
        ("Import Tests", validate_orchestrator_import),
        ("CLI Import", validate_cli_import),
        ("Orchestrator Init", validate_orchestrator_initialization),
        ("CLI Functions", validate_cli_functions),
        ("Orchestrator Methods", validate_orchestrator_methods),
        ("Module Integration", validate_module_integration),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n🧪 {test_name}:")
        try:
            if test_func():
                passed += 1
            else:
                print(f"❌ {test_name} failed")
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
    
    print(f"\n📊 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All validation tests passed! Implementation is working correctly.")
        return 0
    else:
        print("⚠️  Some validation tests failed. Check the implementation.")
        return 1

if __name__ == '__main__':
    sys.exit(main())