#!/usr/bin/env python3
"""
Minimal Database Schema Test

Tests the unified schema without any external dependencies.
"""

import sys
import sqlite3
import tempfile
import shutil
from pathlib import Path

# Direct import without going through __init__.py
sys.path.insert(0, str(Path(__file__).parent.parent / 'src' / 'music_cleanup' / 'core'))

try:
    import unified_schema
    print("✅ Successfully imported unified_schema module")
except ImportError as e:
    print(f"❌ Failed to import unified_schema: {e}")
    sys.exit(1)


def test_schema():
    """Test the unified database schema"""
    print("\n🎵 Testing Unified Database Schema")
    print("=" * 50)
    
    # Create temporary database
    temp_dir = tempfile.mkdtemp()
    test_db_path = Path(temp_dir) / "test_schema.db"
    
    try:
        # Create schema manager
        schema_manager = unified_schema.UnifiedSchemaManager()
        
        # Create database
        print("Creating test database...")
        conn = sqlite3.connect(str(test_db_path))
        
        # Create schema
        schema_manager.create_unified_schema(conn)
        print("✅ Schema created successfully")
        
        # Test tables exist
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cursor.fetchall()]
        expected_tables = list(schema_manager.schema_tables.keys())
        
        print(f"\nFound {len(tables)} tables:")
        for table in tables:
            print(f"  - {table}")
        
        missing = set(expected_tables) - set(tables)
        if missing:
            print(f"❌ Missing tables: {missing}")
            return False
        
        print(f"✅ All {len(expected_tables)} expected tables created")
        
        # Test foreign keys enabled
        cursor = conn.execute("PRAGMA foreign_keys")
        fk_enabled = cursor.fetchone()[0]
        if fk_enabled:
            print("✅ Foreign key constraints enabled")
        else:
            print("❌ Foreign key constraints not enabled")
            return False
        
        # Test basic data insertion
        print("\nTesting data insertion...")
        
        # Insert test data with relationships
        cursor = conn.execute("""
            INSERT INTO fingerprints (fingerprint, duration, bitrate)
            VALUES (?, ?, ?)
        """, ("test_fp_123", 180.0, 320))
        fp_id = cursor.lastrowid
        
        cursor = conn.execute("""
            INSERT INTO metadata (artist, title, genre)
            VALUES (?, ?, ?)
        """, ("Test Artist", "Test Song", "Electronic"))
        meta_id = cursor.lastrowid
        
        cursor = conn.execute("""
            INSERT INTO files (path, fingerprint_id, metadata_id, quality_score)
            VALUES (?, ?, ?, ?)
        """, ("/test/song.mp3", fp_id, meta_id, 0.85))
        file_id = cursor.lastrowid
        
        conn.commit()
        print("✅ Test data inserted successfully")
        
        # Test relationship query
        cursor = conn.execute("""
            SELECT f.path, fp.fingerprint, m.artist, m.title
            FROM files f
            JOIN fingerprints fp ON f.fingerprint_id = fp.id
            JOIN metadata m ON f.metadata_id = m.id
            WHERE f.id = ?
        """, (file_id,))
        
        result = cursor.fetchone()
        if result:
            path, fingerprint, artist, title = result
            print(f"✅ Relationship query successful:")
            print(f"   File: {path}")
            print(f"   Artist: {artist} - {title}")
            print(f"   Fingerprint: {fingerprint}")
        else:
            print("❌ Relationship query failed")
            return False
        
        # Test foreign key constraint
        print("\nTesting foreign key constraints...")
        try:
            cursor = conn.execute("""
                INSERT INTO files (path, fingerprint_id) VALUES (?, ?)
            """, ("/test/invalid.mp3", 99999))
            conn.commit()
            print("❌ Foreign key constraint not enforced")
            return False
        except sqlite3.IntegrityError:
            print("✅ Foreign key constraints properly enforced")
            conn.rollback()
        
        # Test schema validation
        print("\nTesting schema validation...")
        if schema_manager.validate_schema(conn):
            print("✅ Schema validation passed")
        else:
            print("❌ Schema validation failed")
            return False
        
        conn.close()
        
        print("\n" + "=" * 50)
        print("🎉 All schema tests passed!")
        print("✅ Unified database schema working correctly")
        print("✅ Foreign key relationships properly defined")
        print("✅ Data integrity constraints enforced")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def main():
    success = test_schema()
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())