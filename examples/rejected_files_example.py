#!/usr/bin/env python3
"""
Rejected Files System Example for DJ Music Cleanup Tool

This example demonstrates the comprehensive rejected files system that moves
problematic files to organized rejected/ directories instead of deleting them.

Features demonstrated:
- Duplicate handling with numbered suffixes
- Low quality file rejection with thresholds
- Corrupted file quarantine
- Rejection manifest tracking
- File recovery and analysis
"""

import os
import sys
import json
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from music_cleanup.core.rejected_handler import RejectedHandler, RejectionReason
from music_cleanup.core.quality_rejection_handler import QualityRejectionHandler
from music_cleanup.core.config_manager import ConfigManager


def main():
    """Demonstrate the rejected files system"""
    
    print("🗂️  DJ Music Cleanup - Rejected Files System Demo")
    print("=" * 60)
    
    # Load configuration
    config_path = Path(__file__).parent.parent / 'config' / 'metadata_first.json'
    config_manager = ConfigManager(config_path)
    config = config_manager.get_config()
    
    # Initialize handlers
    rejected_handler = RejectedHandler(config)
    quality_handler = QualityRejectionHandler(config)
    
    print("\\n📋 Rejected Files System Overview")
    print("-" * 40)
    print("✅ NO files are ever deleted")
    print("✅ ALL rejected files are moved to organized rejected/ directories")
    print("✅ Detailed manifest tracks all rejections with reasons")
    print("✅ Files can be easily recovered or analyzed")
    print("✅ Folder structure preserved for easy navigation")
    
    # Demonstrate different rejection scenarios
    demonstrate_duplicate_rejection(rejected_handler)
    demonstrate_quality_rejection(rejected_handler, quality_handler)
    demonstrate_corruption_rejection(rejected_handler)
    demonstrate_manifest_system(rejected_handler)
    demonstrate_recovery_system(rejected_handler)
    demonstrate_analysis_tools(rejected_handler, quality_handler)
    
    print("\\n" + "=" * 60)
    print("✨ Rejected Files Demo Complete!")
    print("=" * 60)


def demonstrate_duplicate_rejection(rejected_handler):
    """Demonstrate duplicate file rejection"""
    print("\\n🔄 Duplicate File Rejection")
    print("-" * 40)
    
    # Simulate duplicate files
    example_duplicates = [
        {
            'file_path': './test_files/Swedish House Mafia - Don\\'t You Worry Child.mp3',
            'chosen_file': './organized/Electronic/2010s/Swedish House Mafia - Don\\'t You Worry Child [QS92%].mp3',
            'quality_score': 85.5,
            'group_id': 'group_1_timestamp',
            'rank': 2,
            'metadata': {
                'artist': 'Swedish House Mafia',
                'title': 'Don\\'t You Worry Child',
                'year': '2012',
                'genre': 'Electronic'
            }
        },
        {
            'file_path': './test_files/Swedish House Mafia - Don\\'t You Worry Child (Low Quality).mp3',
            'chosen_file': './organized/Electronic/2010s/Swedish House Mafia - Don\\'t You Worry Child [QS92%].mp3',
            'quality_score': 65.2,
            'group_id': 'group_1_timestamp',
            'rank': 3,
            'metadata': {
                'artist': 'Swedish House Mafia',
                'title': 'Don\\'t You Worry Child',
                'year': '2012',
                'genre': 'Electronic'
            }
        }
    ]
    
    print("Example duplicate scenario:")
    print("1. Best version (QS 92%) → organized/ directory")
    print("2. Medium duplicate (QS 85.5%) → rejected/duplicates/ with _duplicate_2 suffix")
    print("3. Low duplicate (QS 65.2%) → rejected/duplicates/ with _duplicate_3 suffix")
    print()
    
    for duplicate in example_duplicates:
        # This would actually move the file in real usage
        print(f"Rejecting duplicate #{duplicate['rank']}:")
        print(f"  Original: {Path(duplicate['file_path']).name}")
        print(f"  Quality Score: {duplicate['quality_score']:.1f}%")
        print(f"  Chosen instead: {Path(duplicate['chosen_file']).name}")
        print(f"  → rejected/duplicates/{Path(duplicate['file_path']).stem}_duplicate_{duplicate['rank']}{Path(duplicate['file_path']).suffix}")
        print()
    
    print("✅ Benefits:")
    print("  - No files lost - all duplicates preserved")
    print("  - Clear ranking system with suffixes")
    print("  - Easy to find which file was chosen instead")
    print("  - Can recover duplicates if needed")


def demonstrate_quality_rejection(rejected_handler, quality_handler):
    """Demonstrate quality-based rejection"""
    print("\\n🎯 Quality-Based Rejection")
    print("-" * 40)
    
    # Simulate files with different quality scores
    example_files = [
        {
            'file_path': './test_files/high_quality_track.flac',
            'quality_score': 95.0,
            'bitrate': 1411,
            'format': 'FLAC',
            'metadata': {'artist': 'Artist A', 'title': 'Track 1'}
        },
        {
            'file_path': './test_files/good_quality_track.mp3',
            'quality_score': 82.5,
            'bitrate': 320,
            'format': 'MP3',
            'metadata': {'artist': 'Artist B', 'title': 'Track 2'}
        },
        {
            'file_path': './test_files/acceptable_quality_track.mp3',
            'quality_score': 68.0,
            'bitrate': 192,
            'format': 'MP3',
            'metadata': {'artist': 'Artist C', 'title': 'Track 3'}
        },
        {
            'file_path': './test_files/low_quality_track.mp3',
            'quality_score': 45.0,
            'bitrate': 128,
            'format': 'MP3',
            'metadata': {'artist': 'Artist D', 'title': 'Track 4'}
        },
        {
            'file_path': './test_files/very_low_quality_track.mp3',
            'quality_score': 25.0,
            'bitrate': 64,
            'format': 'MP3',
            'metadata': {'artist': 'Artist E', 'title': 'Track 5'}
        }
    ]
    
    # Get quality thresholds from config
    min_score = quality_handler.min_quality_score
    auto_reject = quality_handler.auto_reject_below
    
    print(f"Quality thresholds:")
    print(f"  Minimum acceptable: {min_score}%")
    print(f"  Auto-reject below: {auto_reject}%")
    print()
    
    print("Quality analysis results:")
    for file_info in example_files:
        quality_score = file_info['quality_score']
        filename = Path(file_info['file_path']).name
        
        if quality_score >= min_score:
            action = "✅ KEEP"
            destination = "organized/"
        elif quality_score >= auto_reject:
            action = "⚠️  REJECT (low quality)"
            destination = "rejected/low_quality/"
        else:
            action = "❌ REJECT (very low quality)"
            destination = "rejected/low_quality/"
        
        print(f"  {filename}")
        print(f"    Quality Score: {quality_score}% | {file_info['bitrate']} kbps {file_info['format']}")
        print(f"    Action: {action}")
        print(f"    Destination: {destination}")
        print()
    
    print("✅ Benefits:")
    print("  - Configurable quality thresholds")
    print("  - No data loss - low quality files preserved")
    print("  - Easy to review and potentially recover files")
    print("  - Quality score preserved in manifest")


def demonstrate_corruption_rejection(rejected_handler):
    """Demonstrate corrupted file rejection"""
    print("\\n🚫 Corrupted File Rejection")
    print("-" * 40)
    
    # Simulate corrupted files
    corrupted_examples = [
        {
            'file_path': './test_files/truncated_file.mp3',
            'corruption_type': 'truncated_file',
            'details': 'File appears to be cut off mid-stream',
            'health_score': 15.0,
            'metadata': {'artist': 'Unknown', 'title': 'Truncated Track'}
        },
        {
            'file_path': './test_files/corrupted_header.mp3',
            'corruption_type': 'corrupted_header',
            'details': 'MP3 header is corrupted, cannot read metadata',
            'health_score': 5.0,
            'metadata': {}
        },
        {
            'file_path': './test_files/silent_file.wav',
            'corruption_type': 'complete_silence',
            'details': 'File contains only silence - likely corrupted',
            'health_score': 0.0,
            'metadata': {'artist': 'Test', 'title': 'Silent Track'}
        }
    ]
    
    print("Corruption detection and quarantine:")
    for corrupted in corrupted_examples:
        filename = Path(corrupted['file_path']).name
        print(f"🚫 {filename}")
        print(f"  Issue: {corrupted['corruption_type']}")
        print(f"  Details: {corrupted['details']}")
        print(f"  Health Score: {corrupted['health_score']}%")
        print(f"  → rejected/corrupted/{filename}")
        print()
    
    print("✅ Benefits:")
    print("  - Corrupted files safely quarantined")
    print("  - Detailed corruption analysis preserved")
    print("  - Files can be examined or attempted recovery")
    print("  - Prevents corruption from spreading to organized library")


def demonstrate_manifest_system(rejected_handler):
    """Demonstrate the rejection manifest system"""
    print("\\n📋 Rejection Manifest System")
    print("-" * 40)
    
    # Simulate manifest data
    manifest_example = {
        "metadata": {
            "created_at": "2024-01-15T10:30:00",
            "updated_at": "2024-01-15T14:45:00", 
            "total_rejections": 157,
            "version": "2.0"
        },
        "rejections": [
            {
                "original_path": "./music/Artist - Track (Duplicate).mp3",
                "rejected_path": "./rejected/duplicates/Artist - Track (Duplicate)_duplicate_2.mp3",
                "filename": "Artist - Track (Duplicate).mp3",
                "reason": "duplicate",
                "quality_score": 75.5,
                "chosen_file": "./organized/Electronic/2020s/Artist - Track [QS89%].mp3",
                "duplicate_group_id": "group_5_1705320600",
                "duplicate_rank": 2,
                "artist": "Artist",
                "title": "Track",
                "year": "2023",
                "genre": "Electronic",
                "rejected_at": "2024-01-15T12:30:00",
                "notes": "Duplicate #2 in group group_5_1705320600"
            },
            {
                "original_path": "./music/Low Quality Song.mp3",
                "rejected_path": "./rejected/low_quality/Low Quality Song.mp3",
                "filename": "Low Quality Song.mp3",
                "reason": "low_quality",
                "quality_score": 42.0,
                "threshold_used": 70.0,
                "artist": "Some Artist",
                "title": "Low Quality Song",
                "rejected_at": "2024-01-15T14:15:00",
                "notes": "Quality score 42.0 below threshold 70"
            }
        ]
    }
    
    print("Manifest structure (rejected_manifest.json):")
    print(json.dumps(manifest_example, indent=2)[:800] + "...")
    print()
    
    print("✅ Manifest Features:")
    print("  - Complete audit trail of all rejections")
    print("  - Detailed reason for each rejection")
    print("  - Original and new file paths")
    print("  - Quality scores and thresholds")
    print("  - Metadata preservation")
    print("  - Timestamps for all operations")
    print("  - Duplicate group tracking")
    print("  - Export to CSV for analysis")


def demonstrate_recovery_system(rejected_handler):
    """Demonstrate file recovery capabilities"""
    print("\\n♻️  File Recovery System")
    print("-" * 40)
    
    print("Recovery scenarios:")
    print()
    
    print("1. 🔄 Restore accidentally rejected file:")
    print("   - Find file in rejection manifest")
    print("   - Use rejected_handler.restore_file()")
    print("   - File moved back to original or specified location")
    print("   - Manifest updated to remove entry")
    print()
    
    print("2. 📊 Analyze rejection patterns:")
    print("   - Export manifest to CSV")
    print("   - Analyze quality distribution")
    print("   - Identify systemic issues")
    print("   - Adjust thresholds if needed")
    print()
    
    print("3. 🔍 Review specific rejection categories:")
    print("   rejections_by_reason = rejected_handler.get_rejections_by_reason('low_quality')")
    print("   low_quality_files = rejected_handler.get_rejections_by_quality(40, 60)")
    print()
    
    print("4. 🧹 Cleanup and maintenance:")
    print("   - Remove empty directories")
    print("   - Archive old rejection data")
    print("   - Clear manifest entries for deleted files")
    print()
    
    print("✅ Recovery Benefits:")
    print("  - No permanent data loss")
    print("  - Easy file restoration")
    print("  - Pattern analysis for improvement")
    print("  - Flexible recovery options")


def demonstrate_analysis_tools(rejected_handler, quality_handler):
    """Demonstrate analysis and reporting tools"""
    print("\\n📊 Analysis & Reporting Tools")
    print("-" * 40)
    
    # Simulate statistics
    rejection_stats = {
        'total_rejected': 157,
        'duplicates': 89,
        'low_quality': 52,
        'corrupted': 16,
        'other': 0,
        'rejection_rate': {
            'duplicates': 56.7,
            'low_quality': 33.1,
            'corrupted': 10.2,
            'other': 0.0
        }
    }
    
    quality_stats = {
        'files_analyzed': 1250,
        'files_rejected': 52,
        'files_kept': 1198,
        'rejection_rate': 4.2,
        'space_freed_mb': 245.8,
        'thresholds': {
            'min_score': 70,
            'auto_reject_below': 50,
            'production_threshold': 85
        }
    }
    
    print("Rejection Statistics:")
    print(f"  Total files rejected: {rejection_stats['total_rejected']}")
    print(f"  Duplicates: {rejection_stats['duplicates']} ({rejection_stats['rejection_rate']['duplicates']:.1f}%)")
    print(f"  Low quality: {rejection_stats['low_quality']} ({rejection_stats['rejection_rate']['low_quality']:.1f}%)")
    print(f"  Corrupted: {rejection_stats['corrupted']} ({rejection_stats['rejection_rate']['corrupted']:.1f}%)")
    print()
    
    print("Quality Analysis:")
    print(f"  Files analyzed: {quality_stats['files_analyzed']}")
    print(f"  Rejection rate: {quality_stats['rejection_rate']:.1f}%")
    print(f"  Space freed: {quality_stats['space_freed_mb']:.1f} MB")
    print(f"  Quality thresholds: Min {quality_stats['thresholds']['min_score']}%, Auto-reject <{quality_stats['thresholds']['auto_reject_below']}%")
    print()
    
    print("Available Reports:")
    print("  📋 rejected_manifest.json - Complete rejection audit trail")
    print("  📊 rejection_analysis.csv - CSV export for spreadsheet analysis")
    print("  📈 quality_distribution.json - Quality score analysis")
    print("  🗂️  Directory structure preserved in rejected/ folders")
    print()
    
    print("✅ Analysis Benefits:")
    print("  - Comprehensive statistics and metrics")
    print("  - Export capabilities for external analysis")
    print("  - Quality trend monitoring")
    print("  - Threshold optimization guidance")


def demonstrate_workflow_integration():
    """Demonstrate how rejection system integrates with main workflow"""
    print("\\n🔄 Workflow Integration")
    print("-" * 40)
    
    workflow_steps = [
        "1. 🎵 Audio file discovery and initial scanning",
        "2. 🔍 Metadata extraction (fingerprint → tags → filename → queue)",
        "3. 📊 Quality analysis and scoring",
        "4. 🚫 Corruption detection and health checking",
        "",
        "5. 🗂️  REJECTION SYSTEM INTEGRATION:",
        "   ├─ Corrupted files → rejected/corrupted/",
        "   ├─ Low quality files → rejected/low_quality/",
        "   └─ Duplicates → rejected/duplicates/ (with suffixes)",
        "",
        "6. ✅ Healthy, high-quality files → organized/genre/decade/",
        "7. 📋 All rejections tracked in rejected_manifest.json",
        "8. 📊 Statistics and reports generated"
    ]
    
    for step in workflow_steps:
        print(step)
    
    print()
    print("✅ Integration Benefits:")
    print("  - Seamless integration with existing workflow")
    print("  - No workflow disruption - transparent operation")
    print("  - Enhanced safety with no data loss")
    print("  - Improved organization and tracking")


if __name__ == "__main__":
    try:
        main()
        demonstrate_workflow_integration()
    except KeyboardInterrupt:
        print("\\n👋 Demo interrupted by user")
    except Exception as e:
        print(f"\\n❌ Error: {e}")
        print("\\nNote: This demo shows the rejection system capabilities.")
        print("In actual usage, files would be moved according to configuration.")