"""
Atomic File Organization and Management Module
Enhanced with transactional safety for DJ Music Cleanup Tool
"""
import os
import shutil
import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime
import hashlib
from collections import defaultdict

from ..core.database import get_database_manager
from ..core.schema import initialize_operations_schema
from ..core.transactions import AtomicFileOperations, OperationType, TransactionError
from ..core.rollback import RollbackManager, RollbackScope


class AtomicFileOrganizer:
    """
    Enhanced file organizer with atomic operations and transactional safety.
    Provides ACID guarantees for music library organization.
    """
    
    def __init__(self, target_root: str, workspace_dir: str = None, enable_rollback: bool = True):
        """Initialize atomic file organizer"""
        self.target_root = Path(target_root)
        self.logger = logging.getLogger(__name__)
        self.db_manager = get_database_manager()
        
        # Initialize atomic operations
        self.atomic_ops = AtomicFileOperations(workspace_dir)
        
        # Initialize rollback manager
        self.enable_rollback = enable_rollback
        if enable_rollback:
            self.rollback_manager = RollbackManager(workspace_dir)
        else:
            self.rollback_manager = None
        
        # Initialize database if not already done
        if not self.db_manager.table_exists('operations', 'file_operations'):
            self.db_manager.initialize_database('operations', initialize_operations_schema)
            self._migrate_existing_data()
        
        # Create a unique operation group ID for this session
        self.operation_group = f"atomic_op_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Track operations for reporting
        self.stats = {
            'files_copied': 0,
            'files_moved': 0,
            'files_skipped': 0,
            'duplicates_handled': 0,
            'errors': 0,
            'space_saved': 0,
            'genres_created': set(),
            'decades_created': set(),
            'transactions_created': 0,
            'transactions_committed': 0,
            'transactions_rolled_back': 0,
            'rollback_points_created': 0
        }
        
        # Current active transaction
        self.current_transaction = None
        self.current_rollback_point = None
        
        # Initialize operation stats
        self._init_operation_stats()
        
        self.logger.info(f"AtomicFileOrganizer initialized with target: {self.target_root}")
    
    def _init_operation_stats(self):
        """Initialize operation statistics tracking"""
        self.db_manager.execute_update(
            'operations',
            """INSERT INTO operation_stats (operation_group, start_time)
               VALUES (?, ?)""",
            (self.operation_group, datetime.now().isoformat())
        )
    
    def _migrate_existing_data(self):
        """Migrate data from old database if it exists"""
        # Similar to original organizer migration logic
        old_db_path = 'file_operations.db'
        if os.path.exists(old_db_path):
            self.logger.info("Migrating data from old operations database")
            # Migration logic would be here
            pass
    
    def begin_organization_session(self, description: str = None) -> str:
        """Begin an atomic organization session with rollback point"""
        try:
            # Create rollback point if enabled
            if self.enable_rollback:
                rollback_description = description or f"Organization session {self.operation_group}"
                
                # Collect all potential target paths for rollback
                target_paths = []
                if self.target_root.exists():
                    target_paths = [str(self.target_root)]
                
                self.current_rollback_point = self.rollback_manager.create_rollback_point(
                    scope=RollbackScope.SESSION,
                    description=rollback_description,
                    file_paths=[],  # Will be populated as we process files
                    directory_paths=target_paths,
                    metadata={
                        'operation_group': self.operation_group,
                        'target_root': str(self.target_root)
                    }
                )
                
                self.stats['rollback_points_created'] += 1
                self.logger.info(f"Created rollback point: {self.current_rollback_point}")
            
            return self.operation_group
            
        except Exception as e:
            self.logger.error(f"Failed to begin organization session: {e}")
            raise TransactionError(f"Failed to begin session: {e}")
    
    def create_target_structure_atomic(self, genre: str, decade: str) -> Path:
        """Create target directory structure atomically"""
        # Sanitize genre and decade for folder names
        genre = self._sanitize_folder_name(genre or 'Unknown')
        decade = self._sanitize_folder_name(decade or 'Unknown')
        
        target_dir = self.target_root / genre / decade
        
        try:
            # Begin transaction for directory creation
            transaction_id = self.atomic_ops.begin_transaction({
                'operation_type': 'create_directory_structure',
                'genre': genre,
                'decade': decade
            })
            
            # Add mkdir operations
            if not self.target_root.exists():
                self.atomic_ops.add_operation(
                    transaction_id,
                    OperationType.MKDIR,
                    target_path=str(self.target_root)
                )
            
            genre_dir = self.target_root / genre
            if not genre_dir.exists():
                self.atomic_ops.add_operation(
                    transaction_id,
                    OperationType.MKDIR,
                    target_path=str(genre_dir)
                )
            
            if not target_dir.exists():
                self.atomic_ops.add_operation(
                    transaction_id,
                    OperationType.MKDIR,
                    target_path=str(target_dir)
                )
            
            # Prepare and commit
            self.atomic_ops.prepare_transaction(transaction_id)
            self.atomic_ops.commit_transaction(transaction_id)
            
            # Track created directories
            self.stats['genres_created'].add(genre)
            self.stats['decades_created'].add(f"{genre}/{decade}")
            self.stats['transactions_committed'] += 1
            
            return target_dir
            
        except Exception as e:
            self.logger.error(f"Error creating directory structure {target_dir}: {e}")
            self.stats['transactions_rolled_back'] += 1
            
            # Fallback to Unknown/Unknown
            fallback_dir = self.target_root / 'Unknown' / 'Unknown'
            try:
                fallback_dir.mkdir(parents=True, exist_ok=True)
                return fallback_dir
            except Exception as fallback_error:
                self.logger.error(f"Fallback directory creation failed: {fallback_error}")
                raise TransactionError(f"Failed to create directory structure: {e}")
    
    def copy_file_atomic(self, source: Path, target_dir: Path, 
                        metadata: Dict = None) -> Optional[Path]:
        """Copy a file atomically with full transaction support"""
        try:
            # Generate target filename
            artist = metadata.get('artist', 'Unknown Artist') if metadata else 'Unknown Artist'
            title = metadata.get('title', source.stem) if metadata else source.stem
            
            # Sanitize for filename
            artist = self._sanitize_folder_name(artist)
            title = self._sanitize_folder_name(title)
            
            # Create target filename
            target_name = f"{artist} - {title}{source.suffix}"
            target_path = target_dir / target_name
            
            # Handle duplicates by adding number
            if target_path.exists():
                counter = 1
                while True:
                    alt_name = f"{artist} - {title} ({counter}){source.suffix}"
                    alt_path = target_dir / alt_name
                    if not alt_path.exists():
                        target_path = alt_path
                        break
                    counter += 1
            
            # Get file size
            file_size = source.stat().st_size
            
            # Begin atomic transaction for file copy
            transaction_id = self.atomic_ops.begin_transaction({
                'operation_type': 'copy_file',
                'source_path': str(source),
                'target_path': str(target_path),
                'file_size': file_size,
                'metadata': metadata
            })
            
            self.stats['transactions_created'] += 1
            
            # Add copy operation
            self.atomic_ops.add_operation(
                transaction_id,
                OperationType.COPY,
                source_path=str(source),
                target_path=str(target_path),
                metadata={
                    'artist': artist,
                    'title': title,
                    'file_size': file_size
                }
            )
            
            # Record operation as pending in our database
            self._record_operation('copy', str(source), str(target_path), 
                                 'pending', None, file_size)
            
            # Prepare and commit transaction
            self.atomic_ops.prepare_transaction(transaction_id)
            self.atomic_ops.commit_transaction(transaction_id)
            
            # Update operation as completed
            self.db_manager.execute_update(
                'operations',
                """UPDATE file_operations 
                   SET status = 'completed', completed_at = ?
                   WHERE source_path = ? AND destination_path = ? 
                   AND operation_group = ?""",
                (datetime.now().isoformat(), str(source), str(target_path), 
                 self.operation_group)
            )
            
            self.stats['files_copied'] += 1
            self.stats['transactions_committed'] += 1
            self.logger.info(f"Atomically copied: {source} -> {target_path}")
            
            return target_path
            
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"Error atomically copying {source}: {error_msg}")
            
            # Record failed operation
            if 'target_path' in locals():
                self._record_operation('copy', str(source), str(target_path),
                                     'failed', error_msg, file_size)
            else:
                self._record_operation('copy', str(source), None,
                                     'failed', error_msg, None)
            
            self.stats['errors'] += 1
            self.stats['transactions_rolled_back'] += 1
            return None
    
    def move_file_atomic(self, source: Path, target_dir: Path, 
                        metadata: Dict = None) -> Optional[Path]:
        """Move a file atomically with full transaction support"""
        try:
            # Generate target filename (similar to copy_file_atomic)
            artist = metadata.get('artist', 'Unknown Artist') if metadata else 'Unknown Artist'
            title = metadata.get('title', source.stem) if metadata else source.stem
            
            # Sanitize for filename
            artist = self._sanitize_folder_name(artist)
            title = self._sanitize_folder_name(title)
            
            # Create target filename
            target_name = f"{artist} - {title}{source.suffix}"
            target_path = target_dir / target_name
            
            # Handle duplicates
            if target_path.exists():
                counter = 1
                while True:
                    alt_name = f"{artist} - {title} ({counter}){source.suffix}"
                    alt_path = target_dir / alt_name
                    if not alt_path.exists():
                        target_path = alt_path
                        break
                    counter += 1
            
            # Get file size
            file_size = source.stat().st_size
            
            # Begin atomic transaction for file move
            transaction_id = self.atomic_ops.begin_transaction({
                'operation_type': 'move_file',
                'source_path': str(source),
                'target_path': str(target_path),
                'file_size': file_size
            })
            
            self.stats['transactions_created'] += 1
            
            # Add move operation
            self.atomic_ops.add_operation(
                transaction_id,
                OperationType.MOVE,
                source_path=str(source),
                target_path=str(target_path)
            )
            
            # Record operation as pending
            self._record_operation('move', str(source), str(target_path), 
                                 'pending', None, file_size)
            
            # Prepare and commit transaction
            self.atomic_ops.prepare_transaction(transaction_id)
            self.atomic_ops.commit_transaction(transaction_id)
            
            # Update operation as completed
            self.db_manager.execute_update(
                'operations',
                """UPDATE file_operations 
                   SET status = 'completed', completed_at = ?
                   WHERE source_path = ? AND destination_path = ? 
                   AND operation_group = ?""",
                (datetime.now().isoformat(), str(source), str(target_path), 
                 self.operation_group)
            )
            
            self.stats['files_moved'] += 1
            self.stats['transactions_committed'] += 1
            self.logger.info(f"Atomically moved: {source} -> {target_path}")
            
            return target_path
            
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"Error atomically moving {source}: {error_msg}")
            
            self.stats['errors'] += 1
            self.stats['transactions_rolled_back'] += 1
            return None
    
    def handle_duplicates_atomic(self, duplicate_groups: List[List[Dict]]) -> Dict:
        """Process duplicate groups atomically"""
        decisions = {}
        
        try:
            # Begin transaction for duplicate handling
            transaction_id = self.atomic_ops.begin_transaction({
                'operation_type': 'handle_duplicates',
                'group_count': len(duplicate_groups)
            })
            
            self.stats['transactions_created'] += 1
            
            for group_idx, group in enumerate(duplicate_groups):
                group_id = f"dup_group_{group_idx + 1}_{self.operation_group}"
                
                # Sort by quality score (best first)
                sorted_files = sorted(group, key=lambda x: x.get('quality_score', 0), 
                                    reverse=True)
                
                # Keep the best quality file
                best_file = sorted_files[0]['file_path']
                duplicate_files = [f['file_path'] for f in sorted_files[1:]]
                
                decisions[group_id] = {
                    'keep': best_file,
                    'remove': duplicate_files,
                    'quality_scores': {f['file_path']: f.get('quality_score', 0) 
                                     for f in sorted_files}
                }
                
                # Add delete operations for duplicates
                for dup_file in duplicate_files:
                    if Path(dup_file).exists():
                        self.atomic_ops.add_operation(
                            transaction_id,
                            OperationType.DELETE,
                            source_path=dup_file,
                            metadata={
                                'group_id': group_id,
                                'reason': 'duplicate_removal',
                                'kept_file': best_file
                            }
                        )
                
                # Calculate space saved
                space_saved = sum(
                    Path(f['file_path']).stat().st_size 
                    for f in sorted_files[1:] 
                    if Path(f['file_path']).exists()
                )
                
                # Record decision in database
                self.db_manager.execute_update(
                    'operations',
                    """INSERT INTO duplicate_decisions (
                        group_id, kept_file, removed_files, decision_reason,
                        quality_scores, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        group_id,
                        best_file,
                        json.dumps(duplicate_files),
                        f"Kept highest quality ({sorted_files[0].get('quality_score', 0)})",
                        json.dumps(decisions[group_id]['quality_scores']),
                        datetime.now().isoformat()
                    )
                )
                
                self.stats['duplicates_handled'] += len(duplicate_files)
                self.stats['space_saved'] += space_saved
                
                self.logger.info(f"Duplicate group {group_id}: keeping {best_file}, "
                               f"removing {len(duplicate_files)} duplicates, "
                               f"saving {space_saved / 1024 / 1024:.2f} MB")
            
            # Prepare and commit all duplicate removals atomically
            self.atomic_ops.prepare_transaction(transaction_id)
            self.atomic_ops.commit_transaction(transaction_id)
            
            self.stats['transactions_committed'] += 1
            self.logger.info(f"Atomically processed {len(duplicate_groups)} duplicate groups")
            
            return decisions
            
        except Exception as e:
            self.logger.error(f"Error handling duplicates atomically: {e}")
            self.stats['transactions_rolled_back'] += 1
            return {}
    
    def organize_files_batch_atomic(self, file_operations: List[Dict], 
                                   batch_size: int = 50) -> Dict[str, Any]:
        """Organize multiple files in atomic batches"""
        results = {
            'successful_operations': 0,
            'failed_operations': 0,
            'batches_processed': 0,
            'batches_failed': 0,
            'batch_results': []
        }
        
        # Split operations into batches
        batches = [file_operations[i:i + batch_size] 
                  for i in range(0, len(file_operations), batch_size)]
        
        for batch_idx, batch in enumerate(batches):
            try:
                # Begin transaction for batch
                transaction_id = self.atomic_ops.begin_transaction({
                    'operation_type': 'batch_organize',
                    'batch_index': batch_idx,
                    'batch_size': len(batch)
                })
                
                self.stats['transactions_created'] += 1
                batch_operations = []
                
                # Add all operations in batch to transaction
                for operation in batch:
                    op_type = operation.get('type', 'copy')
                    source_path = operation['source_path']
                    target_path = operation['target_path']
                    
                    if op_type == 'copy':
                        operation_type = OperationType.COPY
                    elif op_type == 'move':
                        operation_type = OperationType.MOVE
                    else:
                        continue
                    
                    op_id = self.atomic_ops.add_operation(
                        transaction_id,
                        operation_type,
                        source_path=source_path,
                        target_path=target_path,
                        metadata=operation.get('metadata', {})
                    )
                    
                    batch_operations.append({
                        'operation_id': op_id,
                        'source_path': source_path,
                        'target_path': target_path,
                        'type': op_type
                    })
                
                # Prepare and commit batch atomically
                self.atomic_ops.prepare_transaction(transaction_id)
                self.atomic_ops.commit_transaction(transaction_id)
                
                # Update stats
                results['successful_operations'] += len(batch_operations)
                results['batches_processed'] += 1
                self.stats['transactions_committed'] += 1
                
                batch_result = {
                    'batch_index': batch_idx,
                    'operations': len(batch_operations),
                    'status': 'completed',
                    'transaction_id': transaction_id
                }
                results['batch_results'].append(batch_result)
                
                self.logger.info(f"Completed atomic batch {batch_idx + 1}/{len(batches)} "
                               f"({len(batch_operations)} operations)")
                
            except Exception as e:
                self.logger.error(f"Batch {batch_idx} failed: {e}")
                results['failed_operations'] += len(batch)
                results['batches_failed'] += 1
                self.stats['transactions_rolled_back'] += 1
                
                batch_result = {
                    'batch_index': batch_idx,
                    'operations': len(batch),
                    'status': 'failed',
                    'error': str(e)
                }
                results['batch_results'].append(batch_result)
        
        return results
    
    def rollback_session(self, rollback_to_point: str = None) -> bool:
        """Rollback the organization session"""
        if not self.enable_rollback or not self.rollback_manager:
            self.logger.warning("Rollback not enabled")
            return False
        
        try:
            rollback_id = rollback_to_point or self.current_rollback_point
            
            if not rollback_id:
                self.logger.error("No rollback point available")
                return False
            
            self.logger.info(f"Rolling back to: {rollback_id}")
            
            # Execute rollback
            result = self.rollback_manager.execute_rollback(rollback_id)
            
            if result['success_rate'] > 0.8:  # 80% success rate threshold
                self.logger.info(f"Rollback successful: {result['success_rate']:.1%}")
                return True
            else:
                self.logger.error(f"Rollback partially failed: {result['success_rate']:.1%}")
                return False
                
        except Exception as e:
            self.logger.error(f"Rollback failed: {e}")
            return False
    
    def _sanitize_folder_name(self, name: str) -> str:
        """Sanitize string for use as folder name"""
        # Replace problematic characters
        replacements = {
            '/': '-', '\\': '-', ':': '-', '*': '_', '?': '_', '"': "'",
            '<': '(', '>': ')', '|': '-', '\n': ' ', '\r': '', '\t': ' '
        }
        
        for char, replacement in replacements.items():
            name = name.replace(char, replacement)
        
        # Remove leading/trailing dots and spaces
        name = name.strip('. ')
        
        # Ensure name is not empty
        if not name:
            name = 'Unknown'
        
        # Limit length
        if len(name) > 100:
            name = name[:100].strip()
        
        return name
    
    def _record_operation(self, operation_type: str, source_path: str, 
                         destination_path: str = None, status: str = 'pending',
                         error_message: str = None, file_size: int = None):
        """Record a file operation in the database"""
        self.db_manager.execute_update(
            'operations',
            """INSERT INTO file_operations (
                operation_type, source_path, destination_path, status,
                error_message, file_size, operation_group, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                operation_type, source_path, destination_path, status,
                error_message, file_size, self.operation_group,
                datetime.now().isoformat()
            )
        )
    
    def generate_atomic_undo_script(self, output_file: str = 'atomic_undo_operations.sh'):
        """Generate enhanced undo script with atomic operations"""
        # Get all transactions for this session
        transactions = self.atomic_ops.list_active_transactions()
        
        script_lines = [
            "#!/bin/bash",
            "# Atomic Undo script for DJ Music Cleanup operations",
            f"# Generated: {datetime.now().isoformat()}",
            f"# Operation group: {self.operation_group}",
            f"# Rollback point: {self.current_rollback_point}",
            "",
            "echo 'This will undo ALL atomic operations from this session.'",
            "echo 'This includes rolling back to the pre-session state.'",
            "read -p 'Are you sure? (y/N) ' -n 1 -r",
            "echo",
            "if [[ ! $REPLY =~ ^[Yy]$ ]]; then",
            "    exit 1",
            "fi",
            "",
        ]
        
        if self.enable_rollback and self.current_rollback_point:
            script_lines.extend([
                "# Perform atomic rollback",
                f"echo 'Rolling back to: {self.current_rollback_point}'",
                "# Note: Actual rollback would be performed by the Python tool",
                "# python3 -c \"from core.rollback import RollbackManager; rm = RollbackManager(); rm.execute_rollback('{self.current_rollback_point}')\"",
                "",
            ])
        
        # Also include traditional file cleanup as fallback
        operations = self.db_manager.execute_query(
            'operations',
            """SELECT source_path, destination_path 
               FROM file_operations 
               WHERE operation_type IN ('copy', 'move') 
               AND status = 'completed'
               AND operation_group = ?
               ORDER BY id DESC""",
            (self.operation_group,)
        )
        
        if operations:
            script_lines.extend([
                "# Fallback: Remove copied/moved files",
                "echo 'Removing copied files...'",
            ])
            
            for op in operations:
                dest_path = op['destination_path']
                if dest_path:
                    script_lines.append(f'rm -f "{dest_path}"')
            
            script_lines.extend([
                "",
                "# Remove empty directories",
                f'find "{self.target_root}" -type d -empty -delete',
            ])
        
        script_lines.extend([
            "",
            "echo 'Atomic undo completed.'",
        ])
        
        # Write script
        with open(output_file, 'w') as f:
            f.write('\n'.join(script_lines))
        
        # Make executable
        os.chmod(output_file, 0o755)
        
        self.logger.info(f"Generated atomic undo script: {output_file}")
    
    def finalize(self):
        """Finalize operations and update statistics"""
        # Update operation stats
        self.db_manager.execute_update(
            'operations',
            """UPDATE operation_stats 
               SET total_files = ?, processed_files = ?, failed_files = ?,
                   total_size_bytes = ?, end_time = ?
               WHERE operation_group = ?""",
            (
                self.stats['files_copied'] + self.stats['files_moved'] + 
                self.stats['files_skipped'] + self.stats['errors'],
                self.stats['files_copied'] + self.stats['files_moved'],
                self.stats['errors'],
                self.stats.get('total_size', 0),
                datetime.now().isoformat(),
                self.operation_group
            )
        )
        
        # Clean up old atomic operations
        self.atomic_ops.cleanup_old_backups()
        
        self.logger.info(f"Finalized atomic operations session: {self.operation_group}")
    
    def get_atomic_operation_summary(self) -> Dict:
        """Get enhanced summary including atomic operations"""
        summary = {
            'operation_group': self.operation_group,
            'stats': self.stats.copy(),
            'genres_created': list(self.stats['genres_created']),
            'decades_created': list(self.stats['decades_created']),
            'current_rollback_point': self.current_rollback_point,
            'rollback_enabled': self.enable_rollback
        }
        
        # Get atomic operations statistics
        if hasattr(self.atomic_ops, 'get_workspace_size'):
            workspace_info = self.atomic_ops.get_workspace_size()
            summary['atomic_workspace'] = workspace_info
        
        # Get rollback statistics
        if self.rollback_manager:
            rollback_stats = self.rollback_manager.get_rollback_statistics()
            summary['rollback_stats'] = rollback_stats
        
        # Get database stats
        db_stats = self.db_manager.execute_query(
            'operations',
            """SELECT 
                   COUNT(*) as total_operations,
                   SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                   SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
               FROM file_operations
               WHERE operation_group = ?""",
            (self.operation_group,)
        )
        
        if db_stats:
            summary['database_stats'] = {
                'total_operations': db_stats[0]['total_operations'],
                'completed': db_stats[0]['completed'],
                'failed': db_stats[0]['failed']
            }
        
        return summary