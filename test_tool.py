#!/usr/bin/env python3
"""
Test script for the DJ Music Cleanup Tool
This script tests all major components without requiring Chromaprint
"""
import os
import sys
import tempfile
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config import Config
from modules.fingerprinting import AudioFingerprinter
from modules.metadata import MetadataManager
from modules.organizer import FileOrganizer
from utils.progress import setup_logging, ProgressTracker


def test_config():
    """Test configuration management"""
    print("Testing configuration management...")
    
    # Test default config
    config = Config()
    assert config.get('batch_size', 0) > 0
    
    # Test genre mapping
    assert config.get_genre_category('house') == 'House'
    assert config.get_genre_category('techno') == 'Techno'
    assert config.get_genre_category('unknown') == 'Unknown'
    
    # Test decade conversion
    assert config.get_decade_from_year(1995) == '1990s'
    assert config.get_decade_from_year(2005) == '2000s'
    assert config.get_decade_from_year(2025) == '2020s'
    
    print("✓ Configuration tests passed")


def test_metadata_manager():
    """Test metadata extraction and cleaning"""
    print("Testing metadata management...")
    
    metadata_manager = MetadataManager(enable_musicbrainz=False)
    
    # Test filename parsing
    test_files = [
        "01. Avicii - Levels (Radio Edit).mp3",
        "Avicii-Levels.mp3",
        "levels_avicii_320.mp3",
        "03 - Swedish House Mafia - One.mp3"
    ]
    
    for filename in test_files:
        metadata = metadata_manager._extract_from_filename(filename)
        print(f"  {filename} -> Artist: {metadata.get('artist')}, Title: {metadata.get('title')}")
    
    # Test filename cleaning
    clean_name = metadata_manager.clean_filename("Avicii", "Levels (Radio Edit)", ".mp3")
    assert clean_name == "Avicii - Levels (Radio Edit).mp3"
    
    # Test genre normalization
    assert metadata_manager._normalize_genre("house") == "House"
    assert metadata_manager._normalize_genre("tech house") == "Tech House"
    
    print("✓ Metadata tests passed")


def test_fingerprinting():
    """Test fingerprinting module (without actual audio files)"""
    print("Testing fingerprinting module...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = os.path.join(temp_dir, "test_fingerprints.db")
        fingerprinter = AudioFingerprinter(db_path=db_path)
        
        # Test database initialization
        assert os.path.exists(db_path)
        
        # Test file hash generation
        test_file = os.path.join(temp_dir, "test.txt")
        with open(test_file, 'w') as f:
            f.write("test content")
        
        file_hash = fingerprinter.get_file_hash(test_file)
        assert file_hash is not None
        
        # Test statistics
        stats = fingerprinter.get_statistics()
        assert 'total_files' in stats
        
        print("✓ Fingerprinting tests passed")


def test_organizer():
    """Test file organization"""
    print("Testing file organizer...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        target_dir = os.path.join(temp_dir, "organized")
        organizer = FileOrganizer(target_dir)
        
        # Test directory creation
        test_dir = organizer.create_target_structure("House", "2010s")
        assert test_dir.exists()
        assert "House" in str(test_dir)
        assert "2010s" in str(test_dir)
        
        # Test filename sanitization
        safe_name = organizer._sanitize_folder_name("House/Deep House")
        assert "/" not in safe_name
        
        # Test year to decade conversion
        assert organizer._year_to_decade(2015) == "2010s"
        assert organizer._year_to_decade(1995) == "1990s"
        
        print("✓ Organizer tests passed")


def test_progress_tracker():
    """Test progress tracking"""
    print("Testing progress tracker...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = os.path.join(temp_dir, "progress.db")
        tracker = ProgressTracker(total_items=100, desc="Test", 
                                 db_path=db_path, enable_resume=True)
        
        # Test updates
        tracker.update(1)
        tracker.update(1, error=True)
        tracker.update(1, skip=True)
        
        stats = tracker.get_stats()
        assert stats['processed'] == 1
        assert stats['errors'] == 1
        assert stats['skipped'] == 1
        
        tracker.close()
        
        print("✓ Progress tracker tests passed")


def test_full_integration():
    """Test full integration without real audio files"""
    print("Testing full integration...")
    
    # Create test config
    test_config = {
        'source_folders': [],
        'target_folder': '/tmp/test_target',
        'enable_musicbrainz': False,
        'batch_size': 10,
        'multiprocessing_workers': 1
    }
    
    config = Config()
    config.update(test_config)
    
    # Test validation
    errors = config.validate()
    # Should have some errors due to missing folders
    assert len(errors) > 0
    
    print("✓ Integration tests passed")


def create_test_files():
    """Create some test audio files for testing"""
    print("Creating test files...")
    
    test_dir = "/home/vboxuser/claude-projects-secure/music_test_data/input"
    
    # Create some dummy files with realistic names
    test_files = [
        "01. Avicii - Levels (Radio Edit).mp3",
        "02 - Swedish House Mafia - One.mp3",
        "03-David Guetta-Titanium.mp3",
        "levels_avicii_320.mp3",  # Duplicate
        "Avicii-Levels.flac",     # Better quality duplicate
        "04 - Deadmau5 - Ghosts n Stuff.mp3",
        "Unknown Artist - Unknown Title.mp3",
        "track05.mp3",
        "Calvin Harris - Feel So Close (2011).mp3",
        "Tiësto - Adagio For Strings.mp3"
    ]
    
    for filename in test_files:
        filepath = os.path.join(test_dir, filename)
        with open(filepath, 'wb') as f:
            # Create dummy MP3 header (just for testing)
            f.write(b'\xFF\xFB\x90\x00')  # MP3 sync word
            f.write(b'ID3')  # ID3 tag
            f.write(b'\x00' * 100000)  # Padding (make files larger for testing)
    
    print(f"Created {len(test_files)} test files in {test_dir}")


def main():
    """Run all tests"""
    print("=" * 60)
    print("DJ Music Cleanup Tool - Testing Suite")
    print("=" * 60)
    
    # Setup logging
    setup_logging(log_level='INFO', console=True)
    
    try:
        test_config()
        test_metadata_manager()
        test_fingerprinting()
        test_organizer()
        test_progress_tracker()
        test_full_integration()
        
        print("\n" + "=" * 60)
        print("ALL TESTS PASSED! ✓")
        print("=" * 60)
        
        # Ask if user wants to create test files (skip in non-interactive mode)
        try:
            response = input("\nCreate test files for manual testing? (y/n): ")
            if response.lower() == 'y':
                create_test_files()
                print("\nYou can now run:")
                print("python music_cleanup.py --scan-only --config test_config.json")
                print("python music_cleanup.py --dry-run --config test_config.json")
        except EOFError:
            print("\nNon-interactive mode - creating test files automatically...")
            create_test_files()
            print("\nYou can now run:")
            print("python music_cleanup.py --scan-only --config test_config.json")
            print("python music_cleanup.py --dry-run --config test_config.json")
            
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()