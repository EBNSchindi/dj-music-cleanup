"""
Batch Processor - Handles memory-efficient batch processing

Processes files in configurable batches to maintain constant memory usage
regardless of library size.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

from .constants import DEFAULT_BATCH_SIZE, PROGRESS_UPDATE_INTERVAL


class BatchProcessor:
    """
    Memory-efficient batch processing for large music libraries.
    """
    
    def __init__(self, orchestrator):
        """
        Initialize batch processor.
        
        Args:
            orchestrator: Parent orchestrator instance
        """
        self.orchestrator = orchestrator
        self.config = orchestrator.config
        self.streaming_config = orchestrator.streaming_config
        self.logger = logging.getLogger(__name__)
        
        self.batch_size = self.config.get('batch_size', DEFAULT_BATCH_SIZE)
    
    def analyze_files_in_batches(
        self,
        file_list: List[str],
        progress_callback: Optional[callable] = None
    ) -> List[Dict[str, Any]]:
        """
        Analyze files in memory-efficient batches.
        
        Args:
            file_list: List of file paths to analyze
            progress_callback: Optional progress callback
            
        Returns:
            List of analyzed file information
        """
        analyzed_files = []
        current_batch = []
        processed_count = 0
        
        self.logger.info(f"🔍 Processing {len(file_list)} files in batches of {self.batch_size}")
        
        for file_path in file_list:
            current_batch.append(file_path)
            
            # Process batch when full
            if len(current_batch) >= self.batch_size:
                batch_results = self._process_analysis_batch(current_batch)
                analyzed_files.extend(batch_results)
                processed_count += len(current_batch)
                
                # Progress update
                if progress_callback:
                    progress_callback(f"Analyzed: {processed_count}/{len(file_list)} files")
                
                # Memory management
                current_batch.clear()
                del batch_results
        
        # Process remaining files
        if current_batch:
            batch_results = self._process_analysis_batch(current_batch)
            analyzed_files.extend(batch_results)
            processed_count += len(current_batch)
            
            if progress_callback:
                progress_callback(f"Analyzed: {processed_count}/{len(file_list)} files")
        
        self.logger.info(f"🔍 Analysis complete: {len(analyzed_files)} files processed")
        return analyzed_files
    
    def organize_files_in_batches(
        self,
        file_list: List[str],
        target_folder: str,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Organize files in memory-efficient batches.
        
        Args:
            file_list: List of file paths to organize
            target_folder: Target directory for organization
            progress_callback: Optional progress callback
            
        Returns:
            Dictionary with organization results
        """
        results = {
            'files_processed': 0,
            'files_organized': 0,
            'files_skipped': 0,
            'errors': 0
        }
        
        current_batch = []
        
        self.logger.info(f"📁 Organizing {len(file_list)} files in batches of {self.batch_size}")
        
        for file_path in file_list:
            current_batch.append(file_path)
            
            # Process batch when full
            if len(current_batch) >= self.batch_size:
                batch_results = self._process_organization_batch(current_batch, target_folder)
                self._update_results(results, batch_results)
                
                # Progress update
                if progress_callback:
                    progress_callback(f"Organized: {results['files_processed']}/{len(file_list)} files")
                
                # Memory management
                current_batch.clear()
                del batch_results
        
        # Process remaining files
        if current_batch:
            batch_results = self._process_organization_batch(current_batch, target_folder)
            self._update_results(results, batch_results)
            
            if progress_callback:
                progress_callback(f"Organized: {results['files_processed']}/{len(file_list)} files")
        
        self.logger.info(f"📁 Organization complete: {results['files_organized']} files organized")
        return results
    
    def _process_analysis_batch(self, batch: List[str]) -> List[Dict[str, Any]]:
        """
        Process a single batch of files for analysis using FileAnalyzer.
        
        Args:
            batch: List of file paths in current batch
            
        Returns:
            List of analyzed file information
        """
        from .file_analyzer import FileAnalyzer
        from ..utils.analysis_converters import convert_to_file_info_dict
        
        # Create analyzer with orchestrator's config
        analyzer = FileAnalyzer(
            enable_fingerprinting=self.config.get('enable_fingerprinting', False),
            enable_defect_detection=self.config.get('enable_defect_detection', True),
            fingerprint_algorithm=self.config.get('fingerprint_algorithm', 'chromaprint'),
            min_health_score=self.config.get('min_health_score', 50.0)
        )
        
        analyzed_files = []
        
        # Use FileAnalyzer's batch processing
        results = analyzer.analyze_batch(batch)
        
        # Convert results to legacy format
        for result in results:
            if result and result.processed_successfully:
                file_info = convert_to_file_info_dict(result)
                
                # Add audio issues from health analysis
                if result.health_issues:
                    file_info['audio_issues'] = result.health_issues
                else:
                    file_info['audio_issues'] = []
                
                analyzed_files.append(file_info)
        
        return analyzed_files
    
    def _process_organization_batch(
        self,
        batch: List[str], 
        target_folder: str
    ) -> Dict[str, Any]:
        """
        Process a single batch of files for organization.
        
        Args:
            batch: List of file paths in current batch
            target_folder: Target directory for organization
            
        Returns:
            Dictionary with batch results
        """
        batch_results = {
            'files_processed': 0,
            'files_organized': 0,
            'files_skipped': 0,
            'errors': 0
        }
        
        for file_path in batch:
            try:
                # Use orchestrator's existing organization logic
                result = self.orchestrator._process_single_file_organization(
                    file_path, target_folder
                )
                
                batch_results['files_processed'] += 1
                
                if result.get('success'):
                    batch_results['files_organized'] += 1
                elif result.get('skipped'):
                    batch_results['files_skipped'] += 1
                else:
                    batch_results['errors'] += 1
                
            except Exception as e:
                self.logger.error(f"Error organizing file {file_path}: {e}")
                batch_results['errors'] += 1
        
        return batch_results
    
    def _update_results(self, main_results: Dict[str, Any], batch_results: Dict[str, Any]):
        """
        Update main results with batch results.
        
        Args:
            main_results: Main results dictionary to update
            batch_results: Batch results to add
        """
        for key in batch_results:
            if key in main_results:
                main_results[key] += batch_results[key]