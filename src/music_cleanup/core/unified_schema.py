"""
Unified Database Schema for DJ Music Cleanup Tool

Consolidates the three separate databases (fingerprints.db, operations.db, progress.db)
into a single music_cleanup.db with proper foreign key relationships and normalized structure.
"""

import logging
import sqlite3
import json
from typing import Dict, List, Callable, Optional, Any
from datetime import datetime
from pathlib import Path

# Setup logger with a safe fallback
try:
    logger = logging.getLogger(__name__)
except:
    import sys
    logger = logging.getLogger()
    logger.addHandler(logging.StreamHandler(sys.stdout))


class UnifiedSchemaManager:
    """Manages the unified database schema with proper relationships"""
    
    def __init__(self):
        self.schema_version = 1
        self.schema_tables = self._get_unified_schema()
        
    def _get_unified_schema(self) -> Dict[str, str]:
        """Define the unified database schema with foreign key relationships"""
        return {
            # Central files table - core entity for all file-related data
            'files': """
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE NOT NULL,
                    file_hash TEXT,
                    file_size INTEGER,
                    modified_time REAL,
                    fingerprint_id INTEGER,
                    metadata_id INTEGER,
                    quality_score REAL,
                    status TEXT DEFAULT 'discovered' CHECK(status IN ('discovered', 'processing', 'completed', 'failed', 'skipped')),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (fingerprint_id) REFERENCES fingerprints(id) ON DELETE SET NULL,
                    FOREIGN KEY (metadata_id) REFERENCES metadata(id) ON DELETE SET NULL
                )
            """,
            
            # Audio fingerprints - normalized fingerprint data
            'fingerprints': """
                CREATE TABLE IF NOT EXISTS fingerprints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fingerprint TEXT UNIQUE NOT NULL,
                    duration REAL,
                    sample_rate INTEGER,
                    bit_depth INTEGER,
                    channels INTEGER,
                    codec TEXT,
                    bitrate INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
            
            # Metadata - normalized metadata information
            'metadata': """
                CREATE TABLE IF NOT EXISTS metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    artist TEXT,
                    title TEXT,
                    album TEXT,
                    year INTEGER,
                    genre TEXT,
                    track_number INTEGER,
                    disc_number INTEGER,
                    artist_sort TEXT,
                    album_artist TEXT,
                    composer TEXT,
                    musicbrainz_track_id TEXT,
                    musicbrainz_album_id TEXT,
                    musicbrainz_artist_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
            
            # Quality analysis results
            'quality_analysis': """
                CREATE TABLE IF NOT EXISTS quality_analysis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER NOT NULL,
                    overall_score REAL NOT NULL,
                    dynamic_range REAL,
                    peak_level REAL,
                    rms_level REAL,
                    crest_factor REAL,
                    spectral_centroid REAL,
                    spectral_rolloff REAL,
                    zero_crossing_rate REAL,
                    tempo REAL,
                    quality_issues TEXT, -- JSON array of issues
                    analysis_version TEXT DEFAULT '1.0',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
                )
            """,
            
            # Duplicate groups - tracks which files are duplicates
            'duplicate_groups': """
                CREATE TABLE IF NOT EXISTS duplicate_groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_hash TEXT UNIQUE NOT NULL, -- Hash based on fingerprint or metadata
                    detection_method TEXT NOT NULL CHECK(detection_method IN ('fingerprint', 'metadata', 'hybrid')),
                    similarity_threshold REAL DEFAULT 0.95,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
            
            # Duplicate group members - many-to-many relationship
            'duplicate_members': """
                CREATE TABLE IF NOT EXISTS duplicate_members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id INTEGER NOT NULL,
                    file_id INTEGER NOT NULL,
                    is_primary BOOLEAN DEFAULT 0, -- Which file to keep
                    similarity_score REAL,
                    decision_reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(group_id, file_id),
                    FOREIGN KEY (group_id) REFERENCES duplicate_groups(id) ON DELETE CASCADE,
                    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
                )
            """,
            
            # File operations - tracks all file system operations
            'file_operations': """
                CREATE TABLE IF NOT EXISTS file_operations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER,
                    operation_type TEXT NOT NULL CHECK(operation_type IN ('copy', 'move', 'delete', 'rename', 'analyze')),
                    source_path TEXT NOT NULL,
                    destination_path TEXT,
                    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'in_progress', 'completed', 'failed', 'skipped', 'rolled_back')),
                    error_message TEXT,
                    operation_group TEXT, -- Groups related operations together
                    transaction_id TEXT, -- For atomic operations
                    parent_operation_id INTEGER, -- For operation hierarchies
                    rollback_data TEXT, -- JSON data for rollback
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE SET NULL,
                    FOREIGN KEY (parent_operation_id) REFERENCES file_operations(id) ON DELETE SET NULL
                )
            """,
            
            # Operation groups - metadata about operation batches
            'operation_groups': """
                CREATE TABLE IF NOT EXISTS operation_groups (
                    id TEXT PRIMARY KEY, -- UUID or session-based ID
                    operation_type TEXT NOT NULL, -- 'organize', 'cleanup', 'analyze', etc.
                    total_files INTEGER DEFAULT 0,
                    processed_files INTEGER DEFAULT 0,
                    successful_files INTEGER DEFAULT 0,
                    failed_files INTEGER DEFAULT 0,
                    skipped_files INTEGER DEFAULT 0,
                    total_size_bytes INTEGER DEFAULT 0,
                    processed_size_bytes INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'completed', 'failed', 'cancelled')),
                    configuration TEXT, -- JSON configuration used
                    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    end_time TIMESTAMP,
                    error_message TEXT
                )
            """,
            
            # Progress tracking for ongoing operations
            'progress_tracking': """
                CREATE TABLE IF NOT EXISTS progress_tracking (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation_group_id TEXT NOT NULL,
                    file_id INTEGER,
                    current_phase TEXT NOT NULL, -- 'discovery', 'analysis', 'fingerprinting', 'organization', etc.
                    phase_progress REAL DEFAULT 0.0, -- 0.0 to 1.0
                    phase_data TEXT, -- JSON data specific to the phase
                    last_checkpoint TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (operation_group_id) REFERENCES operation_groups(id) ON DELETE CASCADE,
                    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
                )
            """,
            
            # Recovery checkpoints for crash recovery
            'recovery_checkpoints': """
                CREATE TABLE IF NOT EXISTS recovery_checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation_group_id TEXT NOT NULL,
                    checkpoint_type TEXT NOT NULL CHECK(checkpoint_type IN ('auto', 'manual', 'phase_complete', 'error')),
                    checkpoint_data TEXT NOT NULL, -- JSON state data
                    files_processed INTEGER DEFAULT 0,
                    operations_completed INTEGER DEFAULT 0,
                    memory_usage_mb REAL,
                    error_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (operation_group_id) REFERENCES operation_groups(id) ON DELETE CASCADE
                )
            """,
            
            # Organization target structure
            'organization_targets': """
                CREATE TABLE IF NOT EXISTS organization_targets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_id INTEGER NOT NULL,
                    target_path TEXT NOT NULL,
                    target_filename TEXT NOT NULL,
                    organization_rule TEXT, -- Rule that determined this target
                    confidence_score REAL DEFAULT 1.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (file_id) REFERENCES files(id) ON DELETE CASCADE
                )
            """,
            
            # System configuration and settings
            'system_config': """
                CREATE TABLE IF NOT EXISTS system_config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    value_type TEXT DEFAULT 'string' CHECK(value_type IN ('string', 'integer', 'float', 'boolean', 'json')),
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """,
            
            # Schema version tracking
            'schema_version': """
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    description TEXT,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
        }
    
    def _get_indexes(self) -> Dict[str, str]:
        """Define indexes for optimal query performance"""
        return {
            # Files table indexes
            'idx_files_path': "CREATE INDEX IF NOT EXISTS idx_files_path ON files(path)",
            'idx_files_hash': "CREATE INDEX IF NOT EXISTS idx_files_hash ON files(file_hash)",
            'idx_files_fingerprint': "CREATE INDEX IF NOT EXISTS idx_files_fingerprint ON files(fingerprint_id)",
            'idx_files_metadata': "CREATE INDEX IF NOT EXISTS idx_files_metadata ON files(metadata_id)",
            'idx_files_status': "CREATE INDEX IF NOT EXISTS idx_files_status ON files(status)",
            'idx_files_quality': "CREATE INDEX IF NOT EXISTS idx_files_quality ON files(quality_score)",
            
            # Fingerprints indexes
            'idx_fingerprints_fingerprint': "CREATE INDEX IF NOT EXISTS idx_fingerprints_fingerprint ON fingerprints(fingerprint)",
            'idx_fingerprints_duration': "CREATE INDEX IF NOT EXISTS idx_fingerprints_duration ON fingerprints(duration)",
            'idx_fingerprints_codec': "CREATE INDEX IF NOT EXISTS idx_fingerprints_codec ON fingerprints(codec)",
            
            # Metadata indexes
            'idx_metadata_artist': "CREATE INDEX IF NOT EXISTS idx_metadata_artist ON metadata(artist)",
            'idx_metadata_album': "CREATE INDEX IF NOT EXISTS idx_metadata_album ON metadata(album)",
            'idx_metadata_genre': "CREATE INDEX IF NOT EXISTS idx_metadata_genre ON metadata(genre)",
            'idx_metadata_year': "CREATE INDEX IF NOT EXISTS idx_metadata_year ON metadata(year)",
            'idx_metadata_musicbrainz_track': "CREATE INDEX IF NOT EXISTS idx_metadata_musicbrainz_track ON metadata(musicbrainz_track_id)",
            
            # Quality analysis indexes
            'idx_quality_file': "CREATE INDEX IF NOT EXISTS idx_quality_file ON quality_analysis(file_id)",
            'idx_quality_score': "CREATE INDEX IF NOT EXISTS idx_quality_score ON quality_analysis(overall_score)",
            
            # Duplicate groups indexes
            'idx_duplicate_groups_hash': "CREATE INDEX IF NOT EXISTS idx_duplicate_groups_hash ON duplicate_groups(group_hash)",
            'idx_duplicate_groups_method': "CREATE INDEX IF NOT EXISTS idx_duplicate_groups_method ON duplicate_groups(detection_method)",
            
            # Duplicate members indexes
            'idx_duplicate_members_group': "CREATE INDEX IF NOT EXISTS idx_duplicate_members_group ON duplicate_members(group_id)",
            'idx_duplicate_members_file': "CREATE INDEX IF NOT EXISTS idx_duplicate_members_file ON duplicate_members(file_id)",
            'idx_duplicate_members_primary': "CREATE INDEX IF NOT EXISTS idx_duplicate_members_primary ON duplicate_members(is_primary)",
            
            # File operations indexes
            'idx_operations_file': "CREATE INDEX IF NOT EXISTS idx_operations_file ON file_operations(file_id)",
            'idx_operations_type': "CREATE INDEX IF NOT EXISTS idx_operations_type ON file_operations(operation_type)",
            'idx_operations_status': "CREATE INDEX IF NOT EXISTS idx_operations_status ON file_operations(status)",
            'idx_operations_group': "CREATE INDEX IF NOT EXISTS idx_operations_group ON file_operations(operation_group)",
            'idx_operations_transaction': "CREATE INDEX IF NOT EXISTS idx_operations_transaction ON file_operations(transaction_id)",
            'idx_operations_created': "CREATE INDEX IF NOT EXISTS idx_operations_created ON file_operations(created_at)",
            
            # Operation groups indexes
            'idx_operation_groups_type': "CREATE INDEX IF NOT EXISTS idx_operation_groups_type ON operation_groups(operation_type)",
            'idx_operation_groups_status': "CREATE INDEX IF NOT EXISTS idx_operation_groups_status ON operation_groups(status)",
            'idx_operation_groups_start': "CREATE INDEX IF NOT EXISTS idx_operation_groups_start ON operation_groups(start_time)",
            
            # Progress tracking indexes
            'idx_progress_group': "CREATE INDEX IF NOT EXISTS idx_progress_group ON progress_tracking(operation_group_id)",
            'idx_progress_file': "CREATE INDEX IF NOT EXISTS idx_progress_file ON progress_tracking(file_id)",
            'idx_progress_phase': "CREATE INDEX IF NOT EXISTS idx_progress_phase ON progress_tracking(current_phase)",
            'idx_progress_checkpoint': "CREATE INDEX IF NOT EXISTS idx_progress_checkpoint ON progress_tracking(last_checkpoint)",
            
            # Recovery checkpoints indexes
            'idx_checkpoints_group': "CREATE INDEX IF NOT EXISTS idx_checkpoints_group ON recovery_checkpoints(operation_group_id)",
            'idx_checkpoints_type': "CREATE INDEX IF NOT EXISTS idx_checkpoints_type ON recovery_checkpoints(checkpoint_type)",
            'idx_checkpoints_created': "CREATE INDEX IF NOT EXISTS idx_checkpoints_created ON recovery_checkpoints(created_at)",
            
            # Organization targets indexes
            'idx_targets_file': "CREATE INDEX IF NOT EXISTS idx_targets_file ON organization_targets(file_id)",
            'idx_targets_path': "CREATE INDEX IF NOT EXISTS idx_targets_path ON organization_targets(target_path)",
            
            # System config indexes
            'idx_config_updated': "CREATE INDEX IF NOT EXISTS idx_config_updated ON system_config(updated_at)"
        }
    
    def _get_triggers(self) -> Dict[str, str]:
        """Define triggers for maintaining data consistency"""
        return {
            # Update files.updated_at when any related data changes
            'trigger_files_updated': """
                CREATE TRIGGER IF NOT EXISTS trigger_files_updated
                AFTER UPDATE ON files
                FOR EACH ROW
                BEGIN
                    UPDATE files SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
                END
            """,
            
            # Update metadata.updated_at when metadata changes
            'trigger_metadata_updated': """
                CREATE TRIGGER IF NOT EXISTS trigger_metadata_updated
                AFTER UPDATE ON metadata
                FOR EACH ROW
                BEGIN
                    UPDATE metadata SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
                END
            """,
            
            # Update system_config.updated_at when config changes
            'trigger_config_updated': """
                CREATE TRIGGER IF NOT EXISTS trigger_config_updated
                AFTER UPDATE ON system_config
                FOR EACH ROW
                BEGIN
                    UPDATE system_config SET updated_at = CURRENT_TIMESTAMP WHERE key = NEW.key;
                END
            """,
            
            # Automatically update operation group statistics
            'trigger_operation_stats': """
                CREATE TRIGGER IF NOT EXISTS trigger_operation_stats
                AFTER UPDATE OF status ON file_operations
                FOR EACH ROW
                WHEN NEW.operation_group IS NOT NULL
                BEGIN
                    UPDATE operation_groups 
                    SET 
                        processed_files = (
                            SELECT COUNT(*) FROM file_operations 
                            WHERE operation_group = NEW.operation_group 
                            AND status IN ('completed', 'failed', 'skipped')
                        ),
                        successful_files = (
                            SELECT COUNT(*) FROM file_operations 
                            WHERE operation_group = NEW.operation_group 
                            AND status = 'completed'
                        ),
                        failed_files = (
                            SELECT COUNT(*) FROM file_operations 
                            WHERE operation_group = NEW.operation_group 
                            AND status = 'failed'
                        ),
                        skipped_files = (
                            SELECT COUNT(*) FROM file_operations 
                            WHERE operation_group = NEW.operation_group 
                            AND status = 'skipped'
                        )
                    WHERE id = NEW.operation_group;
                END
            """
        }
    
    def create_unified_schema(self, connection) -> None:
        """Create the complete unified schema"""
        logger.info("Creating unified database schema...")
        
        # Enable foreign key constraints
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        
        # Create all tables
        for table_name, table_sql in self.schema_tables.items():
            try:
                connection.execute(table_sql)
                logger.debug(f"Created table: {table_name}")
            except Exception as e:
                logger.error(f"Error creating table {table_name}: {e}")
                raise
        
        # Create indexes
        indexes = self._get_indexes()
        for index_name, index_sql in indexes.items():
            try:
                connection.execute(index_sql)
                logger.debug(f"Created index: {index_name}")
            except Exception as e:
                logger.error(f"Error creating index {index_name}: {e}")
                raise
        
        # Create triggers
        triggers = self._get_triggers()
        for trigger_name, trigger_sql in triggers.items():
            try:
                connection.execute(trigger_sql)
                logger.debug(f"Created trigger: {trigger_name}")
            except Exception as e:
                logger.error(f"Error creating trigger {trigger_name}: {e}")
                raise
        
        # Initialize schema version
        connection.execute(
            """INSERT OR REPLACE INTO schema_version (version, description) 
               VALUES (?, ?)""",
            (self.schema_version, "Initial unified schema")
        )
        
        # Initialize system configuration
        self._initialize_system_config(connection)
        
        connection.commit()
        logger.info("Unified database schema created successfully")
    
    def _initialize_system_config(self, connection) -> None:
        """Initialize default system configuration"""
        default_config = [
            ('schema_version', str(self.schema_version), 'integer', 'Current schema version'),
            ('db_creation_time', datetime.now().isoformat(), 'string', 'Database creation timestamp'),
            ('migration_source', 'unified_schema', 'string', 'Source of this database'),
            ('enable_foreign_keys', 'true', 'boolean', 'Enable foreign key constraints'),
            ('enable_wal_mode', 'true', 'boolean', 'Enable WAL journal mode'),
            ('auto_vacuum', 'incremental', 'string', 'Auto vacuum mode'),
            ('cache_size', '2000', 'integer', 'Page cache size'),
            ('temp_store', 'memory', 'string', 'Temporary storage location')
        ]
        
        for key, value, value_type, description in default_config:
            connection.execute(
                """INSERT OR IGNORE INTO system_config 
                   (key, value, value_type, description) VALUES (?, ?, ?, ?)""",
                (key, value, value_type, description)
            )
    
    def get_table_relationships(self) -> Dict[str, List[Dict[str, str]]]:
        """Get foreign key relationships for documentation/validation"""
        return {
            'files': [
                {'references': 'fingerprints', 'on': 'fingerprint_id'},
                {'references': 'metadata', 'on': 'metadata_id'}
            ],
            'quality_analysis': [
                {'references': 'files', 'on': 'file_id'}
            ],
            'duplicate_members': [
                {'references': 'duplicate_groups', 'on': 'group_id'},
                {'references': 'files', 'on': 'file_id'}
            ],
            'file_operations': [
                {'references': 'files', 'on': 'file_id'},
                {'references': 'file_operations', 'on': 'parent_operation_id'}
            ],
            'progress_tracking': [
                {'references': 'operation_groups', 'on': 'operation_group_id'},
                {'references': 'files', 'on': 'file_id'}
            ],
            'recovery_checkpoints': [
                {'references': 'operation_groups', 'on': 'operation_group_id'}
            ],
            'organization_targets': [
                {'references': 'files', 'on': 'file_id'}
            ]
        }
    
    def validate_schema(self, connection) -> bool:
        """Validate that the schema is correctly created"""
        try:
            # Check that all tables exist
            cursor = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            existing_tables = {row[0] for row in cursor.fetchall()}
            expected_tables = set(self.schema_tables.keys())
            
            missing_tables = expected_tables - existing_tables
            if missing_tables:
                logger.error(f"Missing tables: {missing_tables}")
                return False
            
            # Check foreign key constraints are enabled
            cursor = connection.execute("PRAGMA foreign_keys")
            fk_enabled = cursor.fetchone()[0]
            if not fk_enabled:
                logger.error("Foreign key constraints are not enabled")
                return False
            
            # Check schema version
            cursor = connection.execute(
                "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
            )
            current_version = cursor.fetchone()
            if not current_version or current_version[0] != self.schema_version:
                logger.error(f"Schema version mismatch: expected {self.schema_version}")
                return False
            
            logger.info("Schema validation successful")
            return True
            
        except Exception as e:
            logger.error(f"Schema validation failed: {e}")
            return False


def initialize_unified_schema(connection):
    """Initialize function for DatabaseManager compatibility"""
    schema_manager = UnifiedSchemaManager()
    schema_manager.create_unified_schema(connection)


# Utility functions for common queries
class UnifiedSchemaQueries:
    """Common SQL queries for the unified schema"""
    
    @staticmethod
    def insert_file(path: str, file_hash: str = None, file_size: int = None, 
                   modified_time: float = None) -> str:
        return """
            INSERT INTO files (path, file_hash, file_size, modified_time)
            VALUES (?, ?, ?, ?)
        """
    
    @staticmethod
    def insert_fingerprint(fingerprint: str, duration: float = None, 
                          sample_rate: int = None, bitrate: int = None) -> str:
        return """
            INSERT INTO fingerprints (fingerprint, duration, sample_rate, bitrate)
            VALUES (?, ?, ?, ?)
        """
    
    @staticmethod
    def insert_metadata(artist: str = None, title: str = None, album: str = None,
                        year: int = None, genre: str = None) -> str:
        return """
            INSERT INTO metadata (artist, title, album, year, genre)
            VALUES (?, ?, ?, ?, ?)
        """
    
    @staticmethod
    def link_file_fingerprint(file_id: int, fingerprint_id: int) -> str:
        return """
            UPDATE files SET fingerprint_id = ? WHERE id = ?
        """
    
    @staticmethod
    def link_file_metadata(file_id: int, metadata_id: int) -> str:
        return """
            UPDATE files SET metadata_id = ? WHERE id = ?
        """
    
    @staticmethod
    def get_file_with_relations(file_id: int) -> str:
        return """
            SELECT 
                f.*,
                fp.fingerprint, fp.duration, fp.sample_rate, fp.bitrate,
                m.artist, m.title, m.album, m.year, m.genre,
                qa.overall_score, qa.quality_issues
            FROM files f
            LEFT JOIN fingerprints fp ON f.fingerprint_id = fp.id
            LEFT JOIN metadata m ON f.metadata_id = m.id
            LEFT JOIN quality_analysis qa ON f.id = qa.file_id
            WHERE f.id = ?
        """
    
    @staticmethod
    def find_duplicates_by_fingerprint() -> str:
        return """
            SELECT 
                fp.fingerprint,
                GROUP_CONCAT(f.id) as file_ids,
                GROUP_CONCAT(f.path) as file_paths,
                COUNT(*) as duplicate_count
            FROM files f
            JOIN fingerprints fp ON f.fingerprint_id = fp.id
            GROUP BY fp.fingerprint
            HAVING COUNT(*) > 1
        """
    
    @staticmethod
    def get_operation_group_progress(group_id: str) -> str:
        return """
            SELECT 
                og.*,
                COUNT(fo.id) as total_operations,
                COUNT(CASE WHEN fo.status = 'completed' THEN 1 END) as completed_operations,
                COUNT(CASE WHEN fo.status = 'failed' THEN 1 END) as failed_operations
            FROM operation_groups og
            LEFT JOIN file_operations fo ON og.id = fo.operation_group
            WHERE og.id = ?
            GROUP BY og.id
        """