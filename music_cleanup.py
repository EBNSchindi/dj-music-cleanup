#!/usr/bin/env python3
"""
DJ Music Library Cleanup Tool
Main entry point and CLI interface
"""
import os
import sys
import argparse
import logging
from pathlib import Path
from typing import List, Dict
import json
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config import get_config, Config
from modules.fingerprinting import AudioFingerprinter
from modules.metadata import MetadataManager
from modules.organizer import FileOrganizer
from utils.progress import ProgressTracker, BatchProcessor, setup_logging, ReportGenerator


class MusicLibraryCleanup:
    """Main application class for music library cleanup"""
    
    def __init__(self, config_file: str = None):
        """Initialize the cleanup tool"""
        self.config = get_config(config_file)
        self.fingerprinter = None
        self.metadata_manager = None
        self.organizer = None
        self.logger = logging.getLogger(__name__)
        
        # Setup components
        self._setup_components()
    
    def _setup_components(self):
        """Initialize all components"""
        # Setup logging
        log_file = f"logs/cleanup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        setup_logging(
            log_file=log_file,
            log_level=self.config.get('log_level', 'INFO')
        )
        
        # Initialize components
        self.fingerprinter = AudioFingerprinter(
            db_path=self.config.get('fingerprint_cache_db', 'fingerprints.db'),
            acoustid_key=self.config.get('acoustid_api_key')
        )
        
        self.metadata_manager = MetadataManager(
            enable_musicbrainz=self.config.get('enable_musicbrainz', True),
            mb_contact=self.config.get('musicbrainz_contact')
        )
        
        self.organizer = FileOrganizer(
            target_root=self.config.get('target_folder', 'D:\\Bereinigt')
        )
    
    def scan_music_files(self) -> List[str]:
        """Scan for music files in source folders"""
        self.logger.info("Scanning for music files...")
        
        music_files = []
        supported_formats = set(self.config.get('supported_formats', ['.mp3']))
        
        for source_folder in self.config.get('source_folders', []):
            if not os.path.exists(source_folder):
                self.logger.warning(f"Source folder not found: {source_folder}")
                continue
            
            self.logger.info(f"Scanning {source_folder}...")
            
            for root, dirs, files in os.walk(source_folder):
                # Skip protected folders
                if self.config.is_protected_path(root):
                    self.logger.info(f"Skipping protected folder: {root}")
                    dirs.clear()  # Don't descend into subdirectories
                    continue
                
                for file in files:
                    ext = os.path.splitext(file)[1].lower()
                    if ext in supported_formats:
                        file_path = os.path.join(root, file)
                        
                        # Check file size limits
                        try:
                            size_mb = os.path.getsize(file_path) / (1024 * 1024)
                            min_size = self.config.get('min_file_size_mb', 0.5)
                            max_size = self.config.get('max_file_size_mb', 50)
                            
                            if min_size <= size_mb <= max_size:
                                music_files.append(file_path)
                            else:
                                self.logger.debug(f"Skipping file (size: {size_mb:.1f}MB): {file_path}")
                        except OSError:
                            self.logger.error(f"Cannot access file: {file_path}")
        
        self.logger.info(f"Found {len(music_files)} music files")
        return music_files
    
    def process_fingerprinting(self, music_files: List[str]) -> Dict[str, Dict]:
        """Process audio fingerprinting for all files"""
        self.logger.info("Starting audio fingerprinting phase...")
        
        batch_processor = BatchProcessor(
            items=music_files,
            batch_size=self.config.get('batch_size', 1000),
            desc="Fingerprinting audio files"
        )
        
        all_fingerprints = {}
        
        try:
            for batch in batch_processor.get_batches():
                # Process batch with multiprocessing
                results = self.fingerprinter.process_files_batch(
                    batch,
                    max_workers=self.config.get('multiprocessing_workers', 4)
                )
                all_fingerprints.update(results)
        
        finally:
            batch_processor.close()
        
        return all_fingerprints
    
    def find_and_rank_duplicates(self) -> List[List[Dict]]:
        """Find and rank duplicate files"""
        self.logger.info("Finding duplicate files...")
        
        duplicate_groups = self.fingerprinter.find_duplicates()
        
        self.logger.info(f"Found {len(duplicate_groups)} duplicate groups")
        
        # Rank duplicates by quality
        ranked_groups = []
        for group in duplicate_groups:
            ranked_group = self.fingerprinter.rank_duplicates(group)
            ranked_groups.append(ranked_group)
        
        return ranked_groups
    
    def process_metadata(self, music_files: List[str]) -> Dict[str, Dict]:
        """Extract and enrich metadata for all files"""
        self.logger.info("Processing metadata...")
        
        batch_processor = BatchProcessor(
            items=music_files,
            batch_size=self.config.get('batch_size', 1000),
            desc="Extracting metadata"
        )
        
        all_metadata = {}
        
        try:
            for batch in batch_processor.get_batches():
                for file_path in batch:
                    try:
                        # Extract metadata
                        metadata = self.metadata_manager.extract_metadata(file_path)
                        
                        # Enrich with MusicBrainz if enabled
                        if self.config.get('enable_musicbrainz'):
                            metadata = self.metadata_manager.enrich_from_musicbrainz(metadata)
                        
                        all_metadata[file_path] = metadata
                        batch_processor.tracker.update(file_path=file_path)
                        
                    except Exception as e:
                        self.logger.error(f"Error processing metadata for {file_path}: {e}")
                        batch_processor.tracker.update(error=True, file_path=file_path)
        
        finally:
            batch_processor.close()
        
        return all_metadata
    
    def organize_files(self, metadata_dict: Dict[str, Dict], 
                      duplicate_groups: List[List[Dict]], 
                      dry_run: bool = False):
        """Organize files into new structure"""
        self.logger.info(f"Organizing files (dry_run={dry_run})...")
        
        # First, handle duplicates
        duplicate_files = set()
        best_files = set()
        
        for group in duplicate_groups:
            if group:
                best_file = group[0]['file_path']
                best_files.add(best_file)
                
                # Mark other files as duplicates
                for dup in group[1:]:
                    duplicate_files.add(dup['file_path'])
                
                # Handle duplicate group
                self.organizer.handle_duplicate_group(group, dry_run=dry_run)
        
        # Process non-duplicate files
        files_to_process = []
        for file_path, metadata in metadata_dict.items():
            if file_path not in duplicate_files:
                # Skip files in protected folders
                if self.config.is_protected_path(file_path):
                    self.logger.debug(f"Skipping protected file: {file_path}")
                    continue
                
                files_to_process.append((file_path, metadata))
        
        # Process files in batches
        batch_processor = BatchProcessor(
            items=files_to_process,
            batch_size=self.config.get('batch_size', 1000),
            desc="Organizing files"
        )
        
        try:
            for batch in batch_processor.get_batches():
                for file_path, metadata in batch:
                    try:
                        # Generate clean filename
                        extension = os.path.splitext(file_path)[1]
                        new_filename = self.metadata_manager.clean_filename(
                            metadata.get('artist'),
                            metadata.get('title'),
                            extension
                        )
                        
                        # Copy file to organized location
                        success, result = self.organizer.copy_file(
                            file_path,
                            metadata,
                            new_filename=new_filename,
                            dry_run=dry_run
                        )
                        
                        if success:
                            batch_processor.tracker.update(file_path=file_path)
                        else:
                            batch_processor.tracker.update(error=True, file_path=file_path)
                    
                    except Exception as e:
                        self.logger.error(f"Error organizing {file_path}: {e}")
                        batch_processor.tracker.update(error=True, file_path=file_path)
        
        finally:
            batch_processor.close()
    
    def run_full_cleanup(self, dry_run: bool = False, resume: bool = False):
        """Run the complete cleanup process"""
        self.logger.info("=" * 60)
        self.logger.info("Starting Music Library Cleanup")
        self.logger.info(f"Dry run: {dry_run}")
        self.logger.info(f"Resume: {resume}")
        self.logger.info("=" * 60)
        
        # Validate configuration
        errors = self.config.validate()
        if errors:
            self.logger.error("Configuration errors found:")
            for error in errors:
                self.logger.error(f"  - {error}")
            return False
        
        # Phase 1: Scan files
        music_files = self.scan_music_files()
        if not music_files:
            self.logger.warning("No music files found to process")
            return False
        
        # Phase 2: Fingerprinting
        fingerprint_data = self.process_fingerprinting(music_files)
        
        # Phase 3: Find duplicates
        duplicate_groups = self.find_and_rank_duplicates()
        
        # Phase 4: Process metadata
        metadata_dict = self.process_metadata(music_files)
        
        # Phase 5: Organize files
        self.organize_files(metadata_dict, duplicate_groups, dry_run=dry_run)
        
        # Generate reports
        self.generate_reports(duplicate_groups)
        
        self.logger.info("=" * 60)
        self.logger.info("Music Library Cleanup Complete!")
        self.logger.info("=" * 60)
        
        return True
    
    def generate_reports(self, duplicate_groups: List[List[Dict]]):
        """Generate comprehensive reports"""
        self.logger.info("Generating reports...")
        
        report_gen = ReportGenerator()
        
        # Get statistics
        organizer_report = self.organizer.generate_report()
        fingerprint_stats = self.fingerprinter.get_statistics()
        
        # Combine statistics
        combined_stats = {
            **organizer_report['summary'],
            **fingerprint_stats,
            'genre_distribution': organizer_report.get('genre_distribution', {}),
            'space_saved_gb': organizer_report['duplicates']['space_saved_gb']
        }
        
        # Generate reports
        html_report = report_gen.generate_html_report(
            combined_stats,
            duplicate_groups,
            self.organizer.get_operation_history(limit=1000)
        )
        
        duplicate_list = report_gen.generate_duplicate_list(duplicate_groups)
        
        # Create undo script
        self.organizer.create_undo_script()
        
        self.logger.info(f"HTML Report: {html_report}")
        self.logger.info(f"Duplicate List: {duplicate_list}")
        self.logger.info("Undo script created: undo_operations.sh")
    
    def analyze_only(self):
        """Run analysis only without making changes"""
        self.logger.info("Running analysis mode...")
        
        # Scan files
        music_files = self.scan_music_files()
        if not music_files:
            self.logger.warning("No music files found")
            return
        
        # Quick analysis
        total_size = 0
        format_counts = {}
        
        for file_path in music_files:
            try:
                size = os.path.getsize(file_path)
                total_size += size
                
                ext = os.path.splitext(file_path)[1].lower()
                format_counts[ext] = format_counts.get(ext, 0) + 1
            except:
                pass
        
        # Print analysis
        print("\n" + "=" * 60)
        print("MUSIC LIBRARY ANALYSIS")
        print("=" * 60)
        print(f"Total files: {len(music_files)}")
        print(f"Total size: {total_size / (1024**3):.2f} GB")
        print("\nFormat distribution:")
        for ext, count in sorted(format_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  {ext}: {count} files")
        
        # Sample metadata check
        print("\nChecking metadata completeness (sample of 100 files)...")
        sample_files = music_files[:100]
        metadata_stats = {
            'has_artist': 0,
            'has_title': 0,
            'has_album': 0,
            'has_year': 0,
            'has_genre': 0
        }
        
        for file_path in sample_files:
            metadata = self.metadata_manager.extract_metadata(file_path)
            if metadata.get('artist'):
                metadata_stats['has_artist'] += 1
            if metadata.get('title'):
                metadata_stats['has_title'] += 1
            if metadata.get('album'):
                metadata_stats['has_album'] += 1
            if metadata.get('year'):
                metadata_stats['has_year'] += 1
            if metadata.get('genre'):
                metadata_stats['has_genre'] += 1
        
        print("\nMetadata completeness (based on sample):")
        for field, count in metadata_stats.items():
            percent = (count / len(sample_files)) * 100
            print(f"  {field}: {percent:.1f}%")
        
        print("\nUse --quality-analysis to analyze audio quality")
        print("Use --dry-run to see what changes would be made")
        print("Use --execute to perform the cleanup")
    
    def analyze_audio_quality(self):
        """Run comprehensive audio quality analysis"""
        self.logger.info("Running audio quality analysis...")
        
        # Scan files
        music_files = self.scan_music_files()
        if not music_files:
            self.logger.warning("No music files found")
            return
        
        # Process files with quality analysis
        fingerprint_data = self.process_fingerprinting(music_files)
        
        # Get quality statistics
        stats = self.fingerprinter.get_statistics()
        quality_report = self.fingerprinter.get_quality_report()
        
        # Display results
        print("\n" + "=" * 60)
        print("AUDIO QUALITY ANALYSIS REPORT")
        print("=" * 60)
        
        print(f"Total files analyzed: {quality_report['total_files_analyzed']}")
        
        if quality_report['quality_summary']['quality_distribution']:
            print("\nQuality Distribution:")
            for rating, count in quality_report['quality_summary']['quality_distribution'].items():
                print(f"  {rating}: {count} files")
        
        if quality_report['quality_summary']['issue_distribution']:
            print("\nDetected Issues:")
            for issue, count in quality_report['quality_summary']['issue_distribution'].items():
                print(f"  {issue}: {count} files")
        
        if quality_report['recommendations']:
            print("\nRecommendations:")
            for rec in quality_report['recommendations']:
                print(f"  • {rec}")
        
        # Show most problematic files
        if quality_report['problematic_files']:
            print(f"\nMost Problematic Files (showing first 10):")
            for i, file_info in enumerate(quality_report['problematic_files'][:10]):
                print(f"  {i+1}. {file_info['file_path']}")
                print(f"     Quality: {file_info['quality_rating']} (score: {file_info['quality_score']})")
                print(f"     Issues: {', '.join(file_info['issues'])}")
                print(f"     Format: {file_info['format']} @ {file_info['bitrate']} kbps")
                print()
        
        # Show statistics
        print(f"\nOverall Statistics:")
        print(f"  Files with quality issues: {stats['files_with_issues']}")
        print(f"  Duplicate groups found: {stats['duplicate_groups']}")
        print(f"  Total duplicate files: {stats['duplicate_files']}")
        
        print("\n" + "=" * 60)
        print("Quality analysis complete!")
        print("=" * 60)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="DJ Music Library Cleanup Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --scan-only          # Analyze library without changes
  %(prog)s --quality-analysis   # Analyze audio quality and detect issues
  %(prog)s --dry-run           # Show what would be done
  %(prog)s --execute           # Perform full cleanup
  %(prog)s --resume            # Resume interrupted cleanup
  %(prog)s --config my.json    # Use custom config file
        """
    )
    
    # Operation modes
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('--scan-only', action='store_true',
                           help='Only analyze library, no changes')
    mode_group.add_argument('--quality-analysis', action='store_true',
                           help='Analyze audio quality and detect issues')
    mode_group.add_argument('--dry-run', action='store_true',
                           help='Simulate cleanup and show what would be done')
    mode_group.add_argument('--execute', action='store_true',
                           help='Execute full cleanup (modifies files)')
    
    # Options
    parser.add_argument('--config', type=str, default='music_cleanup_config.json',
                       help='Configuration file path')
    parser.add_argument('--resume', action='store_true',
                       help='Resume from last checkpoint')
    parser.add_argument('--create-config', action='store_true',
                       help='Create example configuration file')
    
    args = parser.parse_args()
    
    # Create example config if requested
    if args.create_config:
        config = Config()
        config.create_example_config()
        print("Example configuration created: example_config.json")
        print("Edit this file and use with --config option")
        return
    
    # Check if config exists
    if not os.path.exists(args.config) and not args.create_config:
        print(f"Configuration file not found: {args.config}")
        print("Create one with --create-config or specify with --config")
        return
    
    # Initialize and run
    try:
        cleanup = MusicLibraryCleanup(args.config)
        
        if args.scan_only:
            cleanup.analyze_only()
        elif args.quality_analysis:
            cleanup.analyze_audio_quality()
        elif args.dry_run:
            cleanup.config.set('dry_run', True)
            cleanup.run_full_cleanup(dry_run=True, resume=args.resume)
        elif args.execute:
            # Confirm before executing
            print("\nWARNING: This will copy and organize your music files.")
            print("Protected folders will not be modified.")
            print("Original files will not be deleted.")
            
            try:
                response = input("\nContinue? (yes/no): ")
                
                if response.lower() == 'yes':
                    cleanup.run_full_cleanup(dry_run=False, resume=args.resume)
                else:
                    print("Operation cancelled.")
            except EOFError:
                print("\nNon-interactive mode detected - proceeding with execution...")
                cleanup.run_full_cleanup(dry_run=False, resume=args.resume)
    
    except KeyboardInterrupt:
        print("\n\nOperation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        logging.exception("Unhandled exception")
        sys.exit(1)


if __name__ == '__main__':
    main()