"""
Shared pytest fixtures for DJ Music Cleanup Tool tests.

Eliminates duplicated test code by providing common fixtures
for configuration, databases, and file structures.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, MagicMock
from collections import defaultdict

from src.music_cleanup.core.config import Config
from src.music_cleanup.core.streaming import StreamingConfig
from src.music_cleanup.core.config_manager import MusicCleanupConfig
from src.music_cleanup.core.unified_database import UnifiedDatabase


@pytest.fixture
def temp_workspace():
    """Create temporary workspace directory."""
    workspace = tempfile.mkdtemp()
    yield workspace
    shutil.rmtree(workspace, ignore_errors=True)


@pytest.fixture
def temp_music_library():
    """Create temporary music library with test files."""
    library = tempfile.mkdtemp()
    
    # Create sample directory structure
    (Path(library) / "Artist1" / "Album1").mkdir(parents=True)
    (Path(library) / "Artist2" / "Album2").mkdir(parents=True)
    (Path(library) / "Various" / "Compilation").mkdir(parents=True)
    
    # Create sample files
    sample_files = [
        "Artist1/Album1/01 - Track 1.mp3",
        "Artist1/Album1/02 - Track 2.flac", 
        "Artist2/Album2/01 - Another Track.mp3",
        "Various/Compilation/01 - Mixed Track.wav"
    ]
    
    for file_path in sample_files:
        full_path = Path(library) / file_path
        full_path.write_bytes(b"fake audio data for testing")
    
    yield library
    shutil.rmtree(library, ignore_errors=True)


@pytest.fixture
def mock_config():
    """Create mock configuration dictionary."""
    return {
        'output_directory': '/test/output',
        'audio_formats': ['.mp3', '.flac', '.wav'],
        'quality_threshold': 192,
        'enable_fingerprinting': False,
        'skip_duplicates': False,
        'integrity_level': 'checksum',
        'protected_paths': [],
        'min_health_score': 70,
        'fingerprint_length': 120,
        'batch_size': 1000,
        'max_workers': 2,
        'silence_threshold': 0.001,
        'defect_sample_duration': 30.0
    }


@pytest.fixture
def streaming_config():
    """Create streaming configuration."""
    return StreamingConfig(
        batch_size=10,
        max_workers=2,
        memory_limit_mb=100
    )


@pytest.fixture
def mock_file_info():
    """Create mock file information for testing."""
    return {
        'file_path': '/test/path/track.mp3',
        'file_size': 5242880,  # 5MB
        'modified_time': 1640995200,  # 2022-01-01
        'hash': 'mock_hash_123',
        'metadata': {
            'title': 'Test Track',
            'artist': 'Test Artist',
            'album': 'Test Album',
            'duration': 180.0,
            'bitrate': 320,
            'format': 'MP3'
        },
        'health_score': 85.0,
        'defects': [],
        'is_duplicate': False
    }


@pytest.fixture
def mock_corrupted_file_info():
    """Create mock corrupted file information for testing."""
    return {
        'file_path': '/test/path/corrupted.mp3',
        'file_size': 1024,  # Very small
        'modified_time': 1640995200,
        'hash': 'corrupted_hash_456',
        'metadata': {},
        'health_score': 15.0,  # Very low
        'defects': ['truncated_file', 'corrupted_header'],
        'is_duplicate': False
    }


@pytest.fixture
def mock_duplicate_group():
    """Create mock duplicate group for testing."""
    return {
        'signature': 'duplicate_sig_789',
        'files': [
            {
                'file_path': '/test/path/original.mp3',
                'health_score': 90.0,
                'metadata': {'bitrate': 320, 'duration': 180.0}
            },
            {
                'file_path': '/test/path/copy.mp3', 
                'health_score': 85.0,
                'metadata': {'bitrate': 256, 'duration': 180.0}
            }
        ],
        'best_version': '/test/path/original.mp3'
    }


@pytest.fixture
def mock_progress_callback():
    """Create mock progress callback function."""
    return Mock()


@pytest.fixture
def mock_database(temp_workspace):
    """Create mock database for testing."""
    db_path = Path(temp_workspace) / "test.db"
    db = UnifiedDatabase(str(db_path))
    db.initialize()
    yield db
    db.close()


@pytest.fixture 
def mock_config_manager(mock_config, temp_workspace):
    """Create mock configuration manager."""
    config_file = Path(temp_workspace) / "config.json"
    config_manager = Mock()
    config_manager.get_config.return_value = MusicCleanupConfig(**mock_config)
    config_manager.config_file = str(config_file)
    config_manager.save_config = Mock()
    return config_manager


@pytest.fixture
def sample_analyzed_files():
    """Create sample analyzed files list for testing."""
    return [
        {
            'file_path': '/test/good_file1.mp3',
            'health_score': 90.0,
            'defects': [],
            'metadata': {'artist': 'Artist1', 'title': 'Track1'}
        },
        {
            'file_path': '/test/good_file2.flac',
            'health_score': 95.0, 
            'defects': [],
            'metadata': {'artist': 'Artist2', 'title': 'Track2'}
        },
        {
            'file_path': '/test/corrupted_file.mp3',
            'health_score': 20.0,
            'defects': ['truncated_file'],
            'metadata': {'artist': 'Artist3', 'title': 'Corrupted'}
        }
    ]