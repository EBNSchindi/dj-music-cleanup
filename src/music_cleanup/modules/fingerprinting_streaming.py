"""
Audio fingerprinting module with streaming architecture integration
Enhanced for memory-efficient processing of very large libraries
"""
import os
import json
import gc
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Generator
import hashlib
from datetime import datetime
import time

# Optional imports for audio fingerprinting
try:
    import acoustid
    ACOUSTID_AVAILABLE = True
except ImportError:
    ACOUSTID_AVAILABLE = False

try:
    import chromaprint
    CHROMAPRINT_AVAILABLE = True
except ImportError:
    CHROMAPRINT_AVAILABLE = False

from mutagen import File as MutagenFile
from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.oggvorbis import OggVorbis
from mutagen.mp4 import MP4
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

from .audio_quality import AudioQualityAnalyzer
from ..core.database import get_database_manager
from ..core.schema import initialize_fingerprints_schema
from ..core.streaming import (
    StreamingConfig, StreamProcessor, RateLimiter, 
    MemoryMonitor, StreamingProgressTracker
)
from ..core.chunk_manager import (
    FileChunkingConfig, ChunkReader, AudioChunkProcessor,
    TemporaryChunkStorage
)


class StreamingAudioProcessor(StreamProcessor):
    """Stream processor for audio fingerprinting"""
    
    def __init__(self, config: StreamingConfig, fingerprinter: 'AudioFingerprinter'):
        super().__init__(config)
        self.fingerprinter = fingerprinter
        
    def process_item(self, file_path: str) -> Dict:
        """Process a single audio file"""
        return self.fingerprinter.fingerprint_file(file_path)


class AudioFingerprinter:
    """Enhanced audio fingerprinter with streaming support"""
    
    def __init__(self, acoustid_key: str = None, 
                 streaming_config: StreamingConfig = None,
                 chunk_config: FileChunkingConfig = None):
        """Initialize fingerprinter with streaming capabilities"""
        self.acoustid_key = acoustid_key
        self.logger = logging.getLogger(__name__)
        self.quality_analyzer = AudioQualityAnalyzer()
        self.db_manager = get_database_manager()
        
        # Streaming configuration
        self.streaming_config = streaming_config or StreamingConfig()
        self.chunk_config = chunk_config or FileChunkingConfig()
        
        # Initialize streaming components
        self.chunk_reader = ChunkReader(self.chunk_config)
        self.audio_processor = AudioChunkProcessor(self.chunk_config)
        self.memory_monitor = MemoryMonitor(
            self.streaming_config.max_memory_usage_mb,
            self.streaming_config.memory_check_interval
        ) if self.streaming_config.enable_memory_monitoring else None
        
        # Rate limiter for external APIs
        self.rate_limiter = RateLimiter(self.streaming_config.api_rate_limit)
        
        # Cache for recently processed files
        self.processing_cache = {}
        self.cache_max_size = 1000
        
        # Performance metrics
        self.metrics = {
            'files_processed': 0,
            'cache_hits': 0,
            'memory_checks': 0,
            'chunk_processing_time': 0,
            'fingerprint_time': 0
        }
        
        # Initialize database if not already done
        if not self.db_manager.table_exists('fingerprints', 'fingerprints'):
            self.db_manager.initialize_database('fingerprints', initialize_fingerprints_schema)
            self._migrate_existing_data()
    
    def _migrate_existing_data(self):
        """Migrate data from old database if it exists"""
        old_db_path = 'fingerprints.db'
        if os.path.exists(old_db_path):
            self.logger.info("Migrating data from old fingerprints database")
            import sqlite3
            old_conn = sqlite3.connect(old_db_path)
            old_conn.row_factory = sqlite3.Row
            
            try:
                # Migrate fingerprints
                cursor = old_conn.execute("SELECT * FROM fingerprints")
                rows = cursor.fetchall()
                
                if rows:
                    with self.db_manager.transaction('fingerprints') as conn:
                        for row in rows:
                            # Map old schema to new schema
                            conn.execute("""
                                INSERT OR IGNORE INTO fingerprints (
                                    file_path, fingerprint, file_hash, file_size, 
                                    modified_time, duration, sample_rate, channels, 
                                    codec, bitrate, quality_score, quality_issues
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                row['file_path'],
                                row['fingerprint'],
                                row['file_hash'],
                                row['file_size'],
                                datetime.fromisoformat(row['created_at']).timestamp(),
                                row['duration'],
                                row['sample_rate'],
                                row['channels'],
                                row['format'],
                                row['bitrate'],
                                row['quality_score'],
                                row['quality_issues']
                            ))
                    
                    self.logger.info(f"Migrated {len(rows)} fingerprints")
                
                # Migrate duplicates
                cursor = old_conn.execute("SELECT * FROM duplicates")
                dup_rows = cursor.fetchall()
                
                if dup_rows:
                    with self.db_manager.transaction('fingerprints') as conn:
                        for row in dup_rows:
                            conn.execute("""
                                INSERT OR IGNORE INTO duplicates (
                                    group_id, file_path, is_primary, similarity_score
                                ) VALUES (?, ?, ?, ?)
                            """, (
                                row['group_id'],
                                row['file_path'],
                                row.get('is_best', 0),
                                1.0  # Default similarity
                            ))
                    
                    self.logger.info(f"Migrated {len(dup_rows)} duplicate entries")
                    
            except Exception as e:
                self.logger.error(f"Error during migration: {e}")
            finally:
                old_conn.close()
                # Rename old database
                os.rename(old_db_path, old_db_path + '.migrated')
                self.logger.info("Old database renamed to fingerprints.db.migrated")
    
    def get_file_hash_chunked(self, file_path: str) -> Optional[str]:
        """Calculate file hash using chunked reading for memory efficiency"""
        try:
            hash_md5 = hashlib.md5()
            
            # Use chunked reading for large files
            with self.chunk_reader.open_chunked_file(file_path) as reader:
                # Read header chunk
                header_chunk = reader.read_header_chunk()
                if header_chunk:
                    hash_md5.update(header_chunk.hash.encode())
                
                # Read a few more chunks for better hash diversity
                chunk_count = 0
                for chunk_info in reader.read_chunks(self.chunk_config.default_chunk_size):
                    hash_md5.update(chunk_info.hash.encode())
                    chunk_count += 1
                    
                    # Only use first few chunks for speed
                    if chunk_count >= 3:
                        break
                
                # Add file size to hash
                hash_md5.update(str(reader.file_size).encode())
            
            return hash_md5.hexdigest()
            
        except Exception as e:
            self.logger.error(f"Error hashing {file_path}: {e}")
            return None
    
    def get_audio_metadata_streaming(self, file_path: str) -> Dict:
        """Extract audio metadata with streaming optimization"""
        try:
            # Check cache first
            cache_key = f"metadata:{file_path}"
            if cache_key in self.processing_cache:
                self.metrics['cache_hits'] += 1
                return self.processing_cache[cache_key]
            
            # Memory check
            if self.memory_monitor and not self.memory_monitor.check_memory():
                self.metrics['memory_checks'] += 1
                gc.collect()
            
            # Use chunked header reading for large files
            file_size = os.path.getsize(file_path)
            if file_size > self.chunk_config.large_file_threshold:
                metadata = self._extract_metadata_chunked(file_path)
            else:
                metadata = self._extract_metadata_traditional(file_path)
            
            # Cache result
            self._cache_result(cache_key, metadata)
            
            return metadata
            
        except Exception as e:
            self.logger.error(f"Error reading metadata from {file_path}: {e}")
            return {}
    
    def _extract_metadata_chunked(self, file_path: str) -> Dict:
        """Extract metadata using chunked reading for large files"""
        metadata = {}
        
        # Get header chunk first
        header_chunk = self.chunk_reader.read_header_chunk(file_path)
        if header_chunk and header_chunk.metadata:
            metadata.update(header_chunk.metadata)
        
        # Then use traditional mutagen for detailed metadata
        # (only read what's needed for large files)
        try:
            audio_file = MutagenFile(file_path)
            if audio_file is None:
                return metadata
                
            # Extract key information
            info = audio_file.info
            metadata.update({
                'duration': getattr(info, 'length', 0),
                'bitrate': getattr(info, 'bitrate', 0),
                'sample_rate': getattr(info, 'sample_rate', 0),
                'channels': getattr(info, 'channels', 0),
            })
            
            # Get bit depth for lossless formats
            if hasattr(info, 'bits_per_sample'):
                metadata['bit_depth'] = info.bits_per_sample
            
            # Extract essential tags only (avoid reading large embedded images)
            if audio_file.tags:
                metadata.update({
                    'title': str(audio_file.tags.get('TIT2', audio_file.tags.get('TITLE', ['']))[0]),
                    'artist': str(audio_file.tags.get('TPE1', audio_file.tags.get('ARTIST', ['']))[0]),
                    'album': str(audio_file.tags.get('TALB', audio_file.tags.get('ALBUM', ['']))[0]),
                    'date': str(audio_file.tags.get('TDRC', audio_file.tags.get('DATE', ['']))[0])
                })
            
        except Exception as e:
            self.logger.debug(f"Error in traditional metadata extraction: {e}")
        
        return metadata
    
    def _extract_metadata_traditional(self, file_path: str) -> Dict:
        """Extract metadata using traditional method for small files"""
        try:
            audio_file = MutagenFile(file_path)
            if audio_file is None:
                return {}
                
            metadata = {
                'format': audio_file.mime[0].split('/')[1] if audio_file.mime else 'unknown',
                'duration': getattr(audio_file.info, 'length', 0),
                'bitrate': getattr(audio_file.info, 'bitrate', 0),
                'sample_rate': getattr(audio_file.info, 'sample_rate', 0),
                'channels': getattr(audio_file.info, 'channels', 0),
            }
            
            # Get bit depth for lossless formats
            if hasattr(audio_file.info, 'bits_per_sample'):
                metadata['bit_depth'] = audio_file.info.bits_per_sample
                
            # Extract tags
            if audio_file.tags:
                metadata['title'] = str(audio_file.tags.get('title', [''])[0])
                metadata['artist'] = str(audio_file.tags.get('artist', [''])[0])
                metadata['album'] = str(audio_file.tags.get('album', [''])[0])
                metadata['date'] = str(audio_file.tags.get('date', [''])[0])
                
            return metadata
        except Exception as e:
            self.logger.error(f"Error reading metadata from {file_path}: {e}")
            return {}
    
    def generate_fingerprint_streaming(self, file_path: str) -> Optional[str]:
        """Generate fingerprint with streaming optimization"""
        start_time = time.time()
        
        try:
            # Rate limiting for external API calls
            self.rate_limiter.wait()
            
            # Memory check
            if self.memory_monitor and not self.memory_monitor.check_memory():
                gc.collect()
            
            # Use fpcalc command-line tool
            result = subprocess.run(
                ['fpcalc', '-json', file_path],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                fingerprint = data.get('fingerprint')
                
                # Update metrics
                self.metrics['fingerprint_time'] += time.time() - start_time
                
                return fingerprint
            else:
                self.logger.error(f"fpcalc error for {file_path}: {result.stderr}")
                return None
                
        except FileNotFoundError:
            self.logger.error("fpcalc not found. Please install chromaprint.")
            return None
        except subprocess.TimeoutExpired:
            self.logger.error(f"Fingerprinting timeout for {file_path}")
            return None
        except Exception as e:
            self.logger.error(f"Error fingerprinting {file_path}: {e}")
            return None
    
    def fingerprint_file_streaming(self, file_path: str, force: bool = False) -> Optional[Dict]:
        """Stream-aware fingerprinting of a single audio file"""
        file_path = os.path.abspath(file_path)
        
        # Check cache first
        if not force:
            cached = self.get_cached_fingerprint(file_path)
            if cached:
                return cached
        
        # Memory check before processing
        if self.memory_monitor and not self.memory_monitor.check_memory():
            self.logger.warning(f"Memory limit approached, skipping {file_path}")
            return None
        
        try:
            # Get file info
            file_stat = os.stat(file_path)
            
            # Use chunked hashing for large files
            file_hash = self.get_file_hash_chunked(file_path)
            if not file_hash:
                return None
            
            # Generate fingerprint
            fingerprint = self.generate_fingerprint_streaming(file_path)
            if not fingerprint:
                return None
            
            # Get metadata with streaming optimization
            metadata = self.get_audio_metadata_streaming(file_path)
            
            # Analyze quality with chunked processing for large files
            quality_info = self._analyze_quality_streaming(file_path)
            
            # Store in database
            with self.db_manager.transaction('fingerprints') as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO fingerprints (
                        file_path, fingerprint, file_hash, file_size, modified_time,
                        duration, sample_rate, bit_depth, channels, codec, bitrate,
                        quality_score, quality_issues, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    file_path,
                    fingerprint,
                    file_hash,
                    file_stat.st_size,
                    file_stat.st_mtime,
                    metadata.get('duration', 0),
                    metadata.get('sample_rate', 0),
                    metadata.get('bit_depth', 0),
                    metadata.get('channels', 0),
                    metadata.get('format', 'unknown'),
                    metadata.get('bitrate', 0),
                    quality_info.get('overall_score', 0),
                    json.dumps(quality_info.get('issues', [])),
                    datetime.now().isoformat(),
                    datetime.now().isoformat()
                ))
            
            # Update metrics
            self.metrics['files_processed'] += 1
            
            result = {
                'file_path': file_path,
                'fingerprint': fingerprint,
                'file_hash': file_hash,
                'metadata': metadata,
                'quality': quality_info
            }
            
            # Cache result
            self._cache_result(f"fingerprint:{file_path}", result)
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error fingerprinting {file_path}: {e}")
            return None
    
    def _analyze_quality_streaming(self, file_path: str) -> Dict:
        """Analyze audio quality with streaming optimization"""
        try:
            # For large files, use chunked analysis
            file_size = os.path.getsize(file_path)
            
            if file_size > self.chunk_config.large_file_threshold:
                return self._analyze_quality_chunked(file_path)
            else:
                return self.quality_analyzer.analyze_file(file_path)
                
        except Exception as e:
            self.logger.error(f"Error analyzing quality for {file_path}: {e}")
            return {'overall_score': 0, 'issues': []}
    
    def _analyze_quality_chunked(self, file_path: str) -> Dict:
        """Analyze quality using chunked processing"""
        start_time = time.time()
        
        try:
            # Use audio chunk processor for efficient analysis
            quality_issues = []
            total_entropy = 0
            chunk_count = 0
            
            for chunk_result in self.audio_processor.process_audio_file_chunked(file_path):
                if chunk_result['type'] == 'audio_data':
                    audio_info = chunk_result['audio_info']
                    entropy = chunk_result['chunk_info'].metadata.get('entropy', 0)
                    
                    total_entropy += entropy
                    chunk_count += 1
                    
                    # Check for quality issues based on entropy
                    if entropy < 2.0:
                        quality_issues.append("Low audio entropy detected")
                    
                    # Memory check during chunked processing
                    if self.memory_monitor and not self.memory_monitor.check_memory():
                        self.logger.debug("Memory limit during quality analysis")
                        break
            
            # Calculate overall score based on entropy
            if chunk_count > 0:
                avg_entropy = total_entropy / chunk_count
                overall_score = min(1000, int(avg_entropy * 100))
            else:
                overall_score = 0
                quality_issues.append("No audio data found")
            
            # Update metrics
            self.metrics['chunk_processing_time'] += time.time() - start_time
            
            return {
                'overall_score': overall_score,
                'issues': quality_issues,
                'chunks_analyzed': chunk_count,
                'average_entropy': avg_entropy if chunk_count > 0 else 0
            }
            
        except Exception as e:
            self.logger.error(f"Error in chunked quality analysis: {e}")
            return {'overall_score': 0, 'issues': ['Analysis failed']}
    
    def get_cached_fingerprint(self, file_path: str) -> Optional[Dict]:
        """Get fingerprint from cache or database if file hasn't changed"""
        file_path = os.path.abspath(file_path)
        
        # Check in-memory cache first
        cache_key = f"fingerprint:{file_path}"
        if cache_key in self.processing_cache:
            self.metrics['cache_hits'] += 1
            return self.processing_cache[cache_key]
        
        try:
            file_stat = os.stat(file_path)
            
            results = self.db_manager.execute_query(
                'fingerprints',
                """SELECT * FROM fingerprints 
                   WHERE file_path = ? AND modified_time >= ?""",
                (file_path, file_stat.st_mtime - 1)
            )
            
            if results:
                row = results[0]
                result = {
                    'file_path': row['file_path'],
                    'fingerprint': row['fingerprint'],
                    'file_hash': row['file_hash'],
                    'metadata': {
                        'duration': row['duration'],
                        'format': row['codec'],
                        'bitrate': row['bitrate'],
                        'sample_rate': row['sample_rate'],
                        'channels': row['channels']
                    },
                    'quality': {
                        'overall_score': row['quality_score'],
                        'issues': json.loads(row['quality_issues'] or '[]')
                    }
                }
                
                # Cache for future use
                self._cache_result(cache_key, result)
                
                return result
        except Exception as e:
            self.logger.error(f"Error getting cached fingerprint: {e}")
            
        return None
    
    def _cache_result(self, key: str, result: any):
        """Cache result with size management"""
        if len(self.processing_cache) >= self.cache_max_size:
            # Remove oldest entries (simple LRU)
            oldest_keys = list(self.processing_cache.keys())[:100]
            for old_key in oldest_keys:
                del self.processing_cache[old_key]
        
        self.processing_cache[key] = result
    
    def stream_fingerprint_files(self, file_paths: Generator[str, None, None]) -> Generator[Dict, None, None]:
        """Stream process multiple files with memory management"""
        with StreamingProgressTracker("Fingerprinting", enable_db_tracking=True) as progress:
            processed_count = 0
            
            for file_path in file_paths:
                try:
                    # Memory check
                    if self.memory_monitor and not self.memory_monitor.check_memory():
                        self.logger.warning("Memory limit during streaming fingerprinting")
                        gc.collect()
                    
                    result = self.fingerprint_file_streaming(file_path)
                    if result:
                        yield result
                        progress.update(1, has_error=False)
                    else:
                        progress.update(1, has_error=True)
                    
                    processed_count += 1
                    
                    # Periodic cache cleanup
                    if processed_count % 1000 == 0:
                        self._cleanup_cache()
                        self.logger.debug(f"Processed {processed_count} files")
                    
                except Exception as e:
                    self.logger.error(f"Error in stream processing {file_path}: {e}")
                    progress.update(1, has_error=True)
    
    def _cleanup_cache(self):
        """Clean up caches to prevent memory growth"""
        # Clear half of the cache
        cache_size = len(self.processing_cache)
        if cache_size > self.cache_max_size // 2:
            keys_to_remove = list(self.processing_cache.keys())[:cache_size // 2]
            for key in keys_to_remove:
                del self.processing_cache[key]
        
        # Force garbage collection
        gc.collect()
    
    def find_duplicates_streaming(self, threshold: float = 0.95) -> Generator[List[Dict], None, None]:
        """Stream-based duplicate detection for very large datasets"""
        from ..core.streaming import DatabaseStreamer
        
        self.logger.info("Starting streaming duplicate detection...")
        
        db_streamer = DatabaseStreamer(self.streaming_config)
        fingerprint_groups = {}
        
        # Stream fingerprints in batches to manage memory
        for batch in db_streamer.stream_query_results(
            'fingerprints',
            "SELECT file_path, fingerprint, quality_score FROM fingerprints ORDER BY fingerprint",
            batch_size=self.streaming_config.database_batch_size
        ):
            # Process batch
            for row in batch:
                fp = row['fingerprint']
                if fp not in fingerprint_groups:
                    fingerprint_groups[fp] = []
                fingerprint_groups[fp].append({
                    'file_path': row['file_path'],
                    'quality_score': row['quality_score']
                })
            
            # Yield completed groups and clear memory
            for fingerprint, files in list(fingerprint_groups.items()):
                if len(files) > 1:
                    # Sort by quality score
                    files.sort(key=lambda x: x['quality_score'], reverse=True)
                    yield files
                    
                    # Remove from memory
                    del fingerprint_groups[fingerprint]
            
            # Memory check
            if self.memory_monitor and not self.memory_monitor.check_memory():
                self.logger.warning("Memory limit during duplicate detection")
                fingerprint_groups.clear()
                gc.collect()
    
    def get_performance_metrics(self) -> Dict:
        """Get performance metrics for monitoring"""
        return {
            **self.metrics,
            'cache_size': len(self.processing_cache),
            'cache_hit_rate': self.metrics['cache_hits'] / max(self.metrics['files_processed'], 1),
            'avg_chunk_time': self.metrics['chunk_processing_time'] / max(self.metrics['files_processed'], 1),
            'avg_fingerprint_time': self.metrics['fingerprint_time'] / max(self.metrics['files_processed'], 1)
        }
    
    # Legacy methods for compatibility
    def fingerprint_file(self, file_path: str, force: bool = False) -> Optional[Dict]:
        """Legacy method - redirects to streaming version"""
        return self.fingerprint_file_streaming(file_path, force)
    
    def find_duplicates(self, threshold: float = 0.95) -> List[List[Dict]]:
        """Legacy method - collects streaming results"""
        return list(self.find_duplicates_streaming(threshold))
    
    def get_duplicate_stats(self) -> Dict:
        """Get statistics about duplicates"""
        stats = {}
        
        # Count total duplicates
        result = self.db_manager.execute_query(
            'fingerprints',
            """SELECT COUNT(DISTINCT group_id) as groups, 
                      COUNT(*) as total_files 
               FROM duplicates"""
        )
        
        if result:
            stats['duplicate_groups'] = result[0]['groups'] or 0
            stats['total_duplicate_files'] = result[0]['total_files'] or 0
        
        # Calculate potential space savings
        result = self.db_manager.execute_query(
            'fingerprints',
            """SELECT SUM(f.file_size) as total_size
               FROM duplicates d
               JOIN fingerprints f ON d.file_path = f.file_path
               WHERE d.is_primary = 0"""
        )
        
        if result and result[0]['total_size']:
            stats['potential_space_savings'] = result[0]['total_size']
        else:
            stats['potential_space_savings'] = 0
        
        return stats