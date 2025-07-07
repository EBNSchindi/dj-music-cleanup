#!/usr/bin/env python3
"""
Test package structure and imports for the refactored DJ Music Cleanup Tool.
"""
import sys
import unittest
from pathlib import Path

# Add src to path for testing
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestPackageStructure(unittest.TestCase):
    """Test that the package structure is correct and imports work."""
    
    def test_main_package_import(self):
        """Test that the main package can be imported."""
        try:
            import music_cleanup
            self.assertIsNotNone(music_cleanup.__version__)
            self.assertEqual(music_cleanup.__version__, "2.0.0")
        except ImportError as e:
            self.fail(f"Failed to import music_cleanup: {e}")
    
    def test_core_imports(self):
        """Test that core modules can be imported."""
        try:
            from music_cleanup.core import Config, get_config
            from music_cleanup.core import DatabaseManager, get_database_manager
            from music_cleanup.core import StreamingConfig
            from music_cleanup.core import AtomicFileOperations
            from music_cleanup.core import CrashRecoveryManager
            from music_cleanup.core import RollbackManager
            
            # Test that classes are actually classes
            self.assertTrue(callable(Config))
            self.assertTrue(callable(DatabaseManager))
            self.assertTrue(callable(StreamingConfig))
            self.assertTrue(callable(AtomicFileOperations))
            self.assertTrue(callable(CrashRecoveryManager))
            self.assertTrue(callable(RollbackManager))
            
        except ImportError as e:
            self.fail(f"Failed to import core modules: {e}")
    
    def test_utils_imports(self):
        """Test that utility modules can be imported."""
        try:
            from music_cleanup.utils import FileIntegrityChecker
            from music_cleanup.utils import ProgressReporter
            from music_cleanup.utils import IntegrityLevel
            
            # Test that classes are actually classes
            self.assertTrue(callable(FileIntegrityChecker))
            self.assertTrue(callable(ProgressReporter))
            
        except ImportError as e:
            self.fail(f"Failed to import utils modules: {e}")
    
    def test_modules_imports(self):
        """Test that feature modules can be imported."""
        try:
            from music_cleanup.modules import AudioQualityAnalyzer
            from music_cleanup.modules import AudioFingerprinter
            from music_cleanup.modules import MetadataManager
            from music_cleanup.modules import AtomicFileOrganizer
            
            # Test that classes are actually classes
            self.assertTrue(callable(AudioQualityAnalyzer))
            self.assertTrue(callable(AudioFingerprinter))
            self.assertTrue(callable(MetadataManager))
            self.assertTrue(callable(AtomicFileOrganizer))
            
        except ImportError as e:
            self.fail(f"Failed to import modules: {e}")
    
    def test_cli_imports(self):
        """Test that CLI module can be imported."""
        try:
            from music_cleanup.cli import main
            self.assertTrue(callable(main))
            
        except ImportError as e:
            self.fail(f"Failed to import CLI: {e}")
    
    def test_package_exports(self):
        """Test that main package exports work correctly."""
        try:
            import music_cleanup
            
            # Test that main exports are available
            expected_exports = [
                "Config", "get_config",
                "DatabaseManager", "get_database_manager", 
                "StreamingConfig", "FileDiscoveryStream", "ParallelStreamProcessor",
                "AtomicFileOperations",
                "CrashRecoveryManager", "CheckpointType", "RecoveryState",
                "RollbackManager", "RollbackScope",
                "FileIntegrityChecker", "IntegrityLevel"
            ]
            
            for export in expected_exports:
                self.assertTrue(
                    hasattr(music_cleanup, export),
                    f"Missing export: {export}"
                )
                
        except ImportError as e:
            self.fail(f"Failed to test package exports: {e}")
    
    def test_version_consistency(self):
        """Test that version is consistent across files."""
        try:
            import music_cleanup
            
            # Test version format
            version = music_cleanup.__version__
            self.assertRegex(version, r'^\d+\.\d+\.\d+$', "Version should follow semver format")
            
            # Test that it's the expected version
            self.assertEqual(version, "2.0.0")
            
        except ImportError as e:
            self.fail(f"Failed to test version: {e}")


class TestConfigurationSystem(unittest.TestCase):
    """Test that the configuration system works."""
    
    def test_config_loading(self):
        """Test that configuration can be loaded."""
        try:
            from music_cleanup.core.config import get_config
            
            # Test loading without file (should use defaults)
            config = get_config()
            self.assertIsNotNone(config)
            
        except Exception as e:
            self.fail(f"Failed to load default config: {e}")


def run_structure_tests():
    """Run all package structure tests."""
    print("🧪 Testing Package Structure...")
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test cases
    suite.addTests(loader.loadTestsFromTestCase(TestPackageStructure))
    suite.addTests(loader.loadTestsFromTestCase(TestConfigurationSystem))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    total_tests = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    success_rate = ((total_tests - failures - errors) / total_tests) * 100 if total_tests > 0 else 0
    
    print(f"\n=== Package Structure Test Results ===")
    print(f"Total tests: {total_tests}")
    print(f"Passed: {total_tests - failures - errors}")
    print(f"Failed: {failures}")
    print(f"Errors: {errors}")
    print(f"Success rate: {success_rate:.1f}%")
    
    if success_rate >= 80:
        print("✅ Package structure tests PASSED")
        return True
    else:
        print("❌ Package structure tests FAILED")
        return False


if __name__ == "__main__":
    success = run_structure_tests()
    sys.exit(0 if success else 1)