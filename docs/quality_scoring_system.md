# Quality Scoring System

Das Quality Scoring System kombiniert alle Qualitäts-Analysen zu einem einheitlichen Score und bietet automatische Datei-Verwaltung mit Umbenennung und Metadaten-Tagging.

## Überblick

Das System bewertet Audio-Dateien in 4 Hauptkategorien:

1. **Technical Quality** (25%): Format, Bitrate, Encoding
2. **Audio Fidelity** (25%): Dynamic Range, Frequenzgang, Spectral-Analyse  
3. **File Integrity** (15%): Gesundheit, Defekte, Korruption
4. **Reference Quality** (35%): Vergleich mit besten verfügbaren Versionen ⭐

## Scoring-Profile

### DJ Professional (Standard)
Optimiert für professionelle DJ-Nutzung:
- **Höchste Gewichtung auf Reference Quality (35%)** ⭐
- Gleichgewichtige Technical Quality und Audio Fidelity (je 25%)
- Strenge Bewertung basierend auf MusicBrainz-Vergleich

### DJ Casual  
Moderater für Hobby-DJs:
- Fokus auf Technical Quality (30%)
- Reference Quality wichtig (25%)
- Weniger streng bei Dynamic Range

### Archival
Fokus auf Erhaltung und Authentizität:
- Höchste Gewichtung auf Technical Quality (35%)
- Format wichtiger als Bitrate
- Moderate Reference Quality Gewichtung (20%)

## Bewertungsskala

| Grade | Score | Beschreibung | DJ-Tauglichkeit |
|-------|-------|--------------|-----------------|
| A+ | 95-100 | Perfekte Qualität | ⭐ Professionell |
| A | 90-94 | Exzellente Qualität | ⭐ Professionell |
| A- | 85-89 | Sehr gute Qualität | ✅ Gut |
| B+ | 80-84 | Gute Qualität | ✅ Gut |
| B | 75-79 | Ordentliche Qualität | ✅ Akzeptabel |
| B- | 70-74 | Ausreichende Qualität | ⚠️ Grenzwertig |
| C+ | 65-69 | Mäßige Qualität | ⚠️ Problematisch |
| C | 60-64 | Schwache Qualität | ❌ Nicht empfohlen |
| C- | 55-59 | Schlechte Qualität | ❌ Ersetzen |
| D | 50-54 | Sehr schlechte Qualität | ❌ Ersetzen |
| F | 0-49 | Inakzeptable Qualität | 🗑️ Löschen |

## Verwendung

### Basis-Verwendung
```python
from music_cleanup.audio import IntegratedQualityManager, QualityProcessingOptions

# Standard-Konfiguration für DJs
options = QualityProcessingOptions(
    scoring_profile=ScoringProfile.DJ_PROFESSIONAL,
    rename_files=True,
    tag_metadata=True
)

manager = IntegratedQualityManager(options)
result = manager.process_file("track.mp3")

print(f"Score: {result.unified_score.final_score:.1f}")
print(f"Grade: {result.unified_score.grade}")
print(f"Action: {result.unified_score.recommended_action}")
```

### Batch-Processing
```python
# Verzeichnis mit allen Optionen verarbeiten
options = QualityProcessingOptions(
    rename_files=True,
    rename_pattern="{artist} - {title} [QS{score}%]",
    organize_files=True,
    output_directory="./Organized_Music",
    auto_quarantine_below=40.0
)

results = manager.process_directory("/path/to/music", recursive=True)
report = manager.generate_quality_report(results, "quality_report.json")
```

### Kommandozeile
```bash
# Einzeldatei mit Umbenennung
python examples/quality_scoring_demo.py track.mp3 --rename

# Verzeichnis mit Organisation
python examples/quality_scoring_demo.py /music --organize --output-dir ./Sorted

# Mit detailliertem Report
python examples/quality_scoring_demo.py /music --export-report collection_report.json
```

## Datei-Umbenennung

### Standard-Pattern
```
{artist} - {title} [QS{score}%]
```
**Beispiel:** `The Beatles - Yesterday [QS87%].mp3`

### Verfügbare Platzhalter
- `{title}` - Song-Titel
- `{artist}` - Künstler
- `{score}` - Quality Score in Prozent (z.B. "87")
- `{grade}` - Letter Grade (A+, B, etc.)
- `{original}` - Original-Dateiname

### Benutzerdefinierte Pattern
```python
options.rename_pattern = "{title} [{grade}] - {artist}"
# Ergebnis: "Yesterday [A-] - The Beatles.mp3"

options.rename_pattern = "[{score}%] {original}"
# Ergebnis: "[87%] The Beatles - Yesterday.mp3"

options.rename_pattern = "{artist} - {title} [QS{score}%]"  # Standard
# Ergebnis: "The Beatles - Yesterday [QS87%].mp3"
```

## Metadaten-Tagging

Das System fügt umfangreiche Qualitäts-Metadaten hinzu:

### Standard-Tags (alle Scores in Prozent)
- `DJ_QUALITY_SCORE`: Haupt-Score (z.B. "87.3%")
- `DJ_QUALITY_GRADE`: Letter Grade (z.B. "A-")
- `DJ_QUALITY_ACTION`: Empfohlene Aktion
- `DJ_QUALITY_TECH`: Technical Quality Score (z.B. "85.2%")
- `DJ_QUALITY_AUDIO`: Audio Fidelity Score (z.B. "89.1%")
- `DJ_QUALITY_INTEGRITY`: File Integrity Score (z.B. "95.0%")
- `DJ_QUALITY_REFERENCE`: Reference Quality Score (z.B. "78.5%") ⭐
- `DJ_QUALITY_CONFIDENCE`: Confidence Level (z.B. "92.3%")

### Erweiterte Tags
- `DJ_QUALITY_ANALYZED`: JSON mit Timestamp und Details
- `DJ_REFERENCE_BEST`: JSON mit bester Referenz-Version

### Format-Unterstützung
- **MP3**: ID3v2 TXXX Tags
- **FLAC**: Vorbis Comments
- **M4A**: iTunes-kompatible Tags
- **WAV**: ID3v2 (falls unterstützt)

## Quality-Info Management

**Quality-Information wird NICHT in Ordner-Struktur organisiert, sondern in:**

### 1. Dateinamen
```
The Beatles - Yesterday [QS87%].mp3
Daft Punk - One More Time [QS92%].flac
Artist - Low Quality Track [QS43%].mp3
```

### 2. Metadaten-Tags
Alle Quality-Scores werden direkt in die Audio-Metadaten geschrieben:
- Haupt-Score in Prozent
- Alle Kategorie-Scores in Prozent  
- Reference-Quality mit hoher Gewichtung (35%)
- Empfohlene Aktionen

### 3. Vorteile dieses Ansatzes
- ✅ Quality-Info bleibt bei der Datei
- ✅ Keine komplexe Ordner-Struktur
- ✅ DJ-Software kann Tags lesen
- ✅ Portable zwischen Systemen
- ✅ Einfache Sortierung nach Score

## Score-Berechnung Details

### Technical Quality (25%)
```python
technical_score = weighted_average([
    (bitrate_score, 0.35),      # 320kbps MP3 = 100, 128kbps = 50
    (format_score, 0.35),       # FLAC = 100, MP3 = 80, WMA = 60
    (frequency_score, 0.30)     # 20kHz = 100, 16kHz = 75, 12kHz = 40
])
```

### Audio Fidelity (25%)
```python
audio_score = weighted_average([
    (dynamic_range_score, 0.35),    # DR > 0.8 = 100, < 0.2 = compressed
    (spectral_score, 0.25),         # Spectral analysis quality
    (100 - clipping_penalty, 0.25), # Clipping detection
    (100 - noise_penalty, 0.15)     # Noise floor analysis
])
```

### File Integrity (15%)
```python
integrity_score = weighted_average([
    (health_score, 0.70),           # Defect detection results
    (100 - defect_penalty, 0.30)   # Additional defect penalties
])
```

### Reference Quality (35%) ⭐ HÖCHSTE GEWICHTUNG
```python
reference_score = weighted_average([
    (reference_comparison_score, 0.80),  # MusicBrainz comparison
    (100 - upgrade_penalty, 0.20)       # Penalty if better version exists
])
```

## Empfohlene Workflows

### 1. Neue Musiksammlung bewerten
```bash
python quality_scoring_demo.py /new_music \
  --export-report initial_assessment.json
```

### 2. Sammlung mit Scoring verarbeiten
```bash
python quality_scoring_demo.py /music_library \
  --rename \
  --export-report collection_quality.json
```

### 3. Niedrige Qualität identifizieren
```python
options = QualityProcessingOptions(
    auto_quarantine_below=50.0,  # Sehr streng
    rename_pattern="{artist} - {title} [QS{score}%] [POOR]",
    tag_metadata=True
)
```

### 4. Archival-Qualität prüfen
```python
options = QualityProcessingOptions(
    scoring_profile=ScoringProfile.ARCHIVAL,
    tag_metadata=True,
    rename_files=False  # Originalnamen beibehalten
)
```

## Troubleshooting

### Niedrige Scores trotz guter Dateien
- Prüfe Reference-Check: Möglicherweise bessere Version verfügbar
- Wähle weniger strenges Profil (DJ_CASUAL)
- Custom Weights für deine Anforderungen

### Umbenennung schlägt fehl
- Prüfe Schreibrechte im Verzeichnis
- Vermeide Sonderzeichen in Pattern
- Aktiviere `backup_original_names=True`

### Metadaten-Tagging funktioniert nicht
- Installiere `mutagen`: `pip install mutagen`
- Prüfe Datei-Format-Unterstützung
- Manche Formate sind Read-Only

### Performance-Optimierung
- Reduziere `analysis_duration` für schnellere Analyse
- Deaktiviere Reference-Check für lokale Analyse
- Verwende Batch-Processing für große Sammlungen