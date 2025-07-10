"""
Unified Quality Scoring System

Kombiniert alle Qualitäts-Checks zu einem einheitlichen Score
und bietet Funktionen für Datei-Umbenennung und Metadaten-Tagging.
"""

import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import json

try:
    import mutagen
    from mutagen.mp3 import MP3
    from mutagen.flac import FLAC
    from mutagen.id3 import ID3, TXXX, TIT2, TPE1
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False

from .advanced_quality_analyzer import AudioQualityReport
from .defect_detection import AudioHealthReport
from .reference_quality_checker import ReferenceComparisonResult


class ScoringProfile(Enum):
    """Vordefinierte Scoring-Profile für verschiedene Anwendungsfälle"""
    DJ_PROFESSIONAL = "dj_professional"  # Streng für professionelle DJs
    DJ_CASUAL = "dj_casual"  # Moderater für Hobby-DJs
    ARCHIVAL = "archival"  # Fokus auf Erhaltung
    STREAMING = "streaming"  # Optimiert für Streaming
    CUSTOM = "custom"  # Benutzerdefiniert


@dataclass
class QualityScoreComponents:
    """Einzelne Komponenten des Qualitäts-Scores"""
    # Technische Qualität (0-100)
    bitrate_score: float = 0.0
    format_score: float = 0.0
    frequency_score: float = 0.0
    dynamic_range_score: float = 0.0
    
    # Gesundheit (0-100)
    health_score: float = 0.0
    defect_penalty: float = 0.0
    
    # Reference-basiert (0-100)
    reference_score: float = 0.0
    upgrade_penalty: float = 0.0
    
    # Audio-Analyse (0-100)
    spectral_score: float = 0.0
    clipping_penalty: float = 0.0
    noise_penalty: float = 0.0
    
    # Weights für finale Berechnung
    weights: Dict[str, float] = field(default_factory=dict)


@dataclass
class UnifiedQualityScore:
    """Einheitlicher Qualitäts-Score mit allen Details"""
    final_score: float  # 0-100
    grade: str  # A+, A, B+, B, C, D, F
    components: QualityScoreComponents
    
    # Kategorien
    technical_quality: float  # Format, Bitrate, etc.
    audio_fidelity: float  # Spectral, Dynamic Range, etc.
    file_integrity: float  # Health, Defects
    reference_quality: float  # Comparison to best version
    
    # Zusätzliche Infos
    confidence: float  # Wie sicher sind wir bei diesem Score
    issues_summary: List[str] = field(default_factory=list)
    strengths: List[str] = field(default_factory=list)
    
    # Empfohlene Aktionen
    recommended_action: str = ""
    is_keeper: bool = True
    needs_replacement: bool = False


class QualityScoringSystem:
    """
    Unified Quality Scoring System
    
    Kombiniert alle Qualitäts-Checks zu einem gewichteten Score:
    - Technical Quality (Bitrate, Format, Encoding)
    - Audio Fidelity (Dynamic Range, Frequency Response)
    - File Integrity (Defects, Corruption)
    - Reference Quality (Compared to best known version)
    """
    
    # Scoring-Profile mit unterschiedlichen Gewichtungen
    SCORING_PROFILES = {
        ScoringProfile.DJ_PROFESSIONAL: {
            'technical_quality': 0.25,
            'audio_fidelity': 0.25,
            'file_integrity': 0.15,
            'reference_quality': 0.35,  # Deutlich höher gewichtet
            # Component weights
            'bitrate': 0.20,
            'format': 0.15,
            'frequency': 0.15,
            'dynamic_range': 0.20,
            'health': 0.15,
            'reference': 0.15
        },
        ScoringProfile.DJ_CASUAL: {
            'technical_quality': 0.30,
            'audio_fidelity': 0.25,
            'file_integrity': 0.20,
            'reference_quality': 0.25,  # Höher gewichtet
            # Component weights
            'bitrate': 0.25,
            'format': 0.20,
            'frequency': 0.10,
            'dynamic_range': 0.15,
            'health': 0.15,
            'reference': 0.15
        },
        ScoringProfile.ARCHIVAL: {
            'technical_quality': 0.35,
            'audio_fidelity': 0.20,
            'file_integrity': 0.25,
            'reference_quality': 0.20,  # Moderat höher gewichtet
            # Component weights
            'bitrate': 0.15,
            'format': 0.30,
            'frequency': 0.10,
            'dynamic_range': 0.10,
            'health': 0.20,
            'reference': 0.15
        }
    }
    
    # Grade-Schwellwerte
    GRADE_THRESHOLDS = {
        'A+': 95,
        'A': 90,
        'A-': 85,
        'B+': 80,
        'B': 75,
        'B-': 70,
        'C+': 65,
        'C': 60,
        'C-': 55,
        'D': 50,
        'F': 0
    }
    
    def __init__(self, 
                 profile: ScoringProfile = ScoringProfile.DJ_PROFESSIONAL,
                 custom_weights: Dict[str, float] = None):
        """
        Initialize the scoring system.
        
        Args:
            profile: Scoring-Profil zu verwenden
            custom_weights: Benutzerdefinierte Gewichtungen
        """
        self.profile = profile
        self.logger = logging.getLogger(__name__)
        
        # Load weights
        if profile == ScoringProfile.CUSTOM and custom_weights:
            self.weights = custom_weights
        else:
            self.weights = self.SCORING_PROFILES.get(
                profile, 
                self.SCORING_PROFILES[ScoringProfile.DJ_PROFESSIONAL]
            )
    
    def calculate_unified_score(self,
                              quality_report: AudioQualityReport,
                              health_report: AudioHealthReport) -> UnifiedQualityScore:
        """
        Berechnet einheitlichen Quality Score aus allen Analysen.
        
        Args:
            quality_report: Ergebnis der Qualitätsanalyse
            health_report: Ergebnis der Gesundheitsanalyse
            
        Returns:
            UnifiedQualityScore mit detaillierter Bewertung
        """
        components = QualityScoreComponents(weights=self.weights)
        
        # 1. Technical Quality Components
        components.bitrate_score = self._calculate_bitrate_score(quality_report)
        components.format_score = self._calculate_format_score(quality_report)
        components.frequency_score = self._calculate_frequency_score(quality_report)
        
        # 2. Audio Fidelity Components
        components.dynamic_range_score = self._calculate_dynamic_range_score(quality_report)
        components.spectral_score = self._calculate_spectral_score(quality_report)
        components.clipping_penalty = self._calculate_clipping_penalty(quality_report)
        components.noise_penalty = self._calculate_noise_penalty(quality_report)
        
        # 3. File Integrity Components
        components.health_score = health_report.health_score
        components.defect_penalty = self._calculate_defect_penalty(health_report)
        
        # 4. Reference Quality Components
        if quality_report.reference_comparison:
            components.reference_score = quality_report.reference_comparison.quality_score_relative
            components.upgrade_penalty = self._calculate_upgrade_penalty(quality_report)
        else:
            components.reference_score = 75.0  # Neutral wenn keine Referenz
        
        # Calculate category scores
        technical_quality = self._weighted_average([
            (components.bitrate_score, 0.35),
            (components.format_score, 0.35),
            (components.frequency_score, 0.30)
        ])
        
        audio_fidelity = self._weighted_average([
            (components.dynamic_range_score, 0.35),
            (components.spectral_score, 0.25),
            (100 - components.clipping_penalty, 0.25),
            (100 - components.noise_penalty, 0.15)
        ])
        
        file_integrity = self._weighted_average([
            (components.health_score, 0.70),
            (100 - components.defect_penalty, 0.30)
        ])
        
        reference_quality = self._weighted_average([
            (components.reference_score, 0.80),
            (100 - components.upgrade_penalty, 0.20)
        ])
        
        # Calculate final score
        final_score = self._weighted_average([
            (technical_quality, self.weights['technical_quality']),
            (audio_fidelity, self.weights['audio_fidelity']),
            (file_integrity, self.weights['file_integrity']),
            (reference_quality, self.weights['reference_quality'])
        ])
        
        # Determine grade
        grade = self._calculate_grade(final_score)
        
        # Calculate confidence
        confidence = self._calculate_confidence(quality_report, health_report)
        
        # Generate summaries
        issues_summary = self._generate_issues_summary(
            quality_report, health_report, components
        )
        strengths = self._generate_strengths_summary(
            quality_report, health_report, components
        )
        
        # Determine action
        recommended_action = self._determine_action(
            final_score, grade, quality_report, health_report
        )
        
        # Create unified score
        unified_score = UnifiedQualityScore(
            final_score=final_score,
            grade=grade,
            components=components,
            technical_quality=technical_quality,
            audio_fidelity=audio_fidelity,
            file_integrity=file_integrity,
            reference_quality=reference_quality,
            confidence=confidence,
            issues_summary=issues_summary,
            strengths=strengths,
            recommended_action=recommended_action,
            is_keeper=final_score >= 70 and health_report.is_healthy,
            needs_replacement=final_score < 60 or quality_report.upgrade_available
        )
        
        return unified_score
    
    def _calculate_bitrate_score(self, report: AudioQualityReport) -> float:
        """Calculate bitrate-based score"""
        bitrate = report.estimated_bitrate or 0
        format_ext = Path(report.file_path).suffix.lower()
        
        if format_ext in ['.flac', '.wav', '.aiff', '.alac']:
            return 100.0  # Lossless gets perfect score
        
        # MP3/AAC scoring
        if bitrate >= 320:
            return 100.0
        elif bitrate >= 256:
            return 90.0
        elif bitrate >= 192:
            return 75.0
        elif bitrate >= 128:
            return 50.0
        else:
            return max(0, bitrate / 128 * 50)
    
    def _calculate_format_score(self, report: AudioQualityReport) -> float:
        """Calculate format-based score"""
        format_ext = Path(report.file_path).suffix.lower()
        
        format_scores = {
            '.flac': 100,
            '.wav': 100,
            '.aiff': 100,
            '.alac': 100,
            '.ape': 95,
            '.m4a': 85,  # Usually AAC
            '.mp3': 80,
            '.ogg': 75,
            '.opus': 85,
            '.wma': 60,
            '.m4p': 40,  # DRM
        }
        
        return format_scores.get(format_ext, 50)
    
    def _calculate_frequency_score(self, report: AudioQualityReport) -> float:
        """Calculate frequency response score"""
        cutoff = report.frequency_cutoff or 22050
        
        if cutoff >= 20000:
            return 100.0
        elif cutoff >= 18000:
            return 90.0
        elif cutoff >= 16000:
            return 75.0
        elif cutoff >= 14000:
            return 60.0
        elif cutoff >= 12000:
            return 40.0
        else:
            return max(0, cutoff / 12000 * 40)
    
    def _calculate_dynamic_range_score(self, report: AudioQualityReport) -> float:
        """Calculate dynamic range score"""
        dr = report.dynamic_range
        if dr is None:
            return 75.0  # Neutral if not analyzed
        
        # DR values typically 0-1 in our system
        if dr >= 0.8:
            return 100.0
        elif dr >= 0.6:
            return 85.0
        elif dr >= 0.4:
            return 70.0
        elif dr >= 0.2:
            return 50.0
        else:
            return max(0, dr * 250)  # Very compressed
    
    def _calculate_spectral_score(self, report: AudioQualityReport) -> float:
        """Calculate spectral quality score"""
        if not report.spectral_analysis:
            return 75.0  # Neutral
        
        spectral = report.spectral_analysis
        score = 100.0
        
        # Penalize for spectral issues
        if 'high_freq_cutoff' in spectral:
            score -= 20
        if 'spectral_dullness' in spectral:
            score -= 15
        
        return max(0, score)
    
    def _calculate_clipping_penalty(self, report: AudioQualityReport) -> float:
        """Calculate clipping penalty"""
        if not report.dynamics_analysis:
            return 0.0
        
        clipping_ratio = report.dynamics_analysis.get('clipping_ratio', 0)
        
        if clipping_ratio > 0.05:  # >5%
            return 50.0
        elif clipping_ratio > 0.01:  # >1%
            return 30.0
        elif clipping_ratio > 0.001:  # >0.1%
            return 15.0
        else:
            return 0.0
    
    def _calculate_noise_penalty(self, report: AudioQualityReport) -> float:
        """Calculate noise penalty"""
        # Check for noise issues in quality issues
        for issue in report.issues:
            if 'noise' in issue.description.lower():
                return min(30, issue.severity * 0.5)
        return 0.0
    
    def _calculate_defect_penalty(self, report: AudioHealthReport) -> float:
        """Calculate defect penalty"""
        if not report.defects:
            return 0.0
        
        total_penalty = 0.0
        for defect in report.defects:
            # Critical defects
            if defect.severity >= 80:
                total_penalty += 30
            elif defect.severity >= 60:
                total_penalty += 20
            elif defect.severity >= 40:
                total_penalty += 10
            else:
                total_penalty += 5
        
        return min(100, total_penalty)
    
    def _calculate_upgrade_penalty(self, report: AudioQualityReport) -> float:
        """Calculate penalty for available upgrades"""
        if not report.reference_comparison or not report.upgrade_available:
            return 0.0
        
        ref = report.reference_comparison
        # Bigger penalty if much better version exists
        quality_diff = 100 - ref.quality_score_relative
        
        if quality_diff > 50:
            return 30.0
        elif quality_diff > 30:
            return 20.0
        elif quality_diff > 15:
            return 10.0
        else:
            return 5.0
    
    def _weighted_average(self, values: List[Tuple[float, float]]) -> float:
        """Calculate weighted average"""
        total_weight = sum(weight for _, weight in values)
        if total_weight == 0:
            return 0.0
        
        weighted_sum = sum(value * weight for value, weight in values)
        return weighted_sum / total_weight
    
    def _calculate_grade(self, score: float) -> str:
        """Calculate letter grade from score"""
        for grade, threshold in self.GRADE_THRESHOLDS.items():
            if score >= threshold:
                return grade
        return 'F'
    
    def _calculate_confidence(self, quality_report: AudioQualityReport, 
                            health_report: AudioHealthReport) -> float:
        """Calculate confidence in the score"""
        confidence = 100.0
        
        # Reduce confidence for missing analyses
        if not quality_report.spectral_analysis:
            confidence -= 10
        if not quality_report.dynamics_analysis:
            confidence -= 10
        if not quality_report.reference_comparison:
            confidence -= 15
        if not health_report.metadata_accessible:
            confidence -= 20
        
        return max(0, confidence)
    
    def _generate_issues_summary(self, quality_report: AudioQualityReport,
                               health_report: AudioHealthReport,
                               components: QualityScoreComponents) -> List[str]:
        """Generate summary of main issues"""
        issues = []
        
        # Low scores
        if components.bitrate_score < 70:
            issues.append(f"Low bitrate: {quality_report.estimated_bitrate}kbps")
        if components.frequency_score < 70:
            issues.append(f"Limited frequency range: {quality_report.frequency_cutoff:.0f}Hz")
        if components.dynamic_range_score < 60:
            issues.append("Over-compressed (loudness war)")
        if components.health_score < 70:
            issues.append(f"File integrity issues: {len(health_report.defects)} defects")
        
        # Specific problems
        if quality_report.upgrade_available:
            issues.append("Better quality version available")
        if components.clipping_penalty > 20:
            issues.append("Significant clipping detected")
        
        return issues
    
    def _generate_strengths_summary(self, quality_report: AudioQualityReport,
                                  health_report: AudioHealthReport,
                                  components: QualityScoreComponents) -> List[str]:
        """Generate summary of strengths"""
        strengths = []
        
        if components.format_score >= 90:
            strengths.append("High-quality format")
        if components.bitrate_score >= 90:
            strengths.append("Excellent bitrate")
        if components.frequency_score >= 90:
            strengths.append("Full frequency spectrum")
        if components.dynamic_range_score >= 80:
            strengths.append("Good dynamic range")
        if components.health_score >= 95:
            strengths.append("Perfect file integrity")
        if quality_report.is_best_version:
            strengths.append("Best available version")
        
        return strengths
    
    def _determine_action(self, score: float, grade: str,
                        quality_report: AudioQualityReport,
                        health_report: AudioHealthReport) -> str:
        """Determine recommended action"""
        if score >= 90 and health_report.is_healthy:
            return "Keep - Excellent quality"
        elif score >= 75 and health_report.is_healthy:
            return "Keep - Good quality"
        elif score >= 60 and health_report.is_healthy:
            if quality_report.upgrade_available:
                return "Keep but consider upgrading"
            return "Keep - Acceptable quality"
        elif health_report.health_score < 50:
            return "Replace - File integrity issues"
        elif quality_report.upgrade_available and score < 70:
            return "Replace - Better version available"
        elif score < 50:
            return "Replace - Poor quality"
        else:
            return "Review manually"


class QualityFileManager:
    """
    Manages file operations based on quality scores.
    Handles renaming and metadata tagging.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def rename_with_quality_score(self, 
                                file_path: str,
                                unified_score: UnifiedQualityScore,
                                pattern: str = "{title} - {artist} [QS{score}%]") -> str:
        """
        Rename file with quality score.
        
        Args:
            file_path: Original file path
            unified_score: Calculated quality score
            pattern: Naming pattern with placeholders
            
        Returns:
            New file path
        """
        try:
            path = Path(file_path)
            
            # Extract metadata for naming
            title, artist = self._extract_title_artist(file_path)
            
            # Format score
            score_str = f"{unified_score.final_score:.0f}"
            grade = unified_score.grade
            
            # Replace placeholders
            new_name = pattern.format(
                title=title or "Unknown Title",
                artist=artist or "Unknown Artist",
                score=score_str,
                grade=grade,
                original=path.stem
            )
            
            # Clean filename
            new_name = self._clean_filename(new_name)
            
            # Add extension
            new_path = path.parent / f"{new_name}{path.suffix}"
            
            # Handle duplicates
            counter = 1
            while new_path.exists() and new_path != path:
                new_path = path.parent / f"{new_name} ({counter}){path.suffix}"
                counter += 1
            
            # Rename if different
            if new_path != path:
                path.rename(new_path)
                self.logger.info(f"Renamed: {path.name} -> {new_path.name}")
                return str(new_path)
            
            return file_path
            
        except Exception as e:
            self.logger.error(f"Failed to rename {file_path}: {e}")
            return file_path
    
    def tag_with_quality_score(self,
                             file_path: str,
                             unified_score: UnifiedQualityScore,
                             quality_report: AudioQualityReport = None,
                             health_report: AudioHealthReport = None) -> bool:
        """
        Add quality score to file metadata.
        
        Args:
            file_path: File to tag
            unified_score: Quality score to add
            quality_report: Optional quality analysis details
            health_report: Optional health analysis details
            
        Returns:
            Success status
        """
        if not MUTAGEN_AVAILABLE:
            self.logger.warning("mutagen not available for tagging")
            return False
        
        try:
            audio = mutagen.File(file_path)
            if not audio:
                return False
            
            # Create quality metadata - alle Scores in Prozent
            quality_data = {
                'DJ_QUALITY_SCORE': f"{unified_score.final_score:.1f}%",
                'DJ_QUALITY_GRADE': unified_score.grade,
                'DJ_QUALITY_TECH': f"{unified_score.technical_quality:.1f}%",
                'DJ_QUALITY_AUDIO': f"{unified_score.audio_fidelity:.1f}%",
                'DJ_QUALITY_INTEGRITY': f"{unified_score.file_integrity:.1f}%",
                'DJ_QUALITY_REFERENCE': f"{unified_score.reference_quality:.1f}%",
                'DJ_QUALITY_ACTION': unified_score.recommended_action,
                'DJ_QUALITY_CONFIDENCE': f"{unified_score.confidence:.1f}%",
                'DJ_QUALITY_ANALYZED': json.dumps({
                    'timestamp': os.path.getmtime(file_path),
                    'is_keeper': unified_score.is_keeper,
                    'needs_replacement': unified_score.needs_replacement,
                    'issues_count': len(unified_score.issues_summary),
                    'strengths_count': len(unified_score.strengths)
                })
            }
            
            # Add reference info if available
            if quality_report and quality_report.reference_comparison:
                ref = quality_report.reference_comparison
                if ref.best_reference:
                    quality_data['DJ_REFERENCE_BEST'] = json.dumps({
                        'artist': ref.best_reference.artist,
                        'album': ref.best_reference.album,
                        'format': ref.best_reference.format,
                        'quality': ref.best_reference.quality.value
                    })
            
            # Tag based on format
            if MUTAGEN_AVAILABLE:
                from mutagen.mp3 import MP3
                from mutagen.flac import FLAC
                
                if isinstance(audio, MP3):
                    self._tag_mp3(audio, quality_data)
                elif isinstance(audio, FLAC):
                    self._tag_flac(audio, quality_data)
                else:
                    # Generic tagging
                    for key, value in quality_data.items():
                        audio[key] = value
            else:
                # Generic tagging without mutagen
                for key, value in quality_data.items():
                    audio[key] = value
            
            audio.save()
            self.logger.info(f"Tagged {Path(file_path).name} with quality score: {unified_score.final_score:.1f}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to tag {file_path}: {e}")
            return False
    
    def _extract_title_artist(self, file_path: str) -> Tuple[str, str]:
        """Extract title and artist from metadata or filename"""
        title, artist = None, None
        
        if MUTAGEN_AVAILABLE:
            try:
                audio = mutagen.File(file_path)
                if audio:
                    title = str(audio.get('title', [''])[0]) if 'title' in audio else None
                    artist = str(audio.get('artist', [''])[0]) if 'artist' in audio else None
            except:
                pass
        
        # Fallback to filename parsing
        if not title or not artist:
            filename = Path(file_path).stem
            # Try common patterns
            patterns = [
                r'^(.+?)\s*-\s*(.+?)$',  # Artist - Title
                r'^(.+?)\s*–\s*(.+?)$',  # Artist – Title (em dash)
                r'^(.+?)\s*_\s*(.+?)$',  # Artist _ Title
            ]
            
            for pattern in patterns:
                match = re.match(pattern, filename)
                if match:
                    artist = artist or match.group(1).strip()
                    title = title or match.group(2).strip()
                    break
            
            # Last resort
            if not title:
                title = filename
        
        return title, artist
    
    def _clean_filename(self, name: str) -> str:
        """Clean filename for filesystem compatibility"""
        # Remove invalid characters
        invalid_chars = '<>:"|?*'
        for char in invalid_chars:
            name = name.replace(char, '')
        
        # Replace multiple spaces
        name = re.sub(r'\s+', ' ', name)
        
        # Trim
        name = name.strip()
        
        # Limit length
        if len(name) > 200:
            name = name[:200]
        
        return name
    
    def _tag_mp3(self, audio: Any, quality_data: Dict[str, str]):
        """Tag MP3 file with ID3"""
        if hasattr(audio, 'tags'):
            if audio.tags is None:
                audio.add_tags()
            
            for key, value in quality_data.items():
                # Use TXXX frame for custom tags
                if MUTAGEN_AVAILABLE:
                    from mutagen.id3 import TXXX
                    audio.tags.add(TXXX(encoding=3, desc=key, text=value))
    
    def _tag_flac(self, audio: Any, quality_data: Dict[str, str]):
        """Tag FLAC file with Vorbis comments"""
        for key, value in quality_data.items():
            audio[key] = value
    
    def organize_by_quality(self, 
                          files: List[Tuple[str, UnifiedQualityScore]],
                          base_dir: str,
                          structure: str = "quality") -> Dict[str, List[str]]:
        """
        Organize files into directories based on quality.
        
        Args:
            files: List of (file_path, score) tuples
            base_dir: Base directory for organization
            structure: Organization structure ('quality', 'grade', 'action')
            
        Returns:
            Mapping of directories to moved files
        """
        organized = {}
        base_path = Path(base_dir)
        
        for file_path, score in files:
            # Determine target directory
            if structure == "quality":
                if score.final_score >= 90:
                    subdir = "Premium Quality (90+)"
                elif score.final_score >= 75:
                    subdir = "Good Quality (75-89)"
                elif score.final_score >= 60:
                    subdir = "Acceptable Quality (60-74)"
                else:
                    subdir = "Low Quality (Below 60)"
            elif structure == "grade":
                subdir = f"Grade {score.grade}"
            elif structure == "action":
                if score.is_keeper:
                    subdir = "Keep"
                elif score.needs_replacement:
                    subdir = "Replace"
                else:
                    subdir = "Review"
            else:
                subdir = "Unsorted"
            
            # Create directory
            target_dir = base_path / subdir
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # Move file
            try:
                source = Path(file_path)
                target = target_dir / source.name
                
                # Handle duplicates
                if target.exists():
                    counter = 1
                    while target.exists():
                        target = target_dir / f"{source.stem}_{counter}{source.suffix}"
                        counter += 1
                
                shutil.move(str(source), str(target))
                
                if subdir not in organized:
                    organized[subdir] = []
                organized[subdir].append(str(target))
                
            except Exception as e:
                self.logger.error(f"Failed to organize {file_path}: {e}")
        
        return organized