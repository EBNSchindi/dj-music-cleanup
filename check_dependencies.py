#!/usr/bin/env python3
"""
Dependency checker for DJ Music Cleanup Tool
"""
import sys
import subprocess
import importlib
import os

def check_python_version():
    """Check Python version"""
    print("Checking Python version...")
    version = sys.version_info
    if version >= (3, 8):
        print(f"✓ Python {version.major}.{version.minor}.{version.micro} (OK)")
        return True
    else:
        print(f"❌ Python {version.major}.{version.minor}.{version.micro} (Need 3.8+)")
        return False

def check_python_packages():
    """Check required Python packages"""
    print("\nChecking Python packages...")
    
    required_packages = [
        ('mutagen', 'Audio metadata handling'),
        ('tqdm', 'Progress bars'),
        ('unidecode', 'Text processing'),
        ('requests', 'HTTP requests'),
    ]
    
    optional_packages = [
        ('pyacoustid', 'Audio fingerprinting'),
        ('musicbrainzngs', 'Metadata enrichment'),
        ('eyed3', 'MP3 metadata'),
    ]
    
    all_ok = True
    
    for package, description in required_packages:
        try:
            importlib.import_module(package)
            print(f"✓ {package} - {description}")
        except ImportError:
            print(f"❌ {package} - {description} (REQUIRED)")
            all_ok = False
    
    for package, description in optional_packages:
        try:
            importlib.import_module(package)
            print(f"✓ {package} - {description}")
        except ImportError:
            print(f"⚠️  {package} - {description} (OPTIONAL)")
    
    return all_ok

def check_chromaprint():
    """Check Chromaprint installation"""
    print("\nChecking Chromaprint...")
    
    try:
        result = subprocess.run(['fpcalc', '-version'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            version = result.stdout.strip()
            print(f"✓ Chromaprint fpcalc found: {version}")
            return True
        else:
            print("❌ fpcalc command failed")
            return False
    except FileNotFoundError:
        print("⚠️  fpcalc not found in PATH")
        print("   Install from: https://acoustid.org/chromaprint")
        print("   Or use: brew install chromaprint (macOS)")
        print("   Or use: apt-get install libchromaprint-tools (Ubuntu)")
        return False
    except subprocess.TimeoutExpired:
        print("❌ fpcalc command timed out")
        return False
    except Exception as e:
        print(f"❌ Error checking fpcalc: {e}")
        return False

def check_disk_space():
    """Check available disk space"""
    print("\nChecking disk space...")
    
    try:
        import shutil
        total, used, free = shutil.disk_usage("/")
        free_gb = free / (1024**3)
        
        if free_gb > 10:
            print(f"✓ Available disk space: {free_gb:.1f} GB")
            return True
        else:
            print(f"⚠️  Available disk space: {free_gb:.1f} GB (may be insufficient)")
            return False
    except Exception as e:
        print(f"❌ Error checking disk space: {e}")
        return False

def check_permissions():
    """Check file permissions"""
    print("\nChecking permissions...")
    
    try:
        # Check if we can write to current directory
        test_file = "test_write_permissions.tmp"
        with open(test_file, 'w') as f:
            f.write("test")
        os.remove(test_file)
        print("✓ Write permissions OK")
        return True
    except Exception as e:
        print(f"❌ Write permission error: {e}")
        return False

def install_missing_packages():
    """Install missing required packages"""
    print("\nInstalling missing packages...")
    
    try:
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'],
                      check=True)
        print("✓ Packages installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Package installation failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Error installing packages: {e}")
        return False

def main():
    """Main dependency check"""
    print("=" * 60)
    print("DJ Music Cleanup Tool - Dependency Check")
    print("=" * 60)
    
    all_checks = []
    
    # Run all checks
    all_checks.append(check_python_version())
    all_checks.append(check_python_packages())
    all_checks.append(check_chromaprint())
    all_checks.append(check_disk_space())
    all_checks.append(check_permissions())
    
    print("\n" + "=" * 60)
    
    if all(all_checks):
        print("✅ ALL CHECKS PASSED - Ready to use!")
    else:
        print("⚠️  Some checks failed - see details above")
        
        # Offer to install missing packages
        response = input("\nInstall missing Python packages? (y/n): ")
        if response.lower() == 'y':
            install_missing_packages()
    
    print("\nNext steps:")
    print("1. Run: python test_tool.py")
    print("2. Run: python music_cleanup.py --create-config")
    print("3. Edit the config file with your folders")
    print("4. Run: python music_cleanup.py --scan-only")
    print("=" * 60)

if __name__ == '__main__':
    main()