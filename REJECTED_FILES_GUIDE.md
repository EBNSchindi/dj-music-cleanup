# Rejected Files System Guide

The DJ Music Cleanup Tool features a comprehensive rejected files system that **never deletes files**. Instead, all problematic files are moved to organized `rejected/` directories with detailed tracking and recovery capabilities.

## 🎯 Core Philosophy

**NO FILES ARE EVER DELETED** - Everything is preserved for potential recovery or analysis.

## 📁 Directory Structure

```
./rejected/
├── duplicates/           # Duplicate files with numbered suffixes
├── low_quality/         # Files below quality threshold
├── corrupted/           # Corrupted or unplayable files
├── rejected_manifest.json  # Complete audit trail
└── rejection_analysis.csv  # CSV export for analysis
```

## 🔄 Duplicate Handling

When duplicates are found:
- **Best version** → `organized/` directory
- **All other versions** → `rejected/duplicates/` with numbered suffixes

### Example:
```
Original files:
- track_v1.mp3 (QS: 65%)
- track_v2.mp3 (QS: 89%) ← Best version
- track_v3.mp3 (QS: 72%)

Result:
✅ organized/Electronic/2020s/Artist - Track [QS89%].mp3
📋 rejected/duplicates/track_v1_duplicate_2.mp3
📋 rejected/duplicates/track_v3_duplicate_3.mp3
```

## 🎯 Quality-Based Rejection

Files are rejected based on configurable quality thresholds:

### Default Thresholds:
- **Minimum acceptable**: 70%
- **Auto-reject below**: 50%
- **Production threshold**: 85%

### Quality Categories:
- **Excellent** (90-100%): Optimal for professional use
- **Good** (75-89%): Suitable for most DJ applications
- **Acceptable** (60-74%): Basic quality, may be kept
- **Poor** (40-59%): Rejected to `low_quality/`
- **Unacceptable** (0-39%): Always rejected

## 🚫 Corruption Handling

Corrupted files are detected and moved to `rejected/corrupted/`:

### Detection Criteria:
- Health score below threshold
- Critical audio defects (truncation, header corruption, silence)
- DJ-specific issues (too short/long, metadata inaccessible)

### Corruption Types:
- **Truncated files**: Incomplete downloads
- **Corrupted headers**: Cannot read metadata
- **Complete silence**: Likely corrupted audio
- **Format errors**: Invalid audio data

## 📋 Rejection Manifest

The `rejected_manifest.json` file tracks ALL rejections with detailed information:

```json
{
  "metadata": {
    "created_at": "2024-01-15T10:30:00",
    "total_rejections": 157,
    "version": "2.0"
  },
  "rejections": [
    {
      "original_path": "./music/duplicate.mp3",
      "rejected_path": "./rejected/duplicates/duplicate_duplicate_2.mp3",
      "reason": "duplicate",
      "quality_score": 75.5,
      "chosen_file": "./organized/Electronic/Artist - Track [QS89%].mp3",
      "duplicate_group_id": "group_5_timestamp",
      "duplicate_rank": 2,
      "artist": "Artist Name",
      "title": "Track Title",
      "rejected_at": "2024-01-15T12:30:00",
      "notes": "Duplicate #2 in group"
    }
  ]
}
```

## ♻️ File Recovery

### Restore Individual Files:
```python
from music_cleanup.core.rejected_handler import RejectedHandler

rejected_handler = RejectedHandler(config)

# Find rejection entry in manifest
rejection_entry = {...}  # From manifest

# Restore to original location
rejected_handler.restore_file(rejection_entry)

# Or restore to new location
rejected_handler.restore_file(rejection_entry, "./new/location/file.mp3")
```

### Bulk Recovery:
```python
# Get all low-quality rejections
low_quality_files = rejected_handler.get_rejections_by_reason('low_quality')

# Get files in quality range
files_60_to_70 = rejected_handler.get_rejections_by_quality(60, 70)

# Review and selectively restore
for rejection in files_60_to_70:
    if should_restore(rejection):
        rejected_handler.restore_file(rejection)
```

## 📊 Analysis and Reporting

### Export for Analysis:
```python
# Export manifest to CSV
csv_path = rejected_handler.export_manifest_to_csv()
# Opens in Excel/LibreOffice for analysis

# Get statistics
stats = rejected_handler.get_stats()
print(f"Total rejected: {stats['total_rejected']}")
print(f"Duplicates: {stats['duplicates']}")
print(f"Low quality: {stats['low_quality']}")
```

### Quality Analysis:
```python
from music_cleanup.core.quality_rejection_handler import QualityRejectionHandler

quality_handler = QualityRejectionHandler(config)

# Analyze quality distribution
analysis = quality_handler.process_quality_analysis(files, context="production")
print(f"Excellent quality: {analysis['quality_distribution']['excellent']} files")
```

## ⚙️ Configuration

### Basic Configuration:
```json
{
  "paths": {
    "output_dir": "./organized",
    "rejected_dir": "./rejected",
    "create_if_missing": true
  },
  "rejection": {
    "keep_structure": true,
    "create_manifest": true,
    "categories": {
      "duplicates": "duplicates",
      "low_quality": "low_quality",
      "corrupted": "corrupted"
    }
  },
  "quality": {
    "min_score": 70,
    "always_keep_best": true,
    "auto_reject_below": 50
  }
}
```

### Advanced Configuration:
```json
{
  "rejection": {
    "keep_structure": true,
    "create_manifest": true,
    "enable_automatic_analysis": true,
    "generate_reports": true,
    "categories": {
      "duplicates": "duplicates",
      "low_quality": "low_quality", 
      "corrupted": "corrupted",
      "unsupported": "unsupported",
      "invalid_metadata": "invalid_metadata",
      "processing_errors": "errors"
    }
  },
  "quality": {
    "min_score": 80,
    "always_keep_best": true,
    "auto_reject_below": 60,
    "production_threshold": 85
  }
}
```

## 🛠️ Maintenance

### Regular Maintenance Tasks:

1. **Review Rejections**:
   ```bash
   # Export and review rejection data
   python -m music_cleanup.tools.rejection_analyzer
   ```

2. **Cleanup Empty Directories**:
   ```python
   removed = rejected_handler.cleanup_empty_directories()
   ```

3. **Archive Old Data**:
   ```python
   # Move old rejections to archive
   # Useful for large libraries with ongoing processing
   ```

## 🎯 Best Practices

### 1. Regular Review
- Export rejection manifest to CSV monthly
- Review quality thresholds based on your collection
- Analyze rejection patterns for systematic issues

### 2. Threshold Tuning
- Start with conservative thresholds
- Gradually adjust based on results
- Consider different profiles for different music types

### 3. Duplicate Management
- Always keep the highest quality version
- Review duplicate groups for metadata accuracy
- Consider format preferences (FLAC > MP3 320 > MP3 256, etc.)

### 4. Recovery Workflow
- Before major deletions, review rejected files
- Keep rejected files for at least one full processing cycle
- Use quality range queries to find borderline cases

## 🚨 Safety Features

### Data Protection:
- ✅ No files ever permanently deleted
- ✅ Complete audit trail maintained
- ✅ Easy restoration of any rejected file
- ✅ Detailed reasoning for each rejection
- ✅ Folder structure preservation

### Error Recovery:
- ✅ Failed moves logged and tracked
- ✅ Partial operation recovery
- ✅ Conflict resolution for existing files
- ✅ Database integrity checks

## 📈 Benefits

### For DJs:
- **Zero data loss**: All files preserved for potential use
- **Quality assurance**: Only high-quality files in main library
- **Easy recovery**: Quick restoration of accidentally rejected files
- **Organization**: Clear separation of problematic files

### For Large Collections:
- **Scalability**: Efficient handling of thousands of files
- **Analysis**: Detailed reporting for collection improvement
- **Automation**: Systematic processing with manual oversight
- **Flexibility**: Configurable thresholds for different needs

## 🔧 Troubleshooting

### Common Issues:

1. **Manifest Not Updated**:
   - Check file permissions on rejected directory
   - Verify JSON file is not corrupted
   - Enable logging for detailed error information

2. **Files Not Moving**:
   - Check source file permissions
   - Verify destination directory exists and is writable
   - Review configuration paths

3. **Recovery Failed**:
   - Ensure original path directory exists
   - Check for filename conflicts
   - Verify rejected file still exists

4. **High Rejection Rate**:
   - Review quality thresholds - may be too strict
   - Check source audio quality
   - Analyze rejection patterns in manifest

## 📞 Support

For issues with the rejected files system:
1. Check the logs for detailed error information
2. Review the rejection manifest for audit trail
3. Use the built-in analysis tools for pattern detection
4. Export CSV data for external analysis

The rejected files system ensures that your valuable music collection is never permanently lost while maintaining a clean, organized library of high-quality tracks.