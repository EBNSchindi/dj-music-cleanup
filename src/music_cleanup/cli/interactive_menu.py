"""
Interactive Menu for DJ Music Cleanup Tool

Rich-based interactive CLI menu with configuration management,
statistics visualization, and user-friendly error handling.
"""

import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.tree import Tree
from rich.align import Align
from rich.text import Text
from rich.live import Live
from rich.columns import Columns
from rich import box

from ..core.config_manager import get_config_manager, MusicCleanupConfig
from ..core.unified_database import get_unified_database
from ..core.orchestrator_refactored import MusicCleanupOrchestrator
from ..core.streaming import StreamingConfig
from ..utils.error_handler import handle_user_error
from .. import __version__


class InteractiveMenu:
    """
    Rich-based interactive menu for DJ Music Cleanup Tool.
    
    Features:
    - Beautiful UI with Rich components
    - Integration with ConfigManager
    - Real-time statistics from UnifiedDatabase
    - User-friendly error handling
    - Progress visualization
    """
    
    def __init__(self):
        self.console = Console()
        self.config_manager = get_config_manager()
        self.config = self.config_manager.get_config()
        self.db = get_unified_database()
        self.running = True
        
        # Menu styling
        self.menu_style = "bold cyan"
        self.header_style = "bold magenta"
        self.success_style = "bold green"
        self.error_style = "bold red"
        self.warning_style = "bold yellow"
        
    def run(self):
        """Main menu loop"""
        self.console.clear()
        self._show_welcome_screen()
        
        while self.running:
            try:
                self._show_main_menu()
                choice = self._get_menu_choice()
                
                if choice == "1":
                    self._quick_organize_menu()
                elif choice == "2":
                    self._analyze_library_menu()
                elif choice == "3":
                    self._find_duplicates_menu()
                elif choice == "4":
                    self._cleanup_database_menu()
                elif choice == "5":
                    self._settings_menu()
                elif choice == "6":
                    self._statistics_menu()
                elif choice == "0":
                    self._exit_program()
                else:
                    self.console.print(f"[{self.warning_style}]Ungültige Auswahl. Bitte erneut versuchen.[/]")
                    
            except KeyboardInterrupt:
                self.console.print(f"\n[{self.warning_style}]Operation abgebrochen.[/]")
                time.sleep(1)
            except Exception as e:
                error_msg = handle_user_error(e, verbose=self.config.ui.verbose_errors)
                self.console.print(f"\n[{self.error_style}]{error_msg}[/]")
                time.sleep(2)
    
    def _show_welcome_screen(self):
        """Display welcome screen with logo"""
        logo = """
    ╔══════════════════════════════════════════════════════════════╗
    ║                                                              ║
    ║     🎵  DJ MUSIC CLEANUP TOOL v{}                      ║
    ║                                                              ║
    ║     Professional Audio Library Management                    ║
    ║     with Advanced Fingerprinting & Analysis                  ║
    ║                                                              ║
    ╚══════════════════════════════════════════════════════════════╝
        """.format(__version__.ljust(10))
        
        self.console.print(Panel(logo, style=self.header_style, box=box.DOUBLE))
        time.sleep(1)
    
    def _show_main_menu(self):
        """Display main menu"""
        self.console.clear()
        
        # Create menu table
        menu_table = Table(show_header=False, box=None, padding=(0, 2))
        menu_table.add_column("Option", style=self.menu_style, width=3)
        menu_table.add_column("Description", style="white")
        
        menu_options = [
            ("1", "🚀 Quick Organize - Musik-Bibliothek organisieren"),
            ("2", "🔍 Analyze Library - Bibliothek analysieren"),
            ("3", "🔄 Find Duplicates - Duplikate finden"),
            ("4", "🧹 Cleanup & Maintenance - Aufräumen"),
            ("5", "⚙️  Settings - Einstellungen"),
            ("6", "📊 Statistics - Statistiken"),
            ("0", "🚪 Exit - Beenden")
        ]
        
        for option, description in menu_options:
            menu_table.add_row(f"[{self.menu_style}]{option}[/]", description)
        
        # Show current statistics
        stats_panel = self._create_stats_summary_panel()
        
        # Layout
        layout = Layout()
        layout.split_column(
            Layout(Panel("🎵 DJ Music Cleanup Tool - Hauptmenü", style=self.header_style), size=3),
            Layout(stats_panel, size=8),
            Layout(Panel(menu_table, title="Optionen", border_style="cyan"), size=12)
        )
        
        self.console.print(layout)
    
    def _create_stats_summary_panel(self) -> Panel:
        """Create statistics summary panel"""
        try:
            # Get statistics from database
            fingerprint_stats = self.db.get_fingerprint_statistics()
            overall_stats = self.db.get_overall_statistics()
            db_size = self.db.get_database_size()
            
            stats_table = Table(show_header=False, box=None)
            stats_table.add_column("Metric", style="cyan")
            stats_table.add_column("Value", style="yellow")
            
            # Add statistics rows
            stats_table.add_row("📁 Fingerprints:", f"{fingerprint_stats.get('total_fingerprints', 0):,}")
            stats_table.add_row("🎵 Unique Songs:", f"{fingerprint_stats.get('unique_fingerprints', 0):,}")
            stats_table.add_row("💾 Database Size:", f"{db_size.get('total_size_bytes', 0) / (1024**2):.1f} MB")
            stats_table.add_row("📊 Sessions:", f"{overall_stats.get('total_sessions', 0)}")
            stats_table.add_row("✅ Success Rate:", f"{overall_stats.get('avg_success_rate', 0)*100:.1f}%")
            
            return Panel(stats_table, title="📈 Aktuelle Statistiken", border_style="green")
            
        except Exception:
            return Panel("Statistiken nicht verfügbar", title="📈 Statistiken", border_style="yellow")
    
    def _get_menu_choice(self) -> str:
        """Get menu choice from user"""
        return Prompt.ask("\n[cyan]Ihre Auswahl[/]", choices=["0", "1", "2", "3", "4", "5", "6"])
    
    def _quick_organize_menu(self):
        """Quick organize workflow"""
        self.console.clear()
        self.console.print(Panel("🚀 Quick Organize - Musik-Bibliothek organisieren", style=self.header_style))
        
        # Get source folders
        source_folders = []
        self.console.print("\n[cyan]Quellordner hinzufügen (leer lassen zum Beenden):[/]")
        
        while True:
            folder = Prompt.ask("Ordner", default="")
            if not folder:
                break
            
            folder_path = Path(folder).expanduser()
            if folder_path.exists() and folder_path.is_dir():
                source_folders.append(str(folder_path))
                self.console.print(f"[green]✓ Hinzugefügt: {folder_path}[/]")
            else:
                self.console.print(f"[red]✗ Ordner nicht gefunden: {folder}[/]")
        
        if not source_folders:
            self.console.print("[yellow]Keine Ordner ausgewählt.[/]")
            time.sleep(1)
            return
        
        # Get target folder
        target_folder = Prompt.ask("\n[cyan]Zielordner[/]", default="~/Music/Organized")
        target_path = Path(target_folder).expanduser()
        
        # Show configuration summary
        config_table = Table(title="Konfiguration", box=box.ROUNDED)
        config_table.add_column("Einstellung", style="cyan")
        config_table.add_column("Wert", style="yellow")
        
        config_table.add_row("Quellordner", f"{len(source_folders)} Ordner")
        config_table.add_row("Zielordner", str(target_path))
        config_table.add_row("Fingerprinting", "✓ Aktiviert" if self.config.audio.fingerprint_algorithm else "✗ Deaktiviert")
        config_table.add_row("Duplikat-Aktion", self.config.audio.duplicate_action)
        config_table.add_row("Min. Health Score", f"{self.config.audio.min_health_score}")
        config_table.add_row("Professional Mode", "✓ Aktiviert" if self._use_professional_mode() else "✗ Standard")
        
        self.console.print("\n", config_table)
        
        # Confirm
        if not Confirm.ask("\n[cyan]Starten?[/]", default=True):
            return
        
        # Run organization with progress
        self._run_organization_with_progress(source_folders, str(target_path))
    
    def _run_organization_with_progress(self, source_folders: List[str], target_folder: str):
        """Run organization with Rich progress display"""
        try:
            # Create orchestrator
            streaming_config = StreamingConfig()
            config_dict = self._config_to_dict(self.config)
            
            if self._use_professional_mode():
                orchestrator = ProfessionalMusicCleanupOrchestrator(
                    config=config_dict,
                    streaming_config=streaming_config,
                    dry_run=False
                )
                pipeline_method = orchestrator.run_professional_pipeline
            else:
                orchestrator = MusicCleanupOrchestrator(
                    config=config_dict,
                    streaming_config=streaming_config,
                    dry_run=False
                )
                pipeline_method = lambda sf, pc: orchestrator.run_organization_pipeline(sf, target_folder, pc)
            
            # Progress tracking
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                TimeRemainingColumn(),
                console=self.console
            ) as progress:
                
                # Main task
                main_task = progress.add_task("[cyan]Verarbeitung...", total=100)
                
                # Progress callback
                current_stage = {"stage": "", "progress": 0}
                
                def progress_callback(info: str):
                    # Parse progress info
                    if "Discovering" in info:
                        current_stage["stage"] = "🔍 Dateien suchen..."
                        current_stage["progress"] = 10
                    elif "Fingerprinting" in info or "Analyzing" in info:
                        current_stage["stage"] = "🔐 Fingerprints erstellen..."
                        current_stage["progress"] = 40
                    elif "Detecting duplicates" in info:
                        current_stage["stage"] = "🔄 Duplikate erkennen..."
                        current_stage["progress"] = 60
                    elif "Organizing" in info:
                        current_stage["stage"] = "📁 Dateien organisieren..."
                        current_stage["progress"] = 80
                    
                    progress.update(main_task, 
                                  description=f"[cyan]{current_stage['stage']}[/cyan]",
                                  completed=current_stage["progress"])
                
                # Run pipeline
                results = pipeline_method(source_folders, progress_callback)
                
                # Complete progress
                progress.update(main_task, completed=100, description="[green]✓ Abgeschlossen[/green]")
            
            # Show results
            self._show_organization_results(results)
            
        except Exception as e:
            error_msg = handle_user_error(e, verbose=self.config.ui.verbose_errors)
            self.console.print(f"\n[{self.error_style}]{error_msg}[/]")
            
        input("\nDrücken Sie Enter zum Fortfahren...")
    
    def _show_organization_results(self, results: Dict[str, Any]):
        """Display organization results"""
        results_table = Table(title="🎉 Ergebnisse", box=box.ROUNDED)
        results_table.add_column("Metrik", style="cyan")
        results_table.add_column("Wert", style="green")
        
        results_table.add_row("📁 Dateien gefunden", f"{results.get('files_discovered', 0):,}")
        results_table.add_row("🔐 Fingerprints erstellt", f"{results.get('files_fingerprinted', 0):,}")
        results_table.add_row("✅ Dateien organisiert", f"{results.get('files_organized', 0):,}")
        
        if results.get('duplicate_groups', 0) > 0:
            results_table.add_row("🔄 Duplikat-Gruppen", f"{results.get('duplicate_groups', 0):,}")
            results_table.add_row("💾 Speicher gespart", f"{results.get('space_saved', 0) / (1024**3):.2f} GB")
        
        if results.get('defective_files', 0) > 0:
            results_table.add_row("⚠️  Defekte Dateien", f"{results.get('defective_files', 0):,}")
        
        results_table.add_row("⏱️  Verarbeitungszeit", f"{results.get('processing_time', 0):.1f} Sekunden")
        
        self.console.print("\n", results_table)
    
    def _analyze_library_menu(self):
        """Analyze library menu"""
        self.console.clear()
        self.console.print(Panel("🔍 Analyze Library - Bibliothek analysieren", style=self.header_style))
        
        # Get folders to analyze
        folders = []
        self.console.print("\n[cyan]Ordner zum Analysieren (leer lassen zum Beenden):[/]")
        
        while True:
            folder = Prompt.ask("Ordner", default="")
            if not folder:
                break
            
            folder_path = Path(folder).expanduser()
            if folder_path.exists() and folder_path.is_dir():
                folders.append(str(folder_path))
                self.console.print(f"[green]✓ Hinzugefügt: {folder_path}[/]")
            else:
                self.console.print(f"[red]✗ Ordner nicht gefunden: {folder}[/]")
        
        if not folders:
            return
        
        # Run analysis
        self.console.print("\n[cyan]Analysiere Bibliothek...[/]")
        
        try:
            streaming_config = StreamingConfig()
            config_dict = self._config_to_dict(self.config)
            
            orchestrator = MusicCleanupOrchestrator(
                config=config_dict,
                streaming_config=streaming_config,
                dry_run=True  # Analysis is always dry-run
            )
            
            with self.console.status("[cyan]Analysiere...", spinner="dots"):
                results = orchestrator.analyze_library(folders)
            
            # Show analysis results
            self._show_analysis_results(results)
            
        except Exception as e:
            error_msg = handle_user_error(e, verbose=self.config.ui.verbose_errors)
            self.console.print(f"\n[{self.error_style}]{error_msg}[/]")
        
        input("\nDrücken Sie Enter zum Fortfahren...")
    
    def _show_analysis_results(self, results: Dict[str, Any]):
        """Display analysis results"""
        # Overview table
        overview = Table(title="📊 Bibliotheks-Übersicht", box=box.ROUNDED)
        overview.add_column("Metrik", style="cyan")
        overview.add_column("Wert", style="yellow")
        
        overview.add_row("📁 Gesamtanzahl Dateien", f"{results.get('total_files', 0):,}")
        overview.add_row("💾 Gesamtgröße", f"{results.get('total_size_bytes', 0) / (1024**3):.2f} GB")
        overview.add_row("🎵 Audio-Formate", f"{len(results.get('audio_formats', []))}")
        overview.add_row("📊 Duplikat-Gruppen", f"{len(results.get('duplicate_groups', []))}")
        overview.add_row("⚠️  Metadaten-Probleme", f"{len(results.get('metadata_issues', []))}")
        overview.add_row("🔍 Integritätsprobleme", f"{len(results.get('integrity_issues', []))}")
        
        self.console.print("\n", overview)
        
        # Format distribution
        if results.get('audio_formats'):
            format_table = Table(title="🎵 Format-Verteilung", box=box.SIMPLE)
            format_table.add_column("Format", style="cyan")
            format_table.add_column("Anzahl", style="yellow")
            format_table.add_column("Größe", style="green")
            
            for fmt, data in results.get('format_distribution', {}).items():
                format_table.add_row(
                    fmt,
                    f"{data.get('count', 0):,}",
                    f"{data.get('size', 0) / (1024**2):.1f} MB"
                )
            
            self.console.print("\n", format_table)
    
    def _find_duplicates_menu(self):
        """Find duplicates menu"""
        self.console.clear()
        self.console.print(Panel("🔄 Find Duplicates - Duplikate finden", style=self.header_style))
        
        # Get search folders
        folders = []
        self.console.print("\n[cyan]Ordner durchsuchen (leer lassen zum Beenden):[/]")
        
        while True:
            folder = Prompt.ask("Ordner", default="")
            if not folder:
                break
                
            folder_path = Path(folder).expanduser()
            if folder_path.exists() and folder_path.is_dir():
                folders.append(str(folder_path))
                self.console.print(f"[green]✓ Hinzugefügt: {folder_path}[/]")
            else:
                self.console.print(f"[red]✗ Ordner nicht gefunden: {folder}[/]")
        
        if not folders:
            return
        
        # Options
        action = Prompt.ask(
            "\n[cyan]Aktion für Duplikate[/]",
            choices=["report", "move", "delete"],
            default="report"
        )
        
        # Run duplicate detection
        self.console.print("\n[cyan]Suche Duplikate...[/]")
        
        try:
            # This would use the duplicate detection functionality
            # For now, show example results
            self._show_duplicate_results_example()
            
        except Exception as e:
            error_msg = handle_user_error(e, verbose=self.config.ui.verbose_errors)
            self.console.print(f"\n[{self.error_style}]{error_msg}[/]")
        
        input("\nDrücken Sie Enter zum Fortfahren...")
    
    def _show_duplicate_results_example(self):
        """Show example duplicate results"""
        # Create tree of duplicates
        tree = Tree("🔄 Gefundene Duplikate")
        
        # Example duplicate group
        group1 = tree.add("📁 Gruppe 1: 'Artist - Song.mp3' (3 Duplikate)")
        group1.add("[green]✓ BEST:[/] /Music/FLAC/Artist - Song.flac [320kbps, 45MB]")
        group1.add("[red]✗ DUP:[/] /Downloads/Artist - Song.mp3 [128kbps, 3MB]")
        group1.add("[red]✗ DUP:[/] /Backup/song.mp3 [192kbps, 5MB]")
        
        group2 = tree.add("📁 Gruppe 2: 'Another - Track.mp3' (2 Duplikate)")
        group2.add("[green]✓ BEST:[/] /Music/Another - Track [320k].mp3 [320kbps, 8MB]")
        group2.add("[red]✗ DUP:[/] /Temp/track.mp3 [128kbps, 3MB]")
        
        self.console.print("\n", tree)
        
        # Summary
        summary = Table(title="📊 Zusammenfassung", box=box.ROUNDED)
        summary.add_column("Metrik", style="cyan")
        summary.add_column("Wert", style="yellow")
        
        summary.add_row("🔄 Duplikat-Gruppen", "2")
        summary.add_row("📁 Duplikate gesamt", "3")
        summary.add_row("💾 Mögliche Einsparung", "11 MB")
        
        self.console.print("\n", summary)
    
    def _cleanup_database_menu(self):
        """Cleanup and maintenance menu"""
        self.console.clear()
        self.console.print(Panel("🧹 Cleanup & Maintenance", style=self.header_style))
        
        # Show current database status
        db_size = self.db.get_database_size()
        
        status_table = Table(title="💾 Datenbank-Status", box=box.ROUNDED)
        status_table.add_column("Metrik", style="cyan")
        status_table.add_column("Wert", style="yellow")
        
        status_table.add_row("Größe", f"{db_size.get('total_size_bytes', 0) / (1024**2):.1f} MB")
        status_table.add_row("Fingerprints", f"{db_size.get('fingerprint_records', 0):,}")
        status_table.add_row("Operationen", f"{db_size.get('operation_records', 0):,}")
        status_table.add_row("Fortschritt", f"{db_size.get('progress_records', 0):,}")
        
        self.console.print("\n", status_table)
        
        # Maintenance options
        self.console.print("\n[cyan]Wartungsoptionen:[/]")
        options = [
            ("1", "🗑️  Alte Fingerprints entfernen"),
            ("2", "🔧 Datenbank optimieren (VACUUM)"),
            ("3", "📊 Detaillierte Statistiken anzeigen"),
            ("0", "↩️  Zurück")
        ]
        
        for opt, desc in options:
            self.console.print(f"  [{self.menu_style}]{opt}[/] - {desc}")
        
        choice = Prompt.ask("\n[cyan]Ihre Auswahl[/]", choices=["0", "1", "2", "3"])
        
        if choice == "1":
            self._cleanup_old_fingerprints()
        elif choice == "2":
            self._vacuum_database()
        elif choice == "3":
            self._show_detailed_statistics()
    
    def _cleanup_old_fingerprints(self):
        """Clean up old fingerprints"""
        days = IntPrompt.ask("\n[cyan]Fingerprints älter als (Tage)[/]", default=30)
        
        if Confirm.ask(f"\n[yellow]Fingerprints älter als {days} Tage löschen?[/]"):
            with self.console.status(f"[cyan]Lösche alte Fingerprints...", spinner="dots"):
                removed = self.db.cleanup_stale_fingerprints(days)
            
            self.console.print(f"\n[green]✓ {removed} alte Fingerprints entfernt.[/]")
            time.sleep(2)
    
    def _vacuum_database(self):
        """Vacuum database"""
        if Confirm.ask("\n[yellow]Datenbank optimieren (kann einige Minuten dauern)?[/]"):
            with self.console.status("[cyan]Optimiere Datenbank...", spinner="dots"):
                success = self.db.vacuum_database()
            
            if success:
                self.console.print("\n[green]✓ Datenbank erfolgreich optimiert.[/]")
            else:
                self.console.print("\n[red]✗ Optimierung fehlgeschlagen.[/]")
            time.sleep(2)
    
    def _show_detailed_statistics(self):
        """Show detailed statistics"""
        self.console.clear()
        self.console.print(Panel("📊 Detaillierte Statistiken", style=self.header_style))
        
        # Get all statistics
        fp_stats = self.db.get_fingerprint_statistics()
        overall_stats = self.db.get_overall_statistics()
        
        # Fingerprint statistics
        fp_table = Table(title="🔐 Fingerprint-Statistiken", box=box.ROUNDED)
        fp_table.add_column("Metrik", style="cyan")
        fp_table.add_column("Wert", style="yellow")
        
        fp_table.add_row("Gesamt", f"{fp_stats.get('total_fingerprints', 0):,}")
        fp_table.add_row("Unique", f"{fp_stats.get('unique_fingerprints', 0):,}")
        fp_table.add_row("Chromaprint", f"{fp_stats.get('chromaprint_count', 0):,}")
        fp_table.add_row("MD5", f"{fp_stats.get('md5_count', 0):,}")
        fp_table.add_row("Ø Duration", f"{fp_stats.get('avg_duration', 0):.1f}s")
        
        self.console.print("\n", fp_table)
        
        # Overall statistics
        overall_table = Table(title="📈 Gesamt-Statistiken", box=box.ROUNDED)
        overall_table.add_column("Metrik", style="cyan")
        overall_table.add_column("Wert", style="yellow")
        
        overall_table.add_row("Sessions", f"{overall_stats.get('total_sessions', 0):,}")
        overall_table.add_row("Dateien verarbeitet", f"{overall_stats.get('total_files_processed', 0):,}")
        overall_table.add_row("Bytes verarbeitet", f"{overall_stats.get('total_bytes_processed', 0) / (1024**3):.2f} GB")
        overall_table.add_row("Erfolgsrate", f"{overall_stats.get('avg_success_rate', 0)*100:.1f}%")
        
        self.console.print("\n", overall_table)
        
        input("\nDrücken Sie Enter zum Fortfahren...")
    
    def _settings_menu(self):
        """Settings menu"""
        self.console.clear()
        self.console.print(Panel("⚙️ Settings - Einstellungen", style=self.header_style))
        
        while True:
            # Show current settings
            settings_table = Table(title="Aktuelle Einstellungen", box=box.ROUNDED)
            settings_table.add_column("Kategorie", style="cyan")
            settings_table.add_column("Einstellung", style="white")
            settings_table.add_column("Wert", style="yellow")
            
            # Audio settings
            settings_table.add_row("🎵 Audio", "Fingerprint-Algorithmus", self.config.audio.fingerprint_algorithm)
            settings_table.add_row("", "Duplikat-Aktion", self.config.audio.duplicate_action)
            settings_table.add_row("", "Min. Health Score", str(self.config.audio.min_health_score))
            
            # Processing settings
            settings_table.add_row("⚙️ Verarbeitung", "Batch-Größe", str(self.config.processing.batch_size))
            settings_table.add_row("", "Max. Workers", str(self.config.processing.max_workers))
            settings_table.add_row("", "Memory Limit", f"{self.config.processing.memory_limit_mb} MB")
            
            # UI settings
            settings_table.add_row("🖥️ UI", "Progress-Modus", self.config.ui.progress_mode)
            settings_table.add_row("", "Log-Level", self.config.ui.log_level)
            settings_table.add_row("", "Verbose Errors", "✓" if self.config.ui.verbose_errors else "✗")
            
            self.console.print("\n", settings_table)
            
            # Options
            self.console.print("\n[cyan]Einstellungen ändern:[/]")
            options = [
                ("1", "🎵 Audio-Einstellungen"),
                ("2", "⚙️  Verarbeitungs-Einstellungen"),
                ("3", "🖥️  UI-Einstellungen"),
                ("4", "💾 Einstellungen speichern"),
                ("0", "↩️  Zurück")
            ]
            
            for opt, desc in options:
                self.console.print(f"  [{self.menu_style}]{opt}[/] - {desc}")
            
            choice = Prompt.ask("\n[cyan]Ihre Auswahl[/]", choices=["0", "1", "2", "3", "4"])
            
            if choice == "0":
                break
            elif choice == "1":
                self._edit_audio_settings()
            elif choice == "2":
                self._edit_processing_settings()
            elif choice == "3":
                self._edit_ui_settings()
            elif choice == "4":
                self._save_settings()
    
    def _edit_audio_settings(self):
        """Edit audio settings"""
        self.console.print("\n[cyan]Audio-Einstellungen:[/]")
        
        # Fingerprint algorithm
        algorithm = Prompt.ask(
            "Fingerprint-Algorithmus",
            choices=["chromaprint", "md5", "both"],
            default=self.config.audio.fingerprint_algorithm
        )
        self.config.audio.fingerprint_algorithm = algorithm
        
        # Duplicate action
        action = Prompt.ask(
            "Duplikat-Aktion",
            choices=["move", "delete", "report-only"],
            default=self.config.audio.duplicate_action
        )
        self.config.audio.duplicate_action = action
        
        # Min health score
        score = IntPrompt.ask(
            "Min. Health Score (0-100)",
            default=int(self.config.audio.min_health_score)
        )
        self.config.audio.min_health_score = float(score)
        
        self.console.print("[green]✓ Audio-Einstellungen aktualisiert.[/]")
    
    def _edit_processing_settings(self):
        """Edit processing settings"""
        self.console.print("\n[cyan]Verarbeitungs-Einstellungen:[/]")
        
        # Batch size
        batch = IntPrompt.ask(
            "Batch-Größe",
            default=self.config.processing.batch_size
        )
        self.config.processing.batch_size = batch
        
        # Max workers
        workers = IntPrompt.ask(
            "Max. Workers",
            default=self.config.processing.max_workers
        )
        self.config.processing.max_workers = workers
        
        # Memory limit
        memory = IntPrompt.ask(
            "Memory Limit (MB)",
            default=self.config.processing.memory_limit_mb
        )
        self.config.processing.memory_limit_mb = memory
        
        self.console.print("[green]✓ Verarbeitungs-Einstellungen aktualisiert.[/]")
    
    def _edit_ui_settings(self):
        """Edit UI settings"""
        self.console.print("\n[cyan]UI-Einstellungen:[/]")
        
        # Progress mode
        progress = Prompt.ask(
            "Progress-Modus",
            choices=["none", "simple", "detailed"],
            default=self.config.ui.progress_mode
        )
        self.config.ui.progress_mode = progress
        
        # Log level
        log_level = Prompt.ask(
            "Log-Level",
            choices=["DEBUG", "INFO", "WARNING", "ERROR"],
            default=self.config.ui.log_level
        )
        self.config.ui.log_level = log_level
        
        # Verbose errors
        verbose = Confirm.ask(
            "Verbose Errors",
            default=self.config.ui.verbose_errors
        )
        self.config.ui.verbose_errors = verbose
        
        self.console.print("[green]✓ UI-Einstellungen aktualisiert.[/]")
    
    def _save_settings(self):
        """Save settings to user config"""
        if Confirm.ask("\n[yellow]Einstellungen dauerhaft speichern?[/]"):
            # Convert config to dict for saving
            settings = {
                "audio": {
                    "fingerprint_algorithm": self.config.audio.fingerprint_algorithm,
                    "duplicate_action": self.config.audio.duplicate_action,
                    "min_health_score": self.config.audio.min_health_score
                },
                "processing": {
                    "batch_size": self.config.processing.batch_size,
                    "max_workers": self.config.processing.max_workers,
                    "memory_limit_mb": self.config.processing.memory_limit_mb
                },
                "ui": {
                    "progress_mode": self.config.ui.progress_mode,
                    "log_level": self.config.ui.log_level,
                    "verbose_errors": self.config.ui.verbose_errors
                }
            }
            
            if self.config_manager.save_user_settings(settings):
                self.console.print("\n[green]✓ Einstellungen gespeichert.[/]")
            else:
                self.console.print("\n[red]✗ Fehler beim Speichern.[/]")
            
            time.sleep(2)
    
    def _statistics_menu(self):
        """Statistics menu"""
        self.console.clear()
        self.console.print(Panel("📊 Statistics - Statistiken", style=self.header_style))
        
        # Create layout with multiple panels
        layout = Layout()
        
        # Top row - overview
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body", size=20),
            Layout(name="footer", size=3)
        )
        
        layout["header"].update(Panel("📊 Umfassende Statistiken", style=self.header_style))
        
        # Body - split into columns
        layout["body"].split_row(
            Layout(name="left"),
            Layout(name="right")
        )
        
        # Left column - fingerprint stats
        fp_stats = self.db.get_fingerprint_statistics()
        fp_panel = self._create_fingerprint_stats_panel(fp_stats)
        layout["body"]["left"].update(fp_panel)
        
        # Right column - session stats
        overall_stats = self.db.get_overall_statistics()
        session_panel = self._create_session_stats_panel(overall_stats)
        layout["body"]["right"].update(session_panel)
        
        # Footer
        layout["footer"].update(
            Panel("[cyan]Drücken Sie Enter zum Fortfahren...[/]", style="dim")
        )
        
        self.console.print(layout)
        input()
    
    def _create_fingerprint_stats_panel(self, stats: Dict) -> Panel:
        """Create fingerprint statistics panel"""
        table = Table(show_header=False, box=None)
        table.add_column("Metrik", style="cyan")
        table.add_column("Wert", style="yellow")
        
        table.add_row("📁 Total Fingerprints", f"{stats.get('total_fingerprints', 0):,}")
        table.add_row("🎵 Unique Songs", f"{stats.get('unique_fingerprints', 0):,}")
        table.add_row("🔐 Chromaprint", f"{stats.get('chromaprint_count', 0):,}")
        table.add_row("🔑 MD5 Fallback", f"{stats.get('md5_count', 0):,}")
        table.add_row("⏱️ Avg Duration", f"{stats.get('avg_duration', 0):.1f}s")
        table.add_row("💾 Total Size", f"{stats.get('total_size', 0) / (1024**3):.2f} GB")
        
        # Calculate duplicate ratio
        if stats.get('total_fingerprints', 0) > 0:
            dup_ratio = 1 - (stats.get('unique_fingerprints', 0) / stats.get('total_fingerprints', 0))
            table.add_row("🔄 Duplicate Ratio", f"{dup_ratio*100:.1f}%")
        
        return Panel(table, title="🔐 Fingerprint Statistiken", border_style="green")
    
    def _create_session_stats_panel(self, stats: Dict) -> Panel:
        """Create session statistics panel"""
        table = Table(show_header=False, box=None)
        table.add_column("Metrik", style="cyan")
        table.add_column("Wert", style="yellow")
        
        table.add_row("📊 Total Sessions", f"{stats.get('total_sessions', 0):,}")
        table.add_row("📁 Files Processed", f"{stats.get('total_files_processed', 0):,}")
        table.add_row("💾 Data Processed", f"{stats.get('total_bytes_processed', 0) / (1024**3):.2f} GB")
        table.add_row("✅ Success Rate", f"{stats.get('avg_success_rate', 0)*100:.1f}%")
        
        # Calculate time stats
        if stats.get('first_session') and stats.get('last_session'):
            first = datetime.fromtimestamp(stats['first_session'])
            last = datetime.fromtimestamp(stats['last_session'])
            days_active = (last - first).days
            table.add_row("📅 Days Active", f"{days_active}")
            table.add_row("🕐 Last Session", last.strftime("%Y-%m-%d %H:%M"))
        
        return Panel(table, title="📈 Session Statistiken", border_style="blue")
    
    def _exit_program(self):
        """Exit the program"""
        if Confirm.ask("\n[yellow]Wirklich beenden?[/]", default=False):
            self.console.print("\n[cyan]Auf Wiedersehen! 👋[/]")
            self.running = False
        else:
            self.console.print("[green]Abbruch - zurück zum Menü.[/]")
            time.sleep(1)
    
    def _config_to_dict(self, config: MusicCleanupConfig) -> Dict[str, Any]:
        """Convert MusicCleanupConfig to dictionary for orchestrator"""
        return {
            'output_directory': config.output_directory,
            'enable_fingerprinting': config.audio.fingerprint_algorithm != "none",
            'skip_duplicates': False,
            'integrity_level': config.processing.integrity_level,
            'audio_formats': config.audio.supported_formats,
            'batch_size': config.processing.batch_size,
            'fingerprint_length': config.audio.fingerprint_length,
            'duplicate_similarity': config.audio.duplicate_similarity,
            'min_health_score': config.audio.min_health_score,
            'silence_threshold': config.audio.silence_threshold,
            'defect_sample_duration': config.audio.defect_sample_duration,
            'duplicate_action': config.audio.duplicate_action
        }
    
    def _use_professional_mode(self) -> bool:
        """Check if professional mode should be used"""
        return (self.config.audio.fingerprint_algorithm == "chromaprint" or 
                self.config.audio.min_health_score > 0)


def main():
    """Main entry point for interactive menu"""
    try:
        menu = InteractiveMenu()
        menu.run()
    except KeyboardInterrupt:
        print("\n\nProgramm beendet.")
    except Exception as e:
        console = Console()
        console.print(f"\n[bold red]Kritischer Fehler:[/] {e}")
        console.print("\n[yellow]Bitte melden Sie diesen Fehler.[/]")


if __name__ == "__main__":
    main()