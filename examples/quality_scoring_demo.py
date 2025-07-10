#!/usr/bin/env python3
"""
Quality Scoring Demo

Demonstriert das umfassende Quality Scoring System mit Datei-Umbenennung,
Metadaten-Tagging und automatischer Organisation.
"""

import sys
import json
import argparse
from pathlib import Path
from typing import List

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from music_cleanup.audio import (
    IntegratedQualityManager,
    QualityProcessingOptions,
    ScoringProfile
)


def demo_single_file(file_path: str, rename: bool = False, tag: bool = True):
    """Demonstriert Quality Scoring für eine einzelne Datei"""
    
    print(f"\n{'='*70}")
    print(f"🎵 QUALITY SCORING DEMO: {Path(file_path).name}")
    print(f"{'='*70}")
    
    # Konfiguration
    options = QualityProcessingOptions(
        scoring_profile=ScoringProfile.DJ_PROFESSIONAL,
        rename_files=rename,
        tag_metadata=tag,
        backup_original_names=True
    )
    
    # Quality Manager
    manager = IntegratedQualityManager(options)
    
    # Processing
    result = manager.process_file(file_path)
    
    if not result.success:
        print(f"❌ Error: {result.error_message}")
        return
    
    # Results
    score = result.unified_score
    
    print(f"\n📊 UNIFIED QUALITY SCORE")
    print(f"  Final Score: {score.final_score:.1f}%")
    print(f"  Grade: {score.grade}")
    print(f"  Confidence: {score.confidence:.1f}%")
    
    print(f"\n📈 CATEGORY BREAKDOWN")
    print(f"  Technical Quality: {score.technical_quality:.1f}%")
    print(f"  Audio Fidelity: {score.audio_fidelity:.1f}%")
    print(f"  File Integrity: {score.file_integrity:.1f}%")
    print(f"  Reference Quality: {score.reference_quality:.1f}% (Gewichtung: 35%)")
    
    print(f"\n🔍 DETAILED COMPONENTS")
    comp = score.components
    print(f"  Bitrate Score: {comp.bitrate_score:.1f}")
    print(f"  Format Score: {comp.format_score:.1f}")
    print(f"  Frequency Score: {comp.frequency_score:.1f}")
    print(f"  Dynamic Range Score: {comp.dynamic_range_score:.1f}")
    print(f"  Health Score: {comp.health_score:.1f}")
    print(f"  Reference Score: {comp.reference_score:.1f}")
    
    # Issues and Strengths
    if score.issues_summary:
        print(f"\n⚠️  ISSUES FOUND ({len(score.issues_summary)})")
        for issue in score.issues_summary:
            print(f"  - {issue}")
    
    if score.strengths:
        print(f"\n✅ STRENGTHS ({len(score.strengths)})")
        for strength in score.strengths:
            print(f"  - {strength}")
    
    # Recommendation
    print(f"\n💡 RECOMMENDATION")
    print(f"  Action: {score.recommended_action}")
    print(f"  Keep File: {'✅ Yes' if score.is_keeper else '❌ No'}")
    print(f"  Needs Replacement: {'⚠️  Yes' if score.needs_replacement else '✅ No'}")
    
    # File Operations
    print(f"\n📁 FILE OPERATIONS")
    print(f"  Original: {result.original_path}")
    print(f"  Final: {result.final_path}")
    print(f"  Renamed: {'✅ Yes' if result.was_renamed else '❌ No'}")
    print(f"  Tagged: {'✅ Yes' if result.was_tagged else '❌ No'}")
    print(f"  Quarantined: {'⚠️  Yes' if result.was_quarantined else '✅ No'}")
    print(f"  Processing Time: {result.processing_time:.2f}s")
    
    # Reference Information
    if result.quality_report.reference_comparison:
        ref = result.quality_report.reference_comparison
        print(f"\n📚 REFERENCE COMPARISON")
        print(f"  References Found: {len(ref.all_references)}")
        if ref.best_reference:
            best = ref.best_reference
            print(f"  Best Version: {best.artist} - {best.title}")
            print(f"  Format: {best.format} ({best.quality.value})")
            print(f"  Release: {best.album} ({best.release_date})")
        print(f"  Relative Score: {ref.quality_score_relative:.1f}%")
        print(f"  Upgrade Available: {'⬆️  Yes' if ref.upgrade_available else '✅ No'}")


def demo_directory_processing(directory: str):
    """Demonstriert Batch-Processing eines Verzeichnisses"""
    
    print(f"\n{'='*70}")
    print(f"📁 DIRECTORY PROCESSING DEMO: {directory}")
    print(f"{'='*70}")
    
    # Konfiguration - nur Dateinamen und Metadaten
    options = QualityProcessingOptions(
        scoring_profile=ScoringProfile.DJ_PROFESSIONAL,
        rename_files=True,
        rename_pattern="{artist} - {title} [QS{score}%]",
        tag_metadata=True,
        organize_files=False,  # Keine Ordner-Organisation
        auto_quarantine_below=40.0
    )
    
    # Quality Manager
    manager = IntegratedQualityManager(options)
    
    # Processing
    results = manager.process_directory(directory, recursive=True)
    
    # Generate Report
    report = manager.generate_quality_report(results)
    
    print(f"\n📊 COLLECTION SUMMARY")
    summary = report['summary']
    print(f"  Total Files: {summary['total_files']}")
    print(f"  Successful: {summary['successful_analyses']}")
    print(f"  Failed: {summary['failed_analyses']}")
    print(f"  Average Score: {summary['average_score']:.1f}")
    print(f"  Score Range: {summary['min_score']:.1f} - {summary['max_score']:.1f}")
    
    print(f"\n🏆 QUALITY DISTRIBUTION")
    dist = report['quality_distribution']
    total = summary['successful_analyses']
    print(f"  Excellent (90+): {dist['excellent_90_plus']} ({dist['excellent_90_plus']/total*100:.1f}%)")
    print(f"  Good (75-89): {dist['good_75_89']} ({dist['good_75_89']/total*100:.1f}%)")
    print(f"  Acceptable (60-74): {dist['acceptable_60_74']} ({dist['acceptable_60_74']/total*100:.1f}%)")
    print(f"  Poor (<60): {dist['poor_below_60']} ({dist['poor_below_60']/total*100:.1f}%)")
    
    print(f"\n📋 GRADE DISTRIBUTION")
    for grade, count in sorted(report['grade_distribution'].items()):
        percentage = count / total * 100
        print(f"  Grade {grade}: {count} files ({percentage:.1f}%)")
    
    print(f"\n🔧 FILE OPERATIONS")
    ops = report['file_operations']
    print(f"  Renamed: {ops['renamed']}")
    print(f"  Tagged: {ops['tagged']}")
    print(f"  Organized: {ops['organized']}")
    print(f"  Quarantined: {ops['quarantined']}")
    
    if report['common_issues']:
        print(f"\n⚠️  COMMON ISSUES")
        for issue, count in list(report['common_issues'].items())[:5]:
            print(f"  {issue}: {count} files")
    
    print(f"\n💡 COLLECTION RECOMMENDATIONS")
    for rec in report['recommendations']:
        print(f"  - {rec}")
    
    print(f"\n📁 DATEI-OPERATIONEN")
    renamed_count = len([r for r in results if r.was_renamed])
    tagged_count = len([r for r in results if r.was_tagged])
    print(f"  Dateien umbenannt: {renamed_count}")
    print(f"  Metadaten getaggt: {tagged_count}")
    print(f"  Quality-Info in Dateinamen und Metadaten gespeichert")
    
    return results, report


def export_detailed_report(results: list, report: dict, output_file: str):
    """Exportiert detaillierten Report"""
    
    # Enhanced report with individual file details
    enhanced_report = {
        **report,
        'scoring_methodology': {
            'profile': 'DJ_PROFESSIONAL',
            'weights': {
                'technical_quality': 0.25,
                'audio_fidelity': 0.25,
                'file_integrity': 0.15,
                'reference_quality': 0.35  # Deutlich höher gewichtet
            },
            'grade_thresholds': {
                'A+': 95, 'A': 90, 'A-': 85,
                'B+': 80, 'B': 75, 'B-': 70,
                'C+': 65, 'C': 60, 'C-': 55,
                'D': 50, 'F': 0
            }
        }
    }
    
    with open(output_file, 'w') as f:
        json.dump(enhanced_report, f, indent=2)
    
    print(f"\n📄 Detailed report exported to: {output_file}")


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='Quality Scoring Demo for DJ Music Cleanup'
    )
    parser.add_argument(
        'path',
        help='Audio file or directory to analyze'
    )
    parser.add_argument(
        '--rename',
        action='store_true',
        help='Rename files with quality score'
    )
    parser.add_argument(
        '--no-tag',
        action='store_true',
        help='Skip metadata tagging'
    )
    # Organize options entfernt - nur Dateinamen und Metadaten
    parser.add_argument(
        '--export-report',
        help='Export detailed JSON report'
    )
    parser.add_argument(
        '--profile',
        choices=['dj_professional', 'dj_casual', 'archival'],
        default='dj_professional',
        help='Scoring profile to use'
    )
    
    args = parser.parse_args()
    
    path = Path(args.path)
    
    if not path.exists():
        print(f"❌ Error: '{args.path}' does not exist")
        sys.exit(1)
    
    if path.is_file():
        # Single file demo
        demo_single_file(
            str(path), 
            rename=args.rename, 
            tag=not args.no_tag
        )
    
    elif path.is_dir():
        # Directory demo
        results, report = demo_directory_processing(str(path))
        
        # Export report if requested
        if args.export_report:
            export_detailed_report(results, report, args.export_report)
    
    else:
        print(f"❌ Error: '{args.path}' is not a valid file or directory")
        sys.exit(1)


if __name__ == '__main__':
    main()