"""
Intelligent file chunking and memory management for audio processing.
Handles chunked reading of audio files for fingerprinting and analysis.
"""

import os
import mmap
import hashlib
import logging
from typing import Generator, BinaryIO, Tuple, Dict, Any, Optional, List
from pathlib import Path
from dataclasses import dataclass
from contextlib import contextmanager
import struct
import tempfile
import shutil

logger = logging.getLogger(__name__)


@dataclass
class ChunkInfo:
    """Information about a file chunk"""
    chunk_id: int
    offset: int
    size: int
    hash: str
    is_header: bool = False
    is_audio_data: bool = False
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class FileChunkingConfig:
    """Configuration for file chunking operations"""
    # Basic chunk sizes
    default_chunk_size: int = 65536  # 64KB
    large_file_chunk_size: int = 1048576  # 1MB for files >100MB
    header_chunk_size: int = 8192  # 8KB for file headers
    
    # Audio-specific chunking
    audio_frame_size: int = 4096  # Audio frame size for analysis
    fingerprint_chunk_size: int = 32768  # 32KB for fingerprinting
    
    # Memory management
    max_chunks_in_memory: int = 10
    enable_memory_mapping: bool = True
    temp_dir: Optional[str] = None
    
    # File size thresholds
    large_file_threshold: int = 104857600  # 100MB
    small_file_threshold: int = 1048576   # 1MB
    
    # Performance tuning
    read_ahead_chunks: int = 2
    enable_chunk_caching: bool = True
    cache_header_chunks: bool = True


class ChunkReader:
    """Read files in chunks with intelligent sizing"""
    
    def __init__(self, config: FileChunkingConfig):
        self.config = config
        self.chunk_cache = {}  # Simple LRU-like cache
        self.cache_hits = 0
        self.cache_misses = 0
    
    def get_optimal_chunk_size(self, file_path: str, purpose: str = 'default') -> int:
        """Determine optimal chunk size based on file size and purpose"""
        try:
            file_size = os.path.getsize(file_path)
        except OSError:
            return self.config.default_chunk_size
        
        # Purpose-specific sizing
        if purpose == 'header':
            return self.config.header_chunk_size
        elif purpose == 'fingerprint':
            return self.config.fingerprint_chunk_size
        elif purpose == 'audio_analysis':
            return self.config.audio_frame_size
        
        # Size-based optimization
        if file_size > self.config.large_file_threshold:
            return self.config.large_file_chunk_size
        elif file_size < self.config.small_file_threshold:
            return min(self.config.default_chunk_size, file_size // 4)
        else:
            return self.config.default_chunk_size
    
    @contextmanager
    def open_chunked_file(self, file_path: str, mode: str = 'rb'):
        """Context manager for chunked file access"""
        file_handle = None
        mmap_obj = None
        
        try:
            file_handle = open(file_path, mode)
            
            # Use memory mapping for large files if enabled
            if (self.config.enable_memory_mapping and 
                mode == 'rb' and 
                os.path.getsize(file_path) > self.config.large_file_threshold):
                try:
                    mmap_obj = mmap.mmap(file_handle.fileno(), 0, access=mmap.ACCESS_READ)
                    yield ChunkedFileReader(mmap_obj, self.config, file_path)
                except OSError:
                    # Fall back to regular file if mmap fails
                    yield ChunkedFileReader(file_handle, self.config, file_path)
            else:
                yield ChunkedFileReader(file_handle, self.config, file_path)
                
        finally:
            if mmap_obj:
                mmap_obj.close()
            if file_handle:
                file_handle.close()
    
    def read_file_chunks(self, file_path: str, 
                        purpose: str = 'default') -> Generator[ChunkInfo, None, None]:
        """Read file in chunks and return chunk information"""
        chunk_size = self.get_optimal_chunk_size(file_path, purpose)
        
        with self.open_chunked_file(file_path) as reader:
            for chunk_info in reader.read_chunks(chunk_size):
                yield chunk_info
    
    def read_header_chunk(self, file_path: str) -> Optional[ChunkInfo]:
        """Read just the header chunk of a file"""
        cache_key = f"header:{file_path}"
        
        # Check cache first
        if self.config.cache_header_chunks and cache_key in self.chunk_cache:
            self.cache_hits += 1
            return self.chunk_cache[cache_key]
        
        self.cache_misses += 1
        
        try:
            with self.open_chunked_file(file_path) as reader:
                chunk = reader.read_header_chunk()
                
                # Cache header chunk
                if self.config.cache_header_chunks and chunk:
                    self._cache_chunk(cache_key, chunk)
                
                return chunk
        except Exception as e:
            logger.error(f"Error reading header chunk from {file_path}: {e}")
            return None
    
    def _cache_chunk(self, key: str, chunk: ChunkInfo):
        """Cache a chunk with simple LRU eviction"""
        # Simple cache size management
        if len(self.chunk_cache) >= self.config.max_chunks_in_memory:
            # Remove oldest entry (simple approach)
            oldest_key = next(iter(self.chunk_cache))
            del self.chunk_cache[oldest_key]
        
        self.chunk_cache[key] = chunk
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache performance statistics"""
        total_requests = self.cache_hits + self.cache_misses
        hit_rate = self.cache_hits / total_requests if total_requests > 0 else 0
        
        return {
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'hit_rate': hit_rate,
            'cache_size': len(self.chunk_cache)
        }


class ChunkedFileReader:
    """Read a file in chunks with metadata tracking"""
    
    def __init__(self, file_handle, config: FileChunkingConfig, file_path: str):
        self.file_handle = file_handle
        self.config = config
        self.file_path = file_path
        self.current_offset = 0
        self.file_size = self._get_file_size()
        self.chunk_counter = 0
    
    def _get_file_size(self) -> int:
        """Get total file size"""
        try:
            if hasattr(self.file_handle, 'fileno'):
                return os.fstat(self.file_handle.fileno()).st_size
            else:
                # For mmap objects
                return len(self.file_handle)
        except (OSError, AttributeError):
            return 0
    
    def read_chunks(self, chunk_size: int) -> Generator[ChunkInfo, None, None]:
        """Read file in chunks of specified size"""
        self.current_offset = 0
        self.chunk_counter = 0
        
        while self.current_offset < self.file_size:
            # Determine chunk size (handle partial chunk at end)
            remaining_bytes = self.file_size - self.current_offset
            actual_chunk_size = min(chunk_size, remaining_bytes)
            
            # Read chunk data
            chunk_data = self._read_chunk_data(actual_chunk_size)
            if not chunk_data:
                break
            
            # Create chunk info
            chunk_info = ChunkInfo(
                chunk_id=self.chunk_counter,
                offset=self.current_offset,
                size=len(chunk_data),
                hash=self._hash_chunk(chunk_data),
                is_header=(self.chunk_counter == 0),
                is_audio_data=self._is_audio_data_chunk(chunk_data, self.current_offset),
                metadata=self._extract_chunk_metadata(chunk_data, self.current_offset)
            )
            
            yield chunk_info
            
            self.current_offset += len(chunk_data)
            self.chunk_counter += 1
    
    def read_header_chunk(self) -> Optional[ChunkInfo]:
        """Read just the header chunk"""
        self.current_offset = 0
        header_size = min(self.config.header_chunk_size, self.file_size)
        
        chunk_data = self._read_chunk_data(header_size)
        if not chunk_data:
            return None
        
        return ChunkInfo(
            chunk_id=0,
            offset=0,
            size=len(chunk_data),
            hash=self._hash_chunk(chunk_data),
            is_header=True,
            is_audio_data=False,
            metadata=self._extract_header_metadata(chunk_data)
        )
    
    def read_chunk_at_offset(self, offset: int, size: int) -> Optional[bytes]:
        """Read specific chunk at given offset"""
        try:
            if hasattr(self.file_handle, 'seek'):
                self.file_handle.seek(offset)
                return self.file_handle.read(size)
            else:
                # For mmap objects
                return self.file_handle[offset:offset + size]
        except (OSError, ValueError) as e:
            logger.error(f"Error reading chunk at offset {offset}: {e}")
            return None
    
    def _read_chunk_data(self, size: int) -> bytes:
        """Read chunk data from current position"""
        try:
            if hasattr(self.file_handle, 'read'):
                return self.file_handle.read(size)
            else:
                # For mmap objects
                data = self.file_handle[self.current_offset:self.current_offset + size]
                return data
        except (OSError, ValueError) as e:
            logger.error(f"Error reading chunk data: {e}")
            return b''
    
    def _hash_chunk(self, data: bytes) -> str:
        """Generate hash for chunk data"""
        return hashlib.md5(data).hexdigest()
    
    def _is_audio_data_chunk(self, data: bytes, offset: int) -> bool:
        """Determine if chunk contains audio data"""
        # Basic heuristic: skip common header areas
        if offset < 8192:  # First 8KB likely contains metadata
            return False
        
        # Look for audio data patterns
        if len(data) < 100:
            return False
        
        # Check for common audio patterns
        # This is a simplified check - could be enhanced with format-specific logic
        non_zero_bytes = sum(1 for b in data[:100] if b != 0)
        return non_zero_bytes > 50  # Audio data usually has more variation
    
    def _extract_chunk_metadata(self, data: bytes, offset: int) -> Dict[str, Any]:
        """Extract metadata from chunk"""
        metadata = {
            'offset': offset,
            'entropy': self._calculate_entropy(data[:min(1024, len(data))]),
            'has_patterns': self._detect_patterns(data[:min(512, len(data))])
        }
        
        # Add format-specific metadata if it's a header chunk
        if offset == 0:
            metadata.update(self._extract_header_metadata(data))
        
        return metadata
    
    def _extract_header_metadata(self, data: bytes) -> Dict[str, Any]:
        """Extract metadata from file header"""
        metadata = {}
        
        if len(data) < 12:
            return metadata
        
        # Detect file format from header
        header_start = data[:12]
        
        if header_start.startswith(b'ID3'):
            metadata['format'] = 'mp3'
            metadata['has_id3'] = True
            if len(data) >= 10:
                # Parse ID3 version
                metadata['id3_version'] = f"{data[3]}.{data[4]}"
        
        elif header_start.startswith(b'fLaC'):
            metadata['format'] = 'flac'
            metadata['has_flac_header'] = True
        
        elif header_start[4:8] == b'ftyp':
            metadata['format'] = 'm4a'
            metadata['has_mp4_header'] = True
        
        elif header_start.startswith(b'OggS'):
            metadata['format'] = 'ogg'
            metadata['has_ogg_header'] = True
        
        elif header_start.startswith(b'RIFF') and header_start[8:12] == b'WAVE':
            metadata['format'] = 'wav'
            metadata['has_wave_header'] = True
        
        else:
            metadata['format'] = 'unknown'
        
        return metadata
    
    def _calculate_entropy(self, data: bytes) -> float:
        """Calculate entropy of data (measure of randomness)"""
        if not data:
            return 0.0
        
        # Count byte frequencies
        byte_counts = [0] * 256
        for byte in data:
            byte_counts[byte] += 1
        
        # Calculate entropy
        import math
        entropy = 0.0
        data_len = len(data)
        
        for count in byte_counts:
            if count > 0:
                probability = count / data_len
                entropy -= probability * math.log2(probability)
        
        return entropy
    
    def _detect_patterns(self, data: bytes) -> Dict[str, bool]:
        """Detect patterns in chunk data"""
        if len(data) < 16:
            return {}
        
        patterns = {
            'mostly_zeros': sum(1 for b in data if b == 0) > len(data) * 0.8,
            'mostly_ones': sum(1 for b in data if b == 0xFF) > len(data) * 0.8,
            'has_repeating_pattern': self._has_repeating_pattern(data),
            'has_ascii_text': self._has_ascii_text(data)
        }
        
        return patterns
    
    def _has_repeating_pattern(self, data: bytes, max_pattern_len: int = 16) -> bool:
        """Check for repeating byte patterns"""
        if len(data) < max_pattern_len * 2:
            return False
        
        for pattern_len in range(2, min(max_pattern_len + 1, len(data) // 2)):
            pattern = data[:pattern_len]
            repeats = 0
            
            for i in range(pattern_len, len(data) - pattern_len + 1, pattern_len):
                if data[i:i + pattern_len] == pattern:
                    repeats += 1
                else:
                    break
            
            if repeats >= 3:  # Pattern repeats at least 3 times
                return True
        
        return False
    
    def _has_ascii_text(self, data: bytes) -> bool:
        """Check if data contains readable ASCII text"""
        if len(data) < 20:
            return False
        
        ascii_chars = sum(1 for b in data[:100] if 32 <= b <= 126)
        return ascii_chars > len(data[:100]) * 0.7


class TemporaryChunkStorage:
    """Manage temporary storage for large file chunks"""
    
    def __init__(self, config: FileChunkingConfig):
        self.config = config
        self.temp_dir = config.temp_dir or tempfile.gettempdir()
        self.temp_files = []
        
    def store_chunk(self, chunk_data: bytes, chunk_id: str) -> str:
        """Store chunk data in temporary file"""
        temp_file = tempfile.NamedTemporaryFile(
            dir=self.temp_dir,
            prefix=f"chunk_{chunk_id}_",
            suffix=".tmp",
            delete=False
        )
        
        try:
            temp_file.write(chunk_data)
            temp_file.flush()
            temp_path = temp_file.name
            self.temp_files.append(temp_path)
            return temp_path
        finally:
            temp_file.close()
    
    def load_chunk(self, temp_path: str) -> bytes:
        """Load chunk data from temporary file"""
        try:
            with open(temp_path, 'rb') as f:
                return f.read()
        except OSError as e:
            logger.error(f"Error loading chunk from {temp_path}: {e}")
            return b''
    
    def cleanup(self):
        """Clean up all temporary files"""
        for temp_path in self.temp_files:
            try:
                os.unlink(temp_path)
            except OSError:
                pass  # File might already be deleted
        
        self.temp_files.clear()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()


class AudioChunkProcessor:
    """Specialized processor for audio file chunks"""
    
    def __init__(self, config: FileChunkingConfig):
        self.config = config
        self.chunk_reader = ChunkReader(config)
    
    def process_audio_file_chunked(self, file_path: str) -> Generator[Dict[str, Any], None, None]:
        """Process audio file in chunks for analysis"""
        try:
            file_format = self._detect_audio_format(file_path)
            
            with self.chunk_reader.open_chunked_file(file_path) as reader:
                # First, read header chunk
                header_chunk = reader.read_header_chunk()
                if header_chunk:
                    yield {
                        'type': 'header',
                        'chunk_info': header_chunk,
                        'format_info': self._parse_audio_header(header_chunk, file_format)
                    }
                
                # Then process audio data chunks
                audio_chunk_size = self.config.audio_frame_size
                for chunk_info in reader.read_chunks(audio_chunk_size):
                    if chunk_info.is_audio_data:
                        yield {
                            'type': 'audio_data',
                            'chunk_info': chunk_info,
                            'audio_info': self._analyze_audio_chunk(chunk_info, file_format)
                        }
                
        except Exception as e:
            logger.error(f"Error processing audio file {file_path}: {e}")
            yield {
                'type': 'error',
                'error': str(e),
                'file_path': file_path
            }
    
    def _detect_audio_format(self, file_path: str) -> str:
        """Detect audio file format from extension and header"""
        ext = Path(file_path).suffix.lower()
        format_map = {
            '.mp3': 'mp3',
            '.flac': 'flac',
            '.m4a': 'm4a',
            '.ogg': 'ogg',
            '.opus': 'opus',
            '.wav': 'wav'
        }
        return format_map.get(ext, 'unknown')
    
    def _parse_audio_header(self, header_chunk: ChunkInfo, file_format: str) -> Dict[str, Any]:
        """Parse format-specific header information"""
        header_info = {
            'format': file_format,
            'header_size': header_chunk.size
        }
        
        # Add format-specific parsing
        if file_format == 'mp3' and header_chunk.metadata.get('has_id3'):
            header_info['id3_version'] = header_chunk.metadata.get('id3_version')
        
        return header_info
    
    def _analyze_audio_chunk(self, chunk_info: ChunkInfo, file_format: str) -> Dict[str, Any]:
        """Analyze audio data chunk"""
        return {
            'chunk_id': chunk_info.chunk_id,
            'entropy': chunk_info.metadata.get('entropy', 0),
            'has_patterns': chunk_info.metadata.get('has_patterns', {}),
            'estimated_quality': self._estimate_quality_from_entropy(
                chunk_info.metadata.get('entropy', 0)
            )
        }
    
    def _estimate_quality_from_entropy(self, entropy: float) -> str:
        """Estimate audio quality based on entropy"""
        if entropy > 7.5:
            return 'high'
        elif entropy > 6.0:
            return 'medium'
        else:
            return 'low'