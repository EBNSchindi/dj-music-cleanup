"""
Corruption Handler - Manages corrupted file detection and quarantine

Handles Phase 2.5 of the pipeline: filtering corrupted files before
duplicate detection to ensure only healthy files are processed.
Integrates with RejectedHandler for proper file management.
"""

import logging
import shutil
from pathlib import Path
from typing import Dict, List, Tuple, Any
from datetime import datetime

from .constants import (
    MIN_HEALTH_SCORE_DEFAULT,
    CRITICAL_DEFECTS,
    QUARANTINE_FOLDER_NAME,
    ERROR_MESSAGES
)
from .rejected_handler import RejectedHandler


class CorruptionHandler:
    """
    Handles detection and quarantine of corrupted audio files.
    """
    
    def __init__(self, orchestrator):
        """
        Initialize corruption handler.
        
        Args:
            orchestrator: Parent orchestrator instance
        """
        self.orchestrator = orchestrator
        self.config = orchestrator.config
        self.workspace_dir = orchestrator.workspace_dir
        self.dry_run = orchestrator.dry_run
        self.logger = logging.getLogger(__name__)
        
        self.min_health_score = self.config.get('min_health_score', MIN_HEALTH_SCORE_DEFAULT)
        self.quarantine_files = self.config.get('quarantine_corrupted_files', False)
        
        # Initialize rejected handler for moving corrupted files
        self.rejected_handler = RejectedHandler(self.config)
    
    def filter_corrupted_files(
        self,
        analyzed_files: List[Dict[str, Any]],
        target_folder: str
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Filter corrupted files from analyzed files.
        
        This is the critical Phase 2.5 that ensures corrupted files
        cannot be selected as "best version" in duplicate detection.
        
        Args:
            analyzed_files: List of analyzed file information
            target_folder: Target folder for quarantine directory
            
        Returns:
            Tuple of (healthy_files, corrupted_files)
        """
        healthy_files = []
        corrupted_files = []
        
        self.logger.info(f"🚫 Filtering corrupted files (threshold: {self.min_health_score})")
        
        for file_info in analyzed_files:
            if self._is_file_corrupted(file_info):
                corrupted_files.append(file_info)
                self._log_corruption_reason(file_info)
            else:
                healthy_files.append(file_info)
        
        self.logger.info(f"🚫 Filtered out {len(corrupted_files)} corrupted files")
        self.logger.info(f"✅ Continuing with {len(healthy_files)} healthy files")
        
        # Handle corrupted files (quarantine and report)
        if corrupted_files:
            self._handle_corrupted_files(corrupted_files, target_folder)
        
        return healthy_files, corrupted_files
    
    def _is_file_corrupted(self, file_info: Dict[str, Any]) -> bool:
        """
        Determine if a file is corrupted based on health score and defects.
        
        Args:
            file_info: File information dictionary
            
        Returns:
            True if file is corrupted, False otherwise
        """
        health_score = file_info.get('health_score', 0)
        issues = file_info.get('audio_issues', [])
        
        # Check health score threshold
        if health_score < self.min_health_score:
            return True
        
        # Check for critical defects
        has_critical_defect = any(defect in issues for defect in CRITICAL_DEFECTS)
        if has_critical_defect:
            return True
        
        # Additional DJ-specific checks
        if self._has_dj_specific_issues(file_info):
            return True
        
        return False
    
    def _has_dj_specific_issues(self, file_info: Dict[str, Any]) -> bool:
        """
        Check for DJ-specific issues that make files unusable.
        
        Args:
            file_info: File information dictionary
            
        Returns:
            True if file has DJ-specific issues
        """
        # Check file duration (too short or too long for DJ use)
        duration = file_info.get('duration', 0)
        if duration < 10.0:  # Less than 10 seconds
            return True
        if duration > 3600.0:  # More than 1 hour
            return True
        
        # Check file size (suspiciously small)
        file_size = file_info.get('file_size', 0)
        if file_size < 100 * 1024:  # Less than 100KB
            return True
        
        # Check for metadata accessibility
        if not file_info.get('metadata_accessible', True):
            return True
        
        return False
    
    def _log_corruption_reason(self, file_info: Dict[str, Any]):
        """
        Log the reason why a file was marked as corrupted.
        
        Args:
            file_info: Corrupted file information
        """
        file_path = file_info['file_path']
        health_score = file_info.get('health_score', 0)
        issues = file_info.get('audio_issues', [])
        
        filename = Path(file_path).name
        
        if health_score < self.min_health_score:
            self.logger.warning(f"🚫 {filename}: Health score too low ({health_score})")
        
        if issues:
            critical_issues = [issue for issue in issues if issue in CRITICAL_DEFECTS]
            if critical_issues:
                self.logger.warning(f"🚫 {filename}: Critical defects - {', '.join(critical_issues)}")
    
    def _handle_corrupted_files(
        self,
        corrupted_files: List[Dict[str, Any]], 
        target_folder: str
    ):
        """
        Handle corrupted files using rejection system and generate reports.
        
        Args:
            corrupted_files: List of corrupted file information
            target_folder: Target folder for creating quarantine directory
        """
        try:
            # Generate detailed report in workspace
            quarantine_dir = Path(target_folder) / QUARANTINE_FOLDER_NAME
            quarantine_dir.mkdir(parents=True, exist_ok=True)
            report_path = self._generate_corruption_report(corrupted_files, quarantine_dir)
            
            # Move corrupted files using rejection system
            moved_count = 0
            if not self.dry_run:
                for file_info in corrupted_files:
                    try:
                        # Determine corruption details
                        corruption_details = self._get_corruption_details(file_info)
                        
                        # Extract metadata if available
                        metadata = {
                            'artist': file_info.get('artist'),
                            'title': file_info.get('title'),
                            'year': file_info.get('year'),
                            'genre': file_info.get('genre')
                        }
                        
                        # Move file using rejection system
                        rejected_path = self.rejected_handler.reject_corrupted(
                            file_path=file_info['file_path'],
                            corruption_details=corruption_details,
                            metadata=metadata
                        )
                        
                        if rejected_path:
                            moved_count += 1
                            self.logger.debug(f"Moved corrupted file: {Path(file_info['file_path']).name}")
                        
                    except Exception as e:
                        self.logger.error(f"Error moving corrupted file {file_info['file_path']}: {e}")
                        continue
            
            # Update orchestrator statistics
            self.orchestrator.stats['corrupted_files_quarantined'] = len(corrupted_files)
            self.orchestrator.stats['corrupted_files_moved'] = moved_count
            
            self.logger.info(f"📋 Corruption report generated: {report_path}")
            self.logger.info(f"📁 Moved {moved_count}/{len(corrupted_files)} corrupted files to rejected/")
            
        except Exception as e:
            self.logger.error(f"Error handling corrupted files: {e}")
    
    def _get_corruption_details(self, file_info: Dict[str, Any]) -> str:
        """
        Get detailed corruption information for a file.
        
        Args:
            file_info: File information dictionary
            
        Returns:
            String describing the corruption details
        """
        details = []
        
        health_score = file_info.get('health_score', 0)
        if health_score < self.min_health_score:
            details.append(f"Health score {health_score} below threshold {self.min_health_score}")
        
        issues = file_info.get('audio_issues', [])
        if issues:
            critical_issues = [issue for issue in issues if issue in CRITICAL_DEFECTS]
            if critical_issues:
                details.append(f"Critical defects: {', '.join(critical_issues)}")
            
            other_issues = [issue for issue in issues if issue not in CRITICAL_DEFECTS]
            if other_issues:
                details.append(f"Other issues: {', '.join(other_issues)}")
        
        # Check DJ-specific issues
        duration = file_info.get('duration', 0)
        if duration < 10.0:
            details.append("Duration too short for DJ use")
        elif duration > 3600.0:
            details.append("Duration too long for DJ use")
        
        file_size = file_info.get('file_size', 0)
        if file_size < 100 * 1024:
            details.append("File size suspiciously small")
        
        return "; ".join(details) if details else "Unknown corruption"
    
    def _generate_corruption_report(
        self,
        corrupted_files: List[Dict[str, Any]],
        quarantine_dir: Path
    ) -> Path:
        """
        Generate detailed corruption report.
        
        Args:
            corrupted_files: List of corrupted file information
            quarantine_dir: Quarantine directory path
            
        Returns:
            Path to generated report
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_path = quarantine_dir / f"corruption_report_{timestamp}.txt"
        
        with open(report_path, 'w', encoding='utf-8') as report:
            report.write("DJ MUSIC CLEANUP - CORRUPTION ANALYSIS REPORT\n")
            report.write("=" * 60 + "\n\n")
            report.write(f"Report Generated: {datetime.now().isoformat()}\n")
            report.write(f"Total Corrupted Files: {len(corrupted_files)}\n")
            report.write(f"Health Score Threshold: {self.min_health_score}\n\n")
            
            # Group by corruption reason
            corruption_stats = self._analyze_corruption_patterns(corrupted_files)
            
            report.write("CORRUPTION SUMMARY BY TYPE:\n")
            report.write("-" * 30 + "\n")
            for reason, count in corruption_stats.items():
                report.write(f"{reason}: {count} files\n")
            report.write("\n")
            
            # Detailed file listing
            report.write("DETAILED FILE ANALYSIS:\n")
            report.write("-" * 30 + "\n")
            
            for i, file_info in enumerate(corrupted_files, 1):
                self._write_file_details(report, i, file_info)
            
            # Recommendations
            report.write("\nRECOMMENDations:\n")
            report.write("-" * 30 + "\n")
            report.write("1. Review files with 'truncated_file' - may be incomplete downloads\n")
            report.write("2. Files with 'corrupted_header' cannot be recovered\n")
            report.write("3. Check original sources for 'complete_silence' files\n")
            report.write("4. Files below health score 50 should be deleted\n")
        
        return report_path
    
    def _analyze_corruption_patterns(
        self,
        corrupted_files: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """
        Analyze corruption patterns for reporting.
        
        Args:
            corrupted_files: List of corrupted file information
            
        Returns:
            Dictionary of corruption reasons and counts
        """
        corruption_stats = {}
        
        for file_info in corrupted_files:
            health_score = file_info.get('health_score', 0)
            issues = file_info.get('audio_issues', [])
            
            if health_score < self.min_health_score:
                reason = f"Low health score (<{self.min_health_score})"
                corruption_stats[reason] = corruption_stats.get(reason, 0) + 1
            
            for issue in issues:
                if issue in CRITICAL_DEFECTS:
                    corruption_stats[issue] = corruption_stats.get(issue, 0) + 1
        
        return corruption_stats
    
    def _write_file_details(self, report, file_num: int, file_info: Dict[str, Any]):
        """
        Write detailed file information to report.
        
        Args:
            report: Open file handle for report
            file_num: File number for listing
            file_info: File information dictionary
        """
        file_path = file_info['file_path']
        health_score = file_info.get('health_score', 'N/A')
        issues = file_info.get('audio_issues', [])
        duration = file_info.get('duration', 0)
        file_size = file_info.get('file_size', 0)
        
        report.write(f"{file_num:3d}. {Path(file_path).name}\n")
        report.write(f"     Path: {file_path}\n")
        report.write(f"     Health Score: {health_score}\n")
        report.write(f"     Duration: {duration:.1f}s\n")
        report.write(f"     Size: {file_size:,} bytes\n")
        
        if issues:
            report.write(f"     Issues: {', '.join(issues)}\n")
        else:
            report.write(f"     Issues: Health score below threshold\n")
        
        report.write(f"     Action: {'Quarantined' if self.quarantine_files else 'Reported only'}\n")
        report.write("\n")
    
    def _copy_files_to_quarantine(
        self,
        corrupted_files: List[Dict[str, Any]],
        quarantine_dir: Path
    ):
        """
        Copy corrupted files to quarantine directory.
        
        Args:
            corrupted_files: List of corrupted file information
            quarantine_dir: Quarantine directory path
        """
        copied_count = 0
        
        for i, file_info in enumerate(corrupted_files, 1):
            try:
                source_path = Path(file_info['file_path'])
                if not source_path.exists():
                    continue
                
                # Create unique filename
                target_path = quarantine_dir / f"corrupted_{i:04d}_{source_path.name}"
                
                # Handle name conflicts
                counter = 1
                while target_path.exists():
                    stem = source_path.stem
                    suffix = source_path.suffix
                    target_path = quarantine_dir / f"corrupted_{i:04d}_{stem}_{counter}{suffix}"
                    counter += 1
                
                shutil.copy2(source_path, target_path)
                copied_count += 1
                
            except Exception as e:
                self.logger.error(f"Error copying corrupted file to quarantine: {e}")
        
        self.logger.info(f"📁 Copied {copied_count}/{len(corrupted_files)} corrupted files to quarantine")