"""
Progress tracking and reporting utilities
Modified to use centralized DatabaseManager
"""
import os
import sys
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json
from pathlib import Path
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

from ..core.unified_database import get_unified_database
# Progress schema is now integrated in unified_database


class ProgressTracker:
    """Track and display progress for long-running operations"""
    
    def __init__(self, total_items: int = None, desc: str = "Processing",
                 enable_resume: bool = True):
        """Initialize progress tracker"""
        self.total_items = total_items
        self.desc = desc
        self.enable_resume = enable_resume
        self.start_time = time.time()
        self.processed = 0
        self.errors = 0
        self.skipped = 0
        self.current_phase = None
        self.phase_start_time = None
        self.logger = logging.getLogger(__name__)
        
        # Get database manager
        self.db_manager = get_unified_database()
        
        # Initialize progress bar
        self.pbar = None
        if total_items:
            self.pbar = tqdm(total=total_items, desc=desc, 
                           unit='files', dynamic_ncols=True)
        
        # Initialize database for resume capability
        if enable_resume:
            if not self.db_manager.table_exists('progress', 'progress_state'):
                # Progress schema already initialized in unified database
                pass
                self._migrate_existing_data()
            self._load_state()
    
    def _migrate_existing_data(self):
        """Migrate data from old database if it exists"""
        old_db_path = 'progress.db'
        if os.path.exists(old_db_path):
            self.logger.info("Migrating data from old progress database")
            import sqlite3
            old_conn = sqlite3.connect(old_db_path)
            old_conn.row_factory = sqlite3.Row
            
            try:
                # Migrate progress state
                cursor = old_conn.execute("SELECT * FROM progress_state WHERE id = 1")
                state = cursor.fetchone()
                
                if state:
                    self.db_manager.execute_update(
                        'progress',
                        """INSERT OR REPLACE INTO progress_state 
                           (id, current_phase, current_file, total_files, 
                            processed_files, phase_data, last_updated)
                           VALUES (1, ?, ?, ?, ?, ?, ?)""",
                        (
                            state['current_phase'],
                            state['last_file'],
                            state['total_items'],
                            state['processed'],
                            state['state_data'],
                            state['updated_at']
                        )
                    )
                    self.logger.info("Migrated progress state")
                
                # Migrate processed files
                cursor = old_conn.execute("SELECT * FROM processed_files")
                files = cursor.fetchall()
                
                if files:
                    file_data = []
                    for file in files:
                        # Map old status to new schema
                        status = file['status']
                        if status not in ['completed', 'failed', 'skipped']:
                            status = 'completed'
                        
                        file_data.append((
                            file['file_path'],
                            state['current_phase'] or 'unknown',
                            status,
                            None,  # error_message
                            file['processed_at']
                        ))
                    
                    self.db_manager.execute_many(
                        'progress',
                        """INSERT OR IGNORE INTO processed_files 
                           (file_path, phase, status, error_message, processed_at)
                           VALUES (?, ?, ?, ?, ?)""",
                        file_data
                    )
                    self.logger.info(f"Migrated {len(files)} processed files")
                    
            except Exception as e:
                self.logger.error(f"Error during migration: {e}")
            finally:
                old_conn.close()
                # Rename old database
                os.rename(old_db_path, old_db_path + '.migrated')
                self.logger.info("Old database renamed to progress.db.migrated")
    
    def _save_state(self, last_file: str = None, state_data: Dict = None):
        """Save current state for resume capability"""
        if not self.enable_resume:
            return
        
        self.db_manager.execute_update(
            'progress',
            """INSERT OR REPLACE INTO progress_state 
               (id, current_phase, current_file, total_files, processed_files, 
                phase_data, last_updated)
               VALUES (1, ?, ?, ?, ?, ?, ?)""",
            (
                self.current_phase,
                last_file,
                self.total_items,
                self.processed,
                json.dumps(state_data) if state_data else None,
                datetime.now().isoformat()
            )
        )
    
    def _load_state(self) -> Optional[Dict]:
        """Load saved state for resuming"""
        if not self.enable_resume:
            return None
        
        result = self.db_manager.execute_query(
            'progress',
            "SELECT * FROM progress_state WHERE id = 1"
        )
        
        if result:
            state = result[0]
            self.processed = state['processed_files'] or 0
            self.total_items = state['total_files'] or self.total_items
            self.current_phase = state['current_phase']
            
            # Update progress bar
            if self.pbar and self.processed > 0:
                self.pbar.n = self.processed
                self.pbar.refresh()
            
            return {
                'last_file': state['current_file'],
                'phase_data': json.loads(state['phase_data']) if state['phase_data'] else None,
                'processed': self.processed
            }
        
        return None
    
    def set_phase(self, phase: str, checkpoint_data: Dict = None):
        """Set current processing phase"""
        self.current_phase = phase
        self.phase_start_time = time.time()
        
        if self.enable_resume:
            # Save phase checkpoint
            self.db_manager.execute_update(
                'progress',
                """INSERT OR REPLACE INTO phase_checkpoints 
                   (phase, checkpoint_data, files_processed, files_total, 
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    phase,
                    json.dumps(checkpoint_data) if checkpoint_data else None,
                    self.processed,
                    self.total_items,
                    datetime.now().isoformat(),
                    datetime.now().isoformat()
                )
            )
            
            self._save_state(state_data=checkpoint_data)
    
    def update(self, n: int = 1, file_path: str = None, 
               status: str = 'completed', error: str = None):
        """Update progress"""
        self.processed += n
        
        if status == 'error':
            self.errors += 1
        elif status == 'skipped':
            self.skipped += 1
        
        # Update progress bar
        if self.pbar:
            self.pbar.update(n)
            
            # Update description with stats
            stats_str = f"{self.desc} | Errors: {self.errors}"
            if self.skipped > 0:
                stats_str += f" | Skipped: {self.skipped}"
            self.pbar.set_description(stats_str)
        
        # Save to database
        if self.enable_resume and file_path:
            self.db_manager.execute_update(
                'progress',
                """INSERT OR REPLACE INTO processed_files 
                   (file_path, phase, status, error_message, processed_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    file_path,
                    self.current_phase or 'unknown',
                    status,
                    error,
                    datetime.now().isoformat()
                )
            )
            
            # Periodically save state
            if self.processed % 10 == 0:
                self._save_state(last_file=file_path)
    
    def is_processed(self, file_path: str, phase: str = None) -> bool:
        """Check if a file has already been processed"""
        if not self.enable_resume:
            return False
        
        if phase:
            result = self.db_manager.execute_query(
                'progress',
                """SELECT 1 FROM processed_files 
                   WHERE file_path = ? AND phase = ? AND status = 'completed'""",
                (file_path, phase)
            )
        else:
            result = self.db_manager.execute_query(
                'progress',
                """SELECT 1 FROM processed_files 
                   WHERE file_path = ? AND status = 'completed'""",
                (file_path,)
            )
        
        return len(result) > 0
    
    def get_resume_info(self) -> Dict:
        """Get information for resuming processing"""
        if not self.enable_resume:
            return {}
        
        # Get phase checkpoints
        checkpoints = self.db_manager.execute_query(
            'progress',
            """SELECT phase, files_processed, files_total, updated_at
               FROM phase_checkpoints
               ORDER BY updated_at DESC"""
        )
        
        # Get processed files count by phase
        phase_counts = self.db_manager.execute_query(
            'progress',
            """SELECT phase, status, COUNT(*) as count
               FROM processed_files
               GROUP BY phase, status"""
        )
        
        # Format results
        phase_stats = {}
        for row in phase_counts:
            phase = row['phase']
            if phase not in phase_stats:
                phase_stats[phase] = {'completed': 0, 'failed': 0, 'skipped': 0}
            phase_stats[phase][row['status']] = row['count']
        
        return {
            'checkpoints': [dict(cp) for cp in checkpoints],
            'phase_stats': phase_stats,
            'total_processed': self.processed,
            'can_resume': len(checkpoints) > 0
        }
    
    def close(self):
        """Close progress tracker and save final state"""
        if self.pbar:
            self.pbar.close()
        
        if self.enable_resume:
            self._save_state()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class ProgressReporter:
    """Generate progress reports and statistics"""
    
    def __init__(self):
        self.db_manager = get_unified_database()
    
    def generate_report(self, output_format: str = 'text') -> str:
        """Generate a progress report"""
        # Check if progress database is initialized
        if not self.db_manager.table_exists('progress', 'progress_state'):
            return "No progress data available."
        
        # Get current state
        state_result = self.db_manager.execute_query(
            'progress',
            "SELECT * FROM progress_state WHERE id = 1"
        )
        
        if not state_result:
            return "No progress data available."
        
        state = state_result[0]
        
        # Get phase statistics
        phase_stats = self.db_manager.execute_query(
            'progress',
            """SELECT phase, status, COUNT(*) as count
               FROM processed_files
               GROUP BY phase, status
               ORDER BY phase, status"""
        )
        
        # Format report
        if output_format == 'json':
            return self._generate_json_report(state, phase_stats)
        else:
            return self._generate_text_report(state, phase_stats)
    
    def _generate_text_report(self, state: Dict, phase_stats: List[Dict]) -> str:
        """Generate text format report"""
        lines = [
            "=" * 60,
            "DJ Music Cleanup Tool - Progress Report",
            "=" * 60,
            f"Last Updated: {state['last_updated']}",
            f"Current Phase: {state['current_phase'] or 'None'}",
            f"Total Files: {state['total_files'] or 'Unknown'}",
            f"Processed Files: {state['processed_files'] or 0}",
            ""
        ]
        
        # Group stats by phase
        phases = {}
        for row in phase_stats:
            phase = row['phase']
            if phase not in phases:
                phases[phase] = {}
            phases[phase][row['status']] = row['count']
        
        # Add phase details
        lines.append("Phase Statistics:")
        lines.append("-" * 40)
        
        for phase, stats in phases.items():
            total = sum(stats.values())
            completed = stats.get('completed', 0)
            failed = stats.get('failed', 0)
            skipped = stats.get('skipped', 0)
            
            lines.append(f"\n{phase}:")
            lines.append(f"  Total: {total}")
            lines.append(f"  Completed: {completed}")
            if failed > 0:
                lines.append(f"  Failed: {failed}")
            if skipped > 0:
                lines.append(f"  Skipped: {skipped}")
            
            if total > 0:
                completion_pct = (completed / total) * 100
                lines.append(f"  Completion: {completion_pct:.1f}%")
        
        lines.append("=" * 60)
        
        return "\n".join(lines)
    
    def _generate_json_report(self, state: Dict, phase_stats: List[Dict]) -> str:
        """Generate JSON format report"""
        # Group stats by phase
        phases = {}
        for row in phase_stats:
            phase = row['phase']
            if phase not in phases:
                phases[phase] = {'completed': 0, 'failed': 0, 'skipped': 0}
            phases[phase][row['status']] = row['count']
        
        report = {
            'last_updated': state['last_updated'],
            'current_phase': state['current_phase'],
            'total_files': state['total_files'],
            'processed_files': state['processed_files'],
            'phases': phases
        }
        
        return json.dumps(report, indent=2)