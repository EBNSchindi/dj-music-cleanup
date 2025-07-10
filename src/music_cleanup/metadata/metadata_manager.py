"""
Metadata-First Manager for DJ Music Cleanup Tool

Implements the strict metadata acquisition priority:
1. Audio Fingerprint Lookup (ALWAYS FIRST!)
2. File Tags Fallback  
3. Intelligent Filename Parsing
4. Metadata Queue (NEVER "Unknown")
"""

import logging
import hashlib
from pathlib import Path
from typing import Dict, Optional, Any, List
from dataclasses import dataclass, field
from datetime import datetime

from ..utils.decorators import handle_errors, track_performance
from .fingerprint_processor import FingerprintProcessor
from .api_services import AcoustIDService, MusicBrainzService
from .filename_parser import FilenameParser
from .metadata_queue import MetadataQueue


@dataclass
class MetadataResult:
    """Complete metadata result with source tracking"""
    artist: str
    title: str
    year: str = "0000"
    genre: str = "Unknown Genre"
    album: Optional[str] = None
    bpm: Optional[int] = None
    key: Optional[str] = None
    
    # Source tracking
    source: str = "unknown"  # acoustid, tags, filename, manual
    confidence: float = 0.0
    needs_verification: bool = False
    needs_review: bool = False
    
    # Additional metadata
    fingerprint: Optional[str] = None
    file_hash: Optional[str] = None
    quality_score: Optional[float] = None
    
    # Processing info
    processed_at: datetime = field(default_factory=datetime.now)
    api_response: Optional[Dict] = None

    def is_complete(self) -> bool:
        """Check if metadata is complete enough for processing"""
        return bool(self.artist and self.title and self.artist != "Unknown")
    
    def get_filename_pattern(self, pattern: str = "{year} - {artist} - {title} - QS{score}%") -> str:
        """Generate filename using pattern"""
        score = int(self.quality_score or 0)
        return pattern.format(
            year=self.year,
            artist=self._sanitize_filename(self.artist),
            title=self._sanitize_filename(self.title),
            score=score
        )
    
    def get_folder_path(self) -> str:
        """Generate folder path: genre/decade"""
        # Determine decade
        if self.year and self.year != "0000":
            try:
                decade = f"{int(self.year)//10*10}s"
            except (ValueError, TypeError):
                decade = "Unknown Era"
        else:
            decade = "Unknown Era"
        
        # Clean genre
        genre = self.genre or "Unknown Genre"
        if genre == "Unknown":
            genre = "Unknown Genre"
        
        return f"{self._sanitize_folder(genre)}/{decade}"
    
    def _sanitize_filename(self, name: str) -> str:
        """Sanitize name for filename use"""
        if not name:
            return "Unknown"
        
        # Remove/replace invalid characters
        invalid_chars = '<>:"/\\|?*'
        sanitized = ''.join(c if c not in invalid_chars else '_' for c in name)
        
        # Clean up whitespace
        sanitized = ' '.join(sanitized.split())
        
        # Limit length
        if len(sanitized) > 100:
            sanitized = sanitized[:97] + "..."
        
        return sanitized.strip()
    
    def _sanitize_folder(self, name: str) -> str:
        """Sanitize name for folder use"""
        if not name:
            return "Unknown"
        
        # Remove/replace invalid characters
        invalid_chars = '<>:"/\\|?*'
        sanitized = ''.join(c if c not in invalid_chars else '_' for c in name)
        
        # Clean up whitespace and dots
        sanitized = sanitized.strip(' .')
        
        return sanitized or "Unknown"


class MetadataManager:
    """
    Metadata-First Manager implementing strict priority order.
    
    CRITICAL: ALWAYS follows this exact order:
    1. Audio Fingerprint Lookup (NEVER skip!)
    2. File Tags Fallback
    3. Filename Parsing  
    4. Metadata Queue (NO "Unknown" entries)
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize metadata manager with configuration.
        
        Args:
            config: Configuration with metadata settings
        """
        self.config = config.get('metadata', {})
        self.logger = logging.getLogger(__name__)
        
        # Core components - FINGERPRINT ALWAYS ENABLED
        self.fingerprint_processor = FingerprintProcessor(self.config)
        self.filename_parser = FilenameParser(self.config)
        self.metadata_queue = MetadataQueue(config.get('output_directories', {}))
        
        # API Services
        self.acoustid_service = AcoustIDService(self.config.get('services', {}).get('acoustid', {}))
        self.musicbrainz_service = MusicBrainzService(self.config.get('services', {}).get('musicbrainz', {}))
        
        # Settings
        self.min_confidence = self.config.get('min_confidence', 0.8)
        self.fingerprint_first = self.config.get('fingerprint_first', True)  # ALWAYS True
        self.never_create_unknown = self.config.get('never_create_unknown', True)
        self.queue_unknown = self.config.get('queue_unknown', True)
        
        # Stats
        self.stats = {
            'fingerprint_success': 0,
            'tags_fallback': 0,
            'filename_parsing': 0,
            'queued_for_review': 0,
            'total_processed': 0
        }
        
        self.logger.info("MetadataManager initialized with Metadata-First approach")
        self.logger.info(f"  Min confidence: {self.min_confidence}")
        self.logger.info(f"  Never create unknown: {self.never_create_unknown}")
    
    @handle_errors(return_on_error=None)
    @track_performance(threshold_ms=5000)
    def get_metadata(self, file_path: str, quality_score: Optional[float] = None) -> Optional[MetadataResult]:
        """
        Get metadata using strict priority order.
        
        CRITICAL: ALWAYS follows this exact order:
        1. Audio Fingerprint Lookup (NEVER skip!)
        2. File Tags Fallback
        3. Filename Parsing
        4. Metadata Queue (NO "Unknown" entries)
        
        Args:
            file_path: Path to audio file
            quality_score: Optional quality score for filename pattern
            
        Returns:
            MetadataResult with complete metadata or None if queued
        """
        self.stats['total_processed'] += 1
        file_path = Path(file_path)
        
        self.logger.info(f"Processing metadata for: {file_path.name}")
        
        # STEP 1: AUDIO FINGERPRINT LOOKUP (ALWAYS FIRST!)
        fingerprint_result = self._try_fingerprint_lookup(file_path)
        if fingerprint_result and fingerprint_result.is_complete():
            fingerprint_result.quality_score = quality_score
            self.stats['fingerprint_success'] += 1
            self.logger.info(f"✅ Fingerprint success: {fingerprint_result.artist} - {fingerprint_result.title}")
            return fingerprint_result
        
        self.logger.warning(f"❌ Fingerprint lookup failed for: {file_path.name}")
        
        # STEP 2: FILE TAGS FALLBACK (only if fingerprint failed)
        tags_result = self._try_file_tags(file_path)
        if tags_result and tags_result.is_complete():
            tags_result.needs_verification = True
            tags_result.quality_score = quality_score
            self.stats['tags_fallback'] += 1
            self.logger.info(f"⚠️  Tags fallback: {tags_result.artist} - {tags_result.title}")
            return tags_result
        
        self.logger.warning(f"❌ File tags insufficient for: {file_path.name}")
        
        # STEP 3: FILENAME PARSING (last resort)
        filename_result = self._try_filename_parsing(file_path)
        if filename_result and filename_result.is_complete():
            filename_result.needs_review = True
            filename_result.quality_score = quality_score
            self.stats['filename_parsing'] += 1
            self.logger.info(f"🔍 Filename parsed: {filename_result.artist} - {filename_result.title}")
            return filename_result
        
        self.logger.warning(f"❌ Filename parsing failed for: {file_path.name}")
        
        # STEP 4: METADATA QUEUE (NEVER create "Unknown")
        if self.queue_unknown:
            fingerprint_data = fingerprint_result.fingerprint if fingerprint_result else None
            self.metadata_queue.queue_file(file_path, fingerprint_data, tags_result, filename_result)
            self.stats['queued_for_review'] += 1
            self.logger.info(f"📋 Queued for manual review: {file_path.name}")
        
        return None  # File is NOT processed until metadata is available
    
    def _try_fingerprint_lookup(self, file_path: Path) -> Optional[MetadataResult]:
        """
        STEP 1: Audio fingerprint lookup (ALWAYS FIRST!)
        
        Process:
        1. Generate Chromaprint fingerprint
        2. Check cache first
        3. AcoustID API lookup
        4. MusicBrainz metadata if successful
        5. Only accept confidence > min_confidence
        """
        try:
            # Generate fingerprint
            fingerprint_data = self.fingerprint_processor.generate_fingerprint(str(file_path))
            if not fingerprint_data:
                self.logger.debug(f"Failed to generate fingerprint for: {file_path.name}")
                return None
            
            # Check cache first
            cached_result = self.fingerprint_processor.check_cache(fingerprint_data)
            if cached_result:
                self.logger.debug(f"Cache hit for: {file_path.name}")
                cached_result.source = 'acoustid_cached'
                return cached_result
            
            # AcoustID API lookup
            acoustid_result = self.acoustid_service.lookup_fingerprint(fingerprint_data)
            if not acoustid_result:
                self.logger.debug(f"AcoustID lookup failed for: {file_path.name}")
                return None
            
            # Check confidence threshold
            confidence = acoustid_result.get('confidence', 0)
            if confidence < self.min_confidence:
                self.logger.debug(f"Low confidence ({confidence:.2f}) for: {file_path.name}")
                # Store low confidence result for possible matches in queue
                low_confidence_result = MetadataResult(
                    artist=acoustid_result.get('artist', 'Unknown'),
                    title=acoustid_result.get('title', 'Unknown'),
                    source='acoustid_low_confidence',
                    confidence=confidence,
                    fingerprint=fingerprint_data
                )
                return low_confidence_result  # Will be used in queue as possible match
            
            # Get MusicBrainz metadata if available
            musicbrainz_data = None
            if recording_id := acoustid_result.get('recording_id'):
                musicbrainz_data = self.musicbrainz_service.get_recording(recording_id)
            
            # Build metadata result
            result = MetadataResult(
                artist=acoustid_result.get('artist', 'Unknown'),
                title=acoustid_result.get('title', 'Unknown'),
                year=str(acoustid_result.get('year') or musicbrainz_data.get('year') or '0000'),
                genre=musicbrainz_data.get('genre') if musicbrainz_data else 'Unknown Genre',
                album=musicbrainz_data.get('album') if musicbrainz_data else None,
                source='acoustid',
                confidence=acoustid_result.get('confidence', 0),
                fingerprint=fingerprint_data,
                file_hash=self._calculate_file_hash(file_path),
                api_response=acoustid_result
            )
            
            # Try to detect genre from audio if not in MusicBrainz
            if result.genre == 'Unknown Genre':
                detected_genre = self._detect_genre_from_audio(file_path)
                if detected_genre:
                    result.genre = detected_genre
            
            # Cache successful result
            self.fingerprint_processor.cache_result(fingerprint_data, result)
            
            return result
            
        except Exception as e:
            self.logger.error(f"Fingerprint lookup error for {file_path.name}: {e}")
            return None
    
    def _try_file_tags(self, file_path: Path) -> Optional[MetadataResult]:
        """
        STEP 2: File tags fallback (only if fingerprint failed)
        
        Read ID3v2, ID3v1, Vorbis Comments, MP4 tags
        Validate completeness (Artist, Title, Year minimum)
        """
        try:
            import mutagen
            
            audio_file = mutagen.File(str(file_path))
            if not audio_file or not audio_file.tags:
                return None
            
            # Extract basic tags
            artist = self._extract_tag(audio_file.tags, ['TPE1', 'ARTIST', '©ART', 'ALBUMARTIST'])
            title = self._extract_tag(audio_file.tags, ['TIT2', 'TITLE', '©nam'])
            year = self._extract_tag(audio_file.tags, ['TDRC', 'DATE', '©day', 'YEAR'])
            genre = self._extract_tag(audio_file.tags, ['TCON', 'GENRE', '©gen'])
            album = self._extract_tag(audio_file.tags, ['TALB', 'ALBUM', '©alb'])
            
            # Clean year
            if year:
                year = str(year)[:4]  # Take first 4 digits
                try:
                    int(year)  # Validate it's a number
                except ValueError:
                    year = "0000"
            else:
                year = "0000"
            
            # Validate minimum requirements
            if not artist or not title:
                return None
            
            result = MetadataResult(
                artist=str(artist).strip(),
                title=str(title).strip(),
                year=year,
                genre=str(genre).strip() if genre else "Unknown Genre",
                album=str(album).strip() if album else None,
                source='tags',
                confidence=0.7,  # Tags get medium confidence
                file_hash=self._calculate_file_hash(file_path),
                needs_verification=True
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"File tags reading error for {file_path.name}: {e}")
            return None
    
    def _try_filename_parsing(self, file_path: Path) -> Optional[MetadataResult]:
        """
        STEP 3: Intelligent filename parsing (last resort)
        
        Parse patterns like:
        - "BPM - Artist - Title (Remix).mp3"
        - "Artist - Title (Extended Mix) [Label].mp3"
        - "01. Artist - Title.mp3"
        """
        try:
            parsed = self.filename_parser.parse_filename(file_path.name)
            if not parsed or not parsed.get('artist') or parsed.get('artist') == 'Unknown':
                return None
            
            result = MetadataResult(
                artist=parsed['artist'],
                title=parsed['title'],
                year="0000",  # Filename rarely contains reliable year
                genre="Unknown Genre",  # Cannot determine from filename
                bpm=parsed.get('bpm'),
                source='filename',
                confidence=0.5,  # Filename gets low confidence
                file_hash=self._calculate_file_hash(file_path),
                needs_review=True  # ALWAYS needs review
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Filename parsing error for {file_path.name}: {e}")
            return None
    
    def _extract_tag(self, tags: Any, tag_names: List[str]) -> Optional[str]:
        """Extract tag value trying multiple tag name variants"""
        for tag_name in tag_names:
            if tag_name in tags:
                value = tags[tag_name]
                if isinstance(value, list) and value:
                    return str(value[0]).strip()
                elif value:
                    return str(value).strip()
        return None
    
    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file for identification"""
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    
    def _detect_genre_from_audio(self, file_path: Path) -> Optional[str]:
        """
        Attempt to detect genre from audio analysis.
        Uses basic audio characteristics to make educated guesses.
        """
        try:
            # Basic genre detection based on filename patterns and BPM
            filename_lower = file_path.name.lower()
            
            # Electronic/Dance music indicators
            if any(keyword in filename_lower for keyword in ['edm', 'house', 'techno', 'trance', 'electro']):
                return 'Electronic'
            
            # Hip-hop indicators
            if any(keyword in filename_lower for keyword in ['hip', 'rap', 'trap', 'drill']):
                return 'Hip-Hop'
            
            # Rock indicators
            if any(keyword in filename_lower for keyword in ['rock', 'metal', 'punk', 'alternative']):
                return 'Rock'
            
            # Pop indicators
            if any(keyword in filename_lower for keyword in ['pop', 'mainstream', 'chart', 'hit']):
                return 'Pop'
            
            # Jazz indicators
            if any(keyword in filename_lower for keyword in ['jazz', 'blues', 'soul', 'funk']):
                return 'Jazz'
            
            # Classical indicators
            if any(keyword in filename_lower for keyword in ['classical', 'symphony', 'concerto', 'opera']):
                return 'Classical'
            
            # Country indicators
            if any(keyword in filename_lower for keyword in ['country', 'folk', 'bluegrass', 'americana']):
                return 'Country'
            
            # Reggae indicators
            if any(keyword in filename_lower for keyword in ['reggae', 'dub', 'ska', 'dancehall']):
                return 'Reggae'
            
            # TODO: Future enhancement - implement audio analysis using librosa
            # This would analyze tempo, spectral features, etc.
            # For now, return None to indicate no genre detected
            return None
            
        except Exception as e:
            self.logger.error(f"Genre detection error: {e}")
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get processing statistics"""
        total = self.stats['total_processed']
        if total == 0:
            return self.stats
        
        return {
            **self.stats,
            'success_rate': {
                'fingerprint': round(self.stats['fingerprint_success'] / total * 100, 1),
                'tags': round(self.stats['tags_fallback'] / total * 100, 1),
                'filename': round(self.stats['filename_parsing'] / total * 100, 1),
                'queued': round(self.stats['queued_for_review'] / total * 100, 1)
            }
        }
    
    def reset_stats(self) -> None:
        """Reset processing statistics"""
        self.stats = {key: 0 for key in self.stats.keys()}
    
    def process_completed_queue_files(self) -> List[MetadataResult]:
        """
        Process files that have been manually reviewed and completed in the metadata queue.
        
        Returns:
            List of MetadataResult objects ready for file processing
        """
        results = []
        
        try:
            completed_files = self.metadata_queue.get_completed_files()
            
            for queued_file in completed_files:
                if queued_file.manual_metadata:
                    # Convert manual metadata to MetadataResult
                    result = MetadataResult(
                        artist=queued_file.manual_metadata['artist'],
                        title=queued_file.manual_metadata['title'],
                        year=queued_file.manual_metadata.get('year', '0000'),
                        genre=queued_file.manual_metadata.get('genre', 'Unknown Genre'),
                        album=queued_file.manual_metadata.get('album'),
                        bpm=queued_file.manual_metadata.get('bpm'),
                        key=queued_file.manual_metadata.get('key'),
                        source='manual',
                        confidence=queued_file.manual_metadata.get('confidence', 1.0),
                        fingerprint=queued_file.fingerprint,
                        file_hash=queued_file.file_hash
                    )
                    
                    results.append(result)
            
            # Remove completed files from queue
            if results:
                removed_count = self.metadata_queue.remove_completed_files()
                self.logger.info(f"Processed {len(results)} completed files from metadata queue")
                
            return results
            
        except Exception as e:
            self.logger.error(f"Error processing completed queue files: {e}")
            return []
    
    def get_metadata_queue_stats(self) -> Dict[str, Any]:
        """Get metadata queue statistics"""
        return self.metadata_queue.get_stats()
    
    def export_metadata_queue_to_csv(self, output_file: Optional[str] = None) -> str:
        """Export metadata queue to CSV for bulk editing"""
        try:
            from pathlib import Path
            export_path = self.metadata_queue.export_to_csv(
                Path(output_file) if output_file else None
            )
            return str(export_path)
        except Exception as e:
            self.logger.error(f"CSV export error: {e}")
            return ""
    
    def import_metadata_queue_from_csv(self, input_file: Optional[str] = None) -> int:
        """Import processed metadata from CSV"""
        try:
            from pathlib import Path
            return self.metadata_queue.import_from_csv(
                Path(input_file) if input_file else None
            )
        except Exception as e:
            self.logger.error(f"CSV import error: {e}")
            return 0