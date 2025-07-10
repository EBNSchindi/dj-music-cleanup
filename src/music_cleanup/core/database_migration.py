"""
Database Migration System for DJ Music Cleanup Tool

Handles migration from separate databases (fingerprints.db, operations.db, progress.db)
to the unified music_cleanup.db schema with proper data integrity and relationships.
"""

import logging
import sqlite3
import shutil
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
import hashlib

from .unified_schema import UnifiedSchemaManager, initialize_unified_schema

logger = logging.getLogger(__name__)


class DatabaseMigration:
    """Handles migration from legacy databases to unified schema"""
    
    def __init__(self, source_db_dir: Path, target_db_path: Path, backup_dir: Optional[Path] = None):
        self.source_db_dir = Path(source_db_dir)
        self.target_db_path = Path(target_db_path)
        self.backup_dir = Path(backup_dir) if backup_dir else self.source_db_dir / "backups"
        
        # Legacy database files
        self.legacy_dbs = {
            'fingerprints': self.source_db_dir / 'fingerprints.db',
            'operations': self.source_db_dir / 'file_operations.db',
            'progress': self.source_db_dir / 'progress.db'
        }
        
        self.migration_log = []
        self.unified_schema = UnifiedSchemaManager()
    
    def migrate(self, dry_run: bool = False) -> bool:
        """
        Perform complete migration from legacy databases to unified schema.
        
        Args:
            dry_run: If True, perform validation and planning without actual migration
            
        Returns:
            True if migration successful, False otherwise
        """
        logger.info(f"Starting database migration (dry_run={dry_run})")
        
        try:
            # Step 1: Validate source databases
            if not self._validate_source_databases():
                return False
            
            # Step 2: Create backups
            if not dry_run:
                self._create_backups()
            
            # Step 3: Create target database with unified schema
            if not dry_run:
                self._create_target_database()
            
            # Step 4: Migrate data
            migration_plan = self._create_migration_plan()
            
            if dry_run:
                self._log_migration_plan(migration_plan)
                return True
            
            success = self._execute_migration(migration_plan)
            
            if success:
                # Step 5: Validate migrated data
                if self._validate_migrated_data():
                    logger.info("Database migration completed successfully")
                    self._log_migration_summary()
                    return True
                else:
                    logger.error("Migration validation failed")
                    return False
            else:
                logger.error("Migration execution failed")
                return False
                
        except Exception as e:
            logger.error(f"Migration failed with error: {e}")
            return False
    
    def _validate_source_databases(self) -> bool:
        """Validate that source databases exist and are accessible"""
        logger.info("Validating source databases...")
        
        missing_dbs = []
        for db_name, db_path in self.legacy_dbs.items():
            if not db_path.exists():
                missing_dbs.append(f"{db_name}: {db_path}")
                continue
            
            try:
                # Test connection
                conn = sqlite3.connect(str(db_path))
                cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]
                conn.close()
                
                logger.debug(f"Found {len(tables)} tables in {db_name}: {tables}")
                
            except Exception as e:
                logger.error(f"Cannot access {db_name} database: {e}")
                return False
        
        if missing_dbs:
            logger.warning(f"Missing databases (will create empty): {missing_dbs}")
        
        return True
    
    def _create_backups(self) -> None:
        """Create backups of existing databases"""
        logger.info("Creating database backups...")
        
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        for db_name, db_path in self.legacy_dbs.items():
            if db_path.exists():
                backup_path = self.backup_dir / f"{db_name}_{timestamp}.db"
                shutil.copy2(db_path, backup_path)
                logger.info(f"Backed up {db_name} to {backup_path}")
        
        # Also backup target if it exists
        if self.target_db_path.exists():
            backup_path = self.backup_dir / f"music_cleanup_{timestamp}.db"
            shutil.copy2(self.target_db_path, backup_path)
            logger.info(f"Backed up existing target database to {backup_path}")
    
    def _create_target_database(self) -> None:
        """Create target database with unified schema"""
        logger.info("Creating target database with unified schema...")
        
        # Remove existing target database
        if self.target_db_path.exists():
            self.target_db_path.unlink()
        
        # Create new database with unified schema
        conn = sqlite3.connect(str(self.target_db_path))
        try:
            initialize_unified_schema(conn)
            logger.info("Target database created successfully")
        finally:
            conn.close()
    
    def _create_migration_plan(self) -> Dict[str, Any]:
        """Create detailed migration plan"""
        logger.info("Creating migration plan...")
        
        plan = {
            'source_analysis': {},
            'migration_steps': [],
            'estimated_records': 0
        }
        
        # Analyze each source database
        for db_name, db_path in self.legacy_dbs.items():
            if not db_path.exists():
                plan['source_analysis'][db_name] = {'exists': False, 'tables': {}}
                continue
            
            analysis = self._analyze_source_database(db_path)
            plan['source_analysis'][db_name] = analysis
            plan['estimated_records'] += sum(analysis['tables'].values())
        
        # Define migration steps
        plan['migration_steps'] = [
            {'step': 1, 'description': 'Migrate fingerprints data', 'source': 'fingerprints'},
            {'step': 2, 'description': 'Migrate metadata from fingerprints', 'source': 'fingerprints'},
            {'step': 3, 'description': 'Migrate files registry', 'source': 'fingerprints'},
            {'step': 4, 'description': 'Migrate duplicate groups', 'source': 'fingerprints'},
            {'step': 5, 'description': 'Migrate file operations', 'source': 'operations'},
            {'step': 6, 'description': 'Migrate operation groups', 'source': 'operations'},
            {'step': 7, 'description': 'Migrate progress tracking', 'source': 'progress'},
            {'step': 8, 'description': 'Create relationships and indexes', 'source': 'all'},
            {'step': 9, 'description': 'Validate data integrity', 'source': 'all'}
        ]
        
        return plan
    
    def _analyze_source_database(self, db_path: Path) -> Dict[str, Any]:
        """Analyze a source database structure and content"""
        analysis = {'exists': True, 'tables': {}, 'indexes': [], 'size_mb': 0}
        
        try:
            # Get file size
            analysis['size_mb'] = db_path.stat().st_size / (1024 * 1024)
            
            conn = sqlite3.connect(str(db_path))
            
            # Get table information
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            for table in tables:
                try:
                    cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    analysis['tables'][table] = count
                except:
                    analysis['tables'][table] = 0
            
            # Get indexes
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
            analysis['indexes'] = [row[0] for row in cursor.fetchall()]
            
            conn.close()
            
        except Exception as e:
            logger.error(f"Error analyzing {db_path}: {e}")
            analysis['error'] = str(e)
        
        return analysis
    
    def _log_migration_plan(self, plan: Dict[str, Any]) -> None:
        """Log the migration plan for dry run"""
        logger.info("=== MIGRATION PLAN ===")
        
        # Source analysis
        logger.info("Source Database Analysis:")
        for db_name, analysis in plan['source_analysis'].items():
            if analysis['exists']:
                logger.info(f"  {db_name}: {analysis['size_mb']:.1f} MB")
                for table, count in analysis['tables'].items():
                    logger.info(f"    {table}: {count:,} records")
            else:
                logger.info(f"  {db_name}: Not found")
        
        # Migration steps
        logger.info(f"Migration Steps ({len(plan['migration_steps'])} total):")
        for step in plan['migration_steps']:
            logger.info(f"  Step {step['step']}: {step['description']} (from {step['source']})")
        
        logger.info(f"Estimated total records to migrate: {plan['estimated_records']:,}")
        logger.info("=== END MIGRATION PLAN ===")
    
    def _execute_migration(self, plan: Dict[str, Any]) -> bool:
        """Execute the migration plan"""
        logger.info("Executing migration plan...")
        
        target_conn = sqlite3.connect(str(self.target_db_path))
        target_conn.execute("PRAGMA foreign_keys = OFF")  # Disable during migration
        
        try:
            success = True
            
            # Execute each migration step
            for step in plan['migration_steps']:
                step_num = step['step']
                description = step['description']
                source = step['source']
                
                logger.info(f"Executing step {step_num}: {description}")
                
                if not self._execute_migration_step(step_num, source, target_conn):
                    logger.error(f"Migration step {step_num} failed")
                    success = False
                    break
            
            if success:
                # Re-enable foreign keys and validate
                target_conn.execute("PRAGMA foreign_keys = ON")
                target_conn.commit()
                
                # Rebuild statistics
                target_conn.execute("ANALYZE")
                target_conn.commit()
                
            return success
            
        except Exception as e:
            logger.error(f"Migration execution failed: {e}")
            return False
        finally:
            target_conn.close()
    
    def _execute_migration_step(self, step_num: int, source: str, target_conn: sqlite3.Connection) -> bool:
        """Execute a specific migration step"""
        try:
            if step_num == 1:
                return self._migrate_fingerprints(target_conn)
            elif step_num == 2:
                return self._migrate_metadata(target_conn)
            elif step_num == 3:
                return self._migrate_files(target_conn)
            elif step_num == 4:
                return self._migrate_duplicates(target_conn)
            elif step_num == 5:
                return self._migrate_file_operations(target_conn)
            elif step_num == 6:
                return self._migrate_operation_groups(target_conn)
            elif step_num == 7:
                return self._migrate_progress_tracking(target_conn)
            elif step_num == 8:
                return self._create_relationships(target_conn)
            elif step_num == 9:
                return self._validate_relationships(target_conn)
            else:
                logger.error(f"Unknown migration step: {step_num}")
                return False
                
        except Exception as e:
            logger.error(f"Error in migration step {step_num}: {e}")
            return False
    
    def _migrate_fingerprints(self, target_conn: sqlite3.Connection) -> bool:
        """Migrate fingerprints data"""
        fingerprints_db = self.legacy_dbs['fingerprints']
        if not fingerprints_db.exists():
            logger.info("No fingerprints database found, skipping")
            return True
        
        source_conn = sqlite3.connect(str(fingerprints_db))
        try:
            # Check if fingerprints table exists
            cursor = source_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='fingerprints'"
            )
            if not cursor.fetchone():
                logger.info("No fingerprints table found, skipping")
                return True
            
            # Migrate fingerprints
            cursor = source_conn.execute("""
                SELECT fingerprint, duration, sample_rate, bit_depth, channels, 
                       codec, bitrate, created_at
                FROM fingerprints
            """)
            
            fingerprints = cursor.fetchall()
            logger.info(f"Migrating {len(fingerprints)} fingerprints...")
            
            for fp in fingerprints:
                target_conn.execute("""
                    INSERT INTO fingerprints 
                    (fingerprint, duration, sample_rate, bit_depth, channels, codec, bitrate, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, fp)
            
            target_conn.commit()
            self.migration_log.append(f"Migrated {len(fingerprints)} fingerprints")
            return True
            
        except Exception as e:
            logger.error(f"Error migrating fingerprints: {e}")
            return False
        finally:
            source_conn.close()
    
    def _migrate_metadata(self, target_conn: sqlite3.Connection) -> bool:
        """Extract and migrate metadata from fingerprints"""
        fingerprints_db = self.legacy_dbs['fingerprints']
        if not fingerprints_db.exists():
            return True
        
        source_conn = sqlite3.connect(str(fingerprints_db))
        try:
            # Check if fingerprints table has metadata columns
            cursor = source_conn.execute("PRAGMA table_info(fingerprints)")
            columns = [row[1] for row in cursor.fetchall()]
            
            metadata_columns = ['artist', 'album', 'title', 'year', 'genre']
            available_metadata = [col for col in metadata_columns if col in columns]
            
            if not available_metadata:
                logger.info("No metadata columns found in fingerprints table")
                return True
            
            # Extract unique metadata combinations
            select_clause = ', '.join(available_metadata)
            cursor = source_conn.execute(f"""
                SELECT DISTINCT {select_clause}
                FROM fingerprints
                WHERE {' OR '.join(f'{col} IS NOT NULL' for col in available_metadata)}
            """)
            
            metadata_records = cursor.fetchall()
            logger.info(f"Migrating {len(metadata_records)} unique metadata records...")
            
            # Create placeholder values for missing columns
            for record in metadata_records:
                # Pad record to match all metadata columns
                padded_record = []
                record_index = 0
                
                for col in metadata_columns:
                    if col in available_metadata:
                        padded_record.append(record[record_index])
                        record_index += 1
                    else:
                        padded_record.append(None)
                
                target_conn.execute("""
                    INSERT INTO metadata (artist, album, title, year, genre)
                    VALUES (?, ?, ?, ?, ?)
                """, padded_record)
            
            target_conn.commit()
            self.migration_log.append(f"Migrated {len(metadata_records)} metadata records")
            return True
            
        except Exception as e:
            logger.error(f"Error migrating metadata: {e}")
            return False
        finally:
            source_conn.close()
    
    def _migrate_files(self, target_conn: sqlite3.Connection) -> bool:
        """Migrate files registry from fingerprints database"""
        fingerprints_db = self.legacy_dbs['fingerprints']
        if not fingerprints_db.exists():
            return True
        
        source_conn = sqlite3.connect(str(fingerprints_db))
        try:
            cursor = source_conn.execute("""
                SELECT file_path, file_hash, file_size, modified_time, quality_score
                FROM fingerprints
            """)
            
            files = cursor.fetchall()
            logger.info(f"Migrating {len(files)} files...")
            
            for file_record in files:
                file_path, file_hash, file_size, modified_time, quality_score = file_record
                
                # Find fingerprint_id
                fp_cursor = target_conn.execute(
                    "SELECT id FROM fingerprints WHERE fingerprint = (SELECT fingerprint FROM fingerprints WHERE file_path = ?)",
                    (file_path,)
                )
                fp_result = fp_cursor.fetchone()
                fingerprint_id = fp_result[0] if fp_result else None
                
                # Find metadata_id by looking up original metadata
                metadata_id = None
                try:
                    # Try to find matching metadata from original fingerprints
                    source_cursor = source_conn.execute("""
                        SELECT artist, title, album, year, genre 
                        FROM fingerprints WHERE file_path = ?
                    """, (file_path,))
                    metadata_result = source_cursor.fetchone()
                    
                    if metadata_result and any(metadata_result):
                        # Find matching metadata in target
                        md_cursor = target_conn.execute("""
                            SELECT id FROM metadata 
                            WHERE artist = ? AND title = ? AND album = ? AND year = ? AND genre = ?
                        """, metadata_result)
                        md_result = md_cursor.fetchone()
                        metadata_id = md_result[0] if md_result else None
                except:
                    pass  # No metadata columns in source
                
                target_conn.execute("""
                    INSERT INTO files 
                    (path, file_hash, file_size, modified_time, fingerprint_id, metadata_id, quality_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (file_path, file_hash, file_size, modified_time, fingerprint_id, metadata_id, quality_score))
            
            target_conn.commit()
            self.migration_log.append(f"Migrated {len(files)} files")
            return True
            
        except Exception as e:
            logger.error(f"Error migrating files: {e}")
            return False
        finally:
            source_conn.close()
    
    def _migrate_duplicates(self, target_conn: sqlite3.Connection) -> bool:
        """Migrate duplicate groups and members"""
        fingerprints_db = self.legacy_dbs['fingerprints']
        if not fingerprints_db.exists():
            return True
        
        source_conn = sqlite3.connect(str(fingerprints_db))
        try:
            # Check if duplicates table exists
            cursor = source_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='duplicates'"
            )
            if not cursor.fetchone():
                logger.info("No duplicates table found, skipping")
                return True
            
            # Migrate duplicate groups
            cursor = source_conn.execute("SELECT DISTINCT group_id FROM duplicates")
            group_ids = [row[0] for row in cursor.fetchall()]
            
            logger.info(f"Migrating {len(group_ids)} duplicate groups...")
            
            for group_id in group_ids:
                # Create group hash from group_id
                group_hash = hashlib.md5(group_id.encode()).hexdigest()
                
                target_conn.execute("""
                    INSERT INTO duplicate_groups (group_hash, detection_method)
                    VALUES (?, ?)
                """, (group_hash, 'metadata'))  # Assume metadata-based for legacy
                
                group_db_id = target_conn.lastrowid
                
                # Migrate group members
                cursor = source_conn.execute("""
                    SELECT file_path, is_primary, similarity_score
                    FROM duplicates WHERE group_id = ?
                """, (group_id,))
                
                members = cursor.fetchall()
                for file_path, is_primary, similarity_score in members:
                    # Find file_id
                    file_cursor = target_conn.execute(
                        "SELECT id FROM files WHERE path = ?", (file_path,)
                    )
                    file_result = file_cursor.fetchone()
                    
                    if file_result:
                        file_id = file_result[0]
                        target_conn.execute("""
                            INSERT INTO duplicate_members 
                            (group_id, file_id, is_primary, similarity_score)
                            VALUES (?, ?, ?, ?)
                        """, (group_db_id, file_id, is_primary, similarity_score))
            
            target_conn.commit()
            self.migration_log.append(f"Migrated {len(group_ids)} duplicate groups")
            return True
            
        except Exception as e:
            logger.error(f"Error migrating duplicates: {e}")
            return False
        finally:
            source_conn.close()
    
    def _migrate_file_operations(self, target_conn: sqlite3.Connection) -> bool:
        """Migrate file operations"""
        operations_db = self.legacy_dbs['operations']
        if not operations_db.exists():
            logger.info("No operations database found, skipping")
            return True
        
        source_conn = sqlite3.connect(str(operations_db))
        try:
            cursor = source_conn.execute("""
                SELECT operation_type, source_path, destination_path, status, 
                       error_message, file_size, operation_group, created_at, completed_at
                FROM file_operations
            """)
            
            operations = cursor.fetchall()
            logger.info(f"Migrating {len(operations)} file operations...")
            
            for op in operations:
                operation_type, source_path, dest_path, status, error_msg, file_size, op_group, created_at, completed_at = op
                
                # Find file_id
                file_cursor = target_conn.execute(
                    "SELECT id FROM files WHERE path = ?", (source_path,)
                )
                file_result = file_cursor.fetchone()
                file_id = file_result[0] if file_result else None
                
                target_conn.execute("""
                    INSERT INTO file_operations 
                    (file_id, operation_type, source_path, destination_path, status, 
                     error_message, operation_group, created_at, completed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (file_id, operation_type, source_path, dest_path, status, 
                      error_msg, op_group, created_at, completed_at))
            
            target_conn.commit()
            self.migration_log.append(f"Migrated {len(operations)} file operations")
            return True
            
        except Exception as e:
            logger.error(f"Error migrating file operations: {e}")
            return False
        finally:
            source_conn.close()
    
    def _migrate_operation_groups(self, target_conn: sqlite3.Connection) -> bool:
        """Migrate operation groups from operation stats"""
        operations_db = self.legacy_dbs['operations']
        if not operations_db.exists():
            return True
        
        source_conn = sqlite3.connect(str(operations_db))
        try:
            # Check if operation_stats table exists
            cursor = source_conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='operation_stats'"
            )
            if not cursor.fetchone():
                logger.info("No operation_stats table found, skipping")
                return True
            
            cursor = source_conn.execute("""
                SELECT operation_group, total_files, processed_files, failed_files,
                       total_size_bytes, start_time, end_time
                FROM operation_stats
            """)
            
            groups = cursor.fetchall()
            logger.info(f"Migrating {len(groups)} operation groups...")
            
            for group in groups:
                op_group, total_files, processed_files, failed_files, total_size, start_time, end_time = group
                
                status = 'completed' if end_time else 'active'
                successful_files = processed_files - failed_files if processed_files and failed_files else 0
                
                target_conn.execute("""
                    INSERT INTO operation_groups 
                    (id, operation_type, total_files, processed_files, successful_files, 
                     failed_files, total_size_bytes, status, start_time, end_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (op_group, 'unknown', total_files, processed_files, successful_files,
                      failed_files, total_size, status, start_time, end_time))
            
            target_conn.commit()
            self.migration_log.append(f"Migrated {len(groups)} operation groups")
            return True
            
        except Exception as e:
            logger.error(f"Error migrating operation groups: {e}")
            return False
        finally:
            source_conn.close()
    
    def _migrate_progress_tracking(self, target_conn: sqlite3.Connection) -> bool:
        """Migrate progress tracking data"""
        progress_db = self.legacy_dbs['progress']
        if not progress_db.exists():
            logger.info("No progress database found, skipping")
            return True
        
        source_conn = sqlite3.connect(str(progress_db))
        try:
            # Migrate processed files as progress tracking
            cursor = source_conn.execute("""
                SELECT file_path, phase, status, processed_at
                FROM processed_files
            """)
            
            processed = cursor.fetchall()
            logger.info(f"Migrating {len(processed)} progress records...")
            
            for record in processed:
                file_path, phase, status, processed_at = record
                
                # Find file_id
                file_cursor = target_conn.execute(
                    "SELECT id FROM files WHERE path = ?", (file_path,)
                )
                file_result = file_cursor.fetchone()
                file_id = file_result[0] if file_result else None
                
                if file_id:
                    progress = 1.0 if status == 'completed' else 0.0
                    
                    target_conn.execute("""
                        INSERT INTO progress_tracking 
                        (operation_group_id, file_id, current_phase, phase_progress, last_checkpoint)
                        VALUES (?, ?, ?, ?, ?)
                    """, ('legacy_migration', file_id, phase, progress, processed_at))
            
            target_conn.commit()
            self.migration_log.append(f"Migrated {len(processed)} progress records")
            return True
            
        except Exception as e:
            logger.error(f"Error migrating progress tracking: {e}")
            return False
        finally:
            source_conn.close()
    
    def _create_relationships(self, target_conn: sqlite3.Connection) -> bool:
        """Create and validate foreign key relationships"""
        logger.info("Creating relationships and updating references...")
        
        try:
            # Update any missing file relationships
            cursor = target_conn.execute("""
                UPDATE files 
                SET fingerprint_id = (
                    SELECT fp.id FROM fingerprints fp 
                    WHERE fp.fingerprint = (
                        SELECT f2.fingerprint FROM fingerprints f2 
                        WHERE f2.file_path = files.path LIMIT 1
                    )
                )
                WHERE fingerprint_id IS NULL
            """)
            
            target_conn.commit()
            logger.info("Relationships created successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error creating relationships: {e}")
            return False
    
    def _validate_relationships(self, target_conn: sqlite3.Connection) -> bool:
        """Validate foreign key relationships"""
        logger.info("Validating foreign key relationships...")
        
        try:
            # Check foreign key constraints
            cursor = target_conn.execute("PRAGMA foreign_key_check")
            violations = cursor.fetchall()
            
            if violations:
                logger.error(f"Foreign key violations found: {violations}")
                return False
            
            logger.info("All foreign key relationships are valid")
            return True
            
        except Exception as e:
            logger.error(f"Error validating relationships: {e}")
            return False
    
    def _validate_migrated_data(self) -> bool:
        """Validate the migrated data integrity"""
        logger.info("Validating migrated data...")
        
        conn = sqlite3.connect(str(self.target_db_path))
        try:
            validation_results = {}
            
            # Count records in each table
            tables = ['files', 'fingerprints', 'metadata', 'duplicate_groups', 
                     'duplicate_members', 'file_operations', 'operation_groups']
            
            for table in tables:
                cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                validation_results[table] = count
                logger.info(f"  {table}: {count:,} records")
            
            # Validate relationships
            cursor = conn.execute("""
                SELECT COUNT(*) FROM files 
                WHERE fingerprint_id IS NOT NULL 
                AND fingerprint_id NOT IN (SELECT id FROM fingerprints)
            """)
            orphaned_fingerprints = cursor.fetchone()[0]
            
            cursor = conn.execute("""
                SELECT COUNT(*) FROM files 
                WHERE metadata_id IS NOT NULL 
                AND metadata_id NOT IN (SELECT id FROM metadata)
            """)
            orphaned_metadata = cursor.fetchone()[0]
            
            if orphaned_fingerprints > 0:
                logger.warning(f"Found {orphaned_fingerprints} files with invalid fingerprint references")
            
            if orphaned_metadata > 0:
                logger.warning(f"Found {orphaned_metadata} files with invalid metadata references")
            
            # Check for essential data
            if validation_results['files'] == 0:
                logger.warning("No files migrated - this might be expected for a new installation")
            
            return True
            
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            return False
        finally:
            conn.close()
    
    def _log_migration_summary(self) -> None:
        """Log migration summary"""
        logger.info("=== MIGRATION SUMMARY ===")
        for log_entry in self.migration_log:
            logger.info(f"  ✓ {log_entry}")
        logger.info("=== MIGRATION COMPLETE ===")


def run_migration(source_db_dir: str, target_db_path: str, 
                  backup_dir: str = None, dry_run: bool = False) -> bool:
    """
    Convenience function to run database migration.
    
    Args:
        source_db_dir: Directory containing legacy database files
        target_db_path: Path for the new unified database
        backup_dir: Directory for backups (optional)
        dry_run: If True, only validate and plan migration
    
    Returns:
        True if migration successful, False otherwise
    """
    migration = DatabaseMigration(
        source_db_dir=Path(source_db_dir),
        target_db_path=Path(target_db_path),
        backup_dir=Path(backup_dir) if backup_dir else None
    )
    
    return migration.migrate(dry_run=dry_run)