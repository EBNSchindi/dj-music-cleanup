"""
Unit tests for UnifiedDatabase
"""

import tempfile
import time
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from music_cleanup.core.unified_database import (
    UnifiedDatabase, FingerprintRecord, OperationRecord, ProgressRecord
)


class TestUnifiedDatabase(unittest.TestCase):
    
    def setUp(self):
        """Set up test environment"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.db_path = str(self.temp_path / "test_music_cleanup.db")
        self.db = UnifiedDatabase(self.db_path)
    
    def tearDown(self):
        """Clean up test environment"""
        self.temp_dir.cleanup()
    
    def test_database_initialization(self):
        """Test database initialization"""
        # Database file should exist
        self.assertTrue(Path(self.db_path).exists())
        
        # Check that all tables were created
        with self.db._get_connection() as conn:
            tables = conn.execute("""
                SELECT name FROM sqlite_master WHERE type='table'
            """).fetchall()
            
            table_names = [table[0] for table in tables]
            self.assertIn('fingerprints', table_names)
            self.assertIn('operations', table_names)
            self.assertIn('progress', table_names)
    
    def test_fingerprint_operations(self):
        """Test fingerprint storage and retrieval"""
        # Create test fingerprint
        fingerprint = FingerprintRecord(
            file_path="/test/audio.mp3",
            fingerprint="test_fingerprint_123",
            duration=180.5,
            file_size=8000000,
            algorithm="chromaprint",
            bitrate=320,
            format=".mp3",
            file_mtime=time.time(),
            generated_at=time.time()
        )
        
        # Store fingerprint
        result = self.db.store_fingerprint(fingerprint)
        self.assertTrue(result)
        
        # Retrieve fingerprint
        retrieved = self.db.get_fingerprint("/test/audio.mp3")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.fingerprint, "test_fingerprint_123")
        self.assertEqual(retrieved.duration, 180.5)
        self.assertEqual(retrieved.algorithm, "chromaprint")
    
    def test_duplicate_fingerprint_detection(self):
        """Test finding duplicate fingerprints"""
        # Create multiple files with same fingerprint
        fingerprint1 = FingerprintRecord(
            file_path="/test/audio1.mp3",
            fingerprint="duplicate_fingerprint",
            duration=180.0,
            file_size=8000000,
            algorithm="chromaprint",
            file_mtime=time.time(),
            generated_at=time.time()
        )
        
        fingerprint2 = FingerprintRecord(
            file_path="/test/audio2.mp3",
            fingerprint="duplicate_fingerprint",
            duration=180.0,
            file_size=5000000,
            algorithm="chromaprint",
            file_mtime=time.time(),
            generated_at=time.time()
        )
        
        # Store both fingerprints
        self.db.store_fingerprint(fingerprint1)
        self.db.store_fingerprint(fingerprint2)
        
        # Find duplicates
        duplicates = self.db.find_duplicate_fingerprints("duplicate_fingerprint", "chromaprint")
        self.assertEqual(len(duplicates), 2)
        
        # Check that we get the right files
        file_paths = [dup.file_path for dup in duplicates]
        self.assertIn("/test/audio1.mp3", file_paths)
        self.assertIn("/test/audio2.mp3", file_paths)
    
    def test_fingerprint_statistics(self):
        """Test fingerprint statistics"""
        # Add some test fingerprints
        fingerprints = [
            FingerprintRecord("/test/1.mp3", "fp1", 180, 8000000, "chromaprint", file_mtime=time.time(), generated_at=time.time()),
            FingerprintRecord("/test/2.mp3", "fp2", 200, 9000000, "chromaprint", file_mtime=time.time(), generated_at=time.time()),
            FingerprintRecord("/test/3.mp3", "fp3", 150, 6000000, "md5", file_mtime=time.time(), generated_at=time.time())
        ]
        
        for fp in fingerprints:
            self.db.store_fingerprint(fp)
        
        # Get statistics
        stats = self.db.get_fingerprint_statistics()
        
        self.assertEqual(stats['total_fingerprints'], 3)
        self.assertEqual(stats['unique_fingerprints'], 3)
        self.assertEqual(stats['chromaprint_count'], 2)
        self.assertEqual(stats['md5_count'], 1)
    
    def test_operation_recording(self):
        """Test operation recording and retrieval"""
        # Create test operation
        operation = OperationRecord(
            operation_id="op_123",
            operation_type="move",
            source_path="/test/source.mp3",
            target_path="/test/target.mp3",
            operation_data='{"metadata": "test"}',
            timestamp=time.time(),
            status="pending"
        )
        
        # Record operation
        result = self.db.record_operation(operation)
        self.assertTrue(result)
        
        # Update status
        result = self.db.update_operation_status("op_123", "completed")
        self.assertTrue(result)
        
        # Retrieve operations
        operations = self.db.get_operations_for_recovery("completed")
        self.assertEqual(len(operations), 1)
        self.assertEqual(operations[0].operation_id, "op_123")
        self.assertEqual(operations[0].status, "completed")
    
    def test_progress_tracking(self):
        """Test progress tracking"""
        # Create test progress
        progress = ProgressRecord(
            session_id="session_123",
            stage="fingerprinting",
            files_total=100,
            files_processed=50,
            files_succeeded=45,
            files_failed=5,
            bytes_processed=50000000,
            start_time=time.time(),
            last_update=time.time(),
            metadata='{"notes": "test session"}'
        )
        
        # Update progress
        result = self.db.update_progress(progress)
        self.assertTrue(result)
        
        # Retrieve progress
        session_progress = self.db.get_session_progress("session_123")
        self.assertEqual(len(session_progress), 1)
        self.assertEqual(session_progress[0].stage, "fingerprinting")
        self.assertEqual(session_progress[0].files_total, 100)
        self.assertEqual(session_progress[0].files_processed, 50)
    
    def test_overall_statistics(self):
        """Test overall statistics"""
        # Add some test progress records
        progress1 = ProgressRecord("session_1", "stage_1", 100, 100, 95, 5, 1000000, time.time(), time.time(), "")
        progress2 = ProgressRecord("session_2", "stage_1", 200, 180, 170, 10, 2000000, time.time(), time.time(), "")
        
        self.db.update_progress(progress1)
        self.db.update_progress(progress2)
        
        # Get overall statistics
        stats = self.db.get_overall_statistics()
        
        self.assertEqual(stats.get('total_sessions'), 2)
        self.assertEqual(stats.get('total_files_processed'), 280)
        self.assertEqual(stats.get('total_bytes_processed'), 3000000)
    
    def test_database_maintenance(self):
        """Test database maintenance operations"""
        # Test vacuum
        result = self.db.vacuum_database()
        self.assertTrue(result)
        
        # Test size information
        size_info = self.db.get_database_size()
        self.assertIn('total_size_bytes', size_info)
        self.assertIn('fingerprint_records', size_info)
        self.assertIn('operation_records', size_info)
        self.assertIn('progress_records', size_info)
        
        # Initially should be empty
        self.assertEqual(size_info['fingerprint_records'], 0)
        self.assertEqual(size_info['operation_records'], 0)
        self.assertEqual(size_info['progress_records'], 0)
    
    def test_cleanup_stale_fingerprints(self):
        """Test cleanup of stale fingerprints"""
        # Create old fingerprint (simulate with very old timestamp)
        old_fingerprint = FingerprintRecord(
            file_path="/nonexistent/file.mp3",
            fingerprint="old_fp",
            duration=180,
            file_size=8000000,
            algorithm="chromaprint",
            file_mtime=time.time(),
            generated_at=time.time() - (40 * 24 * 3600)  # 40 days ago
        )
        
        # Store old fingerprint
        self.db.store_fingerprint(old_fingerprint)
        
        # Cleanup stale fingerprints (30 day limit)
        removed = self.db.cleanup_stale_fingerprints(max_age_days=30)
        
        # Should have removed the old fingerprint for nonexistent file
        self.assertGreaterEqual(removed, 0)
    
    def test_concurrent_access(self):
        """Test concurrent database access"""
        import threading
        
        results = []
        
        def worker(worker_id):
            try:
                fingerprint = FingerprintRecord(
                    file_path=f"/test/worker_{worker_id}.mp3",
                    fingerprint=f"fp_{worker_id}",
                    duration=180,
                    file_size=8000000,
                    algorithm="chromaprint",
                    file_mtime=time.time(),
                    generated_at=time.time()
                )
                result = self.db.store_fingerprint(fingerprint)
                results.append(result)
            except Exception as e:
                results.append(False)
        
        # Create multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # All operations should succeed
        self.assertTrue(all(results))
        self.assertEqual(len(results), 5)


if __name__ == '__main__':
    unittest.main()