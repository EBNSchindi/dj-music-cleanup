"""
Crash Recovery and Checkpoint System for DJ Music Cleanup Tool
Advanced recovery capabilities for interrupted operations and system crashes
"""
import os
import sys
import json
import time
import shutil
import tempfile
import threading
import signal
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import logging
import sqlite3
import hashlib

from .transactions import AtomicFileOperations, Transaction, TransactionState, OperationType
from .rollback import RollbackManager, RollbackScope
from .unified_database import get_unified_database


class RecoveryState(Enum):
    """Recovery operation states"""
    HEALTHY = "healthy"
    INTERRUPTED = "interrupted"
    CRASHED = "crashed"
    RECOVERING = "recovering"
    CORRUPTED = "corrupted"
    RECOVERED = "recovered"


class CheckpointType(Enum):
    """Types of recovery checkpoints"""
    STARTUP = "startup"
    SESSION_BEGIN = "session_begin"
    BATCH_COMPLETE = "batch_complete"
    TRANSACTION_COMMIT = "transaction_commit"
    ERROR_OCCURRED = "error_occurred"
    MANUAL = "manual"
    SHUTDOWN = "shutdown"


@dataclass
class RecoveryCheckpoint:
    """Recovery checkpoint data"""
    checkpoint_id: str
    checkpoint_type: CheckpointType
    created_at: str
    session_id: str
    operation_group: str
    state_snapshot: Dict[str, Any]
    active_transactions: List[str]
    rollback_points: List[str]
    file_operations_count: int
    system_state: Dict[str, Any]
    metadata: Dict[str, Any]


@dataclass
class RecoveryPlan:
    """Recovery execution plan"""
    recovery_id: str
    target_checkpoint: str
    recovery_actions: List[Dict[str, Any]]
    estimated_duration: float
    risk_level: str
    rollback_required: bool
    data_loss_risk: bool
    created_at: str


class RecoveryError(Exception):
    """Exception for recovery-specific errors"""
    pass


class CrashRecoveryManager:
    """
    Advanced crash recovery and checkpoint manager.
    Provides comprehensive recovery from interruptions and crashes.
    """
    
    def __init__(self, workspace_dir: str = None, enable_auto_checkpoints: bool = True):
        """Initialize crash recovery manager"""
        self.logger = logging.getLogger(__name__)
        
        # Setup workspace
        if workspace_dir:
            self.workspace_dir = Path(workspace_dir)
        else:
            self.workspace_dir = Path(tempfile.gettempdir()) / "dj_cleanup_recovery"
        
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        
        # Recovery storage
        self.checkpoints_dir = self.workspace_dir / "checkpoints"
        self.recovery_logs_dir = self.workspace_dir / "recovery_logs"
        self.state_snapshots_dir = self.workspace_dir / "state_snapshots"
        self.crash_dumps_dir = self.workspace_dir / "crash_dumps"
        
        for directory in [self.checkpoints_dir, self.recovery_logs_dir, 
                         self.state_snapshots_dir, self.crash_dumps_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        # Dependencies
        self.db_manager = get_unified_database()
        self.atomic_ops = None  # Will be set by caller
        self.rollback_manager = None  # Will be set by caller
        
        # Configuration
        self.enable_auto_checkpoints = enable_auto_checkpoints
        self.checkpoint_interval = 300  # 5 minutes
        self.max_checkpoints = 100
        self.crash_detection_enabled = True
        
        # Current session tracking
        self.current_session_id = None
        self.current_operation_group = None
        self.last_checkpoint_time = time.time()
        self.checkpoint_thread = None
        self.shutdown_requested = False
        
        # Recovery state
        self.recovery_state = RecoveryState.HEALTHY
        self.active_checkpoints: Dict[str, RecoveryCheckpoint] = {}
        self.recovery_history: List[str] = []
        
        # Setup signal handlers for crash detection
        if self.crash_detection_enabled:
            self._setup_crash_handlers()
        
        # Load existing checkpoints
        self._load_checkpoints()
        
        # Start automatic checkpoint thread
        if enable_auto_checkpoints:
            self._start_checkpoint_thread()
        
        self.logger.info(f"CrashRecoveryManager initialized with workspace: {self.workspace_dir}")
    
    def _setup_crash_handlers(self):
        """Setup signal handlers for crash detection"""
        try:
            # Handle common crash signals
            signal.signal(signal.SIGTERM, self._handle_crash_signal)
            signal.signal(signal.SIGINT, self._handle_crash_signal)
            
            # Handle fatal errors (Unix only)
            if hasattr(signal, 'SIGSEGV'):
                signal.signal(signal.SIGSEGV, self._handle_crash_signal)
            if hasattr(signal, 'SIGABRT'):
                signal.signal(signal.SIGABRT, self._handle_crash_signal)
                
        except Exception as e:
            self.logger.warning(f"Could not setup crash handlers: {e}")
    
    def _handle_crash_signal(self, signum, frame):
        """Handle crash signals"""
        self.logger.critical(f"Crash signal received: {signum}")
        
        try:
            # Create emergency checkpoint
            self.create_emergency_checkpoint(f"crash_signal_{signum}")
            
            # Save crash dump
            self._save_crash_dump(signum, frame)
            
        except Exception as e:
            self.logger.error(f"Error during crash handling: {e}")
        
        # Re-raise the signal
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)
    
    def _save_crash_dump(self, signum: int, frame):
        """Save crash dump information"""
        try:
            crash_id = f"crash_{int(time.time())}_{signum}"
            crash_file = self.crash_dumps_dir / f"{crash_id}.json"
            
            crash_info = {
                'crash_id': crash_id,
                'signal': signum,
                'timestamp': datetime.now().isoformat(),
                'session_id': self.current_session_id,
                'operation_group': self.current_operation_group,
                'recovery_state': self.recovery_state.value,
                'active_checkpoints': list(self.active_checkpoints.keys()),
                'system_info': {
                    'platform': sys.platform,
                    'python_version': sys.version,
                    'working_directory': os.getcwd(),
                    'memory_usage': self._get_memory_usage()
                }
            }
            
            # Add stack trace if available
            if frame:
                import traceback
                crash_info['stack_trace'] = traceback.format_stack(frame)
            
            with open(crash_file, 'w') as f:
                json.dump(crash_info, f, indent=2)
            
            self.logger.info(f"Crash dump saved: {crash_file}")
            
        except Exception as e:
            self.logger.error(f"Failed to save crash dump: {e}")
    
    def _load_checkpoints(self):
        """Load existing checkpoints from storage"""
        try:
            for checkpoint_file in self.checkpoints_dir.glob("*.json"):
                with open(checkpoint_file, 'r') as f:
                    checkpoint_data = json.load(f)
                
                checkpoint = RecoveryCheckpoint(
                    checkpoint_id=checkpoint_data['checkpoint_id'],
                    checkpoint_type=CheckpointType(checkpoint_data['checkpoint_type']),
                    created_at=checkpoint_data['created_at'],
                    session_id=checkpoint_data['session_id'],
                    operation_group=checkpoint_data['operation_group'],
                    state_snapshot=checkpoint_data.get('state_snapshot', {}),
                    active_transactions=checkpoint_data.get('active_transactions', []),
                    rollback_points=checkpoint_data.get('rollback_points', []),
                    file_operations_count=checkpoint_data.get('file_operations_count', 0),
                    system_state=checkpoint_data.get('system_state', {}),
                    metadata=checkpoint_data.get('metadata', {})
                )
                
                self.active_checkpoints[checkpoint.checkpoint_id] = checkpoint
                self.logger.debug(f"Loaded checkpoint: {checkpoint.checkpoint_id}")
        
        except Exception as e:
            self.logger.error(f"Error loading checkpoints: {e}")
    
    def _save_checkpoint(self, checkpoint: RecoveryCheckpoint):
        """Save checkpoint to persistent storage"""
        try:
            checkpoint_file = self.checkpoints_dir / f"{checkpoint.checkpoint_id}.json"
            
            checkpoint_data = {
                'checkpoint_id': checkpoint.checkpoint_id,
                'checkpoint_type': checkpoint.checkpoint_type.value,
                'created_at': checkpoint.created_at,
                'session_id': checkpoint.session_id,
                'operation_group': checkpoint.operation_group,
                'state_snapshot': checkpoint.state_snapshot,
                'active_transactions': checkpoint.active_transactions,
                'rollback_points': checkpoint.rollback_points,
                'file_operations_count': checkpoint.file_operations_count,
                'system_state': checkpoint.system_state,
                'metadata': checkpoint.metadata
            }
            
            with open(checkpoint_file, 'w') as f:
                json.dump(checkpoint_data, f, indent=2)
            
        except Exception as e:
            self.logger.error(f"Error saving checkpoint {checkpoint.checkpoint_id}: {e}")
            raise RecoveryError(f"Failed to save checkpoint: {e}")
    
    def _start_checkpoint_thread(self):
        """Start automatic checkpoint thread"""
        if self.checkpoint_thread and self.checkpoint_thread.is_alive():
            return
        
        self.checkpoint_thread = threading.Thread(
            target=self._checkpoint_worker,
            daemon=True
        )
        self.checkpoint_thread.start()
        self.logger.info("Started automatic checkpoint thread")
    
    def _checkpoint_worker(self):
        """Background worker for automatic checkpoints"""
        while not self.shutdown_requested:
            try:
                time.sleep(self.checkpoint_interval)
                
                if not self.shutdown_requested and self.current_session_id:
                    # Check if checkpoint is needed
                    if time.time() - self.last_checkpoint_time > self.checkpoint_interval:
                        self.create_checkpoint(CheckpointType.MANUAL, "automatic_checkpoint")
                        
            except Exception as e:
                self.logger.error(f"Error in checkpoint worker: {e}")
    
    def _generate_checkpoint_id(self, checkpoint_type: CheckpointType) -> str:
        """Generate unique checkpoint ID"""
        timestamp = int(time.time() * 1000)
        type_name = checkpoint_type.value
        return f"{type_name}_{timestamp}"
    
    def _capture_system_state(self) -> Dict[str, Any]:
        """Capture current system state"""
        try:
            state = {
                'timestamp': datetime.now().isoformat(),
                'working_directory': os.getcwd(),
                'memory_usage': self._get_memory_usage(),
                'disk_usage': self._get_disk_usage(),
                'process_id': os.getpid(),
                'thread_count': threading.active_count(),
                'open_file_count': self._get_open_file_count()
            }
            
            # Add database connection status
            if self.db_manager:
                state['database_status'] = {
                    'connections_active': len(self.db_manager.connections),
                    'base_path': str(self.db_manager.base_path) if self.db_manager.base_path else None
                }
            
            return state
            
        except Exception as e:
            self.logger.warning(f"Error capturing system state: {e}")
            return {'error': str(e)}
    
    def _get_memory_usage(self) -> Dict[str, float]:
        """Get current memory usage"""
        try:
            import resource
            usage = resource.getrusage(resource.RUSAGE_SELF)
            return {
                'rss_mb': usage.ru_maxrss / 1024,  # Convert to MB (Linux)
                'user_time': usage.ru_utime,
                'system_time': usage.ru_stime
            }
        except ImportError:
            return {'error': 'resource module not available'}
    
    def _get_disk_usage(self) -> Dict[str, int]:
        """Get disk usage for workspace"""
        try:
            usage = shutil.disk_usage(self.workspace_dir)
            return {
                'total_bytes': usage.total,
                'used_bytes': usage.used,
                'free_bytes': usage.free
            }
        except Exception:
            return {'error': 'disk usage unavailable'}
    
    def _get_open_file_count(self) -> int:
        """Get count of open file descriptors"""
        try:
            import resource
            return resource.getrlimit(resource.RLIMIT_NOFILE)[0]
        except ImportError:
            return -1
    
    def begin_session(self, session_id: str, operation_group: str) -> str:
        """Begin a new recovery session"""
        self.current_session_id = session_id
        self.current_operation_group = operation_group
        self.recovery_state = RecoveryState.HEALTHY
        
        # Create initial checkpoint
        checkpoint_id = self.create_checkpoint(
            CheckpointType.SESSION_BEGIN,
            f"Session started: {session_id}",
            {
                'session_id': session_id,
                'operation_group': operation_group
            }
        )
        
        self.logger.info(f"Recovery session started: {session_id}")
        return checkpoint_id
    
    def create_checkpoint(self, checkpoint_type: CheckpointType, 
                         description: str = None, metadata: Dict = None) -> str:
        """Create a recovery checkpoint"""
        try:
            checkpoint_id = self._generate_checkpoint_id(checkpoint_type)
            
            # Capture current state
            state_snapshot = {
                'description': description or f"Checkpoint {checkpoint_type.value}",
                'atomic_operations': self._capture_atomic_state(),
                'rollback_state': self._capture_rollback_state(),
                'database_state': self._capture_database_state()
            }
            
            # Get active transactions
            active_transactions = []
            if self.atomic_ops:
                active_transactions = [t['transaction_id'] for t in self.atomic_ops.list_active_transactions()]
            
            # Get rollback points
            rollback_points = []
            if self.rollback_manager:
                rollback_points = [rp['rollback_id'] for rp in self.rollback_manager.list_rollback_points()]
            
            # Count file operations
            file_operations_count = 0
            if self.current_operation_group:
                ops = self.db_manager.execute_query(
                    'operations',
                    "SELECT COUNT(*) as count FROM file_operations WHERE operation_group = ?",
                    (self.current_operation_group,)
                )
                if ops:
                    file_operations_count = ops[0]['count']
            
            # Create checkpoint
            checkpoint = RecoveryCheckpoint(
                checkpoint_id=checkpoint_id,
                checkpoint_type=checkpoint_type,
                created_at=datetime.now().isoformat(),
                session_id=self.current_session_id or "unknown",
                operation_group=self.current_operation_group or "unknown",
                state_snapshot=state_snapshot,
                active_transactions=active_transactions,
                rollback_points=rollback_points,
                file_operations_count=file_operations_count,
                system_state=self._capture_system_state(),
                metadata=metadata or {}
            )
            
            # Save checkpoint
            self.active_checkpoints[checkpoint_id] = checkpoint
            self._save_checkpoint(checkpoint)
            
            # Update timing
            self.last_checkpoint_time = time.time()
            
            # Clean up old checkpoints
            self._cleanup_old_checkpoints()
            
            self.logger.info(f"Created checkpoint: {checkpoint_id} ({checkpoint_type.value})")
            return checkpoint_id
            
        except Exception as e:
            self.logger.error(f"Failed to create checkpoint: {e}")
            raise RecoveryError(f"Checkpoint creation failed: {e}")
    
    def create_emergency_checkpoint(self, reason: str) -> str:
        """Create emergency checkpoint during crash/interruption"""
        try:
            checkpoint_id = f"emergency_{int(time.time())}"
            
            # Minimal state capture for speed
            state_snapshot = {
                'emergency_reason': reason,
                'timestamp': datetime.now().isoformat(),
                'recovery_state': self.recovery_state.value
            }
            
            # Try to capture atomic state quickly
            try:
                if self.atomic_ops:
                    state_snapshot['active_transactions'] = len(self.atomic_ops.active_transactions)
            except Exception:
                pass
            
            checkpoint = RecoveryCheckpoint(
                checkpoint_id=checkpoint_id,
                checkpoint_type=CheckpointType.ERROR_OCCURRED,
                created_at=datetime.now().isoformat(),
                session_id=self.current_session_id or "emergency",
                operation_group=self.current_operation_group or "emergency",
                state_snapshot=state_snapshot,
                active_transactions=[],
                rollback_points=[],
                file_operations_count=0,
                system_state={'emergency': True},
                metadata={'reason': reason}
            )
            
            # Quick save
            self._save_checkpoint(checkpoint)
            self.active_checkpoints[checkpoint_id] = checkpoint
            
            self.logger.critical(f"Emergency checkpoint created: {checkpoint_id}")
            return checkpoint_id
            
        except Exception as e:
            self.logger.error(f"Emergency checkpoint failed: {e}")
            return None
    
    def _capture_atomic_state(self) -> Dict[str, Any]:
        """Capture atomic operations state"""
        try:
            if not self.atomic_ops:
                return {}
            
            return {
                'active_transactions_count': len(self.atomic_ops.active_transactions),
                'workspace_size': self.atomic_ops.get_workspace_size() if hasattr(self.atomic_ops, 'get_workspace_size') else {},
                'workspace_path': str(self.atomic_ops.workspace_dir)
            }
        except Exception as e:
            return {'error': str(e)}
    
    def _capture_rollback_state(self) -> Dict[str, Any]:
        """Capture rollback manager state"""
        try:
            if not self.rollback_manager:
                return {}
            
            return {
                'rollback_points_count': len(self.rollback_manager.rollback_points),
                'workspace_path': str(self.rollback_manager.workspace_dir),
                'checksums_enabled': self.rollback_manager.enable_checksums
            }
        except Exception as e:
            return {'error': str(e)}
    
    def _capture_database_state(self) -> Dict[str, Any]:
        """Capture database state"""
        try:
            if not self.db_manager:
                return {}
            
            state = {
                'connections_count': len(self.db_manager.connections),
                'base_path': str(self.db_manager.base_path) if self.db_manager.base_path else None
            }
            
            # Get table counts
            for db_name in self.db_manager.connections.keys():
                try:
                    if db_name == 'operations':
                        ops_count = self.db_manager.execute_query(
                            db_name,
                            "SELECT COUNT(*) as count FROM file_operations"
                        )
                        if ops_count:
                            state[f'{db_name}_operations_count'] = ops_count[0]['count']
                except Exception:
                    pass
            
            return state
        except Exception as e:
            return {'error': str(e)}
    
    def detect_interruption(self) -> Optional[Dict[str, Any]]:
        """Detect if previous session was interrupted"""
        interruption_info = {
            'interrupted': False,
            'last_checkpoint': None,
            'incomplete_transactions': [],
            'crash_dumps': [],
            'recovery_needed': False
        }
        
        try:
            # Check for crash dumps
            crash_dumps = list(self.crash_dumps_dir.glob("*.json"))
            if crash_dumps:
                interruption_info['crash_dumps'] = [str(dump) for dump in crash_dumps]
                interruption_info['interrupted'] = True
                interruption_info['recovery_needed'] = True
            
            # Check for incomplete transactions
            if self.atomic_ops:
                active_transactions = self.atomic_ops.list_active_transactions()
                if active_transactions:
                    interruption_info['incomplete_transactions'] = [
                        t['transaction_id'] for t in active_transactions
                    ]
                    interruption_info['interrupted'] = True
                    interruption_info['recovery_needed'] = True
            
            # Find most recent checkpoint
            if self.active_checkpoints:
                latest_checkpoint = max(
                    self.active_checkpoints.values(),
                    key=lambda cp: cp.created_at
                )
                interruption_info['last_checkpoint'] = {
                    'checkpoint_id': latest_checkpoint.checkpoint_id,
                    'created_at': latest_checkpoint.created_at,
                    'checkpoint_type': latest_checkpoint.checkpoint_type.value
                }
            
            # Check if recovery is needed based on checkpoint age
            if interruption_info['last_checkpoint']:
                last_time = datetime.fromisoformat(interruption_info['last_checkpoint']['created_at'])
                time_since = datetime.now() - last_time
                
                if time_since > timedelta(hours=1):  # Checkpoint older than 1 hour
                    interruption_info['recovery_needed'] = True
            
            if interruption_info['interrupted']:
                self.recovery_state = RecoveryState.INTERRUPTED
                self.logger.warning(f"Interruption detected: {interruption_info}")
            
            return interruption_info
            
        except Exception as e:
            self.logger.error(f"Error detecting interruption: {e}")
            return interruption_info
    
    def create_recovery_plan(self, target_checkpoint_id: str = None) -> RecoveryPlan:
        """Create recovery plan from interruption"""
        try:
            recovery_id = f"recovery_{int(time.time())}"
            
            # Determine target checkpoint
            if target_checkpoint_id:
                if target_checkpoint_id not in self.active_checkpoints:
                    raise RecoveryError(f"Checkpoint {target_checkpoint_id} not found")
                target_checkpoint = self.active_checkpoints[target_checkpoint_id]
            else:
                # Use most recent checkpoint
                if not self.active_checkpoints:
                    raise RecoveryError("No checkpoints available for recovery")
                
                target_checkpoint = max(
                    self.active_checkpoints.values(),
                    key=lambda cp: cp.created_at
                )
            
            # Analyze recovery actions needed
            recovery_actions = []
            
            # 1. Rollback incomplete transactions
            if target_checkpoint.active_transactions:
                recovery_actions.append({
                    'action': 'rollback_transactions',
                    'transactions': target_checkpoint.active_transactions,
                    'estimated_time': len(target_checkpoint.active_transactions) * 30
                })
            
            # 2. Restore from rollback points if needed
            if target_checkpoint.rollback_points:
                recovery_actions.append({
                    'action': 'restore_rollback_points',
                    'rollback_points': target_checkpoint.rollback_points,
                    'estimated_time': 120
                })
            
            # 3. Verify file integrity
            recovery_actions.append({
                'action': 'verify_integrity',
                'file_count': target_checkpoint.file_operations_count,
                'estimated_time': target_checkpoint.file_operations_count * 0.1
            })
            
            # 4. Resume operations from checkpoint
            recovery_actions.append({
                'action': 'resume_operations',
                'session_id': target_checkpoint.session_id,
                'operation_group': target_checkpoint.operation_group,
                'estimated_time': 60
            })
            
            # Calculate risk level
            total_transactions = len(target_checkpoint.active_transactions)
            risk_level = "low"
            if total_transactions > 10:
                risk_level = "medium"
            if total_transactions > 50:
                risk_level = "high"
            
            # Estimate total duration
            estimated_duration = sum(action.get('estimated_time', 0) for action in recovery_actions)
            
            # Check if rollback is required
            rollback_required = len(target_checkpoint.active_transactions) > 0
            
            # Assess data loss risk
            data_loss_risk = False
            if target_checkpoint.checkpoint_type in [CheckpointType.ERROR_OCCURRED]:
                data_loss_risk = True
            
            recovery_plan = RecoveryPlan(
                recovery_id=recovery_id,
                target_checkpoint=target_checkpoint.checkpoint_id,
                recovery_actions=recovery_actions,
                estimated_duration=estimated_duration,
                risk_level=risk_level,
                rollback_required=rollback_required,
                data_loss_risk=data_loss_risk,
                created_at=datetime.now().isoformat()
            )
            
            self.logger.info(f"Created recovery plan: {recovery_id} -> {target_checkpoint.checkpoint_id}")
            return recovery_plan
            
        except Exception as e:
            self.logger.error(f"Failed to create recovery plan: {e}")
            raise RecoveryError(f"Recovery plan creation failed: {e}")
    
    def execute_recovery(self, recovery_plan: RecoveryPlan, dry_run: bool = False) -> Dict[str, Any]:
        """Execute recovery plan"""
        self.recovery_state = RecoveryState.RECOVERING
        
        result = {
            'recovery_id': recovery_plan.recovery_id,
            'target_checkpoint': recovery_plan.target_checkpoint,
            'dry_run': dry_run,
            'actions_completed': 0,
            'actions_failed': 0,
            'total_actions': len(recovery_plan.recovery_actions),
            'start_time': datetime.now().isoformat(),
            'action_results': []
        }
        
        try:
            for action in recovery_plan.recovery_actions:
                action_result = {
                    'action': action['action'],
                    'status': 'pending',
                    'start_time': datetime.now().isoformat(),
                    'error': None
                }
                
                try:
                    if dry_run:
                        action_result['status'] = 'simulated'
                        self.logger.info(f"[DRY RUN] Would execute: {action['action']}")
                    else:
                        # Execute actual recovery action
                        self._execute_recovery_action(action)
                        action_result['status'] = 'completed'
                    
                    result['actions_completed'] += 1
                    
                except Exception as e:
                    action_result['status'] = 'failed'
                    action_result['error'] = str(e)
                    result['actions_failed'] += 1
                    self.logger.error(f"Recovery action failed: {action['action']}: {e}")
                
                action_result['end_time'] = datetime.now().isoformat()
                result['action_results'].append(action_result)
            
            result['end_time'] = datetime.now().isoformat()
            
            # Update recovery state
            if result['actions_failed'] == 0:
                self.recovery_state = RecoveryState.RECOVERED
                result['success'] = True
                self.logger.info(f"Recovery completed successfully: {recovery_plan.recovery_id}")
            else:
                self.recovery_state = RecoveryState.CORRUPTED
                result['success'] = False
                self.logger.error(f"Recovery partially failed: {result['actions_failed']}/{result['total_actions']} actions failed")
            
            return result
            
        except Exception as e:
            self.recovery_state = RecoveryState.CORRUPTED
            result['success'] = False
            result['error'] = str(e)
            result['end_time'] = datetime.now().isoformat()
            self.logger.error(f"Recovery execution failed: {e}")
            return result
    
    def _execute_recovery_action(self, action: Dict[str, Any]):
        """Execute a single recovery action"""
        action_type = action['action']
        
        if action_type == 'rollback_transactions':
            self._rollback_transactions(action['transactions'])
        
        elif action_type == 'restore_rollback_points':
            self._restore_rollback_points(action['rollback_points'])
        
        elif action_type == 'verify_integrity':
            self._verify_file_integrity(action.get('file_count', 0))
        
        elif action_type == 'resume_operations':
            self._resume_operations(action['session_id'], action['operation_group'])
        
        else:
            raise RecoveryError(f"Unknown recovery action: {action_type}")
    
    def _rollback_transactions(self, transaction_ids: List[str]):
        """Rollback incomplete transactions"""
        if not self.atomic_ops:
            return
        
        for transaction_id in transaction_ids:
            try:
                if transaction_id in self.atomic_ops.active_transactions:
                    self.atomic_ops.rollback_transaction(transaction_id)
                    self.logger.info(f"Rolled back transaction: {transaction_id}")
            except Exception as e:
                self.logger.error(f"Failed to rollback transaction {transaction_id}: {e}")
    
    def _restore_rollback_points(self, rollback_point_ids: List[str]):
        """Restore from rollback points if needed"""
        if not self.rollback_manager:
            return
        
        # For now, just verify rollback points exist
        for rollback_id in rollback_point_ids:
            try:
                verification = self.rollback_manager.verify_rollback_point(rollback_id)
                if verification['integrity_score'] < 0.8:
                    self.logger.warning(f"Rollback point {rollback_id} has low integrity: {verification['integrity_score']:.2%}")
            except Exception as e:
                self.logger.error(f"Failed to verify rollback point {rollback_id}: {e}")
    
    def _verify_file_integrity(self, file_count: int):
        """Verify file integrity after recovery"""
        # Basic file existence and accessibility check
        # More comprehensive integrity checking would be implemented here
        self.logger.info(f"Verifying integrity of {file_count} file operations")
        
        if self.current_operation_group:
            # Check file operations in database
            operations = self.db_manager.execute_query(
                'operations',
                """SELECT destination_path FROM file_operations 
                   WHERE operation_group = ? AND status = 'completed'""",
                (self.current_operation_group,)
            )
            
            missing_files = 0
            for op in operations:
                if op['destination_path'] and not os.path.exists(op['destination_path']):
                    missing_files += 1
            
            if missing_files > 0:
                self.logger.warning(f"Found {missing_files} missing files during integrity check")
    
    def _resume_operations(self, session_id: str, operation_group: str):
        """Resume operations from checkpoint"""
        self.current_session_id = session_id
        self.current_operation_group = operation_group
        
        self.logger.info(f"Resumed operations: session={session_id}, group={operation_group}")
    
    def _cleanup_old_checkpoints(self):
        """Clean up old checkpoints"""
        if len(self.active_checkpoints) <= self.max_checkpoints:
            return
        
        # Sort by creation time and remove oldest
        sorted_checkpoints = sorted(
            self.active_checkpoints.values(),
            key=lambda cp: cp.created_at
        )
        
        checkpoints_to_remove = len(sorted_checkpoints) - self.max_checkpoints
        
        for i in range(checkpoints_to_remove):
            checkpoint = sorted_checkpoints[i]
            try:
                self.delete_checkpoint(checkpoint.checkpoint_id)
            except Exception as e:
                self.logger.error(f"Failed to cleanup checkpoint {checkpoint.checkpoint_id}: {e}")
    
    def delete_checkpoint(self, checkpoint_id: str):
        """Delete a checkpoint"""
        if checkpoint_id not in self.active_checkpoints:
            raise RecoveryError(f"Checkpoint {checkpoint_id} not found")
        
        try:
            # Remove from memory
            del self.active_checkpoints[checkpoint_id]
            
            # Remove file
            checkpoint_file = self.checkpoints_dir / f"{checkpoint_id}.json"
            if checkpoint_file.exists():
                checkpoint_file.unlink()
            
            self.logger.info(f"Deleted checkpoint: {checkpoint_id}")
        
        except Exception as e:
            self.logger.error(f"Failed to delete checkpoint {checkpoint_id}: {e}")
            raise RecoveryError(f"Failed to delete checkpoint: {e}")
    
    def list_checkpoints(self, session_id: str = None) -> List[Dict[str, Any]]:
        """List available checkpoints"""
        checkpoints = []
        
        for checkpoint in self.active_checkpoints.values():
            if session_id is None or checkpoint.session_id == session_id:
                checkpoint_info = {
                    'checkpoint_id': checkpoint.checkpoint_id,
                    'checkpoint_type': checkpoint.checkpoint_type.value,
                    'created_at': checkpoint.created_at,
                    'session_id': checkpoint.session_id,
                    'operation_group': checkpoint.operation_group,
                    'file_operations_count': checkpoint.file_operations_count,
                    'active_transactions': len(checkpoint.active_transactions),
                    'rollback_points': len(checkpoint.rollback_points)
                }
                checkpoints.append(checkpoint_info)
        
        # Sort by creation time (newest first)
        checkpoints.sort(key=lambda x: x['created_at'], reverse=True)
        return checkpoints
    
    def get_recovery_statistics(self) -> Dict[str, Any]:
        """Get recovery system statistics"""
        stats = {
            'total_checkpoints': len(self.active_checkpoints),
            'workspace_path': str(self.workspace_dir),
            'current_session': self.current_session_id,
            'current_operation_group': self.current_operation_group,
            'recovery_state': self.recovery_state.value,
            'auto_checkpoints_enabled': self.enable_auto_checkpoints,
            'checkpoint_interval': self.checkpoint_interval,
            'last_checkpoint_time': self.last_checkpoint_time
        }
        
        # Count checkpoints by type
        checkpoint_types = {}
        for checkpoint in self.active_checkpoints.values():
            cp_type = checkpoint.checkpoint_type.value
            checkpoint_types[cp_type] = checkpoint_types.get(cp_type, 0) + 1
        
        stats['checkpoint_types'] = checkpoint_types
        
        # Get crash dumps
        crash_dumps = list(self.crash_dumps_dir.glob("*.json"))
        stats['crash_dumps_count'] = len(crash_dumps)
        
        # Recovery history
        stats['recovery_history_count'] = len(self.recovery_history)
        
        return stats
    
    def shutdown(self):
        """Shutdown recovery manager gracefully"""
        self.shutdown_requested = True
        
        # Create shutdown checkpoint
        if self.current_session_id:
            self.create_checkpoint(CheckpointType.SHUTDOWN, "Graceful shutdown")
        
        # Stop checkpoint thread
        if self.checkpoint_thread and self.checkpoint_thread.is_alive():
            self.checkpoint_thread.join(timeout=5)
        
        self.logger.info("Recovery manager shutdown completed")
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if exc_type:
            # Exception occurred, create emergency checkpoint
            self.create_emergency_checkpoint(f"Exception: {exc_type.__name__}")
        
        self.shutdown()