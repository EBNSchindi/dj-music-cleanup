"""
Database schema definitions and migrations for DJ Music Cleanup Tool
"""

import logging
from typing import Dict, List, Callable
from datetime import datetime

logger = logging.getLogger(__name__)


class SchemaManager:
    """Manages database schemas and migrations"""
    
    def __init__(self):
        self.schemas = {
            'fingerprints': self._get_fingerprints_schema,
            'operations': self._get_operations_schema,
            'progress': self._get_progress_schema
        }
        
    def _get_fingerprints_schema(self) -> Dict[str, str]:
        """Schema for fingerprints database"""
        return {
            'fingerprints': """
                CREATE TABLE IF NOT EXISTS fingerprints (
                    file_path TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL,
                    file_hash TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    modified_time REAL NOT NULL,
                    duration REAL,
                    sample_rate INTEGER,
                    bit_depth INTEGER,
                    channels INTEGER,
                    codec TEXT,
                    bitrate INTEGER,
                    quality_score REAL,
                    quality_issues TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
            'fingerprints_idx': """
                CREATE INDEX IF NOT EXISTS idx_fingerprints_hash 
                ON fingerprints(file_hash)
            """,
            'fingerprints_quality_idx': """
                CREATE INDEX IF NOT EXISTS idx_fingerprints_quality 
                ON fingerprints(quality_score)
            """,
            'duplicates': """
                CREATE TABLE IF NOT EXISTS duplicates (
                    group_id TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    is_primary BOOLEAN DEFAULT 0,
                    similarity_score REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (group_id, file_path),
                    FOREIGN KEY (file_path) REFERENCES fingerprints(file_path)
                        ON DELETE CASCADE
                )
            """,
            'duplicates_idx': """
                CREATE INDEX IF NOT EXISTS idx_duplicates_group 
                ON duplicates(group_id)
            """,
            'schema_version': """
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
        }
        
    def _get_operations_schema(self) -> Dict[str, str]:
        """Schema for file operations database"""
        return {
            'file_operations': """
                CREATE TABLE IF NOT EXISTS file_operations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation_type TEXT NOT NULL CHECK(operation_type IN ('copy', 'move', 'delete', 'rename')),
                    source_path TEXT NOT NULL,
                    destination_path TEXT,
                    status TEXT NOT NULL CHECK(status IN ('pending', 'completed', 'failed', 'skipped')),
                    error_message TEXT,
                    file_size INTEGER,
                    operation_group TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                )
            """,
            'operations_idx': """
                CREATE INDEX IF NOT EXISTS idx_operations_status 
                ON file_operations(status)
            """,
            'operations_group_idx': """
                CREATE INDEX IF NOT EXISTS idx_operations_group 
                ON file_operations(operation_group)
            """,
            'duplicate_decisions': """
                CREATE TABLE IF NOT EXISTS duplicate_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT NOT NULL,
                    kept_file TEXT NOT NULL,
                    removed_files TEXT NOT NULL,
                    decision_reason TEXT,
                    quality_scores TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
            'operation_stats': """
                CREATE TABLE IF NOT EXISTS operation_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation_group TEXT NOT NULL,
                    total_files INTEGER DEFAULT 0,
                    processed_files INTEGER DEFAULT 0,
                    failed_files INTEGER DEFAULT 0,
                    total_size_bytes INTEGER DEFAULT 0,
                    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    end_time TIMESTAMP,
                    UNIQUE(operation_group)
                )
            """,
            'schema_version': """
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
        }
        
    def _get_progress_schema(self) -> Dict[str, str]:
        """Schema for progress tracking database"""
        return {
            'progress_state': """
                CREATE TABLE IF NOT EXISTS progress_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    current_phase TEXT NOT NULL,
                    current_file TEXT,
                    total_files INTEGER DEFAULT 0,
                    processed_files INTEGER DEFAULT 0,
                    phase_data TEXT,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
            'processed_files': """
                CREATE TABLE IF NOT EXISTS processed_files (
                    file_path TEXT PRIMARY KEY,
                    phase TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('completed', 'failed', 'skipped')),
                    error_message TEXT,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
            'processed_idx': """
                CREATE INDEX IF NOT EXISTS idx_processed_phase 
                ON processed_files(phase)
            """,
            'phase_checkpoints': """
                CREATE TABLE IF NOT EXISTS phase_checkpoints (
                    phase TEXT PRIMARY KEY,
                    checkpoint_data TEXT,
                    files_processed INTEGER DEFAULT 0,
                    files_total INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
            'schema_version': """
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
        }
        
    def create_schema(self, connection, db_name: str):
        """Create schema for a specific database"""
        if db_name not in self.schemas:
            raise ValueError(f"Unknown database: {db_name}")
            
        schema_dict = self.schemas[db_name]()
        
        for table_name, create_sql in schema_dict.items():
            try:
                connection.execute(create_sql)
                logger.debug(f"Created/verified table: {table_name}")
            except Exception as e:
                logger.error(f"Error creating table {table_name}: {e}")
                raise
                
        # Set initial schema version
        connection.execute(
            "INSERT OR IGNORE INTO schema_version (version) VALUES (?)",
            (1,)
        )
        

class MigrationManager:
    """Manages database migrations"""
    
    def __init__(self):
        self.migrations: Dict[str, Dict[int, List[str]]] = {
            'fingerprints': {},
            'operations': {},
            'progress': {}
        }
        
    def add_migration(self, db_name: str, version: int, 
                     migration_sql: List[str]):
        """Add a migration for a specific database version"""
        if db_name not in self.migrations:
            self.migrations[db_name] = {}
        self.migrations[db_name][version] = migration_sql
        
    def get_current_version(self, connection) -> int:
        """Get current schema version"""
        try:
            cursor = connection.execute(
                "SELECT MAX(version) FROM schema_version"
            )
            result = cursor.fetchone()
            return result[0] if result and result[0] else 0
        except:
            return 0
            
    def apply_migrations(self, connection, db_name: str, 
                        target_version: int = None):
        """Apply migrations up to target version"""
        current_version = self.get_current_version(connection)
        
        if db_name not in self.migrations:
            return
            
        db_migrations = self.migrations[db_name]
        if not db_migrations:
            return
            
        if target_version is None:
            target_version = max(db_migrations.keys())
            
        for version in sorted(db_migrations.keys()):
            if version > current_version and version <= target_version:
                logger.info(f"Applying migration {version} to {db_name}")
                
                for sql in db_migrations[version]:
                    try:
                        connection.execute(sql)
                    except Exception as e:
                        logger.error(f"Migration {version} failed: {e}")
                        raise
                        
                # Update schema version
                connection.execute(
                    "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
                    (version,)
                )
                connection.commit()
                

# Schema initialization functions for DatabaseManager
def initialize_fingerprints_schema(connection):
    """Initialize fingerprints database schema"""
    schema_mgr = SchemaManager()
    schema_mgr.create_schema(connection, 'fingerprints')
    

def initialize_operations_schema(connection):
    """Initialize operations database schema"""
    schema_mgr = SchemaManager()
    schema_mgr.create_schema(connection, 'operations')
    

def initialize_progress_schema(connection):
    """Initialize progress database schema"""
    schema_mgr = SchemaManager()
    schema_mgr.create_schema(connection, 'progress')
    

# Example migrations
def setup_example_migrations():
    """Setup example migrations for future schema changes"""
    migration_mgr = MigrationManager()
    
    # Example: Add artist and album fields to fingerprints
    migration_mgr.add_migration('fingerprints', 2, [
        "ALTER TABLE fingerprints ADD COLUMN artist TEXT",
        "ALTER TABLE fingerprints ADD COLUMN album TEXT",
        "ALTER TABLE fingerprints ADD COLUMN title TEXT",
        "ALTER TABLE fingerprints ADD COLUMN year INTEGER"
    ])
    
    # Example: Add undo capability to operations
    migration_mgr.add_migration('operations', 2, [
        """CREATE TABLE IF NOT EXISTS undo_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation_id INTEGER NOT NULL,
            undo_command TEXT NOT NULL,
            executed BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (operation_id) REFERENCES file_operations(id)
        )"""
    ])
    
    return migration_mgr