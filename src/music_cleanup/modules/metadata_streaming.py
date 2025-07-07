"""
Metadata extraction and enrichment module with streaming architecture integration
Enhanced for memory-efficient processing of very large libraries
"""
import os
import re
import logging
import gc
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Generator
from datetime import datetime

# Optional import for MusicBrainz
try:
    import musicbrainzngs
    MUSICBRAINZ_AVAILABLE = True
except ImportError:
    MUSICBRAINZ_AVAILABLE = False

from mutagen import File as MutagenFile
from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.oggvorbis import OggVorbis
from mutagen.mp4 import MP4
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, TCON, TPE2
import requests

try:
    from unidecode import unidecode
    UNIDECODE_AVAILABLE = True
except ImportError:
    UNIDECODE_AVAILABLE = False
    def unidecode(text):
        return text  # Fallback: just return original text

from ..core.database import get_database_manager
from ..core.schema import initialize_operations_schema
from ..core.streaming import (
    StreamingConfig, StreamProcessor, RateLimiter, 
    MemoryMonitor, StreamingProgressTracker
)
from ..core.chunk_manager import (
    FileChunkingConfig, ChunkReader
)


class StreamingMetadataProcessor(StreamProcessor):
    """Stream processor for metadata enhancement"""
    
    def __init__(self, config: StreamingConfig, metadata_manager: 'MetadataManager'):
        super().__init__(config)
        self.metadata_manager = metadata_manager
        
    def process_item(self, item_data: Dict) -> Dict:
        """Process a single file's metadata"""
        file_path = item_data.get('file_path')
        existing_metadata = item_data.get('metadata', {})
        
        return self.metadata_manager.enhance_metadata_streaming(file_path, existing_metadata)


class MetadataManager:
    """Enhanced metadata manager with streaming support"""
    
    def __init__(self, enable_musicbrainz: bool = True, 
                 mb_app_name: str = "DJ-Music-Cleanup",
                 mb_app_version: str = "2.0", 
                 mb_contact: str = None,
                 streaming_config: StreamingConfig = None,
                 chunk_config: FileChunkingConfig = None):
        """Initialize metadata manager with streaming capabilities"""
        self.logger = logging.getLogger(__name__)
        self.enable_musicbrainz = enable_musicbrainz
        self.db_manager = get_database_manager()
        
        # Streaming configuration
        self.streaming_config = streaming_config or StreamingConfig()
        self.chunk_config = chunk_config or FileChunkingConfig()
        
        # Initialize streaming components
        self.chunk_reader = ChunkReader(self.chunk_config)
        self.memory_monitor = MemoryMonitor(
            self.streaming_config.max_memory_usage_mb,
            self.streaming_config.memory_check_interval
        ) if self.streaming_config.enable_memory_monitoring else None
        
        # Rate limiter for external APIs
        self.rate_limiter = RateLimiter(self.streaming_config.api_rate_limit)
        
        # Cache for metadata lookups
        self.metadata_cache = {}
        self.cache_max_size = 5000  # Larger cache for metadata
        
        # Performance metrics
        self.metrics = {
            'files_processed': 0,
            'cache_hits': 0,
            'musicbrainz_lookups': 0,
            'memory_checks': 0,
            'extraction_time': 0,
            'enhancement_time': 0
        }
        
        # Setup MusicBrainz
        if enable_musicbrainz and mb_contact and MUSICBRAINZ_AVAILABLE:
            musicbrainzngs.set_useragent(mb_app_name, mb_app_version, mb_contact)
            musicbrainzngs.set_rate_limit(True)  # Respect rate limits
        elif enable_musicbrainz and not MUSICBRAINZ_AVAILABLE:
            self.logger.warning("MusicBrainz requested but musicbrainzngs not available")
            self.enable_musicbrainz = False
        
        # Initialize database if not already done
        if not self.db_manager.table_exists('operations', 'metadata_cache'):
            self.db_manager.initialize_database('operations', initialize_operations_schema)
        
        # Common patterns for cleaning filenames
        self.cleanup_patterns = [
            # Remove track numbers
            (r'^(\d{1,3}[\.\-\s])+', ''),
            # Remove CD/Disc indicators
            (r'\[?CD\s*\d+\]?', ''),
            # Remove quality indicators
            (r'\[?\d{3,4}\s*kbps\]?', ''),
            (r'\[?320\]?', ''),
            (r'\[?FLAC\]?', ''),
            # Remove years in brackets
            (r'\[?\d{4}\]?', ''),
            # Remove common tags
            (r'\[?www\.[^\]]+\]?', ''),
            (r'\[?Original Mix\]?', ''),
            (r'\[?Extended Mix\]?', ''),
            (r'\[?Radio Edit\]?', ''),
            # Clean up extra spaces and underscores
            (r'_+', ' '),
            (r'\s+', ' '),
            # Remove file extensions in names
            (r'\.(mp3|flac|wav|m4a|ogg|wma)$', ''),
        ]
        
        # Genre normalization map (DJ-focused)
        self.genre_map = {
            'dnb': 'Drum & Bass',
            'd&b': 'Drum & Bass',
            'drum n bass': 'Drum & Bass',
            'hip hop': 'Hip-Hop',
            'hiphop': 'Hip-Hop',
            'r&b': 'R&B',
            'rnb': 'R&B',
            'tech house': 'Tech House',
            'deep house': 'Deep House',
            'prog house': 'Progressive House',
            'progressive': 'Progressive House',
            'electrohouse': 'Electro House',
            'future house': 'Future House',
            'bigroom': 'Big Room House',
            'edm': 'Electronic',
            'idm': 'Electronic',
            'electronica': 'Electronic',
            'dubstep': 'Dubstep',
            'future garage': 'Future Garage',
            'trap': 'Trap',
            'future bass': 'Future Bass',
            'hardstyle': 'Hardstyle',
            'hardcore': 'Hardcore',
            'trance': 'Trance',
            'psy trance': 'Psytrance',
            'psytrance': 'Psytrance',
            'goa': 'Goa Trance',
            'techno': 'Techno',
            'minimal': 'Minimal Techno',
            'acid': 'Acid Techno',
            'breakbeat': 'Breakbeat',
            'breaks': 'Breakbeat',
            'garage': 'UK Garage',
            'grime': 'Grime',
            'reggae': 'Reggae',
            'dub': 'Dub',
            'dancehall': 'Dancehall',
            'ambient': 'Ambient',
            'chillout': 'Chillout',
            'downtempo': 'Downtempo',
        }
    
    def extract_metadata_streaming(self, file_path: str) -> Dict[str, any]:
        """Extract metadata with streaming optimization"""
        start_time = time.time()
        
        try:
            # Check cache first
            cache_key = f"extract:{file_path}"
            if cache_key in self.metadata_cache:
                self.metrics['cache_hits'] += 1
                return self.metadata_cache[cache_key]
            
            # Memory check
            if self.memory_monitor and not self.memory_monitor.check_memory():
                self.metrics['memory_checks'] += 1
                gc.collect()
            
            # Use chunked reading for large files
            file_size = os.path.getsize(file_path)
            if file_size > self.chunk_config.large_file_threshold:
                metadata = self._extract_metadata_chunked(file_path)
            else:
                metadata = self._extract_metadata_traditional(file_path)
            
            # Cache result
            self._cache_result(cache_key, metadata)
            
            # Update metrics
            self.metrics['extraction_time'] += time.time() - start_time
            self.metrics['files_processed'] += 1
            
            return metadata
            
        except Exception as e:
            self.logger.error(f"Error extracting metadata from {file_path}: {e}")
            return self._extract_from_filename(file_path)
    
    def _extract_metadata_chunked(self, file_path: str) -> Dict[str, any]:
        """Extract metadata using chunked reading for large files"""
        try:
            # First try to get header information from chunk reader
            header_chunk = self.chunk_reader.read_header_chunk(file_path)
            metadata = {}
            
            # If header chunk has metadata, use it
            if header_chunk and header_chunk.metadata:
                metadata.update(header_chunk.metadata)
            
            # For detailed metadata, still use mutagen but with minimal reads
            try:
                audio = MutagenFile(file_path)
                if audio is None:
                    return self._extract_from_filename(file_path)
                
                # Extract essential information only
                essential_metadata = {
                    'file_path': file_path,
                    'filename': os.path.basename(file_path),
                    'format': audio.mime[0].split('/')[-1] if audio.mime else self._get_format_from_extension(file_path),
                    'duration': getattr(audio.info, 'length', 0),
                    'bitrate': getattr(audio.info, 'bitrate', 0),
                    'sample_rate': getattr(audio.info, 'sample_rate', 0),
                    'channels': getattr(audio.info, 'channels', 0),
                }
                
                # Get bit depth for lossless formats
                if hasattr(audio.info, 'bits_per_sample'):
                    essential_metadata['bit_depth'] = audio.info.bits_per_sample
                
                # Extract only essential tags to avoid reading large embedded images
                if audio.tags:
                    tag_mapping = {
                        'title': ['TIT2', 'Title', 'title', '\xa9nam'],
                        'artist': ['TPE1', 'Artist', 'artist', '\xa9ART'],
                        'album': ['TALB', 'Album', 'album', '\xa9alb'],
                        'date': ['TDRC', 'Date', 'date', '\xa9day', 'year'],
                        'genre': ['TCON', 'Genre', 'genre', '\xa9gen'],
                        'albumartist': ['TPE2', 'AlbumArtist', 'albumartist', 'aART'],
                    }
                    
                    for key, possible_tags in tag_mapping.items():
                        value = None
                        for tag in possible_tags:
                            if tag in audio.tags:
                                value = audio.tags[tag]
                                if isinstance(value, list) and value:
                                    value = str(value[0])
                                else:
                                    value = str(value)
                                break
                        
                        if value:
                            essential_metadata[key] = self._clean_tag_value(value)
                
                metadata.update(essential_metadata)
                
            except Exception as e:
                self.logger.debug(f"Error in traditional metadata extraction for large file: {e}")
                # Fallback to filename extraction
                return self._extract_from_filename(file_path)
            
            # Post-process metadata
            metadata = self._post_process_metadata(metadata, file_path)
            
            return metadata
            
        except Exception as e:
            self.logger.error(f"Error in chunked metadata extraction: {e}")
            return self._extract_from_filename(file_path)
    
    def _extract_metadata_traditional(self, file_path: str) -> Dict[str, any]:
        """Extract metadata using traditional method for small files"""
        try:
            audio = MutagenFile(file_path)
            if audio is None:
                return self._extract_from_filename(file_path)
            
            metadata = {
                'file_path': file_path,
                'filename': os.path.basename(file_path),
                'format': audio.mime[0].split('/')[-1] if audio.mime else self._get_format_from_extension(file_path),
                'duration': getattr(audio.info, 'length', 0),
                'bitrate': getattr(audio.info, 'bitrate', 0),
                'sample_rate': getattr(audio.info, 'sample_rate', 0),
                'channels': getattr(audio.info, 'channels', 0),
            }
            
            # Get bit depth for lossless formats
            if hasattr(audio.info, 'bits_per_sample'):
                metadata['bit_depth'] = audio.info.bits_per_sample
            
            # Extract tags
            if audio.tags:
                tag_mapping = {
                    'title': ['TIT2', 'Title', 'title', '\xa9nam'],
                    'artist': ['TPE1', 'Artist', 'artist', '\xa9ART'],
                    'album': ['TALB', 'Album', 'album', '\xa9alb'],
                    'date': ['TDRC', 'Date', 'date', '\xa9day', 'year'],
                    'genre': ['TCON', 'Genre', 'genre', '\xa9gen'],
                    'albumartist': ['TPE2', 'AlbumArtist', 'albumartist', 'aART'],
                    'track': ['TRCK', 'Track', 'track', 'trkn'],
                    'comment': ['COMM', 'Comment', 'comment', '\xa9cmt'],
                }
                
                for key, possible_tags in tag_mapping.items():
                    value = None
                    for tag in possible_tags:
                        if tag in audio.tags:
                            value = audio.tags[tag]
                            if isinstance(value, list) and value:
                                value = str(value[0])
                            else:
                                value = str(value)
                            break
                    
                    if value:
                        metadata[key] = self._clean_tag_value(value)
            
            # Post-process metadata
            metadata = self._post_process_metadata(metadata, file_path)
            
            return metadata
            
        except Exception as e:
            self.logger.error(f"Error extracting metadata from {file_path}: {e}")
            return self._extract_from_filename(file_path)
    
    def _post_process_metadata(self, metadata: Dict, file_path: str) -> Dict:
        """Post-process extracted metadata"""
        # If no metadata from tags, try filename
        if not metadata.get('artist') or not metadata.get('title'):
            filename_metadata = self._extract_from_filename(file_path)
            for key in ['artist', 'title']:
                if not metadata.get(key) and filename_metadata.get(key):
                    metadata[key] = filename_metadata[key]
        
        # Normalize genre
        if metadata.get('genre'):
            metadata['genre'] = self._normalize_genre(metadata['genre'])
        
        # Extract year from date
        if metadata.get('date'):
            year = self._extract_year(metadata['date'])
            if year:
                metadata['year'] = year
        
        return metadata
    
    def enhance_metadata_streaming(self, file_path: str, existing_metadata: Dict = None) -> Dict:
        """Stream-aware metadata enhancement"""
        start_time = time.time()
        
        try:
            # Use existing metadata if provided, otherwise extract
            if existing_metadata:
                metadata = existing_metadata.copy()
            else:
                metadata = self.extract_metadata_streaming(file_path)
            
            # Memory check
            if self.memory_monitor and not self.memory_monitor.check_memory():
                self.logger.debug("Memory limit during metadata enhancement")
                return metadata
            
            # Enhance with external sources if enabled
            if self.enable_musicbrainz:
                # Check cache first
                cache_key = f"mb:{metadata.get('artist', '')}:{metadata.get('title', '')}"
                if cache_key in self.metadata_cache:
                    cached_mb_data = self.metadata_cache[cache_key]
                    if cached_mb_data:
                        metadata.update(cached_mb_data)
                        self.metrics['cache_hits'] += 1
                else:
                    # Rate limiting
                    self.rate_limiter.wait()
                    enhanced = self._enrich_from_musicbrainz_streaming(metadata)
                    if enhanced != metadata:
                        # Cache the enhancement
                        enhancement = {k: v for k, v in enhanced.items() if k not in metadata or metadata[k] != v}
                        self._cache_result(cache_key, enhancement)
                        metadata = enhanced
            
            # Update metrics
            self.metrics['enhancement_time'] += time.time() - start_time
            
            return metadata
            
        except Exception as e:
            self.logger.error(f"Error enhancing metadata for {file_path}: {e}")
            return existing_metadata or {}
    
    def _enrich_from_musicbrainz_streaming(self, metadata: Dict) -> Dict:
        """Stream-optimized MusicBrainz enrichment"""
        if not self.enable_musicbrainz or not MUSICBRAINZ_AVAILABLE:
            return metadata
        
        artist = metadata.get('artist')
        title = metadata.get('title')
        
        if not artist or not title:
            return metadata
        
        try:
            # Search for recording with timeout
            results = musicbrainzngs.search_recordings(
                artist=artist,
                recording=title,
                limit=3  # Reduced limit for speed
            )
            
            if results and results['recording-list']:
                best_match = results['recording-list'][0]
                
                # Update metrics
                self.metrics['musicbrainz_lookups'] += 1
                
                # Update metadata with MusicBrainz data
                if 'artist-credit' in best_match:
                    mb_artist = best_match['artist-credit'][0]['artist']['name']
                    if mb_artist:
                        metadata['artist'] = mb_artist
                
                if 'title' in best_match:
                    metadata['title'] = best_match['title']
                
                # Get first release for additional info
                if 'release-list' in best_match and best_match['release-list']:
                    release = best_match['release-list'][0]
                    
                    if 'date' in release:
                        year = self._extract_year(release['date'])
                        if year:
                            metadata['year'] = year
                    
                    if 'title' in release and not metadata.get('album'):
                        metadata['album'] = release['title']
                
                metadata['musicbrainz_id'] = best_match['id']
                
                # Shorter rate limit for streaming
                time.sleep(0.5)
            
        except Exception as e:
            self.logger.debug(f"MusicBrainz lookup failed for {artist} - {title}: {e}")
        
        return metadata
    
    def stream_enhance_metadata(self, metadata_stream: Generator[Dict, None, None]) -> Generator[Dict, None, None]:
        """Stream process metadata enhancement for multiple files"""
        with StreamingProgressTracker("Metadata Enhancement", enable_db_tracking=True) as progress:
            processed_count = 0
            
            for metadata_item in metadata_stream:
                try:
                    # Memory check
                    if self.memory_monitor and not self.memory_monitor.check_memory():
                        self.logger.warning("Memory limit during streaming metadata enhancement")
                        gc.collect()
                    
                    # Enhance metadata
                    enhanced = self.enhance_metadata_streaming(
                        metadata_item.get('file_path'),
                        metadata_item
                    )
                    
                    if enhanced:
                        yield enhanced
                        progress.update(1, has_error=False)
                    else:
                        progress.update(1, has_error=True)
                    
                    processed_count += 1
                    
                    # Periodic cache cleanup
                    if processed_count % 2000 == 0:
                        self._cleanup_cache()
                        self.logger.debug(f"Enhanced metadata for {processed_count} files")
                
                except Exception as e:
                    self.logger.error(f"Error in streaming metadata enhancement: {e}")
                    # Return original metadata on error
                    yield metadata_item
                    progress.update(1, has_error=True)
    
    def _cache_result(self, key: str, result: any):
        """Cache result with size management"""
        if len(self.metadata_cache) >= self.cache_max_size:
            # Remove oldest entries (simple LRU)
            oldest_keys = list(self.metadata_cache.keys())[:200]
            for old_key in oldest_keys:
                del self.metadata_cache[old_key]
        
        self.metadata_cache[key] = result
    
    def _cleanup_cache(self):
        """Clean up caches to prevent memory growth"""
        # Clear half of the cache
        cache_size = len(self.metadata_cache)
        if cache_size > self.cache_max_size // 2:
            keys_to_remove = list(self.metadata_cache.keys())[:cache_size // 2]
            for key in keys_to_remove:
                del self.metadata_cache[key]
        
        # Force garbage collection
        gc.collect()
    
    def get_file_metadata(self, file_path: str) -> Dict:
        """Get file metadata with caching (compatibility method)"""
        return self.extract_metadata_streaming(file_path)
    
    def enhance_metadata(self, file_path: str, existing_metadata: Dict = None) -> Dict:
        """Legacy method - redirects to streaming version"""
        return self.enhance_metadata_streaming(file_path, existing_metadata)
    
    def get_performance_metrics(self) -> Dict:
        """Get performance metrics for monitoring"""
        return {
            **self.metrics,
            'cache_size': len(self.metadata_cache),
            'cache_hit_rate': self.metrics['cache_hits'] / max(self.metrics['files_processed'], 1),
            'avg_extraction_time': self.metrics['extraction_time'] / max(self.metrics['files_processed'], 1),
            'avg_enhancement_time': self.metrics['enhancement_time'] / max(self.metrics['files_processed'], 1),
            'musicbrainz_success_rate': self.metrics['musicbrainz_lookups'] / max(self.metrics['files_processed'], 1)
        }
    
    # All the utility methods from the original MetadataManager
    def _extract_from_filename(self, file_path: str) -> Dict[str, str]:
        """Extract metadata from filename when tags are missing"""
        filename = os.path.splitext(os.path.basename(file_path))[0]
        
        # Clean up filename
        cleaned = filename
        for pattern, replacement in self.cleanup_patterns:
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
        
        cleaned = cleaned.strip()
        
        metadata = {
            'file_path': file_path,
            'filename': os.path.basename(file_path),
            'format': self._get_format_from_extension(file_path)
        }
        
        # Try common patterns
        patterns = [
            # Artist - Title (Mix)
            r'^([^-]+?)\s*-\s*([^(\[]+)(?:\s*[\(\[]([^\)\]]+)[\)\]])?',
            # Artist-Title
            r'^([^-]+?)-([^-]+)$',
            # Artist_-_Title
            r'^([^_]+?)_+\-_+([^_]+)$',
            # Title by Artist
            r'^(.+?)\s+by\s+(.+)$',
        ]
        
        for pattern in patterns:
            match = re.match(pattern, cleaned, re.IGNORECASE)
            if match:
                groups = match.groups()
                if len(groups) >= 2:
                    if pattern.endswith(r'by\s+(.+)$'):
                        # "Title by Artist" pattern
                        metadata['title'] = groups[0].strip()
                        metadata['artist'] = groups[1].strip()
                    else:
                        # "Artist - Title" pattern
                        metadata['artist'] = groups[0].strip()
                        metadata['title'] = groups[1].strip()
                        
                    # Check for mix type in parentheses
                    if len(groups) > 2 and groups[2]:
                        metadata['mix'] = groups[2].strip()
                    
                    break
        
        # If no pattern matched, use the cleaned filename as title
        if not metadata.get('title'):
            metadata['title'] = cleaned
        
        return metadata
    
    def _clean_tag_value(self, value: str) -> str:
        """Clean and normalize tag values"""
        if not value:
            return ''
        
        # Convert to string and strip
        value = str(value).strip()
        
        # Remove null characters
        value = value.replace('\x00', '')
        
        # Clean up encoding issues
        try:
            value = value.encode('latin-1').decode('utf-8')
        except:
            pass
        
        # Remove extra whitespace
        value = ' '.join(value.split())
        
        return value
    
    def _normalize_genre(self, genre: str) -> str:
        """Normalize genre string"""
        if not genre:
            return 'Unknown'
        
        genre_lower = genre.lower().strip()
        
        # Check genre map
        if genre_lower in self.genre_map:
            return self.genre_map[genre_lower]
        
        # Check partial matches
        for key, normalized in self.genre_map.items():
            if key in genre_lower:
                return normalized
        
        # Title case if not found
        return genre.title()
    
    def _extract_year(self, date_str: str) -> Optional[int]:
        """Extract year from date string"""
        if not date_str:
            return None
        
        # Try different patterns
        patterns = [
            r'(\d{4})',  # Just year
            r'(\d{4})-\d{2}-\d{2}',  # ISO date
            r'(\d{2})/\d{2}/(\d{4})',  # US date
            r'(\d{2})\.\d{2}\.(\d{4})',  # EU date
        ]
        
        for pattern in patterns:
            match = re.search(pattern, str(date_str))
            if match:
                year_str = match.group(1)
                if len(year_str) == 2:
                    # Handle 2-digit years
                    year = int(year_str)
                    if year > 50:
                        return 1900 + year
                    else:
                        return 2000 + year
                else:
                    year = int(year_str)
                    if 1900 <= year <= datetime.now().year:
                        return year
        
        return None
    
    def _get_format_from_extension(self, file_path: str) -> str:
        """Get format from file extension"""
        ext = os.path.splitext(file_path)[1].lower()
        format_map = {
            '.mp3': 'mp3',
            '.flac': 'flac',
            '.wav': 'wav',
            '.m4a': 'm4a',
            '.ogg': 'ogg',
            '.wma': 'wma',
            '.aac': 'aac',
        }
        return format_map.get(ext, 'unknown')
    
    def clean_filename(self, artist: str, title: str, extension: str) -> str:
        """Generate clean filename from metadata"""
        # Clean artist and title
        if artist:
            artist = self._sanitize_filename(artist)
        else:
            artist = 'Unknown Artist'
        
        if title:
            title = self._sanitize_filename(title)
        else:
            title = 'Unknown Title'
        
        # Format: "Artist - Title.ext"
        filename = f"{artist} - {title}{extension}"
        
        # Ensure filename isn't too long (Windows limit)
        max_length = 255 - len(extension)
        if len(filename) > 255:
            # Truncate title first, then artist if needed
            available_length = max_length - len(artist) - 3  # 3 for " - "
            if available_length > 30:
                title = title[:available_length-3] + '...'
            else:
                # Very long artist name
                artist = artist[:100] + '...'
                title = title[:50] + '...'
            
            filename = f"{artist} - {title}{extension}"
        
        return filename
    
    def _sanitize_filename(self, name: str) -> str:
        """Sanitize string for use in filename"""
        if not name:
            return ''
        
        # Remove/replace invalid characters for Windows
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            name = name.replace(char, '')
        
        # Replace other problematic characters
        name = name.replace('/', '-')
        name = name.replace('\\', '-')
        name = name.replace(':', '-')
        name = name.replace('?', '')
        name = name.replace('*', '')
        name = name.replace('"', "'")
        name = name.replace('<', '(')
        name = name.replace('>', ')')
        name = name.replace('|', '-')
        
        # Remove control characters
        name = ''.join(char for char in name if ord(char) >= 32)
        
        # Remove trailing dots and spaces (Windows doesn't like them)
        name = name.strip('. ')
        
        # Collapse multiple spaces
        name = ' '.join(name.split())
        
        return name
    
    def update_file_tags(self, file_path: str, metadata: Dict) -> bool:
        """Update file tags with cleaned metadata"""
        try:
            audio = MutagenFile(file_path)
            if audio is None:
                return False
            
            # Handle different formats
            if isinstance(audio, MP3):
                # Ensure ID3 tags exist
                if audio.tags is None:
                    audio.add_tags()
                
                # Update tags
                if metadata.get('title'):
                    audio.tags['TIT2'] = TIT2(encoding=3, text=metadata['title'])
                if metadata.get('artist'):
                    audio.tags['TPE1'] = TPE1(encoding=3, text=metadata['artist'])
                if metadata.get('album'):
                    audio.tags['TALB'] = TALB(encoding=3, text=metadata['album'])
                if metadata.get('date') or metadata.get('year'):
                    date_str = metadata.get('date', str(metadata.get('year', '')))
                    audio.tags['TDRC'] = TDRC(encoding=3, text=date_str)
                if metadata.get('genre'):
                    audio.tags['TCON'] = TCON(encoding=3, text=metadata['genre'])
                if metadata.get('albumartist'):
                    audio.tags['TPE2'] = TPE2(encoding=3, text=metadata['albumartist'])
            
            else:
                # For other formats, use the common interface
                if audio.tags is None:
                    audio.add_tags()
                
                # Update tags using common keys
                tag_mapping = {
                    'title': ['title', 'Title', '\xa9nam'],
                    'artist': ['artist', 'Artist', '\xa9ART'],
                    'album': ['album', 'Album', '\xa9alb'],
                    'date': ['date', 'Date', '\xa9day'],
                    'genre': ['genre', 'Genre', '\xa9gen'],
                    'albumartist': ['albumartist', 'AlbumArtist', 'aART'],
                }
                
                for key, value in metadata.items():
                    if key in tag_mapping and value:
                        # Try each possible tag name
                        for tag_name in tag_mapping[key]:
                            try:
                                audio.tags[tag_name] = value
                                break
                            except:
                                continue
            
            # Save changes
            audio.save()
            return True
            
        except Exception as e:
            self.logger.error(f"Error updating tags for {file_path}: {e}")
            return False