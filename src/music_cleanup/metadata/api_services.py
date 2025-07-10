"""
API Services for Metadata Lookup

Implements AcoustID and MusicBrainz API clients with rate limiting,
error handling, and result validation.
"""

import logging
import time
import requests
from typing import Dict, Optional, Any, List
from urllib.parse import urlencode
import json

from ..utils.decorators import handle_errors, retry, track_performance


class RateLimiter:
    """Simple rate limiter for API calls"""
    
    def __init__(self, max_requests: int = 10, time_window: int = 60):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = []
    
    def wait_if_needed(self) -> None:
        """Wait if rate limit would be exceeded"""
        now = time.time()
        
        # Remove old requests
        self.requests = [req_time for req_time in self.requests 
                        if now - req_time < self.time_window]
        
        # Wait if at limit
        if len(self.requests) >= self.max_requests:
            wait_time = self.time_window - (now - self.requests[0]) + 0.1
            if wait_time > 0:
                time.sleep(wait_time)
        
        self.requests.append(now)


class AcoustIDService:
    """
    AcoustID API client for audio fingerprint lookup.
    
    Features:
    - Fingerprint-based music identification
    - Rate limiting and retry logic
    - Confidence scoring
    - MusicBrainz recording ID retrieval
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize AcoustID service.
        
        Args:
            config: AcoustID configuration with api_key
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        self.api_key = config.get('api_key', '')
        self.enabled = config.get('enabled', True) and bool(self.api_key)
        self.base_url = 'https://api.acoustid.org/v2'
        
        # Rate limiting: 3 requests per second
        self.rate_limiter = RateLimiter(max_requests=3, time_window=1)
        
        # Request settings
        self.timeout = config.get('timeout', 10)
        self.max_results = config.get('max_results', 5)
        
        if not self.enabled:
            self.logger.warning("AcoustID service disabled (no API key)")
        else:
            self.logger.info("AcoustID service initialized")
    
    @handle_errors(return_on_error=None)
    @track_performance(threshold_ms=5000)
    @retry(max_attempts=3, delay=2.0)
    def lookup_fingerprint(self, fingerprint: str, duration: Optional[float] = None) -> Optional[Dict]:
        """
        Look up metadata by audio fingerprint.
        
        Args:
            fingerprint: Chromaprint fingerprint
            duration: Audio duration in seconds (optional)
            
        Returns:
            Dict with artist, title, confidence, recording_id or None
        """
        if not self.enabled:
            return None
        
        try:
            # Rate limiting
            self.rate_limiter.wait_if_needed()
            
            # Prepare request
            params = {
                'client': self.api_key,
                'format': 'json',
                'fingerprint': fingerprint,
                'meta': 'recordings+releasegroups+compress'
            }
            
            if duration:
                params['duration'] = int(duration)
            
            # Make request
            response = requests.get(
                f"{self.base_url}/lookup",
                params=params,
                timeout=self.timeout,
                headers={'User-Agent': 'DJ-Music-Cleanup/2.0'}
            )
            
            response.raise_for_status()
            data = response.json()
            
            # Check for API errors
            if data.get('status') != 'ok':
                self.logger.warning(f"AcoustID API error: {data.get('error', 'Unknown error')}")
                return None
            
            # Parse results
            results = data.get('results', [])
            if not results:
                self.logger.debug("No AcoustID results found")
                return None
            
            # Find best result
            best_result = self._find_best_result(results)
            if not best_result:
                self.logger.debug("No suitable AcoustID result found")
                return None
            
            self.logger.debug(f"AcoustID lookup successful: {best_result.get('artist')} - {best_result.get('title')}")
            return best_result
            
        except requests.RequestException as e:
            self.logger.error(f"AcoustID API request failed: {e}")
            return None
        except json.JSONDecodeError as e:
            self.logger.error(f"AcoustID JSON decode error: {e}")
            return None
        except Exception as e:
            self.logger.error(f"AcoustID lookup error: {e}")
            return None
    
    def _find_best_result(self, results: List[Dict]) -> Optional[Dict]:
        """
        Find the best result from AcoustID results.
        
        Args:
            results: List of AcoustID result objects
            
        Returns:
            Best result dict or None
        """
        best_result = None
        best_score = 0.0
        
        for result in results[:self.max_results]:
            score = result.get('score', 0.0)
            recordings = result.get('recordings', [])
            
            if not recordings or score < 0.5:
                continue
            
            # Find best recording
            for recording in recordings:
                # Check if recording has required metadata
                title = recording.get('title')
                artists = recording.get('artists', [])
                
                if not title or not artists:
                    continue
                
                artist_name = artists[0].get('name', '') if artists else ''
                if not artist_name:
                    continue
                
                # Calculate combined score
                recording_score = score * 0.8  # Base score from fingerprint match
                
                # Bonus for complete metadata
                if recording.get('duration'):
                    recording_score += 0.1
                
                releasegroups = recording.get('releasegroups', [])
                if releasegroups:
                    recording_score += 0.1
                    
                    # Try to get year from first release group
                    first_release = releasegroups[0]
                    if first_release.get('releases'):
                        recording_score += 0.05
                
                if recording_score > best_score:
                    best_score = recording_score
                    
                    # Extract year from release groups
                    year = None
                    if releasegroups:
                        for rg in releasegroups:
                            for release in rg.get('releases', []):
                                date = release.get('date')
                                if date and len(date) >= 4:
                                    try:
                                        year = int(date[:4])
                                        break
                                    except ValueError:
                                        continue
                            if year:
                                break
                    
                    best_result = {
                        'artist': artist_name,
                        'title': title,
                        'year': year,
                        'confidence': recording_score,
                        'recording_id': recording.get('id'),
                        'duration': recording.get('duration'),
                        'raw_result': result  # Keep original for debugging
                    }
        
        return best_result


class MusicBrainzService:
    """
    MusicBrainz API client for detailed metadata lookup.
    
    Features:
    - Recording metadata retrieval
    - Release group information
    - Genre and style information
    - Rate limiting compliance
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize MusicBrainz service.
        
        Args:
            config: MusicBrainz configuration
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        self.enabled = config.get('enabled', True)
        self.app_name = config.get('app_name', 'DJ-Music-Cleanup/2.0')
        self.contact = config.get('contact', 'support@example.com')
        self.base_url = 'https://musicbrainz.org/ws/2'
        
        # Rate limiting: 1 request per second (MusicBrainz requirement)
        self.rate_limiter = RateLimiter(max_requests=1, time_window=1)
        
        # Request settings
        self.timeout = config.get('timeout', 15)
        
        if not self.enabled:
            self.logger.warning("MusicBrainz service disabled")
        else:
            self.logger.info("MusicBrainz service initialized")
    
    @handle_errors(return_on_error=None)
    @track_performance(threshold_ms=10000)
    @retry(max_attempts=2, delay=3.0)
    def get_recording(self, recording_id: str) -> Optional[Dict]:
        """
        Get detailed recording information from MusicBrainz.
        
        Args:
            recording_id: MusicBrainz recording ID
            
        Returns:
            Dict with detailed metadata or None
        """
        if not self.enabled or not recording_id:
            return None
        
        try:
            # Rate limiting
            self.rate_limiter.wait_if_needed()
            
            # Prepare request
            params = {
                'fmt': 'json',
                'inc': 'releases+release-groups+genres+tags+artist-credits'
            }
            
            headers = {
                'User-Agent': f"{self.app_name} ( {self.contact} )",
                'Accept': 'application/json'
            }
            
            # Make request
            response = requests.get(
                f"{self.base_url}/recording/{recording_id}",
                params=params,
                headers=headers,
                timeout=self.timeout
            )
            
            response.raise_for_status()
            data = response.json()
            
            # Extract metadata
            result = self._extract_recording_metadata(data)
            
            if result:
                self.logger.debug(f"MusicBrainz lookup successful for recording: {recording_id}")
            
            return result
            
        except requests.RequestException as e:
            self.logger.error(f"MusicBrainz API request failed: {e}")
            return None
        except json.JSONDecodeError as e:
            self.logger.error(f"MusicBrainz JSON decode error: {e}")
            return None
        except Exception as e:
            self.logger.error(f"MusicBrainz lookup error: {e}")
            return None
    
    def _extract_recording_metadata(self, data: Dict) -> Optional[Dict]:
        """
        Extract useful metadata from MusicBrainz recording data.
        
        Args:
            data: MusicBrainz recording response
            
        Returns:
            Extracted metadata dict
        """
        try:
            result = {}
            
            # Genre from genres or tags
            genres = data.get('genres', [])
            if genres:
                result['genre'] = genres[0].get('name')
            else:
                # Try tags as fallback
                tags = data.get('tags', [])
                genre_tags = [tag for tag in tags if tag.get('count', 0) > 5]
                if genre_tags:
                    result['genre'] = genre_tags[0].get('name')
            
            # Album from releases
            releases = data.get('releases', [])
            if releases:
                # Use the first release group title as album
                first_release = releases[0]
                release_group = first_release.get('release-group', {})
                if release_group.get('title'):
                    result['album'] = release_group['title']
                
                # Try to get year from release date
                date = first_release.get('date')
                if date and len(date) >= 4:
                    try:
                        result['year'] = int(date[:4])
                    except ValueError:
                        pass
            
            # Additional metadata
            if data.get('length'):
                result['duration'] = data['length'] / 1000.0  # Convert ms to seconds
            
            # Disambiguation
            if data.get('disambiguation'):
                result['disambiguation'] = data['disambiguation']
            
            return result if result else None
            
        except Exception as e:
            self.logger.error(f"MusicBrainz metadata extraction error: {e}")
            return None