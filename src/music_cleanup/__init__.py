"""
DJ Music Cleanup Tool

A professional DJ music library cleanup and organization tool with streaming
architecture, transactional safety, and crash recovery capabilities.

Features:
- Memory-efficient streaming architecture (O(1) memory complexity)
- Atomic file operations with ACID guarantees
- Crash recovery and checkpoint system
- Multi-level file integrity checking
- Audio fingerprinting and duplicate detection
- Metadata extraction and standardization
- Intelligent file organization
"""

__version__ = "2.0.0"
__author__ = "DJ Music Cleanup Contributors"
__email__ = "dj-music-cleanup@example.com"
__license__ = "MIT"

# Export main classes and functions
from .core.config import Config, get_config
from .core.database import DatabaseManager, get_database_manager
from .core.streaming import StreamingConfig, FileDiscoveryStream, ParallelStreamProcessor
from .core.transactions import AtomicFileOperations
from .core.recovery import CrashRecoveryManager, CheckpointType, RecoveryState
from .core.rollback import RollbackManager, RollbackScope
from .utils.integrity import FileIntegrityChecker, IntegrityLevel

__all__ = [
    "__version__",
    "__author__", 
    "__email__",
    "__license__",
    "Config",
    "get_config",
    "DatabaseManager",
    "get_database_manager",
    "StreamingConfig",
    "FileDiscoveryStream", 
    "ParallelStreamProcessor",
    "AtomicFileOperations",
    "CrashRecoveryManager",
    "CheckpointType",
    "RecoveryState",
    "RollbackManager",
    "RollbackScope",
    "FileIntegrityChecker",
    "IntegrityLevel",
]