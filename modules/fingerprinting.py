"""
Audio fingerprinting module using Chromaprint/AcoustID
"""
import os
import sqlite3
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import hashlib
from datetime import datetime
# Optional imports for audio fingerprinting
try:
    import acoustid
    ACOUSTID_AVAILABLE = True
except ImportError:
    ACOUSTID_AVAILABLE = False

try:
    import chromaprint
    CHROMAPRINT_AVAILABLE = True
except ImportError:
    CHROMAPRINT_AVAILABLE = False
from mutagen import File as MutagenFile
from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.oggvorbis import OggVorbis
from mutagen.mp4 import MP4
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging


class AudioFingerprinter:
    """Handle audio fingerprinting and duplicate detection"""
    
    def __init__(self, db_path: str = 'fingerprints.db', acoustid_key: str = None):
        """Initialize fingerprinter with database"""
        self.db_path = db_path
        self.acoustid_key = acoustid_key
        self.logger = logging.getLogger(__name__)
        self._init_database()
        
    def _init_database(self):
        """Initialize SQLite database for fingerprint storage"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create fingerprints table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fingerprints (
                file_path TEXT PRIMARY KEY,
                fingerprint TEXT,
                duration REAL,
                file_hash TEXT,
                file_size INTEGER,
                format TEXT,
                bitrate INTEGER,
                sample_rate INTEGER,
                channels INTEGER,
                created_at TIMESTAMP,
                acoustid_id TEXT,
                metadata TEXT
            )
        ''')
        
        # Create index for fingerprint matching
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_fingerprint 
            ON fingerprints(fingerprint)
        ''')
        
        # Create duplicates table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS duplicates (
                group_id TEXT,
                file_path TEXT,
                quality_score INTEGER,
                is_best INTEGER DEFAULT 0,
                FOREIGN KEY (file_path) REFERENCES fingerprints(file_path)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def get_file_hash(self, file_path: str, chunk_size: int = 8192) -> str:
        """Calculate file hash for quick comparison"""
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, 'rb') as f:
                # Read first and last chunks for speed
                f.seek(0)
                hash_md5.update(f.read(chunk_size))
                
                # Get file size
                f.seek(0, 2)
                file_size = f.tell()
                
                if file_size > chunk_size * 2:
                    f.seek(-chunk_size, 2)
                    hash_md5.update(f.read(chunk_size))
                
                hash_md5.update(str(file_size).encode())
            
            return hash_md5.hexdigest()
        except Exception as e:
            self.logger.error(f"Error hashing file {file_path}: {e}")
            return None
    
    def extract_audio_info(self, file_path: str) -> Dict:
        """Extract audio format information"""
        try:
            audio = MutagenFile(file_path)
            if audio is None:
                return None
            
            info = {
                'format': audio.mime[0].split('/')[-1] if audio.mime else 'unknown',
                'duration': audio.info.length if hasattr(audio.info, 'length') else 0,
                'bitrate': getattr(audio.info, 'bitrate', 0),
                'sample_rate': getattr(audio.info, 'sample_rate', 0),
                'channels': getattr(audio.info, 'channels', 0),
                'file_size': os.path.getsize(file_path)
            }
            
            # Get metadata
            metadata = {}
            if audio.tags:
                common_tags = ['title', 'artist', 'album', 'date', 'genre', 'albumartist']
                for tag in common_tags:
                    value = audio.tags.get(tag)
                    if value:
                        metadata[tag] = str(value[0]) if isinstance(value, list) else str(value)
            
            info['metadata'] = metadata
            return info
            
        except Exception as e:
            self.logger.error(f"Error extracting audio info from {file_path}: {e}")
            return None
    
    def generate_fingerprint(self, file_path: str) -> Tuple[str, float]:
        """Generate audio fingerprint using chromaprint"""
        try:
            # Check if fpcalc is available
            if self._is_fpcalc_available():
                # Use fpcalc command line tool (more reliable)
                result = subprocess.run(
                    ['fpcalc', '-raw', '-length', '120', file_path],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    fingerprint = None
                    duration = None
                    
                    for line in lines:
                        if line.startswith('FINGERPRINT='):
                            fingerprint = line.split('=', 1)[1]
                        elif line.startswith('DURATION='):
                            duration = float(line.split('=', 1)[1])
                    
                    if fingerprint and duration:
                        return fingerprint, duration
            
            # Fallback to Python API
            if ACOUSTID_AVAILABLE:
                try:
                    duration, fp_encoded = acoustid.fingerprint_file(file_path)
                    return fp_encoded.decode() if isinstance(fp_encoded, bytes) else fp_encoded, duration
                except Exception as e:
                    self.logger.warning(f"Python acoustid failed: {e}")
            
            # Final fallback: hash-based fingerprint
            self.logger.debug(f"Using hash-based fingerprint for {file_path}")
            return self._generate_hash_fingerprint(file_path)
            
        except Exception as e:
            self.logger.error(f"Error generating fingerprint for {file_path}: {e}")
            return None, None
    
    def _is_fpcalc_available(self) -> bool:
        """Check if fpcalc command is available"""
        try:
            result = subprocess.run(['fpcalc', '-version'], 
                                  capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except:
            return False
    
    def _generate_hash_fingerprint(self, file_path: str) -> Tuple[str, float]:
        """Generate hash-based fingerprint as fallback"""
        try:
            # Get file hash and metadata as pseudo-fingerprint
            file_hash = self.get_file_hash(file_path)
            audio_info = self.extract_audio_info(file_path)
            
            if file_hash and audio_info:
                # Create pseudo-fingerprint from hash and metadata
                pseudo_fp = f"{file_hash}_{audio_info.get('duration', 0)}"
                return pseudo_fp, audio_info.get('duration', 0)
            
            return None, None
        except Exception as e:
            self.logger.error(f"Error generating hash fingerprint: {e}")
            return None, None
    
    def store_fingerprint(self, file_path: str, fingerprint: str, duration: float, 
                         audio_info: Dict, file_hash: str):
        """Store fingerprint in database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO fingerprints 
                (file_path, fingerprint, duration, file_hash, file_size, 
                 format, bitrate, sample_rate, channels, created_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                file_path,
                fingerprint,
                duration,
                file_hash,
                audio_info.get('file_size', 0),
                audio_info.get('format', 'unknown'),
                audio_info.get('bitrate', 0),
                audio_info.get('sample_rate', 0),
                audio_info.get('channels', 0),
                datetime.now().isoformat(),
                json.dumps(audio_info.get('metadata', {}))
            ))
            
            conn.commit()
            
        except Exception as e:
            self.logger.error(f"Error storing fingerprint for {file_path}: {e}")
        finally:
            conn.close()
    
    def get_cached_fingerprint(self, file_path: str, file_hash: str) -> Optional[str]:
        """Get cached fingerprint if file hasn't changed"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT fingerprint FROM fingerprints 
            WHERE file_path = ? AND file_hash = ?
        ''', (file_path, file_hash))
        
        result = cursor.fetchone()
        conn.close()
        
        return result[0] if result else None
    
    def process_file(self, file_path: str) -> Dict:
        """Process a single file and return fingerprint data"""
        try:
            # Get file hash
            file_hash = self.get_file_hash(file_path)
            if not file_hash:
                return None
            
            # Check cache
            cached_fp = self.get_cached_fingerprint(file_path, file_hash)
            
            # Extract audio info
            audio_info = self.extract_audio_info(file_path)
            if not audio_info:
                return None
            
            # Generate or use cached fingerprint
            if cached_fp:
                fingerprint = cached_fp
                duration = audio_info['duration']
                self.logger.debug(f"Using cached fingerprint for {file_path}")
            else:
                fingerprint, duration = self.generate_fingerprint(file_path)
                if not fingerprint:
                    return None
                
                # Store in database
                self.store_fingerprint(file_path, fingerprint, duration, audio_info, file_hash)
            
            return {
                'file_path': file_path,
                'fingerprint': fingerprint,
                'duration': duration,
                'file_hash': file_hash,
                'audio_info': audio_info
            }
            
        except Exception as e:
            self.logger.error(f"Error processing file {file_path}: {e}")
            return None
    
    def find_duplicates(self, threshold: float = 0.95) -> List[List[Dict]]:
        """Find duplicate files based on fingerprints"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get all fingerprints
        cursor.execute('''
            SELECT file_path, fingerprint, duration, format, bitrate, file_size, metadata
            FROM fingerprints
            WHERE fingerprint IS NOT NULL
        ''')
        
        files = []
        for row in cursor.fetchall():
            files.append({
                'file_path': row[0],
                'fingerprint': row[1],
                'duration': row[2],
                'format': row[3],
                'bitrate': row[4],
                'file_size': row[5],
                'metadata': json.loads(row[6]) if row[6] else {}
            })
        
        conn.close()
        
        # Group by exact fingerprint match (most reliable for duplicates)
        fingerprint_groups = {}
        for file_data in files:
            fp = file_data['fingerprint']
            if fp not in fingerprint_groups:
                fingerprint_groups[fp] = []
            fingerprint_groups[fp].append(file_data)
        
        # Filter groups with duplicates
        duplicate_groups = []
        for fp, group in fingerprint_groups.items():
            if len(group) > 1:
                duplicate_groups.append(group)
        
        return duplicate_groups
    
    def rank_duplicates(self, duplicate_group: List[Dict]) -> List[Dict]:
        """Rank duplicates by quality"""
        format_priority = {
            'flac': 1000,
            'wav': 990,
            'audio/x-flac': 1000,
            'audio/x-wav': 990,
            'mp3': 500,
            'audio/mpeg': 500,
            'm4a': 400,
            'audio/mp4': 400,
            'ogg': 350,
            'audio/ogg': 350,
            'wma': 300,
            'audio/x-ms-wma': 300
        }
        
        for file_data in duplicate_group:
            # Calculate quality score
            format_score = format_priority.get(file_data['format'].lower(), 100)
            bitrate_score = file_data['bitrate'] / 1000 if file_data['bitrate'] else 0
            
            # Bonus for complete metadata
            metadata = file_data.get('metadata', {})
            metadata_score = sum(10 for field in ['artist', 'title', 'album', 'date'] 
                               if metadata.get(field))
            
            file_data['quality_score'] = format_score + bitrate_score + metadata_score
        
        # Sort by quality score (highest first)
        return sorted(duplicate_group, key=lambda x: x['quality_score'], reverse=True)
    
    def process_files_batch(self, file_paths: List[str], max_workers: int = 4) -> Dict[str, Dict]:
        """Process multiple files in parallel"""
        results = {}
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_path = {
                executor.submit(self.process_file, path): path 
                for path in file_paths
            }
            
            for future in as_completed(future_to_path):
                path = future_to_path[future]
                try:
                    result = future.result()
                    if result:
                        results[path] = result
                except Exception as e:
                    self.logger.error(f"Error processing {path}: {e}")
        
        return results
    
    def get_statistics(self) -> Dict:
        """Get fingerprinting statistics from database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        stats = {}
        
        # Total files processed
        cursor.execute('SELECT COUNT(*) FROM fingerprints')
        stats['total_files'] = cursor.fetchone()[0]
        
        # Files with fingerprints
        cursor.execute('SELECT COUNT(*) FROM fingerprints WHERE fingerprint IS NOT NULL')
        stats['files_with_fingerprints'] = cursor.fetchone()[0]
        
        # Format distribution
        cursor.execute('''
            SELECT format, COUNT(*) as count 
            FROM fingerprints 
            GROUP BY format 
            ORDER BY count DESC
        ''')
        stats['format_distribution'] = dict(cursor.fetchall())
        
        # Duplicate groups
        duplicate_groups = self.find_duplicates()
        stats['duplicate_groups'] = len(duplicate_groups)
        stats['duplicate_files'] = sum(len(group) for group in duplicate_groups)
        
        conn.close()
        return stats