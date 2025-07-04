"""
Metadata extraction and enrichment module
"""
import os
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
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

import time


class MetadataManager:
    """Handle metadata extraction, cleaning, and enrichment"""
    
    def __init__(self, enable_musicbrainz: bool = True, mb_app_name: str = "DJ-Music-Cleanup",
                 mb_app_version: str = "1.0", mb_contact: str = None):
        """Initialize metadata manager"""
        self.logger = logging.getLogger(__name__)
        self.enable_musicbrainz = enable_musicbrainz
        
        if enable_musicbrainz and mb_contact and MUSICBRAINZ_AVAILABLE:
            musicbrainzngs.set_useragent(mb_app_name, mb_app_version, mb_contact)
            musicbrainzngs.set_rate_limit(True)  # Respect rate limits
        elif enable_musicbrainz and not MUSICBRAINZ_AVAILABLE:
            self.logger.warning("MusicBrainz requested but musicbrainzngs not available")
            self.enable_musicbrainz = False
        
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
        
        # Genre normalization map
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
    
    def extract_metadata(self, file_path: str) -> Dict[str, any]:
        """Extract metadata from audio file"""
        try:
            audio = MutagenFile(file_path)
            if audio is None:
                return self._extract_from_filename(file_path)
            
            metadata = {
                'file_path': file_path,
                'filename': os.path.basename(file_path),
                'format': audio.mime[0].split('/')[-1] if audio.mime else self._get_format_from_extension(file_path),
                'duration': audio.info.length if hasattr(audio.info, 'length') else None,
                'bitrate': getattr(audio.info, 'bitrate', None),
                'sample_rate': getattr(audio.info, 'sample_rate', None),
            }
            
            # Extract tags
            if audio.tags:
                # Try to get common tags
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
            
        except Exception as e:
            self.logger.error(f"Error extracting metadata from {file_path}: {e}")
            return self._extract_from_filename(file_path)
    
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
    
    def enrich_from_musicbrainz(self, metadata: Dict) -> Dict:
        """Enrich metadata using MusicBrainz"""
        if not self.enable_musicbrainz or not MUSICBRAINZ_AVAILABLE:
            return metadata
        
        artist = metadata.get('artist')
        title = metadata.get('title')
        
        if not artist or not title:
            return metadata
        
        try:
            # Search for recording
            results = musicbrainzngs.search_recordings(
                artist=artist,
                recording=title,
                limit=5
            )
            
            if results and results['recording-list']:
                best_match = results['recording-list'][0]
                
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
                    
                    # Try to get genre from release group
                    if 'release-group' in release:
                        rg_id = release['release-group']['id']
                        try:
                            rg_info = musicbrainzngs.get_release_group_by_id(
                                rg_id, includes=['tags']
                            )
                            if 'tag-list' in rg_info['release-group']:
                                tags = [tag['name'] for tag in rg_info['release-group']['tag-list']]
                                if tags and not metadata.get('genre'):
                                    # Use the most relevant tag as genre
                                    metadata['genre'] = self._normalize_genre(tags[0])
                        except:
                            pass
                
                metadata['musicbrainz_id'] = best_match['id']
                
                # Rate limit
                time.sleep(1)
            
        except Exception as e:
            self.logger.debug(f"MusicBrainz lookup failed for {artist} - {title}: {e}")
        
        return metadata
    
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