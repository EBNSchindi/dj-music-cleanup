#!/usr/bin/env python3
"""
Advanced Quality Analysis Example

Demonstriert die Verwendung der erweiterten Audio-Qualitätsanalyse
für DJ-Music-Cleanup.
"""

import sys
import json
from pathlib import Path
from typing import List, Dict, Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from music_cleanup.audio import (
    AdvancedQualityAnalyzer,
    AudioDefectDetector,
    QualityIssueType
)
from music_cleanup.core import Config


def analyze_file_quality(file_path: str) -> Dict[str, Any]:
    """Analysiert einzelne Datei mit beiden Analyzern"""
    
    # Erweiterte Qualitätsanalyse
    quality_analyzer = AdvancedQualityAnalyzer(
        min_quality_score=60.0,
        analysis_duration=30.0
    )
    
    # Defekt-Erkennung
    defect_detector = AudioDefectDetector(
        min_health_score=50.0
    )
    
    print(f"\n{'='*60}")
    print(f"Analyzing: {Path(file_path).name}")
    print(f"{'='*60}")
    
    # Quality Analysis
    quality_report = quality_analyzer.analyze_audio_quality(file_path)
    
    print(f"\n📊 Quality Analysis:")
    print(f"  - Quality Score: {quality_report.quality_score:.1f}/100")
    print(f"  - Category: {quality_analyzer.get_quality_category(quality_report.quality_score)}")
    print(f"  - High Quality: {'✅ Yes' if quality_report.is_high_quality else '❌ No'}")
    
    if quality_report.estimated_bitrate:
        print(f"  - Estimated Bitrate: {quality_report.estimated_bitrate}kbps")
    if quality_report.frequency_cutoff:
        print(f"  - Frequency Cutoff: {quality_report.frequency_cutoff:.0f}Hz")
    if quality_report.dynamic_range is not None:
        print(f"  - Dynamic Range: {quality_report.dynamic_range:.2f}")
    
    # Quality Issues
    if quality_report.issues:
        print(f"\n🔍 Quality Issues Found ({len(quality_report.issues)}):")
        for issue in quality_report.issues:
            print(f"  - {issue.issue_type.value}: {issue.description}")
            if issue.recommendation:
                print(f"    💡 {issue.recommendation}")
    
    # Health Analysis
    health_report = defect_detector.analyze_audio_health(file_path)
    
    print(f"\n🏥 Health Analysis:")
    print(f"  - Health Score: {health_report.health_score:.1f}/100")
    print(f"  - Healthy: {'✅ Yes' if health_report.is_healthy else '❌ No'}")
    
    # Defects
    if health_report.defects:
        print(f"\n⚠️  Defects Found ({len(health_report.defects)}):")
        for defect in health_report.defects:
            print(f"  - {defect.defect_type.value}: {defect.description}")
    
    # DJ-Ready Check
    is_dj_ready, reasons = quality_analyzer.is_dj_ready(quality_report)
    print(f"\n🎧 DJ-Ready: {'✅ Yes' if is_dj_ready else '❌ No'}")
    if not is_dj_ready:
        print("  Reasons:")
        for reason in reasons:
            print(f"  - {reason}")
    
    # Reference-based Quality Check
    if quality_report.reference_comparison:
        ref_comp = quality_report.reference_comparison
        print(f"\n📚 Reference Comparison:")
        print(f"  - References Found: {len(ref_comp.all_references)}")
        
        if ref_comp.best_reference:
            best_ref = ref_comp.best_reference
            print(f"  - Best Reference: {best_ref.artist} - {best_ref.title}")
            print(f"    • Format: {best_ref.format}")
            print(f"    • Quality: {best_ref.quality.value}")
            print(f"    • Release: {best_ref.album} ({best_ref.release_date})")
            if best_ref.label:
                print(f"    • Label: {best_ref.label}")
        
        print(f"  - Quality Score (relative): {ref_comp.quality_score_relative:.1f}%")
        print(f"  - Upgrade Available: {'⬆️  Yes' if ref_comp.upgrade_available else '✅ No'}")
        print(f"  - Is Best Version: {'👑 Yes' if ref_comp.is_best_available else '❌ No'}")
        
        if ref_comp.recommendations:
            print(f"\n  💡 Recommendations:")
            for rec in ref_comp.recommendations:
                print(f"    - {rec}")
    
    # Critical Corruption Check
    is_corrupted, corruption_reasons = defect_detector.is_critically_corrupted({'file_path': file_path})
    if is_corrupted:
        print(f"\n💀 CRITICAL CORRUPTION DETECTED:")
        for reason in corruption_reasons:
            print(f"  - {reason}")
    
    return {
        'file': file_path,
        'quality_score': quality_report.quality_score,
        'health_score': health_report.health_score,
        'is_dj_ready': is_dj_ready,
        'is_corrupted': is_corrupted,
        'quality_issues': len(quality_report.issues),
        'defects': len(health_report.defects),
        'upgrade_available': quality_report.upgrade_available,
        'is_best_version': quality_report.is_best_version
    }


def analyze_directory(directory: str, extensions: List[str] = None) -> None:
    """Analysiert alle Audio-Dateien in einem Verzeichnis"""
    
    if extensions is None:
        extensions = ['.mp3', '.flac', '.wav', '.m4a', '.aiff']
    
    path = Path(directory)
    if not path.exists():
        print(f"Error: Directory '{directory}' does not exist")
        return
    
    # Sammle Audio-Dateien
    audio_files = []
    for ext in extensions:
        audio_files.extend(path.rglob(f'*{ext}'))
    
    if not audio_files:
        print(f"No audio files found in '{directory}'")
        return
    
    print(f"\nFound {len(audio_files)} audio files to analyze")
    
    # Analysiere Dateien
    results = []
    quality_analyzer = AdvancedQualityAnalyzer()
    
    for audio_file in audio_files:
        try:
            result = analyze_file_quality(str(audio_file))
            results.append(result)
        except Exception as e:
            print(f"\n❌ Error analyzing {audio_file.name}: {e}")
    
    # Zusammenfassung
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    
    if results:
        avg_quality = sum(r['quality_score'] for r in results) / len(results)
        avg_health = sum(r['health_score'] for r in results) / len(results)
        dj_ready_count = sum(1 for r in results if r['is_dj_ready'])
        corrupted_count = sum(1 for r in results if r['is_corrupted'])
        
        print(f"\n📊 Overall Statistics:")
        print(f"  - Files Analyzed: {len(results)}")
        print(f"  - Average Quality Score: {avg_quality:.1f}/100")
        print(f"  - Average Health Score: {avg_health:.1f}/100")
        print(f"  - DJ-Ready Files: {dj_ready_count}/{len(results)} ({dj_ready_count/len(results)*100:.1f}%)")
        print(f"  - Corrupted Files: {corrupted_count}/{len(results)} ({corrupted_count/len(results)*100:.1f}%)")
        
        # Quality Distribution
        excellent = sum(1 for r in results if r['quality_score'] >= 90)
        good = sum(1 for r in results if 75 <= r['quality_score'] < 90)
        acceptable = sum(1 for r in results if 60 <= r['quality_score'] < 75)
        poor = sum(1 for r in results if r['quality_score'] < 60)
        
        print(f"\n📈 Quality Distribution:")
        print(f"  - Excellent (90+): {excellent} files")
        print(f"  - Good (75-89): {good} files")
        print(f"  - Acceptable (60-74): {acceptable} files")
        print(f"  - Poor (<60): {poor} files")
        
        # Top Issues
        issue_types = {}
        for result in results:
            if result['quality_issues'] > 0:
                # We don't have direct access to issue types in summary
                # In real implementation, we would track this
                pass
        
        # Get analyzer statistics
        stats = quality_analyzer.get_statistics()
        if stats['upsampling_rate'] > 0:
            print(f"\n⚠️  Upsampling detected in {stats['upsampling_rate']:.1f}% of files")
        if stats['compression_rate'] > 0:
            print(f"⚠️  Over-compression detected in {stats['compression_rate']:.1f}% of files")


def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Advanced Audio Quality Analysis for DJ Music Libraries'
    )
    parser.add_argument(
        'path',
        help='Audio file or directory to analyze'
    )
    parser.add_argument(
        '--min-quality',
        type=float,
        default=60.0,
        help='Minimum quality score for "high quality" (default: 60.0)'
    )
    parser.add_argument(
        '--extensions',
        nargs='+',
        help='File extensions to analyze (default: mp3 flac wav m4a aiff)'
    )
    parser.add_argument(
        '--export',
        help='Export results to JSON file'
    )
    
    args = parser.parse_args()
    
    path = Path(args.path)
    
    if path.is_file():
        # Einzeldatei-Analyse
        result = analyze_file_quality(str(path))
        
        if args.export:
            with open(args.export, 'w') as f:
                json.dump(result, f, indent=2)
            print(f"\nResults exported to: {args.export}")
    
    elif path.is_dir():
        # Verzeichnis-Analyse
        analyze_directory(str(path), args.extensions)
    
    else:
        print(f"Error: '{args.path}' is not a valid file or directory")
        sys.exit(1)


if __name__ == '__main__':
    main()