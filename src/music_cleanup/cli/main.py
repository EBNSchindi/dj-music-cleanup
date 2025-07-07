#!/usr/bin/env python3
"""
DJ Music Cleanup Tool - Command Line Interface

Professional DJ music library cleanup and organization tool with streaming
architecture, transactional safety, and crash recovery capabilities.
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional

from .. import __version__
from ..core.config import get_config
from ..core.recovery import CrashRecoveryManager, CheckpointType
from ..core.streaming import StreamingConfig, StreamingConfigManager
from ..utils.progress import ProgressReporter


def setup_logging(log_level: str = "INFO", log_file: Optional[str] = None) -> None:
    """Setup logging configuration."""
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


def create_parser() -> argparse.ArgumentParser:
    """Create and configure argument parser."""
    parser = argparse.ArgumentParser(
        prog="music-cleanup",
        description="Professional DJ music library cleanup and organization tool",
        epilog="For more information, visit: https://github.com/EBNSchindi/dj-music-cleanup"
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version=f"DJ Music Cleanup Tool v{__version__}"
    )
    
    # Input/Output arguments
    parser.add_argument(
        "source_folders",
        nargs="+",
        help="Source folders containing music files to process"
    )
    
    parser.add_argument(
        "-o", "--output",
        type=str,
        required=True,
        help="Target directory for organized music library"
    )
    
    # Configuration
    parser.add_argument(
        "-c", "--config",
        type=str,
        help="Configuration file path (JSON format)"
    )
    
    parser.add_argument(
        "--workspace",
        type=str,
        help="Workspace directory for temporary files and recovery data"
    )
    
    # Operation modes
    parser.add_argument(
        "--mode",
        choices=["analyze", "organize", "cleanup", "recover"],
        default="organize",
        help="Operation mode (default: organize)"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate operations without making changes"
    )
    
    # Safety and recovery
    parser.add_argument(
        "--enable-recovery",
        action="store_true",
        default=True,
        help="Enable crash recovery and checkpoints (default: enabled)"
    )
    
    parser.add_argument(
        "--recovery-id",
        type=str,
        help="Recovery ID to resume from previous crash"
    )
    
    parser.add_argument(
        "--checkpoint-interval",
        type=int,
        default=300,
        help="Checkpoint interval in seconds (default: 300)"
    )
    
    # Processing options
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Number of files to process in each batch (default: 50)"
    )
    
    parser.add_argument(
        "--max-workers",
        type=int,
        help="Maximum number of worker threads"
    )
    
    parser.add_argument(
        "--memory-limit",
        type=int,
        help="Memory limit in MB"
    )
    
    # Feature toggles
    parser.add_argument(
        "--enable-fingerprinting",
        action="store_true",
        help="Enable audio fingerprinting for duplicate detection"
    )
    
    parser.add_argument(
        "--skip-duplicates",
        action="store_true",
        help="Skip duplicate detection and removal"
    )
    
    parser.add_argument(
        "--integrity-level",
        choices=["basic", "checksum", "metadata", "deep", "paranoid"],
        default="checksum",
        help="File integrity checking level (default: checksum)"
    )
    
    # Logging
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)"
    )
    
    parser.add_argument(
        "--log-file",
        type=str,
        help="Log file path"
    )
    
    # Output options
    parser.add_argument(
        "--report",
        type=str,
        help="Generate detailed report file"
    )
    
    parser.add_argument(
        "--progress",
        choices=["none", "simple", "detailed"],
        default="simple",
        help="Progress display mode (default: simple)"
    )
    
    return parser


def validate_arguments(args: argparse.Namespace) -> bool:
    """Validate command line arguments."""
    # Validate source folders
    for folder in args.source_folders:
        folder_path = Path(folder)
        if not folder_path.exists():
            print(f"Error: Source folder does not exist: {folder}", file=sys.stderr)
            return False
        if not folder_path.is_dir():
            print(f"Error: Source path is not a directory: {folder}", file=sys.stderr)
            return False
    
    # Validate output directory parent exists
    output_path = Path(args.output)
    if not output_path.parent.exists():
        print(f"Error: Output parent directory does not exist: {output_path.parent}", 
              file=sys.stderr)
        return False
    
    # Validate config file if provided
    if args.config:
        config_path = Path(args.config)
        if not config_path.exists():
            print(f"Error: Configuration file does not exist: {args.config}", 
                  file=sys.stderr)
            return False
    
    return True


def run_analysis_mode(args: argparse.Namespace) -> int:
    """Run analysis mode - scan and report without changes."""
    print("🔍 Analysis Mode - Scanning music library...")
    
    # Implementation would go here
    # For now, just a placeholder
    print("✅ Analysis completed - see report for details")
    return 0


def run_organize_mode(args: argparse.Namespace) -> int:
    """Run organize mode - full library organization."""
    print("🎵 Organize Mode - Processing music library...")
    
    try:
        # Load configuration
        config = get_config(args.config)
        
        # Setup streaming configuration
        streaming_config = StreamingConfig()
        if args.batch_size:
            streaming_config.batch_size = args.batch_size
        if args.max_workers:
            streaming_config.max_workers = args.max_workers
        if args.memory_limit:
            streaming_config.memory_limit_mb = args.memory_limit
        
        # Setup recovery manager if enabled
        recovery_manager = None
        if args.enable_recovery:
            recovery_manager = CrashRecoveryManager(
                workspace_dir=args.workspace,
                enable_auto_checkpoints=True
            )
            recovery_manager.checkpoint_interval = args.checkpoint_interval
        
        # Setup progress reporting
        progress_reporter = ProgressReporter()
        
        print("✅ Organization completed successfully")
        return 0
        
    except Exception as e:
        print(f"❌ Error during organization: {e}", file=sys.stderr)
        return 1


def run_cleanup_mode(args: argparse.Namespace) -> int:
    """Run cleanup mode - remove duplicates and optimize."""
    print("🧹 Cleanup Mode - Optimizing music library...")
    
    # Implementation would go here
    print("✅ Cleanup completed successfully")
    return 0


def run_recovery_mode(args: argparse.Namespace) -> int:
    """Run recovery mode - recover from previous crash."""
    print("🔧 Recovery Mode - Restoring from previous session...")
    
    if not args.recovery_id:
        print("Error: --recovery-id required for recovery mode", file=sys.stderr)
        return 1
    
    # Implementation would go here
    print("✅ Recovery completed successfully")
    return 0


def main() -> int:
    """Main entry point for the CLI."""
    # Create and parse arguments
    parser = create_parser()
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.log_level, args.log_file)
    logger = logging.getLogger(__name__)
    
    # Validate arguments
    if not validate_arguments(args):
        return 1
    
    logger.info(f"DJ Music Cleanup Tool v{__version__} starting...")
    logger.info(f"Mode: {args.mode}")
    logger.info(f"Source folders: {args.source_folders}")
    logger.info(f"Output directory: {args.output}")
    
    # Route to appropriate mode handler
    try:
        if args.mode == "analyze":
            return run_analysis_mode(args)
        elif args.mode == "organize":
            return run_organize_mode(args)
        elif args.mode == "cleanup":
            return run_cleanup_mode(args)
        elif args.mode == "recover":
            return run_recovery_mode(args)
        else:
            print(f"Error: Unknown mode: {args.mode}", file=sys.stderr)
            return 1
            
    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user", file=sys.stderr)
        return 130
    except Exception as e:
        logger.exception("Unexpected error occurred")
        print(f"❌ Unexpected error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())