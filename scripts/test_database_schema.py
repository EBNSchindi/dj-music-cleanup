#!/usr/bin/env python3
"""
Database Schema Testing Script

Tests the unified database schema, foreign key relationships,
and data integrity constraints.
"""

import sys
import sqlite3
import tempfile
import shutil
import logging
from pathlib import Path
from typing import Dict, List, Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from music_cleanup.core.unified_schema import UnifiedSchemaManager, UnifiedSchemaQueries
from music_cleanup.core.database import DatabaseManager


def setup_logging():
    """Setup logging for tests"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )


class DatabaseSchemaTest:
    """Test suite for database schema"""
    
    def __init__(self):
        self.test_db_path = None
        self.temp_dir = None
        self.schema_manager = UnifiedSchemaManager()
        self.queries = UnifiedSchemaQueries()
        self.test_results = []
    
    def setup_test_database(self):
        """Create a temporary test database"""
        self.temp_dir = tempfile.mkdtemp()
        self.test_db_path = Path(self.temp_dir) / "test_music_cleanup.db"
        
        # Create database with unified schema
        conn = sqlite3.connect(str(self.test_db_path))
        try:
            self.schema_manager.create_unified_schema(conn)
            logging.info(f"Test database created: {self.test_db_path}")
        except Exception as e:
            logging.error(f"Failed to create test database: {e}")
            raise
        finally:
            conn.close()
    
    def cleanup_test_database(self):
        """Clean up test database"""
        if self.temp_dir:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def run_test(self, test_name: str, test_func):
        """Run a single test and record results"""
        try:
            logging.info(f"Running test: {test_name}")
            result = test_func()
            if result:
                logging.info(f"✅ {test_name} PASSED")
                self.test_results.append((test_name, "PASSED", None))
            else:
                logging.error(f"❌ {test_name} FAILED")
                self.test_results.append((test_name, "FAILED", "Test returned False"))
        except Exception as e:
            logging.error(f"❌ {test_name} ERROR: {e}")
            self.test_results.append((test_name, "ERROR", str(e)))
    
    def test_schema_creation(self) -> bool:
        """Test that all tables are created correctly"""
        conn = sqlite3.connect(str(self.test_db_path))
        try:
            # Check that all expected tables exist
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            actual_tables = {row[0] for row in cursor.fetchall()}
            
            expected_tables = set(self.schema_manager.schema_tables.keys())
            
            missing_tables = expected_tables - actual_tables
            extra_tables = actual_tables - expected_tables
            
            if missing_tables:
                logging.error(f"Missing tables: {missing_tables}")
                return False
            
            if extra_tables:
                logging.warning(f"Extra tables: {extra_tables}")
            
            logging.info(f"All {len(expected_tables)} expected tables found")
            return True
            
        finally:
            conn.close()
    
    def test_foreign_key_constraints(self) -> bool:
        """Test that foreign key constraints are properly defined"""
        conn = sqlite3.connect(str(self.test_db_path))
        try:
            # Check foreign keys are enabled
            cursor = conn.execute("PRAGMA foreign_keys")
            fk_enabled = cursor.fetchone()[0]
            if not fk_enabled:
                logging.error("Foreign keys are not enabled")
                return False
            
            # Check each table's foreign key definitions
            relationships = self.schema_manager.get_table_relationships()
            
            for table, expected_fks in relationships.items():
                cursor = conn.execute(f"PRAGMA foreign_key_list({table})")
                actual_fks = cursor.fetchall()
                
                if len(actual_fks) != len(expected_fks):
                    logging.error(f"Table {table}: expected {len(expected_fks)} FKs, found {len(actual_fks)}")
                    return False
            
            logging.info("All foreign key constraints properly defined")
            return True
            
        finally:
            conn.close()
    
    def test_insert_and_relationships(self) -> bool:
        """Test inserting data and validating relationships"""
        conn = sqlite3.connect(str(self.test_db_path))
        try:
            # Insert test fingerprint
            cursor = conn.execute("""
                INSERT INTO fingerprints (fingerprint, duration, sample_rate, bitrate)
                VALUES (?, ?, ?, ?)
            """, ("test_fingerprint_123", 180.5, 44100, 320))
            fingerprint_id = cursor.lastrowid
            
            # Insert test metadata
            cursor = conn.execute("""
                INSERT INTO metadata (artist, title, album, year, genre)
                VALUES (?, ?, ?, ?, ?)
            """, ("Test Artist", "Test Song", "Test Album", 2023, "Electronic"))
            metadata_id = cursor.lastrowid
            
            # Insert test file with relationships
            cursor = conn.execute("""
                INSERT INTO files (path, file_hash, file_size, fingerprint_id, metadata_id, quality_score)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("/test/music/song.mp3", "abc123hash", 5000000, fingerprint_id, metadata_id, 0.85))
            file_id = cursor.lastrowid
            
            # Insert quality analysis
            cursor = conn.execute("""
                INSERT INTO quality_analysis (file_id, overall_score, dynamic_range, quality_issues)
                VALUES (?, ?, ?, ?)
            """, (file_id, 0.85, 12.5, '["low_bitrate"]'))
            
            # Create duplicate group and members
            cursor = conn.execute("""
                INSERT INTO duplicate_groups (group_hash, detection_method)
                VALUES (?, ?)
            """, ("group_hash_123", "fingerprint"))
            group_id = cursor.lastrowid
            
            cursor = conn.execute("""
                INSERT INTO duplicate_members (group_id, file_id, is_primary, similarity_score)
                VALUES (?, ?, ?, ?)
            """, (group_id, file_id, True, 1.0))
            
            # Create file operation
            cursor = conn.execute("""
                INSERT INTO file_operations (file_id, operation_type, source_path, status)
                VALUES (?, ?, ?, ?)
            """, (file_id, "copy", "/test/music/song.mp3", "completed"))
            
            conn.commit()
            
            # Test join query
            cursor = conn.execute(self.queries.get_file_with_relations(file_id))
            result = cursor.fetchone()
            
            if not result:
                logging.error("Failed to retrieve file with relationships")
                return False
            
            # Verify data integrity
            if result['path'] != "/test/music/song.mp3":
                logging.error("File path mismatch")
                return False
            
            if result['artist'] != "Test Artist":
                logging.error("Artist metadata mismatch")
                return False
            
            if result['fingerprint'] != "test_fingerprint_123":
                logging.error("Fingerprint mismatch")
                return False
            
            logging.info("Data insertion and relationships work correctly")
            return True
            
        finally:
            conn.close()
    
    def test_foreign_key_violations(self) -> bool:
        """Test that foreign key violations are properly caught"""
        conn = sqlite3.connect(str(self.test_db_path))
        try:
            # Try to insert file with invalid fingerprint_id
            try:
                cursor = conn.execute("""
                    INSERT INTO files (path, fingerprint_id) VALUES (?, ?)
                """, ("/test/invalid.mp3", 99999))
                conn.commit()
                logging.error("Foreign key violation was not caught")
                return False
            except sqlite3.IntegrityError:
                logging.info("Foreign key violation properly caught")
                conn.rollback()
            
            # Try to insert duplicate member with invalid file_id
            try:
                cursor = conn.execute("""
                    INSERT INTO duplicate_members (group_id, file_id) VALUES (?, ?)
                """, (1, 99999))
                conn.commit()
                logging.error("Foreign key violation was not caught")
                return False
            except sqlite3.IntegrityError:
                logging.info("Foreign key violation properly caught")
                conn.rollback()
            
            return True
            
        finally:
            conn.close()
    
    def test_cascade_deletes(self) -> bool:
        """Test that cascade deletes work properly"""
        conn = sqlite3.connect(str(self.test_db_path))
        try:
            # Insert test data
            cursor = conn.execute("""
                INSERT INTO files (path, file_hash) VALUES (?, ?)
            """, ("/test/cascade.mp3", "cascade_hash"))
            file_id = cursor.lastrowid
            
            cursor = conn.execute("""
                INSERT INTO quality_analysis (file_id, overall_score) VALUES (?, ?)
            """, (file_id, 0.5))
            quality_id = cursor.lastrowid
            
            conn.commit()
            
            # Verify quality analysis exists
            cursor = conn.execute("SELECT COUNT(*) FROM quality_analysis WHERE id = ?", (quality_id,))
            count_before = cursor.fetchone()[0]
            
            if count_before != 1:
                logging.error("Quality analysis not found before delete")
                return False
            
            # Delete file (should cascade to quality_analysis)
            cursor = conn.execute("DELETE FROM files WHERE id = ?", (file_id,))
            conn.commit()
            
            # Verify quality analysis was deleted
            cursor = conn.execute("SELECT COUNT(*) FROM quality_analysis WHERE id = ?", (quality_id,))
            count_after = cursor.fetchone()[0]
            
            if count_after != 0:
                logging.error("Cascade delete did not work")
                return False
            
            logging.info("Cascade deletes work correctly")
            return True
            
        finally:
            conn.close()
    
    def test_indexes_and_performance(self) -> bool:
        """Test that indexes exist and basic performance"""
        conn = sqlite3.connect(str(self.test_db_path))
        try:
            # Check that indexes exist
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
            )
            indexes = [row[0] for row in cursor.fetchall()]
            
            expected_indexes = [name for name in self.schema_manager._get_indexes().keys()]
            
            missing_indexes = set(expected_indexes) - set(indexes)
            if missing_indexes:
                logging.error(f"Missing indexes: {missing_indexes}")
                return False
            
            # Test query plan uses indexes
            cursor = conn.execute("EXPLAIN QUERY PLAN SELECT * FROM files WHERE path = ?", ("/test/path",))
            plan = cursor.fetchall()
            
            # Should use index on path
            uses_index = any("idx_files_path" in str(step) for step in plan)
            if not uses_index:
                logging.warning("Query plan may not be using path index")
            
            logging.info(f"All {len(expected_indexes)} indexes found")
            return True
            
        finally:
            conn.close()
    
    def test_triggers(self) -> bool:
        """Test that triggers work correctly"""
        conn = sqlite3.connect(str(self.test_db_path))
        try:
            # Insert test data
            cursor = conn.execute("""
                INSERT INTO files (path) VALUES (?)
            """, ("/test/trigger.mp3",))
            file_id = cursor.lastrowid
            original_updated_at = conn.execute(
                "SELECT updated_at FROM files WHERE id = ?", (file_id,)
            ).fetchone()[0]
            
            # Wait a moment and update
            import time
            time.sleep(0.1)
            
            cursor = conn.execute("""
                UPDATE files SET file_size = ? WHERE id = ?
            """, (1000000, file_id))
            conn.commit()
            
            # Check that updated_at was changed
            new_updated_at = conn.execute(
                "SELECT updated_at FROM files WHERE id = ?", (file_id,)
            ).fetchone()[0]
            
            if new_updated_at == original_updated_at:
                logging.error("Update trigger did not fire")
                return False
            
            logging.info("Triggers work correctly")
            return True
            
        finally:
            conn.close()
    
    def test_database_manager_integration(self) -> bool:
        """Test integration with DatabaseManager"""
        try:
            # Create database manager
            db_manager = DatabaseManager()
            db_manager.set_base_path(self.temp_dir)
            
            # Initialize unified database
            db_name = db_manager.initialize_unified_database()
            
            if db_name != 'unified':
                logging.error(f"Expected 'unified', got '{db_name}'")
                return False
            
            # Test basic operations
            with db_manager.get_connection('unified') as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM files")
                count = cursor.fetchone()[0]
                logging.info(f"Files table accessible, count: {count}")
            
            # Test transaction
            with db_manager.transaction('unified') as conn:
                conn.execute("INSERT INTO files (path) VALUES (?)", ("/test/transaction.mp3",))
            
            # Verify transaction committed
            rows = db_manager.execute_query('unified', "SELECT COUNT(*) FROM files WHERE path = ?", 
                                          ("/test/transaction.mp3",))
            if len(rows) == 0 or rows[0][0] != 1:
                logging.error("Transaction test failed")
                return False
            
            logging.info("DatabaseManager integration works correctly")
            return True
            
        except Exception as e:
            logging.error(f"DatabaseManager integration failed: {e}")
            return False
    
    def run_all_tests(self):
        """Run all tests"""
        logging.info("🎵 Starting Database Schema Tests")
        logging.info("=" * 50)
        
        try:
            self.setup_test_database()
            
            # Run all tests
            tests = [
                ("Schema Creation", self.test_schema_creation),
                ("Foreign Key Constraints", self.test_foreign_key_constraints),
                ("Insert and Relationships", self.test_insert_and_relationships),
                ("Foreign Key Violations", self.test_foreign_key_violations),
                ("Cascade Deletes", self.test_cascade_deletes),
                ("Indexes and Performance", self.test_indexes_and_performance),
                ("Triggers", self.test_triggers),
                ("DatabaseManager Integration", self.test_database_manager_integration)
            ]
            
            for test_name, test_func in tests:
                self.run_test(test_name, test_func)
            
            # Print results
            self.print_test_summary()
            
        finally:
            self.cleanup_test_database()
    
    def print_test_summary(self):
        """Print test summary"""
        logging.info("=" * 50)
        logging.info("🧪 Test Results Summary")
        logging.info("=" * 50)
        
        passed = sum(1 for _, status, _ in self.test_results if status == "PASSED")
        failed = sum(1 for _, status, _ in self.test_results if status == "FAILED")
        errors = sum(1 for _, status, _ in self.test_results if status == "ERROR")
        total = len(self.test_results)
        
        for test_name, status, error in self.test_results:
            if status == "PASSED":
                logging.info(f"✅ {test_name}")
            elif status == "FAILED":
                logging.error(f"❌ {test_name}")
            else:
                logging.error(f"💥 {test_name}: {error}")
        
        logging.info("=" * 50)
        logging.info(f"Total: {total}, Passed: {passed}, Failed: {failed}, Errors: {errors}")
        
        if passed == total:
            logging.info("🎉 All tests passed! Database schema is working correctly.")
            return True
        else:
            logging.error(f"⚠️  {failed + errors} test(s) failed. Review the schema implementation.")
            return False


def main():
    """Main entry point"""
    setup_logging()
    
    tester = DatabaseSchemaTest()
    success = tester.run_all_tests()
    
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())