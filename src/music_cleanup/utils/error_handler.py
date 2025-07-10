"""
User-Friendly Error Handling

Converts technical exceptions into understandable error messages
with helpful suggestions for users.
"""

import logging
import traceback
from enum import Enum
from typing import Dict, Optional, Any, List
from pathlib import Path


class ErrorCategory(Enum):
    """Categories of errors"""
    FILE_ACCESS = "file_access"
    AUDIO_PROCESSING = "audio_processing"
    CONFIGURATION = "configuration"
    DEPENDENCY = "dependency"
    NETWORK = "network"
    STORAGE = "storage"
    USER_INPUT = "user_input"
    SYSTEM = "system"


class UserFriendlyError:
    """User-friendly error representation"""
    
    def __init__(self, 
                 category: ErrorCategory,
                 title: str,
                 message: str,
                 suggestions: List[str] = None,
                 technical_details: str = None,
                 error_code: str = None):
        self.category = category
        self.title = title
        self.message = message
        self.suggestions = suggestions or []
        self.technical_details = technical_details
        self.error_code = error_code


class ErrorHandler:
    """
    Converts technical exceptions into user-friendly error messages.
    
    Features:
    - Categorizes errors by type
    - Provides helpful suggestions
    - Hides technical details unless requested
    - Supports localization
    """
    
    def __init__(self, verbose: bool = False, language: str = "en"):
        self.verbose = verbose
        self.language = language
        self.logger = logging.getLogger(__name__)
        
        # Error message templates
        self.error_templates = self._load_error_templates()
    
    def _load_error_templates(self) -> Dict[str, Dict[str, Any]]:
        """Load error message templates"""
        return {
            # File Access Errors
            "file_not_found": {
                "category": ErrorCategory.FILE_ACCESS,
                "title": "Datei nicht gefunden",
                "message": "Die Datei '{file_path}' konnte nicht gefunden werden.",
                "suggestions": [
                    "Überprüfen Sie, ob der Dateipfad korrekt ist",
                    "Stellen Sie sicher, dass die Datei existiert",
                    "Prüfen Sie die Schreibweise des Dateinamens"
                ]
            },
            "permission_denied": {
                "category": ErrorCategory.FILE_ACCESS,
                "title": "Zugriff verweigert", 
                "message": "Keine Berechtigung für '{file_path}'.",
                "suggestions": [
                    "Starten Sie das Programm als Administrator/Root",
                    "Überprüfen Sie die Dateiberechtigungen",
                    "Stellen Sie sicher, dass die Datei nicht von einem anderen Programm verwendet wird"
                ]
            },
            "disk_full": {
                "category": ErrorCategory.STORAGE,
                "title": "Speicherplatz voll",
                "message": "Nicht genügend Speicherplatz auf dem Zielverzeichnis.",
                "suggestions": [
                    "Löschen Sie unnötige Dateien",
                    "Wählen Sie ein anderes Zielverzeichnis",
                    "Überprüfen Sie den verfügbaren Speicherplatz"
                ]
            },
            
            # Audio Processing Errors
            "audio_corrupted": {
                "category": ErrorCategory.AUDIO_PROCESSING,
                "title": "Beschädigte Audiodatei",
                "message": "Die Audiodatei '{file_path}' ist beschädigt und kann nicht verarbeitet werden.",
                "suggestions": [
                    "Überprüfen Sie die Datei mit einem Audio-Player",
                    "Versuchen Sie, die Datei neu herunterzuladen",
                    "Verwenden Sie ein Reparatur-Tool für Audiodateien"
                ]
            },
            "unsupported_format": {
                "category": ErrorCategory.AUDIO_PROCESSING,
                "title": "Nicht unterstütztes Format",
                "message": "Das Audioformat '{format}' wird nicht unterstützt.",
                "suggestions": [
                    "Konvertieren Sie die Datei in ein unterstütztes Format (MP3, FLAC, WAV)",
                    "Überprüfen Sie die Liste der unterstützten Formate in der Dokumentation"
                ]
            },
            "fingerprinting_failed": {
                "category": ErrorCategory.AUDIO_PROCESSING,
                "title": "Fingerprint-Erstellung fehlgeschlagen",
                "message": "Der Audio-Fingerprint für '{file_path}' konnte nicht erstellt werden.",
                "suggestions": [
                    "Stellen Sie sicher, dass die Datei nicht beschädigt ist",
                    "Überprüfen Sie, ob Chromaprint installiert ist",
                    "Versuchen Sie es mit dem MD5-Fallback-Modus"
                ]
            },
            
            # Configuration Errors
            "config_invalid": {
                "category": ErrorCategory.CONFIGURATION,
                "title": "Ungültige Konfiguration",
                "message": "Die Konfiguration enthält ungültige Werte: {issues}",
                "suggestions": [
                    "Überprüfen Sie die Konfigurationsdatei",
                    "Verwenden Sie die Standard-Konfiguration",
                    "Konsultieren Sie die Dokumentation für gültige Werte"
                ]
            },
            "config_not_found": {
                "category": ErrorCategory.CONFIGURATION,
                "title": "Konfiguration nicht gefunden",
                "message": "Die Konfigurationsdatei '{config_path}' wurde nicht gefunden.",
                "suggestions": [
                    "Erstellen Sie eine neue Konfigurationsdatei",
                    "Verwenden Sie die Standard-Konfiguration",
                    "Überprüfen Sie den Pfad zur Konfigurationsdatei"
                ]
            },
            
            # Dependency Errors
            "missing_dependency": {
                "category": ErrorCategory.DEPENDENCY,
                "title": "Fehlende Abhängigkeit",
                "message": "Die erforderliche Bibliothek '{dependency}' ist nicht installiert.",
                "suggestions": [
                    "Installieren Sie die Abhängigkeit: pip install {dependency}",
                    "Führen Sie 'pip install -r requirements.txt' aus",
                    "Überprüfen Sie die Installationsanweisungen"
                ]
            },
            "chromaprint_missing": {
                "category": ErrorCategory.DEPENDENCY,
                "title": "Chromaprint nicht verfügbar",
                "message": "Chromaprint (fpcalc) ist nicht installiert oder nicht im PATH.",
                "suggestions": [
                    "Ubuntu/Debian: sudo apt-get install libchromaprint-tools",
                    "macOS: brew install chromaprint",
                    "Windows: Laden Sie Chromaprint von acoustid.org herunter",
                    "Alternativ: Verwenden Sie den MD5-Modus mit --fingerprint-algorithm md5"
                ]
            },
            
            # Network Errors
            "network_timeout": {
                "category": ErrorCategory.NETWORK,
                "title": "Netzwerk-Timeout",
                "message": "Die Netzwerkverbindung ist zu langsam oder nicht verfügbar.",
                "suggestions": [
                    "Überprüfen Sie Ihre Internetverbindung",
                    "Versuchen Sie es später erneut",
                    "Verwenden Sie einen anderen Netzwerk-Provider"
                ]
            },
            
            # Storage Errors
            "database_error": {
                "category": ErrorCategory.STORAGE,
                "title": "Datenbank-Fehler",
                "message": "Ein Fehler bei der Datenbank-Operation ist aufgetreten.",
                "suggestions": [
                    "Überprüfen Sie den verfügbaren Speicherplatz",
                    "Stellen Sie sicher, dass keine andere Instanz läuft",
                    "Versuchen Sie, die Datenbank neu zu erstellen"
                ]
            },
            
            # User Input Errors
            "invalid_path": {
                "category": ErrorCategory.USER_INPUT,
                "title": "Ungültiger Pfad",
                "message": "Der angegebene Pfad '{path}' ist ungültig.",
                "suggestions": [
                    "Überprüfen Sie die Pfad-Syntax",
                    "Verwenden Sie absolute Pfade",
                    "Stellen Sie sicher, dass der Pfad existiert"
                ]
            },
            "invalid_option": {
                "category": ErrorCategory.USER_INPUT,
                "title": "Ungültige Option",
                "message": "Der Wert '{value}' ist für die Option '{option}' ungültig.",
                "suggestions": [
                    "Überprüfen Sie die gültigen Werte in der Hilfe",
                    "Verwenden Sie --help für weitere Informationen"
                ]
            },
            
            # System Errors
            "memory_error": {
                "category": ErrorCategory.SYSTEM,
                "title": "Speicher-Fehler",
                "message": "Nicht genügend Arbeitsspeicher verfügbar.",
                "suggestions": [
                    "Schließen Sie andere Programme",
                    "Verringern Sie die Batch-Größe mit --batch-size",
                    "Verwenden Sie --memory-limit um das Memory-Limit zu setzen"
                ]
            },
            "system_error": {
                "category": ErrorCategory.SYSTEM,
                "title": "System-Fehler",
                "message": "Ein unerwarteter System-Fehler ist aufgetreten.",
                "suggestions": [
                    "Starten Sie das Programm neu",
                    "Überprüfen Sie die System-Logs",
                    "Kontaktieren Sie den Support mit den technischen Details"
                ]
            }
        }
    
    def handle_exception(self, exception: Exception, context: Dict[str, Any] = None) -> UserFriendlyError:
        """
        Convert exception to user-friendly error.
        
        Args:
            exception: The original exception
            context: Additional context information
            
        Returns:
            UserFriendlyError object
        """
        context = context or {}
        
        # Determine error type and create appropriate error
        error_key = self._classify_exception(exception, context)
        error_info = self.error_templates.get(error_key, self.error_templates["system_error"])
        
        # Format message with context
        try:
            formatted_message = error_info["message"].format(**context)
        except (KeyError, ValueError):
            formatted_message = error_info["message"]
        
        # Get technical details if verbose mode
        technical_details = None
        if self.verbose:
            technical_details = f"{type(exception).__name__}: {str(exception)}\n{traceback.format_exc()}"
        
        return UserFriendlyError(
            category=error_info["category"],
            title=error_info["title"],
            message=formatted_message,
            suggestions=error_info["suggestions"].copy(),
            technical_details=technical_details,
            error_code=error_key
        )
    
    def _classify_exception(self, exception: Exception, context: Dict[str, Any]) -> str:
        """Classify exception to determine error template"""
        
        # File access errors
        if isinstance(exception, FileNotFoundError):
            return "file_not_found"
        elif isinstance(exception, PermissionError):
            return "permission_denied"
        elif isinstance(exception, OSError):
            if "No space left on device" in str(exception):
                return "disk_full"
            return "system_error"
        
        # Import errors (dependencies)
        elif isinstance(exception, ImportError):
            if "mutagen" in str(exception):
                return "missing_dependency"
            elif "numpy" in str(exception):
                return "missing_dependency"
            else:
                return "missing_dependency"
        
        # Subprocess errors (Chromaprint)
        elif isinstance(exception, FileNotFoundError) and "fpcalc" in str(exception):
            return "chromaprint_missing"
        
        # Memory errors
        elif isinstance(exception, MemoryError):
            return "memory_error"
        
        # Network errors
        elif isinstance(exception, (ConnectionError, TimeoutError)):
            return "network_timeout"
        
        # Configuration errors
        elif isinstance(exception, ValueError):
            if context.get("config_validation"):
                return "config_invalid"
            elif context.get("user_input"):
                return "invalid_option"
            return "system_error"
        
        # Audio processing errors
        elif "mutagen" in str(type(exception)) or "audio" in str(exception).lower():
            if "corrupt" in str(exception).lower():
                return "audio_corrupted"
            elif "format" in str(exception).lower():
                return "unsupported_format"
            else:
                return "fingerprinting_failed"
        
        # Database errors
        elif "sqlite" in str(type(exception)).lower() or "database" in str(exception).lower():
            return "database_error"
        
        # Default to system error
        else:
            return "system_error"
    
    def format_error_message(self, error: UserFriendlyError, show_suggestions: bool = True) -> str:
        """Format error for display"""
        lines = []
        
        # Title and main message
        lines.append(f"❌ {error.title}")
        lines.append(f"   {error.message}")
        lines.append("")
        
        # Suggestions
        if show_suggestions and error.suggestions:
            lines.append("💡 Lösungsvorschläge:")
            for suggestion in error.suggestions:
                lines.append(f"   • {suggestion}")
            lines.append("")
        
        # Technical details (if verbose)
        if self.verbose and error.technical_details:
            lines.append("🔧 Technische Details:")
            for line in error.technical_details.split('\n'):
                if line.strip():
                    lines.append(f"   {line}")
            lines.append("")
        
        # Error code
        if error.error_code:
            lines.append(f"🔍 Fehler-Code: {error.error_code}")
        
        return '\n'.join(lines)
    
    def log_error(self, error: UserFriendlyError, original_exception: Exception = None):
        """Log error with appropriate level"""
        
        # Log user-friendly message at appropriate level
        if error.category in [ErrorCategory.USER_INPUT, ErrorCategory.CONFIGURATION]:
            self.logger.warning(f"User Error: {error.title} - {error.message}")
        elif error.category == ErrorCategory.DEPENDENCY:
            self.logger.error(f"Dependency Error: {error.title} - {error.message}")
        else:
            self.logger.error(f"System Error: {error.title} - {error.message}")
        
        # Log technical details at debug level
        if original_exception and self.verbose:
            self.logger.debug(f"Technical details: {error.technical_details}")


# Global error handler instance
_error_handler: Optional[ErrorHandler] = None

def get_error_handler(verbose: bool = False) -> ErrorHandler:
    """Get global error handler instance"""
    global _error_handler
    if _error_handler is None or _error_handler.verbose != verbose:
        _error_handler = ErrorHandler(verbose=verbose)
    return _error_handler

def handle_user_error(exception: Exception, context: Dict[str, Any] = None, verbose: bool = False) -> str:
    """Convenience function to handle and format error"""
    handler = get_error_handler(verbose)
    error = handler.handle_exception(exception, context)
    handler.log_error(error, exception)
    return handler.format_error_message(error)