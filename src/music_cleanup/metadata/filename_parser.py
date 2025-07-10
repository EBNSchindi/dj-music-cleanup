"""
Intelligent Filename Parser for DJ Music Cleanup Tool

Recognizes common DJ filename patterns and extracts metadata.
This is STEP 3 in the metadata priority - only used as last resort.
"""

import logging
import re
from typing import Dict, Optional, Any, List
from pathlib import Path

from ..utils.decorators import handle_errors


class FilenameParser:
    """
    Intelligent filename parser for DJ music files.
    
    Recognizes patterns like:
    - "BPM - Artist - Title (Remix).mp3"
    - "Artist - Title (Extended Mix) [Label].mp3"  
    - "01. Artist - Title.mp3"
    - "128 - Swedish House Mafia - Don't You Worry Child (Original Mix).mp3"
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize filename parser.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Compile regex patterns for different filename formats
        self.patterns = self._compile_patterns()
        
        # Words/phrases to clean from filenames
        self.cleanup_patterns = [
            r'^\\d+\\.\\s*',  # Leading track numbers: "01. ", "02. "
            r'_',  # Underscores to spaces
            r'\\btrack\\b',  # Word "track"
            r'\\btitel\\b',  # German "titel"
            r'\\s+',  # Multiple spaces to single space
        ]
        
        # Remix/version indicators to preserve
        self.version_indicators = [
            r'\\(.*?[Rr]emix.*?\\)',
            r'\\(.*?[Mm]ix.*?\\)',
            r'\\(.*?[Ee]dit.*?\\)',
            r'\\(.*?[Vv]ersion.*?\\)',
            r'\\[.*?\\]',  # Label information in brackets
        ]
        
        self.logger.info("FilenameParser initialized")
    
    def _compile_patterns(self) -> List[Dict[str, Any]]:
        """Compile regex patterns for different filename formats"""
        
        patterns = [
            # Pattern 1: "BPM - Artist - Title (Remix).ext"
            {
                'name': 'bpm_artist_title',
                'regex': re.compile(
                    r'^(?P<bpm>\\d{2,3})\\s*-\\s*(?P<artist>.+?)\\s*-\\s*(?P<title>.+?)(?P<version>\\s*\\([^)]*\\))?(?P<label>\\s*\\[[^\\]]*\\])?\\.[^.]+$',
                    re.IGNORECASE
                ),
                'priority': 1
            },
            
            # Pattern 2: "Artist - Title (Extended Mix) [Label].ext"
            {
                'name': 'artist_title_version',
                'regex': re.compile(
                    r'^(?P<artist>.+?)\\s*-\\s*(?P<title>.+?)(?P<version>\\s*\\([^)]*\\))?(?P<label>\\s*\\[[^\\]]*\\])?\\.[^.]+$',
                    re.IGNORECASE
                ),
                'priority': 2
            },
            
            # Pattern 3: "01. Artist - Title.ext" (with track number)
            {
                'name': 'track_artist_title',
                'regex': re.compile(
                    r'^(?P<track>\\d{1,3})\\.?\\s*(?P<artist>.+?)\\s*-\\s*(?P<title>.+?)(?P<version>\\s*\\([^)]*\\))?\\.[^.]+$',
                    re.IGNORECASE
                ),
                'priority': 3
            },
            
            # Pattern 4: "128 BPM - Artist - Title.ext"
            {
                'name': 'bpm_label_artist_title', 
                'regex': re.compile(
                    r'^(?P<bpm>\\d{2,3})\\s*(?:BPM)?\\s*-\\s*(?P<artist>.+?)\\s*-\\s*(?P<title>.+?)(?P<version>\\s*\\([^)]*\\))?\\.[^.]+$',
                    re.IGNORECASE
                ),
                'priority': 4
            },
            
            # Pattern 5: "Artist_-_Title_[Label].ext" (underscores)
            {
                'name': 'underscore_format',
                'regex': re.compile(
                    r'^(?P<artist>.+?)_-_(?P<title>.+?)(?P<label>_\\[[^\\]]*\\])?\\.[^.]+$',
                    re.IGNORECASE
                ),
                'priority': 5
            },
            
            # Pattern 6: "Artist Title (without dash).ext"
            {
                'name': 'artist_title_no_dash',
                'regex': re.compile(
                    r'^(?P<artist_title>.+?)(?P<version>\\s*\\([^)]*\\))?(?P<label>\\s*\\[[^\\]]*\\])?\\.[^.]+$',
                    re.IGNORECASE
                ),
                'priority': 6
            }
        ]
        
        return sorted(patterns, key=lambda x: x['priority'])
    
    @handle_errors(return_on_error=None)
    def parse_filename(self, filename: str) -> Optional[Dict[str, Any]]:
        """
        Parse filename to extract metadata.
        
        Args:
            filename: Audio filename to parse
            
        Returns:
            Dict with parsed metadata or None if parsing fails
        """
        # Remove file extension and clean filename
        name_without_ext = Path(filename).stem
        cleaned_name = self._clean_filename(name_without_ext)
        
        self.logger.debug(f"Parsing filename: {filename}")
        self.logger.debug(f"Cleaned name: {cleaned_name}")
        
        # Try each pattern in priority order
        for pattern_info in self.patterns:
            match = pattern_info['regex'].match(cleaned_name)
            if match:
                result = self._extract_metadata(match, pattern_info)
                if result and self._validate_result(result):
                    self.logger.debug(f"Matched pattern '{pattern_info['name']}': {result.get('artist')} - {result.get('title')}")
                    return result
        
        self.logger.warning(f"No pattern matched for: {filename}")
        return None
    
    def _clean_filename(self, filename: str) -> str:
        """
        Clean filename by removing common artifacts.
        
        Args:
            filename: Raw filename
            
        Returns:
            Cleaned filename
        """
        cleaned = filename
        
        # Apply cleanup patterns
        for pattern in self.cleanup_patterns:
            if pattern == r'_':
                # Replace underscores with spaces
                cleaned = cleaned.replace('_', ' ')
            elif pattern == r'\\s+':
                # Normalize whitespace
                cleaned = re.sub(r'\\s+', ' ', cleaned)
            else:
                # Remove other patterns
                cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        return cleaned.strip()
    
    def _extract_metadata(self, match: re.Match, pattern_info: Dict) -> Optional[Dict[str, Any]]:
        """
        Extract metadata from regex match.
        
        Args:
            match: Regex match object
            pattern_info: Pattern information
            
        Returns:
            Extracted metadata dict
        """
        try:
            groups = match.groupdict()
            result = {
                'pattern_used': pattern_info['name'],
                'confidence': self._calculate_confidence(groups, pattern_info)
            }
            
            # Extract artist and title
            if 'artist' in groups and 'title' in groups:
                result['artist'] = self._clean_field(groups['artist'])
                result['title'] = self._clean_field(groups['title'])
            elif 'artist_title' in groups:
                # Try to split artist_title field
                artist_title = self._clean_field(groups['artist_title'])
                artist, title = self._split_artist_title(artist_title)
                result['artist'] = artist
                result['title'] = title
            else:
                return None
            
            # Extract optional fields
            if 'bpm' in groups and groups['bpm']:
                try:
                    result['bpm'] = int(groups['bpm'])
                except ValueError:
                    pass
            
            if 'track' in groups and groups['track']:
                try:
                    result['track_number'] = int(groups['track'])
                except ValueError:
                    pass
            
            # Extract version/remix info
            version_parts = []
            if 'version' in groups and groups['version']:
                version_parts.append(groups['version'].strip())
            
            if 'label' in groups and groups['label']:
                version_parts.append(groups['label'].strip())
            
            if version_parts:
                result['version_info'] = ' '.join(version_parts)
                
                # Try to extract specific version type
                version_text = ' '.join(version_parts).lower()
                if 'remix' in version_text:
                    result['is_remix'] = True
                if 'extended' in version_text or 'club' in version_text:
                    result['is_extended'] = True
                if 'radio' in version_text or 'edit' in version_text:
                    result['is_edit'] = True
            
            return result
            
        except Exception as e:
            self.logger.error(f"Metadata extraction error: {e}")
            return None
    
    def _clean_field(self, field: str) -> str:
        """
        Clean individual metadata field.
        
        Args:
            field: Raw field value
            
        Returns:
            Cleaned field value
        """
        if not field:
            return ''
        
        # Remove extra whitespace
        cleaned = re.sub(r'\\s+', ' ', field.strip())
        
        # Remove common prefixes/suffixes
        prefixes_to_remove = ['feat.', 'ft.', 'vs.', 'vs', '&']
        
        # Don't remove these if they're essential parts
        # Just clean them up
        
        return cleaned
    
    def _split_artist_title(self, artist_title: str) -> tuple[str, str]:
        """
        Split combined artist_title field into separate artist and title.
        
        Args:
            artist_title: Combined artist and title string
            
        Returns:
            Tuple of (artist, title)
        """
        # Try common separators
        separators = [' - ', ' – ', ' — ', '  ', ' | ']
        
        for sep in separators:
            if sep in artist_title:
                parts = artist_title.split(sep, 1)
                if len(parts) == 2:
                    artist = parts[0].strip()
                    title = parts[1].strip()
                    
                    # Basic validation
                    if len(artist) > 0 and len(title) > 0:
                        return artist, title
        
        # If no separator found, try to guess based on length
        words = artist_title.split()
        if len(words) >= 4:
            # Assume first half is artist, second half is title
            mid = len(words) // 2
            artist = ' '.join(words[:mid])
            title = ' '.join(words[mid:])
            return artist, title
        
        # Fallback: return as title with "Unknown" artist
        return "Unknown", artist_title
    
    def _calculate_confidence(self, groups: Dict, pattern_info: Dict) -> float:
        """
        Calculate confidence score for parsed result.
        
        Args:
            groups: Regex match groups
            pattern_info: Pattern information
            
        Returns:
            Confidence score between 0.0 and 1.0
        """
        base_confidence = 0.5  # Filename parsing gets medium confidence
        
        # Bonus for having both artist and title
        if ('artist' in groups and groups['artist']) and ('title' in groups and groups['title']):
            base_confidence += 0.2
        
        # Bonus for additional metadata
        if 'bpm' in groups and groups['bpm']:
            base_confidence += 0.1
        
        if 'version' in groups and groups['version']:
            base_confidence += 0.05
        
        # Pattern priority bonus (earlier patterns are more reliable)
        priority_bonus = (10 - pattern_info['priority']) * 0.02
        base_confidence += priority_bonus
        
        return min(base_confidence, 0.9)  # Cap at 0.9 for filename parsing
    
    def _validate_result(self, result: Dict[str, Any]) -> bool:
        """
        Validate parsed result to ensure quality.
        
        Args:
            result: Parsed metadata result
            
        Returns:
            True if result is valid
        """
        # Must have artist and title
        if not result.get('artist') or not result.get('title'):
            return False
        
        # Artist and title must be reasonable length
        artist = result['artist'].strip()
        title = result['title'].strip()
        
        if len(artist) < 1 or len(title) < 1:
            return False
        
        if len(artist) > 200 or len(title) > 200:
            return False
        
        # Reject if artist or title is just numbers or common junk
        junk_patterns = [
            r'^\\d+$',  # Just numbers
            r'^[\\W_]+$',  # Just punctuation
            r'^track\\s*\\d*$',  # Just "track" or "track N"
            r'^title\\s*\\d*$',  # Just "title" or "title N"
            r'^unknown',  # Starts with "unknown"
            r'^untitled',  # Starts with "untitled"
        ]
        
        for pattern in junk_patterns:
            if re.match(pattern, artist.lower()) or re.match(pattern, title.lower()):
                return False
        
        return True
    
    def get_supported_patterns(self) -> List[str]:
        """
        Get list of supported filename patterns.
        
        Returns:
            List of pattern descriptions
        """
        return [
            "BPM - Artist - Title (Remix).mp3",
            "Artist - Title (Extended Mix) [Label].mp3", 
            "01. Artist - Title.mp3",
            "128 BPM - Artist - Title.mp3",
            "Artist_-_Title_[Label].mp3",
            "Artist Title (Version).mp3"
        ]