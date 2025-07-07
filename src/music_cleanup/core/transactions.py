"""
Atomic File Operations for DJ Music Cleanup Tool
Ensures transactional safety for critical file operations
"""
import os
import sys
import json
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union
from datetime import datetime
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from enum import Enum
import logging


class OperationType(Enum):
    """Types of atomic operations"""
    COPY = "copy"
    MOVE = "move"
    DELETE = "delete"
    RENAME = "rename"
    MKDIR = "mkdir"
    RMDIR = "rmdir"
    METADATA_UPDATE = "metadata_update"
    DATABASE_UPDATE = "database_update"


class TransactionState(Enum):
    """Transaction states"""
    CREATED = "created"
    PREPARED = "prepared"
    COMMITTED = "committed"
    ABORTED = "aborted"
    ROLLED_BACK = "rolled_back"


@dataclass
class AtomicOperation:
    """Single atomic operation within a transaction"""
    operation_id: str
    operation_type: OperationType
    source_path: Optional[str] = None
    target_path: Optional[str] = None
    backup_path: Optional[str] = None
    metadata: Optional[Dict] = None
    created_at: str = None
    executed_at: Optional[str] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()


@dataclass
class Transaction:
    """Transaction container for multiple atomic operations"""
    transaction_id: str
    state: TransactionState
    operations: List[AtomicOperation]
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    metadata: Optional[Dict] = None
    
    def __post_init__(self):
        if not self.operations:
            self.operations = []


class TransactionError(Exception):
    """Base exception for transaction errors"""
    pass


class AtomicOperationError(TransactionError):
    """Exception for atomic operation failures"""
    pass


class RollbackError(TransactionError):
    """Exception for rollback failures"""
    pass


class AtomicFileOperations:
    """
    Atomic file operations manager for safe music library operations.
    Provides ACID properties for file system operations.
    """
    
    def __init__(self, workspace_dir: str = None, enable_logging: bool = True):
        """Initialize atomic operations manager"""
        self.logger = logging.getLogger(__name__)
        
        # Setup workspace for atomic operations
        if workspace_dir:
            self.workspace_dir = Path(workspace_dir)
        else:
            self.workspace_dir = Path(tempfile.gettempdir()) / "dj_cleanup_atomic"
        
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        
        # Transaction storage
        self.transactions_dir = self.workspace_dir / "transactions"
        self.backups_dir = self.workspace_dir / "backups"
        self.logs_dir = self.workspace_dir / "logs"
        
        for directory in [self.transactions_dir, self.backups_dir, self.logs_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        # Active transactions
        self.active_transactions: Dict[str, Transaction] = {}
        self._lock = threading.RLock()
        
        # Configuration
        self.enable_logging = enable_logging
        self.max_backup_age_days = 7
        self.verify_operations = True
        
        # Load existing transactions on startup
        self._load_active_transactions()
        
        self.logger.info(f"AtomicFileOperations initialized with workspace: {self.workspace_dir}")
    
    def _load_active_transactions(self):
        """Load active transactions from storage"""
        try:
            for transaction_file in self.transactions_dir.glob("*.json"):
                with open(transaction_file, 'r') as f:
                    transaction_data = json.load(f)
                
                # Convert to Transaction object
                operations = [
                    AtomicOperation(
                        operation_id=op_data['operation_id'],
                        operation_type=OperationType(op_data['operation_type']),
                        source_path=op_data.get('source_path'),
                        target_path=op_data.get('target_path'),
                        backup_path=op_data.get('backup_path'),
                        metadata=op_data.get('metadata'),
                        created_at=op_data.get('created_at'),
                        executed_at=op_data.get('executed_at')
                    )
                    for op_data in transaction_data.get('operations', [])
                ]
                
                transaction = Transaction(
                    transaction_id=transaction_data['transaction_id'],
                    state=TransactionState(transaction_data['state']),
                    operations=operations,
                    created_at=transaction_data['created_at'],
                    started_at=transaction_data.get('started_at'),
                    completed_at=transaction_data.get('completed_at'),
                    metadata=transaction_data.get('metadata')
                )
                
                # Only load non-completed transactions
                if transaction.state in [TransactionState.CREATED, TransactionState.PREPARED]:
                    self.active_transactions[transaction.transaction_id] = transaction
                    self.logger.info(f"Loaded active transaction: {transaction.transaction_id}")
        
        except Exception as e:
            self.logger.error(f"Error loading active transactions: {e}")
    
    def _save_transaction(self, transaction: Transaction):
        """Save transaction to persistent storage"""
        try:
            transaction_file = self.transactions_dir / f"{transaction.transaction_id}.json"
            
            # Convert to serializable format
            transaction_data = {
                'transaction_id': transaction.transaction_id,
                'state': transaction.state.value,
                'operations': [
                    {
                        'operation_id': op.operation_id,
                        'operation_type': op.operation_type.value,
                        'source_path': op.source_path,
                        'target_path': op.target_path,
                        'backup_path': op.backup_path,
                        'metadata': op.metadata,
                        'created_at': op.created_at,
                        'executed_at': op.executed_at
                    }
                    for op in transaction.operations
                ],
                'created_at': transaction.created_at,
                'started_at': transaction.started_at,
                'completed_at': transaction.completed_at,
                'metadata': transaction.metadata
            }
            
            with open(transaction_file, 'w') as f:
                json.dump(transaction_data, f, indent=2)
        
        except Exception as e:
            self.logger.error(f"Error saving transaction {transaction.transaction_id}: {e}")
            raise TransactionError(f"Failed to save transaction: {e}")
    
    def _generate_id(self) -> str:
        """Generate unique ID"""
        return f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
    
    def begin_transaction(self, metadata: Dict = None) -> str:
        """Begin a new transaction"""
        with self._lock:
            transaction_id = self._generate_id()
            
            transaction = Transaction(
                transaction_id=transaction_id,
                state=TransactionState.CREATED,
                operations=[],
                created_at=datetime.now().isoformat(),
                metadata=metadata or {}
            )
            
            self.active_transactions[transaction_id] = transaction
            self._save_transaction(transaction)
            
            self.logger.info(f"Started transaction: {transaction_id}")
            return transaction_id
    
    def add_operation(self, transaction_id: str, operation_type: OperationType,
                     source_path: str = None, target_path: str = None,
                     metadata: Dict = None) -> str:
        """Add an operation to a transaction"""
        with self._lock:
            if transaction_id not in self.active_transactions:
                raise TransactionError(f"Transaction {transaction_id} not found")
            
            transaction = self.active_transactions[transaction_id]
            
            if transaction.state != TransactionState.CREATED:
                raise TransactionError(f"Cannot add operations to transaction in state: {transaction.state}")
            
            operation_id = self._generate_id()
            
            operation = AtomicOperation(
                operation_id=operation_id,
                operation_type=operation_type,
                source_path=source_path,
                target_path=target_path,
                metadata=metadata or {}
            )
            
            transaction.operations.append(operation)
            self._save_transaction(transaction)
            
            self.logger.debug(f"Added operation {operation_id} to transaction {transaction_id}")
            return operation_id
    
    def prepare_transaction(self, transaction_id: str) -> bool:
        """Prepare transaction - validate all operations"""
        with self._lock:
            if transaction_id not in self.active_transactions:
                raise TransactionError(f"Transaction {transaction_id} not found")
            
            transaction = self.active_transactions[transaction_id]
            
            if transaction.state != TransactionState.CREATED:
                raise TransactionError(f"Transaction {transaction_id} is not in CREATED state")
            
            try:
                # Validate all operations
                for operation in transaction.operations:
                    self._validate_operation(operation)
                
                # Create backup paths for operations that need them
                for operation in transaction.operations:
                    if operation.operation_type in [OperationType.COPY, OperationType.MOVE, OperationType.DELETE]:
                        if operation.source_path and os.path.exists(operation.source_path):
                            backup_path = self._create_backup_path(operation.source_path)
                            operation.backup_path = backup_path
                
                transaction.state = TransactionState.PREPARED
                self._save_transaction(transaction)
                
                self.logger.info(f"Prepared transaction: {transaction_id}")
                return True
                
            except Exception as e:
                self.logger.error(f"Failed to prepare transaction {transaction_id}: {e}")
                transaction.state = TransactionState.ABORTED
                self._save_transaction(transaction)
                raise TransactionError(f"Transaction preparation failed: {e}")
    
    def commit_transaction(self, transaction_id: str) -> bool:
        """Commit transaction - execute all operations atomically"""
        with self._lock:
            if transaction_id not in self.active_transactions:
                raise TransactionError(f"Transaction {transaction_id} not found")
            
            transaction = self.active_transactions[transaction_id]
            
            if transaction.state != TransactionState.PREPARED:
                raise TransactionError(f"Transaction {transaction_id} is not prepared")
            
            transaction.started_at = datetime.now().isoformat()
            executed_operations = []
            
            try:
                # Execute operations in order
                for operation in transaction.operations:
                    self._execute_operation(operation)
                    operation.executed_at = datetime.now().isoformat()
                    executed_operations.append(operation)
                
                # Mark as committed
                transaction.state = TransactionState.COMMITTED
                transaction.completed_at = datetime.now().isoformat()
                self._save_transaction(transaction)
                
                # Remove from active transactions
                del self.active_transactions[transaction_id]
                
                self.logger.info(f"Committed transaction: {transaction_id}")
                return True
                
            except Exception as e:
                self.logger.error(f"Failed to commit transaction {transaction_id}: {e}")
                
                # Rollback executed operations
                try:
                    self._rollback_operations(executed_operations)
                    transaction.state = TransactionState.ROLLED_BACK
                except Exception as rollback_error:
                    self.logger.error(f"Rollback failed for transaction {transaction_id}: {rollback_error}")
                    transaction.state = TransactionState.ABORTED
                
                transaction.completed_at = datetime.now().isoformat()
                self._save_transaction(transaction)
                
                raise TransactionError(f"Transaction commit failed: {e}")
    
    def rollback_transaction(self, transaction_id: str) -> bool:
        """Rollback transaction"""
        with self._lock:
            if transaction_id not in self.active_transactions:
                raise TransactionError(f"Transaction {transaction_id} not found")
            
            transaction = self.active_transactions[transaction_id]
            
            try:
                # Rollback executed operations
                executed_operations = [op for op in transaction.operations if op.executed_at]
                self._rollback_operations(executed_operations)
                
                transaction.state = TransactionState.ROLLED_BACK
                transaction.completed_at = datetime.now().isoformat()
                self._save_transaction(transaction)
                
                # Remove from active transactions
                del self.active_transactions[transaction_id]
                
                self.logger.info(f"Rolled back transaction: {transaction_id}")
                return True
                
            except Exception as e:
                self.logger.error(f"Failed to rollback transaction {transaction_id}: {e}")
                transaction.state = TransactionState.ABORTED
                self._save_transaction(transaction)
                raise RollbackError(f"Rollback failed: {e}")
    
    def _validate_operation(self, operation: AtomicOperation):
        """Validate an operation before execution"""
        if operation.operation_type == OperationType.COPY:
            if not operation.source_path or not operation.target_path:
                raise AtomicOperationError("Copy operation requires source and target paths")
            
            if not os.path.exists(operation.source_path):
                raise AtomicOperationError(f"Source file does not exist: {operation.source_path}")
            
            # Check if target directory exists or can be created
            target_dir = os.path.dirname(operation.target_path)
            if not os.path.exists(target_dir):
                try:
                    os.makedirs(target_dir, exist_ok=True)
                except Exception as e:
                    raise AtomicOperationError(f"Cannot create target directory: {e}")
        
        elif operation.operation_type == OperationType.MOVE:
            if not operation.source_path or not operation.target_path:
                raise AtomicOperationError("Move operation requires source and target paths")
            
            if not os.path.exists(operation.source_path):
                raise AtomicOperationError(f"Source file does not exist: {operation.source_path}")
        
        elif operation.operation_type == OperationType.DELETE:
            if not operation.source_path:
                raise AtomicOperationError("Delete operation requires source path")
            
            if not os.path.exists(operation.source_path):
                raise AtomicOperationError(f"File to delete does not exist: {operation.source_path}")
        
        elif operation.operation_type == OperationType.RENAME:
            if not operation.source_path or not operation.target_path:
                raise AtomicOperationError("Rename operation requires source and target paths")
            
            if not os.path.exists(operation.source_path):
                raise AtomicOperationError(f"File to rename does not exist: {operation.source_path}")
        
        # Add more validations as needed
    
    def _create_backup_path(self, file_path: str) -> str:
        """Create backup path for a file"""
        file_path = Path(file_path)
        timestamp = int(time.time() * 1000)
        backup_name = f"{file_path.stem}_{timestamp}{file_path.suffix}"
        return str(self.backups_dir / backup_name)
    
    def _execute_operation(self, operation: AtomicOperation):
        """Execute a single atomic operation"""
        try:
            if operation.operation_type == OperationType.COPY:
                # Create backup if source will be preserved
                if operation.backup_path and os.path.exists(operation.target_path):
                    shutil.copy2(operation.target_path, operation.backup_path)
                
                # Ensure target directory exists
                os.makedirs(os.path.dirname(operation.target_path), exist_ok=True)
                
                # Copy file
                shutil.copy2(operation.source_path, operation.target_path)
                
                if self.verify_operations:
                    self._verify_file_copy(operation.source_path, operation.target_path)
            
            elif operation.operation_type == OperationType.MOVE:
                # Create backup of source
                if operation.backup_path:
                    shutil.copy2(operation.source_path, operation.backup_path)
                
                # Ensure target directory exists
                os.makedirs(os.path.dirname(operation.target_path), exist_ok=True)
                
                # Move file
                shutil.move(operation.source_path, operation.target_path)
                
                if self.verify_operations:
                    if not os.path.exists(operation.target_path):
                        raise AtomicOperationError(f"Move verification failed: {operation.target_path}")
            
            elif operation.operation_type == OperationType.DELETE:
                # Create backup
                if operation.backup_path:
                    shutil.copy2(operation.source_path, operation.backup_path)
                
                # Delete file
                os.remove(operation.source_path)
            
            elif operation.operation_type == OperationType.RENAME:
                # Create backup
                if operation.backup_path:
                    shutil.copy2(operation.source_path, operation.backup_path)
                
                # Rename file
                os.rename(operation.source_path, operation.target_path)
            
            elif operation.operation_type == OperationType.MKDIR:
                if operation.target_path:
                    os.makedirs(operation.target_path, exist_ok=True)
            
            elif operation.operation_type == OperationType.RMDIR:
                if operation.source_path and os.path.exists(operation.source_path):
                    shutil.rmtree(operation.source_path)
            
            else:
                raise AtomicOperationError(f"Unsupported operation type: {operation.operation_type}")
        
        except Exception as e:
            raise AtomicOperationError(f"Operation {operation.operation_id} failed: {e}")
    
    def _rollback_operations(self, operations: List[AtomicOperation]):
        """Rollback a list of executed operations"""
        # Rollback in reverse order
        for operation in reversed(operations):
            try:
                self._rollback_operation(operation)
            except Exception as e:
                self.logger.error(f"Failed to rollback operation {operation.operation_id}: {e}")
                # Continue with other rollbacks
    
    def _rollback_operation(self, operation: AtomicOperation):
        """Rollback a single operation"""
        try:
            if operation.operation_type == OperationType.COPY:
                # Remove copied file
                if operation.target_path and os.path.exists(operation.target_path):
                    os.remove(operation.target_path)
                
                # Restore backup if it was overwritten
                if operation.backup_path and os.path.exists(operation.backup_path):
                    shutil.move(operation.backup_path, operation.target_path)
            
            elif operation.operation_type == OperationType.MOVE:
                # Restore from backup
                if operation.backup_path and os.path.exists(operation.backup_path):
                    shutil.move(operation.backup_path, operation.source_path)
                
                # Remove moved file if it exists
                if operation.target_path and os.path.exists(operation.target_path):
                    os.remove(operation.target_path)
            
            elif operation.operation_type == OperationType.DELETE:
                # Restore from backup
                if operation.backup_path and os.path.exists(operation.backup_path):
                    shutil.move(operation.backup_path, operation.source_path)
            
            elif operation.operation_type == OperationType.RENAME:
                # Restore from backup
                if operation.backup_path and os.path.exists(operation.backup_path):
                    # Remove renamed file
                    if operation.target_path and os.path.exists(operation.target_path):
                        os.remove(operation.target_path)
                    
                    # Restore original
                    shutil.move(operation.backup_path, operation.source_path)
            
            elif operation.operation_type == OperationType.MKDIR:
                # Remove created directory
                if operation.target_path and os.path.exists(operation.target_path):
                    shutil.rmtree(operation.target_path)
            
            elif operation.operation_type == OperationType.RMDIR:
                # Cannot restore deleted directory without backup
                self.logger.warning(f"Cannot restore deleted directory: {operation.source_path}")
        
        except Exception as e:
            raise RollbackError(f"Failed to rollback operation {operation.operation_id}: {e}")
    
    def _verify_file_copy(self, source_path: str, target_path: str):
        """Verify that a file was copied correctly"""
        if not os.path.exists(target_path):
            raise AtomicOperationError(f"Copy verification failed: target file does not exist")
        
        source_size = os.path.getsize(source_path)
        target_size = os.path.getsize(target_path)
        
        if source_size != target_size:
            raise AtomicOperationError(f"Copy verification failed: size mismatch ({source_size} != {target_size})")
    
    @contextmanager
    def atomic_transaction(self, metadata: Dict = None):
        """Context manager for atomic transactions"""
        transaction_id = self.begin_transaction(metadata)
        
        try:
            yield transaction_id
            
            # Prepare and commit
            self.prepare_transaction(transaction_id)
            self.commit_transaction(transaction_id)
            
        except Exception as e:
            # Rollback on any error
            try:
                self.rollback_transaction(transaction_id)
            except Exception as rollback_error:
                self.logger.error(f"Rollback failed: {rollback_error}")
            
            raise e
    
    def get_transaction_status(self, transaction_id: str) -> Dict:
        """Get status of a transaction"""
        if transaction_id in self.active_transactions:
            transaction = self.active_transactions[transaction_id]
            return {
                'transaction_id': transaction.transaction_id,
                'state': transaction.state.value,
                'operations_count': len(transaction.operations),
                'created_at': transaction.created_at,
                'started_at': transaction.started_at,
                'completed_at': transaction.completed_at
            }
        
        # Check completed transactions
        transaction_file = self.transactions_dir / f"{transaction_id}.json"
        if transaction_file.exists():
            with open(transaction_file, 'r') as f:
                transaction_data = json.load(f)
            return {
                'transaction_id': transaction_data['transaction_id'],
                'state': transaction_data['state'],
                'operations_count': len(transaction_data.get('operations', [])),
                'created_at': transaction_data['created_at'],
                'started_at': transaction_data.get('started_at'),
                'completed_at': transaction_data.get('completed_at')
            }
        
        return None
    
    def list_active_transactions(self) -> List[Dict]:
        """List all active transactions"""
        return [
            {
                'transaction_id': transaction.transaction_id,
                'state': transaction.state.value,
                'operations_count': len(transaction.operations),
                'created_at': transaction.created_at
            }
            for transaction in self.active_transactions.values()
        ]
    
    def cleanup_old_backups(self, max_age_days: int = None):
        """Clean up old backup files"""
        if max_age_days is None:
            max_age_days = self.max_backup_age_days
        
        cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)
        cleaned_count = 0
        
        try:
            for backup_file in self.backups_dir.glob("*"):
                if backup_file.stat().st_mtime < cutoff_time:
                    backup_file.unlink()
                    cleaned_count += 1
            
            self.logger.info(f"Cleaned up {cleaned_count} old backup files")
            return cleaned_count
            
        except Exception as e:
            self.logger.error(f"Error cleaning up backups: {e}")
            return 0
    
    def get_workspace_size(self) -> Dict[str, int]:
        """Get size information about the workspace"""
        def get_dir_size(directory: Path) -> int:
            total_size = 0
            try:
                for file_path in directory.rglob("*"):
                    if file_path.is_file():
                        total_size += file_path.stat().st_size
            except Exception:
                pass
            return total_size
        
        return {
            'transactions_size_bytes': get_dir_size(self.transactions_dir),
            'backups_size_bytes': get_dir_size(self.backups_dir),
            'logs_size_bytes': get_dir_size(self.logs_dir),
            'total_size_bytes': get_dir_size(self.workspace_dir)
        }
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        # Clean up resources
        self.cleanup_old_backups()