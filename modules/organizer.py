"""
File organization and management module
"""
import os
import shutil
import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import sqlite3
import hashlib
from collections import defaultdict


class FileOrganizer:
    """Handle file organization, copying, and tracking"""
    
    def __init__(self, target_root: str, db_path: str = 'file_operations.db'):
        """Initialize file organizer"""
        self.target_root = Path(target_root)
        self.db_path = db_path
        self.logger = logging.getLogger(__name__)
        self._init_database()
        
        # Track operations for reporting
        self.stats = {
            'files_copied': 0,
            'files_skipped': 0,
            'duplicates_handled': 0,
            'errors': 0,
            'space_saved': 0,
            'genres_created': set(),
            'decades_created': set()
        }
    
    def _init_database(self):
        """Initialize database for tracking file operations"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Track all file operations
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS file_operations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_path TEXT NOT NULL,
                target_path TEXT,
                operation TEXT NOT NULL,
                status TEXT NOT NULL,
                timestamp TIMESTAMP,
                file_size INTEGER,
                error_message TEXT,
                metadata TEXT
            )
        ''')
        
        # Track duplicate handling
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS duplicate_decisions (
                group_id TEXT NOT NULL,
                best_file TEXT NOT NULL,
                duplicate_files TEXT NOT NULL,
                space_saved INTEGER,
                timestamp TIMESTAMP
            )
        ''')
        
        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_source_path ON file_operations(source_path)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_operation ON file_operations(operation)')
        
        conn.commit()
        conn.close()
    
    def create_target_structure(self, genre: str, decade: str) -> Path:
        """Create and return target directory structure"""
        # Sanitize genre and decade for folder names
        genre = self._sanitize_folder_name(genre or 'Unknown')
        decade = self._sanitize_folder_name(decade or 'Unknown')
        
        target_dir = self.target_root / genre / decade
        
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # Track created directories
            self.stats['genres_created'].add(genre)
            self.stats['decades_created'].add(f"{genre}/{decade}")
            
            return target_dir
            
        except Exception as e:
            self.logger.error(f"Error creating directory {target_dir}: {e}")
            # Fallback to Unknown/Unknown
            fallback_dir = self.target_root / 'Unknown' / 'Unknown'
            fallback_dir.mkdir(parents=True, exist_ok=True)
            return fallback_dir
    
    def _sanitize_folder_name(self, name: str) -> str:
        """Sanitize string for use as folder name"""
        # Remove invalid characters
        invalid_chars = '<>:"|?*'
        for char in invalid_chars:
            name = name.replace(char, '')
        
        # Replace slashes with dashes
        name = name.replace('/', '-')
        name = name.replace('\\', '-')
        
        # Remove trailing dots and spaces
        name = name.strip('. ')
        
        # Limit length
        if len(name) > 50:
            name = name[:50].strip()
        
        return name or 'Unknown'
    
    def copy_file(self, source_path: str, metadata: Dict, 
                  new_filename: str = None, dry_run: bool = False) -> Tuple[bool, str]:
        """Copy file to organized location"""
        try:
            source = Path(source_path)
            if not source.exists():
                self._log_operation(source_path, None, 'copy', 'error', 
                                  error='Source file not found')
                return False, "Source file not found"
            
            # Determine target location
            genre = metadata.get('genre', 'Unknown')
            year = metadata.get('year')
            decade = self._year_to_decade(year) if year else 'Unknown'
            
            # Create target directory
            target_dir = self.create_target_structure(genre, decade)
            
            # Determine filename
            if new_filename:
                filename = new_filename
            else:
                filename = source.name
            
            target_path = target_dir / filename
            
            # Handle existing file
            if target_path.exists():
                # Compare files
                if self._files_are_identical(source_path, str(target_path)):
                    self._log_operation(source_path, str(target_path), 'copy', 
                                      'skipped', error='Identical file exists')
                    self.stats['files_skipped'] += 1
                    return True, str(target_path)
                else:
                    # Add number suffix
                    target_path = self._get_unique_path(target_path)
            
            if dry_run:
                self._log_operation(source_path, str(target_path), 'copy', 'dry_run')
                return True, str(target_path)
            
            # Copy file
            shutil.copy2(source_path, target_path)
            
            # Verify copy
            if not self._verify_copy(source_path, str(target_path)):
                os.remove(target_path)
                raise Exception("File verification failed")
            
            # Log success
            file_size = source.stat().st_size
            self._log_operation(source_path, str(target_path), 'copy', 'success', 
                              file_size=file_size, metadata=metadata)
            self.stats['files_copied'] += 1
            
            return True, str(target_path)
            
        except Exception as e:
            self.logger.error(f"Error copying {source_path}: {e}")
            self._log_operation(source_path, None, 'copy', 'error', error=str(e))
            self.stats['errors'] += 1
            return False, str(e)
    
    def _files_are_identical(self, file1: str, file2: str) -> bool:
        """Check if two files are identical using hash"""
        try:
            # Quick check: file size
            if os.path.getsize(file1) != os.path.getsize(file2):
                return False
            
            # Hash comparison
            hash1 = self._calculate_file_hash(file1)
            hash2 = self._calculate_file_hash(file2)
            
            return hash1 == hash2
            
        except Exception:
            return False
    
    def _calculate_file_hash(self, file_path: str, chunk_size: int = 8192) -> str:
        """Calculate SHA256 hash of file"""
        hash_sha256 = hashlib.sha256()
        
        with open(file_path, 'rb') as f:
            while chunk := f.read(chunk_size):
                hash_sha256.update(chunk)
        
        return hash_sha256.hexdigest()
    
    def _verify_copy(self, source: str, target: str) -> bool:
        """Verify copied file integrity"""
        try:
            # Check size
            if os.path.getsize(source) != os.path.getsize(target):
                return False
            
            # For large files, just check size and first/last chunks
            file_size = os.path.getsize(source)
            if file_size > 50 * 1024 * 1024:  # 50MB
                return self._verify_large_file(source, target)
            else:
                # Full hash comparison for smaller files
                return self._files_are_identical(source, target)
                
        except Exception:
            return False
    
    def _verify_large_file(self, source: str, target: str, 
                          chunk_size: int = 1024 * 1024) -> bool:
        """Verify large file by checking beginning and end"""
        try:
            with open(source, 'rb') as f1, open(target, 'rb') as f2:
                # Check first chunk
                if f1.read(chunk_size) != f2.read(chunk_size):
                    return False
                
                # Check last chunk
                file_size = os.path.getsize(source)
                if file_size > chunk_size:
                    f1.seek(-chunk_size, 2)
                    f2.seek(-chunk_size, 2)
                    if f1.read() != f2.read():
                        return False
            
            return True
            
        except Exception:
            return False
    
    def _get_unique_path(self, path: Path) -> Path:
        """Get unique path by adding number suffix"""
        if not path.exists():
            return path
        
        base = path.stem
        extension = path.suffix
        parent = path.parent
        
        counter = 1
        while True:
            new_path = parent / f"{base} ({counter}){extension}"
            if not new_path.exists():
                return new_path
            counter += 1
            
            if counter > 100:
                # Safety limit
                raise Exception("Too many duplicate filenames")
    
    def _year_to_decade(self, year: int) -> str:
        """Convert year to decade string"""
        if not year:
            return 'Unknown'
        
        try:
            year = int(year)
            if year < 1950:
                return 'Pre-1950s'
            elif year >= 2020:
                return '2020s'
            else:
                decade = (year // 10) * 10
                return f'{decade}s'
        except:
            return 'Unknown'
    
    def handle_duplicate_group(self, duplicate_group: List[Dict], 
                             dry_run: bool = False) -> Dict:
        """Handle a group of duplicate files"""
        if not duplicate_group:
            return {}
        
        # Group should already be sorted by quality
        best_file = duplicate_group[0]
        duplicates = duplicate_group[1:]
        
        # Calculate space that will be saved
        space_saved = sum(d.get('file_size', 0) for d in duplicates)
        
        result = {
            'best_file': best_file['file_path'],
            'kept_quality': {
                'format': best_file.get('format'),
                'bitrate': best_file.get('bitrate'),
                'size': best_file.get('file_size')
            },
            'duplicates': [d['file_path'] for d in duplicates],
            'space_saved': space_saved,
            'action': 'dry_run' if dry_run else 'processed'
        }
        
        if not dry_run:
            # Log the decision
            group_id = hashlib.md5(
                best_file.get('fingerprint', '').encode()
            ).hexdigest()[:16]
            
            self._log_duplicate_decision(
                group_id,
                best_file['file_path'],
                [d['file_path'] for d in duplicates],
                space_saved
            )
            
            self.stats['duplicates_handled'] += len(duplicates)
            self.stats['space_saved'] += space_saved
        
        return result
    
    def _log_operation(self, source_path: str, target_path: Optional[str],
                      operation: str, status: str, file_size: int = None,
                      error: str = None, metadata: Dict = None):
        """Log file operation to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO file_operations 
            (source_path, target_path, operation, status, timestamp, 
             file_size, error_message, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            source_path,
            target_path,
            operation,
            status,
            datetime.now().isoformat(),
            file_size,
            error,
            json.dumps(metadata) if metadata else None
        ))
        
        conn.commit()
        conn.close()
    
    def _log_duplicate_decision(self, group_id: str, best_file: str,
                               duplicates: List[str], space_saved: int):
        """Log duplicate handling decision"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO duplicate_decisions 
            (group_id, best_file, duplicate_files, space_saved, timestamp)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            group_id,
            best_file,
            json.dumps(duplicates),
            space_saved,
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
    
    def get_operation_history(self, source_path: str = None, 
                            limit: int = 100) -> List[Dict]:
        """Get operation history from database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if source_path:
            cursor.execute('''
                SELECT * FROM file_operations 
                WHERE source_path = ? 
                ORDER BY timestamp DESC 
                LIMIT ?
            ''', (source_path, limit))
        else:
            cursor.execute('''
                SELECT * FROM file_operations 
                ORDER BY timestamp DESC 
                LIMIT ?
            ''', (limit,))
        
        columns = [desc[0] for desc in cursor.description]
        results = []
        
        for row in cursor.fetchall():
            record = dict(zip(columns, row))
            if record.get('metadata'):
                record['metadata'] = json.loads(record['metadata'])
            results.append(record)
        
        conn.close()
        return results
    
    def generate_report(self) -> Dict:
        """Generate comprehensive report of operations"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        report = {
            'summary': self.stats.copy(),
            'timestamp': datetime.now().isoformat(),
            'target_root': str(self.target_root)
        }
        
        # Get operation counts
        cursor.execute('''
            SELECT operation, status, COUNT(*) as count 
            FROM file_operations 
            GROUP BY operation, status
        ''')
        
        report['operations'] = {}
        for op, status, count in cursor.fetchall():
            if op not in report['operations']:
                report['operations'][op] = {}
            report['operations'][op][status] = count
        
        # Get duplicate statistics
        cursor.execute('''
            SELECT COUNT(*) as groups, SUM(space_saved) as total_saved 
            FROM duplicate_decisions
        ''')
        
        dup_stats = cursor.fetchone()
        report['duplicates'] = {
            'groups_processed': dup_stats[0],
            'space_saved_bytes': dup_stats[1] or 0,
            'space_saved_gb': round((dup_stats[1] or 0) / (1024**3), 2)
        }
        
        # Get genre distribution
        cursor.execute('''
            SELECT 
                json_extract(metadata, '$.genre') as genre,
                COUNT(*) as count
            FROM file_operations
            WHERE status = 'success' AND metadata IS NOT NULL
            GROUP BY genre
            ORDER BY count DESC
        ''')
        
        report['genre_distribution'] = dict(cursor.fetchall())
        
        # Get error summary
        cursor.execute('''
            SELECT error_message, COUNT(*) as count 
            FROM file_operations 
            WHERE status = 'error' AND error_message IS NOT NULL
            GROUP BY error_message 
            ORDER BY count DESC 
            LIMIT 10
        ''')
        
        report['top_errors'] = [
            {'error': err, 'count': count} 
            for err, count in cursor.fetchall()
        ]
        
        conn.close()
        
        # Convert sets to lists for JSON serialization
        report['summary']['genres_created'] = list(self.stats['genres_created'])
        report['summary']['decades_created'] = list(self.stats['decades_created'])
        
        return report
    
    def create_undo_script(self, output_file: str = 'undo_operations.sh'):
        """Create script to undo operations"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get successful copy operations
        cursor.execute('''
            SELECT source_path, target_path 
            FROM file_operations 
            WHERE operation = 'copy' AND status = 'success' 
            AND target_path IS NOT NULL
            ORDER BY timestamp
        ''')
        
        with open(output_file, 'w') as f:
            f.write('#!/bin/bash\n')
            f.write('# Undo script for music cleanup operations\n')
            f.write(f'# Generated: {datetime.now().isoformat()}\n\n')
            
            f.write('echo "This will remove all copied files. Continue? (y/n)"\n')
            f.write('read -r response\n')
            f.write('if [[ "$response" != "y" ]]; then\n')
            f.write('    echo "Aborted."\n')
            f.write('    exit 1\n')
            f.write('fi\n\n')
            
            count = 0
            for source, target in cursor.fetchall():
                f.write(f'# Original: {source}\n')
                f.write(f'rm -f "{target}"\n')
                count += 1
            
            f.write(f'\necho "Removed {count} files."\n')
        
        conn.close()
        
        # Make script executable
        os.chmod(output_file, 0o755)
        
        self.logger.info(f"Undo script created: {output_file}")