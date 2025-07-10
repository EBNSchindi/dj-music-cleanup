#!/bin/bash
# Installation script for DJ Music Cleanup Tool
# This script handles installation on different platforms

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored output
print_color() {
    color=$1
    shift
    echo -e "${color}$*${NC}"
}

print_header() {
    echo
    print_color $BLUE "🎵 DJ Music Cleanup Tool - Installation Script"
    echo "=============================================="
    echo
}

print_success() {
    print_color $GREEN "✅ $*"
}

print_warning() {
    print_color $YELLOW "⚠️  $*"
}

print_error() {
    print_color $RED "❌ $*"
}

print_info() {
    print_color $BLUE "ℹ️  $*"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Detect operating system
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "linux"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    elif [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]]; then
        echo "windows"
    else
        echo "unknown"
    fi
}

# Check Python version
check_python() {
    print_info "Checking Python installation..."
    
    if command_exists python3; then
        python_version=$(python3 --version 2>&1 | cut -d' ' -f2)
        major_version=$(echo $python_version | cut -d'.' -f1)
        minor_version=$(echo $python_version | cut -d'.' -f2)
        
        if [[ $major_version -eq 3 ]] && [[ $minor_version -ge 8 ]]; then
            print_success "Python $python_version found"
            return 0
        else
            print_error "Python 3.8+ required, found $python_version"
            return 1
        fi
    elif command_exists python; then
        python_version=$(python --version 2>&1 | cut -d' ' -f2)
        major_version=$(echo $python_version | cut -d'.' -f1)
        minor_version=$(echo $python_version | cut -d'.' -f2)
        
        if [[ $major_version -eq 3 ]] && [[ $minor_version -ge 8 ]]; then
            print_success "Python $python_version found"
            return 0
        else
            print_error "Python 3.8+ required, found $python_version"
            return 1
        fi
    else
        print_error "Python not found"
        return 1
    fi
}

# Install Python based on OS
install_python() {
    os=$(detect_os)
    print_info "Installing Python for $os..."
    
    case $os in
        "linux")
            if command_exists apt; then
                sudo apt update
                sudo apt install -y python3 python3-pip python3-venv
            elif command_exists yum; then
                sudo yum install -y python3 python3-pip
            elif command_exists dnf; then
                sudo dnf install -y python3 python3-pip
            else
                print_error "Unable to install Python automatically. Please install Python 3.8+ manually."
                exit 1
            fi
            ;;
        "macos")
            if command_exists brew; then
                brew install python
            else
                print_error "Homebrew not found. Please install Python 3.8+ manually from python.org"
                exit 1
            fi
            ;;
        "windows")
            print_error "Please install Python 3.8+ from python.org"
            exit 1
            ;;
        *)
            print_error "Unsupported operating system. Please install Python 3.8+ manually."
            exit 1
            ;;
    esac
}

# Install the package
install_package() {
    print_info "Installing DJ Music Cleanup Tool..."
    
    # Check if we should use pip or pip3
    pip_cmd="pip"
    if command_exists pip3; then
        pip_cmd="pip3"
    fi
    
    # Try to install from PyPI first
    if $pip_cmd install dj-music-cleanup >/dev/null 2>&1; then
        print_success "Installed from PyPI"
    else
        print_warning "PyPI installation failed, installing from source..."
        
        # Install from current directory if we're in the source
        if [[ -f "pyproject.toml" ]]; then
            $pip_cmd install -e .
            print_success "Installed from source"
        else
            print_error "Installation failed. Please check your internet connection and try again."
            exit 1
        fi
    fi
}

# Install optional dependencies
install_optional_deps() {
    print_info "Installing optional dependencies..."
    
    pip_cmd="pip"
    if command_exists pip3; then
        pip_cmd="pip3"
    fi
    
    # Ask user about optional dependencies
    echo
    read -p "Install audio fingerprinting support? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        $pip_cmd install pyacoustid
        print_success "Audio fingerprinting support installed"
    fi
    
    read -p "Install advanced metadata support? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        $pip_cmd install eyed3
        print_success "Advanced metadata support installed"
    fi
}

# Verify installation
verify_installation() {
    print_info "Verifying installation..."
    
    if command_exists music-cleanup; then
        version=$(music-cleanup --version 2>&1 | grep -o 'v[0-9.]*' || echo "unknown")
        print_success "Installation verified - $version"
        return 0
    else
        print_error "Installation verification failed"
        return 1
    fi
}

# Create sample configuration
create_sample_config() {
    print_info "Creating sample configuration..."
    
    config_dir="$HOME/.config/music-cleanup"
    mkdir -p "$config_dir"
    
    if [[ -f "config/default.json" ]]; then
        cp "config/default.json" "$config_dir/config.json"
        print_success "Sample configuration created at $config_dir/config.json"
    else
        print_warning "Sample configuration not found, skipping"
    fi
}

# Print post-installation instructions
print_instructions() {
    echo
    print_color $GREEN "🎉 Installation completed successfully!"
    echo
    print_info "Quick start:"
    echo "  music-cleanup /path/to/music /path/to/organized"
    echo
    print_info "With configuration:"
    echo "  music-cleanup /path/to/music /path/to/organized -c ~/.config/music-cleanup/config.json"
    echo
    print_info "For help:"
    echo "  music-cleanup --help"
    echo
    print_info "Documentation:"
    echo "  https://github.com/EBNSchindi/dj-music-cleanup/docs"
    echo
}

# Main installation flow
main() {
    print_header
    
    # Check/install Python
    if ! check_python; then
        print_warning "Python 3.8+ not found, attempting to install..."
        install_python
        
        # Verify Python installation
        if ! check_python; then
            print_error "Python installation failed"
            exit 1
        fi
    fi
    
    # Install the package
    install_package
    
    # Install optional dependencies
    install_optional_deps
    
    # Verify installation
    if ! verify_installation; then
        print_error "Installation verification failed"
        exit 1
    fi
    
    # Create sample configuration
    create_sample_config
    
    # Print instructions
    print_instructions
}

# Handle command line options
case "${1:-}" in
    --help|-h)
        echo "DJ Music Cleanup Tool Installation Script"
        echo
        echo "Usage: $0 [OPTIONS]"
        echo
        echo "Options:"
        echo "  --help, -h     Show this help message"
        echo "  --minimal      Install without optional dependencies"
        echo "  --dev          Install development dependencies"
        echo
        exit 0
        ;;
    --minimal)
        MINIMAL_INSTALL=1
        ;;
    --dev)
        DEV_INSTALL=1
        ;;
esac

# Run main installation
main