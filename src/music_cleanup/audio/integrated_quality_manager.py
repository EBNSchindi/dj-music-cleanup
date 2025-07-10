"""
Integrated Quality Management System

Kombiniert alle Quality-Checks mit Scoring, Tagging und File Management.
"""

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import json

from .advanced_quality_analyzer import AdvancedQualityAnalyzer
from .defect_detection import AudioDefectDetector
from .quality_scoring import (
    QualityScoringSystem, 
    QualityFileManager,
    UnifiedQualityScore,
    ScoringProfile
)


@dataclass
class QualityProcessingOptions:
    """Konfiguration für Quality Processing"""
    # Analysis options
    enable_reference_check: bool = True
    enable_spectral_analysis: bool = True
    analysis_duration: float = 30.0
    
    # Scoring options
    scoring_profile: ScoringProfile = ScoringProfile.DJ_PROFESSIONAL
    custom_weights: Optional[Dict[str, float]] = None
    
    # File operations
    rename_files: bool = True  # Standardmäßig aktiviert
    rename_pattern: str = "{title} - {artist} [QS{score}%]"  # Mit Prozent
    tag_metadata: bool = True
    backup_original_names: bool = True
    
    # Organization (deaktiviert - nur Dateinamen und Metadaten)
    organize_files: bool = False  # Keine Ordner-Organisation
    organization_structure: str = "none"  # Nicht verwendet
    output_directory: Optional[str] = None  # Nicht verwendet
    
    # Quality thresholds
    min_keeper_score: float = 70.0
    min_acceptable_score: float = 60.0
    auto_quarantine_below: float = 40.0


@dataclass
class QualityProcessingResult:
    """Ergebnis der Quality Processing"""
    file_path: str
    original_path: str
    
    # Scores and analysis
    unified_score: Optional[UnifiedQualityScore] = None
    quality_report: Any = None  # AudioQualityReport
    health_report: Any = None   # AudioHealthReport
    
    # Actions performed
    was_renamed: bool = False
    was_tagged: bool = False
    was_organized: bool = False
    was_quarantined: bool = False
    
    # New paths
    final_path: str = ""
    backup_info: Optional[Dict[str, str]] = None
    
    # Processing info
    processing_time: float = 0.0
    success: bool = True
    error_message: Optional[str] = None


class IntegratedQualityManager:
    """
    Integrated Quality Management System
    
    Kombiniert alle Quality-Analysen mit Scoring, File-Management
    und Organization in einem einheitlichen Workflow.
    """
    
    def __init__(self, options: QualityProcessingOptions = None):
        """
        Initialize the integrated quality manager.
        
        Args:
            options: Processing options, uses defaults if None
        """
        self.options = options or QualityProcessingOptions()
        self.logger = logging.getLogger(__name__)
        
        # Initialize components
        self.quality_analyzer = AdvancedQualityAnalyzer(
            enable_reference_check=self.options.enable_reference_check,
            analysis_duration=self.options.analysis_duration
        )
        
        self.defect_detector = AudioDefectDetector()
        
        self.scoring_system = QualityScoringSystem(
            profile=self.options.scoring_profile,
            custom_weights=self.options.custom_weights
        )
        
        self.file_manager = QualityFileManager()
        
        # Statistics
        self.stats = {
            'files_processed': 0,
            'files_renamed': 0,
            'files_tagged': 0,
            'files_organized': 0,
            'files_quarantined': 0,
            'average_score': 0.0,
            'grade_distribution': {},
            'actions_distribution': {}
        }
    
    def process_file(self, file_path: str) -> QualityProcessingResult:
        """
        Process single file through complete quality pipeline.
        
        Args:
            file_path: Path to audio file
            
        Returns:
            Complete processing result
        """
        import time
        start_time = time.time()
        
        result = QualityProcessingResult(
            file_path=file_path,
            original_path=file_path,
            final_path=file_path
        )
        
        try:
            # 1. Quality Analysis
            self.logger.info(f"Analyzing quality: {Path(file_path).name}")
            result.quality_report = self.quality_analyzer.analyze_audio_quality(file_path)
            
            # 2. Health Analysis
            self.logger.debug(f"Analyzing health: {Path(file_path).name}")
            result.health_report = self.defect_detector.analyze_audio_health(file_path)
            
            # 3. Unified Scoring
            self.logger.debug(f"Calculating unified score: {Path(file_path).name}")
            result.unified_score = self.scoring_system.calculate_unified_score(
                result.quality_report,
                result.health_report
            )
            
            # 4. File Operations
            current_path = file_path
            
            # Quarantine if very low quality
            if result.unified_score.final_score < self.options.auto_quarantine_below:
                quarantine_path = self._quarantine_file(current_path)
                if quarantine_path:
                    result.was_quarantined = True
                    result.final_path = quarantine_path
                    current_path = quarantine_path
                    self.logger.warning(f"Quarantined low quality file: {Path(file_path).name}")
            
            # Tag with metadata
            if self.options.tag_metadata and not result.was_quarantined:
                if self.file_manager.tag_with_quality_score(
                    current_path, 
                    result.unified_score,
                    result.quality_report,
                    result.health_report
                ):
                    result.was_tagged = True
            
            # Rename file
            if self.options.rename_files and not result.was_quarantined:
                if self.options.backup_original_names:
                    result.backup_info = self._backup_original_name(current_path)
                
                new_path = self.file_manager.rename_with_quality_score(
                    current_path,
                    result.unified_score,
                    self.options.rename_pattern
                )
                
                if new_path != current_path:
                    result.was_renamed = True
                    result.final_path = new_path
                    current_path = new_path
            
            # Organization deaktiviert - nur Dateinamen und Metadaten
            # Keine Ordner-Organisation mehr
            
            # Update statistics
            self._update_statistics(result)
            
            result.processing_time = time.time() - start_time
            self.logger.info(
                f"Processed {Path(file_path).name}: "
                f"Score {result.unified_score.final_score:.1f} "
                f"(Grade {result.unified_score.grade})"
            )
            
        except Exception as e:
            result.success = False
            result.error_message = str(e)
            result.processing_time = time.time() - start_time
            self.logger.error(f"Failed to process {file_path}: {e}")
        
        return result
    
    def process_directory(self, 
                        directory: str,
                        recursive: bool = True,
                        extensions: List[str] = None) -> List[QualityProcessingResult]:
        """
        Process all audio files in directory.
        
        Args:
            directory: Directory to process
            recursive: Search subdirectories
            extensions: File extensions to process
            
        Returns:
            List of processing results
        """
        if extensions is None:
            extensions = ['.mp3', '.flac', '.wav', '.m4a', '.aiff', '.ogg']
        
        # Find audio files
        path = Path(directory)
        audio_files = []
        
        if recursive:
            for ext in extensions:
                audio_files.extend(path.rglob(f'*{ext}'))
        else:
            for ext in extensions:
                audio_files.extend(path.glob(f'*{ext}'))
        
        self.logger.info(f"Found {len(audio_files)} audio files to process")
        
        # Process files
        results = []
        for i, audio_file in enumerate(audio_files, 1):
            self.logger.info(f"Processing {i}/{len(audio_files)}: {audio_file.name}")
            result = self.process_file(str(audio_file))
            results.append(result)
        
        # Summary
        self._log_processing_summary(results)
        
        return results
    
    def batch_organize(self, 
                      results: List[QualityProcessingResult],
                      output_dir: str = None) -> Dict[str, List[str]]:
        """
        Batch-Organisation deaktiviert.
        Verwendet nur Dateinamen und Metadaten für Quality-Info.
        
        Args:
            results: Processing results (für Kompatibilität)
            output_dir: Nicht verwendet
            
        Returns:
            Leeres Dictionary (keine Organisation)
        """
        self.logger.info("Batch-Organisation deaktiviert - Quality-Info nur in Dateinamen und Metadaten")
        return {}
    
    def generate_quality_report(self, 
                              results: List[QualityProcessingResult],
                              output_file: str = None) -> Dict[str, Any]:
        """
        Generate comprehensive quality report.
        
        Args:
            results: Processing results
            output_file: Optional file to save JSON report
            
        Returns:
            Quality report data
        """
        successful_results = [r for r in results if r.success]
        
        if not successful_results:
            return {'error': 'No successful results to analyze'}
        
        # Calculate statistics
        scores = [r.unified_score.final_score for r in successful_results]
        grades = [r.unified_score.grade for r in successful_results]
        actions = [r.unified_score.recommended_action for r in successful_results]
        
        # Grade distribution
        grade_dist = {}
        for grade in grades:
            grade_dist[grade] = grade_dist.get(grade, 0) + 1
        
        # Action distribution
        action_dist = {}
        for action in actions:
            action_dist[action] = action_dist.get(action, 0) + 1
        
        # Quality bands
        excellent = len([s for s in scores if s >= 90])
        good = len([s for s in scores if 75 <= s < 90])
        acceptable = len([s for s in scores if 60 <= s < 75])
        poor = len([s for s in scores if s < 60])
        
        # Issues analysis
        common_issues = {}
        for result in successful_results:
            for issue in result.unified_score.issues_summary:
                common_issues[issue] = common_issues.get(issue, 0) + 1
        
        # File operations summary
        operations = {
            'renamed': len([r for r in results if r.was_renamed]),
            'tagged': len([r for r in results if r.was_tagged]),
            'organized': len([r for r in results if r.was_organized]),
            'quarantined': len([r for r in results if r.was_quarantined])
        }
        
        report = {
            'summary': {
                'total_files': len(results),
                'successful_analyses': len(successful_results),
                'failed_analyses': len(results) - len(successful_results),
                'average_score': sum(scores) / len(scores),
                'median_score': sorted(scores)[len(scores) // 2],
                'min_score': min(scores),
                'max_score': max(scores)
            },
            'quality_distribution': {
                'excellent_90_plus': excellent,
                'good_75_89': good,
                'acceptable_60_74': acceptable,
                'poor_below_60': poor
            },
            'grade_distribution': grade_dist,
            'action_distribution': action_dist,
            'common_issues': dict(sorted(common_issues.items(), key=lambda x: x[1], reverse=True)[:10]),
            'file_operations': operations,
            'recommendations': self._generate_collection_recommendations(successful_results),
            'detailed_results': [
                {
                    'file': result.original_path,
                    'final_path': result.final_path,
                    'score': result.unified_score.final_score,
                    'grade': result.unified_score.grade,
                    'action': result.unified_score.recommended_action,
                    'issues': result.unified_score.issues_summary,
                    'processing_time': result.processing_time
                }
                for result in successful_results
            ]
        }
        
        # Save to file if requested
        if output_file:
            with open(output_file, 'w') as f:
                json.dump(report, f, indent=2)
            self.logger.info(f"Quality report saved to: {output_file}")
        
        return report
    
    def _quarantine_file(self, file_path: str) -> Optional[str]:
        """Move file to quarantine directory"""
        try:
            quarantine_dir = Path(file_path).parent / "Quarantine_Low_Quality"
            quarantine_dir.mkdir(exist_ok=True)
            
            source = Path(file_path)
            target = quarantine_dir / source.name
            
            # Handle duplicates
            counter = 1
            while target.exists():
                target = quarantine_dir / f"{source.stem}_quarantine_{counter}{source.suffix}"
                counter += 1
            
            source.rename(target)
            return str(target)
            
        except Exception as e:
            self.logger.error(f"Failed to quarantine {file_path}: {e}")
            return None
    
    def _backup_original_name(self, file_path: str) -> Dict[str, str]:
        """Backup original filename information"""
        path = Path(file_path)
        return {
            'original_name': path.name,
            'original_stem': path.stem,
            'backup_timestamp': str(os.path.getmtime(file_path))
        }
    
    def _organize_single_file(self, 
                            file_path: str, 
                            score: UnifiedQualityScore) -> Optional[str]:
        """Organize single file"""
        try:
            organized = self.file_manager.organize_by_quality(
                [(file_path, score)],
                self.options.output_directory,
                self.options.organization_structure
            )
            
            # Find new path
            for folder_files in organized.values():
                if folder_files:
                    return folder_files[0]
            
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to organize {file_path}: {e}")
            return None
    
    def _update_statistics(self, result: QualityProcessingResult):
        """Update processing statistics"""
        self.stats['files_processed'] += 1
        
        if result.success:
            if result.was_renamed:
                self.stats['files_renamed'] += 1
            if result.was_tagged:
                self.stats['files_tagged'] += 1
            if result.was_organized:
                self.stats['files_organized'] += 1
            if result.was_quarantined:
                self.stats['files_quarantined'] += 1
            
            # Update score average
            current_avg = self.stats['average_score']
            current_count = self.stats['files_processed']
            new_score = result.unified_score.final_score
            self.stats['average_score'] = ((current_avg * (current_count - 1)) + new_score) / current_count
            
            # Grade distribution
            grade = result.unified_score.grade
            if grade not in self.stats['grade_distribution']:
                self.stats['grade_distribution'][grade] = 0
            self.stats['grade_distribution'][grade] += 1
            
            # Action distribution
            action = result.unified_score.recommended_action
            if action not in self.stats['actions_distribution']:
                self.stats['actions_distribution'][action] = 0
            self.stats['actions_distribution'][action] += 1
    
    def _log_processing_summary(self, results: List[QualityProcessingResult]):
        """Log processing summary"""
        successful = len([r for r in results if r.success])
        failed = len(results) - successful
        
        if successful > 0:
            avg_score = sum(r.unified_score.final_score for r in results if r.success) / successful
            
            self.logger.info(f"Processing complete: {successful} successful, {failed} failed")
            self.logger.info(f"Average quality score: {avg_score:.1f}")
            self.logger.info(f"Files renamed: {self.stats['files_renamed']}")
            self.logger.info(f"Files tagged: {self.stats['files_tagged']}")
            self.logger.info(f"Files quarantined: {self.stats['files_quarantined']}")
    
    def _generate_collection_recommendations(self, 
                                           results: List[QualityProcessingResult]) -> List[str]:
        """Generate recommendations for the entire collection"""
        recommendations = []
        
        scores = [r.unified_score.final_score for r in results]
        avg_score = sum(scores) / len(scores)
        
        poor_quality_count = len([s for s in scores if s < 60])
        excellent_count = len([s for s in scores if s >= 90])
        
        # Collection-level recommendations
        if avg_score < 70:
            recommendations.append("Consider upgrading your music collection - many files have quality issues")
        
        if poor_quality_count > len(results) * 0.3:
            recommendations.append(f"{poor_quality_count} files have poor quality and should be replaced")
        
        if excellent_count < len(results) * 0.2:
            recommendations.append("Consider investing in higher quality sources for better DJ performance")
        
        # Common issues
        all_issues = []
        for result in results:
            all_issues.extend(result.unified_score.issues_summary)
        
        if all_issues.count("Low bitrate") > len(results) * 0.5:
            recommendations.append("Many files have low bitrates - consider 320kbps MP3 or lossless formats")
        
        if all_issues.count("Better quality version available") > len(results) * 0.3:
            recommendations.append("Many tracks have better versions available - check MusicBrainz references")
        
        return recommendations
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get processing statistics"""
        return {
            **self.stats,
            'quality_analyzer_stats': self.quality_analyzer.get_statistics(),
            'defect_detector_stats': self.defect_detector.get_statistics()
        }