"""
Advanced audio quality analysis and error detection module
"""
import os
import logging
import struct
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from mutagen import File as MutagenFile
from mutagen.mp3 import MP3, HeaderNotFoundError
from mutagen.flac import FLAC, FLACNoHeaderError
import hashlib


class AudioQualityAnalyzer:
    """Advanced audio quality analysis and corruption detection"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Quality thresholds
        self.quality_thresholds = {
            'excellent': {'bitrate': 320, 'sample_rate': 44100},
            'good': {'bitrate': 256, 'sample_rate': 44100},
            'acceptable': {'bitrate': 192, 'sample_rate': 44100},
            'poor': {'bitrate': 128, 'sample_rate': 22050},
            'very_poor': {'bitrate': 96, 'sample_rate': 22050}
        }
        
        # Common audio problems
        self.error_patterns = {
            'truncated': 'File appears to be truncated',
            'corrupted_header': 'Audio header is corrupted',
            'invalid_bitrate': 'Invalid or suspicious bitrate',
            'sync_error': 'Audio sync frames missing',
            'metadata_corruption': 'Metadata section corrupted',
            'duration_mismatch': 'File size vs duration mismatch',
            'silence_detected': 'Significant silence periods detected',
            'clipping_detected': 'Audio clipping detected'
        }
    
    def analyze_audio_quality(self, file_path: str) -> Dict:
        """Comprehensive audio quality analysis"""
        try:
            analysis = {
                'file_path': file_path,
                'quality_score': 0,
                'quality_rating': 'unknown',
                'technical_info': {},
                'quality_factors': {},
                'issues': [],
                'recommendations': []
            }
            
            # Basic file checks
            if not self._check_file_accessibility(file_path):
                analysis['issues'].append('file_not_accessible')
                return analysis
            
            # Extract technical information
            tech_info = self._extract_technical_info(file_path)
            if not tech_info:
                analysis['issues'].append('unable_to_read_audio_info')
                return analysis
                
            analysis['technical_info'] = tech_info
            
            # Audio format specific analysis
            analysis.update(self._analyze_format_specific(file_path, tech_info))
            
            # Calculate quality score
            analysis['quality_score'] = self._calculate_quality_score(tech_info)
            analysis['quality_rating'] = self._get_quality_rating(analysis['quality_score'])
            
            # Check for audio problems
            analysis['issues'].extend(self._detect_audio_problems(file_path, tech_info))
            
            # Generate recommendations
            analysis['recommendations'] = self._generate_recommendations(tech_info, analysis['issues'])
            
            return analysis
            
        except Exception as e:
            self.logger.error(f"Error analyzing audio quality for {file_path}: {e}")
            return {
                'file_path': file_path,
                'quality_score': 0,
                'issues': ['analysis_failed'],
                'error': str(e)
            }
    
    def _check_file_accessibility(self, file_path: str) -> bool:
        """Check if file is accessible and has reasonable size"""
        try:
            if not os.path.exists(file_path):
                return False
            
            file_size = os.path.getsize(file_path)
            
            # Check for minimum file size (should be at least 50KB for real audio)
            if file_size < 50 * 1024:
                return False
                
            # Check for maximum reasonable size (500MB)
            if file_size > 500 * 1024 * 1024:
                self.logger.warning(f"Very large file detected: {file_path} ({file_size/1024/1024:.1f}MB)")
            
            return True
            
        except Exception:
            return False
    
    def _extract_technical_info(self, file_path: str) -> Optional[Dict]:
        """Extract detailed technical audio information"""
        try:
            audio = MutagenFile(file_path)
            if audio is None:
                return None
            
            info = {
                'format': self._get_format_name(audio),
                'duration': getattr(audio.info, 'length', 0),
                'bitrate': getattr(audio.info, 'bitrate', 0),
                'sample_rate': getattr(audio.info, 'sample_rate', 0),
                'channels': getattr(audio.info, 'channels', 0),
                'file_size': os.path.getsize(file_path),
                'bits_per_sample': getattr(audio.info, 'bits_per_sample', 0),
                'mode': getattr(audio.info, 'mode', 'unknown')
            }
            
            # Format-specific information
            if isinstance(audio, MP3):
                info.update(self._extract_mp3_specific_info(audio))
            elif isinstance(audio, FLAC):
                info.update(self._extract_flac_specific_info(audio))
            
            # Calculate derived metrics
            info['bitrate_per_channel'] = info['bitrate'] / max(info['channels'], 1) if info['bitrate'] else 0
            info['file_size_mb'] = info['file_size'] / (1024 * 1024)
            info['estimated_size'] = self._estimate_file_size(info)
            info['compression_ratio'] = self._calculate_compression_ratio(info)
            
            return info
            
        except Exception as e:
            self.logger.error(f"Error extracting technical info: {e}")
            return None
    
    def _get_format_name(self, audio) -> str:
        """Get human-readable format name"""
        if isinstance(audio, MP3):
            return 'MP3'
        elif isinstance(audio, FLAC):
            return 'FLAC'
        elif hasattr(audio, 'mime') and audio.mime:
            return audio.mime[0].split('/')[-1].upper()
        else:
            return 'Unknown'
    
    def _extract_mp3_specific_info(self, audio: MP3) -> Dict:
        """Extract MP3-specific technical information"""
        info = {}
        
        try:
            # MP3 version and layer
            if hasattr(audio.info, 'version'):
                info['mp3_version'] = f"MPEG {audio.info.version}"
            if hasattr(audio.info, 'layer'):
                info['mp3_layer'] = f"Layer {audio.info.layer}"
            
            # Bitrate mode (CBR/VBR)
            if hasattr(audio.info, 'bitrate_mode'):
                info['bitrate_mode'] = str(audio.info.bitrate_mode)
            
            # Frame count and estimated frames
            if hasattr(audio.info, 'length') and audio.info.length > 0:
                # Estimate frame count for validation
                frame_duration = 0.026  # ~26ms per MP3 frame
                estimated_frames = audio.info.length / frame_duration
                info['estimated_frames'] = int(estimated_frames)
            
        except Exception as e:
            self.logger.debug(f"Error extracting MP3 specific info: {e}")
        
        return info
    
    def _extract_flac_specific_info(self, audio: FLAC) -> Dict:
        """Extract FLAC-specific technical information"""
        info = {}
        
        try:
            # FLAC compression level can sometimes be determined
            if hasattr(audio.info, 'bits_per_sample'):
                info['bits_per_sample'] = audio.info.bits_per_sample
            
            # FLAC files should have lossless compression
            info['is_lossless'] = True
            
            # Calculate theoretical uncompressed size
            if all(hasattr(audio.info, attr) for attr in ['length', 'sample_rate', 'channels', 'bits_per_sample']):
                uncompressed_size = (audio.info.length * audio.info.sample_rate * 
                                   audio.info.channels * audio.info.bits_per_sample) / 8
                info['uncompressed_size'] = uncompressed_size
                
        except Exception as e:
            self.logger.debug(f"Error extracting FLAC specific info: {e}")
        
        return info
    
    def _calculate_quality_score(self, tech_info: Dict) -> int:
        """Calculate overall quality score (0-1000)"""
        score = 0
        
        # Format score (lossless formats get higher scores)
        format_scores = {
            'FLAC': 400,
            'WAV': 380,
            'MP3': 200,
            'M4A': 180,
            'OGG': 160,
            'WMA': 120
        }
        score += format_scores.get(tech_info.get('format', ''), 50)
        
        # Bitrate score
        bitrate = tech_info.get('bitrate', 0)
        if bitrate >= 320000:
            score += 300
        elif bitrate >= 256000:
            score += 250
        elif bitrate >= 192000:
            score += 200
        elif bitrate >= 128000:
            score += 150
        elif bitrate >= 96000:
            score += 100
        else:
            score += 50
        
        # Sample rate score
        sample_rate = tech_info.get('sample_rate', 0)
        if sample_rate >= 48000:
            score += 150
        elif sample_rate >= 44100:
            score += 120
        elif sample_rate >= 32000:
            score += 80
        elif sample_rate >= 22050:
            score += 50
        else:
            score += 20
        
        # Channel configuration score
        channels = tech_info.get('channels', 0)
        if channels >= 2:
            score += 100
        elif channels == 1:
            score += 50
        
        # Duration reasonableness (penalize very short or very long tracks)
        duration = tech_info.get('duration', 0)
        if 30 <= duration <= 600:  # 30 seconds to 10 minutes is normal
            score += 50
        elif 10 <= duration <= 1800:  # 10 seconds to 30 minutes is acceptable
            score += 30
        else:
            score += 10
        
        return min(score, 1000)  # Cap at 1000
    
    def _get_quality_rating(self, score: int) -> str:
        """Convert quality score to human-readable rating"""
        if score >= 850:
            return 'excellent'
        elif score >= 700:
            return 'very_good'
        elif score >= 550:
            return 'good'
        elif score >= 400:
            return 'acceptable'
        elif score >= 250:
            return 'poor'
        else:
            return 'very_poor'
    
    def _detect_audio_problems(self, file_path: str, tech_info: Dict) -> List[str]:
        """Detect various audio problems and corruption issues"""
        issues = []
        
        # Check for file corruption indicators
        issues.extend(self._check_file_corruption(file_path, tech_info))
        
        # Check for quality issues
        issues.extend(self._check_quality_issues(tech_info))
        
        # Check for metadata problems
        issues.extend(self._check_metadata_issues(file_path))
        
        return issues
    
    def _check_file_corruption(self, file_path: str, tech_info: Dict) -> List[str]:
        """Check for file corruption indicators"""
        issues = []
        
        try:
            # Check if file can be opened properly
            audio = MutagenFile(file_path)
            if audio is None:
                issues.append('corrupted_header')
                return issues
            
            # Check duration vs file size consistency
            duration = tech_info.get('duration', 0)
            file_size = tech_info.get('file_size', 0)
            bitrate = tech_info.get('bitrate', 0)
            
            if duration > 0 and bitrate > 0:
                # Estimate expected file size
                expected_size = (duration * bitrate) / 8
                size_ratio = file_size / expected_size if expected_size > 0 else 0
                
                # Allow for 20% variance in file size
                if size_ratio < 0.8:
                    issues.append('file_truncated')
                elif size_ratio > 1.5:
                    issues.append('file_bloated')
            
            # Check for zero duration (often indicates corruption)
            if duration <= 0:
                issues.append('zero_duration')
            
            # Check for suspicious bitrates
            if bitrate > 0:
                if bitrate < 32000 or bitrate > 500000:
                    issues.append('suspicious_bitrate')
            
            # Format-specific checks
            if tech_info.get('format') == 'MP3':
                issues.extend(self._check_mp3_corruption(file_path))
            elif tech_info.get('format') == 'FLAC':
                issues.extend(self._check_flac_corruption(file_path))
                
        except Exception as e:
            self.logger.debug(f"Error checking corruption: {e}")
            issues.append('corruption_check_failed')
        
        return issues
    
    def _check_mp3_corruption(self, file_path: str) -> List[str]:
        """Check MP3-specific corruption issues"""
        issues = []
        
        try:
            # Try to read MP3 headers
            with open(file_path, 'rb') as f:
                # Check for MP3 sync word at the beginning
                f.seek(0)
                header = f.read(4)
                
                # MP3 frame should start with sync word (0xFF 0xFB or similar)
                if len(header) >= 2:
                    if not (header[0] == 0xFF and (header[1] & 0xE0) == 0xE0):
                        # Check if there's an ID3 tag first
                        f.seek(0)
                        id3_header = f.read(3)
                        if id3_header != b'ID3':
                            issues.append('mp3_no_sync_word')
                
                # Check file ending (MP3 files sometimes have corruption at the end)
                f.seek(-4, 2)
                ending = f.read(4)
                # Look for unexpected padding or corruption patterns
                if ending == b'\x00\x00\x00\x00':
                    issues.append('mp3_null_padding')
                    
        except Exception as e:
            self.logger.debug(f"Error checking MP3 corruption: {e}")
            issues.append('mp3_read_error')
        
        return issues
    
    def _check_flac_corruption(self, file_path: str) -> List[str]:
        """Check FLAC-specific corruption issues"""
        issues = []
        
        try:
            # FLAC files should start with 'fLaC' signature
            with open(file_path, 'rb') as f:
                signature = f.read(4)
                if signature != b'fLaC':
                    issues.append('flac_invalid_signature')
                    
        except Exception as e:
            self.logger.debug(f"Error checking FLAC corruption: {e}")
            issues.append('flac_read_error')
        
        return issues
    
    def _check_quality_issues(self, tech_info: Dict) -> List[str]:
        """Check for audio quality issues"""
        issues = []
        
        # Very low bitrate
        bitrate = tech_info.get('bitrate', 0)
        if 0 < bitrate < 96000:
            issues.append('very_low_bitrate')
        
        # Low sample rate
        sample_rate = tech_info.get('sample_rate', 0)
        if 0 < sample_rate < 22050:
            issues.append('low_sample_rate')
        
        # Mono audio when stereo expected
        channels = tech_info.get('channels', 0)
        if channels == 1:
            issues.append('mono_audio')
        
        # Very short duration
        duration = tech_info.get('duration', 0)
        if 0 < duration < 10:
            issues.append('very_short_duration')
        
        # Extremely long duration (might be corruption)
        if duration > 3600:  # More than 1 hour
            issues.append('extremely_long_duration')
        
        return issues
    
    def _check_metadata_issues(self, file_path: str) -> List[str]:
        """Check for metadata-related issues"""
        issues = []
        
        try:
            audio = MutagenFile(file_path)
            
            # No metadata at all
            if not audio.tags:
                issues.append('no_metadata')
            else:
                # Check for corrupted metadata
                try:
                    # Try to access common tags
                    title = audio.tags.get('title') or audio.tags.get('TIT2')
                    artist = audio.tags.get('artist') or audio.tags.get('TPE1')
                    
                    # Check for suspicious characters that might indicate corruption
                    for tag_value in [title, artist]:
                        if tag_value and isinstance(tag_value, (list, tuple)):
                            tag_value = str(tag_value[0]) if tag_value else ''
                        if tag_value and isinstance(tag_value, str):
                            # Check for null bytes or other suspicious characters
                            if '\x00' in tag_value or len(tag_value.strip()) == 0:
                                issues.append('corrupted_metadata')
                                break
                                
                except Exception:
                    issues.append('metadata_read_error')
                    
        except Exception as e:
            self.logger.debug(f"Error checking metadata: {e}")
            issues.append('metadata_check_failed')
        
        return issues
    
    def _estimate_file_size(self, tech_info: Dict) -> int:
        """Estimate expected file size based on audio parameters"""
        duration = tech_info.get('duration', 0)
        bitrate = tech_info.get('bitrate', 0)
        
        if duration <= 0 or bitrate <= 0:
            return 0
        
        # Basic calculation: duration * bitrate / 8 (convert bits to bytes)
        estimated_size = (duration * bitrate) / 8
        
        # Add some overhead for metadata, headers, etc.
        overhead = min(estimated_size * 0.05, 1024 * 1024)  # Max 1MB overhead
        
        return int(estimated_size + overhead)
    
    def _calculate_compression_ratio(self, tech_info: Dict) -> float:
        """Calculate compression ratio for lossy formats"""
        file_size = tech_info.get('file_size', 0)
        duration = tech_info.get('duration', 0)
        sample_rate = tech_info.get('sample_rate', 0)
        channels = tech_info.get('channels', 0)
        bits_per_sample = tech_info.get('bits_per_sample', 16)  # Default to 16-bit
        
        if any(x <= 0 for x in [file_size, duration, sample_rate, channels]):
            return 0.0
        
        # Calculate uncompressed size
        uncompressed_size = duration * sample_rate * channels * (bits_per_sample / 8)
        
        if uncompressed_size <= 0:
            return 0.0
        
        return file_size / uncompressed_size
    
    def _generate_recommendations(self, tech_info: Dict, issues: List[str]) -> List[str]:
        """Generate quality improvement recommendations"""
        recommendations = []
        
        # Bitrate recommendations
        bitrate = tech_info.get('bitrate', 0)
        if bitrate < 128000:
            recommendations.append('Consider re-encoding at higher bitrate (≥192 kbps)')
        
        # Format recommendations
        format_name = tech_info.get('format', '')
        if format_name == 'WMA':
            recommendations.append('Consider converting to MP3 or FLAC for better compatibility')
        
        # Issue-specific recommendations
        if 'very_low_bitrate' in issues:
            recommendations.append('File has very low bitrate - consider finding higher quality source')
        
        if 'corrupted_header' in issues or 'mp3_no_sync_word' in issues:
            recommendations.append('File appears corrupted - re-download or re-rip recommended')
        
        if 'no_metadata' in issues:
            recommendations.append('Add metadata tags for better organization')
        
        if 'mono_audio' in issues:
            recommendations.append('Check if stereo version is available')
        
        return recommendations
    
    def compare_duplicate_quality(self, files: List[Dict]) -> Dict:
        """Compare quality between duplicate files and recommend best version"""
        if not files:
            return {}
        
        results = {
            'best_file': None,
            'quality_comparison': [],
            'recommendation_reason': []
        }
        
        # Analyze each file
        analyzed_files = []
        for file_info in files:
            file_path = file_info.get('file_path')
            if file_path:
                analysis = self.analyze_audio_quality(file_path)
                analysis.update(file_info)  # Include original file info
                analyzed_files.append(analysis)
        
        if not analyzed_files:
            return results
        
        # Sort by quality score (highest first)
        analyzed_files.sort(key=lambda x: x.get('quality_score', 0), reverse=True)
        
        best_file = analyzed_files[0]
        results['best_file'] = best_file
        results['quality_comparison'] = analyzed_files
        
        # Generate recommendation reasons
        reasons = []
        best_score = best_file.get('quality_score', 0)
        best_format = best_file.get('technical_info', {}).get('format', '')
        best_bitrate = best_file.get('technical_info', {}).get('bitrate', 0)
        
        reasons.append(f"Highest quality score: {best_score}")
        
        if best_format in ['FLAC', 'WAV']:
            reasons.append(f"Lossless format ({best_format})")
        elif best_bitrate >= 320000:
            reasons.append(f"High bitrate ({best_bitrate//1000} kbps)")
        
        if len(best_file.get('issues', [])) == 0:
            reasons.append("No quality issues detected")
        
        results['recommendation_reason'] = reasons
        
        return results