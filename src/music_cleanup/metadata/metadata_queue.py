"""
Metadata Queue for DJ Music Cleanup Tool

Handles files with unknown/insufficient metadata by queueing them for manual review.
CRITICAL: This prevents "Unknown" entries from being created in the library.
"""

import logging
import json
import csv
import time
from pathlib import Path
from typing import Dict, Optional, Any, List
from dataclasses import dataclass, asdict
from datetime import datetime

from ..utils.decorators import handle_errors
from ..core.unified_database import UnifiedDatabase


@dataclass
class QueuedFile:
    """Information about a file queued for metadata review"""
    file_path: str
    original_filename: str
    file_size: int
    file_hash: Optional[str] = None
    fingerprint: Optional[str] = None
    
    # Attempted metadata extractions
    tags_result: Optional[Dict] = None
    filename_result: Optional[Dict] = None
    
    # Queue information
    queued_at: datetime = None
    reason: str = "insufficient_metadata"
    confidence_scores: Dict[str, float] = None
    
    # Possible matches (low confidence)
    possible_matches: List[Dict] = None
    
    # Manual review status
    review_status: str = "pending"  # pending, in_progress, completed, rejected
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    manual_metadata: Optional[Dict] = None

    def __post_init__(self):
        if self.queued_at is None:
            self.queued_at = datetime.now()
        if self.confidence_scores is None:
            self.confidence_scores = {}
        if self.possible_matches is None:
            self.possible_matches = []


class MetadataQueue:
    """
    Metadata Queue for handling files with unknown/insufficient metadata.
    
    Features:
    - Files are moved to metadata_queue/ directory
    - metadata_issues.json tracks all queued files
    - CSV export for bulk editing
    - Re-import functionality for processed metadata
    - Database integration for tracking
    """
    
    def __init__(self, output_directories: Dict[str, str]):
        """
        Initialize metadata queue system.
        
        Args:
            output_directories: Configuration for output directories
        """
        self.logger = logging.getLogger(__name__)
        
        # Setup directories
        self.base_dir = Path(output_directories.get('base_directory', './output'))
        self.queue_dir = self.base_dir / 'metadata_queue'
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        
        # Database for tracking
        self.db = UnifiedDatabase()
        
        # Files for tracking queued items
        self.issues_file = self.queue_dir / 'metadata_issues.json'
        self.export_file = self.queue_dir / 'metadata_export.csv'
        self.import_file = self.queue_dir / 'metadata_import.csv'
        
        # Load existing queue
        self.queued_files = self._load_queue()
        
        # Stats
        self.stats = {
            'total_queued': 0,
            'pending_review': 0,
            'completed_review': 0,
            'rejected': 0
        }
        
        self._update_stats()
        
        self.logger.info(f"MetadataQueue initialized: {len(self.queued_files)} files in queue")
    
    @handle_errors(log_level="error")
    def queue_file(self, file_path: Path, fingerprint_data: Optional[str] = None, 
                   tags_result: Optional[Dict] = None, filename_result: Optional[Dict] = None) -> bool:
        """
        Queue a file for manual metadata review.
        
        Args:
            file_path: Original file path
            fingerprint_data: Audio fingerprint if available
            tags_result: Metadata from file tags
            filename_result: Metadata from filename parsing
            
        Returns:
            True if successfully queued
        """
        try:
            # Calculate file hash for identification
            file_hash = self._calculate_file_hash(file_path)
            
            # Check if already queued
            if file_hash in self.queued_files:
                self.logger.debug(f"File already queued: {file_path.name}")
                return True
            
            # Create new queue directory for this file
            queue_subdir = self.queue_dir / f"queued_{int(time.time())}"
            queue_subdir.mkdir(exist_ok=True)
            
            # Move file to queue directory
            new_file_path = queue_subdir / file_path.name
            
            # Copy file to queue (don't move original yet)
            import shutil
            shutil.copy2(file_path, new_file_path)
            
            # Determine reason for queueing
            reason = self._determine_queue_reason(fingerprint_data, tags_result, filename_result)
            
            # Create queued file entry
            queued_file = QueuedFile(
                file_path=str(file_path),
                original_filename=file_path.name,
                file_size=file_path.stat().st_size,
                file_hash=file_hash,
                fingerprint=fingerprint_data,
                tags_result=tags_result,
                filename_result=filename_result,
                reason=reason,
                confidence_scores=self._extract_confidence_scores(tags_result, filename_result),
                possible_matches=self._extract_possible_matches(tags_result, filename_result)
            )
            
            # Store in queue
            self.queued_files[file_hash] = queued_file
            
            # Save to database
            self._save_to_database(queued_file)
            
            # Update JSON file
            self._save_queue()
            
            # Update stats
            self.stats['total_queued'] += 1
            self.stats['pending_review'] += 1
            
            self.logger.info(f"📋 Queued file: {file_path.name} (reason: {reason})")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to queue file {file_path}: {e}")
            return False
    
    def _determine_queue_reason(self, fingerprint_data: Optional[str], 
                               tags_result: Optional[Dict], filename_result: Optional[Dict]) -> str:
        """Determine why file was queued"""
        reasons = []
        
        if not fingerprint_data:
            reasons.append("no_fingerprint")
        
        if not tags_result or not tags_result.get('artist') or not tags_result.get('title'):
            reasons.append("insufficient_tags")
        
        if not filename_result or not filename_result.get('artist') or not filename_result.get('title'):
            reasons.append("filename_parsing_failed")
        
        if fingerprint_data and tags_result and filename_result:
            # All methods tried but confidence too low
            reasons.append("low_confidence")
        
        return ", ".join(reasons) if reasons else "unknown"
    
    def _extract_confidence_scores(self, tags_result: Optional[Dict], 
                                  filename_result: Optional[Dict]) -> Dict[str, float]:
        """Extract confidence scores from attempted metadata extractions"""
        scores = {}
        
        if tags_result and 'confidence' in tags_result:
            scores['tags'] = tags_result['confidence']
        
        if filename_result and 'confidence' in filename_result:
            scores['filename'] = filename_result['confidence']
        
        return scores
    
    def _extract_possible_matches(self, tags_result: Optional[Dict], 
                                 filename_result: Optional[Dict]) -> List[Dict]:
        """Extract possible matches from attempted metadata extractions"""
        matches = []
        
        if tags_result and tags_result.get('artist') and tags_result.get('title'):
            matches.append({
                'source': 'tags',
                'artist': tags_result['artist'],
                'title': tags_result['title'],
                'confidence': tags_result.get('confidence', 0.0)
            })
        
        if filename_result and filename_result.get('artist') and filename_result.get('title'):
            matches.append({
                'source': 'filename',
                'artist': filename_result['artist'],
                'title': filename_result['title'],
                'confidence': filename_result.get('confidence', 0.0)
            })
        
        return matches
    
    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash for file identification"""
        import hashlib
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    
    def _save_to_database(self, queued_file: QueuedFile) -> None:
        """Save queued file to database"""
        try:
            self.db.store_queued_file(asdict(queued_file))
        except Exception as e:
            self.logger.error(f"Database save error: {e}")
    
    def _load_queue(self) -> Dict[str, QueuedFile]:
        """Load existing queue from JSON file"""
        if not self.issues_file.exists():
            return {}
        
        try:
            with open(self.issues_file, 'r') as f:
                data = json.load(f)
            
            queued_files = {}
            for entry in data.get('queued_files', []):
                # Convert datetime strings back to datetime objects
                if 'queued_at' in entry:
                    entry['queued_at'] = datetime.fromisoformat(entry['queued_at'])
                if 'reviewed_at' in entry and entry['reviewed_at']:
                    entry['reviewed_at'] = datetime.fromisoformat(entry['reviewed_at'])
                
                queued_file = QueuedFile(**entry)
                queued_files[queued_file.file_hash] = queued_file
            
            return queued_files
            
        except Exception as e:
            self.logger.error(f"Failed to load queue: {e}")
            return {}
    
    def _save_queue(self) -> None:
        """Save current queue to JSON file"""
        try:
            # Convert to JSON-serializable format
            data = {
                'metadata': {
                    'created_at': datetime.now().isoformat(),
                    'total_files': len(self.queued_files),
                    'version': '2.0'
                },
                'queued_files': []
            }
            
            for queued_file in self.queued_files.values():
                entry = asdict(queued_file)
                # Convert datetime objects to strings
                if entry['queued_at']:
                    entry['queued_at'] = entry['queued_at'].isoformat()
                if entry['reviewed_at']:
                    entry['reviewed_at'] = entry['reviewed_at'].isoformat()
                data['queued_files'].append(entry)
            
            # Save to JSON file
            with open(self.issues_file, 'w') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            self.logger.debug(f"Saved queue: {len(self.queued_files)} files")
            
        except Exception as e:
            self.logger.error(f"Failed to save queue: {e}")
    
    def _update_stats(self) -> None:
        """Update statistics from current queue"""
        self.stats = {
            'total_queued': len(self.queued_files),
            'pending_review': 0,
            'completed_review': 0,
            'rejected': 0
        }
        
        for queued_file in self.queued_files.values():
            if queued_file.review_status == 'pending':
                self.stats['pending_review'] += 1
            elif queued_file.review_status == 'completed':
                self.stats['completed_review'] += 1
            elif queued_file.review_status == 'rejected':
                self.stats['rejected'] += 1
    
    def export_to_csv(self, output_file: Optional[Path] = None) -> Path:
        """
        Export queued files to CSV for bulk editing.
        
        Args:
            output_file: Optional output file path
            
        Returns:
            Path to created CSV file
        """
        if output_file is None:
            output_file = self.export_file
        
        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                # Write header
                writer.writerow([
                    'file_hash', 'original_filename', 'file_path', 'reason',
                    'tags_artist', 'tags_title', 'tags_confidence',
                    'filename_artist', 'filename_title', 'filename_confidence',
                    'suggested_artist', 'suggested_title', 'suggested_year', 'suggested_genre',
                    'review_status', 'notes'
                ])
                
                # Write data
                for queued_file in self.queued_files.values():
                    tags_result = queued_file.tags_result or {}
                    filename_result = queued_file.filename_result or {}
                    
                    writer.writerow([
                        queued_file.file_hash,
                        queued_file.original_filename,
                        queued_file.file_path,
                        queued_file.reason,
                        tags_result.get('artist', ''),
                        tags_result.get('title', ''),
                        tags_result.get('confidence', ''),
                        filename_result.get('artist', ''),
                        filename_result.get('title', ''),
                        filename_result.get('confidence', ''),
                        '',  # suggested_artist (for manual entry)
                        '',  # suggested_title (for manual entry)
                        '',  # suggested_year (for manual entry)
                        '',  # suggested_genre (for manual entry)
                        queued_file.review_status,
                        ''   # notes (for manual entry)
                    ])
            
            self.logger.info(f"Exported {len(self.queued_files)} files to CSV: {output_file}")
            return output_file
            
        except Exception as e:
            self.logger.error(f"CSV export failed: {e}")
            raise
    
    def import_from_csv(self, input_file: Optional[Path] = None) -> int:
        """
        Import processed metadata from CSV file.
        
        Args:
            input_file: Optional input file path
            
        Returns:
            Number of files updated
        """
        if input_file is None:
            input_file = self.import_file
        
        if not input_file.exists():
            self.logger.warning(f"Import file not found: {input_file}")
            return 0
        
        updated_count = 0
        
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    file_hash = row.get('file_hash')
                    if not file_hash or file_hash not in self.queued_files:
                        continue
                    
                    # Extract manual metadata
                    suggested_artist = row.get('suggested_artist', '').strip()
                    suggested_title = row.get('suggested_title', '').strip()
                    suggested_year = row.get('suggested_year', '').strip()
                    suggested_genre = row.get('suggested_genre', '').strip()
                    review_status = row.get('review_status', 'pending').strip()
                    
                    # Only process if we have artist and title
                    if suggested_artist and suggested_title:
                        queued_file = self.queued_files[file_hash]
                        
                        # Update manual metadata
                        queued_file.manual_metadata = {
                            'artist': suggested_artist,
                            'title': suggested_title,
                            'year': suggested_year or '0000',
                            'genre': suggested_genre or 'Unknown Genre',
                            'source': 'manual',
                            'confidence': 1.0
                        }
                        
                        # Update review status
                        queued_file.review_status = review_status
                        queued_file.reviewed_at = datetime.now()
                        
                        # Update in database
                        self._save_to_database(queued_file)
                        
                        updated_count += 1
                        
                        self.logger.debug(f"Updated metadata for: {queued_file.original_filename}")
            
            # Save updated queue
            self._save_queue()
            self._update_stats()
            
            self.logger.info(f"Imported metadata for {updated_count} files")
            return updated_count
            
        except Exception as e:
            self.logger.error(f"CSV import failed: {e}")
            return 0
    
    def get_completed_files(self) -> List[QueuedFile]:
        """
        Get files that have been manually reviewed and completed.
        
        Returns:
            List of completed QueuedFile objects
        """
        return [qf for qf in self.queued_files.values() 
                if qf.review_status == 'completed' and qf.manual_metadata]
    
    def remove_completed_files(self) -> int:
        """
        Remove completed files from queue.
        
        Returns:
            Number of files removed
        """
        to_remove = []
        
        for file_hash, queued_file in self.queued_files.items():
            if queued_file.review_status == 'completed':
                to_remove.append(file_hash)
        
        # Remove from queue
        for file_hash in to_remove:
            del self.queued_files[file_hash]
        
        # Save updated queue
        self._save_queue()
        self._update_stats()
        
        self.logger.info(f"Removed {len(to_remove)} completed files from queue")
        return len(to_remove)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics"""
        self._update_stats()
        return self.stats.copy()
    
    def clear_queue(self, confirmed: bool = False) -> int:
        """
        Clear entire queue (use with caution).
        
        Args:
            confirmed: Must be True to actually clear
            
        Returns:
            Number of files cleared
        """
        if not confirmed:
            self.logger.warning("clear_queue called without confirmation")
            return 0
        
        count = len(self.queued_files)
        self.queued_files.clear()
        self._save_queue()
        self._update_stats()
        
        self.logger.warning(f"Cleared entire queue: {count} files")
        return count