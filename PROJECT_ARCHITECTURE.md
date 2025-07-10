# DJ Music Cleanup Tool - Projektarchitektur & Struktur

## 📁 Projektstruktur

```
dj-music-cleanup/
│
├── organized/                  # ✅ Hauptausgabe (beste Qualität)
│   ├── Electronic/
│   │   ├── 2020s/
│   │   ├── 2010s/
│   │   └── ...
│   ├── House/
│   ├── Rock/
│   └── README.md              # Dokumentation der Organisation
│
├── rejected/                   # ❌ Aussortierte Dateien
│   ├── duplicates/            # Schlechtere Duplikate
│   ├── low_quality/           # Unter Qualitätsschwelle
│   ├── corrupted/             # Defekte Dateien
│   └── README.md              # Anweisungen für abgelehnte Dateien
│
├── config/                      # Konfigurationsdateien
│   ├── default.json            # Standard-Konfiguration
│   ├── development.json        # Entwicklungs-Einstellungen
│   ├── production.json         # Produktions-Einstellungen
│   └── advanced.json           # Erweiterte Profi-Einstellungen
│
├── docs/                       # Dokumentation
│   ├── installation.md         # Installationsanleitung
│   ├── usage.md               # Benutzerhandbuch
│   ├── quality_scoring_system.md    # Qualitätsbewertungs-Dokumentation
│   ├── reference_quality_checking.md # Referenz-Qualitätsprüfung
│   └── advanced_quality_analysis.md  # Fortgeschrittene Analyse
│
├── examples/                   # Beispielskripte
│   ├── basic_usage.py         # Einfache Verwendungsbeispiele
│   ├── advanced_quality_analysis.py # Erweiterte Analysebeispiele
│   └── quality_scoring_demo.py      # Demo für Qualitätsbewertung
│
├── scripts/                    # Utility-Skripte
│   ├── install.sh             # Installations-Skript
│   └── migrate_database.py    # Datenbank-Migrationstool
│
├── src/music_cleanup/         # Hauptquellcode
│   ├── __init__.py           # Package-Initialisierung mit Version
│   │
│   ├── audio/                # Audio-Verarbeitungsmodule
│   │   ├── __init__.py
│   │   ├── advanced_quality_analyzer.py  # Erweiterte Qualitätsanalyse
│   │   ├── defect_detection.py          # Fehler- und Defekterkennung
│   │   ├── duplicate_detection.py       # Duplikaterkennung
│   │   ├── fingerprinting.py            # Audio-Fingerprinting
│   │   ├── integrated_quality_manager.py # Integriertes Qualitätsmanagement
│   │   ├── quality_scoring.py           # Einheitliches Bewertungssystem
│   │   └── reference_quality_checker.py # Referenz-Qualitätsprüfung
│   │
│   ├── cli/                  # Command Line Interface
│   │   ├── __init__.py
│   │   ├── main.py          # Haupt-CLI-Einstiegspunkt
│   │   └── interactive_menu.py # Interaktives Menüsystem
│   │
│   ├── core/                 # Kernfunktionalität
│   │   ├── __init__.py
│   │   ├── async_processor.py          # Asynchrone Verarbeitung
│   │   ├── batch_processor.py          # Batch-Verarbeitung
│   │   ├── chunk_manager.py            # Speicher-Chunk-Verwaltung
│   │   ├── config.py                   # Legacy-Konfiguration (deprecated)
│   │   ├── config_manager.py           # Neues Konfigurationssystem
│   │   ├── constants.py                # Globale Konstanten
│   │   ├── corruption_handler.py       # Korruptions-Behandlung
│   │   ├── database_migration.py       # DB-Migrationsfunktionen
│   │   ├── directory_manager.py        # Verzeichnisverwaltung (NEU)
│   │   ├── duplicate_handler.py        # Duplikat-Verwaltung
│   │   ├── file_analyzer.py            # Einheitliche Dateianalyse (NEU)
│   │   ├── orchestrator.py             # Legacy-Orchestrator (deprecated)
│   │   ├── orchestrator_refactored.py  # Haupt-Orchestrator
│   │   ├── orchestrator_professional.py # Professioneller Orchestrator
│   │   ├── pipeline_executor.py        # Pipeline-Ausführung
│   │   ├── recovery.py                 # Crash-Recovery-System
│   │   ├── rollback.py                 # Rollback-Funktionalität
│   │   ├── streaming.py                # Streaming-Konfiguration
│   │   ├── transactions.py             # Transaktionale Operationen
│   │   ├── unified_database.py         # Vereinheitlichte Datenbank
│   │   └── unified_schema.py           # Datenbankschema-Definitionen
│   │
│   ├── modules/              # Einfache Module (für Kompatibilität)
│   │   ├── __init__.py
│   │   ├── simple_file_discovery.py    # Datei-Erkennung
│   │   ├── simple_file_organizer.py    # Datei-Organisation
│   │   ├── simple_fingerprinter.py     # Basis-Fingerprinting
│   │   ├── simple_metadata_manager.py  # Metadaten-Extraktion
│   │   └── simple_quality_analyzer.py  # Basis-Qualitätsanalyse
│   │
│   └── utils/                # Hilfsfunktionen
│       ├── __init__.py
│       ├── decorators.py             # Utility-Decorators (NEU)
│       ├── error_handler.py          # Fehlerbehandlung
│       ├── integrity.py              # Integritätsprüfung
│       ├── progress.py               # Fortschrittsanzeige
│       ├── setup_directories.py      # Verzeichnis-Setup (NEU)
│       └── tool_checker.py           # Externe Tool-Prüfung
│
├── tests/                    # Testsuite
│   ├── __init__.py
│   ├── fixtures/            # Test-Fixtures
│   │   └── conftest.py
│   ├── integration/         # Integrationstests
│   │   └── test_cli_workflows.py
│   ├── unit/               # Unit-Tests
│   │   └── test_orchestrator.py
│   ├── test_config_manager.py
│   ├── test_package_structure.py
│   └── test_unified_database.py
│
├── .gitignore              # Git-Ignorierungsdatei
├── CHANGELOG.md            # Änderungsprotokoll
├── LICENSE                 # MIT-Lizenz
├── README.md              # Hauptdokumentation
├── pyproject.toml         # Python-Projektdefinition
├── requirements.txt       # Python-Abhängigkeiten
└── setup.py              # Legacy-Setup (für Kompatibilität)
```

## 🏗️ Gesamtarchitektur

### 1. **Schichtenarchitektur**

```
┌─────────────────────────────────────────────────────────────┐
│                    CLI Interface Layer                       │
│  • Benutzerinteraktion (CLI & Interaktives Menü)           │
│  • Argument-Parsing und Validierung                        │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    Orchestration Layer                       │
│  • Pipeline-Koordination                                    │
│  • Workflow-Management                                      │
│  • Transaktionale Sicherheit                              │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    Processing Layer                          │
│  • Batch-Verarbeitung                                      │
│  • Streaming-Architektur                                   │
│  • Parallelisierung                                        │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    Business Logic Layer                      │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐          │
│  │Audio Module │ │Core Module  │ │Simple Module│          │
│  │• Fingerprint│ │• File Mgmt  │ │• Basic Ops │          │
│  │• Quality    │ │• Database   │ │• Fallbacks │          │
│  │• Defects    │ │• Recovery   │ │             │          │
│  └─────────────┘ └─────────────┘ └─────────────┘          │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    Data Layer                                │
│  • Unified SQLite Database                                  │
│  • File System Operations                                  │
│  • External Services (MusicBrainz, AcoustID)              │
└─────────────────────────────────────────────────────────────┘
```

### 2. **Datenfluss-Pipeline**

```
Eingabe (Musikdateien)
         ↓
[1] Discovery Phase
    • Datei-Erkennung
    • Format-Validierung
    • Größenprüfung
         ↓
[2] Analysis Phase
    • Metadaten-Extraktion
    • Qualitätsanalyse
    • Integritätsprüfung
         ↓
[2.5] Corruption Filter (KRITISCH!)
    • Defekt-Erkennung
    • Korruptions-Prüfung
    • Quarantäne defekter Dateien
         ↓
[3] Duplicate Detection (nur gesunde Dateien!)
    • Fingerprint-Generierung
    • Ähnlichkeitsvergleich
    • Duplikat-Gruppierung
         ↓
[4] Organization Phase
    • Ordnerstruktur erstellen
    • Dateien verschieben/kopieren
    • Metadaten aktualisieren
         ↓
Ausgabe (Organisierte Bibliothek)
```

### 3. **Kernkomponenten**

#### **Orchestrator** (`core/orchestrator_refactored.py`)
- Zentrale Koordination aller Operationen
- Delegiert an spezialisierte Handler
- Verwaltet den Gesamtworkflow

#### **FileAnalyzer** (`core/file_analyzer.py`) - NEU
- Einheitliche Dateianalyse
- Konsolidiert alle Analyse-Operationen
- Reduziert Code-Duplikation

#### **UnifiedDatabase** (`core/unified_database.py`)
- Zentrale SQLite-Datenbank
- Drei Hauptschemas:
  - Fingerprints (Audio-Fingerabdrücke)
  - Operations (Recovery/Undo)
  - Progress (Fortschritt/Statistiken)

#### **BatchProcessor** (`core/batch_processor.py`)
- Memory-effiziente Batch-Verarbeitung
- O(1) Speicherkomplexität
- Streaming-Architektur

#### **Audio Module** (`audio/`)
- **QualityScoringSystem**: Einheitliche Bewertung (0-100)
- **DefectDetector**: Erkennt Audiofehler
- **DuplicateDetector**: Findet identische/ähnliche Dateien
- **IntegratedQualityManager**: Kombiniert alle Qualitätsprüfungen

### 4. **Sicherheitsmechanismen**

#### **Transaktionale Sicherheit**
```python
# Atomic Operations mit Rollback
with TransactionManager() as tm:
    tm.move_file(source, target)
    tm.update_metadata(file_id, metadata)
    # Bei Fehler: Automatischer Rollback
```

#### **Crash Recovery**
- Automatische Checkpoints alle 5 Minuten
- Signal-Handler für sauberes Herunterfahren
- Recovery von letztem bekannten Zustand

#### **Integritätsprüfung**
- 5 Stufen: Basic → Checksum → Metadata → Deep → Paranoid
- Kontinuierliche Validierung während der Verarbeitung

### 5. **Konfigurationssystem**

#### **Hierarchische Konfiguration**
1. Standardwerte (`default.json`)
2. Umgebungsspezifisch (`development.json`, `production.json`)
3. Benutzerdefiniert (`~/.music-cleanup/config.json`)
4. CLI-Parameter (höchste Priorität)

#### **Konfigurationsbeispiel**
```json
{
  "audio": {
    "supported_formats": [".mp3", ".flac", ".wav"],
    "min_health_score": 50.0,
    "fingerprint_algorithm": "chromaprint"
  },
  "processing": {
    "batch_size": 100,
    "max_workers": 4,
    "integrity_level": "checksum"
  },
  "streaming": {
    "memory_limit_mb": 1024,
    "chunk_size_mb": 64
  }
}
```

### 6. **Erweiterungspunkte**

#### **Plugin-System** (geplant)
```python
# Beispiel für zukünftige Plugin-Architektur
class AudioAnalyzerPlugin(ABC):
    @abstractmethod
    def analyze(self, file_path: str) -> AnalysisResult:
        pass

# Registrierung
plugin_manager.register("custom_analyzer", CustomAnalyzerPlugin())
```

#### **Neue Analyzer hinzufügen**
1. Implementiere Interface in `audio/`
2. Registriere in `FileAnalyzer`
3. Füge Konfigurationsoption hinzu

### 7. **Performance-Optimierungen**

- **Streaming**: Konstanter Speicherverbrauch (20-25MB)
- **Parallelisierung**: Multi-Threading für CPU-intensive Operationen
- **Lazy Loading**: Komponenten werden erst bei Bedarf geladen
- **Caching**: Fingerprint-Cache in Datenbank
- **Batch-Verarbeitung**: Reduziert I/O-Overhead

### 8. **Best Practices**

- **SOLID-Prinzipien**: Single Responsibility, Open/Closed
- **DRY**: Wiederverwendbare Komponenten
- **Type Safety**: Vollständige Type Hints
- **Error Handling**: Decorator-basiert, konsistent
- **Logging**: Strukturiertes Logging auf allen Ebenen
- **Testing**: Unit-, Integration- und Performance-Tests

## 📊 Metriken & Limits

- **Max. Dateigröße**: 5GB pro Datei
- **Min. Dateigröße**: 100KB
- **Batch-Größe**: 50-1000 Dateien (konfigurierbar)
- **Memory-Limit**: 1024MB (konfigurierbar)
- **Checkpoint-Intervall**: 300 Sekunden
- **Unterstützte Formate**: MP3, FLAC, WAV, M4A, AAC, OGG

## 🔮 Zukünftige Entwicklungen

1. **Async/Await**: Vollständige asynchrone Verarbeitung
2. **Web-Interface**: REST API und Web-UI
3. **Cloud-Integration**: S3, Google Drive Support
4. **Machine Learning**: Automatische Genre-Erkennung
5. **Distributed Processing**: Cluster-Support für sehr große Bibliotheken