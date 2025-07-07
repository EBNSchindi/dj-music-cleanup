"""
Central Orchestrator for DJ Music Cleanup Tool

Coordinates all modules and manages the streaming pipeline for efficient
music library processing with memory efficiency and crash recovery.
"""

import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Generator
from datetime import datetime
from collections import defaultdict

from .config import Config
from .database import DatabaseManager, get_database_manager
from .streaming import (
    StreamingConfig, FileDiscoveryStream, ParallelStreamProcessor,
    MemoryMonitor, StreamingProgressTracker
)
from .transactions import AtomicFileOperations, OperationType
from .recovery import CrashRecoveryManager, CheckpointType
from .rollback import RollbackManager, RollbackScope
from ..modules.fingerprinting_streaming import AudioFingerprinter
from ..modules.metadata_streaming import MetadataManager
from ..modules.audio_quality import AudioQualityAnalyzer
from ..modules.organizer_atomic import AtomicFileOrganizer
from ..utils.integrity import FileIntegrityChecker, IntegrityLevel
from ..utils.progress import ProgressReporter


class MusicCleanupOrchestrator:
    """
    Central orchestrator that coordinates all modules for music library cleanup.
    
    Manages the streaming pipeline, coordinates module interactions, tracks
    progress, and handles errors centrally.
    """
    
    def __init__(
        self, 
        config: Config,
        streaming_config: StreamingConfig,
        workspace_dir: Optional[str] = None,
        enable_recovery: bool = True,
        dry_run: bool = False
    ):
        """
        Initialize the orchestrator with configuration and modules.
        
        Args:
            config: Main configuration object
            streaming_config: Streaming pipeline configuration
            workspace_dir: Directory for temporary files and recovery data
            enable_recovery: Enable crash recovery and checkpoints
            dry_run: Simulate operations without making changes
        """
        self.config = config
        self.streaming_config = streaming_config
        self.workspace_dir = Path(workspace_dir or "workspace")
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.enable_recovery = enable_recovery
        self.dry_run = dry_run
        self.logger = logging.getLogger(__name__)
        
        # Initialize core components
        self.db_manager = get_database_manager()
        self.memory_monitor = MemoryMonitor(streaming_config)
        
        # Initialize modules (lazy loading)
        self._fingerprinter = None
        self._metadata_manager = None
        self._quality_analyzer = None
        self._organizer = None
        self._integrity_checker = None
        
        # Recovery and safety components
        self.recovery_manager = None
        self.atomic_ops = None
        self.rollback_manager = None
        
        if enable_recovery:
            self._init_recovery_components()
        
        # Session tracking
        self.session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.operation_group = f"op_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Statistics tracking
        self.stats = defaultdict(int)
        self.start_time = None
        
        self.logger.info(f"MusicCleanupOrchestrator initialized (session: {self.session_id})")
    
    def _init_recovery_components(self):
        """Initialize recovery and safety components."""
        self.recovery_manager = CrashRecoveryManager(
            workspace_dir=str(self.workspace_dir / "recovery"),
            enable_auto_checkpoints=True
        )
        
        self.atomic_ops = AtomicFileOperations(
            workspace_dir=str(self.workspace_dir / "atomic")
        )
        
        self.rollback_manager = RollbackManager(
            workspace_dir=str(self.workspace_dir / "rollback")
        )
    
    @property
    def fingerprinter(self) -> AudioFingerprinter:
        """Lazy-load fingerprinter module."""
        if self._fingerprinter is None:
            self._fingerprinter = AudioFingerprinter(
                self.config,
                self.streaming_config
            )
        return self._fingerprinter
    
    @property
    def metadata_manager(self) -> MetadataManager:
        """Lazy-load metadata manager."""
        if self._metadata_manager is None:
            self._metadata_manager = MetadataManager(self.config)
        return self._metadata_manager
    
    @property
    def quality_analyzer(self) -> AudioQualityAnalyzer:
        """Lazy-load quality analyzer."""
        if self._quality_analyzer is None:
            self._quality_analyzer = AudioQualityAnalyzer(self.config)
        return self._quality_analyzer
    
    @property
    def organizer(self) -> AtomicFileOrganizer:
        """Lazy-load file organizer."""
        if self._organizer is None:
            self._organizer = AtomicFileOrganizer(
                target_root=self.config.get('output_directory', 'organized'),
                workspace_dir=str(self.workspace_dir / "organizer"),
                enable_rollback=self.enable_recovery
            )
        return self._organizer
    
    @property
    def integrity_checker(self) -> FileIntegrityChecker:
        """Lazy-load integrity checker."""
        if self._integrity_checker is None:
            self._integrity_checker = FileIntegrityChecker(
                workspace_dir=str(self.workspace_dir / "integrity")
            )
        return self._integrity_checker
    
    def analyze_library(
        self, 
        source_folders: List[str], 
        report_path: Optional[str] = None,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Analyze music library without making changes.
        
        Args:
            source_folders: List of folders to analyze
            report_path: Path to save analysis report
            progress_callback: Optional progress callback function
            
        Returns:
            Analysis results dictionary
        """
        self.logger.info(f"Starting library analysis for {len(source_folders)} folders")
        self.start_time = time.time()
        
        # Begin recovery session if enabled
        if self.enable_recovery:
            self.recovery_manager.begin_session(self.session_id, self.operation_group)
        
        results = {
            'total_files': 0,
            'audio_formats': defaultdict(int),
            'quality_distribution': defaultdict(int),
            'duplicate_groups': [],
            'metadata_issues': [],
            'integrity_issues': [],
            'genre_distribution': defaultdict(int),
            'decade_distribution': defaultdict(int),
            'total_size_bytes': 0,
            'analysis_duration': 0
        }
        
        try:
            # Create file discovery stream
            discovery = FileDiscoveryStream(self.streaming_config)
            
            # Analyze files in streaming fashion
            with StreamingProgressTracker(
                "Analyzing library", 
                enable_db_tracking=True,
                operation_group=self.operation_group
            ) as progress:
                
                for file_path in discovery.stream_files(source_folders):
                    try:
                        # Memory check
                        self.memory_monitor.check_memory_usage()
                        
                        # Update progress
                        if progress_callback:
                            progress_callback(file_path)
                        
                        # Analyze file
                        file_results = self._analyze_single_file(file_path)
                        
                        # Update results
                        results['total_files'] += 1
                        results['total_size_bytes'] += file_results.get('size', 0)
                        
                        # Format statistics
                        format_ext = file_results.get('format', 'unknown')
                        results['audio_formats'][format_ext] += 1
                        
                        # Quality statistics
                        quality = file_results.get('quality_category', 'unknown')
                        results['quality_distribution'][quality] += 1
                        
                        # Genre/decade statistics
                        if file_results.get('genre'):
                            results['genre_distribution'][file_results['genre']] += 1
                        if file_results.get('decade'):
                            results['decade_distribution'][file_results['decade']] += 1
                        
                        # Collect issues
                        if file_results.get('metadata_issues'):
                            results['metadata_issues'].append({
                                'file': file_path,
                                'issues': file_results['metadata_issues']
                            })
                        
                        if file_results.get('integrity_status') != 'healthy':
                            results['integrity_issues'].append({
                                'file': file_path,
                                'status': file_results['integrity_status'],
                                'issues': file_results.get('integrity_issues', [])
                            })
                        
                        # Update progress
                        progress.update(1, has_error=False)
                        self.stats['files_analyzed'] += 1
                        
                        # Checkpoint periodically
                        if self.enable_recovery and self.stats['files_analyzed'] % 1000 == 0:
                            self._create_checkpoint("analysis_progress", results)
                        
                    except Exception as e:
                        self.logger.error(f"Error analyzing {file_path}: {e}")
                        progress.update(1, has_error=True)
                        self.stats['analysis_errors'] += 1
            
            # Detect duplicates if enabled
            if not self.config.get('skip_duplicates', False):
                self.logger.info("Detecting duplicates...")
                results['duplicate_groups'] = self._detect_duplicates_streaming(
                    source_folders,
                    progress_callback
                )
                self.stats['duplicate_groups'] = len(results['duplicate_groups'])
            
            # Calculate analysis duration
            results['analysis_duration'] = time.time() - self.start_time
            
            # Generate report if requested
            if report_path:
                self._generate_analysis_report(results, report_path)
            
            # Final checkpoint
            if self.enable_recovery:
                self._create_checkpoint("analysis_complete", results)
            
            self.logger.info(
                f"Analysis completed: {results['total_files']} files analyzed in "
                f"{results['analysis_duration']:.2f} seconds"
            )
            
            return results
            
        except Exception as e:
            self.logger.error(f"Analysis failed: {e}")
            if self.enable_recovery:
                self.recovery_manager.create_emergency_checkpoint(f"analysis_error: {e}")
            raise
    
    def organize_library(
        self,
        source_folders: List[str],
        output_directory: str,
        enable_fingerprinting: bool = False,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Organize music library with full processing pipeline.
        
        Args:
            source_folders: Source folders to process
            output_directory: Target directory for organized library
            enable_fingerprinting: Enable audio fingerprinting
            progress_callback: Optional progress callback
            
        Returns:
            Organization results
        """
        self.logger.info(f"Starting library organization to {output_directory}")
        self.start_time = time.time()
        
        # Update configuration
        self.config['output_directory'] = output_directory
        self.config['enable_fingerprinting'] = enable_fingerprinting
        
        # Begin recovery session
        if self.enable_recovery:
            self.recovery_manager.begin_session(self.session_id, self.operation_group)
            
        # Begin organization session
        self.organizer.begin_organization_session(
            f"Organization: {self.session_id}"
        )
        
        results = {
            'files_processed': 0,
            'files_organized': 0,
            'files_skipped': 0,
            'errors': 0,
            'duplicates_handled': 0,
            'space_saved': 0,
            'organization_duration': 0
        }
        
        try:
            # Create streaming processor
            processor = ParallelStreamProcessor(
                self.streaming_config,
                process_func=self._process_file_for_organization
            )
            
            # Process files through pipeline
            with StreamingProgressTracker(
                "Organizing library",
                enable_db_tracking=True,
                operation_group=self.operation_group
            ) as progress:
                
                # Stream and process files
                discovery = FileDiscoveryStream(self.streaming_config)
                
                for batch_results in processor.process_stream(
                    discovery.stream_files(source_folders)
                ):
                    for result in batch_results:
                        if result['success']:
                            results['files_organized'] += 1
                        elif result.get('skipped'):
                            results['files_skipped'] += 1
                        else:
                            results['errors'] += 1
                        
                        results['files_processed'] += 1
                        
                        # Update progress
                        progress.update(1, has_error=not result['success'])
                        if progress_callback:
                            progress_callback(result)
                        
                        # Periodic checkpoint
                        if self.enable_recovery and results['files_processed'] % 500 == 0:
                            self._create_checkpoint("organize_progress", results)
            
            # Handle duplicates if found
            if self.stats.get('duplicates_found', 0) > 0:
                duplicate_results = self._handle_duplicates_atomic()
                results['duplicates_handled'] = duplicate_results['handled']
                results['space_saved'] = duplicate_results['space_saved']
            
            # Finalize organization
            self.organizer.finalize()
            
            # Calculate duration
            results['organization_duration'] = time.time() - self.start_time
            
            # Final checkpoint
            if self.enable_recovery:
                self._create_checkpoint("organization_complete", results)
            
            self.logger.info(
                f"Organization completed: {results['files_organized']} files organized "
                f"in {results['organization_duration']:.2f} seconds"
            )
            
            return results
            
        except Exception as e:
            self.logger.error(f"Organization failed: {e}")
            
            # Attempt rollback
            if self.enable_recovery and not self.dry_run:
                self.logger.info("Attempting rollback...")
                if self.organizer.rollback_session():
                    self.logger.info("Rollback successful")
                else:
                    self.logger.error("Rollback failed")
            
            # Emergency checkpoint
            if self.enable_recovery:
                self.recovery_manager.create_emergency_checkpoint(f"organize_error: {e}")
            
            raise
    
    def cleanup_library(
        self,
        source_folders: List[str],
        enable_fingerprinting: bool = True,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Clean up library by removing duplicates and optimizing.
        
        Args:
            source_folders: Folders to clean up
            enable_fingerprinting: Use acoustic fingerprinting
            progress_callback: Optional progress callback
            
        Returns:
            Cleanup results
        """
        self.logger.info("Starting library cleanup")
        self.start_time = time.time()
        
        # Begin recovery session
        if self.enable_recovery:
            self.recovery_manager.begin_session(self.session_id, self.operation_group)
        
        results = {
            'files_scanned': 0,
            'duplicates_found': 0,
            'duplicates_removed': 0,
            'space_reclaimed': 0,
            'errors': 0,
            'cleanup_duration': 0
        }
        
        try:
            # Phase 1: Detect duplicates
            self.logger.info("Phase 1: Detecting duplicates...")
            duplicate_groups = self._detect_duplicates_streaming(
                source_folders,
                progress_callback,
                use_fingerprinting=enable_fingerprinting
            )
            
            results['duplicates_found'] = sum(
                len(group) - 1 for group in duplicate_groups
            )
            
            # Phase 2: Handle duplicates
            if duplicate_groups:
                self.logger.info(f"Phase 2: Processing {len(duplicate_groups)} duplicate groups...")
                
                # Process duplicate groups atomically
                with self.atomic_ops.atomic_transaction({
                    'operation': 'cleanup_duplicates',
                    'groups': len(duplicate_groups)
                }) as transaction:
                    
                    for group_idx, group in enumerate(duplicate_groups):
                        try:
                            # Determine which file to keep
                            keep_file, remove_files = self._select_best_duplicate(group)
                            
                            # Add delete operations for duplicates
                            for file_path in remove_files:
                                if not self.dry_run:
                                    self.atomic_ops.add_operation(
                                        transaction.transaction_id,
                                        OperationType.DELETE,
                                        source_path=file_path,
                                        metadata={
                                            'reason': 'duplicate',
                                            'kept_file': keep_file,
                                            'group_id': f"group_{group_idx}"
                                        }
                                    )
                                
                                # Calculate space saved
                                if os.path.exists(file_path):
                                    results['space_reclaimed'] += os.path.getsize(file_path)
                                
                                results['duplicates_removed'] += 1
                            
                            # Update progress
                            if progress_callback:
                                progress_callback({
                                    'action': 'duplicate_group_processed',
                                    'group': group_idx + 1,
                                    'total_groups': len(duplicate_groups),
                                    'kept': keep_file,
                                    'removed': len(remove_files)
                                })
                            
                            # Checkpoint periodically
                            if self.enable_recovery and group_idx % 100 == 0:
                                self._create_checkpoint("cleanup_progress", results)
                                
                        except Exception as e:
                            self.logger.error(f"Error processing duplicate group {group_idx}: {e}")
                            results['errors'] += 1
            
            # Phase 3: Optimize remaining files
            self.logger.info("Phase 3: Optimizing library...")
            optimization_results = self._optimize_library_structure(
                source_folders,
                progress_callback
            )
            results.update(optimization_results)
            
            # Calculate duration
            results['cleanup_duration'] = time.time() - self.start_time
            
            # Final checkpoint
            if self.enable_recovery:
                self._create_checkpoint("cleanup_complete", results)
            
            self.logger.info(
                f"Cleanup completed: {results['duplicates_removed']} duplicates removed, "
                f"{results['space_reclaimed'] / (1024**3):.2f} GB reclaimed"
            )
            
            return results
            
        except Exception as e:
            self.logger.error(f"Cleanup failed: {e}")
            if self.enable_recovery:
                self.recovery_manager.create_emergency_checkpoint(f"cleanup_error: {e}")
            raise
    
    def recover_from_crash(
        self,
        recovery_id: Optional[str] = None,
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Recover from a previous crash or interruption.
        
        Args:
            recovery_id: Specific recovery point ID
            progress_callback: Optional progress callback
            
        Returns:
            Recovery results
        """
        if not self.enable_recovery or not self.recovery_manager:
            raise ValueError("Recovery not enabled")
        
        self.logger.info(f"Starting recovery mode (ID: {recovery_id or 'auto-detect'})")
        
        results = {
            'recovery_successful': False,
            'checkpoint_used': None,
            'files_recovered': 0,
            'operations_rolled_back': 0,
            'duration': 0
        }
        
        start_time = time.time()
        
        try:
            # Detect interruption
            interruption = self.recovery_manager.detect_interruption()
            
            if not interruption['interrupted']:
                self.logger.info("No interruption detected")
                results['recovery_successful'] = True
                return results
            
            # Create recovery plan
            recovery_plan = self.recovery_manager.create_recovery_plan(recovery_id)
            results['checkpoint_used'] = recovery_plan.target_checkpoint
            
            self.logger.info(
                f"Recovery plan created: {len(recovery_plan.recovery_actions)} actions, "
                f"risk level: {recovery_plan.risk_level}"
            )
            
            # Execute recovery
            if not self.dry_run:
                recovery_result = self.recovery_manager.execute_recovery(
                    recovery_plan,
                    dry_run=False
                )
                
                results['recovery_successful'] = recovery_result['success']
                results['operations_rolled_back'] = recovery_result.get(
                    'operations_rolled_back', 0
                )
                
                # Update progress
                if progress_callback:
                    progress_callback(recovery_result)
            else:
                self.logger.info("Dry run mode - skipping actual recovery")
                results['recovery_successful'] = True
            
            results['duration'] = time.time() - start_time
            
            self.logger.info(
                f"Recovery {'completed' if results['recovery_successful'] else 'failed'} "
                f"in {results['duration']:.2f} seconds"
            )
            
            return results
            
        except Exception as e:
            self.logger.error(f"Recovery failed: {e}")
            results['error'] = str(e)
            results['duration'] = time.time() - start_time
            return results
    
    def _analyze_single_file(self, file_path: str) -> Dict[str, Any]:
        """Analyze a single music file."""
        result = {
            'path': file_path,
            'size': 0,
            'format': Path(file_path).suffix.lower(),
            'metadata_issues': [],
            'integrity_status': 'unknown'
        }
        
        try:
            # Get file size
            result['size'] = os.path.getsize(file_path)
            
            # Check integrity
            integrity_level = IntegrityLevel[
                self.config.get('integrity_level', 'checksum').upper()
            ]
            integrity_check = self.integrity_checker.check_file_integrity(
                file_path,
                integrity_level
            )
            
            result['integrity_status'] = integrity_check.status.value
            result['integrity_issues'] = integrity_check.issues
            
            # Extract metadata
            metadata = self.metadata_manager.extract_metadata_streaming(file_path)
            if metadata:
                result.update({
                    'artist': metadata.get('artist'),
                    'title': metadata.get('title'),
                    'genre': metadata.get('genre'),
                    'year': metadata.get('year'),
                    'decade': self._get_decade(metadata.get('year')),
                    'bitrate': metadata.get('bitrate'),
                    'duration': metadata.get('duration')
                })
                
                # Categorize quality
                result['quality_category'] = self._categorize_quality(
                    metadata.get('bitrate', 0)
                )
                
                # Check for metadata issues
                if not metadata.get('artist') or not metadata.get('title'):
                    result['metadata_issues'].append('missing_essential_tags')
                if not metadata.get('year'):
                    result['metadata_issues'].append('missing_year')
            else:
                result['metadata_issues'].append('metadata_extraction_failed')
            
            # Analyze audio quality
            quality_result = self.quality_analyzer.analyze_file(file_path)
            if quality_result:
                result['quality_score'] = quality_result.get('overall_score', 0)
                result['quality_details'] = quality_result
            
        except Exception as e:
            self.logger.debug(f"Error analyzing {file_path}: {e}")
            result['analysis_error'] = str(e)
        
        return result
    
    def _process_file_for_organization(self, file_path: str) -> Dict[str, Any]:
        """Process a single file for organization."""
        result = {
            'file': file_path,
            'success': False,
            'skipped': False,
            'error': None,
            'destination': None
        }
        
        try:
            # Check if file should be processed
            if self._should_skip_file(file_path):
                result['skipped'] = True
                result['skip_reason'] = 'filtered'
                return result
            
            # Extract metadata
            metadata = self.metadata_manager.extract_metadata_streaming(file_path)
            if not metadata:
                result['error'] = 'metadata_extraction_failed'
                return result
            
            # Determine target location
            genre = metadata.get('genre', 'Unknown')
            decade = self._get_decade(metadata.get('year'))
            
            # Create target structure
            target_dir = self.organizer.create_target_structure_atomic(genre, decade)
            
            # Copy/move file atomically
            if self.dry_run:
                result['destination'] = str(target_dir / f"{metadata.get('artist', 'Unknown')} - {metadata.get('title', Path(file_path).stem)}{Path(file_path).suffix}")
                result['success'] = True
            else:
                destination = self.organizer.copy_file_atomic(
                    Path(file_path),
                    target_dir,
                    metadata
                )
                
                if destination:
                    result['destination'] = str(destination)
                    result['success'] = True
                    self.stats['files_organized'] += 1
                else:
                    result['error'] = 'copy_failed'
            
        except Exception as e:
            self.logger.error(f"Error processing {file_path}: {e}")
            result['error'] = str(e)
        
        return result
    
    def _detect_duplicates_streaming(
        self,
        source_folders: List[str],
        progress_callback: Optional[callable] = None,
        use_fingerprinting: bool = False
    ) -> List[List[Dict[str, Any]]]:
        """Detect duplicates using streaming approach."""
        duplicate_groups = []
        
        if use_fingerprinting and self.config.get('enable_fingerprinting'):
            # Use acoustic fingerprinting
            self.logger.info("Using acoustic fingerprinting for duplicate detection")
            duplicate_groups = self.fingerprinter.find_duplicates_streaming(
                source_folders
            )
        else:
            # Use metadata-based detection
            self.logger.info("Using metadata-based duplicate detection")
            
            # Build metadata index
            metadata_index = defaultdict(list)
            discovery = FileDiscoveryStream(self.streaming_config)
            
            for file_path in discovery.stream_files(source_folders):
                try:
                    metadata = self.metadata_manager.extract_metadata_streaming(file_path)
                    if metadata:
                        # Create signature from metadata
                        signature = self._create_metadata_signature(metadata)
                        if signature:
                            metadata_index[signature].append({
                                'file_path': file_path,
                                'metadata': metadata,
                                'size': os.path.getsize(file_path)
                            })
                    
                    if progress_callback:
                        progress_callback({'phase': 'indexing', 'file': file_path})
                        
                except Exception as e:
                    self.logger.debug(f"Error processing {file_path}: {e}")
            
            # Find groups with multiple files
            for signature, files in metadata_index.items():
                if len(files) > 1:
                    # Add quality scores for duplicate selection
                    for file_info in files:
                        quality = self.quality_analyzer.analyze_file(
                            file_info['file_path']
                        )
                        file_info['quality_score'] = quality.get('overall_score', 0) if quality else 0
                    
                    duplicate_groups.append(files)
        
        self.logger.info(f"Found {len(duplicate_groups)} duplicate groups")
        self.stats['duplicates_found'] = len(duplicate_groups)
        
        return duplicate_groups
    
    def _select_best_duplicate(
        self, 
        duplicate_group: List[Dict[str, Any]]
    ) -> Tuple[str, List[str]]:
        """Select the best file from a duplicate group."""
        # Sort by quality score (highest first)
        sorted_group = sorted(
            duplicate_group,
            key=lambda x: (
                x.get('quality_score', 0),
                x.get('size', 0),
                -len(x.get('file_path', ''))  # Prefer shorter paths
            ),
            reverse=True
        )
        
        keep_file = sorted_group[0]['file_path']
        remove_files = [f['file_path'] for f in sorted_group[1:]]
        
        return keep_file, remove_files
    
    def _handle_duplicates_atomic(self) -> Dict[str, Any]:
        """Handle duplicates with atomic operations."""
        # This would integrate with the duplicate handling logic
        # For now, returning placeholder
        return {
            'handled': self.stats.get('duplicates_found', 0),
            'space_saved': 0
        }
    
    def _optimize_library_structure(
        self,
        source_folders: List[str],
        progress_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """Optimize library structure after cleanup."""
        results = {
            'directories_cleaned': 0,
            'empty_directories_removed': 0
        }
        
        # Clean up empty directories
        for folder in source_folders:
            for root, dirs, files in os.walk(folder, topdown=False):
                if not files and not dirs:
                    if not self.dry_run:
                        try:
                            os.rmdir(root)
                            results['empty_directories_removed'] += 1
                        except Exception as e:
                            self.logger.debug(f"Could not remove {root}: {e}")
        
        return results
    
    def _create_checkpoint(self, checkpoint_type: str, data: Dict[str, Any]):
        """Create a recovery checkpoint."""
        if self.enable_recovery and self.recovery_manager:
            try:
                self.recovery_manager.create_checkpoint(
                    CheckpointType.MANUAL,
                    f"Orchestrator: {checkpoint_type}",
                    {
                        'orchestrator_stats': dict(self.stats),
                        'checkpoint_data': data
                    }
                )
            except Exception as e:
                self.logger.warning(f"Failed to create checkpoint: {e}")
    
    def _should_skip_file(self, file_path: str) -> bool:
        """Check if file should be skipped."""
        # Check protected paths
        protected_paths = self.config.get('protected_paths', [])
        for protected in protected_paths:
            if file_path.startswith(protected):
                return True
        
        # Check file extension
        ext = Path(file_path).suffix.lower()
        allowed_formats = self.config.get('audio_formats', [])
        if allowed_formats and ext not in allowed_formats:
            return True
        
        return False
    
    def _create_metadata_signature(self, metadata: Dict[str, Any]) -> Optional[str]:
        """Create a signature from metadata for duplicate detection."""
        artist = metadata.get('artist', '').lower().strip()
        title = metadata.get('title', '').lower().strip()
        
        if not artist or not title:
            return None
        
        # Create normalized signature
        signature = f"{artist}|{title}"
        
        # Optionally include duration for more accuracy
        duration = metadata.get('duration')
        if duration:
            signature += f"|{int(duration)}"
        
        return signature
    
    def _get_decade(self, year: Optional[int]) -> str:
        """Get decade from year."""
        if not year:
            return "Unknown"
        
        try:
            decade = (int(year) // 10) * 10
            return f"{decade}s"
        except:
            return "Unknown"
    
    def _categorize_quality(self, bitrate: int) -> str:
        """Categorize audio quality based on bitrate."""
        if bitrate >= 320:
            return "lossless"
        elif bitrate >= 256:
            return "high"
        elif bitrate >= 192:
            return "good"
        elif bitrate >= 128:
            return "acceptable"
        else:
            return "low"
    
    def _generate_analysis_report(self, results: Dict[str, Any], report_path: str):
        """Generate analysis report."""
        try:
            from ..utils.reporting import ReportGenerator
            
            generator = ReportGenerator()
            generator.generate_analysis_report(
                results,
                report_path,
                title=f"Music Library Analysis - {self.session_id}"
            )
            
            self.logger.info(f"Analysis report saved to: {report_path}")
            
        except Exception as e:
            self.logger.error(f"Failed to generate report: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get current orchestrator statistics."""
        duration = time.time() - self.start_time if self.start_time else 0
        
        return {
            'session_id': self.session_id,
            'operation_group': self.operation_group,
            'statistics': dict(self.stats),
            'duration_seconds': duration,
            'memory_usage': self.memory_monitor.get_current_usage(),
            'recovery_enabled': self.enable_recovery,
            'dry_run': self.dry_run
        }
    
    def cleanup(self):
        """Clean up resources."""
        # Shutdown recovery manager
        if self.recovery_manager:
            self.recovery_manager.shutdown()
        
        # Clean up modules
        if self._fingerprinter:
            self._fingerprinter.cleanup()
        
        # Clean up atomic operations
        if self.atomic_ops:
            self.atomic_ops.cleanup_old_backups()
        
        self.logger.info("Orchestrator cleanup completed")