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
from ..core.orchestrator import MusicCleanupOrchestrator
from ..utils.progress import ProgressReporter
from ..utils.integrity import IntegrityLevel


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
    logger = logging.getLogger(__name__)
    
    try:
        # Load configuration
        config = get_config(args.config)
        
        # Setup streaming configuration
        streaming_config = _create_streaming_config(args)
        
        # Create orchestrator
        orchestrator = MusicCleanupOrchestrator(
            config=config,
            streaming_config=streaming_config,
            workspace_dir=args.workspace,
            enable_recovery=args.enable_recovery,
            dry_run=True  # Analysis mode is always dry run
        )
        
        # Setup progress callback
        def progress_callback(info):
            if args.progress == "detailed":
                print(f"  Analyzing: {info}")
        
        # Run analysis
        results = orchestrator.analyze_library(
            source_folders=args.source_folders,
            report_path=args.report,
            progress_callback=progress_callback if args.progress != "none" else None
        )
        
        # Print summary
        print(f"✅ Analysis completed:")
        print(f"  📁 Total files: {results['total_files']:,}")
        print(f"  💾 Total size: {results['total_size_bytes'] / (1024**3):.2f} GB")
        print(f"  🎵 Audio formats: {len(results['audio_formats'])}")
        print(f"  📊 Duplicate groups: {len(results['duplicate_groups'])}")
        print(f"  ⚠️  Metadata issues: {len(results['metadata_issues'])}")
        print(f"  🔍 Integrity issues: {len(results['integrity_issues'])}")
        print(f"  ⏱️  Duration: {results['analysis_duration']:.2f} seconds")
        
        if args.report:
            print(f"  📋 Report saved to: {args.report}")
        
        # Clean up
        orchestrator.cleanup()
        
        return 0
        
    except KeyboardInterrupt:
        print("\n⚠️  Analysis cancelled by user")
        return 130
    except Exception as e:
        logger.exception("Analysis failed")
        print(f"❌ Analysis failed: {e}", file=sys.stderr)
        return 1


def run_organize_mode(args: argparse.Namespace) -> int:
    """Run organize mode - full library organization."""
    print("🎵 Organize Mode - Processing music library...")
    logger = logging.getLogger(__name__)
    
    try:
        # Load configuration
        config = get_config(args.config)
        
        # Setup streaming configuration
        streaming_config = _create_streaming_config(args)
        
        # Update config with CLI arguments
        config['output_directory'] = args.output
        config['enable_fingerprinting'] = args.enable_fingerprinting
        config['skip_duplicates'] = args.skip_duplicates
        config['integrity_level'] = args.integrity_level
        
        # Create orchestrator
        orchestrator = MusicCleanupOrchestrator(
            config=config,
            streaming_config=streaming_config,
            workspace_dir=args.workspace,
            enable_recovery=args.enable_recovery,
            dry_run=args.dry_run
        )
        
        # Setup progress callback
        def progress_callback(info):
            if args.progress == "detailed":
                if isinstance(info, dict):
                    if info.get('success'):
                        print(f"  ✅ Organized: {info.get('destination', 'N/A')}")
                    elif info.get('skipped'):
                        print(f"  ⏭️  Skipped: {info.get('file', 'N/A')} ({info.get('skip_reason', 'unknown')})")
                    else:
                        print(f"  ❌ Failed: {info.get('file', 'N/A')} - {info.get('error', 'unknown error')}")
                else:
                    print(f"  Processing: {info}")
            elif args.progress == "simple" and isinstance(info, dict):
                if info.get('success'):
                    print(".", end="", flush=True)
        
        # Run organization
        print(f"📁 Source folders: {', '.join(args.source_folders)}")
        print(f"📂 Output directory: {args.output}")
        print(f"🔧 Features: {', '.join(_get_enabled_features(args))}")
        
        if args.dry_run:
            print("⚠️  DRY RUN MODE - No changes will be made")
        
        results = orchestrator.organize_library(
            source_folders=args.source_folders,
            output_directory=args.output,
            enable_fingerprinting=args.enable_fingerprinting,
            progress_callback=progress_callback if args.progress != "none" else None
        )
        
        # Print summary
        print(f"\n✅ Organization completed successfully:")
        print(f"  📁 Files processed: {results['files_processed']:,}")
        print(f"  ✅ Files organized: {results['files_organized']:,}")
        print(f"  ⏭️  Files skipped: {results['files_skipped']:,}")
        print(f"  ❌ Errors: {results['errors']:,}")
        
        if results['duplicates_handled'] > 0:
            print(f"  🔄 Duplicates handled: {results['duplicates_handled']:,}")
            print(f"  💾 Space saved: {results['space_saved'] / (1024**2):.1f} MB")
        
        print(f"  ⏱️  Duration: {results['organization_duration']:.2f} seconds")
        
        if args.report:
            # Generate organization report
            _generate_organization_report(results, args.report)
            print(f"  📋 Report saved to: {args.report}")
        
        # Clean up
        orchestrator.cleanup()
        
        return 0
        
    except KeyboardInterrupt:
        print("\n⚠️  Organization cancelled by user")
        return 130
    except Exception as e:
        logger.exception("Organization failed")
        print(f"❌ Organization failed: {e}", file=sys.stderr)
        return 1


def run_cleanup_mode(args: argparse.Namespace) -> int:
    """Run cleanup mode - remove duplicates and optimize."""
    print("🧹 Cleanup Mode - Optimizing music library...")
    logger = logging.getLogger(__name__)
    
    try:
        # Load configuration
        config = get_config(args.config)
        
        # Setup streaming configuration
        streaming_config = _create_streaming_config(args)
        
        # Update config for cleanup mode
        config['enable_fingerprinting'] = args.enable_fingerprinting
        config['skip_duplicates'] = args.skip_duplicates
        config['integrity_level'] = args.integrity_level
        
        # Create orchestrator
        orchestrator = MusicCleanupOrchestrator(
            config=config,
            streaming_config=streaming_config,
            workspace_dir=args.workspace,
            enable_recovery=args.enable_recovery,
            dry_run=args.dry_run
        )
        
        # Setup progress callback
        def progress_callback(info):
            if args.progress == "detailed":
                if isinstance(info, dict):
                    action = info.get('action')
                    if action == 'duplicate_group_processed':
                        print(f"  🔄 Group {info['group']}/{info['total_groups']}: "
                              f"kept {Path(info['kept']).name}, removed {info['removed']} duplicates")
                    elif action == 'phase':
                        print(f"  📍 {info.get('message', info.get('phase', 'Processing'))}")
                    else:
                        print(f"  Processing: {info}")
                else:
                    print(f"  {info}")
            elif args.progress == "simple":
                print(".", end="", flush=True)
        
        # Run cleanup
        print(f"📁 Source folders: {', '.join(args.source_folders)}")
        print(f"🔧 Features: {', '.join(_get_enabled_features(args))}")
        
        if args.dry_run:
            print("⚠️  DRY RUN MODE - No changes will be made")
        
        results = orchestrator.cleanup_library(
            source_folders=args.source_folders,
            enable_fingerprinting=args.enable_fingerprinting,
            progress_callback=progress_callback if args.progress != "none" else None
        )
        
        # Print summary
        print(f"\n✅ Cleanup completed successfully:")
        print(f"  📁 Files scanned: {results['files_scanned']:,}")
        print(f"  🔍 Duplicates found: {results['duplicates_found']:,}")
        print(f"  🗑️  Duplicates removed: {results['duplicates_removed']:,}")
        print(f"  💾 Space reclaimed: {results['space_reclaimed'] / (1024**3):.2f} GB")
        print(f"  ❌ Errors: {results['errors']:,}")
        print(f"  ⏱️  Duration: {results['cleanup_duration']:.2f} seconds")
        
        if args.report:
            # Generate cleanup report
            _generate_cleanup_report(results, args.report)
            print(f"  📋 Report saved to: {args.report}")
        
        # Clean up
        orchestrator.cleanup()
        
        return 0
        
    except KeyboardInterrupt:
        print("\n⚠️  Cleanup cancelled by user")
        return 130
    except Exception as e:
        logger.exception("Cleanup failed")
        print(f"❌ Cleanup failed: {e}", file=sys.stderr)
        return 1


def run_recovery_mode(args: argparse.Namespace) -> int:
    """Run recovery mode - recover from previous crash."""
    print("🔧 Recovery Mode - Restoring from previous session...")
    logger = logging.getLogger(__name__)
    
    try:
        # Load configuration
        config = get_config(args.config)
        
        # Setup streaming configuration
        streaming_config = _create_streaming_config(args)
        
        # Create orchestrator with recovery enabled
        orchestrator = MusicCleanupOrchestrator(
            config=config,
            streaming_config=streaming_config,
            workspace_dir=args.workspace,
            enable_recovery=True,  # Always enabled for recovery mode
            dry_run=args.dry_run
        )
        
        # Setup progress callback
        def progress_callback(info):
            if args.progress == "detailed":
                if isinstance(info, dict):
                    print(f"  🔧 Recovery: {info}")
                else:
                    print(f"  {info}")
            elif args.progress == "simple":
                print(".", end="", flush=True)
        
        # Run recovery
        if args.dry_run:
            print("⚠️  DRY RUN MODE - Recovery simulation only")
        
        if args.recovery_id:
            print(f"🔍 Using specific recovery ID: {args.recovery_id}")
        else:
            print("🔍 Auto-detecting recovery point...")
        
        results = orchestrator.recover_from_crash(
            recovery_id=args.recovery_id,
            progress_callback=progress_callback if args.progress != "none" else None
        )
        
        # Print summary
        if results['recovery_successful']:
            print(f"\n✅ Recovery completed successfully:")
            print(f"  🔧 Checkpoint used: {results.get('checkpoint_used', 'auto-detected')}")
            print(f"  📁 Files recovered: {results['files_recovered']:,}")
            print(f"  🔄 Operations rolled back: {results['operations_rolled_back']:,}")
            print(f"  ⏱️  Duration: {results['duration']:.2f} seconds")
        else:
            print(f"\n❌ Recovery failed:")
            print(f"  🔧 Checkpoint attempted: {results.get('checkpoint_used', 'none')}")
            print(f"  ❌ Error: {results.get('error', 'Unknown error')}")
            print(f"  ⏱️  Duration: {results['duration']:.2f} seconds")
        
        if args.report:
            # Generate recovery report
            _generate_recovery_report(results, args.report)
            print(f"  📋 Report saved to: {args.report}")
        
        # Clean up
        orchestrator.cleanup()
        
        return 0 if results['recovery_successful'] else 1
        
    except KeyboardInterrupt:
        print("\n⚠️  Recovery cancelled by user")
        return 130
    except Exception as e:
        logger.exception("Recovery failed")
        print(f"❌ Recovery failed: {e}", file=sys.stderr)
        return 1


def _create_streaming_config(args: argparse.Namespace) -> StreamingConfig:
    """Create streaming configuration from CLI arguments."""
    config = StreamingConfig()
    
    if args.batch_size:
        config.batch_size = args.batch_size
    if args.max_workers:
        config.max_workers = args.max_workers
    if args.memory_limit:
        config.memory_limit_mb = args.memory_limit
    
    return config


def _get_enabled_features(args: argparse.Namespace) -> List[str]:
    """Get list of enabled features for display."""
    features = []
    
    if args.enable_recovery:
        features.append("Recovery")
    if args.enable_fingerprinting:
        features.append("Fingerprinting")
    if not args.skip_duplicates:
        features.append("Duplicate Detection")
    
    features.append(f"Integrity: {args.integrity_level}")
    
    return features


def _generate_analysis_report(results: dict, report_path: str):
    """Generate analysis report."""
    try:
        import json
        from datetime import datetime
        
        report_data = {
            'report_type': 'analysis',
            'generated_at': datetime.now().isoformat(),
            'results': results
        }
        
        if report_path.endswith('.json'):
            with open(report_path, 'w') as f:
                json.dump(report_data, f, indent=2)
        else:
            # Generate HTML report
            _generate_html_report(report_data, report_path)
            
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to generate analysis report: {e}")


def _generate_organization_report(results: dict, report_path: str):
    """Generate organization report."""
    try:
        import json
        from datetime import datetime
        
        report_data = {
            'report_type': 'organization',
            'generated_at': datetime.now().isoformat(),
            'results': results
        }
        
        if report_path.endswith('.json'):
            with open(report_path, 'w') as f:
                json.dump(report_data, f, indent=2)
        else:
            # Generate HTML report
            _generate_html_report(report_data, report_path)
            
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to generate organization report: {e}")


def _generate_cleanup_report(results: dict, report_path: str):
    """Generate cleanup report."""
    try:
        import json
        from datetime import datetime
        
        report_data = {
            'report_type': 'cleanup',
            'generated_at': datetime.now().isoformat(),
            'results': results
        }
        
        if report_path.endswith('.json'):
            with open(report_path, 'w') as f:
                json.dump(report_data, f, indent=2)
        else:
            # Generate HTML report
            _generate_html_report(report_data, report_path)
            
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to generate cleanup report: {e}")


def _generate_recovery_report(results: dict, report_path: str):
    """Generate recovery report."""
    try:
        import json
        from datetime import datetime
        
        report_data = {
            'report_type': 'recovery',
            'generated_at': datetime.now().isoformat(),
            'results': results
        }
        
        if report_path.endswith('.json'):
            with open(report_path, 'w') as f:
                json.dump(report_data, f, indent=2)
        else:
            # Generate HTML report
            _generate_html_report(report_data, report_path)
            
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to generate recovery report: {e}")


def _generate_html_report(report_data: dict, report_path: str):
    """Generate HTML report from report data."""
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>DJ Music Cleanup - {report_data['report_type'].title()} Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        .header {{ background: #2c3e50; color: white; padding: 20px; border-radius: 5px; }}
        .section {{ margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
        .stat {{ display: inline-block; margin: 10px; padding: 10px; background: #f8f9fa; border-radius: 3px; }}
        .success {{ color: #28a745; }}
        .warning {{ color: #ffc107; }}
        .error {{ color: #dc3545; }}
        pre {{ background: #f8f9fa; padding: 10px; border-radius: 3px; overflow-x: auto; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🎵 DJ Music Cleanup Tool</h1>
        <h2>{report_data['report_type'].title()} Report</h2>
        <p>Generated: {report_data['generated_at']}</p>
    </div>
    
    <div class="section">
        <h3>Results Summary</h3>
        <pre>{json.dumps(report_data['results'], indent=2)}</pre>
    </div>
</body>
</html>
"""
    
    with open(report_path, 'w') as f:
        f.write(html_content)


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