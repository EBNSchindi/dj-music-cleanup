#!/usr/bin/env python3
"""
Database Migration Script for DJ Music Cleanup Tool

This script migrates from the legacy three-database structure
(fingerprints.db, operations.db, progress.db) to the unified
music_cleanup.db schema with proper relationships.

Usage:
    python migrate_database.py --source-dir /path/to/old/dbs --target /path/to/music_cleanup.db
    python migrate_database.py --dry-run --source-dir /path/to/old/dbs --target /path/to/music_cleanup.db
"""

import argparse
import sys
import logging
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from music_cleanup.core.database_migration import run_migration


def setup_logging(log_level: str = "INFO", log_file: str = None) -> None:
    """Setup logging configuration"""
    level = getattr(logging, log_level.upper())
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Setup console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(console_handler)
    
    # Setup file handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)


def validate_arguments(args: argparse.Namespace) -> bool:
    """Validate command line arguments"""
    # Check source directory
    source_dir = Path(args.source_dir)
    if not source_dir.exists():
        print(f"Error: Source directory does not exist: {source_dir}", file=sys.stderr)
        return False
    
    if not source_dir.is_dir():
        print(f"Error: Source path is not a directory: {source_dir}", file=sys.stderr)
        return False
    
    # Check target path parent exists
    target_path = Path(args.target)
    if not target_path.parent.exists():
        print(f"Error: Target parent directory does not exist: {target_path.parent}", 
              file=sys.stderr)
        return False
    
    # Check backup directory if specified
    if args.backup_dir:
        backup_dir = Path(args.backup_dir)
        if backup_dir.exists() and not backup_dir.is_dir():
            print(f"Error: Backup path exists but is not a directory: {backup_dir}", 
                  file=sys.stderr)
            return False
    
    # Warn if target exists and not dry run
    if target_path.exists() and not args.dry_run:
        response = input(f"Target database {target_path} already exists. Overwrite? (y/N): ")
        if response.lower() != 'y':
            print("Migration cancelled by user")
            return False
    
    return True


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Migrate DJ Music Cleanup Tool databases to unified schema",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run to see what would be migrated
  python migrate_database.py --dry-run --source-dir ./old_dbs --target ./music_cleanup.db
  
  # Actual migration with custom backup location
  python migrate_database.py --source-dir ./old_dbs --target ./music_cleanup.db --backup-dir ./backups
  
  # Migration with debug logging
  python migrate_database.py --source-dir ./old_dbs --target ./music_cleanup.db --log-level DEBUG
        """
    )
    
    # Required arguments
    parser.add_argument(
        '--source-dir',
        required=True,
        help='Directory containing legacy database files (fingerprints.db, operations.db, progress.db)'
    )
    
    parser.add_argument(
        '--target',
        required=True,
        help='Path for the new unified music_cleanup.db database'
    )
    
    # Optional arguments
    parser.add_argument(
        '--backup-dir',
        help='Directory to store database backups (default: source-dir/backups)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Perform validation and show migration plan without making changes'
    )
    
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Logging level (default: INFO)'
    )
    
    parser.add_argument(
        '--log-file',
        help='Write logs to file in addition to console'
    )
    
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force migration even if validation warnings occur'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.log_level, args.log_file)
    logger = logging.getLogger(__name__)
    
    # Validate arguments
    if not validate_arguments(args):
        return 1
    
    # Print migration info
    print("🎵 DJ Music Cleanup Tool - Database Migration")
    print("=" * 50)
    print(f"Source directory: {args.source_dir}")
    print(f"Target database: {args.target}")
    print(f"Backup directory: {args.backup_dir or Path(args.source_dir) / 'backups'}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE MIGRATION'}")
    print("=" * 50)
    
    if args.dry_run:
        print("🔍 This is a dry run - no changes will be made")
    else:
        print("⚠️  This will modify your databases - ensure you have backups!")
        
        if not args.force:
            response = input("\nProceed with migration? (y/N): ")
            if response.lower() != 'y':
                print("Migration cancelled by user")
                return 0
    
    print()
    
    # Run migration
    try:
        logger.info("Starting database migration...")
        
        success = run_migration(
            source_db_dir=args.source_dir,
            target_db_path=args.target,
            backup_dir=args.backup_dir,
            dry_run=args.dry_run
        )
        
        if success:
            if args.dry_run:
                print("\n✅ Migration validation successful!")
                print("   Run without --dry-run to perform actual migration")
            else:
                print("\n✅ Database migration completed successfully!")
                print(f"   Unified database created: {args.target}")
                print("   Legacy databases backed up")
            return 0
        else:
            print("\n❌ Migration failed!")
            print("   Check logs for details")
            return 1
            
    except KeyboardInterrupt:
        print("\n⚠️  Migration cancelled by user")
        return 130
    except Exception as e:
        logger.exception("Unexpected error during migration")
        print(f"\n❌ Unexpected error: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())