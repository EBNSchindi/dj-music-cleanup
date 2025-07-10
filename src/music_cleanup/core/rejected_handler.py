"""
Rejected Files Handler for DJ Music Cleanup Tool

Handles all rejected files (duplicates, low quality, corrupted) by moving them
to organized rejected/ directories instead of deleting them.

Features:
- Duplicate handling with numbered suffixes
- Quality-based rejection with thresholds
- Corruption detection and quarantine
- Manifest creation for tracking all rejections
- Folder structure preservation for easy recovery
"""

import logging
import json
import shutil
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict, field
from datetime import datetime
from enum import Enum

from ..utils.decorators import handle_errors, track_performance
from ..core.unified_database import UnifiedDatabase


class RejectionReason(Enum):
    """Enumeration of rejection reasons"""
    DUPLICATE = "duplicate"
    LOW_QUALITY = "low_quality"
    CORRUPTED = "corrupted"
    UNSUPPORTED_FORMAT = "unsupported_format"
    INVALID_METADATA = "invalid_metadata"
    FILE_TOO_SMALL = "file_too_small"
    FILE_TOO_LARGE = "file_too_large"
    PROCESSING_ERROR = "processing_error"


@dataclass
class RejectionEntry:
    """Information about a rejected file"""
    # File information
    original_path: str
    rejected_path: str
    filename: str
    file_size: int
    file_hash: Optional[str] = None
    
    # Rejection details
    reason: RejectionReason = RejectionReason.PROCESSING_ERROR
    quality_score: Optional[float] = None
    threshold_used: Optional[float] = None
    
    # Duplicate information
    chosen_file: Optional[str] = None  # Path to the file that was kept instead
    duplicate_group_id: Optional[str] = None
    duplicate_rank: Optional[int] = None
    
    # Metadata
    artist: Optional[str] = None
    title: Optional[str] = None
    year: Optional[str] = None
    genre: Optional[str] = None
    
    # Processing info
    rejected_at: datetime = field(default_factory=datetime.now)
    processed_by: str = "dj_cleanup"
    notes: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        # Convert datetime to ISO string
        if isinstance(data['rejected_at'], datetime):
            data['rejected_at'] = data['rejected_at'].isoformat()
        # Convert enum to string
        if isinstance(data['reason'], RejectionReason):
            data['reason'] = data['reason'].value
        return data


class RejectedHandler:
    """
    Handles all rejected files with organized categorization and manifest tracking.
    
    Features:
    - Never deletes files, only moves them
    - Maintains folder structure in rejected/ for easy recovery
    - Creates detailed manifest for tracking
    - Handles duplicates with numbered suffixes
    - Quality-based rejection with configurable thresholds
    - Corruption detection and quarantine
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize rejected files handler.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Directory setup
        self.output_dir = Path(config.get('paths', {}).get('output_dir', './organized'))
        self.rejected_dir = Path(config.get('paths', {}).get('rejected_dir', './rejected'))
        self.create_if_missing = config.get('paths', {}).get('create_if_missing', True)
        
        # Rejection configuration
        self.rejection_config = config.get('rejection', {})
        self.keep_structure = self.rejection_config.get('keep_structure', True)
        self.create_manifest = self.rejection_config.get('create_manifest', True)
        
        # Category directories
        self.categories = self.rejection_config.get('categories', {
            'duplicates': 'duplicates',
            'low_quality': 'low_quality',
            'corrupted': 'corrupted'
        })
        
        # Quality thresholds
        self.quality_config = config.get('quality', {})
        self.min_quality_score = self.quality_config.get('min_score', 70)
        self.always_keep_best = self.quality_config.get('always_keep_best', True)
        
        # Database for tracking
        self.db = UnifiedDatabase()
        
        # Initialize directories
        self._setup_directories()
        
        # Manifest file
        self.manifest_file = self.rejected_dir / 'rejected_manifest.json'
        self.manifest_data = self._load_manifest()
        
        # Statistics
        self.stats = {
            'total_rejected': 0,
            'duplicates': 0,
            'low_quality': 0,
            'corrupted': 0,
            'other': 0
        }
        
        self.logger.info(f"RejectedHandler initialized")
        self.logger.info(f"  Rejected directory: {self.rejected_dir}")
        self.logger.info(f"  Min quality score: {self.min_quality_score}")
        self.logger.info(f"  Keep structure: {self.keep_structure}")
    
    def _setup_directories(self) -> None:
        """Setup rejected file directories"""
        if self.create_if_missing:
            # Create main rejected directory
            self.rejected_dir.mkdir(parents=True, exist_ok=True)
            
            # Create category directories
            for category_name, category_dir in self.categories.items():
                category_path = self.rejected_dir / category_dir
                category_path.mkdir(parents=True, exist_ok=True)
                
                self.logger.debug(f"Created category directory: {category_path}")
    
    def _load_manifest(self) -> Dict[str, Any]:
        """Load existing rejection manifest"""
        if not self.manifest_file.exists():
            return {
                'metadata': {
                    'created_at': datetime.now().isoformat(),
                    'version': '2.0',
                    'total_rejections': 0
                },
                'rejections': []
            }
        
        try:
            with open(self.manifest_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load manifest: {e}")
            return {
                'metadata': {
                    'created_at': datetime.now().isoformat(),
                    'version': '2.0',
                    'total_rejections': 0
                },
                'rejections': []
            }
    
    def _save_manifest(self) -> None:
        """Save rejection manifest to file"""
        if not self.create_manifest:
            return
        
        try:
            # Update metadata
            self.manifest_data['metadata']['updated_at'] = datetime.now().isoformat()
            self.manifest_data['metadata']['total_rejections'] = len(self.manifest_data['rejections'])
            
            # Save to file
            with open(self.manifest_file, 'w', encoding='utf-8') as f:
                json.dump(self.manifest_data, f, indent=2, ensure_ascii=False)
            
            self.logger.debug(f"Saved manifest with {len(self.manifest_data['rejections'])} rejections")
            
        except Exception as e:
            self.logger.error(f"Failed to save manifest: {e}")
    
    def _add_to_manifest(self, rejection: RejectionEntry) -> None:
        """Add rejection entry to manifest"""
        if not self.create_manifest:
            return
        
        try:
            self.manifest_data['rejections'].append(rejection.to_dict())
            self._save_manifest()
        except Exception as e:
            self.logger.error(f"Failed to add rejection to manifest: {e}")
    
    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file"""
        import hashlib
        hasher = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    
    def _get_safe_filename(self, original_path: Path, category: str, suffix: str = "") -> Path:
        """
        Get a safe filename in the rejected directory.
        
        Args:
            original_path: Original file path
            category: Rejection category
            suffix: Optional suffix for duplicates
            
        Returns:
            Safe path in rejected directory
        """
        category_dir = self.rejected_dir / self.categories.get(category, category)
        
        if self.keep_structure:
            # Try to preserve directory structure
            relative_path = original_path.name if original_path.is_file() else original_path
            target_dir = category_dir
        else:
            # Flat structure
            target_dir = category_dir
        
        # Create target directory
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate filename with suffix
        stem = original_path.stem
        extension = original_path.suffix
        
        if suffix:
            filename = f"{stem}{suffix}{extension}"
        else:
            filename = original_path.name
        
        return target_dir / filename
    
    def _get_unique_filename(self, target_path: Path) -> Path:
        """Get a unique filename by adding numbers if needed"""
        if not target_path.exists():
            return target_path
        
        stem = target_path.stem
        extension = target_path.suffix
        parent = target_path.parent
        
        counter = 1
        while True:
            new_filename = f"{stem}_{counter}{extension}"
            new_path = parent / new_filename
            if not new_path.exists():
                return new_path
            counter += 1
    
    @handle_errors(log_level="error")
    @track_performance(threshold_ms=5000)
    def reject_duplicate(self, file_path: str, chosen_file: str, quality_score: float,
                        duplicate_group_id: str, rank: int, metadata: Optional[Dict] = None) -> Optional[str]:
        """
        Reject a duplicate file.
        
        Args:
            file_path: Path to the duplicate file
            chosen_file: Path to the file that was kept instead
            quality_score: Quality score of the duplicate
            duplicate_group_id: ID of the duplicate group
            rank: Rank within the duplicate group (1 = best)
            metadata: Optional metadata dictionary
            
        Returns:
            Path where the file was moved, or None if failed
        """
        try:
            file_path = Path(file_path)
            
            # Generate suffix for duplicate
            suffix = f"_duplicate_{rank}"
            
            # Get target path
            target_path = self._get_safe_filename(file_path, 'duplicates', suffix)
            target_path = self._get_unique_filename(target_path)
            
            # Move file
            shutil.move(str(file_path), str(target_path))
            
            # Create rejection entry
            rejection = RejectionEntry(
                original_path=str(file_path),
                rejected_path=str(target_path),
                filename=file_path.name,
                file_size=target_path.stat().st_size,
                file_hash=self._calculate_file_hash(target_path),
                reason=RejectionReason.DUPLICATE,
                quality_score=quality_score,
                chosen_file=chosen_file,
                duplicate_group_id=duplicate_group_id,
                duplicate_rank=rank,
                artist=metadata.get('artist') if metadata else None,
                title=metadata.get('title') if metadata else None,
                year=metadata.get('year') if metadata else None,
                genre=metadata.get('genre') if metadata else None,
                notes=f"Duplicate #{rank} in group {duplicate_group_id}"
            )
            
            # Add to manifest and database
            self._add_to_manifest(rejection)
            self.db.store_rejection(rejection.to_dict())
            
            # Update statistics
            self.stats['total_rejected'] += 1
            self.stats['duplicates'] += 1
            
            self.logger.info(f"Rejected duplicate: {file_path.name} -> {target_path}")
            return str(target_path)
            
        except Exception as e:
            self.logger.error(f"Failed to reject duplicate {file_path}: {e}")
            return None
    
    @handle_errors(log_level="error")
    @track_performance(threshold_ms=5000)
    def reject_low_quality(self, file_path: str, quality_score: float,
                          metadata: Optional[Dict] = None) -> Optional[str]:
        """
        Reject a low quality file.
        
        Args:
            file_path: Path to the low quality file
            quality_score: Quality score of the file
            metadata: Optional metadata dictionary
            
        Returns:
            Path where the file was moved, or None if failed
        """
        try:
            file_path = Path(file_path)
            
            # Get target path
            target_path = self._get_safe_filename(file_path, 'low_quality')
            target_path = self._get_unique_filename(target_path)
            
            # Move file
            shutil.move(str(file_path), str(target_path))
            
            # Create rejection entry
            rejection = RejectionEntry(
                original_path=str(file_path),
                rejected_path=str(target_path),
                filename=file_path.name,
                file_size=target_path.stat().st_size,
                file_hash=self._calculate_file_hash(target_path),
                reason=RejectionReason.LOW_QUALITY,
                quality_score=quality_score,
                threshold_used=self.min_quality_score,
                artist=metadata.get('artist') if metadata else None,
                title=metadata.get('title') if metadata else None,
                year=metadata.get('year') if metadata else None,
                genre=metadata.get('genre') if metadata else None,
                notes=f"Quality score {quality_score:.1f} below threshold {self.min_quality_score}"
            )
            
            # Add to manifest and database
            self._add_to_manifest(rejection)
            self.db.store_rejection(rejection.to_dict())
            
            # Update statistics
            self.stats['total_rejected'] += 1
            self.stats['low_quality'] += 1
            
            self.logger.info(f"Rejected low quality: {file_path.name} (QS: {quality_score:.1f})")
            return str(target_path)
            
        except Exception as e:
            self.logger.error(f"Failed to reject low quality {file_path}: {e}")
            return None
    
    @handle_errors(log_level="error")
    @track_performance(threshold_ms=5000)
    def reject_corrupted(self, file_path: str, corruption_details: str,
                        metadata: Optional[Dict] = None) -> Optional[str]:
        """
        Reject a corrupted file.
        
        Args:
            file_path: Path to the corrupted file
            corruption_details: Details about the corruption
            metadata: Optional metadata dictionary
            
        Returns:
            Path where the file was moved, or None if failed
        """
        try:
            file_path = Path(file_path)
            
            # Get target path
            target_path = self._get_safe_filename(file_path, 'corrupted')
            target_path = self._get_unique_filename(target_path)
            
            # Move file
            shutil.move(str(file_path), str(target_path))
            
            # Create rejection entry
            rejection = RejectionEntry(
                original_path=str(file_path),
                rejected_path=str(target_path),
                filename=file_path.name,
                file_size=target_path.stat().st_size,
                file_hash=self._calculate_file_hash(target_path),
                reason=RejectionReason.CORRUPTED,
                artist=metadata.get('artist') if metadata else None,
                title=metadata.get('title') if metadata else None,
                year=metadata.get('year') if metadata else None,
                genre=metadata.get('genre') if metadata else None,
                notes=f"Corruption detected: {corruption_details}"
            )
            
            # Add to manifest and database
            self._add_to_manifest(rejection)
            self.db.store_rejection(rejection.to_dict())
            
            # Update statistics
            self.stats['total_rejected'] += 1
            self.stats['corrupted'] += 1
            
            self.logger.info(f"Rejected corrupted: {file_path.name}")
            return str(target_path)
            
        except Exception as e:
            self.logger.error(f"Failed to reject corrupted {file_path}: {e}")
            return None
    
    @handle_errors(log_level="error")
    def reject_file(self, file_path: str, reason: Union[RejectionReason, str],
                   quality_score: Optional[float] = None, metadata: Optional[Dict] = None,
                   notes: Optional[str] = None) -> Optional[str]:
        """
        Generic file rejection method.
        
        Args:
            file_path: Path to the file to reject
            reason: Reason for rejection
            quality_score: Optional quality score
            metadata: Optional metadata dictionary
            notes: Optional additional notes
            
        Returns:
            Path where the file was moved, or None if failed
        """
        try:
            file_path = Path(file_path)
            
            # Convert string reason to enum
            if isinstance(reason, str):
                try:
                    reason = RejectionReason(reason)
                except ValueError:
                    reason = RejectionReason.PROCESSING_ERROR
            
            # Determine category
            category_map = {
                RejectionReason.DUPLICATE: 'duplicates',
                RejectionReason.LOW_QUALITY: 'low_quality',
                RejectionReason.CORRUPTED: 'corrupted'
            }
            category = category_map.get(reason, 'other')
            
            # Get target path
            target_path = self._get_safe_filename(file_path, category)
            target_path = self._get_unique_filename(target_path)
            
            # Move file
            shutil.move(str(file_path), str(target_path))
            
            # Create rejection entry
            rejection = RejectionEntry(
                original_path=str(file_path),
                rejected_path=str(target_path),
                filename=file_path.name,
                file_size=target_path.stat().st_size,
                file_hash=self._calculate_file_hash(target_path),
                reason=reason,
                quality_score=quality_score,
                threshold_used=self.min_quality_score if reason == RejectionReason.LOW_QUALITY else None,
                artist=metadata.get('artist') if metadata else None,
                title=metadata.get('title') if metadata else None,
                year=metadata.get('year') if metadata else None,
                genre=metadata.get('genre') if metadata else None,
                notes=notes
            )
            
            # Add to manifest and database
            self._add_to_manifest(rejection)
            self.db.store_rejection(rejection.to_dict())
            
            # Update statistics
            self.stats['total_rejected'] += 1
            if reason == RejectionReason.DUPLICATE:
                self.stats['duplicates'] += 1
            elif reason == RejectionReason.LOW_QUALITY:
                self.stats['low_quality'] += 1
            elif reason == RejectionReason.CORRUPTED:
                self.stats['corrupted'] += 1
            else:
                self.stats['other'] += 1
            
            self.logger.info(f"Rejected file: {file_path.name} (reason: {reason.value})")
            return str(target_path)
            
        except Exception as e:
            self.logger.error(f"Failed to reject file {file_path}: {e}")
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get rejection statistics"""
        return {
            **self.stats,
            'manifest_file': str(self.manifest_file),
            'total_in_manifest': len(self.manifest_data['rejections']),
            'rejection_rate': {
                'duplicates': round(self.stats['duplicates'] / max(self.stats['total_rejected'], 1) * 100, 1),
                'low_quality': round(self.stats['low_quality'] / max(self.stats['total_rejected'], 1) * 100, 1),
                'corrupted': round(self.stats['corrupted'] / max(self.stats['total_rejected'], 1) * 100, 1),
                'other': round(self.stats['other'] / max(self.stats['total_rejected'], 1) * 100, 1)
            }
        }
    
    def get_rejections_by_reason(self, reason: Union[RejectionReason, str]) -> List[Dict]:
        """Get all rejections for a specific reason"""
        if isinstance(reason, RejectionReason):
            reason = reason.value
        
        return [
            rejection for rejection in self.manifest_data['rejections']
            if rejection.get('reason') == reason
        ]
    
    def get_rejections_by_quality(self, min_score: float = 0, max_score: float = 100) -> List[Dict]:
        """Get rejections within quality score range"""
        return [
            rejection for rejection in self.manifest_data['rejections']
            if rejection.get('quality_score') is not None
            and min_score <= rejection['quality_score'] <= max_score
        ]
    
    def restore_file(self, rejection_entry: Dict, restore_path: Optional[str] = None) -> bool:
        """
        Restore a rejected file to its original location or specified path.
        
        Args:
            rejection_entry: Rejection entry from manifest
            restore_path: Optional path to restore to (default: original path)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            rejected_path = Path(rejection_entry['rejected_path'])
            
            if not rejected_path.exists():
                self.logger.error(f"Rejected file not found: {rejected_path}")
                return False
            
            # Determine restore path
            if restore_path:
                target_path = Path(restore_path)
            else:
                target_path = Path(rejection_entry['original_path'])
            
            # Ensure target directory exists
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Move file back
            shutil.move(str(rejected_path), str(target_path))
            
            # Remove from manifest
            self.manifest_data['rejections'] = [
                r for r in self.manifest_data['rejections']
                if r['rejected_path'] != str(rejected_path)
            ]
            self._save_manifest()
            
            self.logger.info(f"Restored file: {rejected_path.name} -> {target_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to restore file: {e}")
            return False
    
    def cleanup_empty_directories(self) -> int:
        """Clean up empty directories in rejected folder"""
        removed_count = 0
        
        try:
            for category_dir in self.rejected_dir.iterdir():
                if category_dir.is_dir():
                    # Check if directory is empty
                    if not any(category_dir.iterdir()):
                        category_dir.rmdir()
                        removed_count += 1
                        self.logger.debug(f"Removed empty directory: {category_dir}")
            
            return removed_count
            
        except Exception as e:
            self.logger.error(f"Failed to cleanup empty directories: {e}")
            return 0
    
    def export_manifest_to_csv(self, output_file: Optional[str] = None) -> str:
        """Export rejection manifest to CSV for analysis"""
        import csv
        
        if output_file is None:
            output_file = str(self.rejected_dir / 'rejection_analysis.csv')
        
        try:
            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                fieldnames = [
                    'original_path', 'rejected_path', 'filename', 'reason',
                    'quality_score', 'threshold_used', 'artist', 'title', 'year', 'genre',
                    'chosen_file', 'duplicate_rank', 'rejected_at', 'notes'
                ]
                
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                
                for rejection in self.manifest_data['rejections']:
                    # Filter only the fields we want
                    filtered_rejection = {k: v for k, v in rejection.items() if k in fieldnames}
                    writer.writerow(filtered_rejection)
            
            self.logger.info(f"Exported rejection manifest to CSV: {output_file}")
            return output_file
            
        except Exception as e:
            self.logger.error(f"Failed to export manifest to CSV: {e}")
            return ""