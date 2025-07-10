"""
Tool Availability Checker

Checks for required external tools and provides helpful error messages
if tools are missing from the system.
"""

import logging
import shutil
import subprocess
import platform
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class ToolPriority(Enum):
    """Priority levels for tools"""
    REQUIRED = "required"
    RECOMMENDED = "recommended"
    OPTIONAL = "optional"


@dataclass
class ToolInfo:
    """Information about a required tool"""
    name: str
    command: str
    priority: ToolPriority
    package_name: str
    install_instructions: Dict[str, str]
    check_command: Optional[str] = None
    min_version: Optional[str] = None


class ToolsMissingError(Exception):
    """Raised when required tools are missing"""
    
    def __init__(self, missing_tools: List[str]):
        self.missing_tools = missing_tools
        super().__init__(f"Missing required tools: {', '.join(missing_tools)}")


class ToolChecker:
    """
    Checks for availability of required external tools.
    
    Provides detailed installation instructions for missing tools
    based on the detected operating system.
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.system = platform.system().lower()
        
        # Define required tools with installation instructions
        self.tools = {
            'fpcalc': ToolInfo(
                name="Chromaprint Fingerprinter",
                command="fpcalc",
                priority=ToolPriority.REQUIRED,
                package_name="chromaprint",
                install_instructions={
                    'linux': "sudo apt-get install libchromaprint-tools",
                    'darwin': "brew install chromaprint",
                    'windows': "Download from https://acoustid.org/chromaprint and add to PATH"
                },
                check_command="fpcalc -version",
                min_version="1.4.0"
            ),
            'flac': ToolInfo(
                name="FLAC Audio Codec",
                command="flac",
                priority=ToolPriority.RECOMMENDED,
                package_name="flac",
                install_instructions={
                    'linux': "sudo apt-get install flac",
                    'darwin': "brew install flac",
                    'windows': "Download from https://xiph.org/flac/ and add to PATH"
                },
                check_command="flac --version"
            ),
            'ffmpeg': ToolInfo(
                name="FFmpeg Audio/Video Processor",
                command="ffmpeg",
                priority=ToolPriority.RECOMMENDED,
                package_name="ffmpeg",
                install_instructions={
                    'linux': "sudo apt-get install ffmpeg",
                    'darwin': "brew install ffmpeg", 
                    'windows': "Download from https://ffmpeg.org/ and add to PATH"
                },
                check_command="ffmpeg -version"
            ),
            'sox': ToolInfo(
                name="SoX Audio Processor",
                command="sox",
                priority=ToolPriority.OPTIONAL,
                package_name="sox",
                install_instructions={
                    'linux': "sudo apt-get install sox",
                    'darwin': "brew install sox",
                    'windows': "Download from http://sox.sourceforge.net/ and add to PATH"
                },
                check_command="sox --version"
            )
        }
    
    def check_required_tools(self) -> Tuple[List[str], List[str], List[str]]:
        """
        Check availability of all required tools.
        
        Returns:
            Tuple of (missing_required, missing_recommended, missing_optional)
        """
        missing_required = []
        missing_recommended = []
        missing_optional = []
        
        for tool_id, tool_info in self.tools.items():
            if not self._is_tool_available(tool_info):
                if tool_info.priority == ToolPriority.REQUIRED:
                    missing_required.append(tool_id)
                elif tool_info.priority == ToolPriority.RECOMMENDED:
                    missing_recommended.append(tool_id)
                else:
                    missing_optional.append(tool_id)
        
        return missing_required, missing_recommended, missing_optional
    
    def _is_tool_available(self, tool_info: ToolInfo) -> bool:
        """Check if a specific tool is available"""
        # First check if command exists
        if not shutil.which(tool_info.command):
            return False
        
        # If there's a version check command, verify it works
        if tool_info.check_command:
            try:
                result = subprocess.run(
                    tool_info.check_command.split(),
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                return result.returncode == 0
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                return False
        
        return True
    
    def get_tool_version(self, tool_id: str) -> Optional[str]:
        """Get version information for a specific tool"""
        if tool_id not in self.tools:
            return None
        
        tool_info = self.tools[tool_id]
        if not tool_info.check_command:
            return "unknown"
        
        try:
            result = subprocess.run(
                tool_info.check_command.split(),
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                # Extract version from output (simple approach)
                output = result.stdout + result.stderr
                lines = output.split('\\n')
                for line in lines:
                    if 'version' in line.lower() or any(char.isdigit() for char in line):
                        return line.strip()
                return "available"
            return None
        except Exception:
            return None
    
    def generate_install_instructions(self, missing_tools: List[str]) -> str:
        """Generate installation instructions for missing tools"""
        if not missing_tools:
            return "All required tools are available."
        
        instructions = []
        instructions.append("Missing tools detected. Please install the following:\\n")
        
        for tool_id in missing_tools:
            if tool_id not in self.tools:
                continue
                
            tool_info = self.tools[tool_id]
            priority_icon = {
                ToolPriority.REQUIRED: "🔴",
                ToolPriority.RECOMMENDED: "🟡", 
                ToolPriority.OPTIONAL: "🟢"
            }
            
            instructions.append(f"{priority_icon[tool_info.priority]} {tool_info.name} ({tool_info.command})")
            
            # Get OS-specific installation command
            install_cmd = tool_info.install_instructions.get(
                self.system, 
                tool_info.install_instructions.get('linux', 'Package manager install')
            )
            instructions.append(f"   Install: {install_cmd}")
            instructions.append("")
        
        # Add system-specific notes
        if self.system == 'windows':
            instructions.append("📝 Windows Note: After installation, make sure to add tools to your PATH environment variable.")
        elif self.system == 'darwin':
            instructions.append("📝 macOS Note: If you don't have Homebrew, install it from https://brew.sh/")
        else:
            instructions.append("📝 Linux Note: You may need to update your package manager cache first.")
        
        return "\\n".join(instructions)
    
    def check_and_raise_if_missing(self):
        """
        Check for required tools and raise exception if any are missing.
        
        Raises:
            ToolsMissingError: If required tools are missing
        """
        missing_required, missing_recommended, missing_optional = self.check_required_tools()
        
        if missing_required:
            # Log all missing tools for debugging
            self.logger.error(f"Required tools missing: {missing_required}")
            if missing_recommended:
                self.logger.warning(f"Recommended tools missing: {missing_recommended}")
            if missing_optional:
                self.logger.info(f"Optional tools missing: {missing_optional}")
            
            # Generate helpful error message
            tool_names = [self.tools[tool_id].command for tool_id in missing_required]
            instructions = self.generate_install_instructions(missing_required)
            
            error_msg = f"Missing required tools: {', '.join(tool_names)}\\n\\n{instructions}"
            raise ToolsMissingError([error_msg])
        
        # Log warnings for recommended tools
        if missing_recommended:
            self.logger.warning(f"Recommended tools missing: {missing_recommended}")
            instructions = self.generate_install_instructions(missing_recommended)
            self.logger.warning(f"Consider installing: \\n{instructions}")
        
        # Log info for optional tools
        if missing_optional:
            self.logger.info(f"Optional tools available for enhanced functionality: {missing_optional}")
    
    def get_tool_status_report(self) -> Dict[str, Dict[str, str]]:
        """
        Generate a comprehensive status report for all tools.
        
        Returns:
            Dictionary with tool status information
        """
        report = {}
        
        for tool_id, tool_info in self.tools.items():
            status = "available" if self._is_tool_available(tool_info) else "missing"
            version = self.get_tool_version(tool_id) if status == "available" else None
            
            report[tool_id] = {
                'name': tool_info.name,
                'command': tool_info.command,
                'status': status,
                'version': version or "unknown",
                'priority': tool_info.priority.value,
                'install_cmd': tool_info.install_instructions.get(self.system, "Check documentation")
            }
        
        return report
    
    def print_status_report(self):
        """Print a formatted status report to console"""
        print("\\n🔧 Tool Availability Report")
        print("=" * 50)
        
        report = self.get_tool_status_report()
        
        for tool_id, info in report.items():
            status_icon = "✅" if info['status'] == 'available' else "❌"
            priority_text = info['priority'].upper()
            
            print(f"{status_icon} {info['name']} ({info['command']}) - {priority_text}")
            
            if info['status'] == 'available':
                print(f"   Version: {info['version']}")
            else:
                print(f"   Install: {info['install_cmd']}")
            print()


# Global tool checker instance
_tool_checker: Optional[ToolChecker] = None

def get_tool_checker() -> ToolChecker:
    """Get global tool checker instance"""
    global _tool_checker
    if _tool_checker is None:
        _tool_checker = ToolChecker()
    return _tool_checker

def check_required_tools():
    """Convenience function to check required tools"""
    checker = get_tool_checker()
    checker.check_and_raise_if_missing()

def print_tool_status():
    """Convenience function to print tool status"""
    checker = get_tool_checker()
    checker.print_status_report()