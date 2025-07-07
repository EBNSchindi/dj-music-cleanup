#!/usr/bin/env python3
"""
Basic Usage Examples for DJ Music Cleanup Tool

This script demonstrates the most common use cases and basic functionality
of the DJ Music Cleanup Tool.
"""

import os
import sys
from pathlib import Path
from typing import List

# Add the src directory to the path for running examples directly
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from music_cleanup import (
    Config, get_config,
    StreamingConfig, FileDiscoveryStream,
    AtomicFileOperations, CrashRecoveryManager,
    FileIntegrityChecker, IntegrityLevel
)


def example_1_basic_file_discovery():
    """Example 1: Basic file discovery and streaming."""
    print("📁 Example 1: Basic File Discovery")
    print("=" * 50)
    
    # Create a streaming configuration
    config = StreamingConfig(
        batch_size=10,  # Small batch for demonstration
        max_workers=2,
        memory_limit_mb=256
    )
    
    # Create file discovery stream
    discovery = FileDiscoveryStream(config)
    
    # Example source folders (adjust paths as needed)
    source_folders = [
        str(Path.home() / "Music"),  # Default music folder
        "test_music",  # Test folder if it exists
    ]
    
    # Filter to existing folders
    existing_folders = [folder for folder in source_folders if Path(folder).exists()]
    
    if not existing_folders:
        print("⚠️  No music folders found. Creating example structure...")
        # Create example folder structure for demonstration
        test_folder = Path("example_music")
        test_folder.mkdir(exist_ok=True)
        (test_folder / "Artist1 - Song1.mp3").touch()
        (test_folder / "Artist2 - Song2.flac").touch()
        existing_folders = [str(test_folder)]
    
    print(f"🔍 Scanning folders: {existing_folders}")
    
    # Stream files and count them
    file_count = 0
    try:
        for file_path in discovery.stream_files(existing_folders):
            file_count += 1
            print(f"  {file_count}: {file_path}")
            
            # Limit output for demonstration
            if file_count >= 5:
                print("  ... (limiting output for demo)")
                break
                
    except Exception as e:
        print(f"❌ Error during discovery: {e}")
    
    print(f"✅ Found {file_count} music files")
    print()


def example_2_integrity_checking():
    """Example 2: File integrity checking."""
    print("🔍 Example 2: File Integrity Checking")
    print("=" * 50)
    
    # Create integrity checker
    checker = FileIntegrityChecker(workspace_dir="example_workspace")
    
    # Create example file for testing
    test_file = Path("example_test.mp3")
    test_file.write_bytes(b"fake mp3 content for testing")
    
    try:
        print(f"📋 Checking integrity of: {test_file}")
        
        # Basic integrity check
        result = checker.check_file_integrity(
            str(test_file), 
            IntegrityLevel.BASIC
        )
        
        print(f"  Status: {result.status.value}")
        print(f"  File size: {result.file_size} bytes")
        print(f"  Check level: {result.check_level.value}")
        
        if result.issues:
            print(f"  Issues found: {result.issues}")
        
        if result.repair_suggestions:
            print(f"  Repair suggestions: {result.repair_suggestions}")
        
        # Get checker statistics
        stats = checker.get_integrity_statistics()
        print(f"  Workspace: {stats['workspace_path']}")
        print(f"  Supported formats: {len(stats['supported_formats'])}")
        
    except Exception as e:
        print(f"❌ Error during integrity check: {e}")
    finally:
        # Cleanup
        if test_file.exists():
            test_file.unlink()
    
    print("✅ Integrity check completed")
    print()


def example_3_atomic_operations():
    """Example 3: Atomic file operations."""
    print("⚛️  Example 3: Atomic File Operations")
    print("=" * 50)
    
    # Create atomic operations manager
    atomic_ops = AtomicFileOperations(workspace_dir="example_workspace")
    
    try:
        # Begin a transaction
        transaction_id = atomic_ops.begin_transaction({
            'operation_type': 'example_operation',
            'description': 'Demonstration of atomic operations'
        })
        
        print(f"📋 Started transaction: {transaction_id}")
        
        # Create example source file
        source_file = Path("example_source.txt")
        source_file.write_text("Example content for atomic operations")
        
        target_file = Path("example_target.txt")
        
        # Add copy operation to transaction
        operation_id = atomic_ops.add_operation(
            transaction_id,
            atomic_ops.OperationType.COPY,
            source_path=str(source_file),
            target_path=str(target_file)
        )
        
        print(f"  Added operation: {operation_id}")
        
        # Prepare the transaction (validation phase)
        atomic_ops.prepare_transaction(transaction_id)
        print("  ✅ Transaction prepared successfully")
        
        # Commit the transaction
        atomic_ops.commit_transaction(transaction_id)
        print("  ✅ Transaction committed successfully")
        
        # Verify the result
        if target_file.exists():
            print(f"  ✅ File copied successfully: {target_file}")
            print(f"  Content: {target_file.read_text()}")
        else:
            print("  ❌ File copy failed")
        
        # Get transaction statistics
        stats = atomic_ops.get_transaction_statistics()
        print(f"  Total transactions: {stats.get('total_transactions', 0)}")
        print(f"  Active transactions: {stats.get('active_transactions', 0)}")
        
    except Exception as e:
        print(f"❌ Error during atomic operation: {e}")
        
        # Try to rollback if transaction is still active
        try:
            if transaction_id in atomic_ops.active_transactions:
                atomic_ops.rollback_transaction(transaction_id)
                print("  🔄 Transaction rolled back")
        except:
            pass
    
    finally:
        # Cleanup
        for file_path in [source_file, target_file]:
            if file_path.exists():
                file_path.unlink()
    
    print("✅ Atomic operations example completed")
    print()


def example_4_recovery_system():
    """Example 4: Crash recovery and checkpoints."""
    print("🔧 Example 4: Crash Recovery System")
    print("=" * 50)
    
    # Create recovery manager
    recovery_manager = CrashRecoveryManager(
        workspace_dir="example_workspace",
        enable_auto_checkpoints=False  # Disable for demo
    )
    
    try:
        # Start a recovery session
        session_id = recovery_manager.begin_session(
            "demo_session_123",
            "example_operation_group"
        )
        
        print(f"📋 Started recovery session: {session_id}")
        
        # Create a manual checkpoint
        checkpoint_id = recovery_manager.create_checkpoint(
            recovery_manager.CheckpointType.MANUAL,
            "Demonstration checkpoint",
            {"example": "metadata"}
        )
        
        print(f"  Created checkpoint: {checkpoint_id}")
        
        # Check for interruptions (should be none)
        interruption = recovery_manager.detect_interruption()
        print(f"  Interruption detected: {interruption['interrupted']}")
        
        # List all checkpoints
        checkpoints = recovery_manager.list_checkpoints()
        print(f"  Total checkpoints: {len(checkpoints)}")
        
        for cp in checkpoints:
            print(f"    - {cp['checkpoint_type']}: {cp['checkpoint_id'][:16]}...")
        
        # Get recovery statistics
        stats = recovery_manager.get_recovery_statistics()
        print(f"  Recovery state: {stats['recovery_state']}")
        print(f"  Total checkpoints: {stats['total_checkpoints']}")
        
        # Create a recovery plan (demonstration)
        if checkpoints:
            recovery_plan = recovery_manager.create_recovery_plan(checkpoint_id)
            print(f"  Recovery plan created: {recovery_plan.recovery_id}")
            print(f"  Risk level: {recovery_plan.risk_level}")
            print(f"  Actions: {len(recovery_plan.recovery_actions)}")
        
    except Exception as e:
        print(f"❌ Error during recovery demo: {e}")
    
    finally:
        # Shutdown recovery manager
        recovery_manager.shutdown()
    
    print("✅ Recovery system example completed")
    print()


def example_5_configuration_system():
    """Example 5: Configuration management."""
    print("⚙️  Example 5: Configuration System")
    print("=" * 50)
    
    try:
        # Load default configuration
        config = get_config()
        print("📋 Loaded default configuration")
        
        # Display some configuration values
        streaming_config = config.get('streaming_config', {})
        print(f"  Batch size: {streaming_config.get('batch_size', 'not set')}")
        print(f"  Max workers: {streaming_config.get('max_workers', 'not set')}")
        print(f"  Memory limit: {streaming_config.get('memory_limit_mb', 'not set')} MB")
        
        recovery_config = config.get('recovery_config', {})
        print(f"  Auto checkpoints: {recovery_config.get('enable_auto_checkpoints', 'not set')}")
        print(f"  Checkpoint interval: {recovery_config.get('checkpoint_interval', 'not set')} seconds")
        
        processing_config = config.get('processing', {})
        formats = processing_config.get('audio_formats', [])
        print(f"  Supported formats: {len(formats)} types")
        print(f"    {', '.join(formats[:5])}{'...' if len(formats) > 5 else ''}")
        
        # Try to load a custom configuration file
        custom_config_path = Path("config/default.json")
        if custom_config_path.exists():
            custom_config = get_config(str(custom_config_path))
            print(f"  ✅ Loaded custom config from: {custom_config_path}")
            print(f"  Config version: {custom_config.get('version', 'unknown')}")
        else:
            print(f"  ⚠️  Custom config not found: {custom_config_path}")
        
    except Exception as e:
        print(f"❌ Error during configuration demo: {e}")
    
    print("✅ Configuration example completed")
    print()


def cleanup_example_files():
    """Clean up any files created during examples."""
    print("🧹 Cleaning up example files...")
    
    cleanup_paths = [
        "example_music",
        "example_workspace", 
        "example_test.mp3",
        "example_source.txt",
        "example_target.txt"
    ]
    
    for path_str in cleanup_paths:
        path = Path(path_str)
        try:
            if path.is_file():
                path.unlink()
                print(f"  Removed file: {path}")
            elif path.is_dir():
                import shutil
                shutil.rmtree(path)
                print(f"  Removed directory: {path}")
        except Exception as e:
            print(f"  Warning: Could not remove {path}: {e}")
    
    print("✅ Cleanup completed")


def main():
    """Run all basic usage examples."""
    print("🎵 DJ Music Cleanup Tool - Basic Usage Examples")
    print("=" * 60)
    print()
    
    examples = [
        example_1_basic_file_discovery,
        example_2_integrity_checking,
        example_3_atomic_operations,
        example_4_recovery_system,
        example_5_configuration_system,
    ]
    
    for i, example in enumerate(examples, 1):
        try:
            example()
        except KeyboardInterrupt:
            print("\n⚠️  Examples interrupted by user")
            break
        except Exception as e:
            print(f"❌ Error in example {i}: {e}")
            print()
    
    # Cleanup
    cleanup_example_files()
    
    print("🎉 All examples completed!")
    print()
    print("Next steps:")
    print("  - See examples/advanced_config.py for advanced features")
    print("  - See examples/batch_processing.py for automation")
    print("  - Read docs/usage.md for comprehensive documentation")


if __name__ == "__main__":
    main()