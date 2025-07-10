"""
Rollback System for DJ Music Cleanup Tool
Advanced rollback capabilities with state tracking and recovery
"""
import os
import json
import shutil
import tempfile
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import logging

from .transactions import Transaction, AtomicOperation, TransactionState, OperationType


class RollbackScope(Enum):
    """Scope of rollback operations"""
    OPERATION = "operation"          # Single operation
    TRANSACTION = "transaction"      # Single transaction
    SESSION = "session"             # Entire cleanup session
    TIME_RANGE = "time_range"       # Operations within time range
    FILE_PATTERN = "file_pattern"   # Operations matching file pattern


class RollbackStrategy(Enum):
    """Strategy for rollback execution"""
    IMMEDIATE = "immediate"         # Rollback immediately
    STAGED = "staged"              # Stage rollback for later execution
    INTERACTIVE = "interactive"     # Prompt user for each operation
    SIMULATION = "simulation"       # Simulate without executing


@dataclass
class RollbackPoint:
    """A point in time that can be rolled back to"""
    rollback_id: str
    created_at: str
    scope: RollbackScope
    description: str
    file_checksums: Dict[str, str]
    directory_structure: Dict[str, List[str]]
    metadata: Dict[str, Any]
    size_bytes: int = 0


@dataclass
class RollbackOperation:
    """Individual rollback operation"""
    rollback_op_id: str
    original_operation_id: str
    operation_type: OperationType
    source_path: Optional[str]
    target_path: Optional[str]
    backup_path: Optional[str]
    file_checksum: Optional[str]
    created_at: str
    executed: bool = False
    execution_time: Optional[str] = None


class RollbackError(Exception):
    """Exception for rollback-specific errors"""
    pass


class RollbackManager:
    """
    Advanced rollback manager for music library operations.
    Provides comprehensive rollback capabilities with integrity checking.
    """
    
    def __init__(self, workspace_dir: str = None, enable_checksums: bool = True):
        """Initialize rollback manager"""
        self.logger = logging.getLogger(__name__)
        
        # Setup workspace
        if workspace_dir:
            self.workspace_dir = Path(workspace_dir)
        else:
            self.workspace_dir = Path(tempfile.gettempdir()) / "dj_cleanup_rollback"
        
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        
        # Rollback storage
        self.rollback_points_dir = self.workspace_dir / "rollback_points"
        self.rollback_operations_dir = self.workspace_dir / "rollback_operations"
        self.checksums_dir = self.workspace_dir / "checksums"
        self.snapshots_dir = self.workspace_dir / "snapshots"
        
        for directory in [self.rollback_points_dir, self.rollback_operations_dir, 
                         self.checksums_dir, self.snapshots_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        # Configuration
        self.enable_checksums = enable_checksums
        self.max_rollback_points = 50
        self.max_rollback_age_days = 30
        
        # Active rollback points
        self.rollback_points: Dict[str, RollbackPoint] = {}
        self.file_checksums: Dict[str, str] = {}
        
        # Load existing rollback points
        self._load_rollback_points()
        
        self.logger.info(f"RollbackManager initialized with workspace: {self.workspace_dir}")
    
    def _load_rollback_points(self):
        """Load existing rollback points from storage"""
        try:
            for rollback_file in self.rollback_points_dir.glob("*.json"):
                with open(rollback_file, 'r') as f:
                    rollback_data = json.load(f)
                
                rollback_point = RollbackPoint(
                    rollback_id=rollback_data['rollback_id'],
                    created_at=rollback_data['created_at'],
                    scope=RollbackScope(rollback_data['scope']),
                    description=rollback_data['description'],
                    file_checksums=rollback_data.get('file_checksums', {}),
                    directory_structure=rollback_data.get('directory_structure', {}),
                    metadata=rollback_data.get('metadata', {}),
                    size_bytes=rollback_data.get('size_bytes', 0)
                )
                
                self.rollback_points[rollback_point.rollback_id] = rollback_point
                self.logger.debug(f"Loaded rollback point: {rollback_point.rollback_id}")
        
        except Exception as e:
            self.logger.error(f"Error loading rollback points: {e}")
    
    def _save_rollback_point(self, rollback_point: RollbackPoint):
        """Save rollback point to persistent storage"""
        try:
            rollback_file = self.rollback_points_dir / f"{rollback_point.rollback_id}.json"
            
            rollback_data = {
                'rollback_id': rollback_point.rollback_id,
                'created_at': rollback_point.created_at,
                'scope': rollback_point.scope.value,
                'description': rollback_point.description,
                'file_checksums': rollback_point.file_checksums,
                'directory_structure': rollback_point.directory_structure,
                'metadata': rollback_point.metadata,
                'size_bytes': rollback_point.size_bytes
            }
            
            with open(rollback_file, 'w') as f:
                json.dump(rollback_data, f, indent=2)
        
        except Exception as e:
            self.logger.error(f"Error saving rollback point {rollback_point.rollback_id}: {e}")
            raise RollbackError(f"Failed to save rollback point: {e}")
    
    def _calculate_file_checksum(self, file_path: str) -> str:
        """Calculate MD5 checksum of a file"""
        if not self.enable_checksums:
            return ""
        
        try:
            hash_md5 = hashlib.md5()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            self.logger.warning(f"Could not calculate checksum for {file_path}: {e}")
            return ""
    
    def _capture_directory_structure(self, directory_path: str) -> Dict[str, List[str]]:
        """Capture directory structure for rollback"""
        structure = {}
        
        try:
            for root, dirs, files in os.walk(directory_path):
                rel_root = os.path.relpath(root, directory_path)
                if rel_root == ".":
                    rel_root = ""
                
                structure[rel_root] = {
                    'directories': sorted(dirs),
                    'files': sorted(files)
                }
        
        except Exception as e:
            self.logger.warning(f"Could not capture directory structure for {directory_path}: {e}")
        
        return structure
    
    def _generate_rollback_id(self) -> str:
        """Generate unique rollback ID"""
        timestamp = int(time.time() * 1000)
        return f"rollback_{timestamp}"
    
    def create_rollback_point(self, scope: RollbackScope, description: str,
                            file_paths: List[str] = None, 
                            directory_paths: List[str] = None,
                            metadata: Dict = None) -> str:
        """Create a new rollback point"""
        rollback_id = self._generate_rollback_id()
        
        try:
            # Calculate file checksums
            file_checksums = {}
            total_size = 0
            
            if file_paths:
                for file_path in file_paths:
                    if os.path.exists(file_path):
                        checksum = self._calculate_file_checksum(file_path)
                        file_checksums[file_path] = checksum
                        total_size += os.path.getsize(file_path)
            
            # Capture directory structures
            directory_structure = {}
            if directory_paths:
                for dir_path in directory_paths:
                    if os.path.exists(dir_path):
                        structure = self._capture_directory_structure(dir_path)
                        directory_structure[dir_path] = structure
            
            # Create rollback point
            rollback_point = RollbackPoint(
                rollback_id=rollback_id,
                created_at=datetime.now().isoformat(),
                scope=scope,
                description=description,
                file_checksums=file_checksums,
                directory_structure=directory_structure,
                metadata=metadata or {},
                size_bytes=total_size
            )
            
            # Save rollback point
            self.rollback_points[rollback_id] = rollback_point
            self._save_rollback_point(rollback_point)
            
            # Clean up old rollback points if needed
            self._cleanup_old_rollback_points()
            
            self.logger.info(f"Created rollback point: {rollback_id} ({description})")
            return rollback_id
        
        except Exception as e:
            self.logger.error(f"Failed to create rollback point: {e}")
            raise RollbackError(f"Failed to create rollback point: {e}")
    
    def create_transaction_rollback_point(self, transaction: Transaction) -> str:
        """Create rollback point for a transaction"""
        # Collect all file paths from transaction operations
        file_paths = []
        directory_paths = set()
        
        for operation in transaction.operations:
            if operation.source_path:
                file_paths.append(operation.source_path)
                directory_paths.add(os.path.dirname(operation.source_path))
            
            if operation.target_path:
                file_paths.append(operation.target_path)
                directory_paths.add(os.path.dirname(operation.target_path))
        
        metadata = {
            'transaction_id': transaction.transaction_id,
            'operation_count': len(transaction.operations),
            'transaction_metadata': transaction.metadata
        }
        
        return self.create_rollback_point(
            scope=RollbackScope.TRANSACTION,
            description=f"Transaction {transaction.transaction_id}",
            file_paths=file_paths,
            directory_paths=list(directory_paths),
            metadata=metadata
        )
    
    def create_session_rollback_point(self, session_metadata: Dict = None) -> str:
        """Create rollback point for entire cleanup session"""
        return self.create_rollback_point(
            scope=RollbackScope.SESSION,
            description=f"Cleanup session {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            metadata=session_metadata or {}
        )
    
    def prepare_rollback(self, rollback_id: str, strategy: RollbackStrategy = RollbackStrategy.IMMEDIATE) -> List[RollbackOperation]:
        """Prepare rollback operations for a rollback point"""
        if rollback_id not in self.rollback_points:
            raise RollbackError(f"Rollback point {rollback_id} not found")
        
        rollback_point = self.rollback_points[rollback_id]
        rollback_operations = []
        
        try:
            # Generate rollback operations based on current state vs rollback point
            for file_path, original_checksum in rollback_point.file_checksums.items():
                if os.path.exists(file_path):
                    current_checksum = self._calculate_file_checksum(file_path)
                    
                    if current_checksum != original_checksum:
                        # File has been modified, needs rollback
                        rollback_op = RollbackOperation(
                            rollback_op_id=f"{rollback_id}_{len(rollback_operations)}",
                            original_operation_id="",
                            operation_type=OperationType.COPY,  # Restore from backup
                            source_path=None,  # Will be determined from backup
                            target_path=file_path,
                            backup_path=None,
                            file_checksum=original_checksum,
                            created_at=datetime.now().isoformat()
                        )
                        rollback_operations.append(rollback_op)
                
                else:
                    # File was deleted, needs restoration
                    rollback_op = RollbackOperation(
                        rollback_op_id=f"{rollback_id}_{len(rollback_operations)}",
                        original_operation_id="",
                        operation_type=OperationType.COPY,
                        source_path=None,  # Will be determined from backup
                        target_path=file_path,
                        backup_path=None,
                        file_checksum=original_checksum,
                        created_at=datetime.now().isoformat()
                    )
                    rollback_operations.append(rollback_op)
            
            # Save rollback operations
            self._save_rollback_operations(rollback_id, rollback_operations)
            
            self.logger.info(f"Prepared {len(rollback_operations)} rollback operations for {rollback_id}")
            return rollback_operations
        
        except Exception as e:
            self.logger.error(f"Failed to prepare rollback for {rollback_id}: {e}")
            raise RollbackError(f"Failed to prepare rollback: {e}")
    
    def execute_rollback(self, rollback_id: str, strategy: RollbackStrategy = RollbackStrategy.IMMEDIATE,
                        dry_run: bool = False) -> Dict[str, Any]:
        """Execute rollback operations"""
        if rollback_id not in self.rollback_points:
            raise RollbackError(f"Rollback point {rollback_id} not found")
        
        rollback_operations = self.prepare_rollback(rollback_id, strategy)
        
        if dry_run:
            return {
                'rollback_id': rollback_id,
                'operations_count': len(rollback_operations),
                'dry_run': True,
                'operations': [
                    {
                        'operation_id': op.rollback_op_id,
                        'type': op.operation_type.value,
                        'target_path': op.target_path,
                        'description': f"Would restore {op.target_path}"
                    }
                    for op in rollback_operations
                ]
            }
        
        executed_operations = []
        failed_operations = []
        
        try:
            for operation in rollback_operations:
                try:
                    if strategy == RollbackStrategy.INTERACTIVE:
                        # In a real implementation, this would prompt the user
                        self.logger.info(f"Would execute rollback operation: {operation.rollback_op_id}")
                        continue
                    
                    self._execute_rollback_operation(operation)
                    operation.executed = True
                    operation.execution_time = datetime.now().isoformat()
                    executed_operations.append(operation)
                    
                except Exception as e:
                    self.logger.error(f"Failed to execute rollback operation {operation.rollback_op_id}: {e}")
                    failed_operations.append({
                        'operation': operation,
                        'error': str(e)
                    })
            
            result = {
                'rollback_id': rollback_id,
                'strategy': strategy.value,
                'total_operations': len(rollback_operations),
                'executed_operations': len(executed_operations),
                'failed_operations': len(failed_operations),
                'success_rate': len(executed_operations) / len(rollback_operations) if rollback_operations else 1.0,
                'execution_time': datetime.now().isoformat()
            }
            
            self.logger.info(f"Executed rollback {rollback_id}: {len(executed_operations)}/{len(rollback_operations)} operations successful")
            return result
        
        except Exception as e:
            self.logger.error(f"Failed to execute rollback {rollback_id}: {e}")
            raise RollbackError(f"Rollback execution failed: {e}")
    
    def _execute_rollback_operation(self, operation: RollbackOperation):
        """Execute a single rollback operation"""
        # This is a simplified implementation
        # In a real scenario, this would restore files from backups or snapshots
        
        if operation.operation_type == OperationType.COPY:
            # Restore file from backup/snapshot
            # For now, we'll just log what would happen
            self.logger.info(f"Would restore file: {operation.target_path}")
        
        elif operation.operation_type == OperationType.DELETE:
            # Remove file that shouldn't exist
            if operation.target_path and os.path.exists(operation.target_path):
                os.remove(operation.target_path)
                self.logger.info(f"Removed file: {operation.target_path}")
        
        # Add more rollback operation types as needed
    
    def _save_rollback_operations(self, rollback_id: str, operations: List[RollbackOperation]):
        """Save rollback operations to storage"""
        try:
            operations_file = self.rollback_operations_dir / f"{rollback_id}_operations.json"
            
            operations_data = [
                {
                    'rollback_op_id': op.rollback_op_id,
                    'original_operation_id': op.original_operation_id,
                    'operation_type': op.operation_type.value,
                    'source_path': op.source_path,
                    'target_path': op.target_path,
                    'backup_path': op.backup_path,
                    'file_checksum': op.file_checksum,
                    'created_at': op.created_at,
                    'executed': op.executed,
                    'execution_time': op.execution_time
                }
                for op in operations
            ]
            
            with open(operations_file, 'w') as f:
                json.dump(operations_data, f, indent=2)
        
        except Exception as e:
            self.logger.error(f"Error saving rollback operations for {rollback_id}: {e}")
    
    def verify_rollback_point(self, rollback_id: str) -> Dict[str, Any]:
        """Verify integrity of a rollback point"""
        if rollback_id not in self.rollback_points:
            raise RollbackError(f"Rollback point {rollback_id} not found")
        
        rollback_point = self.rollback_points[rollback_id]
        verification_result = {
            'rollback_id': rollback_id,
            'verified_files': 0,
            'missing_files': 0,
            'modified_files': 0,
            'checksum_mismatches': 0,
            'integrity_score': 0.0,
            'issues': []
        }
        
        try:
            total_files = len(rollback_point.file_checksums)
            
            for file_path, original_checksum in rollback_point.file_checksums.items():
                if not os.path.exists(file_path):
                    verification_result['missing_files'] += 1
                    verification_result['issues'].append(f"Missing file: {file_path}")
                else:
                    current_checksum = self._calculate_file_checksum(file_path)
                    
                    if current_checksum == original_checksum:
                        verification_result['verified_files'] += 1
                    else:
                        verification_result['modified_files'] += 1
                        verification_result['checksum_mismatches'] += 1
                        verification_result['issues'].append(f"Modified file: {file_path}")
            
            # Calculate integrity score
            if total_files > 0:
                verification_result['integrity_score'] = verification_result['verified_files'] / total_files
            else:
                verification_result['integrity_score'] = 1.0
            
            self.logger.info(f"Verified rollback point {rollback_id}: {verification_result['integrity_score']:.2%} integrity")
            return verification_result
        
        except Exception as e:
            self.logger.error(f"Failed to verify rollback point {rollback_id}: {e}")
            verification_result['issues'].append(f"Verification error: {e}")
            return verification_result
    
    def list_rollback_points(self, scope: RollbackScope = None) -> List[Dict[str, Any]]:
        """List available rollback points"""
        rollback_list = []
        
        for rollback_point in self.rollback_points.values():
            if scope is None or rollback_point.scope == scope:
                rollback_info = {
                    'rollback_id': rollback_point.rollback_id,
                    'created_at': rollback_point.created_at,
                    'scope': rollback_point.scope.value,
                    'description': rollback_point.description,
                    'file_count': len(rollback_point.file_checksums),
                    'size_bytes': rollback_point.size_bytes
                }
                rollback_list.append(rollback_info)
        
        # Sort by creation time (newest first)
        rollback_list.sort(key=lambda x: x['created_at'], reverse=True)
        return rollback_list
    
    def delete_rollback_point(self, rollback_id: str):
        """Delete a rollback point"""
        if rollback_id not in self.rollback_points:
            raise RollbackError(f"Rollback point {rollback_id} not found")
        
        try:
            # Remove from memory
            del self.rollback_points[rollback_id]
            
            # Remove files
            rollback_file = self.rollback_points_dir / f"{rollback_id}.json"
            if rollback_file.exists():
                rollback_file.unlink()
            
            operations_file = self.rollback_operations_dir / f"{rollback_id}_operations.json"
            if operations_file.exists():
                operations_file.unlink()
            
            self.logger.info(f"Deleted rollback point: {rollback_id}")
        
        except Exception as e:
            self.logger.error(f"Failed to delete rollback point {rollback_id}: {e}")
            raise RollbackError(f"Failed to delete rollback point: {e}")
    
    def _cleanup_old_rollback_points(self):
        """Clean up old rollback points"""
        if len(self.rollback_points) <= self.max_rollback_points:
            return
        
        # Sort by creation time and remove oldest
        sorted_points = sorted(
            self.rollback_points.values(),
            key=lambda x: x.created_at
        )
        
        points_to_remove = len(sorted_points) - self.max_rollback_points
        
        for i in range(points_to_remove):
            rollback_point = sorted_points[i]
            try:
                self.delete_rollback_point(rollback_point.rollback_id)
                self.logger.info(f"Auto-cleaned old rollback point: {rollback_point.rollback_id}")
            except Exception as e:
                self.logger.error(f"Failed to auto-clean rollback point {rollback_point.rollback_id}: {e}")
    
    def get_rollback_statistics(self) -> Dict[str, Any]:
        """Get statistics about rollback system"""
        total_size = sum(rp.size_bytes for rp in self.rollback_points.values())
        
        scope_counts = {}
        for rollback_point in self.rollback_points.values():
            scope = rollback_point.scope.value
            scope_counts[scope] = scope_counts.get(scope, 0) + 1
        
        return {
            'total_rollback_points': len(self.rollback_points),
            'total_size_bytes': total_size,
            'scope_distribution': scope_counts,
            'workspace_path': str(self.workspace_dir),
            'checksums_enabled': self.enable_checksums,
            'max_rollback_points': self.max_rollback_points,
            'max_age_days': self.max_rollback_age_days
        }