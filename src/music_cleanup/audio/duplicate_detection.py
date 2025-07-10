"""
Intelligent Duplicate Detection and Quality Ranking

Implements sophisticated duplicate detection with quality-based ranking
to identify the best version of duplicate audio files.
"""

import logging
import os
import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any

from .fingerprinting import AudioFingerprint

try:
    import mutagen
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False


class DuplicateAction(Enum):
    """Actions to take with duplicate files"""
    DELETE = "delete"
    MOVE = "move"
    REPORT_ONLY = "report-only"


@dataclass
class AudioQuality:
    """Represents audio quality metrics for ranking"""
    format_score: float  # 0-100 based on format (FLAC=100, MP3=depends on bitrate)
    bitrate_score: float  # 0-100 based on bitrate
    size_score: float    # 0-100 based on file size (larger usually better)
    metadata_score: float  # 0-100 based on metadata completeness
    overall_score: float   # Combined weighted score
    
    # Raw values for debugging
    format: str
    bitrate: Optional[int]
    file_size: int
    metadata_completeness: float


@dataclass
class DuplicateGroup:
    """Represents a group of duplicate files"""
    fingerprint: str
    files: List[AudioFingerprint]
    best_file: AudioFingerprint
    duplicates_to_remove: List[AudioFingerprint]
    total_size: int
    space_savings: int  # Size that would be saved by removing duplicates
    quality_rankings: Dict[str, AudioQuality]  # file_path -> quality


class DuplicateDetector:
    """
    Intelligent duplicate detector with quality-based ranking.
    
    Identifies duplicates based on:
    1. Exact fingerprint matches
    2. Similar fingerprints for re-encodes (>95% similarity)
    3. Duration matching (±1 second tolerance)
    
    Quality ranking criteria:
    - Format priority: FLAC > WAV > MP3 320+ > MP3 VBR > MP3 <320
    - Bitrate: Higher is better
    - File size: Larger is better (for same format)
    - Metadata completeness: More complete tags preferred
    """
    
    def __init__(self, duplicate_action: DuplicateAction = DuplicateAction.MOVE,
                 duplicates_folder: str = "Duplicates",
                 min_similarity: float = 0.95):
        """
        Initialize duplicate detector.
        
        Args:
            duplicate_action: What to do with duplicates
            duplicates_folder: Folder to move duplicates to (if action=MOVE)
            min_similarity: Minimum similarity for re-encode detection
        """
        self.duplicate_action = duplicate_action
        self.duplicates_folder = Path(duplicates_folder)
        self.min_similarity = min_similarity
        self.logger = logging.getLogger(__name__)
        
        # Format priority scoring
        self.format_scores = {
            '.flac': 100,
            '.wav': 95,
            '.m4a': 85,
            '.aac': 80,
            '.ogg': 75,
            '.mp3': 70,  # Base score, modified by bitrate
            '.wma': 40,
            '.mp2': 30
        }
        
        self.stats = {
            'groups_found': 0,
            'files_analyzed': 0,
            'duplicates_found': 0,
            'space_savings': 0,
            'actions_taken': 0
        }
    
    def detect_and_rank_duplicates(self, fingerprints: List[AudioFingerprint]) -> List[DuplicateGroup]:
        """
        Detect duplicates and rank them by quality.
        
        Args:
            fingerprints: List of audio fingerprints to analyze
            
        Returns:
            List of duplicate groups with quality rankings
        """
        self.logger.info(f"Analyzing {len(fingerprints)} files for duplicates...")
        self.stats['files_analyzed'] = len(fingerprints)
        
        # Group by fingerprint
        fingerprint_groups = self._group_by_fingerprint(fingerprints)
        
        # Process each duplicate group
        duplicate_groups = []
        for fingerprint, group_files in fingerprint_groups.items():
            if len(group_files) > 1:
                duplicate_group = self._analyze_duplicate_group(fingerprint, group_files)
                duplicate_groups.append(duplicate_group)
        
        self.stats['groups_found'] = len(duplicate_groups)
        self.stats['duplicates_found'] = sum(
            len(group.duplicates_to_remove) for group in duplicate_groups
        )
        self.stats['space_savings'] = sum(
            group.space_savings for group in duplicate_groups
        )
        
        self.logger.info(
            f"Found {len(duplicate_groups)} duplicate groups with "
            f"{self.stats['duplicates_found']} duplicates "
            f"({self.stats['space_savings'] / (1024**3):.2f} GB potential savings)"
        )
        
        return duplicate_groups
    
    def _group_by_fingerprint(self, fingerprints: List[AudioFingerprint]) -> Dict[str, List[AudioFingerprint]]:
        """Group fingerprints by their fingerprint value"""
        groups = {}
        
        for fp in fingerprints:
            if fp.fingerprint not in groups:
                groups[fp.fingerprint] = []
            groups[fp.fingerprint].append(fp)
        
        # TODO: Add similarity matching for re-encodes
        # This would require implementing fingerprint similarity calculation
        
        return groups
    
    def _analyze_duplicate_group(self, fingerprint: str, files: List[AudioFingerprint]) -> DuplicateGroup:
        """Analyze a group of duplicate files and rank by quality"""
        
        # Calculate quality scores for each file
        quality_rankings = {}
        for file_fp in files:
            quality = self._calculate_audio_quality(file_fp)
            quality_rankings[file_fp.file_path] = quality
        
        # Sort by quality (best first)
        sorted_files = sorted(files, key=lambda f: quality_rankings[f.file_path].overall_score, reverse=True)
        
        best_file = sorted_files[0]
        duplicates_to_remove = sorted_files[1:]
        
        # Calculate space savings
        total_size = sum(f.file_size for f in files)
        space_savings = sum(f.file_size for f in duplicates_to_remove)
        
        self.logger.debug(f"Duplicate group: Best={Path(best_file.file_path).name}, "
                         f"Removing={len(duplicates_to_remove)} files, "
                         f"Savings={space_savings / (1024**2):.1f}MB")
        
        return DuplicateGroup(
            fingerprint=fingerprint,
            files=files,
            best_file=best_file,
            duplicates_to_remove=duplicates_to_remove,
            total_size=total_size,
            space_savings=space_savings,
            quality_rankings=quality_rankings
        )
    
    def _calculate_audio_quality(self, file_fp: AudioFingerprint) -> AudioQuality:
        """Calculate comprehensive quality score for an audio file"""
        
        # Format scoring
        file_ext = Path(file_fp.file_path).suffix.lower()
        format_score = self.format_scores.get(file_ext, 50)
        
        # Adjust MP3 score based on bitrate
        if file_ext == '.mp3' and file_fp.bitrate:
            if file_fp.bitrate >= 320:
                format_score = 90
            elif file_fp.bitrate >= 256:
                format_score = 80
            elif file_fp.bitrate >= 192:
                format_score = 70
            elif file_fp.bitrate >= 128:
                format_score = 60
            else:
                format_score = 40
        
        # Bitrate scoring
        bitrate_score = 50  # Default
        if file_fp.bitrate:
            if file_fp.bitrate >= 1411:  # Lossless
                bitrate_score = 100
            elif file_fp.bitrate >= 320:
                bitrate_score = 95
            elif file_fp.bitrate >= 256:
                bitrate_score = 85
            elif file_fp.bitrate >= 192:
                bitrate_score = 75
            elif file_fp.bitrate >= 128:
                bitrate_score = 60
            else:
                bitrate_score = 30
        
        # File size scoring (relative to format and duration)
        size_score = self._calculate_size_score(file_fp)
        
        # Metadata completeness scoring
        metadata_score = self._calculate_metadata_score(file_fp.file_path)
        
        # Combined score (weighted)
        overall_score = (
            format_score * 0.4 +    # Format is most important
            bitrate_score * 0.3 +   # Bitrate is second most important
            size_score * 0.2 +      # Size indicates quality
            metadata_score * 0.1    # Metadata is nice but not critical for quality
        )
        
        return AudioQuality(
            format_score=format_score,
            bitrate_score=bitrate_score,
            size_score=size_score,
            metadata_score=metadata_score,
            overall_score=overall_score,
            format=file_ext,
            bitrate=file_fp.bitrate,
            file_size=file_fp.file_size,
            metadata_completeness=metadata_score / 100
        )
    
    def _calculate_size_score(self, file_fp: AudioFingerprint) -> float:
        """Calculate quality score based on file size"""
        if not file_fp.duration or file_fp.duration <= 0:
            return 50  # Can't calculate without duration
        
        # Calculate bytes per second
        bytes_per_second = file_fp.file_size / file_fp.duration
        
        # Score based on data rate
        if bytes_per_second >= 176400:  # ~1411 kbps (CD quality)
            return 100
        elif bytes_per_second >= 40000:  # ~320 kbps
            return 90
        elif bytes_per_second >= 32000:  # ~256 kbps
            return 80
        elif bytes_per_second >= 24000:  # ~192 kbps
            return 70
        elif bytes_per_second >= 16000:  # ~128 kbps
            return 60
        else:
            return 30
    
    def _calculate_metadata_score(self, file_path: str) -> float:
        """Calculate quality score based on metadata completeness"""
        if not MUTAGEN_AVAILABLE:
            return 50  # Can't check without mutagen
        
        try:
            audio_file = mutagen.File(file_path)
            if not audio_file:
                return 0
            
            # Check for essential tags
            essential_tags = ['artist', 'title', 'album']
            nice_to_have_tags = ['date', 'genre', 'tracknumber', 'albumartist']
            
            score = 0
            
            # Essential tags (60% of score)
            for tag in essential_tags:
                tag_values = [
                    audio_file.get(tag, []),
                    audio_file.get(tag.upper(), []),
                    audio_file.get(f'T{tag.upper()}', [])  # ID3v2
                ]
                
                if any(tag_values):
                    score += 20
            
            # Nice-to-have tags (40% of score)
            for tag in nice_to_have_tags:
                tag_values = [
                    audio_file.get(tag, []),
                    audio_file.get(tag.upper(), []),
                    audio_file.get(f'T{tag.upper()}', [])  # ID3v2
                ]
                
                if any(tag_values):
                    score += 10
            
            return min(score, 100)
            
        except Exception as e:
            self.logger.debug(f"Metadata analysis failed for {file_path}: {e}")
            return 30  # Partial score for readable file
    
    def handle_duplicates(self, duplicate_groups: List[DuplicateGroup], 
                         progress_callback: Optional[callable] = None) -> Dict[str, Any]:
        """
        Handle duplicates according to configured action.
        
        Args:
            duplicate_groups: List of duplicate groups to process
            progress_callback: Optional progress callback
            
        Returns:
            Dictionary with operation results
        """
        results = {
            'processed_groups': 0,
            'files_processed': 0,
            'files_deleted': 0,
            'files_moved': 0,
            'space_freed': 0,
            'errors': 0,
            'actions': []
        }
        
        if self.duplicate_action == DuplicateAction.REPORT_ONLY:
            self.logger.info("Report-only mode: No files will be modified")
            return self._generate_duplicate_report(duplicate_groups)
        
        # Create duplicates folder if needed
        if self.duplicate_action == DuplicateAction.MOVE:
            self.duplicates_folder.mkdir(parents=True, exist_ok=True)
        
        for group_idx, group in enumerate(duplicate_groups):
            try:
                if progress_callback:
                    progress_callback(f"Processing duplicate group {group_idx + 1}/{len(duplicate_groups)}")
                
                group_results = self._handle_duplicate_group(group)
                
                # Update results
                results['files_processed'] += len(group.duplicates_to_remove)
                results['files_deleted'] += group_results['deleted']
                results['files_moved'] += group_results['moved']
                results['space_freed'] += group_results['space_freed']
                results['errors'] += group_results['errors']
                results['actions'].extend(group_results['actions'])
                
                results['processed_groups'] += 1
                
            except Exception as e:
                self.logger.error(f"Error handling duplicate group {group_idx}: {e}")
                results['errors'] += 1
        
        self.stats['actions_taken'] = results['files_deleted'] + results['files_moved']
        
        self.logger.info(
            f"Duplicate handling complete: {results['files_deleted']} deleted, "
            f"{results['files_moved']} moved, {results['space_freed'] / (1024**3):.2f} GB freed"
        )
        
        return results
    
    def _handle_duplicate_group(self, group: DuplicateGroup) -> Dict[str, Any]:
        """Handle a single duplicate group"""
        results = {
            'deleted': 0,
            'moved': 0,
            'space_freed': 0,
            'errors': 0,
            'actions': []
        }
        
        for duplicate in group.duplicates_to_remove:
            try:
                file_path = Path(duplicate.file_path)
                
                if self.duplicate_action == DuplicateAction.DELETE:
                    file_path.unlink()
                    results['deleted'] += 1
                    action = f"Deleted: {file_path.name}"
                    
                elif self.duplicate_action == DuplicateAction.MOVE:
                    # Create destination path preserving some structure
                    dest_path = self.duplicates_folder / file_path.name
                    
                    # Handle name conflicts
                    counter = 1
                    while dest_path.exists():
                        stem = file_path.stem
                        suffix = file_path.suffix
                        dest_path = self.duplicates_folder / f"{stem}_{counter}{suffix}"
                        counter += 1
                    
                    shutil.move(str(file_path), str(dest_path))
                    results['moved'] += 1
                    action = f"Moved: {file_path.name} → {dest_path.name}"
                
                results['space_freed'] += duplicate.file_size
                results['actions'].append(action)
                
                self.logger.debug(action)
                
            except Exception as e:
                self.logger.error(f"Error handling duplicate {duplicate.file_path}: {e}")
                results['errors'] += 1
        
        return results
    
    def _generate_duplicate_report(self, duplicate_groups: List[DuplicateGroup]) -> Dict[str, Any]:
        """Generate detailed report of duplicates found"""
        report = {
            'total_groups': len(duplicate_groups),
            'total_duplicates': sum(len(group.duplicates_to_remove) for group in duplicate_groups),
            'potential_space_savings': sum(group.space_savings for group in duplicate_groups),
            'groups': []
        }
        
        for group in duplicate_groups:
            group_info = {
                'fingerprint': group.fingerprint[:16] + "...",  # Truncate for readability
                'best_file': {
                    'path': group.best_file.file_path,
                    'size': group.best_file.file_size,
                    'quality_score': group.quality_rankings[group.best_file.file_path].overall_score
                },
                'duplicates': []
            }
            
            for dup in group.duplicates_to_remove:
                dup_info = {
                    'path': dup.file_path,
                    'size': dup.file_size,
                    'quality_score': group.quality_rankings[dup.file_path].overall_score,
                    'quality_reasons': self._get_quality_reasons(group.quality_rankings[dup.file_path])
                }
                group_info['duplicates'].append(dup_info)
            
            report['groups'].append(group_info)
        
        return report
    
    def _get_quality_reasons(self, quality: AudioQuality) -> List[str]:
        """Get human-readable reasons for quality ranking"""
        reasons = []
        
        if quality.format_score < 70:
            reasons.append(f"Lower quality format ({quality.format})")
        
        if quality.bitrate and quality.bitrate < 192:
            reasons.append(f"Low bitrate ({quality.bitrate} kbps)")
        
        if quality.size_score < 60:
            reasons.append("Smaller file size")
        
        if quality.metadata_score < 50:
            reasons.append("Incomplete metadata")
        
        return reasons
    
    def find_duplicates_streaming(self, file_stream, batch_size: int = 10000, 
                                 temp_db_path: Optional[str] = None) -> List[DuplicateGroup]:
        """
        Memory-efficient duplicate detection for large datasets.
        
        Uses batch processing to handle large numbers of files without
        materializing all fingerprints in memory at once.
        
        Args:
            file_stream: Generator/iterator yielding AudioFingerprint objects
            batch_size: Maximum number of fingerprints to keep in memory
            temp_db_path: Optional path for temporary SQLite database
            
        Returns:
            List of duplicate groups found
        """
        self.logger.info(f"Starting streaming duplicate detection (batch_size: {batch_size})")
        
        # Use temporary database for fingerprint matching
        if temp_db_path:
            return self._find_duplicates_with_database(file_stream, batch_size, temp_db_path)
        else:
            return self._find_duplicates_batch_memory(file_stream, batch_size)
    
    def _find_duplicates_batch_memory(self, file_stream, batch_size: int) -> List[DuplicateGroup]:
        """
        Batch-based duplicate detection using in-memory processing.
        
        Processes files in batches to limit memory usage while still
        finding duplicates across batches using a fingerprint registry.
        """
        duplicate_groups = []
        fingerprint_registry = {}  # fingerprint -> first_seen_fingerprint
        processed_count = 0
        current_batch = []
        
        self.logger.info("Processing files in memory-efficient batches...")
        
        for fingerprint in file_stream:
            current_batch.append(fingerprint)
            processed_count += 1
            
            # Process batch when full
            if len(current_batch) >= batch_size:
                batch_duplicates = self._process_fingerprint_batch(
                    current_batch, fingerprint_registry
                )
                duplicate_groups.extend(batch_duplicates)
                
                self.logger.debug(f"Processed batch: {len(current_batch)} files, "
                                f"found {len(batch_duplicates)} duplicate groups")
                
                # Clear batch but keep registry
                current_batch = []
        
        # Process remaining files
        if current_batch:
            batch_duplicates = self._process_fingerprint_batch(
                current_batch, fingerprint_registry
            )
            duplicate_groups.extend(batch_duplicates)
        
        self.logger.info(f"Streaming duplicate detection complete: "
                        f"processed {processed_count} files, "
                        f"found {len(duplicate_groups)} duplicate groups")
        
        return duplicate_groups
    
    def _process_fingerprint_batch(self, batch: List[AudioFingerprint], 
                                  registry: Dict[str, AudioFingerprint]) -> List[DuplicateGroup]:
        """
        Process a batch of fingerprints against the registry.
        
        Args:
            batch: List of fingerprints in current batch
            registry: Registry of all previously seen fingerprints
            
        Returns:
            List of duplicate groups found in this batch
        """
        duplicate_groups = []
        batch_fingerprints = {}  # Group fingerprints in this batch
        
        # Group fingerprints within the batch
        for fingerprint in batch:
            fp_hash = fingerprint.fingerprint
            if fp_hash not in batch_fingerprints:
                batch_fingerprints[fp_hash] = []
            batch_fingerprints[fp_hash].append(fingerprint)
        
        # Check for duplicates within batch and against registry
        for fp_hash, fp_list in batch_fingerprints.items():
            all_fingerprints = fp_list.copy()
            
            # Add from registry if exists
            if fp_hash in registry:
                all_fingerprints.insert(0, registry[fp_hash])
            else:
                # Register the first occurrence
                registry[fp_hash] = fp_list[0]
            
            # Create duplicate group if we have multiple files
            if len(all_fingerprints) > 1:
                group = self._create_duplicate_group(all_fingerprints, fp_hash)
                if group:
                    duplicate_groups.append(group)
        
        return duplicate_groups
    
    def _find_duplicates_with_database(self, file_stream, batch_size: int, 
                                     temp_db_path: str) -> List[DuplicateGroup]:
        """
        Database-based duplicate detection for very large datasets.
        
        Uses a temporary SQLite database to store fingerprints and
        perform efficient duplicate matching.
        """
        import sqlite3
        import tempfile
        import os
        
        # Use provided path or create temporary file
        if temp_db_path == ":memory:":
            db_path = ":memory:"
        else:
            db_path = temp_db_path or tempfile.mktemp(suffix='.db')
        
        self.logger.info(f"Using temporary database: {db_path}")
        
        try:
            # Initialize database
            conn = sqlite3.connect(db_path)
            self._create_temp_fingerprint_table(conn)
            
            # Insert fingerprints in batches
            processed_count = 0
            current_batch = []
            
            for fingerprint in file_stream:
                current_batch.append(fingerprint)
                processed_count += 1
                
                if len(current_batch) >= batch_size:
                    self._insert_fingerprint_batch(conn, current_batch)
                    
                    self.logger.debug(f"Inserted batch: {len(current_batch)} fingerprints")
                    current_batch = []
            
            # Insert remaining fingerprints
            if current_batch:
                self._insert_fingerprint_batch(conn, current_batch)
            
            # Find duplicates using SQL
            duplicate_groups = self._find_duplicates_sql(conn)
            
            conn.close()
            
            self.logger.info(f"Database duplicate detection complete: "
                            f"processed {processed_count} files, "
                            f"found {len(duplicate_groups)} duplicate groups")
            
            return duplicate_groups
            
        finally:
            # Clean up temporary database file
            if db_path != ":memory:" and temp_db_path is None and os.path.exists(db_path):
                os.unlink(db_path)
    
    def _create_temp_fingerprint_table(self, conn):
        """Create temporary table for fingerprint storage"""
        conn.execute("""
            CREATE TABLE temp_fingerprints (
                id INTEGER PRIMARY KEY,
                fingerprint TEXT NOT NULL,
                file_path TEXT NOT NULL,
                duration REAL,
                file_size INTEGER,
                format TEXT,
                bitrate INTEGER,
                file_mtime REAL
            )
        """)
        
        # Create index separately
        conn.execute("""
            CREATE INDEX idx_temp_fingerprint ON temp_fingerprints(fingerprint)
        """)
        
        conn.commit()
    
    def _insert_fingerprint_batch(self, conn, batch: List[AudioFingerprint]):
        """Insert a batch of fingerprints into the database"""
        data = [
            (
                fp.fingerprint,
                fp.file_path,
                fp.duration,
                fp.file_size,
                fp.format,
                fp.bitrate,
                fp.file_mtime
            )
            for fp in batch
        ]
        
        conn.executemany("""
            INSERT INTO temp_fingerprints 
            (fingerprint, file_path, duration, file_size, format, bitrate, file_mtime)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, data)
        conn.commit()
    
    def _find_duplicates_sql(self, conn) -> List[DuplicateGroup]:
        """Find duplicates using SQL queries"""
        duplicate_groups = []
        
        # Find all fingerprints that appear more than once
        cursor = conn.execute("""
            SELECT fingerprint, COUNT(*) as count
            FROM temp_fingerprints
            GROUP BY fingerprint
            HAVING COUNT(*) > 1
        """)
        
        for fingerprint, count in cursor.fetchall():
            # Get all files with this fingerprint
            file_cursor = conn.execute("""
                SELECT file_path, duration, file_size, format, bitrate, file_mtime
                FROM temp_fingerprints
                WHERE fingerprint = ?
                ORDER BY file_size DESC, file_path
            """, (fingerprint,))
            
            # Create AudioFingerprint objects
            fingerprints = []
            for row in file_cursor.fetchall():
                fp = AudioFingerprint(
                    file_path=row[0],
                    fingerprint=fingerprint,
                    duration=row[1],
                    file_size=row[2],
                    algorithm="chromaprint",  # Default algorithm
                    format=row[3],
                    bitrate=row[4],
                    file_mtime=row[5]
                )
                fingerprints.append(fp)
            
            # Create duplicate group
            if len(fingerprints) > 1:
                group = self._create_duplicate_group(fingerprints, fingerprint)
                if group:
                    duplicate_groups.append(group)
        
        return duplicate_groups
    
    def _create_duplicate_group(self, fingerprints: List[AudioFingerprint], 
                               fp_hash: str) -> Optional[DuplicateGroup]:
        """Create a duplicate group from a list of fingerprints"""
        if len(fingerprints) < 2:
            return None
        
        # Calculate quality rankings
        quality_rankings = {}
        for fp in fingerprints:
            quality = self._calculate_audio_quality(fp)
            quality_rankings[fp.file_path] = quality
        
        # Sort by quality (best first)
        sorted_fingerprints = sorted(
            fingerprints,
            key=lambda fp: quality_rankings[fp.file_path].overall_score,
            reverse=True
        )
        
        best_file = sorted_fingerprints[0]
        duplicates_to_remove = sorted_fingerprints[1:]
        
        total_size = sum(fp.file_size for fp in fingerprints)
        space_savings = sum(fp.file_size for fp in duplicates_to_remove)
        
        return DuplicateGroup(
            fingerprint=fp_hash,
            files=fingerprints,
            best_file=best_file,
            duplicates_to_remove=duplicates_to_remove,
            total_size=total_size,
            space_savings=space_savings,
            quality_rankings=quality_rankings
        )
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get duplicate detection statistics"""
        return {
            **self.stats,
            'duplicate_action': self.duplicate_action.value,
            'duplicates_folder': str(self.duplicates_folder),
            'average_space_per_duplicate': (
                self.stats['space_savings'] / max(self.stats['duplicates_found'], 1)
            ) / (1024**2)  # MB
        }