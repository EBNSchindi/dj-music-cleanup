# Quick Start Guide - DJ Music Library Cleanup

## 🚀 5-Minute Setup

### 1. Prerequisites
- Install Python 3.8+ from [python.org](https://python.org)
- Install Chromaprint:
  - **Windows**: Download from [acoustid.org/chromaprint](https://acoustid.org/chromaprint)
  - **Mac**: `brew install chromaprint`
  - **Linux**: `sudo apt-get install libchromaprint-tools`

### 2. Installation
```bash
# Clone or download the tool
cd music_cleanup_tool

# Windows users: Just double-click run_cleanup.bat
# OR manually:
python -m venv venv
venv\Scripts\activate     # Windows
source venv/bin/activate  # Mac/Linux
pip install -r requirements.txt
```

### 3. Configuration
```bash
# Create config
python music_cleanup.py --create-config

# Edit example_config.json:
{
    "protected_folders": ["D:\\DJ-Sets", "D:\\Master-Collection"],
    "source_folders": ["D:\\Music", "E:\\Downloads"],
    "target_folder": "D:\\Bereinigt"
}
```

### 4. Run
```bash
# Step 1: Analyze (safe, no changes)
python music_cleanup.py --scan-only

# Step 2: Preview (see what would happen)
python music_cleanup.py --dry-run --config example_config.json

# Step 3: Execute (actually organize files)
python music_cleanup.py --execute --config example_config.json
```

## 🎯 What It Does

1. **Scans** your music folders (respecting protected folders)
2. **Fingerprints** each track (finds true duplicates)
3. **Keeps** the best quality version of duplicates
4. **Organizes** into Genre/Decade folders
5. **Renames** files to "Artist - Title.mp3"
6. **Reports** everything it did

## ⚡ For 300,000+ Files

Optimized config:
```json
{
    "multiprocessing_workers": 8,
    "batch_size": 2000,
    "enable_musicbrainz": false  // Faster without online lookups
}
```

## 🛡️ Safety

- ✅ Never deletes original files
- ✅ Protected folders are read-only
- ✅ Creates undo script
- ✅ Can resume if interrupted
- ✅ Detailed logging

## 📊 Example Output

```
D:\Bereinigt\
├── House\
│   ├── 2010s\
│   │   ├── Avicii - Levels.mp3
│   │   └── Swedish House Mafia - One.mp3
│   └── 2020s\
│       └── David Guetta - Titanium.mp3
├── Techno\
│   └── 2000s\
│       └── Paul Kalkbrenner - Sky and Sand.mp3
└── reports\
    ├── cleanup_report_20240715_143022.html
    └── duplicates_20240715_143022.txt
```

## 🆘 Troubleshooting

| Problem | Solution |
|---------|----------|
| "fpcalc not found" | Add Chromaprint to PATH or copy fpcalc.exe to project folder |
| "Out of memory" | Reduce batch_size to 500 |
| "Permission denied" | Run as Administrator (Windows) |
| Takes too long | Disable musicbrainz, increase workers |

## 💡 Pro Tips

1. **Test First**: Always do a dry-run on a small folder
2. **Backup**: Have backups before running on your entire library
3. **Space**: Need ~2x your library size in free space
4. **Time**: Expect ~1-2 hours per 100,000 files

## 📞 Getting Help

- Check `logs/` folder for detailed errors
- Read the full README.md for advanced options
- Create an issue on GitHub for bugs

---

**Remember**: This tool COPIES files, it never deletes. Your originals are always safe!