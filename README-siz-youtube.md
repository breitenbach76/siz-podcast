# SiZ YouTube Description Generator

Erweitert den Content-Generator um YouTube-spezifische Funktionen für den Podcast "Schweigen ist Zustimmung".

## Features

- ✅ **WordPress-Integration** - Teaser automatisch via REST API laden (mit Cache)
- ✅ **Timestamps aus SRT** - Automatische Kapitelmarken aus Transkriptionen
- ✅ **KI-generierte Kapitel** - Claude analysiert Transkripte für bessere Timestamps
- ✅ **SEO-optimierte Beschreibungen** - Keywords, Hashtags, strukturierte Links
- ✅ **Bulk-Update via API** - Alle 69 Episoden automatisch aktualisieren
- ✅ **Dry-Run Modus** - Vorschau ohne Änderungen

## Installation

```bash
# 1. Abhängigkeiten installieren
pip install requests anthropic google-auth-oauthlib google-api-python-client

# 2. Script in siz-scripts Ordner kopieren
cp siz-youtube-generator.py ~/Documents/siz-scripts/

# 3. .env um YouTube-Credentials erweitern (optional für API-Upload)
```

## Voraussetzungen

### Für Beschreibungs-Generierung:
- Python 3.10+
- Transkripte in `./siz_transkripte/` (SiZ_01.txt, SiZ_01.srt, ...)
- Internet-Verbindung (für WordPress API)
- `ANTHROPIC_API_KEY` in `.env` (optional, für KI-Timestamps)

### Für YouTube Bulk-Upload:
1. **Google Cloud Project erstellen**: https://console.cloud.google.com/
2. **YouTube Data API v3 aktivieren**
3. **OAuth 2.0 Client ID erstellen** (Desktop App)
4. **`client_secrets.json` herunterladen** und in Script-Ordner legen

## Verwendung

### 1. WordPress-Cache laden (optional, passiert automatisch)

```bash
# Nur Cache aktualisieren ohne Generierung
python siz-youtube-generator.py --refresh-cache
```

### 2. Alle Beschreibungen generieren

```bash
# Mit WordPress-Teaser + KI-Timestamps (empfohlen)
python siz-youtube-generator.py --generate

# Mit frischen WordPress-Daten (Cache ignorieren)
python siz-youtube-generator.py --generate --refresh

# Ohne KI (nur regelbasiert, schneller)
python siz-youtube-generator.py --generate --no-ai
```

Ausgabe: `./youtube_descriptions/SiZ_01_youtube.txt` bis `SiZ_69_youtube.txt`

### 3. Einzelne Episode testen

```bash
python siz-youtube-generator.py --episode 42
```

### 3. Video-IDs vom Kanal holen

```bash
python siz-youtube-generator.py --fetch-videos
```

Das Script versucht, Episodennummern aus den Video-Titeln zu extrahieren.
Prüfe `siz-youtube-ids.json` und ergänze fehlende IDs manuell.

### 4. Bulk-Update durchführen

```bash
# Erst Dry-Run (nur Vorschau)
python siz-youtube-generator.py --update --dry-run

# Dann Live-Update
python siz-youtube-generator.py --update
```

## Dateistruktur

```
~/Documents/siz-scripts/
├── siz-youtube-generator.py    # Dieses Script
├── siz-generator.py            # Bestehender WordPress-Generator
├── .env                        # Credentials (NICHT commiten!)
├── client_secrets.json         # Google OAuth (NICHT commiten!)
├── youtube_token.json          # Auto-generiert nach Auth
├── siz-youtube-ids.json        # Episode → Video ID Mapping
├── siz-wordpress-cache.json    # WordPress-Episoden Cache (auto-generiert)
├── siz_transkripte/            # Transkripte (TXT + SRT)
│   ├── SiZ_01.txt
│   ├── SiZ_01.srt
│   └── ...
└── youtube_descriptions/       # Generierte Beschreibungen
    ├── SiZ_01_youtube.txt
    └── ...
```

## WordPress-Integration

Das Script holt die Episoden-Teaser automatisch von der WordPress REST API:

```
https://schweigenistzustimmung.de/wp-json/wp/v2/episodes
```

**Caching:**
- Beim ersten Aufruf werden alle Episoden geladen und lokal gespeichert
- Weitere Aufrufe nutzen den Cache (schnell + offline-fähig)
- Cache wird nach 24h als "stale" markiert (Hinweis im Output)
- Mit `--refresh` wird der Cache aktualisiert

## YouTube-Beschreibungs-Format

```
[SEO-HOOK - erste 160 Zeichen, keywords-reich]

[TEASER - bewährter 3-Akt-Stil aus WordPress]

⏱️ KAPITEL
00:00 Intro
03:24 Thema 1
...

👉 MEHR VON UNS
🔔 Kanal abonnieren: [Link mit sub_confirmation]
🎧 Alle Plattformen: schweigenistzustimmung.de
💬 Community: Discord

💚 UNTERSTÜTZEN
Steady, PayPal, IBAN

📱 SOCIAL MEDIA
Instagram, Bluesky

In dieser Folge erwähnt:
• Person 1
• Organisation 2

#Politik #Podcast #Deutschland #[Themen-Hashtags]
```

## Workflow-Integration

### Für neue Episoden:

1. Aufnahme → Schnitt → Export
2. Whisper-Transkription (TXT + SRT)
3. `python siz-generator.py` für WordPress
4. `python siz-youtube-generator.py --episode XX` für YouTube
5. Upload zu YouTube mit generierter Beschreibung

### Für Bulk-Update bestehender Episoden:

1. `python siz-youtube-generator.py --generate`
2. Stichproben prüfen in `./youtube_descriptions/`
3. `python siz-youtube-generator.py --update --dry-run`
4. Bei Zufriedenheit: `python siz-youtube-generator.py --update`

## Troubleshooting

### "Anthropic API nicht verfügbar"
```bash
pip install anthropic
# .env prüfen: ANTHROPIC_API_KEY=sk-ant-...
```

### "Google API nicht verfügbar"
```bash
pip install google-auth-oauthlib google-api-python-client
```

### "Credentials-Datei nicht gefunden"
1. Google Cloud Console öffnen
2. APIs & Services → Credentials
3. OAuth 2.0 Client ID erstellen (Desktop App)
4. JSON herunterladen → `client_secrets.json`

### "Token abgelaufen"
```bash
rm youtube_token.json
# Nächster API-Aufruf startet neue Authentifizierung
```

## Anpassungen

### Hashtags erweitern
In `siz-youtube-generator.py` die `TOPIC_KEYWORDS` dict erweitern:

```python
TOPIC_KEYWORDS = {
    'neues_thema': ['Keyword1', 'Keyword2'],
    ...
}
```

### Template ändern
`YOUTUBE_TEMPLATE` Variable im Script anpassen.

### Kapitel-Mindestlänge ändern
```python
config = Config(
    min_chapter_duration_seconds=300  # 5 Minuten statt 3
)
```

## Quota-Limits

YouTube Data API hat Tageslimits:
- ~10.000 Quota-Units pro Tag
- `videos.update` kostet 50 Units
- **Max. ~200 Video-Updates pro Tag**

Bei 69 Episoden: Kein Problem, aber bei häufigen Updates aufpassen!

---

Erstellt für: Schweigen ist Zustimmung Podcast
Autor: Claude (Anthropic)
