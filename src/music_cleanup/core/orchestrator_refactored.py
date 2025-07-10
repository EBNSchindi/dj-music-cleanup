"""
Refactored Central Orchestrator for DJ Music Cleanup Tool

Clean, modular orchestrator that delegates to specialized handlers:
- PipelineExecutor: Main workflow coordination
- BatchProcessor: Memory-efficient batch processing  
- CorruptionHandler: Phase 2.5 corruption filtering
- DuplicateHandler: Phase 3 duplicate detection on healthy files only

KRITISCH: Corruption filter runs BEFORE duplicate detection!
"""

import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Generator
from datetime import datetime
from collections import defaultdict

# Core imports
from .config import Config
from .streaming import StreamingConfig
from .constants import MIN_HEALTH_SCORE_DEFAULT, DEFAULT_BATCH_SIZE
from ..utils.tool_checker import get_tool_checker, ToolsMissingError

# Specialized handlers
from .pipeline_executor import PipelineExecutor


class MusicCleanupOrchestrator:
    """
    Clean, refactored orchestrator for DJ music cleanup.
    
    Delegates specialized tasks to dedicated handlers while maintaining
    the core file discovery and component initialization logic.
    """
    
    def __init__(
        self, 
        config: Dict,
        streaming_config: StreamingConfig,
        workspace_dir: Optional[str] = None,
        dry_run: bool = False
    ):
        """
        Initialize the orchestrator with configuration and handlers.
        
        Args:
            config: Main configuration dictionary
            streaming_config: Streaming pipeline configuration
            workspace_dir: Directory for temporary files
            dry_run: Simulate operations without making changes
        """
        self.config = config
        self.streaming_config = streaming_config
        self.workspace_dir = Path(workspace_dir or "workspace")
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.dry_run = dry_run
        self.logger = logging.getLogger(__name__)
        
        # Statistics tracking
        self.stats = defaultdict(int)
        self.start_time = None
        
        # Initialize specialized handlers
        self.pipeline_executor = PipelineExecutor(self)
        
        # Initialize core components (lazy loading to avoid dependency issues)
        self._file_discovery = None
        self._metadata_manager = None
        self._fingerprinter = None
        self._quality_analyzer = None
        self._organizer = None
        
        # Check for required tools
        self._check_required_tools()
        
        self.logger.info(f"MusicCleanupOrchestrator initialized (dry_run: {dry_run})")
        self.logger.info(f"Pipeline: Discovery → Analysis → Corruption Filter → Duplicates → Organization")
    
    def _check_required_tools(self):
        """Check for required external tools"""
        try:
            tool_checker = get_tool_checker()
            
            # Check tools but don't raise exception for missing recommended tools
            missing_required, missing_recommended, missing_optional = tool_checker.check_required_tools()
            
            if missing_required:
                # Generate helpful error message
                instructions = tool_checker.generate_install_instructions(missing_required)
                self.logger.error(f"Missing required tools: {missing_required}")
                self.logger.error(f"Installation instructions:\\n{instructions}")
                raise ToolsMissingError([f"Required tools missing: {', '.join(missing_required)}"])
            
            if missing_recommended:
                self.logger.warning(f"Recommended tools missing: {missing_recommended}")
                self.logger.warning("Some features may be limited without recommended tools")
            
            if missing_optional:
                self.logger.info(f"Optional tools missing: {missing_optional}")
                self.logger.info("Install optional tools for enhanced functionality")
                
        except ImportError:
            # Tool checker not available - continue without checks
            self.logger.warning("Tool availability checker not available")
    
    # === LAZY-LOADED COMPONENTS ===
    
    @property
    def file_discovery(self):
        """Lazy-load file discovery"""
        if self._file_discovery is None:
            from ..modules.simple_file_discovery import SimpleFileDiscovery
            self._file_discovery = SimpleFileDiscovery(self.streaming_config)
        return self._file_discovery
    
    @property
    def metadata_manager(self):
        """Lazy-load metadata manager"""
        if self._metadata_manager is None:
            try:
                # Try to use advanced metadata manager
                from ..modules.metadata_streaming import MetadataStreamingManager
                self._metadata_manager = MetadataStreamingManager(self.config)
                self.logger.info("Using advanced MetadataStreamingManager")
            except ImportError:
                # Fallback to simple metadata manager
                from ..modules.simple_metadata_manager import SimpleMetadataManager
                self._metadata_manager = SimpleMetadataManager(self.config)
                self.logger.warning("Using fallback SimpleMetadataManager")
        return self._metadata_manager
    
    @property
    def fingerprinter(self):
        """Lazy-load fingerprinter"""
        if self._fingerprinter is None:
            try:
                # Try to use advanced fingerprinter
                from ..audio.fingerprinting import AudioFingerprinter
                self._fingerprinter = AudioFingerprinter()
                self.logger.info("Using advanced AudioFingerprinter")
            except ImportError:
                # Fallback to simple fingerprinter
                from ..modules.simple_fingerprinter import SimpleFingerprinter
                self._fingerprinter = SimpleFingerprinter()
                self.logger.warning("Using fallback SimpleFingerprinter")
        return self._fingerprinter
    
    @property
    def quality_analyzer(self):
        """Lazy-load quality analyzer"""
        if self._quality_analyzer is None:
            try:
                # Try to use advanced AudioDefectDetector first
                from ..audio.defect_detection import AudioDefectDetector
                self._quality_analyzer = AudioDefectDetector(
                    min_health_score=self.config.get('min_health_score', MIN_HEALTH_SCORE_DEFAULT),
                    silence_threshold=self.config.get('silence_threshold', 0.001),
                    sample_duration=self.config.get('defect_sample_duration', 30.0)
                )
                self.logger.info("Using advanced AudioDefectDetector")
            except ImportError:
                # Fallback to simple quality analyzer
                from ..modules.simple_quality_analyzer import SimpleQualityAnalyzer
                self._quality_analyzer = SimpleQualityAnalyzer(self.config)
                self.logger.warning("Using fallback SimpleQualityAnalyzer")
        return self._quality_analyzer
    
    @property
    def organizer(self):
        """Lazy-load file organizer"""
        if self._organizer is None:
            from ..modules.simple_file_organizer import SimpleFileOrganizer
            self._organizer = SimpleFileOrganizer(
                target_root=self.config.get('output_directory', 'organized'),
                dry_run=self.dry_run
            )
        return self._organizer
    
    # === MAIN PIPELINE METHODS ===
    
    def run_organization_pipeline(
        self,
        source_folders: List[str],
        target_folder: str,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Main pipeline using specialized handlers.
        
        Phase 1: Discovery → Phase 2: Analysis → Phase 2.5: Corruption Filter → 
        Phase 3: Duplicate Detection → Phase 4: Organization
        
        Args:
            source_folders: List of source directories to process
            target_folder: Target directory for organized files
            progress_callback: Optional callback for progress updates
            
        Returns:
            Dictionary with processing results
        """
        self.logger.info("🎵 Starting refactored modular pipeline...")
        self.start_time = time.time()
        
        # Update config with target folder
        self.config['output_directory'] = target_folder
        
        # Delegate to specialized PipelineExecutor
        return self.pipeline_executor.execute_pipeline(
            source_folders, target_folder, progress_callback
        )
    
    # Alias for backward compatibility
    def organize_files(self, source_folders: List[str], target_folder: str, 
                      progress_callback: Optional[callable] = None) -> Dict[str, Any]:
        """Alias for run_organization_pipeline for backward compatibility"""
        return self.run_organization_pipeline(source_folders, target_folder, progress_callback)
    
    # === FILE DISCOVERY STREAM ===
    
    def _discover_files_stream(self, source_folders: List[str]) -> Generator[str, None, None]:
        """
        Stream file discovery for memory efficiency.
        
        Args:
            source_folders: List of directories to search
            
        Yields:
            File paths as strings
        """
        for file_path in self.file_discovery.discover_files_streaming(source_folders):
            yield file_path
    
    # === FILE ANALYSIS METHODS ===
    
    def _analyze_file_complete(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Analyze a single file: metadata + fingerprint + quality
        Returns file info dict for batch duplicate detection
        """
        try:
            file_path_obj = Path(file_path)
            
            # Skip if file doesn't exist
            if not file_path_obj.exists():
                return None
            
            file_info = {
                'file_path': file_path,
                'file_size': file_path_obj.stat().st_size,
                'file_mtime': file_path_obj.stat().st_mtime,
                'fingerprint': None,
                'metadata': {},
                'health_score': 50,
                'is_healthy': True
            }
            
            # Extract metadata
            metadata = self.metadata_manager.extract_metadata(file_path)
            if metadata:
                file_info['metadata'] = metadata
                file_info['duration'] = metadata.get('duration', 0)
                file_info['bitrate'] = metadata.get('bitrate')
                file_info['format'] = file_path_obj.suffix
            
            # Generate fingerprint if enabled
            if self.config.get('enable_fingerprinting', False):
                if hasattr(self.fingerprinter, 'generate_fingerprint'):
                    # Advanced AudioFingerprinter
                    fingerprint_obj = self.fingerprinter.generate_fingerprint(file_path)
                    if fingerprint_obj:
                        file_info['fingerprint'] = fingerprint_obj.fingerprint
                        file_info['duration'] = fingerprint_obj.duration
                        file_info['bitrate'] = fingerprint_obj.bitrate
                        file_info['algorithm'] = fingerprint_obj.algorithm
                else:
                    # Simple fingerprinter fallback
                    file_info['fingerprint'] = self.fingerprinter.generate_fingerprint(file_path)
            
            # Analyze quality/health
            if hasattr(self.quality_analyzer, 'analyze_audio_health'):
                # Advanced AudioDefectDetector
                health_report = self.quality_analyzer.analyze_audio_health(file_path)
                file_info['health_score'] = health_report.health_score
                file_info['is_healthy'] = health_report.is_healthy
                file_info['defects'] = [d.defect_type.value for d in health_report.defects]
                file_info['metadata_accessible'] = health_report.metadata_accessible
            else:
                # Simple quality analyzer fallback
                file_info['health_score'] = self.quality_analyzer.analyze_quality(file_path) * 100
                file_info['is_healthy'] = file_info['health_score'] > 50
            
            return file_info
            
        except Exception as e:
            self.logger.error(f"Error analyzing {file_path}: {e}")
            return None
    
    def _process_single_file_organization(self, file_path: str, target_folder: str) -> Dict[str, Any]:
        """
        Process a single file for organization.
        
        Args:
            file_path: Path to file to organize
            target_folder: Target directory
            
        Returns:
            Dictionary with operation result
        """
        result = {'success': False, 'skipped': False, 'error': None}
        
        try:
            file_path_obj = Path(file_path)
            
            # Basic file validation
            if not file_path_obj.exists():
                result['error'] = 'File not found'
                return result
            
            # Extract metadata for organization
            metadata = self.metadata_manager.extract_metadata(file_path)
            
            # Use organizer to determine destination and move file
            destination = self.organizer.organize_file(file_path_obj, metadata, 50)  # Default quality
            
            if destination:
                result['success'] = True
                result['destination'] = str(destination)
                self.logger.debug(f"Organized: {file_path_obj.name} → {destination}")
            else:
                result['error'] = 'Organization failed'
            
        except Exception as e:
            result['error'] = str(e)
            self.logger.error(f"Error organizing {file_path}: {e}")
        
        return result
    
    # === UTILITY METHODS ===
    
    def cleanup(self):
        """Clean up resources and temporary files"""
        try:
            self.logger.info("Starting orchestrator cleanup...")
            
            # Cleanup component resources
            if self._fingerprinter and hasattr(self._fingerprinter, 'cleanup'):
                self._fingerprinter.cleanup()
            
            if self._quality_analyzer and hasattr(self._quality_analyzer, 'cleanup'):
                self._quality_analyzer.cleanup()
            
            if self._organizer and hasattr(self._organizer, 'cleanup'):
                self._organizer.cleanup()
            
            # Clear component references to break potential circular references
            self._fingerprinter = None
            self._quality_analyzer = None
            self._metadata_manager = None
            self._file_discovery = None
            self._organizer = None
            
            # Clear statistics to prevent memory accumulation
            self.stats.clear()
            
            self.logger.info("Orchestrator cleanup completed")
            
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
    
    def reset_stats(self):
        """Reset statistics to prevent memory accumulation"""
        self.stats.clear()
        self.start_time = time.time()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get current processing statistics with memory-safe copy"""
        duration = time.time() - self.start_time if self.start_time else 0
        
        # Create a copy to avoid reference retention
        stats_copy = dict(self.stats)
        
        return {
            'statistics': stats_copy,
            'duration_seconds': duration,
            'dry_run': self.dry_run
        }