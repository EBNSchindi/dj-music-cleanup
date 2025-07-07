# Usage Guide

This comprehensive guide covers all features and usage scenarios of the DJ Music Cleanup Tool.

## 📚 Table of Contents

- [Quick Start](#quick-start)
- [Command Line Interface](#command-line-interface)
- [Operation Modes](#operation-modes)
- [Configuration](#configuration)
- [Advanced Features](#advanced-features)
- [Use Cases](#use-cases)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

## 🚀 Quick Start

### Basic Organization
```bash
# Organize music from source to target directory
music-cleanup /path/to/music /path/to/organized

# With progress display
music-cleanup /path/to/music /path/to/organized --progress detailed

# Dry run to preview changes
music-cleanup /path/to/music /path/to/organized --dry-run
```

### With Configuration
```bash
# Use configuration file
music-cleanup /path/to/music /path/to/organized -c config/production.json

# Enable recovery and fingerprinting
music-cleanup /path/to/music /path/to/organized --enable-recovery --enable-fingerprinting
```

## 💻 Command Line Interface

### Basic Syntax
```
music-cleanup [OPTIONS] SOURCE_FOLDERS... -o OUTPUT_DIRECTORY
```

### Essential Options

#### Input/Output
```bash
# Multiple source folders
music-cleanup /music1 /music2 /music3 -o /organized

# Specify workspace for temporary files
music-cleanup /music -o /organized --workspace /tmp/music-workspace
```

#### Operation Modes
```bash
# Analysis mode - scan without changes
music-cleanup /music -o /organized --mode analyze

# Organization mode (default)
music-cleanup /music -o /organized --mode organize

# Cleanup mode - focus on duplicates
music-cleanup /music -o /organized --mode cleanup

# Recovery mode - restore from crash
music-cleanup /music -o /organized --mode recover --recovery-id session_123
```

#### Safety Features
```bash
# Enable crash recovery (recommended)
music-cleanup /music -o /organized --enable-recovery

# Set checkpoint interval (seconds)
music-cleanup /music -o /organized --checkpoint-interval 600

# Integrity checking level
music-cleanup /music -o /organized --integrity-level paranoid
```

#### Performance Tuning
```bash
# Set batch size and workers
music-cleanup /music -o /organized --batch-size 100 --max-workers 8

# Memory limit in MB
music-cleanup /music -o /organized --memory-limit 2048

# Skip duplicate detection for speed
music-cleanup /music -o /organized --skip-duplicates
```

#### Feature Toggles
```bash
# Enable audio fingerprinting
music-cleanup /music -o /organized --enable-fingerprinting

# Generate detailed report
music-cleanup /music -o /organized --report cleanup_report.html

# Specific logging level
music-cleanup /music -o /organized --log-level DEBUG --log-file cleanup.log
```

## 🔧 Operation Modes

### 1. Analyze Mode
Scans your music library and generates reports without making changes.

```bash
music-cleanup /music -o /organized --mode analyze --report analysis.html
```

**What it does:**
- Discovers all music files
- Analyzes metadata quality
- Identifies duplicates
- Checks file integrity
- Generates comprehensive report

**Best for:**
- Understanding your library structure
- Planning organization strategy
- Identifying issues before cleanup

### 2. Organize Mode (Default)
Complete library organization with file copying and restructuring.

```bash
music-cleanup /music -o /organized --mode organize
```

**What it does:**
- Discovers and processes all music files
- Extracts and standardizes metadata
- Organizes into genre/decade structure
- Handles duplicates intelligently
- Creates organized copy of library

**Best for:**
- First-time library organization
- Creating clean, organized copies
- Professional DJ library setup

### 3. Cleanup Mode
Focuses on duplicate removal and library optimization.

```bash
music-cleanup /music -o /organized --mode cleanup --enable-fingerprinting
```

**What it does:**
- Identifies duplicates using multiple methods
- Removes lower-quality versions
- Optimizes storage usage
- Maintains single copy of each track

**Best for:**
- Existing organized libraries
- Storage optimization
- Duplicate removal

### 4. Recovery Mode
Restores from previous interrupted operations.

```bash
music-cleanup /music -o /organized --mode recover --recovery-id session_20250107_143022
```

**What it does:**
- Detects interrupted operations
- Restores from checkpoints
- Continues from where it left off
- Verifies file integrity

**Best for:**
- After system crashes
- Interrupted operations
- Corrupted libraries

## ⚙️ Configuration

### Configuration File Structure
```json
{
  "streaming_config": {
    "batch_size": 100,
    "max_workers": 8,
    "memory_limit_mb": 2048
  },
  "processing": {
    "audio_formats": [".mp3", ".flac", ".wav"],
    "quality_threshold": 192,
    "enable_fingerprinting": true
  },
  "organization": {
    "structure": "genre/decade",
    "naming_pattern": "{artist} - {title}",
    "handle_duplicates": "keep_highest_quality"
  }
}
```

### Environment Variables
```bash
# Configuration file location
export MUSIC_CLEANUP_CONFIG=/path/to/config.json

# Workspace directory
export MUSIC_CLEANUP_WORKSPACE=/path/to/workspace

# Log level
export MUSIC_CLEANUP_LOG_LEVEL=INFO

# Memory limit
export MUSIC_CLEANUP_MEMORY_LIMIT=2048
```

## 🎯 Advanced Features

### Audio Fingerprinting
Enables acoustic duplicate detection using audio signatures.

```bash
# Install fingerprinting support
pip install pyacoustid

# Enable in configuration
music-cleanup /music -o /organized --enable-fingerprinting
```

**Benefits:**
- Detects duplicates even with different metadata
- Identifies re-encoded versions
- Finds partial matches and remixes

### Integrity Checking
Multi-level file validation to ensure library health.

```bash
# Basic file existence check
music-cleanup /music -o /organized --integrity-level basic

# Checksum validation
music-cleanup /music -o /organized --integrity-level checksum

# Metadata validation
music-cleanup /music -o /organized --integrity-level metadata

# Comprehensive validation
music-cleanup /music -o /organized --integrity-level deep

# Maximum security
music-cleanup /music -o /organized --integrity-level paranoid
```

### Crash Recovery
Automatic protection against system failures.

```bash
# Enable with custom settings
music-cleanup /music -o /organized \
  --enable-recovery \
  --checkpoint-interval 300 \
  --workspace /safe/location
```

**Features:**
- Automatic checkpoints every 5 minutes
- Signal-based crash detection
- Atomic file operations
- Complete rollback capability

### Batch Processing
Optimize performance for large libraries.

```bash
# High-performance settings
music-cleanup /music -o /organized \
  --batch-size 200 \
  --max-workers 12 \
  --memory-limit 4096 \
  --skip-duplicates
```

## 📋 Use Cases

### 1. Professional DJ Library Setup

```bash
# Complete professional setup
music-cleanup /raw/music /dj/library \
  -c config/production.json \
  --enable-recovery \
  --enable-fingerprinting \
  --integrity-level deep \
  --report dj_library_report.html
```

**Configuration highlights:**
- High-quality threshold (320kbps+)
- Paranoid integrity checking
- Comprehensive duplicate detection
- Professional naming conventions

### 2. Home Music Collection Cleanup

```bash
# Family music collection
music-cleanup /family/music /organized/music \
  -c config/default.json \
  --mode cleanup \
  --progress detailed
```

**Features:**
- Standard quality threshold
- User-friendly progress display
- Automatic duplicate removal
- Safe operation mode

### 3. Archive Management

```bash
# Digital archive processing
music-cleanup /archive/incoming /archive/processed \
  --integrity-level paranoid \
  --enable-recovery \
  --batch-size 50 \
  --report archive_integrity.html
```

**Focus areas:**
- Maximum integrity verification
- Comprehensive error checking
- Detailed audit trails
- Long-term preservation

### 4. Studio Sample Library

```bash
# Producer sample organization
music-cleanup /samples/raw /samples/organized \
  --mode organize \
  --enable-fingerprinting \
  --integrity-level deep \
  --workspace /fast/ssd/workspace
```

**Optimizations:**
- Fast SSD workspace
- Acoustic fingerprinting for variants
- Deep integrity checking
- Efficient organization

## 🎯 Best Practices

### Pre-Processing Checklist

1. **Backup Original Files**
   ```bash
   # Always backup before processing
   rsync -av /original/music /backup/music
   ```

2. **Test with Small Subset**
   ```bash
   # Test configuration with sample
   music-cleanup /music/sample /test/output --dry-run
   ```

3. **Check Available Space**
   ```bash
   # Ensure sufficient disk space
   df -h /target/directory
   ```

4. **Verify Configuration**
   ```bash
   # Validate configuration file
   music-cleanup --validate-config config.json
   ```

### Performance Optimization

#### For Large Libraries (100K+ files)
```bash
music-cleanup /huge/library /organized \
  --batch-size 200 \
  --max-workers 16 \
  --memory-limit 4096 \
  --checkpoint-interval 600 \
  --workspace /fast/nvme/workspace
```

#### For Limited Resources
```bash
music-cleanup /music /organized \
  --batch-size 25 \
  --max-workers 2 \
  --memory-limit 512 \
  --skip-duplicates
```

#### For Quality Focus
```bash
music-cleanup /music /organized \
  --enable-fingerprinting \
  --integrity-level deep \
  --batch-size 50 \
  --progress detailed
```

### Safety Guidelines

1. **Always Use Recovery Mode**
   ```bash
   music-cleanup /music /organized --enable-recovery
   ```

2. **Regular Checkpoints**
   ```bash
   # More frequent checkpoints for critical data
   music-cleanup /music /organized --checkpoint-interval 180
   ```

3. **Integrity Verification**
   ```bash
   # Verify file integrity after processing
   music-cleanup /organized --mode analyze --integrity-level deep
   ```

4. **Monitor Resources**
   ```bash
   # Watch memory and disk usage
   watch -n 5 'df -h && free -h'
   ```

## 📊 Progress Monitoring

### Progress Display Options
```bash
# No progress display
music-cleanup /music /organized --progress none

# Simple progress bar
music-cleanup /music /organized --progress simple

# Detailed progress with statistics
music-cleanup /music /organized --progress detailed
```

### Log File Analysis
```bash
# Enable detailed logging
music-cleanup /music /organized --log-level DEBUG --log-file detailed.log

# Monitor in real-time
tail -f detailed.log

# Analyze after completion
grep "ERROR\|WARNING" detailed.log
```

### Report Generation
```bash
# Comprehensive HTML report
music-cleanup /music /organized --report cleanup_report.html

# JSON report for automation
music-cleanup /music /organized --report-format json --report results.json
```

## 🔍 Troubleshooting

### Common Issues

#### Memory Issues
```bash
# Reduce memory usage
music-cleanup /music /organized \
  --memory-limit 1024 \
  --batch-size 25 \
  --max-workers 2
```

#### Permission Errors
```bash
# Check and fix permissions
chmod -R 755 /music/directory
chown -R $USER:$USER /music/directory
```

#### Slow Performance
```bash
# Optimize for speed
music-cleanup /music /organized \
  --skip-duplicates \
  --integrity-level basic \
  --batch-size 200
```

#### Incomplete Processing
```bash
# Resume from checkpoint
music-cleanup /music /organized --mode recover --recovery-id session_xyz
```

### Debug Mode
```bash
# Enable maximum debugging
music-cleanup /music /organized \
  --log-level DEBUG \
  --log-file debug.log \
  --progress detailed \
  --dry-run
```

### Getting Help

1. **Check Documentation**
   - [Installation Guide](installation.md)
   - [Configuration Reference](configuration.md)
   - [Troubleshooting Guide](troubleshooting.md)

2. **Generate Debug Information**
   ```bash
   music-cleanup --system-info > debug_info.txt
   ```

3. **Community Support**
   - [GitHub Issues](https://github.com/EBNSchindi/dj-music-cleanup/issues)
   - [Discussions](https://github.com/EBNSchindi/dj-music-cleanup/discussions)

## 📈 Performance Expectations

### Typical Processing Speeds

| Library Size | Files/Second | Memory Usage | Duration |
|-------------|-------------|--------------|----------|
| 1K files    | 800-900     | 20-22 MB     | 1-2 min  |
| 10K files   | 700-800     | 21-23 MB     | 15-20 min |
| 100K files  | 600-700     | 22-25 MB     | 2-3 hours |
| 300K+ files | 500-600     | 24-27 MB     | 8-12 hours |

### Factors Affecting Performance

1. **Hardware**
   - CPU cores (parallel processing)
   - Storage speed (SSD vs HDD)
   - Available RAM (caching)

2. **Configuration**
   - Batch size
   - Worker threads
   - Feature enablement

3. **Library Characteristics**
   - File sizes
   - Metadata quality
   - Duplicate percentage

---

**Ready to organize your music library? Choose the approach that best fits your needs! 🎵**