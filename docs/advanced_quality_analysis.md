# Advanced Audio Quality Analysis

Die erweiterte Audio-Qualitätsanalyse erweitert das dj-music-cleanup Tool um professionelle Qualitätsbewertung für DJ-Musikbibliotheken.

## Features

### 1. Spectral Analysis (Frequenz-Analyse)
- **Frequency Cutoff Detection**: Erkennt begrenzte Frequenzbereiche, die auf niedrige Bitraten hindeuten
- **Spectral Centroid**: Misst die "Helligkeit" des Audios
- **Upsampling Detection**: Erkennt wenn niedrige Qualität zu höherer Bitrate konvertiert wurde

### 2. Dynamic Range Analysis
- **Peak-to-RMS Ratio**: Erkennt überkomprimierte Tracks (Loudness War)
- **Clipping Detection**: Findet verzerrte Bereiche durch Übersteuerung
- **Dynamic Range Scoring**: Bewertet die dynamische Bandbreite

### 3. Encoding Quality Analysis
- **Bitrate Verification**: Überprüft tatsächliche vs. gemeldete Bitrate
- **Format-specific Checks**: MP3, FLAC, WAV spezifische Qualitätsprüfungen
- **Stereo Quality**: Erkennt Fake-Stereo (Mono als Stereo)

## Qualitätskategorien

| Kategorie | Score | Frequenz-Cutoff | Dynamic Range | Empfehlung |
|-----------|-------|-----------------|---------------|------------|
| Excellent | 90-100 | ≥20kHz | ≥0.8 | Perfekt für professionelle DJ-Nutzung |
| Good | 75-89 | ≥16kHz | ≥0.6 | Gut für die meisten DJ-Anwendungen |
| Acceptable | 60-74 | ≥14kHz | ≥0.4 | Akzeptabel, aber nicht ideal |
| Poor | <60 | <14kHz | <0.4 | Nicht empfohlen für DJ-Nutzung |

## Erkannte Qualitätsprobleme

### 1. Low Bitrate
- MP3 unter 192kbps wird als problematisch eingestuft
- Empfehlung: Mindestens 256kbps, idealerweise 320kbps

### 2. Upsampling
- Erkennung wenn niedrige Qualität (z.B. 128kbps) zu höherer Bitrate konvertiert wurde
- Typisches Zeichen: Hohe Bitrate aber Frequenz-Cutoff unter 15kHz

### 3. Over-Compression (Loudness War)
- Peak-to-RMS Ratio unter 6dB zeigt extreme Kompression
- Führt zu Ermüdung beim Hören und schlechtem Mix-Verhalten

### 4. Clipping
- Audio-Übersteuerung die zu Verzerrungen führt
- Mehr als 0.1% geclippte Samples gelten als problematisch

### 5. Frequency Cutoff
- Begrenzte Frequenzbereiche deuten auf niedrige Quellqualität
- Typisch: 128kbps MP3 hat Cutoff bei ~16kHz

## Verwendung

### Einzeldatei-Analyse
```python
from music_cleanup.audio import AdvancedQualityAnalyzer

analyzer = AdvancedQualityAnalyzer(min_quality_score=60.0)
report = analyzer.analyze_audio_quality("track.mp3")

print(f"Quality Score: {report.quality_score}/100")
print(f"DJ-Ready: {analyzer.is_dj_ready(report)[0]}")
```

### Kommandozeile
```bash
# Einzeldatei
python examples/advanced_quality_analysis.py track.mp3

# Verzeichnis
python examples/advanced_quality_analysis.py /path/to/music/

# Mit Export
python examples/advanced_quality_analysis.py track.mp3 --export results.json
```

## Integration mit defect_detection

Die erweiterte Qualitätsanalyse ergänzt die bestehende Defekt-Erkennung:

- **defect_detection.py**: Fokus auf strukturelle Defekte (korrupte Header, Truncation, etc.)
- **advanced_quality_analyzer.py**: Fokus auf Audio-Content-Qualität (Kompression, Frequenzen, etc.)

Beide sollten zusammen verwendet werden für vollständige Analyse:

```python
# Vollständige Analyse
quality_report = quality_analyzer.analyze_audio_quality(file_path)
health_report = defect_detector.analyze_audio_health(file_path)

# Kombinierte Entscheidung
is_usable = (
    quality_report.is_high_quality and 
    health_report.is_healthy and
    quality_analyzer.is_dj_ready(quality_report)[0]
)
```

## Technische Details

### Dependencies
- **numpy** (optional): Für erweiterte Sample-Analyse
- **scipy** (optional): Für FFT und Spectral Analysis
- **mutagen** (optional): Für Metadaten-Extraktion

Die Analyse funktioniert auch ohne diese Dependencies, bietet dann aber reduzierte Funktionalität.

### Performance
- Analyse-Dauer: ~30 Sekunden Audio-Sample pro Datei
- WAV-Dateien: Volle Spectral Analysis möglich
- MP3/FLAC: Metadaten-basierte Qualitätsschätzung

### Limitierungen
1. Ohne librosa keine vollständige Spectral Analysis für komprimierte Formate
2. Reference-basierte Qualitätsbewertung noch nicht implementiert
3. Machine Learning Quality Assessment als zukünftige Erweiterung geplant

## Zukünftige Erweiterungen

### Phase 1 (Aktuell implementiert)
- ✅ Spectral Analysis für WAV
- ✅ Dynamic Range Analysis
- ✅ Upsampling Detection
- ✅ Clipping Detection
- ✅ Frequency Cutoff Detection

### Phase 2 (Geplant)
- Reference-basierte Qualitätsbewertung (AcoustID Integration)
- Erweiterte Spectral Analysis mit librosa
- Batch-Processing Optimierungen

### Phase 3 (Zukunft)
- Machine Learning basierte Qualitätsbewertung
- Integration mit Streaming-Dienst APIs für Referenz-Qualität
- Automatische Qualitäts-Verbesserungs-Empfehlungen