# 🎧 DJ Music Library Cleanup Tool

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Audio Fingerprinting](https://img.shields.io/badge/audio-fingerprinting-green.svg)](https://acoustid.org/chromaprint)

A professional-grade Python tool for cleaning, organizing, and deduplicating large DJ music libraries using audio fingerprinting technology.

**✨ Perfect for DJs with chaotic music collections of 100,000+ files!**

## Features

- **Audio Fingerprinting**: Uses Chromaprint/AcoustID to identify truly duplicate tracks regardless of metadata
- **Intelligent Duplicate Detection**: Automatically selects the highest quality version (FLAC > WAV > 320kbps MP3 > lower bitrates)
- **Metadata Enhancement**: Enriches missing metadata using MusicBrainz database
- **Smart Organization**: Organizes files by Genre/Decade structure
- **Protected Folders**: Never modifies files in designated core/master folders
- **Safe Operation**: Only copies files, never deletes originals
- **Resume Capability**: Can resume interrupted operations
- **Comprehensive Reporting**: Generates detailed HTML reports and duplicate lists
- **Undo Functionality**: Creates scripts to reverse operations if needed

## Requirements

### System Requirements
- Python 3.8 or higher
- Windows/macOS/Linux
- Chromaprint command-line tool (fpcalc)
- At least 2GB RAM (4GB+ recommended for large libraries)

### Installing Chromaprint

#### Windows
1. Download Chromaprint from: https://acoustid.org/chromaprint
2. Extract and add the `fpcalc.exe` location to your PATH
3. Or place `fpcalc.exe` in the project directory

#### macOS
```bash
brew install chromaprint
```

#### Linux (Ubuntu/Debian)
```bash
sudo apt-get install libchromaprint-tools
```

## Installation

1. Clone or download this repository:
```bash
git clone https://github.com/yourusername/dj-music-cleanup.git
cd dj-music-cleanup
```

2. Create a virtual environment (recommended):
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Configuration

1. Create a configuration file:
```bash
python music_cleanup.py --create-config
```

2. Edit `example_config.json` with your settings:
```json
{
    "protected_folders": [
        "D:\\Core-Library",
        "D:\\Master-Collection"
    ],
    "source_folders": [
        "D:\\Music",
        "D:\\Downloads\\Music"
    ],
    "target_folder": "D:\\Bereinigt",
    "quality_priority": ["flac", "wav", "mp3_320", "mp3_256"],
    "enable_musicbrainz": true,
    "multiprocessing_workers": 4,
    "batch_size": 1000
}
```

### Configuration Options

- `protected_folders`: Folders that will NEVER be modified (read-only)
- `source_folders`: Folders to scan for music files
- `target_folder`: Where organized files will be copied
- `quality_priority`: Order of preference for duplicate selection
- `enable_musicbrainz`: Enable metadata enrichment from MusicBrainz
- `multiprocessing_workers`: Number of parallel processing threads
- `batch_size`: Files to process per batch
- `min_file_size_mb`: Ignore files smaller than this (default: 0.5)
- `max_file_size_mb`: Ignore files larger than this (default: 50)

## Usage

### 1. Analyze Your Library (No Changes)
```bash
python music_cleanup.py --scan-only
```
This shows:
- Total number of music files
- Format distribution
- Metadata completeness
- No files are modified

### 2. Dry Run (Preview Changes)
```bash
python music_cleanup.py --dry-run --config my_config.json
```
This shows:
- What files would be copied where
- Which duplicates would be handled
- How much space would be saved
- Still no actual changes made

### 3. Execute Cleanup
```bash
python music_cleanup.py --execute --config my_config.json
```
This will:
- Copy files to organized structure
- Handle duplicates (keep best quality)
- Generate reports
- Create undo script

### 4. Resume Interrupted Operation
```bash
python music_cleanup.py --execute --resume
```

## Output Structure

The tool creates this folder structure:
```
D:\Bereinigt\
├── House\
│   ├── 1990s\
│   ├── 2000s\
│   ├── 2010s\
│   └── 2020s\
├── Techno\
│   ├── 1990s\
│   └── 2000s\
├── Hip-Hop\
│   └── 2010s\
├── Electronic\
└── Unknown\
    ├── Missing-Genre\
    └── Missing-Year\
```

Files are renamed to: `Artist - Title.ext`

## Reports

After execution, find these in the `reports/` folder:

1. **HTML Report** (`cleanup_report_YYYYMMDD_HHMMSS.html`)
   - Summary statistics
   - Genre distribution
   - Duplicate groups
   - Space saved

2. **Duplicate List** (`duplicates_YYYYMMDD_HHMMSS.txt`)
   - All duplicate groups
   - Quality comparison
   - File paths

3. **Undo Script** (`undo_operations.sh`)
   - Reverses all copy operations
   - Use if you need to undo

## Performance Tips

1. **For 300,000+ files:**
   - Use SSD for databases (fingerprints.db)
   - Set `multiprocessing_workers` to CPU cores - 1
   - Process in smaller batches initially
   - Ensure enough free space (2x your library size)

2. **Memory Usage:**
   - Increase `batch_size` for better performance
   - Decrease if you run out of memory

3. **Network:**
   - Disable MusicBrainz if not needed
   - It adds ~1 second per track for lookups

## Troubleshooting

### "fpcalc not found"
- Ensure Chromaprint is installed and in PATH
- Or set the path in your environment

### "Out of memory"
- Reduce `batch_size` in config
- Process folders separately

### "Permission denied"
- Check folder permissions
- Run as administrator (Windows) if needed

### Corrupted files
- Check `logs/` folder for details
- Corrupted files are skipped automatically

## Safety Features

1. **Never Deletes**: Only copies files, originals remain untouched
2. **Protected Folders**: Designated folders are read-only
3. **Verification**: Each copy is verified for integrity
4. **Logging**: All operations are logged
5. **Undo Script**: Can reverse all operations

## Advanced Usage

### Custom Genre Mapping
Edit the `genre_categories` in config:
```json
"genre_categories": {
    "House": ["house", "deep house", "tech house"],
    "MyCustomGenre": ["keyword1", "keyword2"]
}
```

### Using Without MusicBrainz
Set in config:
```json
"enable_musicbrainz": false
```

### Processing Specific Formats Only
```json
"supported_formats": [".mp3", ".flac"]
```

## 📸 Screenshots

### Before: Chaotic Library
```
Track01.mp3
Avicii - Levels (Radio Edit) [2011].mp3
levels_avicii_320.mp3
03 - Levels.mp3
```

### After: Organized Structure  
```
D:\Bereinigt\
├── House\
│   └── 2010s\
│       └── Avicii - Levels.mp3  # Best quality kept
├── Pop\
│   └── 1980s\
│       └── ABBA - Dancing Queen.mp3
└── reports\
    ├── cleanup_report.html
    └── duplicates_found.txt
```

## 🤝 Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new features
4. Submit a pull request

## 📄 License

MIT License - see [LICENSE](LICENSE) file

## 🙏 Acknowledgments

- [Chromaprint/AcoustID](https://acoustid.org/) for audio fingerprinting
- [MusicBrainz](https://musicbrainz.org/) for metadata enrichment
- [Mutagen](https://mutagen.readthedocs.io/) for audio tag handling

## 📞 Support

For issues, questions, or contributions:
- 🐛 **GitHub Issues**: Report bugs and request features
- 💡 **Discussions**: Share your cleanup success stories
- 📖 **Wiki**: Community tips and advanced configurations

---

**Made with ❤️ for the DJ community**
