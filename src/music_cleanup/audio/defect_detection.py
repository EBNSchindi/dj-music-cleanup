"""
Audio Defect Detection Module

Implements comprehensive audio health analysis to detect corrupted,
truncated, or otherwise defective audio files.
"""

import logging
import os
import subprocess
import struct
import time
import wave
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

try:
    import mutagen
    from mutagen.mp3 import MP3
    from mutagen.flac import FLAC
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


class DefectType(Enum):
    """Types of audio defects that can be detected"""
    CORRUPTED_HEADER = "corrupted_header"
    TRUNCATED = "truncated"
    EXCESSIVE_SILENCE = "excessive_silence"
    COMPLETE_SILENCE = "complete_silence"
    SEVERE_CLIPPING = "severe_clipping"
    SYNC_ERRORS = "sync_errors"
    ENCODING_ERRORS = "encoding_errors"
    METADATA_CORRUPTION = "metadata_corruption"
    UNEXPECTED_END = "unexpected_end"


@dataclass
class AudioDefect:
    """Represents a detected audio defect"""
    defect_type: DefectType
    severity: float  # 0-100 (100 = most severe)
    description: str
    location: Optional[float] = None  # Time position in seconds
    details: Optional[Dict[str, Any]] = None


@dataclass
class AudioHealthReport:
    """Comprehensive audio health assessment"""
    file_path: str
    health_score: float  # 0-100 (100 = perfect health)
    is_healthy: bool
    defects: List[AudioDefect]
    analysis_duration: float
    file_readable: bool
    metadata_accessible: bool
    
    # Technical details
    duration: Optional[float]
    file_size: int
    format: str
    sample_analysis: Optional[Dict[str, Any]] = None


class AudioDefectDetector:
    """
    Comprehensive audio defect detector.
    
    Analyzes audio files for various types of defects:
    1. Corrupted headers/metadata
    2. Truncated files
    3. Excessive silence (beginning/end/complete)
    4. Severe clipping
    5. MP3 sync errors
    6. Encoding errors
    7. Unexpected file termination
    """
    
    def __init__(self, 
                 min_health_score: float = 50.0,
                 silence_threshold: float = 0.001,  # Amplitude threshold for silence
                 max_silence_start: float = 10.0,   # Max silence at start (seconds)
                 max_silence_end: float = 10.0,     # Max silence at end (seconds)
                 clipping_threshold: float = 0.98,  # Threshold for clipping detection
                 sample_duration: float = 30.0):    # Duration to sample for analysis
        """
        Initialize the audio defect detector.
        
        Args:
            min_health_score: Minimum score to consider file healthy
            silence_threshold: Amplitude below which is considered silence
            max_silence_start: Maximum acceptable silence at file start
            max_silence_end: Maximum acceptable silence at file end
            clipping_threshold: Amplitude threshold for clipping detection
            sample_duration: Duration to analyze for defects (seconds)
        """
        self.min_health_score = min_health_score
        self.silence_threshold = silence_threshold
        self.max_silence_start = max_silence_start
        self.max_silence_end = max_silence_end
        self.clipping_threshold = clipping_threshold
        self.sample_duration = sample_duration
        self.logger = logging.getLogger(__name__)
        
        self.stats = {
            'files_analyzed': 0,
            'healthy_files': 0,
            'defective_files': 0,
            'defects_found': 0,
            'quarantined_files': 0
        }
    
    def analyze_audio_health(self, file_path: str) -> AudioHealthReport:
        """
        Perform comprehensive health analysis of an audio file.
        
        Args:
            file_path: Path to audio file to analyze
            
        Returns:
            AudioHealthReport with detailed analysis results
        """
        start_time = time.time()
        self.stats['files_analyzed'] += 1
        
        file_path_obj = Path(file_path)
        defects = []
        
        # Basic file checks
        file_readable = os.path.exists(file_path) and os.access(file_path, os.R_OK)
        file_size = os.path.getsize(file_path) if file_readable else 0
        format_ext = file_path_obj.suffix.lower()
        
        if not file_readable:
            defects.append(AudioDefect(
                DefectType.CORRUPTED_HEADER,
                100,
                "File is not readable or does not exist"
            ))
        
        # Metadata accessibility check
        metadata_accessible = False
        duration = None
        
        if file_readable and MUTAGEN_AVAILABLE:
            try:
                audio_file = mutagen.File(file_path)
                if audio_file and hasattr(audio_file, 'info'):
                    metadata_accessible = True
                    duration = getattr(audio_file.info, 'length', None)
                else:
                    defects.append(AudioDefect(
                        DefectType.METADATA_CORRUPTION,
                        80,
                        "Cannot read audio metadata"
                    ))
            except Exception as e:
                defects.append(AudioDefect(
                    DefectType.METADATA_CORRUPTION,
                    90,
                    f"Metadata reading failed: {str(e)[:100]}"
                ))
        
        # Format-specific checks
        if file_readable:
            format_defects = self._check_format_specific_issues(file_path, format_ext)
            defects.extend(format_defects)
            
            # Enhanced truncation detection
            is_truncated, truncation_details = self._detect_truncation(file_path)
            if is_truncated:
                severity = 80 if 'size_mismatch' in truncation_details.get('reason', '') else 70
                defects.append(AudioDefect(
                    DefectType.TRUNCATED,
                    severity,
                    f"Enhanced truncation detected: {truncation_details.get('reason', 'Unknown')}"
                ))
        
        # Duration vs file size validation
        if duration and file_size > 0:
            duration_defects = self._check_duration_consistency(file_path, duration, file_size, format_ext)
            defects.extend(duration_defects)
        
        # Sample-based audio analysis (if possible)
        sample_analysis = None
        if file_readable and metadata_accessible:
            sample_defects, sample_analysis = self._analyze_audio_samples(file_path, format_ext)
            defects.extend(sample_defects)
        
        # Calculate health score
        health_score = self._calculate_health_score(defects, file_readable, metadata_accessible)
        is_healthy = health_score >= self.min_health_score
        
        analysis_duration = time.time() - start_time
        
        # Update statistics
        if is_healthy:
            self.stats['healthy_files'] += 1
        else:
            self.stats['defective_files'] += 1
        self.stats['defects_found'] += len(defects)
        
        report = AudioHealthReport(
            file_path=file_path,
            health_score=health_score,
            is_healthy=is_healthy,
            defects=defects,
            analysis_duration=analysis_duration,
            file_readable=file_readable,
            metadata_accessible=metadata_accessible,
            duration=duration,
            file_size=file_size,
            format=format_ext,
            sample_analysis=sample_analysis
        )
        
        if not is_healthy:
            self.logger.debug(f"Defective file detected: {file_path_obj.name} "
                            f"(score: {health_score:.1f}, defects: {len(defects)})")
        
        return report
    
    def _check_format_specific_issues(self, file_path: str, format_ext: str) -> List[AudioDefect]:
        """Check for format-specific issues"""
        defects = []
        
        if format_ext == '.mp3':
            defects.extend(self._check_mp3_issues(file_path))
        elif format_ext == '.flac':
            defects.extend(self._check_flac_issues(file_path))
        elif format_ext == '.wav':
            defects.extend(self._check_wav_issues(file_path))
        
        return defects
    
    def _check_mp3_issues(self, file_path: str) -> List[AudioDefect]:
        """Check MP3-specific issues"""
        defects = []
        
        try:
            with open(file_path, 'rb') as f:
                # Check for valid MP3 header
                header = f.read(10)
                
                # Check for ID3 tag or MP3 sync
                if not (header.startswith(b'ID3') or self._has_mp3_sync(header)):
                    defects.append(AudioDefect(
                        DefectType.CORRUPTED_HEADER,
                        70,
                        "No valid MP3 header or ID3 tag found"
                    ))
                
                # Enhanced check for abrupt termination
                defects.extend(self._check_mp3_abrupt_ending(f))
        
        except Exception as e:
            defects.append(AudioDefect(
                DefectType.ENCODING_ERRORS,
                50,
                f"Error reading MP3 structure: {str(e)[:50]}"
            ))
        
        return defects
    
    def _detect_truncation(self, file_path: str) -> Tuple[bool, Dict[str, Any]]:
        """
        Erkennt abgeschnittene Audio-Dateien mit verbesserter Analyse.
        
        Args:
            file_path: Path to the audio file to analyze
            
        Returns:
            Tuple[bool, Dict]: (is_truncated, analysis_details)
        """
        try:
            if not MUTAGEN_AVAILABLE:
                return False, {'reason': 'mutagen_not_available'}
            
            audio = mutagen.File(file_path)
            if not audio:
                return True, {'reason': 'cannot_read_file'}
                
            # Check 1: Dateigröße vs erwartete Größe
            duration = getattr(audio.info, 'length', 0)
            bitrate = getattr(audio.info, 'bitrate', 0)
            
            if duration > 0 and bitrate > 0:
                expected_size = (duration * bitrate) / 8
                actual_size = os.path.getsize(file_path)
                
                if actual_size < expected_size * 0.9:  # 10% Toleranz
                    return True, {
                        'reason': 'size_mismatch',
                        'expected': expected_size,
                        'actual': actual_size,
                        'ratio': actual_size / expected_size
                    }
            
            # Check 2: Format-spezifische Truncation-Checks
            if file_path.lower().endswith('.mp3'):
                return self._check_mp3_truncation(file_path)
            elif file_path.lower().endswith('.flac'):
                return self._check_flac_truncation(file_path)
            elif file_path.lower().endswith('.wav'):
                return self._check_wav_truncation(file_path)
            
            return False, {}
            
        except Exception as e:
            return True, {'reason': f'analysis_error: {str(e)}'}
    
    def _check_mp3_truncation(self, file_path: str) -> Tuple[bool, Dict[str, Any]]:
        """MP3-spezifische Truncation-Erkennung"""
        try:
            with open(file_path, 'rb') as f:
                file_size = os.path.getsize(file_path)
                
                # Check 1: Letzte 128 bytes analysieren
                if file_size > 128:
                    f.seek(-128, 2)
                    end_data = f.read(128)
                    
                    # Check für ID3v1 Tag (sollte am Ende sein)
                    if not end_data.startswith(b'TAG'):
                        # Kein Tag, prüfe auf verdächtige Patterns
                        if end_data == b'\x00' * 128:
                            return True, {'reason': 'null_padding_at_end'}
                        
                        # Check für abrupte Wiederholungen
                        unique_bytes = len(set(end_data))
                        if unique_bytes <= 2:
                            return True, {'reason': f'repeated_bytes_at_end: {unique_bytes} unique'}
                
                # Check 2: MP3 Frame Integrität
                f.seek(0)
                header_data = f.read(1024)
                
                # Suche nach MP3 Frame Header
                frame_found = False
                for i in range(len(header_data) - 3):
                    if header_data[i] == 0xFF and (header_data[i + 1] & 0xE0) == 0xE0:
                        frame_found = True
                        break
                
                if not frame_found:
                    return True, {'reason': 'no_valid_mp3_frames'}
                
            return False, {}
            
        except Exception as e:
            return True, {'reason': f'mp3_analysis_error: {str(e)}'}
    
    def _check_flac_truncation(self, file_path: str) -> Tuple[bool, Dict[str, Any]]:
        """FLAC-spezifische Truncation-Erkennung"""
        try:
            # Verwende flac command falls verfügbar
            result = subprocess.run(
                ['flac', '-t', '-s', file_path],
                capture_output=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return True, {'reason': f'flac_validation_failed: {result.stderr.decode()[:100]}'}
                
        except (subprocess.SubprocessError, FileNotFoundError):
            # Fallback: Basic header check
            try:
                with open(file_path, 'rb') as f:
                    header = f.read(4)
                    if not header.startswith(b'fLaC'):
                        return True, {'reason': 'invalid_flac_signature'}
            except Exception:
                return True, {'reason': 'cannot_read_flac_header'}
        
        return False, {}
    
    def _check_wav_truncation(self, file_path: str) -> Tuple[bool, Dict[str, Any]]:
        """WAV-spezifische Truncation-Erkennung"""
        try:
            with wave.open(file_path, 'rb') as wav_file:
                frames = wav_file.getnframes()
                framerate = wav_file.getframerate()
                channels = wav_file.getnchannels()
                sampwidth = wav_file.getsampwidth()
                
                if frames == 0:
                    return True, {'reason': 'no_audio_frames'}
                
                # Check Dateigröße vs erwartete Größe
                expected_size = frames * channels * sampwidth + 44  # +44 for WAV header
                actual_size = os.path.getsize(file_path)
                
                if abs(expected_size - actual_size) > 1024:  # 1KB Toleranz
                    ratio = actual_size / expected_size if expected_size > 0 else 0
                    return True, {
                        'reason': 'wav_size_mismatch',
                        'expected': expected_size,
                        'actual': actual_size,
                        'ratio': ratio
                    }
                    
        except Exception as e:
            return True, {'reason': f'wav_analysis_error: {str(e)}'}
        
        return False, {}

    def _check_mp3_abrupt_ending(self, file_handle) -> List[AudioDefect]:
        """
        Enhanced detection of abrupt MP3 file endings.
        
        Detects multiple types of truncation:
        1. Files ending with repeated bytes (classic truncation)
        2. Files ending mid-frame
        3. Files without proper ending markers
        4. Files with suspicious padding patterns
        """
        defects = []
        
        try:
            # Get file size
            file_handle.seek(0, 2)  # Seek to end
            file_size = file_handle.tell()
            
            if file_size < 128:  # File too small to analyze properly
                defects.append(AudioDefect(
                    DefectType.TRUNCATED,
                    90,
                    f"File extremely small: {file_size} bytes"
                ))
                return defects
            
            # Check different ending patterns
            
            # 1. Check last 128 bytes for ID3v1 tag
            file_handle.seek(-128, 2)
            last_128 = file_handle.read(128)
            has_id3v1 = last_128.startswith(b'TAG')
            
            # 2. Check last 32 bytes for abrupt termination (repeated bytes)
            file_handle.seek(-32, 2)
            last_32 = file_handle.read(32)
            unique_bytes = len(set(last_32))
            
            # Only flag as truncated if EXTREMELY repetitive (likely real truncation)
            if unique_bytes == 1:  # Only if ALL bytes are identical
                defects.append(AudioDefect(
                    DefectType.TRUNCATED,
                    60,  # Reduced severity
                    f"Extremely repetitive ending: only {unique_bytes} unique byte in last 32"
                ))
            
            # 3. Check for proper MP3 frame endings (RELAXED CHECK)
            if not has_id3v1 and file_size < 50000:  # Only check small files
                # Look for MP3 frame sync patterns near the end
                file_handle.seek(-256, 2)  # Check last 256 bytes
                ending_data = file_handle.read(256)
                
                # Look for MP3 sync patterns (0xFF followed by 0xE*)
                sync_found = False
                for i in range(len(ending_data) - 1):
                    if ending_data[i] == 0xFF and (ending_data[i + 1] & 0xE0) == 0xE0:
                        sync_found = True
                        break
                
                # Only flag as truncated if it's a small file without sync
                if not sync_found and file_size < 50000:  # Only small files
                    defects.append(AudioDefect(
                        DefectType.TRUNCATED,
                        40,  # Reduced severity
                        "No MP3 frame sync found in small file"
                    ))
            
            # 4. Check for suspicious padding patterns
            file_handle.seek(-64, 2)
            last_64 = file_handle.read(64)
            
            # Check for excessive padding (RELAXED - only extreme cases)
            zero_count = last_64.count(b'\x00')
            if zero_count > 60:  # More than 95% zeros (very extreme)
                defects.append(AudioDefect(
                    DefectType.TRUNCATED,
                    30,  # Very low severity
                    f"Excessive zero padding at end: {zero_count}/64 zero bytes"
                ))
            
            # Check for 0xFF padding (another truncation indicator) 
            ff_count = last_64.count(b'\xFF')
            if ff_count > 60:  # More than 95% 0xFF (very extreme)
                defects.append(AudioDefect(
                    DefectType.TRUNCATED,
                    55,
                    f"Suspicious 0xFF padding at end: {ff_count}/64 bytes"
                ))
            
            # 5. Check file size against expected duration patterns
            # If we can estimate duration from bitrate header
            self._check_mp3_size_duration_mismatch(file_handle, file_size, defects)
            
        except Exception as e:
            defects.append(AudioDefect(
                DefectType.ENCODING_ERRORS,
                40,
                f"Error analyzing MP3 ending: {str(e)[:50]}"
            ))
        
        return defects
    
    def _check_mp3_size_duration_mismatch(self, file_handle, file_size: int, defects: List[AudioDefect]):
        """
        Check if MP3 file size matches expected duration based on bitrate.
        
        This can detect truncated files where the header claims a certain duration
        but the file is too small to contain that much audio data.
        """
        try:
            # Read MP3 header to extract bitrate information
            file_handle.seek(0)
            header_data = file_handle.read(4096)  # Read first 4KB for header analysis
            
            # Look for MP3 frame header
            for i in range(len(header_data) - 3):
                if header_data[i] == 0xFF and (header_data[i + 1] & 0xE0) == 0xE0:
                    # Found sync pattern, extract frame info
                    frame_header = (header_data[i] << 24 | 
                                  header_data[i+1] << 16 | 
                                  header_data[i+2] << 8 | 
                                  header_data[i+3])
                    
                    # Extract bitrate from header (simplified)
                    bitrate_index = (frame_header >> 12) & 0x0F
                    
                    # Common MP3 bitrates (simplified lookup)
                    bitrate_table = {
                        1: 32, 2: 40, 3: 48, 4: 56, 5: 64, 6: 80, 7: 96, 
                        8: 112, 9: 128, 10: 160, 11: 192, 12: 224, 13: 256, 14: 320
                    }
                    
                    if bitrate_index in bitrate_table:
                        bitrate_kbps = bitrate_table[bitrate_index]
                        
                        # Estimate minimum file size for reasonable duration (e.g., 30 seconds)
                        min_expected_size = (bitrate_kbps * 1000 * 30) // 8  # 30 seconds minimum
                        
                        if file_size < min_expected_size:
                            severity = min(90, ((min_expected_size - file_size) / min_expected_size) * 100)
                            defects.append(AudioDefect(
                                DefectType.TRUNCATED,
                                severity,
                                f"File too small for bitrate: {file_size} bytes at {bitrate_kbps} kbps"
                            ))
                    break
                    
        except Exception:
            # Silent failure - this is an additional check, not critical
            pass
    
    def _check_flac_issues(self, file_path: str) -> List[AudioDefect]:
        """Check FLAC-specific issues using flac command if available"""
        defects = []
        
        try:
            # Try to validate FLAC file using flac command
            result = subprocess.run(
                ['flac', '-t', '-s', file_path],  # Test mode, silent
                capture_output=True,
                timeout=30
            )
            
            if result.returncode != 0:
                defects.append(AudioDefect(
                    DefectType.ENCODING_ERRORS,
                    80,
                    f"FLAC validation failed: {result.stderr.decode()[:100]}"
                ))
        
        except (subprocess.SubprocessError, FileNotFoundError):
            # flac command not available, do basic checks
            try:
                with open(file_path, 'rb') as f:
                    header = f.read(4)
                    if not header.startswith(b'fLaC'):
                        defects.append(AudioDefect(
                            DefectType.CORRUPTED_HEADER,
                            70,
                            "Invalid FLAC signature"
                        ))
            except Exception:
                pass
        
        return defects
    
    def _check_wav_issues(self, file_path: str) -> List[AudioDefect]:
        """Check WAV-specific issues"""
        defects = []
        
        try:
            with wave.open(file_path, 'rb') as wav_file:
                frames = wav_file.getnframes()
                framerate = wav_file.getframerate()
                
                if frames == 0:
                    defects.append(AudioDefect(
                        DefectType.CORRUPTED_HEADER,
                        80,
                        "WAV file contains no audio frames"
                    ))
                
                # Check if duration matches file size expectation
                channels = wav_file.getnchannels()
                sampwidth = wav_file.getsampwidth()
                expected_size = frames * channels * sampwidth + 44  # +44 for header
                actual_size = os.path.getsize(file_path)
                
                if abs(expected_size - actual_size) > 1024:  # Allow 1KB tolerance
                    severity = min(80, abs(expected_size - actual_size) / actual_size * 100)
                    defects.append(AudioDefect(
                        DefectType.TRUNCATED,
                        severity,
                        f"File size mismatch: expected ~{expected_size}, got {actual_size}"
                    ))
        
        except Exception as e:
            defects.append(AudioDefect(
                DefectType.CORRUPTED_HEADER,
                70,
                f"WAV file reading failed: {str(e)[:50]}"
            ))
        
        return defects
    
    def _check_duration_consistency(self, file_path: str, duration: float, 
                                  file_size: int, format_ext: str) -> List[AudioDefect]:
        """Check if duration is consistent with file size"""
        defects = []
        
        if duration <= 0:
            defects.append(AudioDefect(
                DefectType.CORRUPTED_HEADER,
                60,
                "Duration is zero or negative"
            ))
            return defects
        
        # Estimate expected file size based on format and duration
        if format_ext == '.flac':
            # FLAC is variable, but typically 50-70% of WAV size
            expected_min = duration * 44100 * 2 * 2 * 0.3  # 30% of WAV
            expected_max = duration * 44100 * 2 * 2 * 0.8  # 80% of WAV
        elif format_ext == '.wav':
            # WAV is uncompressed: duration * sample_rate * channels * bytes_per_sample
            expected_min = duration * 44100 * 2 * 2 * 0.9  # Allow 10% tolerance
            expected_max = duration * 44100 * 2 * 2 * 1.1
        elif format_ext == '.mp3':
            # MP3 varies by bitrate, estimate from duration
            estimated_bitrate = (file_size * 8) / duration / 1000  # kbps
            if estimated_bitrate < 64:
                defects.append(AudioDefect(
                    DefectType.TRUNCATED,
                    40,
                    f"Unusually low bitrate: {estimated_bitrate:.0f} kbps"
                ))
            return defects  # Skip further MP3 size checks
        else:
            return defects  # Skip size checks for other formats
        
        if file_size < expected_min:
            severity = min(80, (expected_min - file_size) / expected_min * 100)
            defects.append(AudioDefect(
                DefectType.TRUNCATED,
                severity,
                f"File smaller than expected for duration ({file_size} < {expected_min:.0f})"
            ))
        
        return defects
    
    def _analyze_audio_samples(self, file_path: str, format_ext: str) -> Tuple[List[AudioDefect], Optional[Dict[str, Any]]]:
        """Analyze audio samples for silence and clipping"""
        defects = []
        sample_analysis = None
        
        if not NUMPY_AVAILABLE:
            return defects, sample_analysis
        
        try:
            # Try to read audio samples (simplified approach for now)
            if format_ext == '.wav':
                samples, sample_rate = self._read_wav_samples(file_path)
            else:
                # For other formats, skip sample analysis for now
                # In a full implementation, we'd use librosa or similar
                return defects, sample_analysis
            
            if samples is not None:
                silence_defects, clipping_defects, analysis = self._analyze_samples(
                    samples, sample_rate, file_path
                )
                defects.extend(silence_defects)
                defects.extend(clipping_defects)
                sample_analysis = analysis
        
        except Exception as e:
            self.logger.debug(f"Sample analysis failed for {file_path}: {e}")
        
        return defects, sample_analysis
    
    def _read_wav_samples(self, file_path: str) -> Tuple[Optional[Any], int]:
        """Read WAV file samples"""
        try:
            with wave.open(file_path, 'rb') as wav_file:
                frames = wav_file.readframes(-1)
                sample_rate = wav_file.getframerate()
                channels = wav_file.getnchannels()
                sampwidth = wav_file.getsampwidth()
                
                # Convert to numpy array
                if sampwidth == 1:
                    dtype = np.uint8
                elif sampwidth == 2:
                    dtype = np.int16
                elif sampwidth == 4:
                    dtype = np.int32
                else:
                    return None, sample_rate
                
                samples = np.frombuffer(frames, dtype=dtype)
                
                # Convert to mono if stereo
                if channels == 2:
                    samples = samples.reshape(-1, 2).mean(axis=1)
                
                # Normalize to [-1, 1]
                if dtype == np.uint8:
                    samples = (samples - 128) / 128.0
                else:
                    samples = samples / float(np.iinfo(dtype).max)
                
                # Limit analysis to sample_duration
                max_samples = int(self.sample_duration * sample_rate)
                if len(samples) > max_samples:
                    # Take samples from beginning, middle, and end
                    third = max_samples // 3
                    samples = np.concatenate([
                        samples[:third],
                        samples[len(samples)//2:len(samples)//2 + third],
                        samples[-third:]
                    ])
                
                return samples, sample_rate
        
        except Exception:
            return None, 0
    
    def _analyze_samples(self, samples: Any, sample_rate: int, 
                        file_path: str) -> Tuple[List[AudioDefect], List[AudioDefect], Dict[str, Any]]:
        """Analyze audio samples for defects"""
        silence_defects = []
        clipping_defects = []
        
        # Calculate analysis metrics
        rms_level = np.sqrt(np.mean(samples**2))
        peak_level = np.max(np.abs(samples))
        
        # Silence analysis
        silence_mask = np.abs(samples) < self.silence_threshold
        silence_ratio = np.mean(silence_mask)
        
        if silence_ratio > 0.95:  # More than 95% silence
            silence_defects.append(AudioDefect(
                DefectType.COMPLETE_SILENCE,
                90,
                f"File is {silence_ratio*100:.1f}% silent"
            ))
        elif silence_ratio > 0.5:  # More than 50% silence
            silence_defects.append(AudioDefect(
                DefectType.EXCESSIVE_SILENCE,
                50,
                f"File contains {silence_ratio*100:.1f}% silence"
            ))
        
        # Check silence at beginning and end
        start_samples = min(int(self.max_silence_start * sample_rate), len(samples) // 4)
        end_samples = min(int(self.max_silence_end * sample_rate), len(samples) // 4)
        
        start_silence = np.all(np.abs(samples[:start_samples]) < self.silence_threshold)
        end_silence = np.all(np.abs(samples[-end_samples:]) < self.silence_threshold)
        
        if start_silence:
            silence_defects.append(AudioDefect(
                DefectType.EXCESSIVE_SILENCE,
                30,
                f"Excessive silence at file beginning (>{self.max_silence_start}s)"
            ))
        
        if end_silence:
            silence_defects.append(AudioDefect(
                DefectType.EXCESSIVE_SILENCE,
                30,
                f"Excessive silence at file end (>{self.max_silence_end}s)"
            ))
        
        # Clipping analysis
        clipped_samples = np.sum(np.abs(samples) > self.clipping_threshold)
        clipping_ratio = clipped_samples / len(samples)
        
        if clipping_ratio > 0.01:  # More than 1% clipped
            severity = min(80, clipping_ratio * 1000)  # Scale severity
            clipping_defects.append(AudioDefect(
                DefectType.SEVERE_CLIPPING,
                severity,
                f"Severe clipping detected: {clipping_ratio*100:.2f}% of samples"
            ))
        
        analysis = {
            'rms_level': float(rms_level),
            'peak_level': float(peak_level),
            'silence_ratio': float(silence_ratio),
            'clipping_ratio': float(clipping_ratio),
            'dynamic_range': float(peak_level - rms_level) if rms_level > 0 else 0,
            'samples_analyzed': len(samples)
        }
        
        return silence_defects, clipping_defects, analysis
    
    def _has_mp3_sync(self, header: bytes) -> bool:
        """Check for MP3 sync pattern in header"""
        for i in range(len(header) - 1):
            if header[i] == 0xFF and (header[i + 1] & 0xE0) == 0xE0:
                return True
        return False
    
    def _calculate_health_score(self, defects: List[AudioDefect], 
                               file_readable: bool, metadata_accessible: bool) -> float:
        """Calculate overall health score from defects"""
        if not file_readable:
            return 0.0
        
        if not metadata_accessible:
            base_score = 30.0
        else:
            base_score = 100.0
        
        # Subtract severity for each defect
        for defect in defects:
            # Weight defects differently
            if defect.defect_type in [DefectType.CORRUPTED_HEADER, DefectType.COMPLETE_SILENCE]:
                base_score -= defect.severity * 0.8  # High impact
            elif defect.defect_type in [DefectType.TRUNCATED, DefectType.ENCODING_ERRORS]:
                base_score -= defect.severity * 0.6  # Medium impact
            else:
                base_score -= defect.severity * 0.3  # Lower impact
        
        return max(0.0, base_score)
    
    def quarantine_defective_files(self, health_reports: List[AudioHealthReport],
                                  quarantine_folder: str = "Quarantine") -> Dict[str, Any]:
        """Move defective files to quarantine folder"""
        quarantine_path = Path(quarantine_folder)
        quarantine_path.mkdir(parents=True, exist_ok=True)
        
        results = {
            'quarantined': 0,
            'errors': 0,
            'space_quarantined': 0,
            'defect_summary': {}
        }
        
        for report in health_reports:
            if not report.is_healthy:
                try:
                    source_path = Path(report.file_path)
                    dest_path = quarantine_path / source_path.name
                    
                    # Handle name conflicts
                    counter = 1
                    while dest_path.exists():
                        stem = source_path.stem
                        suffix = source_path.suffix
                        dest_path = quarantine_path / f"{stem}_quarantine_{counter}{suffix}"
                        counter += 1
                    
                    # Move file
                    source_path.rename(dest_path)
                    
                    results['quarantined'] += 1
                    results['space_quarantined'] += report.file_size
                    self.stats['quarantined_files'] += 1
                    
                    # Track defect types
                    for defect in report.defects:
                        defect_type = defect.defect_type.value
                        if defect_type not in results['defect_summary']:
                            results['defect_summary'][defect_type] = 0
                        results['defect_summary'][defect_type] += 1
                    
                    self.logger.info(f"Quarantined defective file: {source_path.name}")
                
                except Exception as e:
                    self.logger.error(f"Error quarantining {report.file_path}: {e}")
                    results['errors'] += 1
        
        return results
    
    def is_critically_corrupted(self, file_info: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Prüft ob Track für DJ-Nutzung unbrauchbar ist.
        
        Args:
            file_info: Dictionary mit file_path und anderen Dateiinformationen
            
        Returns:
            Tuple[bool, List[str]]: (is_corrupted, list_of_reasons)
        """
        file_path = file_info.get('file_path')
        if not file_path:
            return True, ["No file path provided"]
        
        # Führe Gesundheitsanalyse durch
        try:
            health_report = self.analyze_audio_health(file_path)
        except Exception as e:
            return True, [f"Health analysis failed: {str(e)[:100]}"]
        
        # Kritische Korruption basiert auf mehreren Faktoren
        critical_reasons = []
        
        # 1. Datei nicht lesbar
        if not health_report.file_readable:
            critical_reasons.append("File is not readable or accessible")
        
        # 2. Metadaten nicht zugänglich
        if not health_report.metadata_accessible:
            critical_reasons.append("Audio metadata cannot be read")
        
        # 3. Gesundheitsscore zu niedrig (unter 20 für kritisch)
        if health_report.health_score < 20:
            critical_reasons.append(f"Health score too low: {health_report.health_score:.1f}/100")
        
        # 4. Kritische Defekte vorhanden
        for defect in health_report.defects:
            if defect.defect_type in [
                DefectType.CORRUPTED_HEADER,
                DefectType.COMPLETE_SILENCE,
                DefectType.METADATA_CORRUPTION
            ] and defect.severity >= 70:
                critical_reasons.append(f"{defect.defect_type.value}: {defect.description}")
            
            # Besonders schwere Truncation-Probleme
            elif defect.defect_type == DefectType.TRUNCATED and defect.severity >= 80:
                critical_reasons.append(f"Severely truncated: {defect.description}")
            
            # Schwere Encoding-Probleme
            elif defect.defect_type == DefectType.ENCODING_ERRORS and defect.severity >= 70:
                critical_reasons.append(f"Encoding errors: {defect.description}")
        
        # 5. Datei zu klein oder Dauer problematisch
        if health_report.duration is not None:
            if health_report.duration < 10:  # Weniger als 10 Sekunden
                critical_reasons.append(f"Track too short for DJ use: {health_report.duration:.1f}s")
            elif health_report.duration > 3600:  # Länger als 1 Stunde
                critical_reasons.append(f"Track unusually long: {health_report.duration:.1f}s")
        
        # 6. Datei zu klein (unter 100KB ist verdächtig)
        if health_report.file_size < 100 * 1024:
            critical_reasons.append(f"File suspiciously small: {health_report.file_size} bytes")
        
        # 7. Spezielle DJ-relevante Checks
        if health_report.sample_analysis:
            # Komplette Stille ist für DJs unbrauchbar
            silence_ratio = health_report.sample_analysis.get('silence_ratio', 0)
            if silence_ratio > 0.8:  # Mehr als 80% Stille
                critical_reasons.append(f"Track mostly silent: {silence_ratio*100:.1f}% silence")
            
            # Extreme Clipping macht Track unbrauchbar
            clipping_ratio = health_report.sample_analysis.get('clipping_ratio', 0)
            if clipping_ratio > 0.05:  # Mehr als 5% geclippt
                critical_reasons.append(f"Severe clipping detected: {clipping_ratio*100:.1f}%")
        
        is_corrupted = len(critical_reasons) > 0
        
        if is_corrupted:
            self.logger.warning(f"Critical corruption detected in {Path(file_path).name}: {critical_reasons}")
        
        return is_corrupted, critical_reasons

    def get_statistics(self) -> Dict[str, Any]:
        """Get defect detection statistics"""
        total_files = self.stats['files_analyzed']
        if total_files == 0:
            return self.stats
        
        return {
            **self.stats,
            'defect_rate': (self.stats['defective_files'] / total_files) * 100,
            'average_defects_per_file': self.stats['defects_found'] / total_files,
            'health_threshold': self.min_health_score,
            'numpy_available': NUMPY_AVAILABLE,
            'mutagen_available': MUTAGEN_AVAILABLE
        }

