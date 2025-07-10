"""
Reference-Based Quality Checker

Vergleicht Audio-Dateien mit Referenz-Versionen über AcoustID und MusicBrainz
um relative Qualität zu bewerten.
"""

import json
import logging
import os
import time
import sqlite3
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urlencode
import hashlib

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    import acoustid
    ACOUSTID_AVAILABLE = True
except ImportError:
    ACOUSTID_AVAILABLE = False

try:
    import musicbrainzngs
    MUSICBRAINZ_AVAILABLE = True
except ImportError:
    MUSICBRAINZ_AVAILABLE = False


class ReferenceQuality(Enum):
    """Qualitätsstufen für Referenz-Versionen"""
    LOSSLESS = "lossless"  # FLAC, WAV, ALAC
    HIGH_BITRATE = "high_bitrate"  # 320kbps MP3, 256kbps AAC
    MEDIUM_BITRATE = "medium_bitrate"  # 192-256kbps
    LOW_BITRATE = "low_bitrate"  # <192kbps
    UNKNOWN = "unknown"


@dataclass
class ReferenceVersion:
    """Repräsentiert eine Referenz-Version eines Tracks"""
    recording_id: str  # MusicBrainz Recording ID
    release_id: Optional[str] = None
    title: str = ""
    artist: str = ""
    album: str = ""
    format: Optional[str] = None  # CD, Digital Media, Vinyl
    quality: ReferenceQuality = ReferenceQuality.UNKNOWN
    bitrate: Optional[int] = None
    duration: Optional[float] = None
    release_date: Optional[str] = None
    release_country: Optional[str] = None
    label: Optional[str] = None
    catalog_number: Optional[str] = None
    confidence_score: float = 0.0  # Wie sicher sind wir, dass es der gleiche Track ist
    source: str = "musicbrainz"  # musicbrainz, spotify, lastfm, etc.
    additional_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReferenceComparisonResult:
    """Ergebnis des Vergleichs mit Referenz-Versionen"""
    test_file: str
    best_reference: Optional[ReferenceVersion] = None
    all_references: List[ReferenceVersion] = field(default_factory=list)
    quality_score_relative: float = 0.0  # 0-100, relativ zur besten Referenz
    quality_score_absolute: float = 0.0  # 0-100, absolute Bewertung
    is_best_available: bool = False
    upgrade_available: bool = False
    comparison_details: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)


class ReferenceQualityChecker:
    """
    Prüft Audio-Qualität gegen bekannte Referenz-Versionen.
    
    Nutzt:
    - AcoustID für Audio-Fingerprinting und Track-Identifikation
    - MusicBrainz für Metadaten und Release-Informationen
    - Optional: Spotify/Last.fm APIs für zusätzliche Audio-Features
    """
    
    # API Konfiguration
    ACOUSTID_API_KEY = os.environ.get('ACOUSTID_API_KEY', 'cSpUJKpD')  # Test key
    MUSICBRAINZ_USER_AGENT = 'DJ-Music-Cleanup/1.0 (https://github.com/user/dj-music-cleanup)'
    
    # Qualitäts-Mapping für verschiedene Formate
    FORMAT_QUALITY_MAP = {
        'FLAC': ReferenceQuality.LOSSLESS,
        'WAV': ReferenceQuality.LOSSLESS,
        'ALAC': ReferenceQuality.LOSSLESS,
        'AIFF': ReferenceQuality.LOSSLESS,
        'DSD': ReferenceQuality.LOSSLESS,
        'MP3 320': ReferenceQuality.HIGH_BITRATE,
        'MP3 256': ReferenceQuality.HIGH_BITRATE,
        'AAC 256': ReferenceQuality.HIGH_BITRATE,
        'MP3 192': ReferenceQuality.MEDIUM_BITRATE,
        'MP3 128': ReferenceQuality.LOW_BITRATE,
        'MP3 VBR': ReferenceQuality.MEDIUM_BITRATE,  # Konservative Schätzung
    }
    
    def __init__(self, 
                 cache_dir: str = None,
                 acoustid_api_key: str = None,
                 enable_spotify: bool = False,
                 enable_lastfm: bool = False):
        """
        Initialize the reference quality checker.
        
        Args:
            cache_dir: Directory für Reference-Cache
            acoustid_api_key: AcoustID API Key (optional)
            enable_spotify: Spotify API nutzen (benötigt Credentials)
            enable_lastfm: Last.fm API nutzen (benötigt API Key)
        """
        self.logger = logging.getLogger(__name__)
        
        # API Keys
        if acoustid_api_key:
            self.ACOUSTID_API_KEY = acoustid_api_key
        
        # Cache Setup
        if cache_dir:
            self.cache_dir = Path(cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.cache_dir = Path.home() / '.dj_music_cleanup' / 'reference_cache'
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.cache_db = self.cache_dir / 'reference_cache.db'
        self._init_cache_db()
        
        # MusicBrainz Setup
        if MUSICBRAINZ_AVAILABLE:
            musicbrainzngs.set_useragent(
                "DJ-Music-Cleanup", 
                "1.0", 
                "https://github.com/user/dj-music-cleanup"
            )
        
        # Statistics
        self.stats = {
            'lookups_performed': 0,
            'cache_hits': 0,
            'references_found': 0,
            'upgrades_detected': 0
        }
    
    def _init_cache_db(self):
        """Initialize cache database"""
        with sqlite3.connect(self.cache_db) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reference_cache (
                    acoustid TEXT PRIMARY KEY,
                    recording_data TEXT,  -- JSON
                    references TEXT,      -- JSON list of ReferenceVersion
                    lookup_time REAL,
                    expires_at REAL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS quality_mappings (
                    recording_id TEXT,
                    format TEXT,
                    quality TEXT,
                    bitrate INTEGER,
                    source TEXT,
                    confidence REAL,
                    PRIMARY KEY (recording_id, format, source)
                )
            """)
    
    def check_against_references(self, 
                               file_path: str, 
                               fingerprint: Optional[str] = None,
                               duration: Optional[float] = None) -> ReferenceComparisonResult:
        """
        Hauptmethode: Vergleicht Datei mit Referenz-Versionen.
        
        Args:
            file_path: Pfad zur Audio-Datei
            fingerprint: Chromaprint fingerprint (optional, wird sonst berechnet)
            duration: Dauer in Sekunden (optional)
            
        Returns:
            ReferenceComparisonResult mit Vergleichsergebnis
        """
        self.stats['lookups_performed'] += 1
        
        # 1. Get AcoustID for the file
        acoustid_result = self._get_acoustid(file_path, fingerprint, duration)
        if not acoustid_result:
            return ReferenceComparisonResult(
                test_file=file_path,
                comparison_details={'error': 'Could not generate AcoustID'}
            )
        
        # 2. Check cache first
        cached_references = self._get_cached_references(acoustid_result['id'])
        if cached_references:
            self.stats['cache_hits'] += 1
            references = cached_references
        else:
            # 3. Lookup references from MusicBrainz
            references = self._lookup_references(acoustid_result)
            if references:
                self._cache_references(acoustid_result['id'], references)
        
        if not references:
            return ReferenceComparisonResult(
                test_file=file_path,
                comparison_details={'error': 'No references found'}
            )
        
        self.stats['references_found'] += len(references)
        
        # 4. Analyze test file quality
        test_quality = self._analyze_test_file_quality(file_path)
        
        # 5. Compare with references
        comparison_result = self._compare_with_references(
            test_quality, references, file_path
        )
        
        # 6. Generate recommendations
        self._generate_recommendations(comparison_result, test_quality)
        
        if comparison_result.upgrade_available:
            self.stats['upgrades_detected'] += 1
        
        return comparison_result
    
    def _get_acoustid(self, file_path: str, 
                     fingerprint: Optional[str] = None,
                     duration: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Get AcoustID for audio file"""
        if not ACOUSTID_AVAILABLE:
            self.logger.warning("acoustid module not available")
            return None
        
        try:
            if fingerprint and duration:
                # Use provided fingerprint
                results = acoustid.lookup(
                    self.ACOUSTID_API_KEY,
                    fingerprint,
                    duration,
                    meta='recordings releasegroups releases'
                )
            else:
                # Calculate fingerprint
                results = acoustid.match(
                    self.ACOUSTID_API_KEY,
                    file_path,
                    meta='recordings releasegroups releases'
                )
            
            if results and 'results' in results and results['results']:
                best_result = results['results'][0]
                return {
                    'id': best_result.get('id'),
                    'score': best_result.get('score', 0),
                    'recordings': best_result.get('recordings', [])
                }
            
        except Exception as e:
            self.logger.error(f"AcoustID lookup failed: {e}")
        
        return None
    
    def _lookup_references(self, acoustid_result: Dict[str, Any]) -> List[ReferenceVersion]:
        """Lookup reference versions from MusicBrainz"""
        references = []
        
        if not MUSICBRAINZ_AVAILABLE:
            self.logger.warning("musicbrainzngs not available")
            return references
        
        try:
            for recording in acoustid_result.get('recordings', []):
                recording_id = recording.get('id')
                if not recording_id:
                    continue
                
                # Get detailed recording info
                try:
                    recording_info = musicbrainzngs.get_recording_by_id(
                        recording_id,
                        includes=['releases', 'artists', 'isrcs']
                    )
                    
                    recording_data = recording_info['recording']
                    
                    # Process each release
                    for release in recording_data.get('release-list', []):
                        ref_version = self._create_reference_version(
                            recording_data, release, acoustid_result['score']
                        )
                        if ref_version:
                            references.append(ref_version)
                    
                except Exception as e:
                    self.logger.debug(f"Error fetching recording {recording_id}: {e}")
            
            # Sort by quality and confidence
            references.sort(
                key=lambda r: (r.quality.value, r.confidence_score), 
                reverse=True
            )
            
        except Exception as e:
            self.logger.error(f"MusicBrainz lookup failed: {e}")
        
        return references
    
    def _create_reference_version(self, recording: Dict, release: Dict, 
                                confidence: float) -> Optional[ReferenceVersion]:
        """Create ReferenceVersion from MusicBrainz data"""
        try:
            # Extract basic info
            ref = ReferenceVersion(
                recording_id=recording['id'],
                release_id=release.get('id'),
                title=recording.get('title', ''),
                artist=self._get_artist_credit(recording),
                album=release.get('title', ''),
                duration=recording.get('length', 0) / 1000.0 if recording.get('length') else None,
                release_date=release.get('date'),
                release_country=release.get('country'),
                confidence_score=confidence
            )
            
            # Determine format and quality
            medium_list = release.get('medium-list', [])
            if medium_list:
                medium = medium_list[0]
                format_name = medium.get('format', 'Unknown')
                ref.format = format_name
                
                # Try to determine quality from format
                ref.quality = self._estimate_quality_from_format(format_name, release)
                
                # Store additional data
                ref.additional_data = {
                    'format': format_name,
                    'track_count': medium.get('track-count', 0),
                    'position': medium.get('position', 1)
                }
            
            # Label info
            label_info_list = release.get('label-info-list', [])
            if label_info_list:
                label_info = label_info_list[0]
                label = label_info.get('label', {})
                ref.label = label.get('name')
                ref.catalog_number = label_info.get('catalog-number')
            
            return ref
            
        except Exception as e:
            self.logger.debug(f"Error creating reference version: {e}")
            return None
    
    def _get_artist_credit(self, recording: Dict) -> str:
        """Extract artist credit from recording"""
        artist_credit = recording.get('artist-credit', [])
        if artist_credit:
            return ' '.join(
                ac.get('name', '') + ac.get('joinphrase', '')
                for ac in artist_credit
            ).strip()
        return ''
    
    def _estimate_quality_from_format(self, format_name: str, 
                                    release: Dict) -> ReferenceQuality:
        """Estimate quality based on format and release info"""
        format_upper = format_name.upper()
        
        # Direct format mapping
        for fmt, quality in self.FORMAT_QUALITY_MAP.items():
            if fmt in format_upper:
                return quality
        
        # Check common formats
        if format_upper in ['CD', 'SACD', 'DVD-AUDIO']:
            return ReferenceQuality.LOSSLESS
        elif 'DIGITAL' in format_upper or 'FILE' in format_upper:
            # For digital, check release date and label
            date = release.get('date', '')
            if date > '2015':  # Newer digital releases tend to be higher quality
                return ReferenceQuality.HIGH_BITRATE
            return ReferenceQuality.MEDIUM_BITRATE
        elif 'VINYL' in format_upper:
            # Vinyl rips vary, be conservative
            return ReferenceQuality.HIGH_BITRATE
        
        return ReferenceQuality.UNKNOWN
    
    def _analyze_test_file_quality(self, file_path: str) -> Dict[str, Any]:
        """Analyze quality indicators of test file"""
        quality_info = {
            'file_path': file_path,
            'file_size': 0,
            'estimated_bitrate': 0,
            'format': Path(file_path).suffix.lower()
        }
        
        try:
            # Get file size
            quality_info['file_size'] = os.path.getsize(file_path)
            
            # Try to get audio info with mutagen
            try:
                import mutagen
                audio = mutagen.File(file_path)
                if audio:
                    quality_info['duration'] = audio.info.length
                    quality_info['bitrate'] = getattr(audio.info, 'bitrate', 0)
                    quality_info['sample_rate'] = getattr(audio.info, 'sample_rate', 0)
                    
                    # Calculate estimated bitrate if not provided
                    if not quality_info['bitrate'] and quality_info['duration'] > 0:
                        quality_info['estimated_bitrate'] = (
                            quality_info['file_size'] * 8 / quality_info['duration'] / 1000
                        )
            except:
                pass
            
            # Determine quality category
            if quality_info['format'] in ['.flac', '.wav', '.aiff', '.alac']:
                quality_info['quality'] = ReferenceQuality.LOSSLESS
            elif quality_info.get('bitrate', 0) >= 256000 or \
                 quality_info.get('estimated_bitrate', 0) >= 256:
                quality_info['quality'] = ReferenceQuality.HIGH_BITRATE
            elif quality_info.get('bitrate', 0) >= 192000 or \
                 quality_info.get('estimated_bitrate', 0) >= 192:
                quality_info['quality'] = ReferenceQuality.MEDIUM_BITRATE
            else:
                quality_info['quality'] = ReferenceQuality.LOW_BITRATE
            
        except Exception as e:
            self.logger.error(f"Error analyzing test file: {e}")
        
        return quality_info
    
    def _compare_with_references(self, test_quality: Dict[str, Any],
                               references: List[ReferenceVersion],
                               file_path: str) -> ReferenceComparisonResult:
        """Compare test file with reference versions"""
        result = ReferenceComparisonResult(
            test_file=file_path,
            all_references=references
        )
        
        if not references:
            return result
        
        # Find best reference
        result.best_reference = references[0]  # Already sorted by quality
        
        # Calculate quality scores
        test_quality_enum = test_quality.get('quality', ReferenceQuality.UNKNOWN)
        best_ref_quality = result.best_reference.quality
        
        # Quality score mapping
        quality_scores = {
            ReferenceQuality.LOSSLESS: 100,
            ReferenceQuality.HIGH_BITRATE: 85,
            ReferenceQuality.MEDIUM_BITRATE: 65,
            ReferenceQuality.LOW_BITRATE: 40,
            ReferenceQuality.UNKNOWN: 50
        }
        
        # Absolute score
        result.quality_score_absolute = quality_scores.get(test_quality_enum, 50)
        
        # Relative score (compared to best available)
        if best_ref_quality != ReferenceQuality.UNKNOWN:
            best_score = quality_scores.get(best_ref_quality, 50)
            test_score = quality_scores.get(test_quality_enum, 50)
            result.quality_score_relative = (test_score / best_score) * 100
        else:
            result.quality_score_relative = result.quality_score_absolute
        
        # Check if upgrade available
        quality_order = [
            ReferenceQuality.LOW_BITRATE,
            ReferenceQuality.MEDIUM_BITRATE,
            ReferenceQuality.HIGH_BITRATE,
            ReferenceQuality.LOSSLESS
        ]
        
        if test_quality_enum in quality_order and best_ref_quality in quality_order:
            test_idx = quality_order.index(test_quality_enum)
            ref_idx = quality_order.index(best_ref_quality)
            result.upgrade_available = ref_idx > test_idx
            result.is_best_available = ref_idx <= test_idx
        
        # Comparison details
        result.comparison_details = {
            'test_quality': test_quality_enum.value,
            'test_bitrate': test_quality.get('bitrate', 0) // 1000 if test_quality.get('bitrate') else None,
            'best_reference_quality': best_ref_quality.value,
            'best_reference_format': result.best_reference.format,
            'total_references_found': len(references),
            'quality_distribution': self._get_quality_distribution(references)
        }
        
        return result
    
    def _get_quality_distribution(self, references: List[ReferenceVersion]) -> Dict[str, int]:
        """Get distribution of quality levels in references"""
        distribution = {}
        for ref in references:
            quality = ref.quality.value
            distribution[quality] = distribution.get(quality, 0) + 1
        return distribution
    
    def _generate_recommendations(self, result: ReferenceComparisonResult,
                                test_quality: Dict[str, Any]):
        """Generate specific recommendations based on comparison"""
        if not result.best_reference:
            result.recommendations.append(
                "No reference versions found for comparison"
            )
            return
        
        # Upgrade available
        if result.upgrade_available:
            result.recommendations.append(
                f"Better quality available: {result.best_reference.quality.value} "
                f"({result.best_reference.format}) - "
                f"{result.best_reference.album} ({result.best_reference.release_date})"
            )
            
            if result.best_reference.label:
                result.recommendations.append(
                    f"Consider getting the {result.best_reference.label} release"
                )
        
        # Already best quality
        elif result.is_best_available:
            result.recommendations.append(
                "This appears to be the best available quality"
            )
        
        # Specific format recommendations
        test_quality_enum = test_quality.get('quality', ReferenceQuality.UNKNOWN)
        
        if test_quality_enum == ReferenceQuality.LOW_BITRATE:
            result.recommendations.append(
                "Low bitrate detected. This file is not suitable for DJ use"
            )
        elif test_quality_enum == ReferenceQuality.MEDIUM_BITRATE:
            result.recommendations.append(
                "Medium bitrate may be acceptable for casual use but not ideal for DJ performance"
            )
        
        # Check for common issues
        if test_quality.get('estimated_bitrate'):
            est_bitrate = test_quality['estimated_bitrate']
            claimed_bitrate = test_quality.get('bitrate', 0) // 1000
            
            if claimed_bitrate > 0 and est_bitrate < claimed_bitrate * 0.8:
                result.recommendations.append(
                    f"File may be upsampled: estimated {est_bitrate:.0f}kbps vs claimed {claimed_bitrate}kbps"
                )
    
    def _get_cached_references(self, acoustid: str) -> Optional[List[ReferenceVersion]]:
        """Get cached reference versions"""
        try:
            with sqlite3.connect(self.cache_db) as conn:
                cursor = conn.execute(
                    "SELECT references, expires_at FROM reference_cache WHERE acoustid = ?",
                    (acoustid,)
                )
                row = cursor.fetchone()
                
                if row and row[1] > time.time():
                    references_json = json.loads(row[0])
                    references = []
                    
                    for ref_data in references_json:
                        ref = ReferenceVersion(**ref_data)
                        references.append(ref)
                    
                    return references
                    
        except Exception as e:
            self.logger.debug(f"Cache read error: {e}")
        
        return None
    
    def _cache_references(self, acoustid: str, references: List[ReferenceVersion]):
        """Cache reference versions"""
        try:
            # Convert references to JSON-serializable format
            references_data = []
            for ref in references:
                ref_dict = {
                    'recording_id': ref.recording_id,
                    'release_id': ref.release_id,
                    'title': ref.title,
                    'artist': ref.artist,
                    'album': ref.album,
                    'format': ref.format,
                    'quality': ref.quality.value,
                    'bitrate': ref.bitrate,
                    'duration': ref.duration,
                    'release_date': ref.release_date,
                    'release_country': ref.release_country,
                    'label': ref.label,
                    'catalog_number': ref.catalog_number,
                    'confidence_score': ref.confidence_score,
                    'source': ref.source,
                    'additional_data': ref.additional_data
                }
                references_data.append(ref_dict)
            
            expires_at = time.time() + (7 * 24 * 60 * 60)  # 7 days
            
            with sqlite3.connect(self.cache_db) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO reference_cache VALUES (?, ?, ?, ?, ?)",
                    (
                        acoustid,
                        '',  # recording_data not used currently
                        json.dumps(references_data),
                        time.time(),
                        expires_at
                    )
                )
                
        except Exception as e:
            self.logger.error(f"Cache write error: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get checker statistics"""
        return {
            **self.stats,
            'cache_hit_rate': (
                self.stats['cache_hits'] / self.stats['lookups_performed'] * 100
                if self.stats['lookups_performed'] > 0 else 0
            ),
            'upgrade_detection_rate': (
                self.stats['upgrades_detected'] / self.stats['lookups_performed'] * 100
                if self.stats['lookups_performed'] > 0 else 0
            ),
            'acoustid_available': ACOUSTID_AVAILABLE,
            'musicbrainz_available': MUSICBRAINZ_AVAILABLE,
            'requests_available': REQUESTS_AVAILABLE
        }