"""
Unified Database Management

Consolidates all databases into a single music_cleanup.db with proper schemas:
- Fingerprints (replaces fingerprints.db)
- Operations/Recovery (replaces operations.db) 
- Progress/Statistics (replaces progress.db)
"""

import logging
import sqlite3
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass, asdict
from contextlib import contextmanager
import json
import threading


@dataclass
class FingerprintRecord:
    """Audio fingerprint record"""
    file_path: str
    fingerprint: str
    duration: float
    file_size: int
    algorithm: str
    bitrate: Optional[int] = None
    format: Optional[str] = None
    file_mtime: float = 0
    generated_at: float = 0


@dataclass
class OperationRecord:
    """File operation record for recovery"""
    operation_id: str
    operation_type: str  # move, copy, delete, organize
    source_path: str
    target_path: Optional[str]
    operation_data: str  # JSON serialized data
    timestamp: float
    status: str  # pending, completed, failed, rolled_back


@dataclass
class ProgressRecord:
    """Processing progress record"""
    session_id: str
    stage: str
    files_total: int
    files_processed: int
    files_succeeded: int
    files_failed: int
    bytes_processed: int
    start_time: float
    last_update: float
    metadata: str  # JSON serialized additional data


class UnifiedDatabase:
    """
    Unified database manager for all DJ Music Cleanup Tool data.
    
    Manages three main schemas in a single SQLite database:
    1. Fingerprints - Audio fingerprint cache
    2. Operations - File operations for recovery/undo
    3. Progress - Processing progress and statistics
    """
    
    def __init__(self, db_path: str = "music_cleanup.db"):
        self.db_path = Path(db_path)
        self.logger = logging.getLogger(__name__)
        self._lock = threading.RLock()
        
        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        self._init_database()
        
        self.logger.info(f"UnifiedDatabase initialized: {self.db_path}")
    
    def _init_database(self):
        """Initialize database with all required schemas"""
        with self._get_connection() as conn:
            # Enable WAL mode for better concurrency
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA synchronous=NORMAL")
            
            # Create fingerprints schema
            conn.execute("""
                CREATE TABLE IF NOT EXISTS fingerprints (
                    file_path TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    duration REAL NOT NULL,
                    file_size INTEGER NOT NULL,
                    algorithm TEXT NOT NULL,
                    bitrate INTEGER,
                    format TEXT,
                    file_mtime REAL NOT NULL,
                    generated_at REAL NOT NULL,
                    UNIQUE(file_path)
                )
            """)
            
            # Create index for fingerprint lookups
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_fingerprint 
                ON fingerprints(fingerprint)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_fingerprint_algorithm 
                ON fingerprints(algorithm, fingerprint)
            """)
            
            # Create operations schema
            conn.execute("""
                CREATE TABLE IF NOT EXISTS operations (
                    operation_id TEXT PRIMARY KEY,
                    operation_type TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    target_path TEXT,
                    operation_data TEXT,
                    timestamp REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    UNIQUE(operation_id)
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_operations_status 
                ON operations(status, timestamp)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_operations_source 
                ON operations(source_path)
            """)
            
            # Create progress schema
            conn.execute("""
                CREATE TABLE IF NOT EXISTS progress (
                    session_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    files_total INTEGER NOT NULL,
                    files_processed INTEGER NOT NULL,
                    files_succeeded INTEGER NOT NULL,
                    files_failed INTEGER NOT NULL,
                    bytes_processed INTEGER NOT NULL,
                    start_time REAL NOT NULL,
                    last_update REAL NOT NULL,
                    metadata TEXT,
                    PRIMARY KEY (session_id, stage)
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_progress_session 
                ON progress(session_id, last_update)
            """)
            
            # Create statistics view
            conn.execute("""
                CREATE VIEW IF NOT EXISTS statistics_summary AS
                SELECT 
                    COUNT(*) as total_sessions,
                    SUM(files_processed) as total_files_processed,
                    SUM(bytes_processed) as total_bytes_processed,
                    AVG(files_succeeded * 1.0 / NULLIF(files_total, 0)) as avg_success_rate,
                    MIN(start_time) as first_session,
                    MAX(last_update) as last_session
                FROM progress
            """)
            
            conn.commit()
    
    @contextmanager
    def _get_connection(self):
        """Get database connection with proper error handling"""
        conn = None
        try:
            with self._lock:
                conn = sqlite3.connect(str(self.db_path), timeout=30.0)
                conn.row_factory = sqlite3.Row
                yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            self.logger.error(f"Database error: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    # ===== FINGERPRINT OPERATIONS =====
    
    def store_fingerprint(self, fingerprint: FingerprintRecord) -> bool:
        """Store audio fingerprint"""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO fingerprints 
                    (file_path, fingerprint, duration, file_size, algorithm, 
                     bitrate, format, file_mtime, generated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    fingerprint.file_path,
                    fingerprint.fingerprint,
                    fingerprint.duration,
                    fingerprint.file_size,
                    fingerprint.algorithm,
                    fingerprint.bitrate,
                    fingerprint.format,
                    fingerprint.file_mtime,
                    fingerprint.generated_at
                ))
                conn.commit()
                return True
        except Exception as e:
            self.logger.error(f"Failed to store fingerprint: {e}")
            return False
    
    def get_fingerprint(self, file_path: str) -> Optional[FingerprintRecord]:
        """Get fingerprint by file path"""
        try:
            with self._get_connection() as conn:
                row = conn.execute("""
                    SELECT * FROM fingerprints WHERE file_path = ?
                """, (file_path,)).fetchone()
                
                if row:
                    return FingerprintRecord(**dict(row))
                return None
        except Exception as e:
            self.logger.error(f"Failed to get fingerprint: {e}")
            return None
    
    def find_duplicate_fingerprints(self, fingerprint: str, algorithm: str = None) -> List[FingerprintRecord]:
        """Find files with matching fingerprints"""
        try:
            with self._get_connection() as conn:
                if algorithm:
                    rows = conn.execute("""
                        SELECT * FROM fingerprints 
                        WHERE fingerprint = ? AND algorithm = ?
                        ORDER BY generated_at DESC
                    """, (fingerprint, algorithm)).fetchall()
                else:
                    rows = conn.execute("""
                        SELECT * FROM fingerprints 
                        WHERE fingerprint = ?
                        ORDER BY generated_at DESC
                    """, (fingerprint,)).fetchall()
                
                return [FingerprintRecord(**dict(row)) for row in rows]
        except Exception as e:
            self.logger.error(f"Failed to find duplicates: {e}")
            return []
    
    def get_fingerprint_statistics(self) -> Dict[str, Any]:
        """Get fingerprint statistics"""
        try:
            with self._get_connection() as conn:
                result = conn.execute("""
                    SELECT 
                        COUNT(*) as total_fingerprints,
                        COUNT(DISTINCT fingerprint) as unique_fingerprints,
                        COUNT(CASE WHEN algorithm = 'chromaprint' THEN 1 END) as chromaprint_count,
                        COUNT(CASE WHEN algorithm = 'md5' THEN 1 END) as md5_count,
                        AVG(duration) as avg_duration,
                        SUM(file_size) as total_size
                    FROM fingerprints
                """).fetchone()
                
                return dict(result) if result else {}
        except Exception as e:
            self.logger.error(f"Failed to get fingerprint stats: {e}")
            return {}
    
    def cleanup_stale_fingerprints(self, max_age_days: int = 30) -> int:
        """Remove fingerprints for files that no longer exist"""
        try:
            cutoff_time = time.time() - (max_age_days * 24 * 3600)
            
            with self._get_connection() as conn:
                # Get potentially stale fingerprints
                rows = conn.execute("""
                    SELECT file_path FROM fingerprints 
                    WHERE generated_at < ?
                """, (cutoff_time,)).fetchall()
                
                # Check which files still exist
                removed_count = 0
                for row in rows:
                    file_path = row[0]
                    if not Path(file_path).exists():
                        conn.execute("DELETE FROM fingerprints WHERE file_path = ?", (file_path,))
                        removed_count += 1
                
                conn.commit()
                return removed_count
        except Exception as e:
            self.logger.error(f"Failed to cleanup fingerprints: {e}")
            return 0
    
    # ===== OPERATION OPERATIONS =====
    
    def record_operation(self, operation: OperationRecord) -> bool:
        """Record file operation for recovery/undo"""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO operations 
                    (operation_id, operation_type, source_path, target_path, 
                     operation_data, timestamp, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    operation.operation_id,
                    operation.operation_type,
                    operation.source_path,
                    operation.target_path,
                    operation.operation_data,
                    operation.timestamp,
                    operation.status
                ))
                conn.commit()
                return True
        except Exception as e:
            self.logger.error(f"Failed to record operation: {e}")
            return False
    
    def update_operation_status(self, operation_id: str, status: str) -> bool:
        """Update operation status"""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    UPDATE operations SET status = ? WHERE operation_id = ?
                """, (status, operation_id))
                conn.commit()
                return True
        except Exception as e:
            self.logger.error(f"Failed to update operation status: {e}")
            return False
    
    def get_operations_for_recovery(self, status: str = "completed") -> List[OperationRecord]:
        """Get operations for recovery/undo"""
        try:
            with self._get_connection() as conn:
                rows = conn.execute("""
                    SELECT * FROM operations 
                    WHERE status = ?
                    ORDER BY timestamp DESC
                """, (status,)).fetchall()
                
                return [OperationRecord(**dict(row)) for row in rows]
        except Exception as e:
            self.logger.error(f"Failed to get operations: {e}")
            return []
    
    # ===== PROGRESS OPERATIONS =====
    
    def update_progress(self, progress: ProgressRecord) -> bool:
        """Update processing progress"""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO progress 
                    (session_id, stage, files_total, files_processed, files_succeeded, 
                     files_failed, bytes_processed, start_time, last_update, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    progress.session_id,
                    progress.stage,
                    progress.files_total,
                    progress.files_processed,
                    progress.files_succeeded,
                    progress.files_failed,
                    progress.bytes_processed,
                    progress.start_time,
                    progress.last_update,
                    progress.metadata
                ))
                conn.commit()
                return True
        except Exception as e:
            self.logger.error(f"Failed to update progress: {e}")
            return False
    
    def get_session_progress(self, session_id: str) -> List[ProgressRecord]:
        """Get progress for a session"""
        try:
            with self._get_connection() as conn:
                rows = conn.execute("""
                    SELECT * FROM progress 
                    WHERE session_id = ?
                    ORDER BY start_time ASC
                """, (session_id,)).fetchall()
                
                return [ProgressRecord(**dict(row)) for row in rows]
        except Exception as e:
            self.logger.error(f"Failed to get progress: {e}")
            return []
    
    def get_overall_statistics(self) -> Dict[str, Any]:
        """Get overall processing statistics"""
        try:
            with self._get_connection() as conn:
                result = conn.execute("SELECT * FROM statistics_summary").fetchone()
                return dict(result) if result else {}
        except Exception as e:
            self.logger.error(f"Failed to get statistics: {e}")
            return {}
    
    # ===== MAINTENANCE OPERATIONS =====
    
    def vacuum_database(self) -> bool:
        """Vacuum database to reclaim space"""
        try:
            with self._get_connection() as conn:
                conn.execute("VACUUM")
                conn.commit()
                self.logger.info("Database vacuumed successfully")
                return True
        except Exception as e:
            self.logger.error(f"Failed to vacuum database: {e}")
            return False
    
    def get_database_size(self) -> Dict[str, int]:
        """Get database size information"""
        try:
            db_size = self.db_path.stat().st_size if self.db_path.exists() else 0
            
            with self._get_connection() as conn:
                fingerprint_count = conn.execute("SELECT COUNT(*) FROM fingerprints").fetchone()[0]
                operation_count = conn.execute("SELECT COUNT(*) FROM operations").fetchone()[0]
                progress_count = conn.execute("SELECT COUNT(*) FROM progress").fetchone()[0]
                
                return {
                    'total_size_bytes': db_size,
                    'fingerprint_records': fingerprint_count,
                    'operation_records': operation_count,
                    'progress_records': progress_count
                }
        except Exception as e:
            self.logger.error(f"Failed to get database size: {e}")
            return {}
    
    def migrate_from_legacy_databases(self, 
                                    fingerprint_db: Optional[str] = None,
                                    operations_db: Optional[str] = None,
                                    progress_db: Optional[str] = None) -> Dict[str, int]:
        """Migrate data from legacy separate databases"""
        migration_results = {
            'fingerprints_migrated': 0,
            'operations_migrated': 0,
            'progress_migrated': 0
        }
        
        # This would implement migration logic
        # For now, just log the intention
        self.logger.info("Legacy database migration would be implemented here")
        
        return migration_results
    
    # ===== BATCH OPERATIONS FOR STREAMING =====
    
    def store_fingerprints_batch(self, fingerprints: List[FingerprintRecord]) -> bool:
        """
        Store multiple fingerprints in a single transaction for better performance.
        
        Args:
            fingerprints: List of fingerprint records to store
            
        Returns:
            True if successful, False otherwise
        """
        if not fingerprints:
            return True
            
        try:
            with self._get_connection() as conn:
                data = [
                    (
                        fp.file_path, fp.fingerprint, fp.duration, fp.file_size,
                        fp.algorithm, fp.bitrate, fp.format, fp.file_mtime, fp.generated_at
                    )
                    for fp in fingerprints
                ]
                
                conn.executemany("""
                    INSERT OR REPLACE INTO fingerprints 
                    (file_path, fingerprint, duration, file_size, algorithm, bitrate, format, file_mtime, generated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, data)
                conn.commit()
                
                self.logger.debug(f"Stored {len(fingerprints)} fingerprints in batch")
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to store fingerprint batch: {e}")
            return False
    
    def find_duplicate_fingerprints_streaming(self, batch_size: int = 1000) -> List[Tuple[str, List[FingerprintRecord]]]:
        """
        Find duplicate fingerprints in streaming batches for memory efficiency.
        
        Args:
            batch_size: Number of duplicates to return per batch
            
        Yields:
            Tuples of (fingerprint, list_of_duplicate_records)
        """
        try:
            with self._get_connection() as conn:
                # Get all fingerprints that appear more than once
                duplicates_cursor = conn.execute("""
                    SELECT fingerprint, COUNT(*) as count
                    FROM fingerprints
                    GROUP BY fingerprint
                    HAVING COUNT(*) > 1
                    ORDER BY COUNT(*) DESC
                """)
                
                batch = []
                for fingerprint, count in duplicates_cursor:
                    # Get all files with this fingerprint
                    files_cursor = conn.execute("""
                        SELECT file_path, fingerprint, duration, file_size, algorithm, 
                               bitrate, format, file_mtime, generated_at
                        FROM fingerprints
                        WHERE fingerprint = ?
                        ORDER BY file_size DESC, file_path
                    """, (fingerprint,))
                    
                    records = [FingerprintRecord(**dict(row)) for row in files_cursor.fetchall()]
                    batch.append((fingerprint, records))
                    
                    if len(batch) >= batch_size:
                        yield batch
                        batch = []
                
                # Yield remaining batch
                if batch:
                    yield batch
                    
        except Exception as e:
            self.logger.error(f"Failed to find duplicate fingerprints: {e}")
            return []
    
    def create_temp_fingerprint_index(self) -> bool:
        """
        Create temporary indexes for faster duplicate detection on large datasets.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            with self._get_connection() as conn:
                # Create temporary index for faster grouping
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_temp_fingerprint_dup 
                    ON fingerprints(fingerprint, file_size DESC)
                """)
                
                # Create index for file path lookups
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_temp_file_path 
                    ON fingerprints(file_path)
                """)
                
                conn.commit()
                self.logger.debug("Created temporary fingerprint indexes")
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to create temporary indexes: {e}")
            return False
    
    def drop_temp_fingerprint_index(self) -> bool:
        """
        Drop temporary indexes after duplicate detection.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            with self._get_connection() as conn:
                conn.execute("DROP INDEX IF EXISTS idx_temp_fingerprint_dup")
                conn.execute("DROP INDEX IF EXISTS idx_temp_file_path")
                conn.commit()
                self.logger.debug("Dropped temporary fingerprint indexes")
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to drop temporary indexes: {e}")
            return False
    
    def get_fingerprint_count_by_hash(self, fingerprint_hash: str) -> int:
        """
        Get count of files with specific fingerprint hash.
        
        Args:
            fingerprint_hash: The fingerprint hash to count
            
        Returns:
            Number of files with this fingerprint
        """
        try:
            with self._get_connection() as conn:
                result = conn.execute("""
                    SELECT COUNT(*) FROM fingerprints WHERE fingerprint = ?
                """, (fingerprint_hash,)).fetchone()
                return result[0] if result else 0
                
        except Exception as e:
            self.logger.error(f"Failed to count fingerprints: {e}")
            return 0
    
    def clear_fingerprints_table(self) -> bool:
        """
        Clear all fingerprints from the database (for testing/reset).
        
        Returns:
            True if successful, False otherwise
        """
        try:
            with self._get_connection() as conn:
                conn.execute("DELETE FROM fingerprints")
                conn.commit()
                self.logger.info("Cleared all fingerprints from database")
                return True
                
        except Exception as e:
            self.logger.error(f"Failed to clear fingerprints: {e}")
            return False


# Global unified database instance
_unified_db: Optional[UnifiedDatabase] = None

def get_unified_database(db_path: str = "music_cleanup.db") -> UnifiedDatabase:
    """Get global unified database instance"""
    global _unified_db
    if _unified_db is None or str(_unified_db.db_path) != db_path:
        _unified_db = UnifiedDatabase(db_path)
    return _unified_db