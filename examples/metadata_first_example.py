#!/usr/bin/env python3
"""
Metadata-First DJ Music Cleanup Example

This example demonstrates the new metadata-first approach where:
1. Audio Fingerprint Lookup is ALWAYS attempted first
2. File Tags are used as fallback
3. Filename Parsing is used as last resort
4. Unknown files are queued for manual review (NEVER processed as "Unknown")

The result is a clean, organized library with accurate metadata and quality scores.
"""

import os
import sys
import json
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from music_cleanup.metadata.metadata_manager import MetadataManager
from music_cleanup.core.config_manager import ConfigManager
from music_cleanup.utils.progress import ProgressTracker

def main():
    """Demonstrate the metadata-first approach"""
    
    print("🎵 DJ Music Cleanup - Metadata-First Approach Demo")
    print("=" * 60)
    
    # Load metadata-first configuration
    config_path = Path(__file__).parent.parent / 'config' / 'metadata_first.json'
    config_manager = ConfigManager(config_path)
    config = config_manager.get_config()
    
    # Initialize metadata manager
    metadata_manager = MetadataManager(config)
    
    # Example files to process
    example_files = [
        "./test_files/128 - Swedish House Mafia - Don't You Worry Child (Original Mix).mp3",
        "./test_files/Deadmau5 - Strobe (Original Mix).mp3",
        "./test_files/01. Unknown Artist - Mystery Track.mp3",
        "./test_files/corrupted_filename_###.mp3",
        "./test_files/artist_title_with_good_tags.mp3"
    ]
    
    print("\\n🔍 Processing Files with Metadata-First Approach")
    print("-" * 60)
    
    results = []
    
    for file_path in example_files:
        print(f"\\nProcessing: {Path(file_path).name}")
        print("-" * 40)
        
        # This is the key call - it follows the strict priority order
        metadata_result = metadata_manager.get_metadata(file_path, quality_score=85.0)
        
        if metadata_result:
            print(f"✅ Success: {metadata_result.source}")
            print(f"   Artist: {metadata_result.artist}")
            print(f"   Title: {metadata_result.title}")
            print(f"   Year: {metadata_result.year}")
            print(f"   Genre: {metadata_result.genre}")
            print(f"   Confidence: {metadata_result.confidence:.2f}")
            
            # Generate the new filename with quality score
            new_filename = metadata_result.get_filename_pattern()
            print(f"   New filename: {new_filename}")
            
            # Generate folder structure
            folder_path = metadata_result.get_folder_path()
            print(f"   Folder: {folder_path}")
            
            if metadata_result.needs_verification:
                print("   ⚠️  Needs verification (from file tags)")
            if metadata_result.needs_review:
                print("   🔍 Needs review (from filename parsing)")
            
            results.append(metadata_result)
        else:
            print("📋 Queued for manual review")
            print("   Reason: Insufficient metadata confidence")
    
    print("\\n" + "=" * 60)
    print("📊 Processing Statistics")
    print("=" * 60)
    
    stats = metadata_manager.get_stats()
    print(f"Total files processed: {stats['total_processed']}")
    print(f"Fingerprint successes: {stats['fingerprint_success']} ({stats['success_rate']['fingerprint']}%)")
    print(f"Tag fallbacks: {stats['tags_fallback']} ({stats['success_rate']['tags']}%)")
    print(f"Filename parsing: {stats['filename_parsing']} ({stats['success_rate']['filename']}%)")
    print(f"Queued for review: {stats['queued_for_review']} ({stats['success_rate']['queued']}%)")
    
    # Show metadata queue statistics
    print("\\n📋 Metadata Queue Statistics")
    print("-" * 40)
    queue_stats = metadata_manager.get_metadata_queue_stats()
    print(f"Total queued: {queue_stats['total_queued']}")
    print(f"Pending review: {queue_stats['pending_review']}")
    print(f"Completed: {queue_stats['completed_review']}")
    print(f"Rejected: {queue_stats['rejected']}")
    
    print("\\n🔧 Metadata Queue Management")
    print("-" * 40)
    
    # Export queued files to CSV for bulk editing
    csv_path = metadata_manager.export_metadata_queue_to_csv()
    if csv_path:
        print(f"✅ Exported queue to CSV: {csv_path}")
        print("   Edit this file to add metadata for unknown files")
        print("   Then import back using import_metadata_queue_from_csv()")
    
    # Demonstrate processing completed queue files
    print("\\n♻️  Processing Completed Queue Files")
    print("-" * 40)
    
    completed_results = metadata_manager.process_completed_queue_files()
    if completed_results:
        print(f"✅ Processed {len(completed_results)} completed files from queue")
        for result in completed_results:
            print(f"   - {result.artist} - {result.title} (manual metadata)")
    else:
        print("📝 No completed files in queue")
        print("   To test this feature:")
        print("   1. Export queue to CSV")
        print("   2. Add metadata to the CSV file")
        print("   3. Set review_status to 'completed'")
        print("   4. Import the CSV back")
    
    print("\\n📁 Example File Organization")
    print("-" * 40)
    
    for result in results:
        folder_path = result.get_folder_path()
        filename = result.get_filename_pattern()
        full_path = f"{folder_path}/{filename}"
        print(f"   {full_path}")
    
    print("\\n🎯 Key Benefits of Metadata-First Approach")
    print("-" * 60)
    print("✅ NO 'Unknown Artist' files ever created")
    print("✅ Audio fingerprinting provides accurate metadata")
    print("✅ Quality scores included in filenames")
    print("✅ Systematic handling of problematic files")
    print("✅ Manual review queue for perfect organization")
    print("✅ Confidence-based processing ensures quality")
    
    print("\\n🔄 Recommended Workflow")
    print("-" * 40)
    print("1. Run cleanup with metadata-first configuration")
    print("2. Export metadata queue to CSV")
    print("3. Manually review and edit unknown files")
    print("4. Import completed metadata back")
    print("5. Re-run cleanup to process completed files")
    print("6. Enjoy your perfectly organized DJ library!")
    
    print("\\n" + "=" * 60)
    print("✨ Demo Complete!")
    print("=" * 60)

def demonstrate_naming_patterns():
    """Demonstrate different naming patterns"""
    print("\\n🏷️  Naming Pattern Examples")
    print("-" * 40)
    
    # Example metadata result
    from music_cleanup.metadata.metadata_manager import MetadataResult
    
    example_result = MetadataResult(
        artist="Swedish House Mafia",
        title="Don't You Worry Child",
        year="2012",
        genre="Electronic",
        source="acoustid",
        confidence=0.92,
        quality_score=89.5
    )
    
    patterns = [
        "{year} - {artist} - {title} - QS{score}%",
        "{artist} - {title} ({year}) - QS{score}%",
        "{artist} - {title} - {year} - Quality {score}%",
        "[{year}] {artist} - {title} (QS{score}%)",
    ]
    
    for pattern in patterns:
        filename = example_result.get_filename_pattern(pattern)
        print(f"   Pattern: {pattern}")
        print(f"   Result:  {filename}")
        print()

def demonstrate_queue_workflow():
    """Demonstrate the metadata queue workflow"""
    print("\\n📋 Metadata Queue Workflow")
    print("-" * 40)
    
    print("1. Files with insufficient metadata are queued:")
    print("   - No fingerprint match found")
    print("   - File tags incomplete or missing")
    print("   - Filename parsing failed")
    print("   - Confidence scores too low")
    print()
    
    print("2. Queue creates structured data:")
    print("   - metadata_queue/queued_TIMESTAMP/original_file.mp3")
    print("   - metadata_queue/metadata_issues.json")
    print("   - metadata_queue/metadata_export.csv")
    print()
    
    print("3. Manual review process:")
    print("   - Export queue to CSV")
    print("   - Edit CSV with correct metadata")
    print("   - Set review_status to 'completed'")
    print("   - Import CSV back")
    print()
    
    print("4. Process completed files:")
    print("   - Retrieve manually corrected metadata")
    print("   - Process files with perfect metadata")
    print("   - Clean up queue by removing completed files")

if __name__ == "__main__":
    try:
        main()
        demonstrate_naming_patterns()
        demonstrate_queue_workflow()
    except KeyboardInterrupt:
        print("\\n👋 Demo interrupted by user")
    except Exception as e:
        print(f"\\n❌ Error: {e}")
        print("\\nNote: This demo requires:")
        print("- Chromaprint/fpcalc installed for fingerprinting")
        print("- AcoustID API key for metadata lookup")
        print("- Test audio files in ./test_files/")