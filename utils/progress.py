"""
Progress tracking and reporting utilities
"""
import os
import sys
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json
from pathlib import Path
from tqdm import tqdm
import sqlite3


class ProgressTracker:
    """Track and display progress for long-running operations"""
    
    def __init__(self, total_items: int = None, desc: str = "Processing",
                 db_path: str = 'progress.db', enable_resume: bool = True):
        """Initialize progress tracker"""
        self.total_items = total_items
        self.desc = desc
        self.db_path = db_path
        self.enable_resume = enable_resume
        self.start_time = time.time()
        self.processed = 0
        self.errors = 0
        self.skipped = 0
        self.current_phase = None
        self.phase_start_time = None
        
        # Initialize progress bar
        self.pbar = None
        if total_items:
            self.pbar = tqdm(total=total_items, desc=desc, 
                           unit='files', dynamic_ncols=True)
        
        # Initialize database for resume capability
        if enable_resume:
            self._init_database()
            self._load_state()
    
    def _init_database(self):
        """Initialize database for tracking progress"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS progress_state (
                id INTEGER PRIMARY KEY,
                total_items INTEGER,
                processed INTEGER,
                errors INTEGER,
                skipped INTEGER,
                current_phase TEXT,
                last_file TEXT,
                state_data TEXT,
                updated_at TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_files (
                file_path TEXT PRIMARY KEY,
                status TEXT,
                processed_at TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def _save_state(self, last_file: str = None, state_data: Dict = None):
        """Save current state for resume capability"""
        if not self.enable_resume:
            return
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO progress_state 
            (id, total_items, processed, errors, skipped, current_phase, 
             last_file, state_data, updated_at)
            VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            self.total_items,
            self.processed,
            self.errors,
            self.skipped,
            self.current_phase,
            last_file,
            json.dumps(state_data) if state_data else None,
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
    
    def _load_state(self) -> Optional[Dict]:
        """Load saved state for resuming"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM progress_state WHERE id = 1
        ''')
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            columns = ['id', 'total_items', 'processed', 'errors', 'skipped',
                      'current_phase', 'last_file', 'state_data', 'updated_at']
            state = dict(zip(columns, row))
            
            if state['state_data']:
                state['state_data'] = json.loads(state['state_data'])
            
            return state
        
        return None
    
    def resume_from_checkpoint(self) -> Optional[Dict]:
        """Resume from last checkpoint"""
        state = self._load_state()
        
        if state:
            self.processed = state['processed']
            self.errors = state['errors']
            self.skipped = state['skipped']
            self.current_phase = state['current_phase']
            
            if self.pbar:
                self.pbar.n = self.processed
                self.pbar.refresh()
            
            return state
        
        return None
    
    def is_file_processed(self, file_path: str) -> bool:
        """Check if file was already processed"""
        if not self.enable_resume:
            return False
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT status FROM processed_files WHERE file_path = ?
        ''', (file_path,))
        
        result = cursor.fetchone()
        conn.close()
        
        return result is not None
    
    def mark_file_processed(self, file_path: str, status: str = 'success'):
        """Mark file as processed"""
        if not self.enable_resume:
            return
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO processed_files 
            (file_path, status, processed_at)
            VALUES (?, ?, ?)
        ''', (file_path, status, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
    
    def update(self, increment: int = 1, error: bool = False, 
               skip: bool = False, file_path: str = None):
        """Update progress"""
        if error:
            self.errors += increment
        elif skip:
            self.skipped += increment
        else:
            self.processed += increment
        
        if self.pbar:
            self.pbar.update(increment)
            self._update_description()
        
        # Save state periodically
        if self.enable_resume and (self.processed + self.errors + self.skipped) % 100 == 0:
            self._save_state(last_file=file_path)
        
        # Mark file as processed
        if file_path and not skip:
            status = 'error' if error else 'success'
            self.mark_file_processed(file_path, status)
    
    def _update_description(self):
        """Update progress bar description with stats"""
        if not self.pbar:
            return
        
        elapsed = time.time() - self.start_time
        rate = self.processed / elapsed if elapsed > 0 else 0
        
        desc_parts = [self.desc]
        
        if self.current_phase:
            desc_parts.append(f"[{self.current_phase}]")
        
        if self.errors > 0:
            desc_parts.append(f"Errors: {self.errors}")
        
        if self.skipped > 0:
            desc_parts.append(f"Skipped: {self.skipped}")
        
        if rate > 0 and self.total_items:
            remaining = self.total_items - (self.processed + self.errors + self.skipped)
            eta = remaining / rate if rate > 0 else 0
            desc_parts.append(f"ETA: {self._format_time(eta)}")
        
        self.pbar.set_description(" | ".join(desc_parts))
    
    def set_phase(self, phase: str):
        """Set current processing phase"""
        self.current_phase = phase
        self.phase_start_time = time.time()
        
        if self.pbar:
            self._update_description()
        
        logging.info(f"Starting phase: {phase}")
    
    def close(self):
        """Close progress bar and save final state"""
        if self.pbar:
            self.pbar.close()
        
        self._save_state()
    
    def get_stats(self) -> Dict:
        """Get current statistics"""
        elapsed = time.time() - self.start_time
        rate = self.processed / elapsed if elapsed > 0 else 0
        
        stats = {
            'processed': self.processed,
            'errors': self.errors,
            'skipped': self.skipped,
            'total': self.total_items,
            'elapsed_seconds': elapsed,
            'elapsed_formatted': self._format_time(elapsed),
            'rate_per_second': rate,
            'rate_per_minute': rate * 60,
            'current_phase': self.current_phase
        }
        
        if self.phase_start_time:
            phase_elapsed = time.time() - self.phase_start_time
            stats['phase_elapsed'] = self._format_time(phase_elapsed)
        
        if self.total_items and rate > 0:
            remaining = self.total_items - (self.processed + self.errors + self.skipped)
            eta = remaining / rate
            stats['remaining'] = remaining
            stats['eta_seconds'] = eta
            stats['eta_formatted'] = self._format_time(eta)
            stats['percent_complete'] = round(
                (self.processed + self.errors + self.skipped) / self.total_items * 100, 2
            )
        
        return stats
    
    def _format_time(self, seconds: float) -> str:
        """Format seconds into human-readable time"""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            secs = int(seconds % 60)
            return f"{minutes}m {secs}s"
        else:
            hours = int(seconds / 3600)
            minutes = int((seconds % 3600) / 60)
            return f"{hours}h {minutes}m"
    
    def log_summary(self):
        """Log final summary"""
        stats = self.get_stats()
        
        logging.info("=" * 60)
        logging.info("PROCESSING COMPLETE")
        logging.info("=" * 60)
        logging.info(f"Total files processed: {stats['processed']}")
        logging.info(f"Errors encountered: {stats['errors']}")
        logging.info(f"Files skipped: {stats['skipped']}")
        logging.info(f"Total time: {stats['elapsed_formatted']}")
        logging.info(f"Average rate: {stats['rate_per_minute']:.1f} files/minute")
        
        if stats.get('percent_complete'):
            logging.info(f"Completion: {stats['percent_complete']}%")


class BatchProcessor:
    """Process items in batches with progress tracking"""
    
    def __init__(self, items: List, batch_size: int = 1000, 
                 desc: str = "Processing batches"):
        """Initialize batch processor"""
        self.items = items
        self.batch_size = batch_size
        self.desc = desc
        self.total_batches = (len(items) + batch_size - 1) // batch_size
        self.current_batch = 0
        
        # Create progress tracker for overall progress
        self.tracker = ProgressTracker(
            total_items=len(items),
            desc=desc
        )
    
    def get_batches(self):
        """Generator to yield batches of items"""
        for i in range(0, len(self.items), self.batch_size):
            self.current_batch += 1
            batch = self.items[i:i + self.batch_size]
            
            # Update phase
            self.tracker.set_phase(
                f"Batch {self.current_batch}/{self.total_batches}"
            )
            
            yield batch
    
    def process_batch(self, batch: List, process_func, *args, **kwargs):
        """Process a batch of items with progress tracking"""
        results = []
        
        for item in batch:
            try:
                # Skip if already processed (for resume capability)
                if isinstance(item, str) and self.tracker.is_file_processed(item):
                    self.tracker.update(skip=True, file_path=item)
                    continue
                
                # Process item
                result = process_func(item, *args, **kwargs)
                results.append(result)
                
                # Update progress
                file_path = item if isinstance(item, str) else None
                self.tracker.update(file_path=file_path)
                
            except Exception as e:
                logging.error(f"Error processing {item}: {e}")
                self.tracker.update(error=True, file_path=str(item))
                results.append(None)
        
        return results
    
    def close(self):
        """Close batch processor and log summary"""
        self.tracker.log_summary()
        self.tracker.close()


def setup_logging(log_file: str = None, log_level: str = 'INFO', 
                  console: bool = True):
    """Setup logging configuration"""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    handlers = []
    
    # Console handler
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(logging.Formatter(log_format))
        handlers.append(console_handler)
    
    # File handler
    if log_file:
        # Create log directory if needed
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(logging.Formatter(log_format))
        handlers.append(file_handler)
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        handlers=handlers
    )
    
    # Reduce noise from some libraries
    logging.getLogger('musicbrainzngs').setLevel(logging.WARNING)
    logging.getLogger('mutagen').setLevel(logging.WARNING)


class ReportGenerator:
    """Generate detailed reports of cleanup operations"""
    
    def __init__(self, output_dir: str = 'reports'):
        """Initialize report generator"""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    def generate_html_report(self, stats: Dict, duplicates: List[List[Dict]], 
                           operations: List[Dict]) -> str:
        """Generate HTML report"""
        html_file = self.output_dir / f'cleanup_report_{self.timestamp}.html'
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Music Library Cleanup Report - {self.timestamp}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1, h2 {{ color: #333; }}
        table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #f2f2f2; }}
        .summary {{ background-color: #e8f4f8; padding: 15px; border-radius: 5px; }}
        .error {{ color: #d9534f; }}
        .success {{ color: #5cb85c; }}
        .warning {{ color: #f0ad4e; }}
    </style>
</head>
<body>
    <h1>Music Library Cleanup Report</h1>
    <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    
    <div class="summary">
        <h2>Summary</h2>
        <ul>
            <li>Total files processed: {stats.get('processed', 0)}</li>
            <li>Files copied: {stats.get('files_copied', 0)}</li>
            <li>Duplicates found: {stats.get('duplicate_files', 0)}</li>
            <li>Space saved: {stats.get('space_saved_gb', 0):.2f} GB</li>
            <li>Errors: {stats.get('errors', 0)}</li>
            <li>Processing time: {stats.get('elapsed_formatted', 'N/A')}</li>
        </ul>
    </div>
    
    <h2>Genre Distribution</h2>
    <table>
        <tr><th>Genre</th><th>Count</th></tr>
"""
        
        # Add genre distribution
        for genre, count in stats.get('genre_distribution', {}).items():
            html_content += f"        <tr><td>{genre or 'Unknown'}</td><td>{count}</td></tr>\n"
        
        html_content += """
    </table>
    
    <h2>Top Duplicate Groups</h2>
    <table>
        <tr>
            <th>Best File</th>
            <th>Format</th>
            <th>Duplicates</th>
            <th>Space Saved</th>
        </tr>
"""
        
        # Add duplicate information
        for group in duplicates[:20]:  # Top 20 duplicate groups
            if group:
                best = group[0]
                html_content += f"""
        <tr>
            <td>{os.path.basename(best.get('file_path', 'Unknown'))}</td>
            <td>{best.get('format', 'Unknown')} @ {best.get('bitrate', 0)//1000}kbps</td>
            <td>{len(group) - 1}</td>
            <td>{sum(f.get('file_size', 0) for f in group[1:]) / (1024**2):.1f} MB</td>
        </tr>
"""
        
        html_content += """
    </table>
</body>
</html>
"""
        
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return str(html_file)
    
    def generate_csv_report(self, operations: List[Dict]) -> str:
        """Generate CSV report of all operations"""
        import csv
        
        csv_file = self.output_dir / f'operations_{self.timestamp}.csv'
        
        if not operations:
            return None
        
        # Get all unique keys
        all_keys = set()
        for op in operations:
            all_keys.update(op.keys())
        
        # Write CSV
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=sorted(all_keys))
            writer.writeheader()
            writer.writerows(operations)
        
        return str(csv_file)
    
    def generate_duplicate_list(self, duplicates: List[List[Dict]]) -> str:
        """Generate text file listing all duplicates"""
        dup_file = self.output_dir / f'duplicates_{self.timestamp}.txt'
        
        with open(dup_file, 'w', encoding='utf-8') as f:
            f.write("DUPLICATE FILES REPORT\n")
            f.write("=" * 80 + "\n\n")
            
            total_space = 0
            
            for i, group in enumerate(duplicates, 1):
                if not group:
                    continue
                
                f.write(f"Duplicate Group {i}:\n")
                f.write("-" * 40 + "\n")
                
                # Sort by quality
                sorted_group = sorted(group, 
                                    key=lambda x: x.get('quality_score', 0), 
                                    reverse=True)
                
                best = sorted_group[0]
                f.write(f"KEEP: {best['file_path']}\n")
                f.write(f"      Format: {best.get('format', 'Unknown')}, ")
                f.write(f"Bitrate: {best.get('bitrate', 0)//1000}kbps, ")
                f.write(f"Size: {best.get('file_size', 0)/(1024**2):.1f}MB\n\n")
                
                f.write("DUPLICATES:\n")
                for dup in sorted_group[1:]:
                    f.write(f"  - {dup['file_path']}\n")
                    f.write(f"    Format: {dup.get('format', 'Unknown')}, ")
                    f.write(f"Bitrate: {dup.get('bitrate', 0)//1000}kbps, ")
                    f.write(f"Size: {dup.get('file_size', 0)/(1024**2):.1f}MB\n")
                    total_space += dup.get('file_size', 0)
                
                f.write("\n")
            
            f.write("=" * 80 + "\n")
            f.write(f"Total space that can be saved: {total_space/(1024**3):.2f} GB\n")
        
        return str(dup_file)