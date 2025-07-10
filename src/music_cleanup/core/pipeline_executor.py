"""
Pipeline Executor - Coordinates the main processing pipeline

Handles the core workflow:
Phase 1: File Discovery
Phase 2: Health Analysis  
Phase 2.5: Corruption Filter
Phase 3: Duplicate Detection
Phase 4: Organization
"""

import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import defaultdict

from .constants import (
    MIN_HEALTH_SCORE_DEFAULT, 
    CRITICAL_DEFECTS,
    DEFAULT_BATCH_SIZE,
    PROGRESS_UPDATE_INTERVAL
)


class PipelineExecutor:
    """
    Executes the main music cleanup pipeline with proper phase separation.
    """
    
    def __init__(self, orchestrator):
        """
        Initialize pipeline executor.
        
        Args:
            orchestrator: Parent orchestrator instance
        """
        self.orchestrator = orchestrator
        self.config = orchestrator.config
        self.streaming_config = orchestrator.streaming_config
        self.workspace_dir = orchestrator.workspace_dir
        self.dry_run = orchestrator.dry_run
        self.logger = logging.getLogger(__name__)
        
        # Import handlers
        from .batch_processor import BatchProcessor
        from .corruption_handler import CorruptionHandler
        from .duplicate_handler import DuplicateHandler
        
        self.batch_processor = BatchProcessor(orchestrator)
        self.corruption_handler = CorruptionHandler(orchestrator)
        self.duplicate_handler = DuplicateHandler(orchestrator)
    
    def execute_pipeline(
        self,
        source_folders: List[str],
        target_folder: str,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Execute the complete music cleanup pipeline.
        
        Args:
            source_folders: List of source directories
            target_folder: Target directory for organized files
            progress_callback: Optional progress callback
            
        Returns:
            Dictionary with processing results
        """
        self.logger.info("🎵 Starting music cleanup pipeline...")
        start_time = time.time()
        
        results = {
            'files_discovered': 0,
            'files_analyzed': 0,
            'files_processed': 0,
            'files_organized': 0,
            'files_skipped': 0,
            'corrupted_files_filtered': 0,
            'healthy_files': 0,
            'duplicate_groups': 0,
            'duplicates_handled': 0,
            'space_saved': 0,
            'errors': 0,
            'processing_time': 0
        }
        
        try:
            # PHASE 1: File Discovery
            discovered_files = self._phase1_discovery(source_folders, progress_callback)
            results['files_discovered'] = len(discovered_files)
            
            if not discovered_files:
                self.logger.warning("No music files found in source folders")
                return results
            
            # PHASE 2: Health Analysis & Metadata Extraction
            analyzed_files = self._phase2_analysis(discovered_files, progress_callback)
            results['files_analyzed'] = len(analyzed_files)
            
            # PHASE 2.5: Corruption Filter (CRITICAL!)
            healthy_files, corrupted_files = self._phase2_5_corruption_filter(
                analyzed_files, target_folder, progress_callback
            )
            results['corrupted_files_filtered'] = len(corrupted_files)
            results['healthy_files'] = len(healthy_files)
            
            # PHASE 3: Duplicate Detection (only healthy files)
            duplicate_groups, duplicates_to_skip = self._phase3_duplicate_detection(
                healthy_files, progress_callback
            )
            results['duplicate_groups'] = len(duplicate_groups)
            
            # PHASE 4: Organization (healthy, non-duplicate files)
            organization_results = self._phase4_organization(
                healthy_files, duplicates_to_skip, target_folder, progress_callback
            )
            results.update(organization_results)
            
            # Calculate final metrics
            results['processing_time'] = time.time() - start_time
            results['duplicates_handled'] = sum(
                len(group.duplicates_to_remove) for group in duplicate_groups
            )
            results['space_saved'] = sum(
                group.space_savings for group in duplicate_groups
            )
            
            self._log_pipeline_summary(results)
            
        except Exception as e:
            self.logger.error(f"Pipeline execution failed: {e}")
            results['errors'] += 1
            raise
        
        return results
    
    def _phase1_discovery(
        self, 
        source_folders: List[str], 
        progress_callback: Optional[callable]
    ) -> List[str]:
        """Phase 1: Discover all music files"""
        self.logger.info("📁 Phase 1: Discovering music files...")
        
        if progress_callback:
            progress_callback("📁 Discovering music files...")
        
        discovered_files = []
        
        for file_path in self.orchestrator._discover_files_stream(source_folders):
            discovered_files.append(file_path)
            
            if len(discovered_files) % PROGRESS_UPDATE_INTERVAL == 0:
                if progress_callback:
                    progress_callback(f"Discovered: {len(discovered_files)} files")
        
        self.logger.info(f"📁 Discovered {len(discovered_files)} music files")
        return discovered_files
    
    def _phase2_analysis(
        self,
        discovered_files: List[str],
        progress_callback: Optional[callable]
    ) -> List[Dict[str, Any]]:
        """Phase 2: Analyze files for health and metadata"""
        self.logger.info("🔍 Phase 2: Analyzing files for health and metadata...")
        
        if progress_callback:
            progress_callback("🔍 Analyzing file health and metadata...")
        
        return self.batch_processor.analyze_files_in_batches(
            discovered_files, progress_callback
        )
    
    def _phase2_5_corruption_filter(
        self,
        analyzed_files: List[Dict[str, Any]], 
        target_folder: str,
        progress_callback: Optional[callable]
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Phase 2.5: Filter corrupted files (CRITICAL!)"""
        self.logger.info("🚫 Phase 2.5: Filtering corrupted files...")
        
        if progress_callback:
            progress_callback("🚫 Filtering corrupted files...")
        
        return self.corruption_handler.filter_corrupted_files(
            analyzed_files, target_folder
        )
    
    def _phase3_duplicate_detection(
        self,
        healthy_files: List[Dict[str, Any]],
        progress_callback: Optional[callable]
    ) -> tuple[List, set]:
        """Phase 3: Duplicate detection (only healthy files)"""
        self.logger.info("🔄 Phase 3: Duplicate detection on healthy files only...")
        
        if progress_callback:
            progress_callback("🔄 Detecting duplicates in healthy files...")
        
        return self.duplicate_handler.detect_and_handle_duplicates(
            healthy_files, progress_callback
        )
    
    def _phase4_organization(
        self,
        healthy_files: List[Dict[str, Any]],
        duplicates_to_skip: set,
        target_folder: str,
        progress_callback: Optional[callable]
    ) -> Dict[str, Any]:
        """Phase 4: Organization (healthy, non-duplicate files)"""
        self.logger.info("📁 Phase 4: Organizing healthy files...")
        
        if progress_callback:
            progress_callback("📁 Organizing files...")
        
        # Filter out duplicates from healthy files
        files_to_organize = []
        skipped_count = 0
        
        for file_info in healthy_files:
            if file_info['file_path'] in duplicates_to_skip:
                skipped_count += 1
                continue
            files_to_organize.append(file_info['file_path'])
        
        self.logger.info(f"📁 Organizing {len(files_to_organize)} healthy, non-duplicate files")
        self.logger.info(f"📁 Skipped {skipped_count} duplicate files")
        
        # Process organization in batches
        return self.batch_processor.organize_files_in_batches(
            files_to_organize, target_folder, progress_callback
        )
    
    def _log_pipeline_summary(self, results: Dict[str, Any]):
        """Log comprehensive pipeline summary"""
        self.logger.info("📊 Pipeline Summary:")
        self.logger.info(f"   📁 Files discovered: {results['files_discovered']:,}")
        self.logger.info(f"   🔍 Files analyzed: {results['files_analyzed']:,}")
        self.logger.info(f"   🚫 Corrupted filtered: {results['corrupted_files_filtered']:,}")
        self.logger.info(f"   ✅ Healthy files: {results['healthy_files']:,}")
        self.logger.info(f"   🔄 Duplicate groups: {results['duplicate_groups']:,}")
        self.logger.info(f"   📁 Files organized: {results['files_organized']:,}")
        self.logger.info(f"   💾 Space saved: {results['space_saved'] / (1024**3):.2f} GB")
        self.logger.info(f"   ⏱️  Total time: {results['processing_time']:.1f} seconds")
        
        if results['files_discovered'] > 0:
            efficiency = (results['files_organized'] / results['files_discovered']) * 100
            self.logger.info(f"   📈 Pipeline efficiency: {efficiency:.1f}%")