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
from .audio_quality import AudioQualityAnalyzer


class AudioFingerprinter:
    """Handle audio fingerprinting and duplicate detection"""
    
    def __init__(self, db_path: str = 'fingerprints.db', acoustid_key: str = None):
        """Initialize fingerprinter with database"""
        self.db_path = db_path
        self.acoustid_key = acoustid_key
        self.logger = logging.getLogger(__name__)
        self.quality_analyzer = AudioQualityAnalyzer()
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
                metadata TEXT,
                quality_score INTEGER,
                quality_rating TEXT,
                quality_issues TEXT
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
                         audio_info: Dict, file_hash: str, quality_analysis: Dict = None):
        """Store fingerprint in database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO fingerprints 
                (file_path, fingerprint, duration, file_hash, file_size, 
                 format, bitrate, sample_rate, channels, created_at, metadata,
                 quality_score, quality_rating, quality_issues)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                json.dumps(audio_info.get('metadata', {})),
                quality_analysis.get('quality_score', 0) if quality_analysis else 0,
                quality_analysis.get('quality_rating', 'unknown') if quality_analysis else 'unknown',
                json.dumps(quality_analysis.get('issues', [])) if quality_analysis else '[]'
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
            
            # Perform quality analysis
            quality_analysis = self.quality_analyzer.analyze_audio_quality(file_path)
            
            # Generate or use cached fingerprint
            if cached_fp:
                fingerprint = cached_fp
                duration = audio_info['duration']
                self.logger.debug(f"Using cached fingerprint for {file_path}")
            else:
                fingerprint, duration = self.generate_fingerprint(file_path)
                if not fingerprint:
                    return None
                
                # Store in database with quality analysis
                self.store_fingerprint(file_path, fingerprint, duration, audio_info, file_hash, quality_analysis)
            
            return {
                'file_path': file_path,
                'fingerprint': fingerprint,
                'duration': duration,
                'file_hash': file_hash,
                'audio_info': audio_info,
                'quality_analysis': quality_analysis
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
            SELECT file_path, fingerprint, duration, format, bitrate, file_size, metadata, 
                   quality_score, quality_rating, quality_issues
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
                'metadata': json.loads(row[6]) if row[6] else {},
                'quality_score': row[7] if row[7] else 0,
                'quality_rating': row[8] if row[8] else 'unknown',
                'quality_issues': json.loads(row[9]) if row[9] else []
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
        """Rank duplicates by quality using advanced quality analysis"""
        # Use the quality analyzer for duplicate comparison
        files_for_analysis = []
        for file_data in duplicate_group:
            files_for_analysis.append({
                'file_path': file_data['file_path'],
                'quality_score': file_data.get('quality_score', 0),
                'quality_rating': file_data.get('quality_rating', 'unknown'),
                'quality_issues': file_data.get('quality_issues', [])
            })
        
        # Use quality analyzer comparison
        comparison_result = self.quality_analyzer.compare_duplicate_quality(files_for_analysis)
        
        if comparison_result and comparison_result.get('quality_comparison'):
            # Sort by quality score from advanced analysis
            sorted_files = comparison_result['quality_comparison']
            
            # Map back to original file data structure
            ranked_files = []
            for analyzed_file in sorted_files:
                original_file = next((f for f in duplicate_group if f['file_path'] == analyzed_file['file_path']), None)
                if original_file:
                    # Add quality information from analysis
                    original_file['advanced_quality_score'] = analyzed_file.get('quality_score', 0)
                    original_file['quality_issues'] = analyzed_file.get('quality_issues', [])
                    ranked_files.append(original_file)
            
            return ranked_files
        
        # Fallback to original ranking if quality analysis fails
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
        
        # Quality statistics
        cursor.execute('''
            SELECT quality_rating, COUNT(*) as count 
            FROM fingerprints 
            WHERE quality_rating IS NOT NULL
            GROUP BY quality_rating 
            ORDER BY count DESC
        ''')
        stats['quality_distribution'] = dict(cursor.fetchall())
        
        # Files with quality issues
        cursor.execute('''
            SELECT COUNT(*) FROM fingerprints 
            WHERE quality_issues IS NOT NULL 
            AND quality_issues != '[]'
        ''')
        stats['files_with_issues'] = cursor.fetchone()[0]
        
        conn.close()
        return stats
    
    def get_quality_report(self) -> Dict:
        """Get detailed quality analysis report"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        report = {
            'total_files_analyzed': 0,
            'quality_summary': {},
            'problematic_files': [],
            'recommendations': []
        }
        
        # Get all files with quality analysis
        cursor.execute('''
            SELECT file_path, quality_score, quality_rating, quality_issues, 
                   format, bitrate, file_size 
            FROM fingerprints 
            WHERE quality_score IS NOT NULL
        ''')
        
        files = cursor.fetchall()
        report['total_files_analyzed'] = len(files)
        
        # Quality distribution
        quality_counts = {}
        issue_counts = {}
        
        for file_data in files:
            file_path, quality_score, quality_rating, quality_issues_json, format_type, bitrate, file_size = file_data
            
            # Count quality ratings
            quality_counts[quality_rating] = quality_counts.get(quality_rating, 0) + 1
            
            # Parse and count issues
            try:
                quality_issues = json.loads(quality_issues_json) if quality_issues_json else []
                for issue in quality_issues:
                    issue_counts[issue] = issue_counts.get(issue, 0) + 1
                
                # Add to problematic files if has issues
                if quality_issues:
                    report['problematic_files'].append({
                        'file_path': file_path,
                        'quality_score': quality_score,
                        'quality_rating': quality_rating,
                        'issues': quality_issues,
                        'format': format_type,
                        'bitrate': bitrate,
                        'file_size_mb': round(file_size / (1024 * 1024), 2) if file_size else 0
                    })
                    
            except (json.JSONDecodeError, TypeError):
                continue
        
        report['quality_summary'] = {
            'quality_distribution': quality_counts,
            'issue_distribution': issue_counts
        }
        
        # Generate recommendations
        recommendations = []
        if issue_counts.get('very_low_bitrate', 0) > 0:
            recommendations.append(f"Found {issue_counts['very_low_bitrate']} files with very low bitrate - consider finding higher quality sources")
        
        if issue_counts.get('corrupted_header', 0) > 0:
            recommendations.append(f"Found {issue_counts['corrupted_header']} files with corrupted headers - re-download recommended")
        
        if issue_counts.get('no_metadata', 0) > 0:
            recommendations.append(f"Found {issue_counts['no_metadata']} files with missing metadata - consider adding tags")
        
        if quality_counts.get('very_poor', 0) > 0:
            recommendations.append(f"Found {quality_counts['very_poor']} files with very poor quality - consider replacing")
        
        report['recommendations'] = recommendations
        
        conn.close()
        return report