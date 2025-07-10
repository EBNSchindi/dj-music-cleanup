# Installation Guide

This guide will help you install and set up the DJ Music Cleanup Tool on your system.

## 📋 System Requirements

### Minimum Requirements
- **Python**: 3.8 or higher
- **RAM**: 256 MB (tool uses constant memory regardless of library size)
- **Storage**: 100 MB for installation + workspace for temporary files
- **OS**: Windows 10+, macOS 10.14+, or Linux (Ubuntu 18.04+)

### Recommended Requirements
- **Python**: 3.10 or higher
- **RAM**: 1 GB (for better performance with large libraries)
- **Storage**: 1 GB+ free space for workspace and logs
- **CPU**: Multi-core processor for parallel processing

## 🚀 Installation Methods

### Method 1: Install from PyPI (Recommended)

```bash
# Install the latest stable version
pip install dj-music-cleanup

# Install with optional fingerprinting support
pip install dj-music-cleanup[fingerprinting]

# Install with all optional dependencies
pip install dj-music-cleanup[fingerprinting,advanced]
```

### Method 2: Install from Source

```bash
# Clone the repository
git clone https://github.com/EBNSchindi/dj-music-cleanup.git
cd dj-music-cleanup

# Create virtual environment (recommended)
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install in development mode
pip install -e .

# Or install with optional dependencies
pip install -e ".[fingerprinting,advanced,dev]"
```

### Method 3: Docker Installation

```bash
# Pull the official Docker image
docker pull djmusiccleanup/dj-music-cleanup:latest

# Run with volume mounts
docker run -v /path/to/music:/music -v /path/to/output:/output \
  djmusiccleanup/dj-music-cleanup:latest \
  /music /output
```

## 🔧 Optional Dependencies

The tool has several optional dependencies that provide additional features:

### Audio Fingerprinting
For advanced duplicate detection using acoustic fingerprints:
```bash
pip install pyacoustid>=1.2.2
```

### Advanced Metadata
For enhanced metadata extraction:
```bash
pip install eyed3>=0.9.7
```

### Audio Analysis
For quality analysis and format conversion:
```bash
pip install librosa>=0.10.0 numpy>=1.24.0
```

### Development Tools
For contributing to the project:
```bash
pip install "dj-music-cleanup[dev]"
```

## ✅ Verification

### Test Installation
```bash
# Check version
music-cleanup --version

# Test with help
music-cleanup --help

# Run basic validation
music-cleanup --validate-installation
```

### Check Dependencies
```bash
# Check all dependencies
python -c "import music_cleanup; print('Installation successful!')"

# Check optional dependencies
python -c "
try:
    import pyacoustid
    print('✅ Audio fingerprinting available')
except ImportError:
    print('❌ Audio fingerprinting not available')

try:
    import eyed3
    print('✅ Advanced metadata available')
except ImportError:
    print('❌ Advanced metadata not available')
"
```

## 🏗️ Platform-Specific Instructions

### Windows

#### Prerequisites
1. **Python**: Download from [python.org](https://www.python.org/downloads/)
2. **Git** (optional): Download from [git-scm.com](https://git-scm.com/)

#### Installation
```cmd
# Install using pip
pip install dj-music-cleanup

# Or with Chocolatey
choco install python
pip install dj-music-cleanup
```

#### Common Issues
- **Path Issues**: Make sure Python Scripts directory is in PATH
- **Permission Errors**: Run Command Prompt as Administrator
- **Long Path Support**: Enable long path support in Windows settings

### macOS

#### Prerequisites
```bash
# Install Homebrew (if not already installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python
brew install python
```

#### Installation
```bash
# Install using pip
pip3 install dj-music-cleanup

# Or using Homebrew
brew tap djmusiccleanup/tap
brew install dj-music-cleanup
```

### Linux (Ubuntu/Debian)

#### Prerequisites
```bash
# Update package list
sudo apt update

# Install Python and pip
sudo apt install python3 python3-pip python3-venv

# Install build dependencies (for some optional packages)
sudo apt install build-essential python3-dev
```

#### Installation
```bash
# Install using pip
pip3 install dj-music-cleanup

# Or using package manager (if available)
sudo apt install dj-music-cleanup
```

### Linux (CentOS/RHEL/Fedora)

#### Prerequisites
```bash
# CentOS/RHEL
sudo yum install python3 python3-pip
# or
sudo dnf install python3 python3-pip

# Fedora
sudo dnf install python3 python3-pip
```

## 🐳 Docker Installation

### Basic Docker Setup
```bash
# Create docker-compose.yml
cat > docker-compose.yml << EOF
version: '3.8'
services:
  music-cleanup:
    image: djmusiccleanup/dj-music-cleanup:latest
    volumes:
      - ./music:/input
      - ./organized:/output
      - ./config:/config
      - ./logs:/logs
    environment:
      - CONFIG_FILE=/config/production.json
    command: /input /output -c /config/production.json
EOF

# Run with Docker Compose
docker-compose up
```

### Advanced Docker Setup
```bash
# Build from source
docker build -t dj-music-cleanup .

# Run with custom configuration
docker run -it \
  -v $(pwd)/music:/music \
  -v $(pwd)/organized:/organized \
  -v $(pwd)/config:/config \
  dj-music-cleanup \
  music-cleanup /music /organized -c /config/custom.json
```

## 🔧 Configuration

### Create Initial Configuration
```bash
# Create config directory
mkdir -p ~/.config/music-cleanup

# Copy default configuration
music-cleanup --create-config ~/.config/music-cleanup/config.json

# Edit configuration
# Windows: notepad ~/.config/music-cleanup/config.json
# macOS: open -a TextEdit ~/.config/music-cleanup/config.json
# Linux: nano ~/.config/music-cleanup/config.json
```

### Environment Variables
```bash
# Set configuration file location
export MUSIC_CLEANUP_CONFIG=/path/to/config.json

# Set workspace directory
export MUSIC_CLEANUP_WORKSPACE=/path/to/workspace

# Set log level
export MUSIC_CLEANUP_LOG_LEVEL=INFO
```

## 🚨 Troubleshooting

### Common Installation Issues

#### Python Version Issues
```bash
# Check Python version
python --version
python3 --version

# Use specific Python version
python3.10 -m pip install dj-music-cleanup
```

#### Permission Issues
```bash
# Install for current user only
pip install --user dj-music-cleanup

# Or use virtual environment
python -m venv music-cleanup-env
source music-cleanup-env/bin/activate  # Linux/macOS
music-cleanup-env\Scripts\activate     # Windows
pip install dj-music-cleanup
```

#### Dependency Conflicts
```bash
# Create clean virtual environment
python -m venv clean-env
source clean-env/bin/activate
pip install --upgrade pip
pip install dj-music-cleanup
```

#### Network Issues
```bash
# Install with different index
pip install -i https://pypi.org/simple/ dj-music-cleanup

# Install from wheel file
pip install https://github.com/EBNSchindi/dj-music-cleanup/releases/download/v2.0.0/dj_music_cleanup-2.0.0-py3-none-any.whl
```

### Platform-Specific Issues

#### Windows
- **Long path issues**: Enable long path support in Windows settings
- **Antivirus interference**: Add Python/pip to antivirus exclusions
- **Unicode issues**: Set `PYTHONIOENCODING=utf-8`

#### macOS
- **Command not found**: Add pip install location to PATH
- **Permission denied**: Use `--user` flag or virtual environment
- **SSL certificate issues**: Update certificates: `pip install --upgrade certifi`

#### Linux
- **Missing dependencies**: Install build tools: `sudo apt install build-essential`
- **Permission issues**: Use virtual environment or `--user` flag
- **Audio libraries**: Install system audio libraries for optional features

## 📞 Getting Help

If you encounter issues during installation:

1. **Check Requirements**: Ensure your system meets minimum requirements
2. **Update pip**: `pip install --upgrade pip`
3. **Try Virtual Environment**: Isolate the installation
4. **Check Documentation**: See [docs/troubleshooting.md](troubleshooting.md)
5. **Search Issues**: Check [GitHub Issues](https://github.com/EBNSchindi/dj-music-cleanup/issues)
6. **Ask for Help**: Create a new issue with installation details

## 🎉 Next Steps

Once installation is complete:

1. **Quick Start**: See [README.md](../README.md#quick-start-5-minutes)
2. **Configuration**: Read [docs/configuration.md](configuration.md)
3. **Usage Guide**: Check [docs/usage.md](usage.md)
4. **Examples**: Explore [examples/](../examples/)

---

**Installation successful? Start organizing your music library! 🎵**