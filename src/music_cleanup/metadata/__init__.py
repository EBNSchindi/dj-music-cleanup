"""
Metadata-First Processing System for DJ Music Cleanup Tool

Implements a robust metadata acquisition pipeline with strict priority order:
1. Audio Fingerprint Lookup (AcoustID/MusicBrainz) - ALWAYS FIRST
2. File Tags Fallback - Only if fingerprint fails
3. Intelligent Filename Parsing - Last resort
4. Metadata Queue - Never use "Unknown"
"""

from .fingerprint_processor import FingerprintProcessor
from .metadata_manager import MetadataManager
from .filename_parser import FilenameParser
from .metadata_queue import MetadataQueue
from .api_services import AcoustIDService, MusicBrainzService

__all__ = [
    'FingerprintProcessor',
    'MetadataManager', 
    'FilenameParser',
    'MetadataQueue',
    'AcoustIDService',
    'MusicBrainzService'
]