"""
Duplicate Handler - Manages duplicate detection on healthy files only

Handles Phase 3 of the pipeline: detecting duplicates only among healthy files
to ensure corrupted files cannot be selected as "best version".
Integrates with RejectedHandler to move duplicates instead of deleting them.
"""

import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from .constants import (
    FINGERPRINT_MATCH_THRESHOLD,
    MIN_DURATION_MATCH
)
from .rejected_handler import RejectedHandler


class DuplicateHandler:
    """
    Handles duplicate detection exclusively on healthy files.
    """
    
    def __init__(self, orchestrator):
        """
        Initialize duplicate handler.
        
        Args:
            orchestrator: Parent orchestrator instance
        """
        self.orchestrator = orchestrator
        self.config = orchestrator.config
        self.workspace_dir = orchestrator.workspace_dir
        self.logger = logging.getLogger(__name__)
        
        self.fingerprint_enabled = self.config.get('enable_fingerprinting', False)
        self.similarity_threshold = self.config.get('duplicate_similarity', FINGERPRINT_MATCH_THRESHOLD)
        
        # Initialize rejected handler for moving duplicates
        self.rejected_handler = RejectedHandler(self.config)
    
    def detect_and_handle_duplicates(
        self,
        healthy_files: List[Dict[str, Any]],
        progress_callback: Optional[callable] = None
    ) -> Tuple[List, set]:
        """
        Detect and handle duplicates among healthy files only.
        
        Args:
            healthy_files: List of healthy file information
            progress_callback: Optional progress callback
            
        Returns:
            Tuple of (duplicate_groups, duplicates_to_skip)
        """
        duplicate_groups = []
        duplicates_to_skip = set()
        
        if not self.fingerprint_enabled:
            self.logger.info("🔄 Fingerprinting disabled, skipping duplicate detection")
            return duplicate_groups, duplicates_to_skip
        
        if not healthy_files:
            self.logger.info("🔄 No healthy files for duplicate detection")
            return duplicate_groups, duplicates_to_skip
        
        try:
            self.logger.info(f"🔄 Starting duplicate detection on {len(healthy_files)} healthy files")
            
            if progress_callback:
                progress_callback("🔄 Detecting duplicates...")
            
            # Convert healthy files to fingerprint objects
            duplicate_groups = self._detect_duplicates_from_healthy_files(healthy_files)
            
            # Create set of files to skip (duplicates)
            for group in duplicate_groups:
                for duplicate in group.duplicates_to_remove:
                    duplicates_to_skip.add(duplicate.file_path)
            
            # Handle duplicates (move/delete/report)
            if duplicate_groups:
                self._handle_duplicate_groups(duplicate_groups)
            
            self.logger.info(f"🔄 Found {len(duplicate_groups)} duplicate groups")
            self.logger.info(f"🔄 Marked {len(duplicates_to_skip)} files as duplicates to skip")
            
        except Exception as e:
            self.logger.error(f"Error in duplicate detection: {e}")
        
        return duplicate_groups, duplicates_to_skip
    
    def _detect_duplicates_from_healthy_files(
        self,
        healthy_files: List[Dict[str, Any]]
    ) -> List:
        """
        Convert healthy files to fingerprints and detect duplicates.
        
        Args:
            healthy_files: List of healthy file information
            
        Returns:
            List of duplicate groups
        """
        try:
            from ..audio.duplicate_detection import DuplicateDetector, DuplicateAction
            from ..audio.fingerprinting import AudioFingerprint
            
            # Filter files that have fingerprints
            files_with_fingerprints = [
                f for f in healthy_files 
                if f.get('fingerprint') and f.get('fingerprint').strip()
            ]
            
            if not files_with_fingerprints:
                self.logger.info("No healthy files with fingerprints found")
                return []
            
            self.logger.info(f"🔄 Creating fingerprint objects for {len(files_with_fingerprints)} healthy files")
            
            # Convert to AudioFingerprint objects
            fingerprints = []
            for file_info in files_with_fingerprints:
                try:
                    fp = AudioFingerprint(
                        file_path=file_info['file_path'],
                        fingerprint=file_info['fingerprint'],
                        duration=file_info.get('duration', 0),
                        file_size=file_info.get('file_size', 0),
                        algorithm=file_info.get('algorithm', 'chromaprint'),
                        format=Path(file_info['file_path']).suffix,
                        bitrate=file_info.get('bitrate'),
                        file_mtime=file_info.get('file_mtime', time.time())
                    )
                    fingerprints.append(fp)
                except Exception as e:
                    self.logger.error(f"Error creating fingerprint object: {e}")
                    continue
            
            if not fingerprints:
                self.logger.warning("No valid fingerprints created")
                return []
            
            # Create duplicate detector
            duplicate_action = DuplicateAction(self.config.get('duplicate_action', 'report-only'))
            detector = DuplicateDetector(
                duplicate_action=duplicate_action,
                duplicates_folder=str(self.workspace_dir / "Duplicates"),
                min_similarity=self.similarity_threshold
            )
            
            # Detect duplicates
            self.logger.info(f"🔄 Analyzing {len(fingerprints)} fingerprints for duplicates")
            duplicate_groups = detector.detect_and_rank_duplicates(fingerprints)
            
            self.logger.info(f"🔄 Found {len(duplicate_groups)} duplicate groups from healthy files")
            
            # Log duplicate group summary
            self._log_duplicate_summary(duplicate_groups)
            
            return duplicate_groups
            
        except ImportError:
            self.logger.warning("Advanced duplicate detection not available")
            return []
        except Exception as e:
            self.logger.error(f"Error in duplicate detection: {e}")
            return []
    
    def _handle_duplicate_groups(self, duplicate_groups: List) -> Dict[str, Any]:
        """
        Handle duplicate groups using rejection system instead of deletion.
        
        Args:
            duplicate_groups: List of duplicate groups
            
        Returns:
            Dictionary with handling results
        """
        results = {
            'files_processed': 0,
            'files_moved': 0,
            'files_deleted': 0,
            'space_freed': 0,
            'duplicate_groups_handled': 0
        }
        
        try:
            for group_idx, group in enumerate(duplicate_groups):
                # Get the best file (to keep)
                best_file_path = group.best_file.file_path
                
                # Generate unique group ID
                group_id = f"group_{group_idx + 1}_{int(time.time())}"
                
                # Process each duplicate in the group
                for rank, duplicate in enumerate(group.duplicates_to_remove, start=2):
                    try:
                        # Get metadata for the duplicate
                        metadata = {
                            'artist': getattr(duplicate, 'artist', None),
                            'title': getattr(duplicate, 'title', None),
                            'year': getattr(duplicate, 'year', None),
                            'genre': getattr(duplicate, 'genre', None)
                        }
                        
                        # Calculate quality score if available
                        quality_score = getattr(duplicate, 'quality_score', None)
                        if quality_score is None and hasattr(duplicate, 'bitrate'):
                            # Simple quality estimation based on bitrate
                            quality_score = min(100, (duplicate.bitrate / 320) * 100)
                        
                        # Move duplicate using rejection system
                        rejected_path = self.rejected_handler.reject_duplicate(
                            file_path=duplicate.file_path,
                            chosen_file=best_file_path,
                            quality_score=quality_score or 0,
                            duplicate_group_id=group_id,
                            rank=rank,
                            metadata=metadata
                        )
                        
                        if rejected_path:
                            results['files_moved'] += 1
                            results['space_freed'] += getattr(duplicate, 'file_size', 0)
                            
                            self.logger.info(f"📋 Moved duplicate #{rank}: {Path(duplicate.file_path).name}")
                        else:
                            self.logger.error(f"Failed to move duplicate: {duplicate.file_path}")
                        
                        results['files_processed'] += 1
                        
                    except Exception as e:
                        self.logger.error(f"Error handling duplicate {duplicate.file_path}: {e}")
                        continue
                
                results['duplicate_groups_handled'] += 1
                
                # Log group handling
                self.logger.info(f"✅ Handled duplicate group {group_idx + 1}:")
                self.logger.info(f"   Best file: {Path(best_file_path).name}")
                self.logger.info(f"   Duplicates moved: {len(group.duplicates_to_remove)}")
            
            # Log final results
            self.logger.info(f"🔄 Duplicate handling results:")
            self.logger.info(f"   Groups processed: {results['duplicate_groups_handled']}")
            self.logger.info(f"   Files processed: {results['files_processed']}")
            self.logger.info(f"   Files moved to rejected/: {results['files_moved']}")
            self.logger.info(f"   Space freed: {results['space_freed'] / (1024**3):.2f} GB")
            
            return results
            
        except Exception as e:
            self.logger.error(f"Error handling duplicates: {e}")
            return results
    
    def _log_duplicate_summary(self, duplicate_groups: List):
        """
        Log a summary of duplicate groups found.
        
        Args:
            duplicate_groups: List of duplicate groups
        """
        if not duplicate_groups:
            return
        
        total_duplicates = sum(len(group.duplicates_to_remove) for group in duplicate_groups)
        total_space_savings = sum(group.space_savings for group in duplicate_groups)
        
        self.logger.info(f"🔄 Duplicate Detection Summary:")
        self.logger.info(f"   Duplicate groups: {len(duplicate_groups)}")
        self.logger.info(f"   Total duplicates: {total_duplicates}")
        self.logger.info(f"   Potential space savings: {total_space_savings / (1024**3):.2f} GB")
        
        # Log top 5 largest duplicate groups
        sorted_groups = sorted(
            duplicate_groups, 
            key=lambda g: g.space_savings, 
            reverse=True
        )
        
        self.logger.info(f"   Top duplicate groups by space savings:")
        for i, group in enumerate(sorted_groups[:5], 1):
            best_file = Path(group.best_file.file_path).name
            duplicates_count = len(group.duplicates_to_remove)
            savings_mb = group.space_savings / (1024**2)
            self.logger.info(f"     {i}. {best_file}: {duplicates_count} duplicates, {savings_mb:.1f} MB")
    
    def get_duplicate_statistics(self) -> Dict[str, Any]:
        """
        Get duplicate detection statistics.
        
        Returns:
            Dictionary with duplicate statistics
        """
        return {
            'fingerprinting_enabled': self.fingerprint_enabled,
            'similarity_threshold': self.similarity_threshold,
            'duplicate_action': self.config.get('duplicate_action', 'report-only'),
            'workspace_dir': str(self.workspace_dir)
        }