# Reference-Based Quality Checking

Die Reference-basierte Qualitätsprüfung vergleicht deine Audio-Dateien mit bekannten Referenz-Versionen aus MusicBrainz und anderen Quellen, um die relative Qualität zu bewerten.

## Funktionsweise

### 1. Track-Identifikation
- **AcoustID**: Generiert akustischen Fingerprint der Audio-Datei
- **MusicBrainz Lookup**: Findet alle bekannten Versionen des gleichen Tracks
- **Confidence Scoring**: Bewertet wie sicher die Übereinstimmung ist

### 2. Referenz-Versionen
Das System findet und analysiert:
- Verschiedene Releases (CD, Vinyl, Digital)
- Verschiedene Masterings
- Verschiedene Bitraten und Formate
- Label-Informationen und Release-Dates

### 3. Qualitätsvergleich
Vergleicht deine Version mit der besten verfügbaren:
- Format (FLAC vs MP3)
- Bitrate
- Release-Qualität (Original vs Remaster)
- Label und Veröffentlichungsjahr

## Konfiguration

### API Keys

#### AcoustID (Optional)
```bash
export ACOUSTID_API_KEY="your_api_key"
```
Ohne eigenen Key wird der Test-Key verwendet (begrenzte Requests).

#### MusicBrainz
Keine API-Key erforderlich, aber User-Agent wird gesetzt.

### Python Dependencies
```bash
pip install pyacoustid musicbrainzngs requests
```

## Verwendung

### Basis-Verwendung
```python
from music_cleanup.audio import AdvancedQualityAnalyzer

# Mit Reference-Check (Standard)
analyzer = AdvancedQualityAnalyzer(enable_reference_check=True)
report = analyzer.analyze_audio_quality("track.mp3")

if report.upgrade_available:
    print(f"Bessere Version verfügbar: {report.reference_comparison.best_reference.format}")
```

### Direkte Reference-Prüfung
```python
from music_cleanup.audio import ReferenceQualityChecker

checker = ReferenceQualityChecker()
result = checker.check_against_references("track.mp3")

print(f"Gefundene Referenzen: {len(result.all_references)}")
print(f"Beste Qualität: {result.best_reference.quality.value}")
print(f"Upgrade verfügbar: {result.upgrade_available}")
```

## Qualitätskategorien

| Kategorie | Beschreibung | Typische Formate |
|-----------|--------------|------------------|
| LOSSLESS | Verlustfreie Qualität | FLAC, WAV, ALAC, AIFF |
| HIGH_BITRATE | Hohe Bitrate | MP3 320kbps, AAC 256kbps |
| MEDIUM_BITRATE | Mittlere Bitrate | MP3 192-256kbps |
| LOW_BITRATE | Niedrige Bitrate | MP3 <192kbps |

## Beispiel-Output

```
📚 Reference Comparison:
  - References Found: 12
  - Best Reference: The Beatles - Yesterday
    • Format: CD
    • Quality: lossless
    • Release: 1 (Remastered) (2009-09-09)
    • Label: Apple Records
  - Quality Score (relative): 65.0%
  - Upgrade Available: ⬆️ Yes
  - Is Best Version: ❌ No

  💡 Recommendations:
    - Better quality available: lossless (CD) - 1 (Remastered) (2009-09-09)
    - Consider getting the Apple Records release
```

## Cache-Management

Reference-Daten werden 7 Tage gecached:
```
~/.dj_music_cleanup/reference_cache/reference_cache.db
```

Cache löschen:
```bash
rm -rf ~/.dj_music_cleanup/reference_cache
```

## Limitierungen

1. **Abhängig von MusicBrainz-Daten**: Nur Tracks die in MusicBrainz vorhanden sind
2. **AcoustID-Genauigkeit**: Stark verzerrte oder beschädigte Files können nicht identifiziert werden
3. **Keine Audio-Feature-Analyse**: Vergleicht nur Metadaten, nicht tatsächliche Audio-Qualität

## Erweiterte Features (Geplant)

### Spotify Integration
```python
# Zukünftig: Audio-Features von Spotify
checker = ReferenceQualityChecker(enable_spotify=True)
```

### Last.fm Integration
```python
# Zukünftig: Popularitäts-Daten
checker = ReferenceQualityChecker(enable_lastfm=True)
```

## Troubleshooting

### "No references found"
- Track ist nicht in MusicBrainz
- Audio-Datei zu stark verändert (Pitch, Tempo)
- Datei zu kurz (<10 Sekunden)

### "AcoustID lookup failed"
- Chromaprint/fpcalc nicht installiert
- API-Limit erreicht (Test-Key)
- Netzwerk-Probleme

### Performance
- Erste Analyse: ~1-3 Sekunden pro Track
- Mit Cache: <100ms pro Track
- Batch-Processing empfohlen für große Bibliotheken