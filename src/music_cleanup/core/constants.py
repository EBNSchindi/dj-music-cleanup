"""
Core Constants for DJ Music Cleanup Tool

Zentrale Konfiguration aller Magic Numbers und Schwellwerte.
"""

# Health Score Thresholds
MIN_HEALTH_SCORE_DEFAULT = 30  # Lowered from 70 - only filter truly corrupted files
CRITICAL_HEALTH_THRESHOLD = 10  # Files below this are critically corrupted  
EXCELLENT_HEALTH_THRESHOLD = 90
MAX_HEALTH_SCORE = 100

# Batch Processing
DEFAULT_BATCH_SIZE = 1000
MAX_BATCH_SIZE = 10000
MEMORY_CHECK_INTERVAL = 100
FINGERPRINT_BATCH_SIZE = 10000

# Duplicate Detection
FINGERPRINT_MATCH_THRESHOLD = 0.95
MIN_DURATION_MATCH = 0.98  # 98% Duration-Übereinstimmung
DUPLICATE_SIMILARITY_THRESHOLD = 0.85

# Performance & Threading
DEFAULT_WORKER_THREADS = 4
MAX_WORKER_THREADS = 16
MAX_CONCURRENT_WORKERS = 8      # For async processing
PROGRESS_UPDATE_INTERVAL = 100  # Files processed before progress update

# Async Processing Configuration
ASYNC_BATCH_SIZE_METADATA = 50  # Smaller batches for metadata extraction
ASYNC_BATCH_SIZE_QUALITY = 25   # Quality analysis is CPU intensive
ASYNC_BATCH_SIZE_FINGERPRINT = 20  # Fingerprinting is very CPU intensive
ASYNC_TASK_TIMEOUT = 60.0       # Timeout for async tasks (seconds)

# File Size Limits
MIN_AUDIO_FILE_SIZE = 100_000      # 100KB - Smaller files likely corrupted
MAX_AUDIO_FILE_SIZE = 500_000_000  # 500MB - Larger files likely not audio
SUSPICIOUS_FILE_SIZE = 1024        # Files smaller than 1KB are suspicious

# Audio Format Specific
MP3_MIN_DURATION = 10.0     # Minimum track duration for DJ use (seconds)
MP3_MAX_DURATION = 3600.0   # Maximum track duration (1 hour)
SAMPLE_ANALYSIS_DURATION = 30.0  # Duration to analyze for defects

# Silence Detection
SILENCE_THRESHOLD = 0.001      # Amplitude threshold for silence
MAX_SILENCE_START = 10.0       # Max silence at file start (seconds)
MAX_SILENCE_END = 10.0         # Max silence at file end (seconds)
MAX_SILENCE_RATIO = 0.8        # Max 80% silence in file

# Clipping Detection
CLIPPING_THRESHOLD = 0.98      # Amplitude threshold for clipping
MAX_CLIPPING_RATIO = 0.05      # Max 5% clipped samples

# Truncation Detection
MP3_FRAME_SYNC_BYTES = b'\xFF\xE0'  # MP3 frame sync pattern
PADDING_TOLERANCE = 0.75       # 75% repeated bytes indicates truncation
SIZE_MISMATCH_TOLERANCE = 0.9  # 10% file size tolerance

# Critical Defects (automatic quarantine)
CRITICAL_DEFECTS = [
    'truncated_file',
    'corrupted_header', 
    'complete_silence',
    'decode_failure',
    'sync_errors',
    'metadata_corruption',
    'encoding_errors'
]

# Database Configuration
DB_WAL_MODE = True
DB_TIMEOUT = 30.0              # Database timeout in seconds
DB_CHECKPOINT_INTERVAL = 1000  # Operations before checkpoint

# Memory Management
MEMORY_LIMIT_MB = 512          # Soft memory limit in MB
GARBAGE_COLLECTION_INTERVAL = 1000  # Files processed before GC

# Quarantine Configuration
QUARANTINE_FOLDER_NAME = "CORRUPTED_QUARANTINE"
REPORTS_FOLDER_NAME = "Reports"
MAX_QUARANTINE_FILES = 10000   # Safety limit

# CLI Display
CONSOLE_WIDTH = 120
PROGRESS_REFRESH_RATE = 10     # Progress updates per second
STATUS_DISPLAY_LINES = 5

# File Extensions
SUPPORTED_AUDIO_FORMATS = {
    '.mp3': 'MP3',
    '.flac': 'FLAC', 
    '.wav': 'WAV',
    '.m4a': 'M4A',
    '.aac': 'AAC',
    '.ogg': 'OGG',
    '.wma': 'WMA'
}

# Quality Scoring Weights
QUALITY_WEIGHTS = {
    'format': 0.4,     # File format importance
    'bitrate': 0.3,    # Bitrate importance  
    'size': 0.2,       # File size importance
    'metadata': 0.1    # Metadata completeness
}

# Format Quality Scores
FORMAT_QUALITY_SCORES = {
    '.flac': 100,
    '.wav': 95,
    '.m4a': 85,
    '.aac': 80,
    '.ogg': 75,
    '.mp3': 70,  # Base score, modified by bitrate
    '.wma': 40,
    '.mp2': 30
}

# Bitrate Quality Thresholds (kbps)
BITRATE_THRESHOLDS = {
    'lossless': 1411,
    'excellent': 320,
    'good': 256,
    'acceptable': 192,
    'poor': 128,
    'unacceptable': 64
}

# Organization Patterns
DEFAULT_NAMING_PATTERN = "{artist} - {title}"
DEFAULT_FOLDER_STRUCTURE = "genre/decade"

# Error Messages
ERROR_MESSAGES = {
    'file_not_found': "Audio file not found or not accessible",
    'corrupted_header': "File header is corrupted or invalid",
    'metadata_error': "Cannot read audio metadata",
    'truncation_detected': "File appears to be truncated",
    'health_too_low': "File health score below acceptable threshold",
    'critical_defect': "File contains critical defects for DJ use"
}