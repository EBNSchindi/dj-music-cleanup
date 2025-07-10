"""
Advanced Audio Quality Analyzer

Erweiterte Audio-Qualitätsanalyse für DJ-Music-Cleanup.
Analysiert echte Audio-Content-Qualität ohne zusätzliche Dependencies.
"""

import logging
import os
import struct
import wave
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import json
import math

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    from scipy import signal, fft
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

try:
    import mutagen
    from mutagen.mp3 import MP3
    from mutagen.flac import FLAC
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False

try:
    from .reference_quality_checker import (
        ReferenceQualityChecker,
        ReferenceComparisonResult,
        ReferenceVersion
    )
    REFERENCE_CHECK_AVAILABLE = True
except ImportError:
    REFERENCE_CHECK_AVAILABLE = False


class QualityIssueType(Enum):
    """Arten von Audio-Qualitätsproblemen"""
    LOW_BITRATE = "low_bitrate"
    UPSAMPLED = "upsampled"
    OVER_COMPRESSED = "over_compressed"
    CLIPPING = "clipping"
    EXCESSIVE_NOISE = "excessive_noise"
    FREQUENCY_CUTOFF = "frequency_cutoff"
    MONO_FAKE_STEREO = "mono_fake_stereo"
    DYNAMIC_RANGE_LOSS = "dynamic_range_loss"
    SPECTRAL_HOLES = "spectral_holes"
    ENCODING_ARTIFACTS = "encoding_artifacts"


@dataclass
class QualityIssue:
    """Repräsentiert ein erkanntes Qualitätsproblem"""
    issue_type: QualityIssueType
    severity: float  # 0-100 (100 = schwerwiegend)
    description: str
    details: Optional[Dict[str, Any]] = None
    recommendation: Optional[str] = None


@dataclass
class AudioQualityReport:
    """Umfassender Audio-Qualitätsbericht"""
    file_path: str
    quality_score: float  # 0-100 (100 = perfekt)
    is_high_quality: bool
    issues: List[QualityIssue]
    
    # Technische Details
    estimated_bitrate: Optional[int] = None
    frequency_cutoff: Optional[float] = None
    dynamic_range: Optional[float] = None
    spectral_centroid: Optional[float] = None
    stereo_correlation: Optional[float] = None
    
    # Erweiterte Analysen
    spectral_analysis: Optional[Dict[str, Any]] = None
    dynamics_analysis: Optional[Dict[str, Any]] = None
    encoding_analysis: Optional[Dict[str, Any]] = None
    
    # Reference-basierte Analyse
    reference_comparison: Optional['ReferenceComparisonResult'] = None
    upgrade_available: bool = False
    is_best_version: bool = False


class AdvancedQualityAnalyzer:
    """
    Erweiterte Audio-Qualitätsanalyse für DJ-Nutzung.
    
    Erkennt:
    1. Upsampled Low-Quality (128kbps → 320kbps)
    2. Überkomprimierte Tracks (Loudness War)
    3. Frequenz-Cutoffs (typisch für niedrige Bitraten)
    4. Fake-Stereo (Mono als Stereo)
    5. Encoding-Artefakte
    6. Dynamik-Verlust
    """
    
    # Qualitäts-Schwellwerte für DJ-Nutzung
    QUALITY_THRESHOLDS = {
        'excellent': {'min_score': 90, 'freq_cutoff': 20000, 'dynamic_range': 0.8},
        'good': {'min_score': 75, 'freq_cutoff': 16000, 'dynamic_range': 0.6},
        'acceptable': {'min_score': 60, 'freq_cutoff': 14000, 'dynamic_range': 0.4},
        'poor': {'min_score': 40, 'freq_cutoff': 12000, 'dynamic_range': 0.2}
    }
    
    def __init__(self,
                 min_quality_score: float = 60.0,
                 target_sample_rate: int = 44100,
                 analysis_duration: float = 30.0,
                 enable_reference_check: bool = True,
                 reference_cache_dir: str = None):
        """
        Initialize the advanced quality analyzer.
        
        Args:
            min_quality_score: Minimum score für "high quality"
            target_sample_rate: Erwartete Sample-Rate für DJ-Nutzung
            analysis_duration: Dauer der Analyse in Sekunden
            enable_reference_check: Reference-basierte Qualitätsprüfung aktivieren
            reference_cache_dir: Verzeichnis für Reference-Cache
        """
        self.min_quality_score = min_quality_score
        self.target_sample_rate = target_sample_rate
        self.analysis_duration = analysis_duration
        self.enable_reference_check = enable_reference_check and REFERENCE_CHECK_AVAILABLE
        self.logger = logging.getLogger(__name__)
        
        # Initialize reference checker if enabled
        self.reference_checker = None
        if self.enable_reference_check:
            try:
                self.reference_checker = ReferenceQualityChecker(
                    cache_dir=reference_cache_dir
                )
                self.logger.info("Reference-based quality checking enabled")
            except Exception as e:
                self.logger.warning(f"Could not initialize reference checker: {e}")
                self.enable_reference_check = False
        
        self.stats = {
            'files_analyzed': 0,
            'high_quality_files': 0,
            'low_quality_files': 0,
            'upsampled_detected': 0,
            'over_compressed_detected': 0,
            'reference_checks_performed': 0,
            'upgrades_available': 0
        }
    
    def analyze_audio_quality(self, file_path: str) -> AudioQualityReport:
        """
        Führt umfassende Qualitätsanalyse durch.
        
        Args:
            file_path: Pfad zur Audio-Datei
            
        Returns:
            AudioQualityReport mit detaillierter Analyse
        """
        self.stats['files_analyzed'] += 1
        
        file_path_obj = Path(file_path)
        issues = []
        
        # Basis-Checks
        if not os.path.exists(file_path):
            return self._create_error_report(file_path, "File does not exist")
        
        file_size = os.path.getsize(file_path)
        format_ext = file_path_obj.suffix.lower()
        
        # Metadaten-Analyse
        metadata_info = self._analyze_metadata(file_path)
        if not metadata_info['success']:
            issues.append(QualityIssue(
                QualityIssueType.ENCODING_ARTIFACTS,
                50,
                "Cannot read audio metadata",
                recommendation="Check file integrity"
            ))
        
        # Bitrate-Analyse
        estimated_bitrate = metadata_info.get('bitrate', 0)
        if estimated_bitrate > 0:
            bitrate_issues = self._analyze_bitrate_quality(estimated_bitrate, format_ext)
            issues.extend(bitrate_issues)
        
        # Audio-Sample-Analyse (wenn möglich)
        sample_analysis = {}
        if format_ext == '.wav' and NUMPY_AVAILABLE:
            # WAV-Dateien können wir direkt analysieren
            spectral_issues, spectral_analysis = self._analyze_wav_spectral_quality(file_path)
            issues.extend(spectral_issues)
            sample_analysis['spectral'] = spectral_analysis
            
            dynamic_issues, dynamics_analysis = self._analyze_wav_dynamics(file_path)
            issues.extend(dynamic_issues)
            sample_analysis['dynamics'] = dynamics_analysis
        elif format_ext in ['.mp3', '.flac'] and metadata_info['success']:
            # Für komprimierte Formate: Metadaten-basierte Analyse
            quality_indicators = self._estimate_compressed_quality(
                file_path, metadata_info, format_ext
            )
            issues.extend(quality_indicators)
        
        # Frequenz-Cutoff-Erkennung (vereinfacht ohne librosa)
        if 'spectral' in sample_analysis:
            frequency_cutoff = sample_analysis['spectral'].get('estimated_cutoff', 22050)
        else:
            frequency_cutoff = self._estimate_frequency_cutoff_from_metadata(
                metadata_info, format_ext
            )
        
        # Upsampling-Erkennung
        if frequency_cutoff < 15000 and estimated_bitrate > 256:
            issues.append(QualityIssue(
                QualityIssueType.UPSAMPLED,
                70,
                f"Likely upsampled: High bitrate ({estimated_bitrate}kbps) but low frequency cutoff ({frequency_cutoff:.0f}Hz)",
                details={'original_quality': 'likely 128-192kbps'},
                recommendation="Find original higher quality source"
            ))
            self.stats['upsampled_detected'] += 1
        
        # Stereo-Qualität (falls analysierbar)
        stereo_correlation = sample_analysis.get('dynamics', {}).get('stereo_correlation')
        if stereo_correlation is not None and stereo_correlation > 0.98:
            issues.append(QualityIssue(
                QualityIssueType.MONO_FAKE_STEREO,
                40,
                "Fake stereo detected (mono duplicated to both channels)",
                details={'correlation': stereo_correlation},
                recommendation="Use true stereo version if available"
            ))
        
        # Qualitäts-Score berechnen
        quality_score = self._calculate_quality_score(
            issues, metadata_info, sample_analysis
        )
        is_high_quality = quality_score >= self.min_quality_score
        
        # Statistik aktualisieren
        if is_high_quality:
            self.stats['high_quality_files'] += 1
        else:
            self.stats['low_quality_files'] += 1
        
        # Report erstellen
        report = AudioQualityReport(
            file_path=file_path,
            quality_score=quality_score,
            is_high_quality=is_high_quality,
            issues=issues,
            estimated_bitrate=estimated_bitrate,
            frequency_cutoff=frequency_cutoff,
            dynamic_range=sample_analysis.get('dynamics', {}).get('dynamic_range'),
            spectral_centroid=sample_analysis.get('spectral', {}).get('spectral_centroid'),
            stereo_correlation=stereo_correlation,
            spectral_analysis=sample_analysis.get('spectral'),
            dynamics_analysis=sample_analysis.get('dynamics'),
            encoding_analysis=metadata_info
        )
        
        # Reference-basierte Qualitätsprüfung
        if self.enable_reference_check and self.reference_checker:
            try:
                # Perform reference comparison
                reference_result = self.reference_checker.check_against_references(
                    file_path,
                    duration=metadata_info.get('duration')
                )
                
                report.reference_comparison = reference_result
                report.upgrade_available = reference_result.upgrade_available
                report.is_best_version = reference_result.is_best_available
                
                self.stats['reference_checks_performed'] += 1
                if reference_result.upgrade_available:
                    self.stats['upgrades_available'] += 1
                    
                    # Add quality issue if significant upgrade available
                    if reference_result.quality_score_relative < 70:
                        issues.append(QualityIssue(
                            QualityIssueType.LOW_BITRATE,
                            60,
                            "Better quality version available",
                            details={
                                'current_quality': reference_result.comparison_details.get('test_quality'),
                                'best_available': reference_result.comparison_details.get('best_reference_quality')
                            },
                            recommendation=reference_result.recommendations[0] if reference_result.recommendations else None
                        ))
                        
                        # Adjust quality score based on reference
                        quality_score = (quality_score + reference_result.quality_score_relative) / 2
                        report.quality_score = quality_score
                        report.is_high_quality = quality_score >= self.min_quality_score
                
            except Exception as e:
                self.logger.warning(f"Reference check failed for {file_path}: {e}")
        
        if not is_high_quality:
            self.logger.debug(
                f"Low quality detected: {file_path_obj.name} "
                f"(score: {quality_score:.1f}, issues: {len(issues)})"
            )
        
        return report
    
    def _analyze_metadata(self, file_path: str) -> Dict[str, Any]:
        """Analysiert Audio-Metadaten"""
        result = {
            'success': False,
            'duration': 0,
            'bitrate': 0,
            'sample_rate': 0,
            'channels': 0
        }
        
        if not MUTAGEN_AVAILABLE:
            return result
        
        try:
            audio = mutagen.File(file_path)
            if audio and hasattr(audio, 'info'):
                result['success'] = True
                result['duration'] = getattr(audio.info, 'length', 0)
                result['bitrate'] = getattr(audio.info, 'bitrate', 0) // 1000  # to kbps
                result['sample_rate'] = getattr(audio.info, 'sample_rate', 0)
                result['channels'] = getattr(audio.info, 'channels', 0)
                
                # Format-spezifische Details
                if isinstance(audio, MP3):
                    result['format'] = 'mp3'
                    result['version'] = getattr(audio.info, 'version', 0)
                    result['layer'] = getattr(audio.info, 'layer', 0)
                elif isinstance(audio, FLAC):
                    result['format'] = 'flac'
                    result['bits_per_sample'] = getattr(audio.info, 'bits_per_sample', 0)
        except Exception as e:
            self.logger.debug(f"Metadata analysis failed: {e}")
        
        return result
    
    def _analyze_bitrate_quality(self, bitrate: int, format_ext: str) -> List[QualityIssue]:
        """Analysiert Bitrate-basierte Qualität"""
        issues = []
        
        if format_ext == '.mp3':
            if bitrate < 192:
                severity = 80 - (bitrate / 192 * 40)  # 80 at 0kbps, 40 at 192kbps
                issues.append(QualityIssue(
                    QualityIssueType.LOW_BITRATE,
                    severity,
                    f"Low MP3 bitrate for DJ use: {bitrate}kbps",
                    details={'recommended_min': 256},
                    recommendation="Use 256kbps or higher for DJ performance"
                ))
            elif bitrate < 256:
                issues.append(QualityIssue(
                    QualityIssueType.LOW_BITRATE,
                    30,
                    f"Acceptable but not ideal bitrate: {bitrate}kbps",
                    details={'recommended': 320},
                    recommendation="320kbps recommended for best quality"
                ))
        
        return issues
    
    def _analyze_wav_spectral_quality(self, file_path: str) -> Tuple[List[QualityIssue], Dict[str, Any]]:
        """Analysiert spektrale Qualität von WAV-Dateien"""
        issues = []
        analysis = {}
        
        if not NUMPY_AVAILABLE:
            return issues, analysis
        
        try:
            # WAV-Datei lesen
            with wave.open(file_path, 'rb') as wav_file:
                framerate = wav_file.getframerate()
                frames = wav_file.readframes(-1)
                sampwidth = wav_file.getsampwidth()
                channels = wav_file.getnchannels()
                
                # Zu numpy konvertieren
                if sampwidth == 2:
                    dtype = np.int16
                elif sampwidth == 4:
                    dtype = np.int32
                else:
                    return issues, analysis
                
                samples = np.frombuffer(frames, dtype=dtype)
                
                # Auf Mono reduzieren für Analyse
                if channels == 2:
                    samples = samples.reshape(-1, 2).mean(axis=1)
                
                # Normalisieren
                samples = samples / float(np.iinfo(dtype).max)
                
                # Begrenzen auf analysis_duration
                max_samples = int(self.analysis_duration * framerate)
                if len(samples) > max_samples:
                    samples = samples[:max_samples]
                
                # Spektrale Analyse
                if SCIPY_AVAILABLE:
                    # FFT für Frequenz-Analyse
                    frequencies, power_spectrum = signal.periodogram(
                        samples, framerate, scaling='spectrum'
                    )
                    
                    # Frequenz-Cutoff erkennen
                    cutoff_freq = self._detect_frequency_cutoff(frequencies, power_spectrum)
                    analysis['estimated_cutoff'] = cutoff_freq
                    
                    if cutoff_freq < 15000:
                        severity = 70 - (cutoff_freq / 15000 * 30)
                        issues.append(QualityIssue(
                            QualityIssueType.FREQUENCY_CUTOFF,
                            severity,
                            f"Frequency cutoff detected at {cutoff_freq:.0f}Hz",
                            details={'full_spectrum': 22050},
                            recommendation="May indicate low quality source or encoding"
                        ))
                    
                    # Spektrales Zentroid (Helligkeit)
                    spectral_centroid = np.sum(frequencies * power_spectrum) / np.sum(power_spectrum)
                    analysis['spectral_centroid'] = spectral_centroid
                    
                    if spectral_centroid < 2000:
                        issues.append(QualityIssue(
                            QualityIssueType.SPECTRAL_HOLES,
                            40,
                            f"Low spectral brightness: {spectral_centroid:.0f}Hz",
                            recommendation="Audio may sound dull or muffled"
                        ))
                else:
                    # Vereinfachte Analyse ohne scipy
                    # Schätze Frequenz-Content durch Zero-Crossing-Rate
                    zero_crossings = np.sum(np.diff(np.sign(samples)) != 0)
                    zcr = zero_crossings / len(samples) * framerate / 2
                    analysis['estimated_cutoff'] = min(zcr * 2, framerate / 2)
                
        except Exception as e:
            self.logger.debug(f"Spectral analysis failed: {e}")
        
        return issues, analysis
    
    def _analyze_wav_dynamics(self, file_path: str) -> Tuple[List[QualityIssue], Dict[str, Any]]:
        """Analysiert Dynamik von WAV-Dateien"""
        issues = []
        analysis = {}
        
        if not NUMPY_AVAILABLE:
            return issues, analysis
        
        try:
            with wave.open(file_path, 'rb') as wav_file:
                framerate = wav_file.getframerate()
                frames = wav_file.readframes(-1)
                sampwidth = wav_file.getsampwidth()
                channels = wav_file.getnchannels()
                
                # Zu numpy konvertieren
                if sampwidth == 2:
                    dtype = np.int16
                elif sampwidth == 4:
                    dtype = np.int32
                else:
                    return issues, analysis
                
                samples = np.frombuffer(frames, dtype=dtype)
                
                # Stereo-Analyse
                if channels == 2:
                    stereo_samples = samples.reshape(-1, 2)
                    left = stereo_samples[:, 0] / float(np.iinfo(dtype).max)
                    right = stereo_samples[:, 1] / float(np.iinfo(dtype).max)
                    
                    # Stereo-Korrelation
                    if len(left) > 0:
                        correlation = np.corrcoef(left, right)[0, 1]
                        analysis['stereo_correlation'] = correlation
                    
                    # Mono für weitere Analyse
                    samples = stereo_samples.mean(axis=1)
                
                # Normalisieren
                samples = samples / float(np.iinfo(dtype).max)
                
                # Dynamic Range Analyse
                peak = np.max(np.abs(samples))
                rms = np.sqrt(np.mean(samples**2))
                
                if rms > 0:
                    peak_to_rms = 20 * np.log10(peak / rms)
                    analysis['peak_to_rms_db'] = peak_to_rms
                    analysis['dynamic_range'] = peak_to_rms / 20  # Normalisiert auf 0-1
                    
                    if peak_to_rms < 6:
                        issues.append(QualityIssue(
                            QualityIssueType.OVER_COMPRESSED,
                            70,
                            f"Severely over-compressed: {peak_to_rms:.1f}dB peak-to-RMS",
                            details={'good_range': '10-20dB'},
                            recommendation="Track suffers from loudness war compression"
                        ))
                        self.stats['over_compressed_detected'] += 1
                    elif peak_to_rms < 10:
                        issues.append(QualityIssue(
                            QualityIssueType.DYNAMIC_RANGE_LOSS,
                            40,
                            f"Limited dynamic range: {peak_to_rms:.1f}dB",
                            recommendation="Some dynamic compression detected"
                        ))
                
                # Clipping-Erkennung
                clipping_threshold = 0.99
                clipped_samples = np.sum(np.abs(samples) > clipping_threshold)
                clipping_ratio = clipped_samples / len(samples)
                analysis['clipping_ratio'] = clipping_ratio
                
                if clipping_ratio > 0.001:  # Mehr als 0.1%
                    severity = min(80, clipping_ratio * 8000)
                    issues.append(QualityIssue(
                        QualityIssueType.CLIPPING,
                        severity,
                        f"Audio clipping detected: {clipping_ratio*100:.2f}% of samples",
                        recommendation="Reduce gain to prevent distortion"
                    ))
                
                # Rausch-Analyse (vereinfacht)
                # Schätze Noise Floor aus stillsten 5% der Samples
                sorted_abs = np.sort(np.abs(samples))
                noise_floor_idx = int(len(sorted_abs) * 0.05)
                noise_floor = np.mean(sorted_abs[:noise_floor_idx])
                
                if noise_floor > 0:
                    snr_estimate = 20 * np.log10(rms / noise_floor)
                    analysis['estimated_snr_db'] = snr_estimate
                    
                    if snr_estimate < 40:
                        issues.append(QualityIssue(
                            QualityIssueType.EXCESSIVE_NOISE,
                            50,
                            f"High noise floor detected: ~{snr_estimate:.0f}dB SNR",
                            recommendation="Audio has significant background noise"
                        ))
                
        except Exception as e:
            self.logger.debug(f"Dynamics analysis failed: {e}")
        
        return issues, analysis
    
    def _detect_frequency_cutoff(self, frequencies: Any, 
                                power_spectrum: Any) -> float:
        """Erkennt Frequenz-Cutoff im Spektrum"""
        if len(frequencies) == 0 or len(power_spectrum) == 0:
            return 22050  # Default
        
        # Normalisiere Power-Spektrum
        if np.max(power_spectrum) > 0:
            normalized_power = power_spectrum / np.max(power_spectrum)
        else:
            return 22050
        
        # Finde höchste Frequenz mit signifikanter Energie
        # Threshold: -60dB (0.001 linear)
        threshold = 0.001
        
        # Von hohen Frequenzen rückwärts suchen
        for i in range(len(frequencies) - 1, -1, -1):
            if normalized_power[i] > threshold:
                # Finde konsistenten Cutoff (nicht nur einzelne Peaks)
                # Prüfe ob Energie in der Umgebung vorhanden ist
                window_size = min(10, i)
                if i >= window_size:
                    window_avg = np.mean(normalized_power[i-window_size:i+1])
                    if window_avg > threshold * 0.5:
                        return frequencies[i]
        
        return frequencies[0]  # Fallback
    
    def _estimate_frequency_cutoff_from_metadata(self, metadata: Dict[str, Any], 
                                               format_ext: str) -> float:
        """Schätzt Frequenz-Cutoff aus Metadaten"""
        bitrate = metadata.get('bitrate', 0)
        sample_rate = metadata.get('sample_rate', 44100)
        
        # Nyquist-Frequenz
        nyquist = sample_rate / 2
        
        if format_ext == '.mp3' and bitrate > 0:
            # MP3 Cutoff-Schätzung basierend auf Bitrate
            if bitrate <= 128:
                return min(16000, nyquist)
            elif bitrate <= 192:
                return min(18000, nyquist)
            elif bitrate <= 256:
                return min(19000, nyquist)
            else:
                return min(20000, nyquist)
        
        # Für andere Formate: Konservative Schätzung
        return nyquist * 0.9
    
    def _estimate_compressed_quality(self, file_path: str, metadata: Dict[str, Any], 
                                   format_ext: str) -> List[QualityIssue]:
        """Schätzt Qualität für komprimierte Formate"""
        issues = []
        
        file_size = os.path.getsize(file_path)
        duration = metadata.get('duration', 0)
        bitrate = metadata.get('bitrate', 0)
        
        if duration > 0:
            # Tatsächliche Bitrate aus Dateigröße berechnen
            actual_bitrate = (file_size * 8) / duration / 1000  # kbps
            
            # Vergleiche mit gemeldeter Bitrate
            if bitrate > 0 and actual_bitrate < bitrate * 0.8:
                issues.append(QualityIssue(
                    QualityIssueType.ENCODING_ARTIFACTS,
                    40,
                    f"Bitrate mismatch: reported {bitrate}kbps, actual ~{actual_bitrate:.0f}kbps",
                    recommendation="File may have encoding issues"
                ))
        
        # Format-spezifische Qualitätsindikatoren
        if format_ext == '.mp3':
            # VBR vs CBR Erkennung (vereinfacht)
            if bitrate > 0 and file_size > 0:
                expected_size = (bitrate * 1000 * duration) / 8
                size_variance = abs(file_size - expected_size) / expected_size
                
                if size_variance < 0.05:  # Weniger als 5% Abweichung
                    # Wahrscheinlich CBR
                    if bitrate < 256:
                        issues.append(QualityIssue(
                            QualityIssueType.LOW_BITRATE,
                            30,
                            f"CBR {bitrate}kbps MP3",
                            recommendation="VBR or higher bitrate recommended"
                        ))
        
        return issues
    
    def _calculate_quality_score(self, issues: List[QualityIssue], 
                               metadata: Dict[str, Any],
                               sample_analysis: Dict[str, Any]) -> float:
        """Berechnet Gesamt-Qualitätsscore"""
        base_score = 100.0
        
        # Basis-Abzüge für fehlende Informationen
        if not metadata.get('success', False):
            base_score -= 10
        
        # Abzüge für Issues
        for issue in issues:
            # Gewichtung nach Issue-Typ
            if issue.issue_type in [
                QualityIssueType.UPSAMPLED, 
                QualityIssueType.OVER_COMPRESSED
            ]:
                base_score -= issue.severity * 0.7
            elif issue.issue_type in [
                QualityIssueType.LOW_BITRATE,
                QualityIssueType.FREQUENCY_CUTOFF
            ]:
                base_score -= issue.severity * 0.5
            else:
                base_score -= issue.severity * 0.3
        
        # Bonus für gute Eigenschaften
        if metadata.get('bitrate', 0) >= 320:
            base_score += 5
        
        if sample_analysis.get('dynamics', {}).get('dynamic_range', 0) > 0.7:
            base_score += 5
        
        if sample_analysis.get('spectral', {}).get('estimated_cutoff', 0) >= 20000:
            base_score += 5
        
        return max(0.0, min(100.0, base_score))
    
    def _create_error_report(self, file_path: str, error_msg: str) -> AudioQualityReport:
        """Erstellt Error-Report"""
        return AudioQualityReport(
            file_path=file_path,
            quality_score=0.0,
            is_high_quality=False,
            issues=[QualityIssue(
                QualityIssueType.ENCODING_ARTIFACTS,
                100,
                error_msg
            )]
        )
    
    def get_quality_category(self, quality_score: float) -> str:
        """Gibt Qualitätskategorie zurück"""
        for category, thresholds in self.QUALITY_THRESHOLDS.items():
            if quality_score >= thresholds['min_score']:
                return category
        return 'poor'
    
    def is_dj_ready(self, report: AudioQualityReport) -> Tuple[bool, List[str]]:
        """
        Prüft ob Track für DJ-Nutzung geeignet ist.
        
        Returns:
            Tuple[bool, List[str]]: (is_ready, list_of_reasons_if_not)
        """
        reasons = []
        
        # Qualitäts-Score Check
        if report.quality_score < 60:
            reasons.append(f"Quality score too low: {report.quality_score:.0f}/100")
        
        # Kritische Issues
        for issue in report.issues:
            if issue.issue_type == QualityIssueType.UPSAMPLED and issue.severity > 60:
                reasons.append("Track appears to be upsampled from low quality source")
            elif issue.issue_type == QualityIssueType.OVER_COMPRESSED and issue.severity > 60:
                reasons.append("Severe dynamic range compression (loudness war victim)")
            elif issue.issue_type == QualityIssueType.LOW_BITRATE and issue.severity > 50:
                reasons.append(f"Bitrate too low for professional use: {report.estimated_bitrate}kbps")
            elif issue.issue_type == QualityIssueType.CLIPPING and issue.severity > 40:
                reasons.append("Significant audio clipping detected")
        
        # Frequenz-Check
        if report.frequency_cutoff and report.frequency_cutoff < 14000:
            reasons.append(f"Limited frequency range: {report.frequency_cutoff:.0f}Hz cutoff")
        
        is_ready = len(reasons) == 0
        
        return is_ready, reasons
    
    def get_statistics(self) -> Dict[str, Any]:
        """Gibt Statistiken zurück"""
        total = self.stats['files_analyzed']
        if total == 0:
            return self.stats
        
        stats = {
            **self.stats,
            'high_quality_rate': (self.stats['high_quality_files'] / total) * 100,
            'upsampling_rate': (self.stats['upsampled_detected'] / total) * 100,
            'compression_rate': (self.stats['over_compressed_detected'] / total) * 100,
            'numpy_available': NUMPY_AVAILABLE,
            'scipy_available': SCIPY_AVAILABLE,
            'mutagen_available': MUTAGEN_AVAILABLE,
            'reference_check_available': REFERENCE_CHECK_AVAILABLE,
            'reference_check_enabled': self.enable_reference_check
        }
        
        if self.stats['reference_checks_performed'] > 0:
            stats['reference_check_rate'] = (self.stats['reference_checks_performed'] / total) * 100
            stats['upgrade_available_rate'] = (self.stats['upgrades_available'] / self.stats['reference_checks_performed']) * 100
        
        return stats